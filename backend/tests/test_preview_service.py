"""Check orchestration order with controlled adapters; no live database or Docker."""
from contextlib import contextmanager
from dataclasses import replace
import json
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from trinity.auth.permissions import Principal
from trinity.errors import Problem
from trinity.main import create_app
from trinity.queries.config import preview_execution_factory
from trinity.queries.service import PreviewService
from trinity.queries.preview import ResolvedPreview
from test_preview_unit import codec, page, publication
from test_preview_provenance import frozen_fixture


class Database:
    def __init__(self):
        self.events = []
        self.open_transactions = 0

    @contextmanager
    def transaction(self, deadline, **kwargs):
        deadline.remaining()
        self.events.append('begin')
        self.open_transactions += 1
        try:
            yield object()
        except Exception:
            self.events.append('rollback')
            raise
        else:
            self.events.append('commit')
        finally:
            self.open_transactions -= 1


class PreviewServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = Database()
        self.user = Principal('synthetic', 'analyst', uuid4())
        self.pinned, _ = frozen_fixture()
        self.execution = Mock(deployment_id=uuid4(), daemon_id='synthetic')
        self.factory = Mock(return_value=self.execution)
        self.codec_factory = Mock(side_effect=codec)
        self.service = PreviewService(self.db, self.factory, codec_factory=self.codec_factory)
        targets = {'resolve_session':self.user, 'read_pinned_publication':self.pinned,
                   'repository.reserve_rate':None, 'repository.reserve_capacity':{'request_id':uuid4()}}
        self.mocks = {}
        for name, value in targets.items():
            p = patch('trinity.queries.service.' + name, return_value=value)
            self.mocks[name] = p.start()
            self.addCleanup(p.stop)
        p = patch('trinity.publication.repository.read_preview_publication', return_value=self.pinned)
        self.provenance = p.start()
        self.addCleanup(p.stop)

    def prepare(self, dataset='national_outages', pairs=(), **kwargs):
        return self.service.prepare('synthetic-token', dataset, pairs, **kwargs)

    def failure(self, code, *args, **kwargs):
        with self.assertRaises(Problem) as caught:
            self.prepare(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_denials_and_primitive_errors_do_not_debit_or_load_configuration(self):
        self.mocks['resolve_session'].return_value = replace(self.user, role='viewer')
        self.failure('dataset_not_found', 'facility_outages', [('limit','bad')])
        self.failure('dataset_not_found', 'unknown')
        self.failure('invalid_request', pairs=[('limit','1'),('limit','2')])
        self.failure('invalid_request', body=b'{}')
        self.mocks['repository.reserve_rate'].assert_not_called()
        self.codec_factory.assert_not_called()
        self.factory.assert_not_called()

    def test_later_semantic_and_cursor_failures_retain_one_committed_debit(self):
        for dataset,pairs,code in (
            ('national_outages',[('facility','01')],'invalid_request'),
            ('generator_outages',[('generator','1')],'invalid_request'),
            ('national_outages',[('cursor','forged')],'invalid_cursor')):
            self.db.events.clear()
            self.mocks['repository.reserve_rate'].reset_mock()
            self.failure(code,dataset,pairs)
            self.assertEqual(self.db.events, ['begin','commit','begin','commit'])
            self.mocks['repository.reserve_rate'].assert_called_once()
            self.mocks['read_pinned_publication'].assert_not_called()
            self.factory.assert_not_called()

    def test_rate_denial_does_not_reach_cursor_or_publication(self):
        self.mocks['repository.reserve_rate'].return_value = 12
        self.failure('rate_limited',pairs=[('cursor','forged')])
        self.codec_factory.assert_not_called()
        self.mocks['read_pinned_publication'].assert_not_called()

    def test_second_identity_downgrade_or_change_denies_before_pin(self):
        for second in (replace(self.user,role='viewer'), replace(self.user,session_id=uuid4())):
            self.mocks['resolve_session'].side_effect = [self.user,second]
            self.failure('dataset_not_found' if second.role == 'viewer' else 'invalid_session','facility_outages')
            self.mocks['read_pinned_publication'].assert_not_called()
            self.factory.assert_not_called()

    def test_no_publication_and_changed_cursor_precede_provenance(self):
        self.mocks['read_pinned_publication'].return_value = None
        self.failure('data_unavailable')
        request = ResolvedPreview('national',publication().latest_observation_date,publication().latest_observation_date)
        token = codec().encode(request, publication().publication_event_id,('2026-10-02',))
        self.failure('publication_changed',pairs=[('cursor',token)])
        self.provenance.assert_not_called()
        self.factory.assert_not_called()

    def test_equivalent_defaults_and_full_key_are_bound_after_fresh_permission(self):
        from datetime import timedelta
        public = self.pinned.publication
        request = ResolvedPreview('generator', public.latest_observation_date-timedelta(days=29),
                                  public.latest_observation_date, '01', '10', 1)
        token = codec().encode(request, public.publication_event_id, ('2026-09-03','01','10'))
        pairs = [('facility','01'),('generator','10'),('limit','1'),('cursor',token)]
        first,_ = self.prepare('generator_outages',pairs)
        explicit,_ = self.prepare('generator_outages',pairs+[('start','2026-09-03'),('end','2026-10-02')])
        self.assertEqual(first.query, explicit.query)
        self.assertEqual(first.query.after, ('2026-09-03','01','10'))
        self.assertNotIn('pv1.', first.query.to_bytes().decode())
        self.failure('invalid_cursor','generator_outages',[pair for pair in pairs if pair[0]!='limit'])

    def test_metadata_transactions_close_before_configuration_or_execution(self):
        def factory():
            self.assertEqual(self.db.open_transactions,0)
            self.assertEqual(self.db.events[-1],'commit')
            return self.execution
        self.factory.side_effect = factory
        self.execution.execute.side_effect = lambda prepared: self.assertEqual(self.db.open_transactions,0) or prepared
        prepared = self.service.execute('synthetic-token','national_outages',[])
        self.assertEqual(prepared.query.dataset,'national')
        self.assertGreater(prepared.deadline.remaining(),29)
        self.mocks['repository.reserve_capacity'].assert_called_once()
        self.assertEqual(self.mocks['repository.reserve_rate'].call_count,1)

    def test_provenance_configuration_capacity_and_cancellation_fail_closed(self):
        self.provenance.side_effect = Problem(503,'dependency_unavailable')
        self.failure('dependency_unavailable')
        self.factory.assert_not_called()
        self.provenance.side_effect = None
        self.mocks['repository.reserve_capacity'].return_value = None
        self.failure('rate_limited')
        self.execution.close.assert_called_once()
        cancelled = threading.Event(); cancelled.set()
        self.failure('query_timeout',cancelled=cancelled)
        self.execution.execute.assert_not_called()

    def test_http_with_real_service_preserves_denial_and_debit_order(self):
        self.mocks['resolve_session'].return_value = replace(self.user, role='viewer')
        with TestClient(create_app(service=Mock(), preview_service=self.service)) as client:
            headers = {'Authorization':'Bearer '+'x'*43}
            denied = client.request('GET','/api/v1/datasets/facility_outages/preview?limit=bad',
                                    content=b'{}',headers=headers)
            self.assertEqual(denied.status_code,404)
            duplicate = client.get('/api/v1/datasets/national_outages/preview?limit=1&limit=2',headers=headers)
            self.assertEqual(duplicate.status_code,422)
            self.mocks['repository.reserve_rate'].assert_not_called()
            semantic = client.get('/api/v1/datasets/national_outages/preview?facility=01',headers=headers)
            self.assertEqual(semantic.status_code,422)
            self.mocks['repository.reserve_rate'].assert_called_once()
            self.factory.assert_not_called()

    def test_delivery_gate_never_constructs_a_runtime(self):
        with patch('trinity.queries.config.execution_factory') as factory:
            with self.assertRaises(Problem):
                preview_execution_factory(self.db)
            factory.assert_not_called()


class PreviewRouteTests(unittest.TestCase):
    def test_testclient_preserves_pairs_body_headers_and_response_shape(self):
        service = Mock()
        service.execute.return_value = page()
        app = create_app(service=Mock(), preview_service=service)
        with TestClient(app) as client:
            response = client.get('/api/v1/datasets/national_outages/preview?limit=1&limit=2',
                                  headers={'Authorization':'Bearer '+'x'*43})
            self.assertEqual(response.status_code,200)
            self.assertEqual(service.execute.call_args.args[2],[('limit','1'),('limit','2')])
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertIn('x-request-id',response.headers)
            self.assertEqual(set(response.json()),set(page().model_dump()))
            response = client.request('GET','/api/v1/datasets/national_outages/preview',content=b'{}',
                                      headers={'Authorization':'Bearer '+'x'*43})
            self.assertEqual(service.execute.call_args.kwargs['body'],b'{}')
            service.execute.side_effect = Problem(422,'invalid_cursor')
            response = client.get('/api/v1/datasets/national_outages/preview?cursor=forged',
                                  headers={'Authorization':'Bearer '+'x'*43})
            self.assertEqual(response.status_code,422)
            self.assertEqual(response.json()['code'],'invalid_cursor')
            self.assertNotIn('forged',response.text)
            self.assertEqual(client.get('/health?limit=1').status_code,422)

    def test_missing_bearer_denies_before_service_and_preview_is_disabled_by_default(self):
        service = Mock()
        with TestClient(create_app(service=Mock(),preview_service=service)) as client:
            response = client.get('/api/v1/datasets/national_outages/preview?limit=1')
            self.assertEqual(response.status_code,401)
            self.assertFalse(client.app.state.preview_enabled)
            service.execute.assert_not_called()


class PreviewDisconnectTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_disconnect_sets_cancellation_and_waits_for_owner(self):
        from unittest.mock import AsyncMock
        from trinity.queries.router import supervised_call
        request = SimpleNamespace(is_disconnected=AsyncMock(return_value=True))
        stopped = threading.Event()
        def execute(*, cancelled):
            if not cancelled.wait(2):
                raise AssertionError('Disconnect was not propagated')
            stopped.set()
            raise Problem(504,'query_timeout')
        with self.assertRaises(Problem):
            await supervised_call(request,execute)
        self.assertTrue(stopped.is_set())
