"""Check permission, debit, publication and route boundaries without live services."""

from dataclasses import replace
from datetime import timedelta
import threading
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from trinity.auth.permissions import Principal
from trinity.errors import Problem
from trinity.main import create_app
from trinity.queries.choice_service import ChoiceService
from trinity.queries.choices import resolve_choices, parse_choice_input
from test_choices import choice_codec
from test_preview_provenance import frozen_fixture
from test_preview_service import Database


class ChoiceServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = Database()
        self.user = Principal('synthetic','analyst',uuid4())
        self.pinned, _ = frozen_fixture()
        self.execution = Mock(deployment_id=uuid4(),daemon_id='synthetic')
        self.factory = Mock(return_value=self.execution)
        self.codecs = Mock(side_effect=choice_codec)
        self.service = ChoiceService(self.db,self.factory,codec_factory=self.codecs)
        self.mocks = {}
        for name, value in {'resolve_session':self.user,'read_pinned_publication':self.pinned,
                            'repository.reserve_rate':None,'repository.reserve_capacity':{'request_id':uuid4()}}.items():
            patcher = patch('trinity.queries.choice_service.'+name,return_value=value)
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)

    def prepare(self, pairs=(), dataset='facility_outages', choice='facilities', **kwargs):
        return self.service.prepare('synthetic',dataset,choice,pairs,**kwargs)

    def failure(self, code, *args, **kwargs):
        with self.assertRaises(Problem) as caught:
            self.prepare(*args,**kwargs)
        self.assertEqual(caught.exception.code,code)

    def test_denial_precedes_parsing_debit_and_configuration(self):
        self.mocks['resolve_session'].return_value = replace(self.user,role='viewer')
        self.failure('dataset_not_found',[('limit','bad')])
        self.failure('dataset_not_found',dataset='unknown')
        self.failure('dataset_not_found',dataset='national_outages')
        self.mocks['repository.reserve_rate'].assert_not_called()
        self.mocks['read_pinned_publication'].assert_not_called()
        self.codecs.assert_not_called()
        self.factory.assert_not_called()

    def test_invalid_route_and_primitive_shape_do_not_debit(self):
        self.failure('dataset_not_found',choice='generators')
        self.failure('invalid_request',[('search','a'),('search','b')])
        self.failure('invalid_request',body=b'{}')
        self.mocks['repository.reserve_rate'].assert_not_called()

    def test_semantics_and_cursor_failures_keep_one_debit(self):
        for pairs, dataset, choice, code in [
            ([], 'generator_outages','generators','invalid_request'),
            ([('start','2026-01-02'),('end','2026-01-01')],'facility_outages','facilities','invalid_request'),
            ([('cursor','forged')],'facility_outages','facilities','invalid_cursor')]:
            self.mocks['repository.reserve_rate'].reset_mock()
            self.failure(code,pairs,dataset,choice)
            self.mocks['repository.reserve_rate'].assert_called_once()
            self.mocks['read_pinned_publication'].assert_not_called()
            self.factory.assert_not_called()

    def test_rate_denial_precedes_cursor_checks(self):
        self.mocks['repository.reserve_rate'].return_value = 7
        self.failure('rate_limited',[('cursor','forged')])
        self.codecs.assert_not_called()

    def test_reauthorization_precedes_publication(self):
        for second in (replace(self.user,role='viewer'),replace(self.user,session_id=uuid4())):
            self.mocks['resolve_session'].side_effect = [self.user,second]
            self.failure('dataset_not_found' if second.role=='viewer' else 'invalid_session')
            self.mocks['read_pinned_publication'].assert_not_called()
        self.factory.assert_not_called()

    def token(self, pairs=(), choice='facilities', dataset='facility'):
        request = parse_choice_input(pairs,choice)
        op = resolve_choices(dataset,choice,request,self.pinned.publication)
        return choice_codec().encode(op,'01')

    def test_changed_publication_and_absence_fail_before_execution(self):
        token = self.token()
        self.mocks['read_pinned_publication'].return_value = None
        self.failure('data_unavailable')
        self.failure('publication_changed',[('cursor',token)])
        changed = replace(self.pinned,publication=self.pinned.publication.model_copy(update={'publication_event_id':uuid4()}))
        self.mocks['read_pinned_publication'].return_value = changed
        self.failure('publication_changed',[('cursor',token)])
        self.factory.assert_not_called()

    def test_bookmark_binds_search_parent_limit_and_route(self):
        cases = [
            (self.token([('search','Plant')]), [], 'facility_outages','facilities'),
            (self.token([('limit','1')]), [], 'facility_outages','facilities'),
            (self.token([('facility','01')],'generators','generator'), [('facility','1')], 'generator_outages','generators'),
            (self.token(), [], 'generator_outages','facilities'),
            (self.token(dataset='generator'), [('facility','01')], 'generator_outages','generators'),
        ]
        for token, pairs, dataset, choice in cases:
            self.failure('invalid_cursor',pairs+[('cursor',token)],dataset,choice)
        self.factory.assert_not_called()

    def test_defaults_match_explicit_dates_and_no_transaction_reaches_execution(self):
        token = self.token()
        public = self.pinned.publication
        implicit,_ = self.prepare([('cursor',token)])
        explicit,_ = self.prepare([('cursor',token),('start',(public.latest_observation_date-timedelta(days=29)).isoformat()),
                                  ('end',public.latest_observation_date.isoformat())])
        self.assertEqual(implicit.query,explicit.query)
        self.assertEqual(explicit.query.after,'01')
        self.assertEqual(self.db.open_transactions,0)
        self.assertGreater(explicit.deadline.remaining(),29)
        self.execution.execute.side_effect = lambda prepared: self.assertEqual(self.db.open_transactions,0) or prepared
        self.service.execute('synthetic','facility_outages','facilities',[])

    def test_capacity_failure_and_cancellation_close_or_prevent_execution(self):
        self.mocks['repository.reserve_capacity'].return_value = None
        self.failure('rate_limited')
        self.execution.close.assert_called_once()
        stopped = threading.Event(); stopped.set()
        self.failure('query_timeout',cancelled=stopped)
        self.execution.execute.assert_not_called()

    def test_real_http_adapter_preserves_authorization_order_and_duplicates(self):
        with TestClient(create_app(service=Mock(),choice_service=self.service)) as client:
            url = '/api/v1/datasets/facility_outages/facilities'
            self.assertEqual(client.get(url).status_code,401)
            headers = {'Authorization':'Bearer '+'x'*43}
            self.mocks['resolve_session'].return_value = replace(self.user,role='viewer')
            self.assertEqual(client.get(url+'?limit=bad',headers=headers).status_code,404)
            self.mocks['resolve_session'].return_value = self.user
            response = client.get(url+'?limit=1&limit=2',headers=headers)
            self.assertEqual(response.status_code,422)
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertIn('x-request-id',response.headers)
            self.mocks['repository.reserve_rate'].assert_not_called()

    def test_routes_are_registered_and_share_default_execution_gate(self):
        auth = Mock(database=self.db)
        with TestClient(create_app(service=auth)) as client:
            self.assertFalse(client.app.state.preview_enabled)
            with patch('trinity.queries.config.execution_factory') as factory:
                response = client.get('/api/v1/datasets/generator_outages/generators?facility=01',
                                      headers={'Authorization':'Bearer '+'x'*43})
                self.assertEqual(response.status_code,503)
                factory.assert_not_called()
