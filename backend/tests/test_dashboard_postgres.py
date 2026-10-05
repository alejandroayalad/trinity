"""Prove national snapshot and shared admission rules on disposable PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from postgres_fixture import PostgresFixture, DSN
from preview_fixture import candidate, publish_fixture, loopback
from test_preview_unit import codec
from trinity.adapters.postgres import Database
from trinity.config import ApiSettings
from trinity.dashboard.service import NationalService
from trinity.errors import Problem
from trinity.main import create_app
from trinity.publication.repository import read_pinned_publication
from trinity.queries.service import PreviewService, QueryService


def mixed_prepare(args):
    """Use separate process connections and real counters without starting work."""
    dsn, token, kind, deployment = args
    database = Database(ApiSettings(TRINITY_DATABASE_URL=dsn))
    database.open()
    factory = lambda: SimpleNamespace(deployment_id=deployment, daemon_id='acceptance', close=lambda: None)
    try:
        if kind in ('dashboard', 'metric'):
            NationalService(database, factory)._prepare(
                token, [('period', '2026-10-01')] if kind == 'metric' else [], metric=kind == 'metric')
        elif kind == 'preview':
            PreviewService(database, factory, codec_factory=codec).prepare(token, 'national_outages', [])
        else:
            QueryService(database, factory).prepare(token, 'SELECT outage FROM national_outages')
        return 'prepared'
    except Problem as error:
        return error.code
    finally:
        database.close()


@unittest.skipUnless(DSN, 'Disposable PostgreSQL required')
class DashboardPostgresTests(PostgresFixture, unittest.TestCase):
    def setUp(self):
        """Publish only producer-validated synthetic bytes in the test database."""
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report, self.receipt, self.objects = candidate(self.root/'candidate')
        self.event, self.version = publish_fixture(DSN, self.report, self.receipt)
        self.factory = Mock(return_value=SimpleNamespace(deployment_id=uuid4(), daemon_id='acceptance', close=lambda: None))
        self.national = NationalService(self.database, self.factory)

    def count(self):
        """Count persisted analytical attempts for the synthetic Analyst."""
        rows = self.sql("SELECT cardinality(admitted_at) AS n FROM analytical_rate_limits WHERE user_id='test_analyst'")
        return rows[0]['n'] if rows else 0

    def test_http_identity_shape_semantic_and_absent_publication_debits(self):
        headers = self.login('analyst')
        with loopback(create_app(service=self.service, national_service=self.national)) as client:
            for path in ('/api/v1/dashboard/national', '/api/v1/metrics/offline-share'):
                self.assertEqual(client.get(path+'?bad=x').status_code, 401)
                self.assertEqual(client.get(path+'?bad=x', headers=headers).status_code, 422)
                self.assertEqual(client.request('GET', path, headers=headers, content=b'{}').status_code, 422)
            self.assertEqual(self.count(), 0)
            for query in ('preset=30D', 'start=2026-02-29', 'preset=30d&preset=30d'):
                self.assertEqual(client.get('/api/v1/dashboard/national?'+query, headers=headers).status_code, 422)
            self.assertEqual(self.count(), 0)
            for query in ('start=2026-10-01', 'preset=30d&end=2026-10-02',
                          'start=2026-10-02&end=2026-10-01', 'start=2024-01-01&end=2025-01-01'):
                self.assertEqual(client.get('/api/v1/dashboard/national?'+query, headers=headers).status_code, 422)
            self.assertEqual(self.count(), 4)
            # A candidate without an active pointer is not user-visible data.
            self.sql('UPDATE active_publication SET publication_event_id=NULL')
            for path in ('/api/v1/dashboard/national', '/api/v1/metrics/offline-share?period=2026-10-01'):
                response = client.get(path, headers=headers)
                self.assertEqual((response.status_code, response.json()['code']), (409, 'data_unavailable'))
            self.assertEqual(self.count(), 6)
        self.factory.assert_not_called()

    def test_expired_revoked_inactive_and_unknown_role_fail_without_debit(self):
        # Each test mutation affects only the disposable persona/session tables.
        headers = self.login('analyst')
        token = headers['Authorization'][7:]
        for mutation in ("UPDATE local_sessions SET revoked_at=now()",
                         "UPDATE local_sessions SET created_at=now()-interval '2 hours',expires_at=now()-interval '1 hour'",
                         "UPDATE local_users SET is_active=false WHERE id='test_analyst'"):
            self.sql(mutation)
            with self.assertRaises(Problem) as caught:
                self.national._prepare(token, [])
            self.assertEqual(caught.exception.status, 401)
            self.sql('UPDATE local_sessions SET revoked_at=NULL,expires_at=now()+interval \'1 hour\'')
            self.sql("UPDATE local_users SET is_active=true WHERE id='test_analyst'")
        # Storage rejects unknown roles itself; do not weaken that constraint.
        import psycopg
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.sql("UPDATE local_users SET role='unknown' WHERE id='test_analyst'")
        self.assertEqual(self.count(), 0)
        self.factory.assert_not_called()

    def test_broken_evidence_returns_503_before_capacity(self):
        token = self.login('analyst')['Authorization'][7:]
        self.sql('UPDATE data_versions SET evidence_bundle_sha256=NULL,validation_attempt_id=NULL')
        with self.assertRaises(Problem) as caught:
            self.national._prepare(token, [])
        self.assertEqual(caught.exception.code, 'dependency_unavailable')
        self.assertEqual(self.count(), 1)
        self.factory.assert_not_called()
        self.assertEqual(self.sql('SELECT count(*) AS n FROM query_reservations')[0]['n'], 0)

    def test_publication_evidence_and_freshness_remain_in_one_real_snapshot(self):
        token = self.login('analyst')['Authorization'][7:]
        report, receipt, _ = candidate(self.root/'next')
        pinned, resume = threading.Event(), threading.Event()
        original = read_pinned_publication
        def pause(connection):
            result = original(connection)
            pinned.set()
            if not resume.wait(10):
                raise RuntimeError('Snapshot barrier expired')
            return result
        with patch('trinity.dashboard.service.read_pinned_publication', side_effect=pause):
            with ThreadPoolExecutor(1) as pool:
                future = pool.submit(self.national._prepare, token, [])
                try:
                    self.assertTrue(pinned.wait(10))
                    publish_fixture(DSN, report, receipt)
                    self.lifecycle('failed')
                finally:
                    resume.set()
                prepared, _, freshness = future.result(10)
        self.assertEqual(prepared.pinned.publication.publication_event_id, self.event)
        self.assertEqual(prepared.pinned.evidence_bundle_sha256, self.receipt.bundle_sha256)
        self.assertEqual(freshness.last_refresh.status, 'succeeded')
        self.assertEqual(freshness.published_at, prepared.pinned.publication.published_at)
        self.assertEqual(self.sql('SELECT status FROM refresh_runs ORDER BY run_seq DESC LIMIT 1')[0]['status'], 'failed')

    def test_all_four_services_share_30_attempts_across_processes(self):
        token = self.login('analyst')['Authorization'][7:]
        self.sql('UPDATE active_publication SET publication_event_id=NULL')
        kinds = ('sql', 'preview', 'dashboard', 'metric')
        args = [(DSN, token, kinds[i % 4], uuid4()) for i in range(40)]
        with multiprocessing.get_context('spawn').Pool(4) as pool:
            results = pool.map(mixed_prepare, args)
        self.assertEqual(results.count('data_unavailable'), 30)
        self.assertEqual(results.count('rate_limited'), 10)
        self.assertEqual(self.count(), 30)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM query_reservations')[0]['n'], 0)

    def test_mixed_capacity_enforces_two_per_user_and_four_per_instance(self):
        tokens = {role: self.login(role)['Authorization'][7:] for role in ('analyst', 'admin', 'viewer')}
        kinds = ('sql', 'preview', 'dashboard', 'metric')
        with multiprocessing.get_context('spawn').Pool(4) as pool:
            first = pool.map(mixed_prepare, [(DSN, tokens['analyst'], kind, uuid4()) for kind in kinds])
            self.assertEqual(first.count('prepared'), 2)
            self.assertEqual(first.count('rate_limited'), 2)
            more = pool.map(mixed_prepare, [(DSN, tokens[role], kind, uuid4())
                                            for role in ('admin', 'viewer') for kind in ('dashboard', 'metric', 'preview')])
        self.assertEqual(more.count('prepared'), 2)
        self.assertEqual(more.count('rate_limited'), 4)
        counts = self.sql("SELECT user_id,count(*) AS n FROM query_reservations WHERE state<>'released' GROUP BY user_id")
        self.assertEqual(sum(row['n'] for row in counts), 4)
        self.assertTrue(all(row['n'] <= 2 for row in counts))
