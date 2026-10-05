"""Verify national orchestration with controlled adapters and in-process HTTP.

No adapter opens PostgreSQL, S3 or Docker. Snapshot checks prove connection reuse
and call order here; concurrent database behavior belongs to real acceptance.
"""
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from trinity.auth.permissions import Principal
from trinity.catalog.registry import describe_dataset
from trinity.connector.validate import MESSAGES
from trinity.dashboard.service import NationalService, RefusingCodec
from trinity.errors import Problem
from trinity.main import create_app
from trinity.queries.preview_schemas import PreviewDiagnostic, build_preview_batch_response
from test_preview_provenance import frozen_fixture

HEADERS = {'Authorization': 'Bearer '+'x'*43}
DASHBOARD = '/api/v1/dashboard/national'
METRIC = '/api/v1/metrics/offline-share'


class Database:
    """Track transaction identity and commits without persisting any data."""
    def __init__(self):
        self.events = []
        self.open_transactions = 0
        self.connections = []

    @contextmanager
    def transaction(self, deadline, **kwargs):
        """Assign a distinct connection marker to each simulated transaction."""
        deadline.remaining()
        connection = SimpleNamespace(number=len(self.connections), options=kwargs)
        self.connections.append(connection)
        self.events.append('begin')
        self.open_transactions += 1
        try:
            yield connection
        except Exception:
            self.events.append('rollback')
            raise
        else:
            self.events.append('commit')
        finally:
            self.open_transactions -= 1


class NationalServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = Database()
        self.user = Principal('synthetic', 'viewer', uuid4())
        self.pinned, _ = frozen_fixture()
        self.execution = Mock(deployment_id=uuid4(), daemon_id='synthetic')
        self.execution.execute.side_effect = self.preview
        self.factory = Mock(return_value=self.execution)
        self.service = NationalService(self.db, self.factory)
        self.diagnostics = [PreviewDiagnostic(code='D02', severity='warning', scope='national',
                                              message=MESSAGES['D02'], affected_count='1')]
        self.rows = [['2026-10-01', '1000.000000', '123.450000', None]]
        targets = {'resolve_session': self.user, 'read_pinned_publication': self.pinned,
                   'read_preview_publication': self.pinned, 'read_last_refresh': None,
                   'repository.reserve_rate': None, 'repository.reserve_capacity': {'request_id': uuid4()}}
        self.mocks = {}
        for name, value in targets.items():
            patcher = patch('trinity.dashboard.service.'+name, return_value=value)
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)

    def preview(self, prepared):
        """Keep real batch validation while replacing only the execution adapter."""
        self.assertEqual(self.db.open_transactions, 0)
        rows = [row for row in self.rows if prepared.query.start <= row[0] <= prepared.query.end]
        batch = {'columns': [c.model_dump() for c in describe_dataset('national').columns],
                 'rows': rows, 'has_more': False}
        return build_preview_batch_response(prepared.query, prepared.pinned.publication, batch,
                                            diagnostics=self.diagnostics, codec=prepared.codec)

    def failure(self, code, *, metric=False, pairs=(), status=None, **kwargs):
        """Assert public failure codes without exposing request inputs."""
        method = self.service.metric if metric else self.service.dashboard
        with self.assertRaises(Problem) as caught:
            method('synthetic-token', pairs, **kwargs)
        self.assertEqual(caught.exception.code, code)
        if status is not None:
            self.assertEqual(caught.exception.status, status)
        return caught.exception

    def test_all_roles_have_identical_national_results(self):
        results = []
        for role in ('viewer', 'analyst', 'admin'):
            self.mocks['resolve_session'].return_value = replace(self.user, role=role)
            results.append((self.service.dashboard('token', []),
                            self.service.metric('token', [('period', '2026-10-01')])))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], results[2])
        self.assertEqual(results[0][1].metric.value, '12.35')

    def test_session_failures_precede_shape_and_debit(self):
        for code in ('invalid_session', 'session_expired', 'account_inactive'):
            self.mocks['resolve_session'].side_effect = Problem(401, code)
            for metric in (False, True):
                self.failure(code, metric=metric, pairs=[('unknown', 'bad')], body=b'{}', status=401)
        self.mocks['resolve_session'].side_effect = None
        self.mocks['resolve_session'].return_value = replace(self.user, role='unknown')
        self.failure('forbidden', status=403)
        self.mocks['repository.reserve_rate'].assert_not_called()
        self.mocks['read_pinned_publication'].assert_not_called()
        self.factory.assert_not_called()

    def test_shape_failures_do_not_debit(self):
        for metric, pairs, body in (
            (False, [('preset', '30d')]*2, b''), (False, [('preset', '30D')], b''),
            (False, [('start', '')], b''), (False, [('start', '20260229')], b''),
            (False, [('unknown', 'x')], b''), (False, [], b'{}'),
            (True, [], b''), (True, [('period', '2026-10-02')]*2, b''),
            (True, [('period', '2026-10-02')], b'{}'),
        ):
            self.failure('invalid_request', metric=metric, pairs=pairs, body=body, status=422)
        self.mocks['repository.reserve_rate'].assert_not_called()
        self.factory.assert_not_called()

    def test_semantic_failures_keep_exactly_one_committed_debit(self):
        cases = [[('preset', '30d'), ('start', '2026-10-01')], [('end', '2026-10-02')],
                 [('start', '2026-10-02'), ('end', '2026-10-01')],
                 [('start', '2024-01-01'), ('end', '2025-01-01')]]
        for pairs in cases:
            self.db.events.clear()
            self.mocks['repository.reserve_rate'].reset_mock()
            self.failure('invalid_request', pairs=pairs)
            self.assertEqual(self.db.events, ['begin', 'commit', 'begin', 'commit'])
            self.mocks['repository.reserve_rate'].assert_called_once()
        self.mocks['read_pinned_publication'].assert_not_called()
        self.factory.assert_not_called()

    def test_rate_denial_precedes_semantic_validation_and_snapshot(self):
        self.mocks['repository.reserve_rate'].return_value = 12
        error = self.failure('rate_limited', pairs=[('start', '2026-10-01')], status=429)
        self.assertEqual(error.retry_after, 12)
        self.mocks['repository.reserve_rate'].assert_called_once()
        self.mocks['read_pinned_publication'].assert_not_called()
        self.factory.assert_not_called()

    def test_second_identity_checks_precede_pin(self):
        for second in (replace(self.user, session_id=uuid4()), replace(self.user, user_id='other'),
                       replace(self.user, role='unknown')):
            self.mocks['resolve_session'].side_effect = [self.user, second]
            self.failure('forbidden' if second.role == 'unknown' else 'invalid_session')
        self.mocks['read_pinned_publication'].assert_not_called()
        self.factory.assert_not_called()

    def test_absent_publication_returns_409_without_execution(self):
        self.mocks['read_pinned_publication'].return_value = None
        for metric, pairs in ((False, []), (True, [('period', '2026-10-01')])):
            self.mocks['repository.reserve_rate'].reset_mock()
            self.failure('data_unavailable', metric=metric, pairs=pairs, status=409)
            self.mocks['repository.reserve_rate'].assert_called_once()
        self.mocks['read_preview_publication'].assert_not_called()
        self.mocks['read_last_refresh'].assert_not_called()
        self.factory.assert_not_called()

    def test_broken_pointer_or_evidence_returns_503_before_capacity(self):
        for target in ('read_pinned_publication', 'read_preview_publication'):
            self.mocks[target].side_effect = Problem(503, 'dependency_unavailable')
            self.failure('dependency_unavailable', status=503)
            self.mocks[target].side_effect = None
        self.mocks['repository.reserve_capacity'].assert_not_called()
        self.factory.assert_not_called()

    def test_publication_evidence_and_freshness_share_one_readonly_snapshot(self):
        self.service.dashboard('token', [])
        pin = self.mocks['read_pinned_publication'].call_args.args[0]
        evidence = self.mocks['read_preview_publication'].call_args.args[0]
        refresh = self.mocks['read_last_refresh'].call_args.args[0]
        self.assertIs(pin, evidence)
        self.assertIs(pin, refresh)
        self.assertTrue(pin.options['readonly'])
        self.assertIsNot(pin, self.mocks['repository.reserve_rate'].call_args.args[0])
        self.assertEqual(self.db.events, ['begin', 'commit']*4)
        prepared = self.execution.execute.call_args.args[0]
        self.assertEqual(prepared.query.dataset, 'national')
        self.assertEqual(prepared.query.page_size, 30)
        self.assertEqual(prepared.pinned, self.pinned)
        self.assertIsInstance(prepared.codec, RefusingCodec)
        self.assertEqual(self.mocks['repository.reserve_rate'].call_count, 1)

    def test_failed_newer_refresh_preserves_old_publication(self):
        self.mocks['read_last_refresh'].return_value = {
            'status': 'failed', 'requested_at': datetime(2026, 10, 4, tzinfo=timezone.utc),
            'finished_at': datetime(2026, 10, 4, 1, tzinfo=timezone.utc),
        }
        result = self.service.dashboard('token', [])
        self.assertEqual(result.publication, self.pinned.publication)
        self.assertEqual(result.freshness.last_refresh.status, 'failed')
        self.assertEqual(result.freshness.published_at, result.publication.published_at)
        self.assertEqual(result.freshness.latest_observation_date, result.publication.latest_observation_date)

    def test_unfinished_refresh_and_invalid_completion(self):
        self.mocks['read_last_refresh'].return_value = {
            'status': 'running', 'requested_at': datetime(2026, 10, 4, tzinfo=timezone.utc), 'finished_at': None,
        }
        self.assertIsNone(self.service.dashboard('token', []).freshness.last_refresh.finished_at)
        self.mocks['read_last_refresh'].return_value['status'] = 'failed'
        self.failure('dependency_unavailable')

    def test_metadata_is_retained_when_controlled_active_pointer_changes(self):
        def execute(prepared):
            # This models a later publication without claiming real concurrency.
            newer = replace(self.pinned, publication=self.pinned.publication.model_copy(
                update={'publication_event_id': uuid4()}))
            self.mocks['read_pinned_publication'].return_value = newer
            return self.preview(prepared)
        self.execution.execute.side_effect = execute
        result = self.service.dashboard('token', [])
        self.assertEqual(result.publication, self.pinned.publication)
        self.assertEqual(result.diagnostics, self.diagnostics)
        self.assertEqual(result.freshness.published_at, self.pinned.publication.published_at)
        self.mocks['read_pinned_publication'].assert_called_once()

    def test_page_size_is_selected_date_count_for_presets_leap_year_and_metric(self):
        for pairs, count in (([], 30), ([('preset', '90d')], 90), ([('preset', '1y')], 365),
                             ([('start', '2024-01-01'), ('end', '2024-12-31')], 366)):
            result = self.service.dashboard('token', pairs)
            operation = self.execution.execute.call_args.args[0].query
            self.assertEqual(operation.page_size, count)
            self.assertEqual(len(result.days), count)
            self.assertIsNone(operation.after)
            self.assertIsNone(operation.facility)
            self.assertIsNone(operation.generator)
        self.service.metric('token', [('period', '2026-10-01')])
        self.assertEqual(self.execution.execute.call_args.args[0].query.page_size, 1)

    def test_configuration_and_execution_have_no_open_metadata_transaction(self):
        def factory():
            self.assertEqual(self.db.open_transactions, 0)
            self.assertEqual(self.db.events[-1], 'commit')
            return self.execution
        self.factory.side_effect = factory
        cancelled = threading.Event()
        self.service.dashboard('token', [], cancelled=cancelled)
        prepared = self.execution.execute.call_args.args[0]
        self.assertIs(prepared.deadline.cancelled, cancelled)
        self.assertGreater(prepared.deadline.remaining(), 29)

    def test_capacity_failure_closes_adapter_and_retains_debit(self):
        self.mocks['repository.reserve_capacity'].return_value = None
        self.failure('rate_limited', status=429)
        self.execution.close.assert_called_once()
        self.execution.execute.assert_not_called()
        self.mocks['repository.reserve_rate'].assert_called_once()

    def test_cancelled_preflight_never_debits_or_executes(self):
        cancelled = threading.Event()
        cancelled.set()
        self.failure('query_timeout', cancelled=cancelled, status=504)
        self.mocks['repository.reserve_rate'].assert_not_called()
        self.factory.assert_not_called()

    def test_duplicate_rows_and_unexpected_lookahead_refuse_partial_results(self):
        self.rows *= 2
        self.failure('dependency_unavailable', status=503)
        self.rows = self.rows[:1]
        def more(prepared):
            batch = {'columns': [c.model_dump() for c in describe_dataset('national').columns],
                     'rows': self.rows, 'has_more': True}
            return build_preview_batch_response(prepared.query, prepared.pinned.publication, batch,
                                                diagnostics=self.diagnostics, codec=prepared.codec)
        self.execution.execute.side_effect = more
        self.failure('dependency_unavailable', metric=True, pairs=[('period', '2026-10-01')], status=503)
        with self.assertRaises(ValueError):
            RefusingCodec().encode('anything')

    def test_wrong_pin_or_range_is_rejected_even_when_preview_valid(self):
        original = self.preview
        for field, value in (('publication', self.pinned.publication.model_copy(update={'version_id': uuid4()})),
                             ('range', SimpleNamespace(start=date(2026, 1, 1), end=date(2026, 1, 2)))):
            self.execution.execute.side_effect = lambda prepared: original(prepared).model_copy(update={field: value})
            self.failure('dependency_unavailable', status=503)

    def test_http_real_service_preserves_auth_shape_and_debit_order(self):
        with TestClient(create_app(service=Mock(), national_service=self.service)) as client:
            for path in (DASHBOARD+'?preset=30D', METRIC+'?period=bad'):
                self.assertEqual(client.get(path).status_code, 401)
                self.assertEqual(client.get(path, headers=HEADERS).status_code, 422)
            for path in (DASHBOARD, METRIC+'?period=2026-10-01'):
                response = client.request('GET', path, content=b'{}', headers=HEADERS)
                self.assertEqual(response.status_code, 422)
            self.assertEqual(client.get(DASHBOARD+'?preset=30d&preset=30d', headers=HEADERS).status_code, 422)
            self.mocks['repository.reserve_rate'].assert_not_called()
            self.assertEqual(client.get(DASHBOARD+'?start=2026-10-01', headers=HEADERS).status_code, 422)
            self.mocks['repository.reserve_rate'].assert_called_once()
            self.factory.assert_not_called()

    def test_http_disabled_execution_uses_existing_switch_and_no_runtime(self):
        # Exercise the default router construction, not an injected service.
        with patch('trinity.queries.config.execution_factory') as runtime:
            with TestClient(create_app(service=SimpleNamespace(database=self.db))) as client:
                self.assertFalse(client.app.state.preview_enabled)
                for path in (DASHBOARD, METRIC+'?period=2026-10-01'):
                    response = client.get(path, headers=HEADERS)
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json()['code'], 'dependency_unavailable')
            runtime.assert_not_called()
        self.mocks['repository.reserve_capacity'].assert_not_called()

    def test_http_enabled_switch_routes_to_shared_factory(self):
        with patch('trinity.queries.config.execution_factory', return_value=self.execution) as runtime:
            with TestClient(create_app(service=SimpleNamespace(database=self.db), enable_preview=True)) as client:
                self.assertEqual(client.get(DASHBOARD, headers=HEADERS).status_code, 200)
            runtime.assert_called_once_with(self.db)

    def test_http_errors_preserve_safe_headers_and_retry_after(self):
        with TestClient(create_app(service=Mock(), national_service=self.service)) as client:
            for path in (DASHBOARD, METRIC+'?period=2026-10-01'):
                self.mocks['repository.reserve_rate'].return_value = 7
                response = client.get(path, headers=HEADERS)
                self.assertEqual(response.status_code, 429)
                self.assertEqual(response.headers['retry-after'], '7')
                self.assertEqual(response.headers['cache-control'], 'no-store')
                self.assertIn('x-request-id', response.headers)
                self.assertTrue(response.headers['content-type'].startswith('application/problem+json'))
                self.assertNotIn('synthetic-token', response.text)
            self.mocks['repository.reserve_rate'].return_value = None
            self.mocks['read_pinned_publication'].return_value = None
            self.assertEqual(client.get(DASHBOARD, headers=HEADERS).status_code, 409)
            self.assertEqual(client.get('/health?unexpected=1').status_code, 422)
            self.assertEqual(client.get(DASHBOARD+'/other?preset=30d', headers=HEADERS).status_code, 422)

    def test_http_exact_openapi_serialization_and_metric_agreement(self):
        schemas = json.loads((Path(__file__).parents[2]/'docs/openapi.json').read_text())['components']['schemas']
        def check(value, schema):
            # Resolve the canonical schema recursively. This checks nested closed
            # objects, primitive types and patterns without adding a dependency.
            if '$ref' in schema:
                return check(value, schemas[schema['$ref'].split('/')[-1]])
            if 'anyOf' in schema:
                for choice in schema['anyOf']:
                    try:
                        check(value, choice)
                        return
                    except AssertionError:
                        pass
                self.fail('No canonical schema alternative matched')
            kind = schema['type']
            if kind == 'null':
                self.assertIsNone(value)
            elif kind == 'object':
                self.assertIsInstance(value, dict)
                self.assertTrue(set(schema.get('required', ())) <= set(value))
                if schema.get('additionalProperties') is False:
                    self.assertTrue(set(value) <= set(schema['properties']))
                for name, item in value.items():
                    check(item, schema['properties'][name])
            elif kind == 'array':
                self.assertIsInstance(value, list)
                self.assertLessEqual(len(value), schema.get('maxItems', len(value)))
                for item in value:
                    check(item, schema['items'])
            elif kind == 'string':
                self.assertIsInstance(value, str)
                if 'pattern' in schema:
                    self.assertIsNotNone(re.search(schema['pattern'], value))
                if schema.get('format') == 'date':
                    self.assertEqual(date.fromisoformat(value).isoformat(), value)
                if 'maxLength' in schema:
                    self.assertLessEqual(len(value), schema['maxLength'])
            else:
                self.fail('Unhandled canonical type '+kind)
            if 'enum' in schema:
                self.assertIn(value, schema['enum'])
        with TestClient(create_app(service=Mock(), national_service=self.service)) as client:
            dashboard = client.get(DASHBOARD+'?start=2026-09-30&end=2026-10-02', headers=HEADERS)
            self.assertEqual(dashboard.status_code, 200)
            check(dashboard.json(), schemas['DashboardResponse'])
            self.assertEqual(dashboard.json()['summary'], dashboard.json()['days'][-1])
            self.assertTrue(dashboard.json()['publication']['published_at'].endswith('Z'))
            for point in dashboard.json()['days']:
                metric = client.get(METRIC+'?period='+point['period'], headers=HEADERS)
                self.assertEqual(metric.status_code, 200)
                check(metric.json(), schemas['MetricResponse'])
                self.assertEqual(metric.json()['metric'], {'value': point['offline_share_percent'], 'reason': point['reason']})
                self.assertEqual(metric.json()['diagnostics'], dashboard.json()['diagnostics'])
                self.assertEqual(metric.headers['cache-control'], 'no-store')
                self.assertIn('x-request-id', metric.headers)
            self.assertEqual(dashboard.headers['cache-control'], 'no-store')
            self.assertIn('x-request-id', dashboard.headers)
            generated = client.app.openapi()
            for path, model in ((DASHBOARD, 'DashboardResponse'), (METRIC, 'MetricResponse')):
                reference = generated['paths'][path]['get']['responses']['200']['content']['application/json']['schema']['$ref']
                self.assertEqual(reference, '#/components/schemas/'+model)


if __name__ == '__main__':
    unittest.main()
