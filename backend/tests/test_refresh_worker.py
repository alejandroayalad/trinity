"""Use real preparation children with synthetic EIA/storage and durable SQL."""
import asyncio
from dataclasses import replace
from datetime import date
import fcntl
import os
from pathlib import Path
import signal
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from postgres_fixture import DSN, PostgresFixture
from test_prepare import fixture_worker
from test_validate import reconciled
from trinity.config import EIASettings, S3Settings
from trinity.connector.prepare import Limits
from trinity.refresh.dispatch import DispatchService
from trinity.refresh.execution import ExecutionService
from trinity.workers.refresh import RefreshWorker
from trinity.workers.recovery import RecoveryService


def blocked_child(request, connection):
    """Ignore terminate so the real supervisor must kill and join this process."""
    import time
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    connection.send({'event':'started','stage':'extract:national','status':None})
    connection.recv()
    while True:time.sleep(.1)


def discovery(request):
    """Require the exact descending, one-row request; the pipeline uses its own fixture."""
    assert request.url.params['sort[0][direction]']=='desc'
    assert request.url.params['length']=='1'
    rows=reconciled()['national']
    return httpx.Response(200,json={'response':{'frequency':'daily','total':str(len(rows)),'data':[rows[-1]]}})


@unittest.skipUnless(DSN,'Use the disposable refresh runner')
class WorkerTests(PostgresFixture, unittest.TestCase):
    def setUp(self):
        super().setUp();self.setup_done()
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        response=self.client.post('/api/v1/refresh-runs',json={},headers={**self.login('admin'),'Idempotency-Key':str(uuid4())})
        self.assertEqual(response.status_code,202,response.text)
        # Fixture covers one day. The accepted policy is changed only in this
        # synthetic test before execution starts; production keeps 2024-10-02.
        self.sql("UPDATE refresh_runs SET requested_start='2026-10-01',policy_snapshot=jsonb_set(policy_snapshot,'{requested_start}','\"2026-10-01\"')")
        self.row=DispatchService(self.database,None).claim()
        self.payload=self.row['payload']

    def worker(self, mode='success', **kwargs):
        return RefreshWorker(self.database,self.root,EIASettings(EIA_API_KEY='synthetic'),
            S3Settings('synthetic-bucket',mode,'us-east-1'),worker=kwargs.pop('worker',fixture_worker),
            discovery_transport=httpx.MockTransport(discovery),**kwargs)

    def test_real_pipeline_durable_order_attempts_receipt_and_no_second_run(self):
        worker=self.worker()
        result=worker.execute(self.payload)
        self.assertEqual(result,'prepared',self.sql('SELECT * FROM refresh_runs'))
        run=self.sql('SELECT * FROM refresh_runs')[0]
        self.assertTrue(run['worker_execution_ref']['child_stopped'])
        self.assertTrue(run['worker_execution_ref']['preparation_complete'])
        self.assertGreater(run['worker_execution_ref']['operation_count'],6)
        steps=self.sql('SELECT * FROM refresh_steps ORDER BY step_seq')
        self.assertEqual([s['work_key'] for s in steps],['discover_latest','national','facility','generator','files','candidate','storage'])
        self.assertTrue(all(s['deadline_at'] for s in steps))
        self.assertTrue(all(s['total_count'] is None for s in steps[:4]))
        self.assertEqual(steps[-2]['processed_count'],39)
        self.assertIsNotNone(steps[-2]['validation_attempt_id'])
        self.assertEqual(worker.execute(self.payload),'ignored')
        self.assertEqual(self.sql('SELECT count(*) AS n FROM data_versions')[0]['n'],1)
        self.assertIsNone(self.sql('SELECT publication_event_id FROM active_publication')[0]['publication_event_id'])
        # Step 4 retains successful custody; Step 5 alone may grant readiness.
        self.assertEqual(self.sql('SELECT status FROM data_versions')[0]['status'],'validating')
        self.sql("UPDATE refresh_runs SET lease_until=now()-interval '1 second'")
        self.assertEqual(RecoveryService(self.database,self.root).once(),'receipt_pending')

    def test_failed_validation_imports_real_rows_without_readiness(self):
        self.assertEqual(self.worker('validation-failure').execute(self.payload),'failed')
        self.assertGreater(self.sql('SELECT count(*) AS n FROM validation_results')[0]['n'],0)
        self.assertGreater(self.sql("SELECT count(*) AS n FROM validation_results WHERE status='fail'")[0]['n'],0)
        version=self.sql('SELECT * FROM data_versions')[0]
        self.assertEqual(version['status'],'rejected')
        self.assertIsNone(version['diagnostics_frozen_at'])
        self.assertIsNone(version['preparation_receipt_sha256'])
        self.assertEqual(self.sql('SELECT count(*) AS n FROM failure_warnings')[0]['n'],1)

    def test_permission_denial_retains_passing_checks_but_rejects_storage(self):
        self.assertEqual(self.worker('storage-failure').execute(self.payload),'failed')
        self.assertEqual(self.sql('SELECT count(*) AS n FROM validation_results')[0]['n'],39)
        self.assertEqual(self.sql('SELECT status FROM data_versions')[0]['status'],'rejected')
        run=self.sql('SELECT * FROM refresh_runs')[0]
        operations=[]
        root=self.root/run['worker_execution_ref']['version_id']
        from trinity.contracts.manifest import read_json
        for line in (root/'evidence/preparation/journal.jsonl').read_bytes().splitlines():
            event=read_json(line)
            if event.get('kind')=='s3_put':operations.append(event)
        self.assertEqual(len(operations),1)

    def test_stage_timeout_kills_confirms_exit_and_retains_blocker(self):
        worker=self.worker(worker=blocked_child,limits=Limits(route=.4,overall=2,terminate_grace=.1))
        self.assertEqual(worker.execute(self.payload),'failed')
        run=self.sql('SELECT * FROM refresh_runs')[0]
        self.assertEqual(run['error_code'],'stage_timeout')
        self.assertTrue(run['worker_execution_ref']['child_stopped'])
        with self.assertRaises(ProcessLookupError):os.kill(run['worker_execution_ref']['child_pid'],0)
        self.assertEqual(worker.execute(self.payload),'ignored')

    def test_frozen_end_stale_fence_and_persisted_budget(self):
        execution=ExecutionService(self.database);owner=uuid4()
        run=execution.claim(self.payload,owner);fence=run['execution_fence']
        first=execution.freeze(run['id'],owner,fence,date(2026,10,2),{'measured':'2026-10-02'})
        again=execution.freeze(run['id'],owner,fence,date(2026,10,2),{'measured':'2026-10-02'})
        self.assertEqual(first['id'],again['id'])
        with self.assertRaises(Exception):execution.freeze(run['id'],owner,fence,date(2026,10,3),{})
        with self.assertRaises(Exception):execution.event(run['id'],owner,fence+1,{'event':'started','stage':'discovery'})
        execution.heartbeat(run['id'],owner,fence)
        self.assertEqual(self.sql('SELECT execution_deadline_at FROM refresh_runs')[0]['execution_deadline_at'],run['execution_deadline_at'])
        self.sql("UPDATE data_versions SET disposition='discarded',discarded_at=now(),discarded_by='test_admin'")
        with self.assertRaises(Exception):execution.event(run['id'],owner,fence,{'event':'started','stage':'discovery'})

    def test_empty_discovery_has_no_version_and_one_failed_run(self):
        worker=self.worker()
        worker.discovery_transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'response':{'frequency':'daily','data':[]}}))
        self.assertEqual(worker.execute(self.payload),'failed')
        self.assertEqual(self.sql('SELECT count(*) AS n FROM data_versions')[0]['n'],0)
        self.assertEqual(self.sql('SELECT status FROM refresh_runs')[0]['status'],'failed')

    def test_partial_validation_process_crash_imports_only_completed_rows(self):
        worker=self.worker(worker=partial_validation_child)
        self.assertEqual(worker.execute(self.payload),'failed')
        self.assertEqual(self.sql('SELECT count(*) AS n FROM validation_results')[0]['n'],3)
        self.assertEqual(self.sql("SELECT status FROM refresh_steps WHERE stage='validate'")[0]['status'],'abandoned')
        self.assertEqual(self.sql('SELECT status FROM data_versions')[0]['status'],'rejected')

    def test_object_limit_is_a_truthful_failure_without_readiness(self):
        # Use the full accepted history window with generated daily rows. Only
        # the trusted object limit is reduced, so the test avoids a 64 MiB file.
        self.sql("UPDATE refresh_runs SET requested_start='2024-10-02',policy_snapshot=jsonb_set(policy_snapshot,'{requested_start}','\"2024-10-02\"')")
        self.assertEqual(self.worker(worker=small_object_child).execute(self.payload),'failed')
        self.assertEqual(self.sql('SELECT worker_execution_ref FROM refresh_runs')[0]['worker_execution_ref']['stage'],'storage')
        self.assertGreater(self.sql("SELECT processed_count FROM refresh_steps WHERE work_key='national'")[0]['processed_count'],700)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM validation_results')[0]['n'],39)
        self.assertEqual(self.sql('SELECT status FROM data_versions')[0]['status'],'rejected')
        self.assertIsNone(self.sql('SELECT preparation_receipt_sha256 FROM data_versions')[0]['preparation_receipt_sha256'])

    def test_temporary_discovery_failure_has_three_persisted_attempts(self):
        calls=[]
        def unavailable(request):
            calls.append(request)
            return httpx.Response(503,json={'error':'synthetic'})
        worker=self.worker();worker.discovery_transport=httpx.MockTransport(unavailable)
        self.assertEqual(worker.execute(self.payload),'failed')
        self.assertEqual(len(calls),3)
        ref=self.sql('SELECT worker_execution_ref FROM refresh_runs')[0]['worker_execution_ref']
        self.assertEqual(ref['operation_count'],3)
        self.assertEqual(ref['last_operation']['attempt'],3)
        self.assertEqual(worker.execute(self.payload),'ignored')

    def test_lease_loss_stops_live_child_before_any_recovery(self):
        import threading
        import time
        outcome=[]
        worker=self.worker(worker=blocked_child,limits=Limits(route=20,overall=25,terminate_grace=.1))
        thread=threading.Thread(target=lambda:outcome.append(worker.execute(self.payload)))
        thread.start()
        try:
            for _ in range(200):
                ref=self.sql('SELECT worker_execution_ref FROM refresh_runs')[0]['worker_execution_ref'] or {}
                if ref.get('child_pid'):break
                time.sleep(.02)
            self.assertIn('child_pid',ref)
            self.sql("UPDATE refresh_runs SET lease_until=now()-interval '1 second'")
            self.assertEqual(RecoveryService(self.database,self.root).once(),'still_owned')
            thread.join(10)
            self.assertFalse(thread.is_alive())
            with self.assertRaises(ProcessLookupError):os.kill(ref['child_pid'],0)
            self.assertEqual(self.sql('SELECT status FROM refresh_runs')[0]['status'],'failed')
        finally:
            thread.join(30)

    def test_recovery_retains_unknown_owner_then_fails_confirmed_stopped_run(self):
        execution=ExecutionService(self.database);owner=uuid4()
        run=execution.claim(self.payload,owner)
        self.sql("UPDATE refresh_runs SET lease_until=now()-interval '1 second'")
        recovery=RecoveryService(self.database,self.root)
        self.assertEqual(recovery.once(),'unknown_owner')
        lock_path=self.root/f"{run['id']}.lock"
        lock_path.touch(mode=0o600)
        execution.reference(run['id'],owner,run['execution_fence'],{'host':socket.gethostname(),
            'lock_inode':lock_path.stat().st_ino,'child_stopped':False},stopped=True)
        self.assertEqual(recovery.once(),'failed')
        self.assertEqual(recovery.once(),'idle')
        self.assertEqual(self.worker().execute(self.payload),'ignored')
        self.assertEqual(self.sql('SELECT count(*) AS n FROM failure_warnings')[0]['n'],1)

    def test_direct_writes_cannot_extend_deadline_or_change_frozen_window(self):
        import psycopg
        execution=ExecutionService(self.database);owner=uuid4()
        run=execution.claim(self.payload,owner)
        execution.freeze(run['id'],owner,run['execution_fence'],date(2026,10,2),{})
        for statement in ("UPDATE refresh_runs SET execution_deadline_at=execution_deadline_at+interval '1 second'",
                          "UPDATE refresh_runs SET requested_end='2026-10-03'",
                          "UPDATE refresh_runs SET requested_start='2024-01-01'"):
            with self.assertRaises(psycopg.errors.CheckViolation):self.sql(statement)


    def test_corrupt_partial_journal_fails_with_warning_and_keeps_original_files(self):
        worker=self.worker(worker=corrupt_validation_child)
        self.assertEqual(worker.execute(self.payload),'failed')
        self.assertEqual(self.sql('SELECT count(*) AS n FROM validation_results')[0]['n'],0)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM failure_warnings')[0]['n'],1)
        ref=self.sql('SELECT worker_execution_ref FROM refresh_runs')[0]['worker_execution_ref']
        journal=self.root/ref['version_id']/'evidence'/ref['validation_attempt_id']/'journal.jsonl'
        self.assertTrue(journal.read_bytes().endswith(b'corrupt\n'))
        self.assertEqual(self.sql('SELECT status FROM data_versions')[0]['status'],'rejected')

    def test_failed_event_commit_stops_child_before_validation(self):
        worker=self.worker()
        original=worker.execution.event
        def reject(run_id,owner,fence,event):
            if event['event']=='validation_attempt':
                raise RuntimeError('synthetic database persistence failure')
            return original(run_id,owner,fence,event)
        worker.execution.event=reject
        self.assertEqual(worker.execute(self.payload),'failed')
        ref=self.sql('SELECT worker_execution_ref FROM refresh_runs')[0]['worker_execution_ref']
        self.assertTrue(ref['child_stopped'])
        with self.assertRaises(ProcessLookupError):os.kill(ref['child_pid'],0)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM validation_results')[0]['n'],0)
        self.assertEqual(worker.execute(self.payload),'ignored')

    def test_actual_crash_after_discovery_keeps_original_window(self):
        import multiprocessing
        context=multiprocessing.get_context('spawn')
        process=context.Process(target=freeze_then_crash,args=(DSN,self.payload))
        process.start();process.join(15)
        if process.is_alive():
            process.kill();process.join();self.fail('discovery owner did not exit')
        self.assertEqual(process.exitcode,8)
        run=self.sql('SELECT * FROM refresh_runs')[0]
        candidate=self.sql('SELECT * FROM data_versions')[0]
        self.assertEqual(run['requested_end'],date(2026,10,2))
        worker=self.worker()
        worker.discovery_transport=httpx.MockTransport(lambda request:self.fail('redelivery rediscovered a newer date'))
        self.assertEqual(worker.execute(self.payload),'ignored')
        self.assertEqual(self.sql('SELECT requested_end FROM refresh_runs')[0]['requested_end'],date(2026,10,2))
        self.assertEqual(self.sql('SELECT id FROM data_versions')[0]['id'],candidate['id'])


    def test_lock_file_failure_records_failure_without_starting_source_work(self):
        worker=self.worker()
        original=os.open
        def denied(path,*args,**kwargs):
            if str(path).endswith('.lock'):
                raise PermissionError('synthetic unavailable worker storage')
            return original(path,*args,**kwargs)
        with patch('trinity.workers.refresh.os.open',side_effect=denied):
            self.assertEqual(worker.execute(self.payload),'failed')
        self.assertEqual(self.sql('SELECT count(*) AS n FROM data_versions')[0]['n'],0)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM failure_warnings')[0]['n'],1)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM refresh_steps')[0]['n'],0)


    def test_unsupported_durable_policy_fails_before_external_work(self):
        self.sql("UPDATE refresh_runs SET policy_snapshot=jsonb_set(policy_snapshot,'{workflow_policy}','\"unsupported\"')")
        self.assertEqual(self.worker().execute(self.payload),'ignored')
        self.assertEqual(self.sql('SELECT status FROM refresh_runs')[0]['status'],'failed')
        self.assertEqual(self.sql('SELECT count(*) AS n FROM data_versions')[0]['n'],0)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM failure_warnings')[0]['n'],1)


