"""Prove receipt handoff through real HTTP, SQL, child processes and Redis.

Source and storage bytes are synthetic. The worker, preparation, verifier,
transactions and process termination are real. Every test keeps an older active
publication so a candidate can never accidentally make this fixture pass empty.
"""
import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime
import multiprocessing
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx
import psycopg

from postgres_fixture import DSN, PostgresFixture
from refresh_worker_fixture import shared_child, storage
import test_refresh_worker as worker_tests
from trinity.adapters.postgres import Database
from trinity.adapters.queue import RefreshQueue
from trinity.config import ApiSettings, EIASettings, S3Settings
from trinity.errors import Problem
from trinity.refresh.registration import CandidateRegistration
from trinity.refresh.dispatch import DispatchService
from trinity.workers.recovery import RecoveryService
from trinity.workers.refresh import RefreshWorker


def crashing_worker(dsn, root, payload, mode, boundary):
    """Lose the actual owner before import, during verification, or after commit."""
    database = Database(ApiSettings(TRINITY_DATABASE_URL=dsn));database.open()
    original = CandidateRegistration.register
    def register(self, **kwargs):
        if boundary=='before':
            os._exit(21)
        result = original(self,**kwargs)
        os._exit(22)
    if boundary=='verify':
        import trinity.refresh.registration as registration
        registration.load_candidate = lambda *args,**kwargs:os._exit(23)
    else:
        CandidateRegistration.register = register
    settings = S3Settings('synthetic-bucket',mode,'us-east-1')
    worker = RefreshWorker(database,root,EIASettings(EIA_API_KEY='synthetic'),settings,
        worker=shared_child,discovery_transport=httpx.MockTransport(worker_tests.discovery),
        storage_factory=lambda:storage(root,settings))
    worker.execute(payload)
    os._exit(24)


