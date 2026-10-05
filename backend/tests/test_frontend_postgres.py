"""Exercise frontend endpoint state through real PostgreSQL and HTTP adapters."""
import os
import unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from postgres_fixture import PostgresFixture

DSN = os.environ.get('TRINITY_TEST_DATABASE_URL')


@unittest.skipUnless(DSN, 'Use run_local_auth_checks.py --frontend for disposable database checks')
class FrontendPostgresTests(PostgresFixture, unittest.TestCase):
    def test_settings_malformed_json_differs_from_invalid_fields(self):
        """Malformed transport is 400; valid JSON with invalid fields is 422."""
        headers = self.login('admin') | {'If-Match': '"settings-0"', 'Content-Type': 'application/json'}
        malformed = self.client.put('/api/v1/settings', content=b'{', headers=headers)
        self.assertEqual((malformed.status_code, malformed.json()['code']), (400, 'invalid_json'))
        invalid = self.client.put('/api/v1/settings', json={}, headers=headers)
        self.assertEqual((invalid.status_code, invalid.json()['code']), (422, 'invalid_request'))
        self.assertEqual(self.sql('SELECT revision FROM shared_settings')[0]['revision'], 0)

    def test_setup_compare_and_swap_preserves_first_completion(self):
        headers = self.login('admin')
        body = {'schedule_enabled': True, 'daily_time': '06:30', 'timezone': 'America/Merida'}
        route = '/api/v1/settings'
        self.assertEqual(self.client.put(route, json=body, headers=headers).status_code, 428)
        first = self.client.put(route, json=body, headers=headers | {'If-Match': '"settings-0"'})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.headers['etag'], '"settings-1"')
        stale = self.client.put(route, json=body, headers=headers | {'If-Match': '"settings-0"'})
        self.assertEqual(stale.status_code, 412)
        second = self.client.put(route, json=body | {'schedule_enabled': False}, headers=headers | {'If-Match': first.headers['etag']})
        self.assertEqual(second.json()['setup_completed_at'], first.json()['setup_completed_at'])
        self.assertEqual(self.sql('SELECT count(*) AS n FROM refresh_runs')[0]['n'], 0)
        status = self.client.get('/api/v1/settings/schedule-status', headers=headers)
        self.assertEqual(status.json()['blocker']['code'], 'schedule_disabled')
        self.assertIsNone(status.json()['next_check_at'])

    def test_settings_concurrent_edit_one_winner(self):
        headers = self.login('admin') | {'If-Match': '"settings-0"'}
        body = {'schedule_enabled': True, 'daily_time': '06:00', 'timezone': 'UTC'}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.client.put('/api/v1/settings', json=body, headers=headers).status_code, range(2)))
        self.assertEqual(sorted(results), [200, 412])

    def test_national_no_publication_and_detail_denial_before_execution(self):
        from unittest.mock import patch
        from test_preview_unit import environment
        with patch.dict(os.environ, environment()):
            for role in ('viewer', 'analyst', 'admin'):
                headers = self.login(role)
                for path in ('/dashboard/national', '/metrics/offline-share?period=2026-10-01'):
                    response = self.client.get('/api/v1' + path, headers=headers)
                    self.assertEqual((response.status_code, response.json()['code']), (409, 'data_unavailable'))
                if role != 'admin':
                    self.assertEqual(self.client.put('/api/v1/settings', json={}, headers=headers).status_code, 403)
                if role == 'viewer':
                    self.assertEqual(self.client.get('/api/v1/datasets/facility_outages/facilities', headers=headers).status_code, 404)

    def failed_run(self):
        """Create failure through admission plus the production dispatch failure path."""
        from trinity.adapters.postgres import Deadline
        from trinity.refresh.dispatch import fail_run
        self.setup_done()
        headers = self.login('admin')
        response = self.client.post('/api/v1/refresh-runs', json={}, headers=headers | {'Idempotency-Key': str(uuid4())})
        self.assertEqual(response.status_code, 202)
        run_id = response.json()['run_id']
        with self.database.transaction(Deadline()) as connection:
            fail_run(connection, run_id, 'dispatch_failed')
        return headers, run_id

    def test_recovery_replay_stale_tag_and_history(self):
        headers, run_id = self.failed_run()
        detail = self.client.get(f'/api/v1/refresh-runs/{run_id}', headers=headers)
        self.assertTrue(next(a['enabled'] for a in detail.json()['actions'] if a['action'] == 'rerun'))
        command_headers = headers | {'Idempotency-Key': str(uuid4()), 'If-Match': detail.headers['etag']}
        first = self.client.post(f'/api/v1/refresh-runs/{run_id}/rerun', json={}, headers=command_headers)
        self.assertEqual(first.status_code, 202, first.text)
        replay = self.client.post(f'/api/v1/refresh-runs/{run_id}/rerun', json={}, headers=command_headers)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()['replayed'])
        self.assertEqual(replay.json()['run_id'], first.json()['run_id'])
        self.assertEqual(self.sql('SELECT count(*) AS n FROM refresh_runs')[0]['n'], 2)
        self.assertEqual(self.sql('SELECT resolution FROM failure_warnings')[0]['resolution'], 'rerun')

    def test_warning_resolution_starts_no_work_and_rejects_unknown_writer(self):
        headers, run_id = self.failed_run()
        self.sql('UPDATE refresh_runs SET worker_owner_id=%s WHERE id=%s', (uuid4(), run_id))
        detail = self.client.get(f'/api/v1/refresh-runs/{run_id}', headers=headers)
        command_headers = headers | {'Idempotency-Key': str(uuid4()), 'If-Match': detail.headers['etag']}
        path = f'/api/v1/refresh-runs/{run_id}/warning'
        self.assertEqual(self.client.delete(path, headers=command_headers).status_code, 409)
        self.sql('UPDATE refresh_runs SET worker_owner_id=NULL WHERE id=%s', (run_id,))
        result = self.client.delete(path, headers=command_headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['result'], 'warning_resolved')
        self.assertEqual(self.sql('SELECT count(*) AS n FROM refresh_runs')[0]['n'], 1)
        self.assertIsNone(self.sql('SELECT holder_run_id FROM refresh_control')[0]['holder_run_id'])

    def test_scheduler_admits_once_and_skips_backlog(self):
        """A due occurrence writes the same outbox intent without API actor receipts."""
        from datetime import datetime, timedelta, timezone
        from trinity.settings.scheduler import Scheduler
        self.setup_done()
        self.sql("UPDATE shared_settings SET daily_time='06:00',schedule_timezone='UTC',updated_at='2026-01-01'")
        scheduler = Scheduler(self.database)
        due = datetime(2026, 10, 5, 6, tzinfo=timezone.utc)
        first = scheduler.tick(due - timedelta(seconds=1), due)
        self.assertIsNotNone(first)
        self.assertIsNone(scheduler.tick(due - timedelta(seconds=1), due))
        row = self.sql('SELECT trigger_kind,requested_by FROM refresh_runs')[0]
        self.assertEqual(row, {'trigger_kind': 'scheduled', 'requested_by': None})
        self.assertEqual(self.sql('SELECT count(*) AS n FROM job_outbox')[0]['n'], 1)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM api_commands')[0]['n'], 0)
        self.assertIsNone(scheduler.tick(due - timedelta(hours=2), due))
