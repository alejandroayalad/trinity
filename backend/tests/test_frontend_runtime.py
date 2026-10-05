"""Check national and choice routes with real PostgreSQL, HTTP and isolated Docker."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from postgres_fixture import PostgresFixture, DSN
from preview_fixture import candidate, publish_fixture
from preview_runtime_fixture import RuntimeSandbox, IMAGE
from test_preview_unit import environment


@unittest.skipUnless(DSN and IMAGE, 'Disposable database and matching image required')
class FrontendRuntimeTests(PostgresFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.setup_done()
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        report, receipt, objects = candidate(root / 'candidate')
        self.event, self.version = publish_fixture(DSN, report, receipt)
        self.sandbox = RuntimeSandbox(self.database, root / 'stage'); self.addCleanup(self.sandbox.close)
        self.sandbox.client.add(self.version, objects)
        env = patch.dict(os.environ, environment()); env.start(); self.addCleanup(env.stop)
        execution = patch('trinity.queries.config.preview_execution_factory', side_effect=lambda *a, **k: self.sandbox.execution())
        execution.start(); self.addCleanup(execution.stop)

    def test_national_metric_same_publication_exact_values_and_cleanup(self):
        for role in ('viewer', 'analyst', 'admin'):
            headers = self.login(role)
            dashboard = self.client.get('/api/v1/dashboard/national?start=2026-09-30&end=2026-10-03', headers=headers)
            self.assertEqual(dashboard.status_code, 200, dashboard.text)
            data = dashboard.json()
            self.assertEqual(data['days'][0]['reason'], 'not_reported')
            self.assertIsNone(data['days'][0]['outage'])
            self.assertEqual(data['summary'], data['days'][-1])
            metric = self.client.get('/api/v1/metrics/offline-share?period=2026-10-03', headers=headers)
            self.assertEqual(metric.status_code, 200, metric.text)
            self.assertEqual(metric.json()['metric']['value'], data['summary']['offline_share_percent'])
            self.assertEqual(metric.json()['publication'], data['publication'])
            self.assertNotIn('DETAIL_CANARY', dashboard.text)
        self.assertTrue(all(r['cleanup_complete'] and r['state'] == 'released' for r in self.sql('SELECT * FROM query_reservations')))
        self.assertEqual(self.sandbox.remaining_containers(), [])

    def test_choices_pages_search_parent_binding_and_changed_publication(self):
        headers = self.login('analyst')
        path = '/api/v1/datasets/facility_outages/facilities'
        first = self.client.get(path + '?limit=1', headers=headers)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertNotIn('facility', first.json())
        self.assertEqual(first.json()['items'][0]['facility'], '001a')
        cursor = first.json()['next_cursor']
        if cursor:
            second = self.client.get(path, params={'limit': '1', 'cursor': cursor}, headers=headers)
            self.assertEqual(second.status_code, 200, second.text)
            changed = self.client.get(path, params={'limit': '1', 'cursor': cursor, 'search': 'changed'}, headers=headers)
            self.assertEqual(changed.status_code, 422)
            self.sql('UPDATE active_publication SET publication_event_id=NULL')
            changed = self.client.get(path, params={'limit': '1', 'cursor': cursor}, headers=headers)
            self.assertEqual((changed.status_code, changed.json()['code']), (409, 'publication_changed'))
