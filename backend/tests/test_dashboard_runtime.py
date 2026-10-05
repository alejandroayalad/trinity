"""Run national HTTP requests through real PostgreSQL and isolated Docker work.

Source bytes come from the synthetic producer through the existing storage
fixture. No retained account, database or cloud object is changed. Fault commands
are test workloads in the same restricted container; production code is unchanged.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import multiprocessing
import os
from pathlib import Path
import signal
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from postgres_fixture import PostgresFixture, DSN
from preview_fixture import candidate, publish_fixture, loopback
from preview_runtime_fixture import IMAGE, RuntimeSandbox, cli
import test_preview_runtime as shared_preview
import test_query_guarantees as shared_guarantees
from test_validate import reconciled
from trinity.adapters.postgres import Database
from trinity.config import ApiSettings
from trinity.dashboard.schemas import DashboardResponse, MetricResponse
from trinity.dashboard.service import NationalService
from trinity.errors import Problem
from trinity.main import create_app
from trinity.queries.service import QueryDeadline

DASHBOARD = '/api/v1/dashboard/national'
METRIC = '/api/v1/metrics/offline-share'


def crash_national_owner(args):
    """Kill only the spawned test supervisor after it starts its owned container."""
    dsn, token, stage, volume, deployment, version, objects = args
    database = Database(ApiSettings(TRINITY_DATABASE_URL=dsn))
    database.open()
    sandbox = RuntimeSandbox(database, stage, volume=volume, deployment=deployment)
    sandbox.client.add(version, objects)
    sandbox.command = 'import time; time.sleep(60)'
    sandbox.after_start = lambda _: os.kill(os.getpid(), signal.SIGKILL)
    NationalService(database, sandbox.execution).dashboard(token, [])


@unittest.skipUnless(DSN and IMAGE, 'Disposable PostgreSQL and matching query image required')
class DashboardRuntimeTests(PostgresFixture, unittest.TestCase):
    def setUp(self):
        """Use existing producer, storage bridge and production execution owner."""
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.report, self.receipt, self.objects = candidate(self.root/'candidate')
        self.event, self.version = publish_fixture(DSN, self.report, self.receipt)
        self.sandbox = RuntimeSandbox(self.database, self.root/'stage')
        self.addCleanup(self.sandbox.close)
        self.sandbox.client.add(self.version, self.objects)
        self.national = NationalService(self.database, self.sandbox.execution)
        self.app = create_app(service=self.service, national_service=self.national)
        self.token = self.login('analyst')['Authorization'][7:]

    # Reuse the shared acceptance checks without inheriting unrelated test cases.
    assert_clean = shared_preview.PreviewRuntimeTests.assert_clean
    observe_release = shared_guarantees.QueryGuaranteeTests.observe_release

    def execute(self, pairs=(), *, metric=False):
        """Call the actual national service, retaining shared cleanup ownership."""
        method = self.national.metric if metric else self.national.dashboard
        return method(self.token, pairs)

    def test_real_http_all_roles_default_custom_gaps_metric_and_exact_models(self):
        """Check canonical serialization and independent one-day runtime reads."""
        with loopback(self.app) as client, self.observe_release() as releases:
            for role in ('viewer', 'analyst', 'admin'):
                headers = self.login(role)
                default = client.get(DASHBOARD, headers=headers)
                self.assertEqual(default.status_code, 200)
                dashboard = DashboardResponse.model_validate_json(default.content)
                self.assertEqual(len(dashboard.days), 30)
                self.assertEqual(dashboard.summary.period.isoformat(), '2026-10-03')
                self.assertEqual(dashboard.summary.offline_share_percent, '10.00')
                self.assertTrue(all(item.scope == 'national' for item in dashboard.diagnostics))
                self.assertNotIn('DETAIL_CANARY', default.text)
                # Explicit historical bounds include the first and last missing
                # dates. The response must not replace October 4 with October 3.
                custom = client.get(DASHBOARD, headers=headers,
                                    params={'start': '2026-09-30', 'end': '2026-10-04'})
                self.assertEqual(custom.status_code, 200)
                result = DashboardResponse.model_validate_json(custom.content)
                self.assertEqual(len(result.days), 5)
                self.assertEqual(result.summary, result.days[-1])
                self.assertEqual(result.summary.reason, 'not_reported')
                for point in result.days:
                    response = client.get(METRIC, headers=headers, params={'period': str(point.period)})
                    self.assertEqual(response.status_code, 200)
                    metric = MetricResponse.model_validate_json(response.content)
                    self.assertEqual((metric.metric.value, metric.metric.reason),
                                     (point.offline_share_percent, point.reason))
                    self.assertEqual(metric.publication, result.publication)
                    self.assertEqual(metric.diagnostics, result.diagnostics)
                    self.assertEqual(response.headers['cache-control'], 'no-store')
                    self.assertIn('x-request-id', response.headers)
                self.assertIsNone(result.days[1].percentOutage)
                self.assertEqual(result.days[1].offline_share_percent, '10.00')
            self.assertEqual(len(releases), 21)
        self.assertTrue(all('facility' not in key and 'generator' not in key for key in self.sandbox.client.calls))
        self.assert_clean()

    def test_pinned_reader_survives_new_publication_and_newer_failed_refresh(self):
        """Hold V1 after staging, finish V2, then verify V1 values and metadata."""
        rows = reconciled()
        for records in rows.values():
            for row in records:
                row['outage'] = str(int(row['outage'])*2)
                row['percentOutage'] = '20'
        with patch('preview_fixture.reconciled', return_value=rows):
            report, receipt, objects = candidate(self.root/'v2')
        entered, resume = threading.Event(), threading.Event()
        def hold(_):
            entered.set()
            if not resume.wait(20):
                raise RuntimeError('Publication barrier expired')
        self.sandbox.before_start = hold
        with self.observe_release(), ThreadPoolExecutor(1) as pool:
            first = pool.submit(self.execute)
            try:
                self.assertTrue(entered.wait(10))
                event, version = publish_fixture(DSN, report, receipt)
                self.sandbox.client.add(version, objects)
                self.lifecycle('failed')
                self.sandbox.before_start = None
                second = self.execute()
                self.assertEqual(second.publication.publication_event_id, event)
                self.assertEqual(second.summary.offline_share_percent, '20.00')
                self.assertEqual(second.freshness.last_refresh.status, 'failed')
            finally:
                resume.set()
            result = first.result(10)
        self.assertEqual(result.publication.publication_event_id, self.event)
        self.assertEqual(result.summary.offline_share_percent, '10.00')
        self.assertEqual(result.freshness.last_refresh.status, 'succeeded')
        self.assertEqual(result.freshness.published_at, result.publication.published_at)
        self.assertEqual([item.code for item in result.diagnostics], ['D02'])
        self.assert_clean()

    def test_real_http_presets_leap_range_and_fully_absent_metric(self):
        """Resolve dates from the fixture's October 3 publication, not the clock."""
        headers = {'Authorization': 'Bearer '+self.token}
        with loopback(self.app) as client, self.observe_release():
            for preset, start, count in (('30d', '2026-09-04', 30),
                                         ('90d', '2026-07-06', 90),
                                         ('1y', '2025-10-04', 365)):
                response = client.get(DASHBOARD, headers=headers, params={'preset': preset})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['range'], {'start': start, 'end': '2026-10-03'})
                self.assertEqual(len(response.json()['days']), count)
            response = client.get(DASHBOARD, headers=headers,
                                  params={'start': '2024-01-01', 'end': '2024-12-31'})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(len(body['days']), 366)
            self.assertEqual(body['days'][59]['period'], '2024-02-29')
            self.assertTrue(all(point['reason'] == 'not_reported' for point in body['days']))
            self.assertEqual(body['summary'], body['days'][-1])
            metric = client.get(METRIC, headers=headers, params={'period': '2030-01-01'})
            self.assertEqual(metric.status_code, 200)
            self.assertEqual(metric.json()['metric'], {'value': None, 'reason': 'not_reported'})
        self.assert_clean()

    def test_national_mount_denies_detail_application_state_network_and_writes(self):
        """Probe actual restrictions, then complete the normal dashboard request."""
        self.sandbox.command = '''import json,os,socket
from pathlib import Path
from trinity.queries.runtime.__main__ import run_request
from trinity.queries.runtime.engine import restricted_context
import pyarrow.parquet as pq
assert set(pq.read_schema('/query/data/part-000000.parquet').names)=={'period','capacity','outage','percentOutage'}
ctx=restricted_context('national',Path('/query/data'))
for name in ('facility_outages','generator_outages','local_users','local_sessions','information_schema.tables'):
 try: ctx.sql('SELECT * FROM '+name).collect()
 except Exception: pass
 else: raise AssertionError('Hidden table was accessible')
for name in ('/query/../unpublished-canary','/var/run/docker.sock','/run/secrets/postgres_password','/etc/shadow'):
 try: open(name,'rb')
 except OSError: pass
 else: raise AssertionError('Hidden file was accessible')
try: open('/query/request.json','wb')
except OSError: pass
else: raise AssertionError('Mount was writable')
for address in (('1.1.1.1',53),('127.0.0.1',5432)):
 try: socket.create_connection(address,timeout=.2)
 except OSError: pass
 else: raise AssertionError('Network was accessible')
assert os.getuid()==10001
assert not any(k.startswith(('AWS_','TRINITY_','PGPASSWORD')) for k in os.environ)
print(json.dumps(run_request(Path('/query/request.json').read_bytes(),Path('/query/data'))))
'''
        # A real sibling sentinel makes denial stronger than testing a nonexistent
        # file. Only this fixture's uniquely named volume receives the sentinel.
        sentinel = self.root/'unpublished-canary'
        sentinel.write_text('synthetic private data')
        helper = cli('create', '--entrypoint', '/bin/true', '--user', '0', '--network', 'none',
                     '--mount', f'type=volume,src={self.sandbox.volume},dst=/stage', IMAGE)
        try:
            cli('cp', str(sentinel), helper+':/stage/unpublished-canary')
        finally:
            cli('rm', helper)
        with patch.dict(os.environ, {'AWS_SECRET_ACCESS_KEY': 'synthetic-canary',
                                    'PGPASSWORD': 'synthetic-canary'}), self.observe_release():
            result = self.execute()
        self.assertEqual(result.summary.offline_share_percent, '10.00')
        self.assertNotIn('DETAIL_CANARY', result.model_dump_json())
        self.assertTrue(all('facility' not in key and 'generator' not in key for key in self.sandbox.client.calls))
        self.assert_clean()

    def test_checksum_and_missing_file_fail_before_launch(self):
        """Keep the published identity while damaging only the test storage bytes."""
        key = f'versions/{self.version}/data/national.parquet'
        original = self.sandbox.client.objects[key]
        self.sandbox.client.objects[key] = bytes([original[0]^1])+original[1:]
        for missing in (False, True):
            if missing:
                del self.sandbox.client.objects[key]
            with self.assertRaises(Problem) as caught:
                self.execute()
            self.assertEqual(caught.exception.code, 'dependency_unavailable')
            self.assertEqual(self.sandbox.created, [])
            self.assert_clean('dependency_unavailable')

    def test_slow_download_and_start_failure_keep_cleanup_ownership(self):
        """Use a short test deadline for storage; do not change production limits."""
        prepared, execution, _ = self.national._prepare(self.token, [])
        self.sandbox.client.before_get = lambda _: time.sleep(.1)
        with self.assertRaises(Problem) as caught:
            execution.execute(replace(prepared, deadline=QueryDeadline(.05)))
        self.assertEqual(caught.exception.code, 'query_timeout')
        self.assertEqual(self.sandbox.created, [])
        self.assert_clean('query_timeout')
        self.sandbox.client.before_get = None
        self.sandbox.before_start = lambda _: (_ for _ in ()).throw(Problem(503, 'dependency_unavailable'))
        with self.observe_release(), self.assertRaises(Problem) as caught:
            self.execute()
        self.assertEqual(caught.exception.code, 'dependency_unavailable')
        self.assert_clean('dependency_unavailable')

    def test_actual_30_second_timeout_confirms_stop_before_release(self):
        """Measure the unchanged production timeout against a real sleeping process."""
        self.sandbox.command = 'import time; time.sleep(60)'
        started = time.monotonic()
        with self.observe_release() as releases, self.assertRaises(Problem) as caught:
            self.execute()
        elapsed = time.monotonic()-started
        self.assertEqual(caught.exception.code, 'query_timeout')
        self.assertGreaterEqual(elapsed, 29)
        self.assertLess(elapsed, 40)
        self.assertEqual(len(releases), 1)
        self.assert_clean('query_timeout')
        print(f'National timeout plus confirmed cleanup: {elapsed:.3f}s')

    def test_oom_and_output_limit_return_no_partial_result(self):
        """Run bounded fault workloads in the same 1 GiB restricted container."""
        for command in ('x=bytearray(2*1024*1024*1024)', "import sys; sys.stdout.write('x'*(7*1024*1024))"):
            self.sandbox.command = command
            with self.observe_release(), self.assertRaises(Problem) as caught:
                self.execute()
            self.assertEqual(caught.exception.code, 'query_resource_limit')
            self.assert_clean('query_resource_limit')

    def test_duplicate_outside_and_lookahead_runtime_rows_are_rejected(self):
        """Inject malformed runtime replies after real execution and binding."""
        for mutation in ("reply['result']['rows'][1]=reply['result']['rows'][0]",
                         "reply['result']['rows'][0][0]='2026-09-30'",
                         "reply['result']['has_more']=True"):
            self.sandbox.command = '''import json
from pathlib import Path
from trinity.queries.runtime.__main__ import run_request
reply=run_request(Path('/query/request.json').read_bytes(),Path('/query/data'))
'''+mutation+"\nprint(json.dumps(reply))"
            with self.observe_release(), self.assertRaises(Problem) as caught:
                self.execute([('start', '2026-10-01'), ('end', '2026-10-03')])
            self.assertEqual(caught.exception.code, 'dependency_unavailable')
            self.assert_clean('dependency_unavailable')

    def test_real_http_disconnect_stops_national_container(self):
        """Close a real socket only after the admitted container is running."""
        self.sandbox.command = 'import time; time.sleep(60)'
        with loopback(self.app) as client, self.observe_release():
            url = client.base_url
            connection = socket.create_connection((url.host, url.port), timeout=5)
            connection.sendall((f'GET {DASHBOARD} HTTP/1.1\r\nHost: localhost\r\n'
                                f'Authorization: Bearer {self.token}\r\n\r\n').encode())
            rows = []
            try:
                limit = time.monotonic()+10
                while time.monotonic() < limit:
                    rows = self.sql("SELECT state FROM query_reservations WHERE state='running'")
                    if rows:
                        break
                    time.sleep(.02)
                self.assertTrue(rows)
            finally:
                connection.close()
            started = time.monotonic()
            while time.monotonic()-started < 10:
                if self.sql("SELECT count(*) AS n FROM query_reservations WHERE state='released'")[0]['n'] == 1:
                    break
                time.sleep(.02)
            self.assert_clean('query_timeout')
            print(f'National disconnect to confirmed cleanup: {time.monotonic()-started:.3f}s')

    def test_supervisor_crash_holds_slot_until_natural_expiry_and_recovery(self):
        """Do not edit deadlines; recover the real orphan after its normal expiry."""
        args = (DSN, self.token, str(self.sandbox.stage), self.sandbox.volume,
                self.sandbox.deployment, str(self.version), self.objects)
        process = multiprocessing.get_context('spawn').Process(target=crash_national_owner, args=(args,))
        process.start()
        process.join(15)
        if process.is_alive():
            process.kill()
            process.join()
            self.fail('Supervisor did not reach crash point')
        self.assertEqual(process.exitcode, -signal.SIGKILL)
        old = self.sql('SELECT * FROM query_reservations')[0]
        self.assertEqual(old['state'], 'starting')
        self.assertFalse(old['cleanup_complete'])
        self.assertEqual(len(self.sandbox.remaining_containers()), 1)
        started = time.monotonic()
        recovery = self.sandbox.execution()
        try:
            with self.observe_release() as releases:
                self.assertFalse(recovery.recover_one())
                while time.monotonic()-started < 40:
                    if recovery.recover_one():
                        break
                    time.sleep(.2)
                self.assertEqual(len(releases), 1)
            with self.assertRaises(Problem):
                recovery.cleanup(old, 'query_timeout')
        finally:
            recovery.close()
        self.assert_clean('query_timeout')
        print(f'National natural-expiry recovery after supervisor death: {time.monotonic()-started:.3f}s')

    def test_uncertain_removal_retains_slot_until_stop_is_confirmed(self):
        """Keep capacity occupied when the adapter cannot confirm removal."""
        self.sandbox.before_remove = lambda _: (_ for _ in ()).throw(Problem(503, 'dependency_unavailable'))
        with self.assertRaises(Problem):
            self.execute()
        row = self.sql('SELECT * FROM query_reservations')[0]
        self.assertNotEqual(row['state'], 'released')
        self.assertFalse(row['cleanup_complete'])
        self.assertEqual(len(self.sandbox.remaining_containers()), 1)
        self.sandbox.before_remove = None
        # This test isolates removal uncertainty. The separate crash case covers
        # natural expiry, so only this owned test reservation is advanced here.
        self.sql("UPDATE query_reservations SET deadline=clock_timestamp()-interval '1 second'")
        recovery = self.sandbox.execution()
        try:
            with self.observe_release():
                self.assertTrue(recovery.recover_one())
        finally:
            recovery.close()
        self.assert_clean('query_timeout')