def partial_validation_child(request, connection):
    """Exit at the OS boundary after three fsynced results, without cleanup."""
    from trinity.connector import validate
    original=validate._Journal.save_result
    count=0
    def save(journal,*args,**kwargs):
        nonlocal count
        result=original(journal,*args,**kwargs)
        count+=1
        if count==3:os._exit(9)
        return result
    validate._Journal.save_result=save
    fixture_worker(request,connection)


def small_object_child(request, connection):
    """Lower a trusted test-only bound; do not allocate a wasteful 64 MiB fixture."""
    from trinity.adapters import s3
    from datetime import timedelta
    import test_prepare
    original=reconciled()
    start,end=request['start'],request['end']
    first=original['national'][0]['period']
    days=[start+timedelta(days=index) for index in range((end-start).days+1)]
    rows={dataset:[{**row,'period':day.isoformat()} for day in days
                   for row in records if row['period']==first]
          for dataset,records in original.items()}
    test_prepare.reconciled=lambda:rows
    s3.MAX_OBJECT_BYTES=1024
    fixture_worker(request,connection)


def corrupt_validation_child(request, connection):
    """Retain a malformed complete journal line, then crash without cleanup."""
    from trinity.connector import validate
    original=validate._Journal.save_result
    def corrupt(journal,*args,**kwargs):
        original(journal,*args,**kwargs)
        journal.stream.write(b'corrupt\n')
        journal.stream.flush();os.fsync(journal.stream.fileno())
        os._exit(9)
    validate._Journal.save_result=corrupt
    fixture_worker(request,connection)


def freeze_then_crash(dsn,payload):
    """Commit real discovery bounds in another process, then lose that owner."""
    from trinity.adapters.postgres import Database
    from trinity.config import ApiSettings
    database=Database(ApiSettings(TRINITY_DATABASE_URL=dsn));database.open()
    execution=ExecutionService(database);owner=uuid4()
    run=execution.claim(payload,owner)
    execution.freeze(run['id'],owner,run['execution_fence'],date(2026,10,2),{'measured':'2026-10-02'})
    os._exit(8)
