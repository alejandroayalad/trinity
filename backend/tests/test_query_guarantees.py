"""Acceptance for pinned versions, sandbox boundaries and uncertain execution.

Use the existing synthetic publication producer, real PostgreSQL and real Docker.
Barriers control races; local byte proxies lose replies after real side effects.
No retained database, live storage or external network service is required.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httpx

from postgres_fixture import PostgresFixture, DSN
from preview_fixture import candidate, publish_fixture, loopback
from preview_runtime_fixture import IMAGE, SOCKET, cli, RuntimeSandbox
import test_preview_runtime as existing
from query_fault_proxy import ReplyLossProxy
from trinity.adapters.postgres import Database
from trinity.config import ApiSettings
from trinity.errors import Problem
from trinity.queries import repository
from trinity.queries.service import QueryService, PreviewService
from trinity.main import create_app
from test_preview_unit import codec


@unittest.skipUnless(DSN and IMAGE, 'Disposable PostgreSQL and matching query image required')
class QueryGuaranteeTests(PostgresFixture, unittest.TestCase):
    def setUp(self):
        """Use real admission and authentication over a synthetic publication."""
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.report, self.receipt, self.objects = candidate(self.root/'candidate')
        self.event, self.version = publish_fixture(DSN, self.report, self.receipt)
        self.sandbox = RuntimeSandbox(self.database, self.root/'stage')
        self.addCleanup(self.sandbox.close)
        self.sandbox.client.add(self.version, self.objects)
        self.queries = QueryService(self.database, self.sandbox.execution)
        previews = PreviewService(self.database, self.sandbox.execution, codec_factory=codec)
        self.app = create_app(service=self.service, preview_service=previews, query_service=self.queries)
        self.token = self.login('analyst')['Authorization'][7:]

    assert_clean = existing.PreviewRuntimeTests.assert_clean

    @contextmanager
    def observe_release(self):
        """Inspect the actual container immediately before every release write."""
        release = repository.release_removed
        observed = []
        inspector = self.sandbox.execution()

        def checked(connection, reservation, outcome):
            self.assertIsNone(inspector.docker.inspect(reservation['container_id']))
            self.assertFalse((self.sandbox.stage / str(reservation['request_id'])).exists())
            observed.append(reservation['request_id'])
            return release(connection, reservation, outcome)

        try:
            with patch.object(repository, 'release_removed', side_effect=checked):
                yield observed
        finally:
            inspector.close()

    def expire(self):
        """Advance only test reservations for deterministic race cases.

        The separate entrypoint/crash test never uses this helper: its deadline
        must expire naturally to exercise the real polling lifecycle.
        """
        self.sql("UPDATE query_reservations SET deadline=clock_timestamp()-interval '1 second'")

    def recover(self):
        execution = self.sandbox.execution()
        try:
            return execution.recover_one()
        finally:
            execution.close()

    def test_v1_reader_survives_v2_publication_and_other_request_cleanup(self):
        """Keep V1 files and values stable while a V2 reader completes and cleans up."""
        # Hold V1 after staging. A V2 query then completes and cleans only its
        # own directory before V1 resumes against its original immutable files.
        entered, resume = threading.Event(), threading.Event()
        def hold(_):
            entered.set()
            if not resume.wait(15):
                raise RuntimeError('Reader barrier expired')
        self.sandbox.before_start = hold
        sql = 'SELECT SUM(outage) FROM national_outages'
        with self.observe_release() as releases, ThreadPoolExecutor(1) as pool:
            future = pool.submit(self.queries.execute, self.token, sql)
            try:
                self.assertTrue(entered.wait(10))
                first = self.sql('SELECT * FROM query_reservations')[0]
                directory = self.sandbox.stage / str(first['request_id'])
                original = {p.name: p.read_bytes() for p in (directory/'data').iterdir()}
                # Change actual producer inputs so version identity alone cannot
                # hide a query accidentally reading the new version's values.
                from test_validate import reconciled
                rows = reconciled()
                for records in rows.values():
                    for row in records:
                        row['outage'] = str(int(row['outage']) * 2)
                        row['percentOutage'] = '20'
                with patch('preview_fixture.reconciled', return_value=rows):
                    report, receipt, objects = candidate(self.root/'v2')
                event, version = publish_fixture(DSN, report, receipt)
                self.sandbox.client.add(version, objects)
                self.sandbox.before_start = None
                second = self.queries.execute(self.token, sql)
                self.assertEqual(second.publication.version_id, version)
                self.assertEqual(second.rows, [['120.000000']])
                self.assertEqual({p.name: p.read_bytes() for p in (directory/'data').iterdir()}, original)
                self.assertEqual(self.sql('SELECT state FROM query_reservations WHERE request_id=%s',
                                          (first['request_id'],))[0]['state'], 'starting')
            finally:
                resume.set()
            result = future.result(10)
            self.assertEqual(result.publication.version_id, self.version)
            self.assertEqual(result.rows, [['60.000000']])
            self.assertEqual(len(releases), 2)
        self.assert_clean()

    def test_sql_policy_and_real_container_reject_external_authority(self):
        """Reject hostile SQL before staging and probe the same sandbox with valid SQL."""
        rejected = [
            'SELECT * FROM local_users',
            "SELECT * FROM read_parquet('/etc/passwd')",
            "SELECT * FROM read_parquet('s3://private/unpublished.parquet')",
            "SELECT * FROM read_csv('https://example.invalid/data')",
            'SELECT * FROM information_schema.tables',
            'SELECT * FROM national_outages; SELECT * FROM local_sessions',
        ]
        with loopback(self.app) as client:
            for sql in rejected:
                response = client.post('/api/v1/queries', headers={'Authorization':'Bearer '+self.token},
                                       json={'sql':sql})
                self.assertEqual(response.status_code, 422)
            self.assertEqual(self.sandbox.client.calls, [])
            self.assertEqual(self.sandbox.created, [])
            # The test-only command performs stronger probes inside the actual
            # restricted container, then executes the validated SQL normally.
            # Production command verification remains unchanged.
            self.sandbox.command = '''import json,os,socket
from pathlib import Path
from trinity.queries.runtime.sql_policy import validate_query
from trinity.queries.runtime.engine import restricted_context
from trinity.queries.runtime.__main__ import run_request
for sql in %r:
 try: validate_query(sql)
 except Exception: pass
 else: raise AssertionError('validator granted external authority')
ctx=restricted_context('national',Path('/query/data'))
for table in ('local_users','local_sessions','facility_outages','information_schema.tables'):
 try: ctx.sql('SELECT * FROM '+table).collect()
 except Exception: pass
 else: raise AssertionError('unregistered table was accessible')
for path in ('/query/../unpublished-canary','/var/run/docker.sock','/run/secrets/postgres_password','/etc/shadow'):
 try: open(path,'rb')
 except OSError: pass
 else: raise AssertionError('protected file was readable')
try: open('/query/request.json','wb')
except OSError: pass
else: raise AssertionError('mount was writable')
for address in (('1.1.1.1',53),('127.0.0.1',5432)):
 try: socket.create_connection(address,timeout=.2)
 except OSError: pass
 else: raise AssertionError('network was accessible')
assert not any(k.startswith(('AWS_','TRINITY_','PGPASSWORD')) for k in os.environ)
assert len(list(Path('/query/data').glob('*.parquet')))==1
print(json.dumps(run_request(Path('/query/request.json').read_bytes(),Path('/query/data'))))
''' % rejected
            # Put a real unpublished sentinel beside request subpaths in the
            # same volume. A missing mount, not a missing sentinel, must deny it.
            sentinel = self.root/'unpublished-canary'
            sentinel.write_text('synthetic private evidence')
            helper = cli('create','--entrypoint','/bin/true','--user','0','--mount',
                         f'type=volume,src={self.sandbox.volume},dst=/stage',IMAGE)
            try:
                cli('cp',str(sentinel),helper+':/stage/unpublished-canary')
            finally:
                cli('rm',helper)
            with patch.dict(os.environ, {'AWS_SECRET_ACCESS_KEY':'synthetic-canary',
                                         'PGPASSWORD':'synthetic-canary'}), self.observe_release():
                response = client.post('/api/v1/queries', headers={'Authorization':'Bearer '+self.token},
                                       json={'sql':'SELECT SUM(outage) FROM national_outages'})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['rows'], [['60.000000']])
        self.assertTrue(all('facility' not in key and 'generator' not in key for key in self.sandbox.client.calls))
        self.assert_clean()

    def test_late_create_after_recovery_claim_cannot_start(self):
        """Complete create after ownership changes; require another recovery before release."""
        entered, resume = threading.Event(), threading.Event()
        def hold(_):
            entered.set()
            if not resume.wait(15): raise RuntimeError('Create barrier expired')
        self.sandbox.before_create = hold
        with self.observe_release() as releases, ThreadPoolExecutor(1) as pool:
            future = pool.submit(self.queries.execute, self.token, 'SELECT outage FROM national_outages')
            try:
                self.assertTrue(entered.wait(10))
                self.expire()
                with self.assertRaises(Problem): self.recover()
                self.assertEqual(self.sql('SELECT state FROM query_reservations')[0]['state'], 'creating')
                self.assertEqual(releases, [])
            finally:
                resume.set()
            with self.assertRaises(Problem): future.result(10)
            inspector = self.sandbox.execution()
            try:
                self.assertFalse(inspector.docker.inspect(self.sandbox.created[0])['State']['Running'])
            finally:
                inspector.close()
            self.expire()
            self.assertTrue(self.recover())
            self.assertEqual(len(releases), 1)
        self.assert_clean('query_timeout')

    def test_late_start_cannot_run_after_recovery_removes_container(self):
        """Resume a granted start only after recovery removes its immutable container ID."""
        entered, resume = threading.Event(), threading.Event()
        def hold(_):
            entered.set()
            if not resume.wait(15): raise RuntimeError('Start barrier expired')
        self.sandbox.before_start = hold
        with self.observe_release() as releases, ThreadPoolExecutor(1) as pool:
            future = pool.submit(self.queries.execute, self.token, 'SELECT outage FROM national_outages')
            try:
                self.assertTrue(entered.wait(10))
                self.expire()
                self.assertTrue(self.recover())
                self.assertEqual(len(releases), 1)
            finally:
                resume.set()
            with self.assertRaises(Problem): future.result(10)
        self.assert_clean('query_timeout')

    def test_start_wins_race_but_recovery_removes_before_release(self):
        """Keep the start caller suspended while recovery stops the actual running process."""
        entered, resume = threading.Event(), threading.Event()
        self.sandbox.command = 'import time; time.sleep(60)'
        def hold(_):
            entered.set()
            if not resume.wait(15): raise RuntimeError('Started barrier expired')
        self.sandbox.after_start = hold
        with self.observe_release() as releases, ThreadPoolExecutor(1) as pool:
            future = pool.submit(self.queries.execute, self.token, 'SELECT outage FROM national_outages')
            try:
                self.assertTrue(entered.wait(10))
                self.expire()
                self.assertTrue(self.recover())
                self.assertEqual(len(releases), 1)
            finally:
                resume.set()
            with self.assertRaises(Problem): future.result(10)
        self.assert_clean('query_timeout')

    def test_start_between_stop_inspection_and_delete_retains_capacity(self):
        """A stopped observation can become stale before Docker handles deletion.

        Force start into that interval. A refused deletion must retain capacity;
        the next recovery must kill and remove the now-running container.
        """
        start_waiting, allow_start = threading.Event(), threading.Event()
        started, finish_start = threading.Event(), threading.Event()
        deleting, allow_delete = threading.Event(), threading.Event()
        self.sandbox.command = 'import time; time.sleep(60)'
        def before_start(_):
            start_waiting.set()
            if not allow_start.wait(15): raise RuntimeError('Start barrier expired')
        def after_start(_):
            started.set()
            if not finish_start.wait(15): raise RuntimeError('Started barrier expired')
        self.sandbox.before_start, self.sandbox.after_start = before_start, after_start
        recovery = self.sandbox.execution()
        original = recovery.docker.call
        def before_delete(method, path, **kwargs):
            if method == 'DELETE':
                deleting.set()
                if not allow_delete.wait(15): raise RuntimeError('Delete barrier expired')
            return original(method, path, **kwargs)
        recovery.docker.call = before_delete
        try:
            with self.observe_release() as releases, ThreadPoolExecutor(2) as pool:
                owner = pool.submit(self.queries.execute, self.token, 'SELECT outage FROM national_outages')
                try:
                    self.assertTrue(start_waiting.wait(10))
                    self.expire()
                    cleaner = pool.submit(recovery.recover_one)
                    self.assertTrue(deleting.wait(10))
                    allow_start.set()
                    self.assertTrue(started.wait(10))
                    allow_delete.set()
                    with self.assertRaises(Problem): cleaner.result(5)
                    self.assertEqual(releases, [])
                    self.assertEqual(self.sql('SELECT state FROM query_reservations')[0]['state'], 'stopping')
                finally:
                    allow_start.set(); allow_delete.set(); finish_start.set()
                with self.assertRaises(Problem): owner.result(5)
                self.expire()
                self.assertTrue(self.recover())
                self.assertEqual(len(releases), 1)
        finally:
            recovery.close()
        self.assert_clean('query_timeout')

    def test_docker_create_and_start_reply_loss_after_real_side_effect(self):
        """Lose real daemon replies and resolve the created or started container safely."""
        for operation in ('create', 'start'):
            with self.subTest(operation=operation):
                prepared, execution = self.queries.prepare(self.token, 'SELECT outage FROM national_outages')
                proxy = ReplyLossProxy(SOCKET)
                execution.docker.client.close()
                execution.docker.client = httpx.Client(base_url=f'http://127.0.0.1:{proxy.port}', timeout=2)
                proxy.arm(b'/containers/create?' if operation == 'create' else b'/start HTTP/')
                self.sandbox.command = 'import time; time.sleep(60)'
                try:
                    with self.observe_release() as releases:
                        with self.assertRaises(Problem): execution.execute(prepared)
                        self.assertTrue(proxy.dropped.is_set())
                        self.assertEqual(len(releases), 1)
                finally:
                    proxy.close()
                self.assert_clean('dependency_unavailable')

    def test_kill_and_delete_reply_loss_keep_capacity_until_confirmed_recovery(self):
        """Retain capacity when stop or removal succeeds but its reply is lost."""
        for operation in ('kill', 'delete'):
            with self.subTest(operation=operation):
                prepared, execution = self.queries.prepare(self.token, 'SELECT outage FROM national_outages')
                proxy = ReplyLossProxy(SOCKET)
                execution.docker.client.close()
                execution.docker.client = httpx.Client(base_url=f'http://127.0.0.1:{proxy.port}', timeout=2)
                self.sandbox.command = 'import time; time.sleep(60)'
                # Start real work before expiring only its in-memory deadline.
                # The durable reservation stays occupied throughout cleanup.
                def expire_after_start(_):
                    prepared.deadline.end = time.monotonic() - 1
                    proxy.arm(b'/kill?' if operation == 'kill' else b'DELETE /')
                self.sandbox.after_start = expire_after_start
                try:
                    with self.observe_release() as releases:
                        with self.assertRaises(Problem): execution.execute(prepared)
                        self.assertTrue(proxy.dropped.is_set())
                        row = self.sql('SELECT * FROM query_reservations WHERE request_id=%s',
                                       (prepared.reservation['request_id'],))[0]
                        self.assertEqual(row['state'], 'stopping')
                        self.assertEqual(releases, [])
                        self.expire()
                        self.assertTrue(self.recover())
                        self.assertEqual(len(releases), 1)
                finally:
                    self.sandbox.after_start = None
                    proxy.close()
                self.assert_clean('query_timeout')

    def test_database_commit_reply_loss_retains_capacity_until_recovery(self):
        """Lose a real COMMIT reply so local state lags the durable running reservation."""
        upstream = Path(parse_qs(urlparse(DSN).query)['host'][0])/'.s.PGSQL.5432'
        proxy = ReplyLossProxy(upstream)
        # This proxy reaches only the runner's trust-authenticated Unix socket.
        # No retained credentials or network database are involved.
        dsn = f'postgresql://trinity_test_owner@127.0.0.1:{proxy.port}/trinity_test_sql?sslmode=disable'
        database = Database(ApiSettings(TRINITY_DATABASE_URL=dsn)); database.open()
        prepared, execution = self.queries.prepare(self.token, 'SELECT outage FROM national_outages')
        execution.database = database
        self.sandbox.command = 'import time; time.sleep(60)'
        transition = repository.transition
        def arm_after_running(connection, reservation, expected, state, **kwargs):
            row = transition(connection, reservation, expected, state, **kwargs)
            if state == 'running': proxy.arm(b'COMMIT')
            return row
        try:
            with self.observe_release() as releases, patch.object(repository, 'transition', side_effect=arm_after_running):
                with self.assertRaises(Problem): execution.execute(prepared)
                self.assertTrue(proxy.dropped.is_set())
                row = self.sql('SELECT * FROM query_reservations')[0]
                self.assertEqual(row['state'], 'running')
                self.assertFalse(row['cleanup_complete'])
                self.assertEqual(releases, [])
                self.expire()
                self.assertTrue(self.recover())
                self.assertEqual(len(releases), 1)
        finally:
            database.close(); proxy.close()
        self.assert_clean('query_timeout')

    def test_sigkill_recovery_entrypoint_with_natural_deadline(self):
        """Run production recovery separately after killing the owner without cleanup."""
        args = (DSN,self.token,str(self.sandbox.stage),self.sandbox.volume,self.sandbox.deployment,
                str(self.version),self.objects)
        owner = multiprocessing.get_context('spawn').Process(target=existing.crash_owner,args=(args,))
        owner.start(); owner.join(15)
        if owner.is_alive():
            owner.kill(); owner.join(); self.fail('Owner did not reach crash boundary')
        self.assertEqual(owner.exitcode, -signal.SIGKILL)
        row = self.sql('SELECT * FROM query_reservations')[0]
        self.assertEqual(row['state'], 'starting')
        env = {key: value for key,value in os.environ.items()
               if not key.startswith(('TRINITY_', 'AWS_', 'PGPASSWORD'))}
        env.update(TRINITY_DATABASE_URL=DSN,TRINITY_QUERY_STAGE_ROOT=str(self.sandbox.stage),
                   TRINITY_QUERY_STAGE_VOLUME=self.sandbox.volume,
                   TRINITY_QUERY_DEPLOYMENT_ID=str(self.sandbox.deployment),
                   TRINITY_QUERY_IMAGE=IMAGE,TRINITY_DOCKER_SOCKET=SOCKET)
        recovery = subprocess.Popen([sys.executable,'-m','trinity.queries.recovery'],env=env,
                                    stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        inspector = self.sandbox.execution()
        started = time.monotonic()
        try:
            limit = started + 45
            while time.monotonic() < limit:
                self.assertIsNone(recovery.poll(), 'Recovery entrypoint exited')
                state = self.sql('SELECT *, clock_timestamp() AS observed_at FROM query_reservations')[0]
                if state['state'] == 'released':
                    self.assertIsNone(inspector.docker.inspect(row['container_id']))
                    self.assertGreaterEqual(state['released_at'], row['deadline'])
                    break
                if state['observed_at'] < row['deadline']:
                    self.assertEqual(state['state'], 'starting')
                    self.assertFalse(state['cleanup_complete'])
                time.sleep(.05)
            else:
                self.fail('Natural-expiry recovery did not release within 45 seconds')
            with self.assertRaises(Problem): inspector.cleanup(row, 'query_timeout')
            self.assert_clean('query_timeout')
            print(f'Natural-expiry recovery entrypoint: {time.monotonic()-started:.3f}s after owner death')
        finally:
            inspector.close()
            recovery.terminate()
            try: recovery.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                recovery.kill(); recovery.communicate()