@unittest.skipUnless(DSN,'Use disposable PostgreSQL/Redis acceptance')
class CandidateTests(PostgresFixture, unittest.TestCase):
    worker = worker_tests.WorkerTests.worker

    def setUp(self):
        super().setUp()
        self.setup_done()
        self.temp = TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        response = self.client.post('/api/v1/refresh-runs',json={},headers={
            **self.login('admin'),'Idempotency-Key':str(uuid4())})
        self.assertEqual(response.status_code,202,response.text)
        # Narrow only this synthetic source window before the immutable claim.
        self.sql("UPDATE refresh_runs SET requested_start='2026-10-01',policy_snapshot=jsonb_set(policy_snapshot,'{requested_start}','\"2026-10-01\"')")
        self.payload = DispatchService(self.database,None).claim()['payload']
        self.run_id = UUID(self.payload['run_id'])
        self.old_event,self.old_version = self.publish()
        self.active_before = self.sql('SELECT * FROM active_publication')
        self.admin = self.login('admin')

    def tearDown(self):
        # This also runs after assertion failures, so every route must preserve
        # the complete pointer row and the existing publication event history.
        self.assertEqual(self.sql('SELECT * FROM active_publication'),self.active_before)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM publication_events')[0]['n'],1)
        super().tearDown()

    def run_row(self):
        return self.sql('SELECT * FROM refresh_runs WHERE id=%s',(self.run_id,))[0]

    def version_row(self):
        return self.sql('SELECT * FROM data_versions WHERE run_id=%s',(self.run_id,))[0]

    def expire_lease(self):
        self.sql("UPDATE refresh_runs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",(self.run_id,))

    def recovery(self, mode='success', **kwargs):
        return RecoveryService(self.database,self.root,storage_factory=kwargs.pop('storage_factory',
            lambda:storage(self.root,S3Settings('synthetic-bucket',mode,'us-east-1'))),**kwargs)

    def crash(self, boundary='before', mode='success'):
        context = multiprocessing.get_context('spawn')
        process = context.Process(target=crashing_worker,args=(DSN,self.root,self.payload,mode,boundary))
        process.start();process.join(20)
        if process.is_alive():
            process.kill();process.join();self.fail('synthetic owner did not exit')
        self.assertEqual(process.exitcode,{'before':21,'after':22,'verify':23}[boundary])
        run = self.run_row()
        with self.assertRaises(ProcessLookupError):os.kill(run['worker_execution_ref']['child_pid'],0)
        return run

    def detail(self, headers=None, suffix=''):
        return self.client.get(f"/api/v1/candidates/{self.version_row()['id']}{suffix}",
                               headers=self.admin if headers is None else headers)

    def assert_routed(self, target):
        self.assertEqual(self.run_row()['status'],target)
        version = self.version_row()
        self.assertEqual(version['status'],'validated')
        self.assertEqual(self.sql('SELECT count(*) AS n FROM validation_results WHERE version_id=%s',
            (version['id'],))[0]['n'],39)
        self.assertEqual(self.sql("SELECT count(*) AS n FROM job_outbox WHERE run_id=%s AND job_kind='publish_version'",
            (self.run_id,))[0]['n'],int(target=='publishing'))
        response = self.detail()
        self.assertEqual(response.status_code,200,response.text)
        body = response.json()
        self.assertEqual(response.headers['etag'],f'"candidate-{body["revision"]}"')
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertIn('x-request-id',response.headers)
        self.assertEqual(body['validation']['passed_required_count'],16)
        self.assertEqual(len(body['validation']['checks']),16)
        self.assertEqual(body['validation']['status'],'passed')
        self.assertEqual(len(body['diagnostics']),23)
        self.assertEqual(body['publication']['attempt'],0)
        self.assertIsNone(body['publication']['publication_event_id'])
        self.assertIsNone(body['publication']['published_at'])
        self.assertNotIn('details_path',response.text)
        self.assertNotIn('synthetic-bucket',response.text)
        self.assertNotIn(str(self.root),response.text)
        return body

    def test_automatic_handoff_detail_and_duplicate_delivery(self):
        worker = self.worker()
        self.assertEqual(worker.execute(self.payload),'publishing')
        body = self.assert_routed('publishing')
        self.assertEqual(body['review_status'],'not_required')
        self.assertFalse(body['approval_required'])
        self.assertEqual(body['review_warning_count'],'0')
        self.assertEqual(body['publication']['status'],'queued')
        self.assertEqual(worker.execute(self.payload),'ignored')
        self.assertEqual(self.recovery().once(),'idle')
        self.assertEqual(self.detail().json(),body)

    def test_warning_handoff_requires_review_without_publication_obligation(self):
        self.assertEqual(self.worker('warnings').execute(self.payload),'awaiting_approval')
        body = self.assert_routed('awaiting_approval')
        self.assertEqual(body['review_status'],'required')
        self.assertTrue(body['approval_required'])
        self.assertGreater(int(body['review_warning_count']),0)
        self.assertEqual(body['publication']['status'],'not_started')
        self.assertTrue(next(a for a in body['actions'] if a['action']=='approve')['enabled'])

    def test_crash_before_registration_recovers_same_identity_and_budget(self):
        before = self.crash()
        version = self.version_row()
        steps = self.sql('SELECT id,deadline_at,attempt FROM refresh_steps WHERE run_id=%s',(self.run_id,))
        self.expire_lease()
        self.assertEqual(self.recovery().once(),'publishing')
        after = self.run_row()
        self.assertEqual(after['execution_fence'],before['execution_fence']+1)
        self.assertNotEqual(after['worker_owner_id'],before['worker_owner_id'])
        self.assertEqual(after['execution_deadline_at'],before['execution_deadline_at'])
        self.assertEqual(after['worker_execution_ref']['operation_count'],before['worker_execution_ref']['operation_count'])
        self.assertEqual(self.version_row()['id'],version['id'])
        self.assertEqual(self.version_row()['preparation_receipt_sha256'],before['worker_execution_ref']['receipt_sha256'])
        self.assertEqual(self.sql('SELECT id,deadline_at,attempt FROM refresh_steps WHERE run_id=%s',(self.run_id,)),steps)
        self.assert_routed('publishing')
        self.assertEqual(self.worker().execute(self.payload),'ignored')

    def test_crash_during_verification_reuses_persisted_deadline_and_attempts(self):
        before = self.crash('verify',mode='warnings')
        self.assertEqual(before['registration_attempts'],1)
        self.expire_lease()
        self.assertEqual(self.recovery('warnings').once(),'awaiting_approval')
        after = self.run_row()
        self.assertEqual(after['registration_attempts'],2)
        self.assertEqual(after['registration_deadline_at'],before['registration_deadline_at'])
        self.assert_routed('awaiting_approval')

    def test_crash_after_commit_before_acknowledgment_never_registers_twice(self):
        before = self.crash('after')
        self.assertEqual(before['status'],'publishing')
        self.assertEqual(self.recovery().once(),'idle')
        self.assertEqual(self.worker().execute(self.payload),'ignored')
        self.assertEqual(self.run_row()['registration_attempts'],1)
        self.assert_routed('publishing')

    def test_stale_owner_cannot_verify_or_import_after_recovery(self):
        before = self.crash()
        self.expire_lease()
        self.assertEqual(self.recovery().once(),'publishing')
        ref = before['worker_execution_ref']
        with patch('trinity.refresh.registration.load_candidate',side_effect=AssertionError('stale remote read')):
            with self.assertRaises(Problem) as caught:
                CandidateRegistration(self.database).register(run_id=self.run_id,
                    version_id=UUID(ref['version_id']),step_id=UUID(ref['validation_step_id']),
                    fence=before['execution_fence'],root=self.root/ref['version_id'],
                    receipt_sha256=ref['receipt_sha256'],storage=None)
        self.assertEqual(caught.exception.status,409)
        self.assert_routed('publishing')

    def test_changed_local_receipt_fails_recovery_with_explained_state(self):
        run = self.crash()
        root = self.root/run['worker_execution_ref']['version_id']
        (root/'evidence/preparation/result.json').write_bytes(b'changed')
        self.expire_lease()
        self.assertEqual(self.recovery().once(),'failed')
        self.assertEqual(self.run_row()['status'],'failed')
        body = self.detail().json()
        self.assertEqual(body['validation_status'],'rejected')
        self.assertEqual(body['review_status'],'not_ready')
        self.assertIsNone(body['approval_required'])
        self.assertIsNotNone(body['failure_warning'])
        self.assertEqual(self.recovery().once(),'idle')
        self.assertEqual((root/'evidence/preparation/result.json').read_bytes(),b'changed')

    def test_duplicate_partial_journal_cannot_strand_failed_recovery(self):
        import json
        run = self.crash()
        ref = run['worker_execution_ref']
        root = self.root/ref['version_id']
        journal = root/'evidence'/ref['validation_attempt_id']/'journal.jsonl'
        lines = journal.read_bytes().splitlines(keepends=True)
        duplicate = next(line for line in lines if json.loads(line).get('event')=='result')
        with journal.open('ab') as stream:
            stream.write(duplicate)
        self.expire_lease()
        self.assertEqual(self.recovery().once(),'failed')
        self.assertEqual(self.detail().json()['validation']['checks'],[])
        self.assertIsNotNone(self.detail().json()['failure_warning'])
        self.assertEqual(self.recovery().once(),'idle')

    def test_missing_parent_receipt_is_not_rebuilt_from_child_receipt(self):
        run = self.crash()
        root = self.root/run['worker_execution_ref']['version_id']
        (root/'evidence/preparation/result.json').unlink()
        self.expire_lease()
        self.assertEqual(self.recovery().once(),'failed')
        self.assertTrue((root/'evidence/preparation/receipt.json').is_file())
        self.assertIsNone(self.version_row()['preparation_receipt_sha256'])

    def test_missing_remote_evidence_fails_without_extracting_again(self):
        run = self.crash()
        remote = self.root/'remote'/'success'/run['worker_execution_ref']['version_id']/'manifest.json'
        remote.unlink()
        self.expire_lease()
        self.assertEqual(self.recovery().once(),'failed')
        self.assertEqual(self.worker().execute(self.payload),'ignored')
        self.assertIsNone(self.version_row()['preparation_receipt_sha256'])
        self.assertEqual(self.detail().json()['publication']['status'],'blocked')

    def test_expired_registration_budget_fails_without_remote_reads(self):
        self.crash()
        self.sql("UPDATE refresh_runs SET registration_deadline_at=clock_timestamp()-interval '1 second' WHERE id=%s",(self.run_id,))
        self.expire_lease()
        with patch('trinity.refresh.registration.load_candidate',side_effect=AssertionError('expired verification')) as read:
            self.assertEqual(self.recovery().once(),'failed')
        read.assert_not_called()
        self.assertEqual(self.run_row()['registration_attempts'],0)
        self.assertIsNotNone(self.detail().json()['failure_warning'])

    def test_registration_attempt_exhaustion_cannot_reset_budget(self):
        self.crash()
        self.sql("UPDATE refresh_runs SET registration_attempts=3,registration_deadline_at=clock_timestamp()+interval '10 seconds' WHERE id=%s",(self.run_id,))
        self.expire_lease()
        with patch('trinity.refresh.registration.load_candidate') as read:
            self.assertEqual(self.recovery().once(),'failed')
        read.assert_not_called()
        self.assertEqual(self.run_row()['registration_attempts'],3)
        for sql in ("registration_attempts=0", "registration_deadline_at=registration_deadline_at+interval '1 second'"):
            with self.assertRaises(psycopg.errors.CheckViolation):
                self.sql(f'UPDATE refresh_runs SET {sql} WHERE id=%s',(self.run_id,))

    def test_deadline_expiring_during_verification_cannot_commit_readiness(self):
        import time
        from trinity.refresh.evidence import load_candidate
        original = CandidateRegistration.register
        def register(writer, **kwargs):
            return original(writer,**{**kwargs,'timeout_seconds':.1})
        def slow_verify(*args, **kwargs):
            evidence = load_candidate(*args,**kwargs)
            time.sleep(.15)
            return evidence
        with patch.object(CandidateRegistration,'register',register), patch(
                'trinity.refresh.registration.load_candidate',side_effect=slow_verify):
            self.assertEqual(self.worker().execute(self.payload),'failed')
        self.assertIsNone(self.version_row()['preparation_receipt_sha256'])
        self.assertEqual(self.run_row()['registration_attempts'],1)
        self.assertEqual(self.detail().json()['review_status'],'not_ready')

    def test_changed_remote_bytes_fail_recovery_and_preserve_evidence(self):
        run = self.crash()
        remote = self.root/'remote'/'success'/run['worker_execution_ref']['version_id']/'manifest.json'
        remote.write_bytes(b'changed remote evidence')
        self.expire_lease()
        self.assertEqual(self.recovery().once(),'failed')
        self.assertEqual(remote.read_bytes(),b'changed remote evidence')
        self.assertIsNone(self.version_row()['preparation_receipt_sha256'])
        self.assertIsNotNone(self.detail().json()['failure_warning'])

    def test_ownership_lost_during_remote_read_cannot_commit(self):
        worker = self.worker()
        original = worker.storage_factory
        called = False
        def factory():
            result = original()
            def replace_owner(request):
                nonlocal called
                if not called:
                    called = True
                    # Exercise the second fence check after remote I/O. This
                    # direct fixture write models replacement database authority.
                    self.sql("""UPDATE refresh_runs SET execution_fence=execution_fence+1,
                        worker_owner_id=%s,lease_until=clock_timestamp()-interval '1 second'
                        WHERE id=%s""",(uuid4(),self.run_id))
            result.client.before_get = replace_owner
            return result
        worker.storage_factory = factory
        self.assertEqual(worker.execute(self.payload),'retained')
        self.assertTrue(called)
        self.assertIsNone(self.version_row()['preparation_receipt_sha256'])
        self.assertEqual(self.recovery().once(),'publishing')
        self.assert_routed('publishing')

    def test_registration_remote_reads_have_no_open_database_transaction(self):
        worker = self.worker()
        original = worker.storage_factory
        transactions = 0
        original_transaction = self.database.transaction
        @contextmanager
        def transaction(*args,**kwargs):
            nonlocal transactions
            with original_transaction(*args,**kwargs) as connection:
                transactions+=1
                try:yield connection
                finally:transactions-=1
        def factory():
            result = original()
            result.client.before_get = lambda request:self.assertEqual(transactions,0)
            return result
        worker.storage_factory = factory
        with patch.object(self.database,'transaction',transaction):
            self.assertEqual(worker.execute(self.payload),'publishing',self.run_row())
        self.assert_routed('publishing')

    def test_registration_transaction_rollback_has_no_partial_readiness(self):
        # A deferred trigger fails COMMIT after all registration writes execute.
        # The worker must journal failure separately; no artifact/intent survives.
        self.sql("""CREATE FUNCTION reject_task5_commit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'synthetic commit rejection'; END $$;
            CREATE CONSTRAINT TRIGGER reject_task5_commit AFTER INSERT ON dataset_artifacts
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION reject_task5_commit();""")
        try:
            self.assertEqual(self.worker().execute(self.payload),'failed')
        finally:
            self.sql('DROP TRIGGER reject_task5_commit ON dataset_artifacts; DROP FUNCTION reject_task5_commit()')
        version = self.version_row()
        self.assertIsNone(version['preparation_receipt_sha256'])
        self.assertEqual(self.sql('SELECT count(*) AS n FROM dataset_artifacts WHERE version_id=%s',(version['id'],))[0]['n'],0)
        self.assertEqual(self.sql("SELECT count(*) AS n FROM job_outbox WHERE job_kind='publish_version'")[0]['n'],0)
        self.assertEqual(self.run_row()['status'],'failed')
        self.assertEqual(self.detail().json()['review_status'],'not_ready')

    def test_candidate_permissions_validation_and_no_invented_checks(self):
        self.crash()
        before = self.detail()
        self.assertEqual(before.status_code,200,before.text)
        self.assertEqual(before.json()['validation']['checks'],[])
        self.assertEqual(before.json()['diagnostics'],[])
        self.assertEqual(before.json()['validation']['passed_required_count'],0)
        self.assertIsNone(before.json()['review_warning_count'])
        self.assertIsNone(before.json()['approval_required'])
        for role in ('viewer','analyst'):
            headers = self.login(role)
            self.assertEqual(self.detail(headers).status_code,403)
            self.assertEqual(self.client.get('/api/v1/candidates/not-a-uuid',headers=headers).status_code,403)
        self.assertEqual(self.detail({}).status_code,401)
        self.assertEqual(self.detail(suffix='?limit=1').status_code,422)
        self.assertEqual(self.client.get('/api/v1/candidates/not-a-uuid',headers=self.admin).status_code,422)
        self.assertEqual(self.client.get(f'/api/v1/candidates/{uuid4()}',headers=self.admin).status_code,404)
        self.expire_lease();self.assertEqual(self.recovery().once(),'publishing')
        self.assertNotEqual(self.detail().headers['etag'],before.headers['etag'])
        # Existing sessions lose access immediately when their stored role changes.
        self.sql("UPDATE local_users SET role='viewer' WHERE id='test_admin'")
        self.assertEqual(self.detail().status_code,403)

    def test_candidate_revision_changes_with_visible_validation_progress(self):
        from datetime import date
        from trinity.refresh.execution import ExecutionService
        execution = ExecutionService(self.database)
        owner = uuid4()
        run = execution.claim(self.payload,owner)
        execution.freeze(self.run_id,owner,run['execution_fence'],date(2026,10,3),{})
        pending = self.detail()
        self.assertEqual(pending.json()['validation']['status'],'pending')
        execution.event(self.run_id,owner,run['execution_fence'],{'event':'started','stage':'validation'})
        running = self.detail()
        self.assertEqual(running.json()['validation']['status'],'running')
        self.assertNotEqual(running.headers['etag'],pending.headers['etag'])
        execution.event(self.run_id,owner,run['execution_fence'],{
            'event':'finished','stage':'validation','status':'success'})
        incomplete = self.detail()
        self.assertEqual(incomplete.json()['validation']['status'],'incomplete')
        self.assertEqual(incomplete.json()['validation']['checks'],[])
        self.assertNotEqual(incomplete.headers['etag'],running.headers['etag'])

    def test_partial_failed_checks_remain_partial_in_candidate_detail(self):
        self.assertEqual(self.worker(worker=worker_tests.partial_validation_child).execute(self.payload),'failed')
        body = self.detail().json()
        self.assertEqual(len(body['validation']['checks']),3)
        self.assertEqual(body['validation']['passed_required_count'],3)
        self.assertEqual(body['validation']['status'],'incomplete')
        self.assertEqual(body['diagnostics'],[])
        self.assertIsNone(body['approval_required'])
        self.assertEqual(body['review_status'],'not_ready')

    @unittest.skipUnless(os.environ.get('TRINITY_TEST_REDIS_PORT'),'Use disposable Redis runner')
    def test_real_redis_delivery_runs_preparation_and_registers_once(self):
        async def exercise():
            queue = RefreshQueue({'host':'127.0.0.1','port':int(os.environ['TRINITY_TEST_REDIS_PORT']),
                'socket_connect_timeout':2,'socket_timeout':2},name=f'task5-{uuid4()}')
            worker = self.worker()
            consumer = queue.consumer(worker.process)
            try:
                await queue.enqueue(self.payload)
                for _ in range(300):
                    if await queue.state(self.payload)=='completed':break
                    await asyncio.sleep(.05)
                self.assertEqual(await queue.state(self.payload),'completed')
                self.assert_routed('publishing')
                await queue.enqueue(self.payload)
                self.assertEqual(await queue.state(self.payload),'completed')
                self.assertEqual(await asyncio.to_thread(worker.execute,self.payload),'ignored')
                self.assertEqual(self.run_row()['registration_attempts'],1)
            finally:
                await consumer.close();await queue.close()
        asyncio.run(exercise())


class CandidateContractTests(unittest.TestCase):
    """Keep the implemented closed response fields aligned with canonical OpenAPI."""
    def test_candidate_models_keep_all_canonical_fields_and_null_slots(self):
        import json
        from trinity.refresh import candidates
        contract = json.loads((Path(__file__).resolve().parents[2]/'docs/openapi.json').read_text())
        for name in ('Candidate','DateRange','Validation','ValidationCheck','Diagnostic','Approval','PublicationProgress'):
            with self.subTest(schema=name):
                expected = contract['components']['schemas'][name]
                model = getattr(candidates,name)
                self.assertEqual(set(model.model_fields),set(expected['properties']))
                self.assertEqual(model.model_config['extra'],'forbid')
                required = {key for key,value in model.model_fields.items() if value.is_required()}
                self.assertEqual(required,set(expected['required'])-({'expected_required_count'} if name=='Validation' else set()))
