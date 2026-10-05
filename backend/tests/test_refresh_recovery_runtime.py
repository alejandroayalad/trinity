"""Check recovery across real SQL, HTTP sockets, Redis and worker processes.

Use only the disposable runners. Concurrent calls use separate database
transactions behind one start barrier. Source rows and object storage remain
synthetic. These checks do not establish retained deployment or EIA coverage.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import os
from pathlib import Path
import socket
import threading
from tempfile import TemporaryDirectory
import unittest
from uuid import UUID, uuid4

import httpx
from postgres_fixture import DSN, PostgresFixture
from preview_fixture import loopback
from publication_fixture import PublicationFixture
from publication_process_fixture import crash_publisher
from test_refresh_recovery_postgres import RecoveryFixture
import test_refresh_worker as worker_fixture
from trinity.adapters.postgres import Deadline
from trinity.adapters.queue import RefreshQueue
from trinity.connector.prepare import Limits
from trinity.errors import Problem
from trinity.main import create_app
from trinity.publication.commands import PublicationCommands
from trinity.publication.service import PublicationService
from trinity.refresh.dispatch import DispatchService
from trinity.refresh.execution import ExecutionService
from trinity.refresh.recovery import RecoveryService
from trinity.refresh.service import RefreshService


def race(*actions):
    """Release independent transactions together; return safe outcomes in order."""
    start = threading.Barrier(len(actions))

    def call(action):
        start.wait(timeout=10)
        try:
            return action()
        except Problem as error:
            return error.status

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        futures = [pool.submit(call, action) for action in actions]
        return [future.result(timeout=30) for future in futures]


@unittest.skipUnless(DSN, 'Use the disposable refresh runner')
class RecoveryRuntimeTests(RecoveryFixture, unittest.TestCase):
    """Check admission, current authority and real lost-response replay."""

    def command(self, action='rerun', key=None):
        """Run the production service without sharing an HTTP test client."""
        return RecoveryService(self.database).command(
            self.admin['Authorization'][7:], str(self.run_id), action,
            b'{}' if action == 'rerun' else b'', [key or self.key], [self.etag])

    def test_rerun_and_delete_have_one_winner(self):
        self.failure()
        results = race(self.command, lambda: self.command('delete_warning', str(uuid4())))
        self.assertEqual(sum(not isinstance(result, int) for result in results), 1)
        self.assertTrue(any(result in (409, 412) for result in results if isinstance(result, int)))
        self.assertEqual(len(self.sql('SELECT id FROM api_commands WHERE target_id=%s', (self.run_id,))), 1)
        holder = self.sql('SELECT holder_run_id FROM refresh_control')[0]['holder_run_id']
        reruns = self.sql("SELECT id FROM refresh_runs WHERE trigger_kind='rerun'")
        self.assertEqual(holder, reruns[0]['id'] if reruns else None)

    def test_same_key_race_replays_one_receipt(self):
        self.failure()
        results = race(self.command, self.command)
        self.assertTrue(all(not isinstance(result, int) for result in results))
        self.assertEqual(results[0].operation_id, results[1].operation_id)
        self.assertEqual(sorted(result.replayed for result in results), [False, True])
        self.assertEqual(len(self.sql('SELECT id FROM refresh_runs')), 2)

    def test_rerun_excludes_manual_start(self):
        self.failure()
        results = race(self.command, lambda: RefreshService(self.database).start(
            self.admin['Authorization'][7:], b'{}', [str(uuid4())]))
        self.assertFalse(isinstance(results[0], int))
        self.assertEqual(results[1], 409)
        self.assertEqual(len(self.sql('SELECT id FROM refresh_runs')), 2)

    def test_delete_cannot_release_a_new_manual_owner(self):
        self.failure()
        results = race(lambda: self.command('delete_warning'), lambda: RefreshService(self.database).start(
            self.admin['Authorization'][7:], b'{}', [str(uuid4())]))
        self.assertFalse(isinstance(results[0], int))
        if results[1] == 409:
            results[1] = RefreshService(self.database).start(
                self.admin['Authorization'][7:], b'{}', [str(uuid4())])
        new_run = results[1].run_id
        self.assertTrue(self.command('delete_warning').replayed)
        self.assertEqual(self.sql('SELECT holder_run_id FROM refresh_control')[0]['holder_run_id'], new_run)

    def scheduled_admission(self):
        """Exercise shared admission, not the absent scheduler clock loop."""
        from trinity.refresh.repository import lock_control, _insert_run
        from trinity.settings.repository import read_settings
        with self.database.transaction(Deadline()) as connection:
            control = lock_control(connection)
            if control['holder_run_id'] is not None:
                raise Problem(409, 'refresh_blocked')
            connection.execute('SELECT id FROM shared_settings WHERE id=1 FOR SHARE')
            return _insert_run(connection, 'scheduled', None, uuid4(), read_settings(connection))['id']

    def test_rerun_excludes_scheduled_admission_primitive(self):
        self.failure()
        results = race(self.command, self.scheduled_admission)
        self.assertFalse(isinstance(results[0], int))
        self.assertEqual(results[1], 409)
        self.assertEqual(len(self.sql('SELECT id FROM refresh_runs')), 2)

    def test_delete_replay_preserves_new_scheduled_owner(self):
        self.failure()
        results = race(lambda: self.command('delete_warning'), self.scheduled_admission)
        self.assertFalse(isinstance(results[0], int))
        new_run = self.scheduled_admission() if results[1] == 409 else results[1]
        self.assertTrue(self.command('delete_warning').replayed)
        self.assertEqual(self.sql('SELECT holder_run_id FROM refresh_control')[0]['holder_run_id'], new_run)

    def test_settings_writer_and_rerun_keep_one_committed_snapshot(self):
        self.failure()

        def update():
            # Exercise the shared settings row lock. The separate settings
            # mutation endpoint is absent here; this checks its SQL boundary.
            with self.database.transaction(Deadline()) as connection:
                connection.execute('UPDATE shared_settings SET revision=revision+1')
            return 'updated'

        results = race(self.command, update)
        self.assertFalse(isinstance(results[0], int))
        new = self.sql('SELECT * FROM refresh_runs WHERE id=%s', (results[0].run_id,))[0]
        self.assertIn(new['settings_revision'], (1, 2))
        self.assertEqual(new['policy_snapshot']['settings_revision'], new['settings_revision'])
        old = self.sql('SELECT settings_revision FROM refresh_runs WHERE id=%s', (self.run_id,))[0]
        self.assertEqual(old['settings_revision'], 1)

    def test_logout_race_never_authorizes_later_replay(self):
        self.failure()
        results = race(self.command, lambda: self.service.logout(self.admin['Authorization'][7:]))
        self.assertTrue(not isinstance(results[0], int) or results[0] == 401)
        self.assertEqual(self.recover().status_code, 401)
        self.assertIn(len(self.sql('SELECT id FROM refresh_runs')), (1, 2))

    def test_role_change_race_never_authorizes_later_replay(self):
        self.failure()
        results = race(self.command, lambda: self.sql("UPDATE local_users SET role='viewer' WHERE id='test_admin'"))
        self.assertTrue(not isinstance(results[0], int) or results[0] == 403)
        self.assertEqual(self.recover().status_code, 403)
        self.assertIn(len(self.sql('SELECT id FROM refresh_runs')), (1, 2))

    def test_real_control_lock_timeout_returns_safe_error_without_writes(self):
        """A competing transaction owns admission beyond the API wait budget."""
        import psycopg
        self.failure()
        before = self.snapshot()
        with psycopg.connect(DSN) as blocker:
            blocker.execute('SELECT id FROM refresh_control WHERE id=1 FOR UPDATE')
            response = self.recover()
            self.assertEqual(response.status_code, 503, response.text)
            self.assertEqual(response.json()['code'], 'dependency_unavailable')
            self.assertEqual(response.headers['retry-after'], '1')
        self.assertEqual(self.snapshot(), before)

    def test_socket_response_loss_replays_committed_result(self):
        self.failure()
        app = create_app(service=self.service)
        dropped = []

        async def lose_response(scope, receive, send):
            """Close the first success after headers, before its promised body."""
            async def intercept(message):
                if (scope.get('path', '').endswith('/rerun') and not dropped
                        and message['type'] == 'http.response.start' and message['status'] == 202):
                    dropped.append(True)
                    await send(message)
                    raise RuntimeError('Synthetic response loss after committed acceptance')
                await send(message)
            await app(scope, receive, intercept)

        headers = self.admin | {'Idempotency-Key': self.key, 'If-Match': self.etag}
        with loopback(lose_response) as client:
            with self.assertRaises(httpx.RemoteProtocolError):
                client.post(f'/api/v1/refresh-runs/{self.run_id}/rerun', json={}, headers=headers)
            replay = client.post(f'/api/v1/refresh-runs/{self.run_id}/rerun', json={}, headers=headers)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertTrue(replay.json()['replayed'])
            detail = client.get(f'/api/v1/refresh-runs/{self.run_id}', headers=self.admin)
            self.assertEqual(detail.status_code, 200)
            self.assertNotEqual(detail.headers['etag'], self.etag)
            self.assertTrue(all(not action['enabled'] for action in detail.json()['actions']
                                if action['action'] in ('rerun', 'delete_warning')))
            self.assertEqual(detail.json()['warning']['resolution'], 'rerun')
            for path in ('/api/v1/me', '/api/v1/refresh-runs'):
                self.assertEqual(client.get(path, headers=self.admin).status_code, 200)
        self.assertEqual(len(dropped), 1)
        self.assertEqual(len(self.sql('SELECT id FROM refresh_runs')), 2)

    @unittest.skipUnless(os.environ.get('TRINITY_TEST_REDIS_PORT'), 'Use the Redis runner')
    def test_queue_outage_then_real_redis_delivery_claims_rerun_once(self):
        self.failure()
        response = self.recover()
        self.assertEqual(response.status_code, 202)
        new_run = UUID(response.json()['run_id'])

        async def scenario():
            # A bound, non-listening socket reserves a genuinely unavailable
            # local port. No retained Redis service is stopped or reconfigured.
            with socket.socket() as reserved:
                reserved.bind(('127.0.0.1', 0))
                unavailable = RefreshQueue({'host': '127.0.0.1', 'port': reserved.getsockname()[1],
                    'socket_connect_timeout': .1, 'socket_timeout': .1}, name=str(uuid4()), timeout=.3)
                try:
                    self.assertTrue(await DispatchService(self.database, unavailable).once())
                finally:
                    await unavailable.close()
            row = self.sql('SELECT * FROM job_outbox WHERE run_id=%s', (new_run,))[0]
            self.assertEqual((row['status'], row['last_error']), ('pending', 'queue_unavailable'))
            self.sql('UPDATE job_outbox SET available_at=now() WHERE run_id=%s', (new_run,))
            queue = RefreshQueue({'host': '127.0.0.1', 'port': int(os.environ['TRINITY_TEST_REDIS_PORT'])},
                                 name='recovery-' + str(uuid4()))
            claims = []

            async def consume(job, token):
                """Use the real fence claim; this test does not extract data."""
                claim = ExecutionService(self.database).claim(job.data, uuid4())
                if claim:
                    claims.append(claim['id'])

            consumer = queue.consumer(consume)
            try:
                self.assertTrue(await DispatchService(self.database, queue).once())
                for _ in range(200):
                    if await queue.state(row['payload']) == 'completed':
                        break
                    await asyncio.sleep(.05)
                self.assertEqual(await queue.state(row['payload']), 'completed')
                await queue.enqueue(row['payload'])
                self.assertIsNone(ExecutionService(self.database).claim(row['payload'], uuid4()))
                self.assertEqual(claims, [new_run])
            finally:
                await consumer.close()
                await queue.close()
        asyncio.run(scenario())
        self.assertEqual(len(self.sql('SELECT id FROM refresh_runs')), 2)

    @unittest.skipUnless(os.environ.get('TRINITY_TEST_REDIS_PORT'), 'Use the Redis runner')
    def test_deleted_warning_has_no_dispatchable_job(self):
        self.failure()
        self.assertEqual(self.recover('delete_warning').status_code, 200)

        async def scenario():
            queue = RefreshQueue({'host': '127.0.0.1', 'port': int(os.environ['TRINITY_TEST_REDIS_PORT'])},
                                 name='recovery-' + str(uuid4()))
            try:
                self.assertFalse(await DispatchService(self.database, queue).once())
                payload = self.sql('SELECT payload FROM job_outbox')[0]['payload']
                self.assertEqual(await queue.state(payload), 'unknown')
            finally:
                await queue.close()
        asyncio.run(scenario())


@unittest.skipUnless(DSN, 'Use the disposable refresh runner')
class RecoveryChildTests(PostgresFixture, unittest.TestCase):
    """Require measured termination before recovery accepts a real child failure."""
    worker = worker_fixture.WorkerTests.worker

    def setUp(self):
        # Reuse the worker builder while keeping this fixture independent.
        super().setUp()
        self.setup_done()
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        response = self.client.post('/api/v1/refresh-runs', json={},
            headers=self.login('admin') | {'Idempotency-Key': str(uuid4())})
        self.assertEqual(response.status_code, 202)
        self.row = DispatchService(self.database, None).claim()
        self.payload = self.row['payload']

    def recover(self, action='rerun'):
        """Read a fresh revision after the worker has recorded its outcome."""
        run = self.sql('SELECT * FROM refresh_runs ORDER BY run_seq')[0]
        headers = self.login('admin') | {'Idempotency-Key': str(uuid4()), 'If-Match': f'"run-{run["revision"]}"'}
        if action == 'rerun':
            return self.client.post(f'/api/v1/refresh-runs/{run["id"]}/rerun', json={}, headers=headers)
        return self.client.delete(f'/api/v1/refresh-runs/{run["id"]}/warning', headers=headers)

    def test_killed_child_old_writes_and_delivery_cannot_revive(self):
        worker = self.worker(worker=worker_fixture.blocked_child, limits=Limits(route=.4, overall=2, terminate_grace=.1))
        self.assertEqual(worker.execute(self.payload), 'failed')
        old = self.sql('SELECT * FROM refresh_runs')[0]
        ref = old['worker_execution_ref']
        self.assertTrue(ref['child_stopped'])
        with self.assertRaises(ProcessLookupError):
            os.kill(ref['child_pid'], 0)
        self.assertEqual(self.recover().status_code, 202)
        with self.assertRaises(Problem):
            ExecutionService(self.database).heartbeat(old['id'], old['worker_owner_id'], old['execution_fence'])
        self.assertEqual(worker.execute(self.payload), 'ignored')
        self.assertEqual(len(self.sql('SELECT id FROM publication_events')), 0)

    def test_exhausted_dispatch_is_recoverable_without_a_worker(self):
        dispatcher = DispatchService(self.database, None)
        row = self.row
        for attempt in range(3):
            self.assertTrue(dispatcher.acknowledge(row, succeeded=False))
            self.sql('UPDATE job_outbox SET available_at=now()')
            row = dispatcher.claim()
        self.assertIsNone(row)
        self.assertEqual(self.sql('SELECT error_code FROM refresh_runs')[0]['error_code'], 'dispatch_failed')
        self.assertEqual(self.recover('delete_warning').status_code, 200)
        self.assertEqual(len(self.sql('SELECT id FROM refresh_runs')), 1)

    def test_unsupported_policy_is_recoverable_before_child_launch(self):
        self.sql("UPDATE refresh_runs SET policy_snapshot=jsonb_set(policy_snapshot,'{workflow_policy}','\"unsupported\"')")
        self.assertEqual(self.worker().execute(self.payload), 'ignored')
        self.assertEqual(self.recover().status_code, 202)
        self.assertIsNone(self.sql('SELECT started_at FROM refresh_runs ORDER BY run_seq')[0]['started_at'])


@unittest.skipUnless(DSN, 'Use the disposable refresh runner')
class RecoveryPublicationTests(PublicationFixture, unittest.TestCase):
    """Keep a published baseline while abandoning a genuinely crashed publisher."""

    def stopped_publisher(self):
        """Crash a separate worker, then use the operator's stop-proof path."""
        self.setup_done()
        self.assertIsNotNone(self.worker.execute(self.payload()))
        self.baseline = self.sql('SELECT * FROM active_publication')
        self.new_candidate()
        payload = self.payload()
        process = multiprocessing.get_context('spawn').Process(target=crash_publisher,
            args=(DSN, self.root, payload, self.objects, 'after_claim', str(self.root / 'crash-marker')))
        process.start()
        process.join(20)
        if process.is_alive():
            process.kill()
            process.join()
            self.fail('Synthetic publisher did not stop')
        self.assertEqual(process.exitcode, 17)
        self.old_claim = (self.row(), self.sql('SELECT * FROM data_versions WHERE id=%s', (self.version,))[0],
            self.sql("SELECT * FROM refresh_steps WHERE run_id=%s AND stage='publish'", (self.run,))[0])
        self.expire()
        row = self.row()
        code, result = self.operator('--expected-generation', str(row['publication_generation']),
                                     '--expected-fence', str(row['execution_fence']))
        self.assertEqual(code, 0, result)
        self.assertEqual(result['outcome'], 'recovered_failure')
        self.run_etag = f'"run-{self.row()["revision"]}"'
        self.version_etag = f'"candidate-{self.sql("SELECT revision FROM data_versions WHERE id=%s", (self.version,))[0]["revision"]}"'
        return payload

    def recover(self, action='rerun'):
        """Use the current Admin with the revision captured before the race."""
        return RecoveryService(self.database).command(self.admin['Authorization'][7:], str(self.run), action,
            b'{}' if action == 'rerun' else b'', [str(uuid4())], [self.run_etag])

    def test_crashed_publisher_abandonment_rejects_old_commit(self):
        payload = self.stopped_publisher()
        files = {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        self.recover()
        with self.assertRaises(Problem) as rejected:
            PublicationService(self.database).finish(self.old_claim, None)
        self.assertEqual(rejected.exception.status, 409)
        self.assertIsNone(self.worker.execute(payload))
        self.assertEqual(self.sql('SELECT * FROM active_publication'), self.baseline)
        self.assertEqual(len(self.sql('SELECT id FROM publication_events')), 1)
        self.assertEqual({str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}, files)

    def publication_race(self, recovery_action, publication_action):
        """Exactly one recovery or candidate command owns the failed lifecycle."""
        self.stopped_publisher()
        results = race(lambda: self.recover(recovery_action), lambda: PublicationCommands(self.database).command(
            self.admin['Authorization'][7:], str(self.version), publication_action, b'{}', [str(uuid4())], [self.version_etag]))
        self.assertEqual(sum(not isinstance(result, int) for result in results), 1)
        self.assertTrue(any(result in (409, 412) for result in results if isinstance(result, int)))
        self.assertEqual(self.sql('SELECT * FROM active_publication'), self.baseline)

    def test_live_publication_commit_cannot_be_abandoned(self):
        """Hold the actual writer before commit; recovery must reject its state."""
        from unittest.mock import patch
        self.setup_done()
        ready, release = threading.Event(), threading.Event()
        original = PublicationService.finish

        def pause(service, claim, evidence):
            ready.set()
            if not release.wait(15):
                raise RuntimeError('Test did not release publication')
            return original(service, claim, evidence)

        with patch.object(PublicationService, 'finish', pause), ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(self.worker.execute, self.payload())
            try:
                self.assertTrue(ready.wait(10))
                self.run_etag = f'"run-{self.row()["revision"]}"'
                with self.assertRaises(Problem) as rejected:
                    self.recover()
                self.assertEqual(rejected.exception.status, 409)
            finally:
                release.set()
            self.assertIsNotNone(result.result(timeout=15))
        self.assertEqual(self.row()['status'], 'succeeded')
        self.assertEqual(len(self.sql('SELECT id FROM publication_events')), 1)
        self.assertIsNone(self.sql('SELECT holder_run_id FROM refresh_control')[0]['holder_run_id'])

    def test_delete_races_publication_retry(self):
        self.publication_race('delete_warning', 'retry')

    def test_rerun_races_candidate_discard(self):
        self.publication_race('rerun', 'discard')

    def test_rerun_races_publication_retry(self):
        self.publication_race('rerun', 'retry')

    def test_delete_races_candidate_discard(self):
        self.publication_race('delete_warning', 'discard')
