"""Exercise real registration, transactions, commands and operator subprocesses."""
import fcntl
import unittest
from unittest.mock import patch
from uuid import uuid4
from botocore.exceptions import EndpointConnectionError
from postgres_fixture import DSN
from publication_fixture import PublicationFixture
from trinity.adapters.postgres import Deadline
from trinity.refresh.evidence import load_candidate
from trinity.publication.service import PublicationService
from trinity.errors import Problem

@unittest.skipUnless(DSN,'Disposable PostgreSQL required')
class PublicationPostgresTests(PublicationFixture,unittest.TestCase):
    def test_automatic_duplicate_after_newer_event(self):
        old=self.payload();first=self.worker.execute(old)
        self.assertEqual(self.row()['status'],'succeeded')
        self.assertIsNone(self.sql('SELECT holder_run_id FROM refresh_control')[0]['holder_run_id'])
        self.new_candidate();second=self.worker.execute(self.payload())
        with patch('trinity.publication.service.load_candidate') as verify:
            duplicate=self.worker.execute(old);verify.assert_not_called()
        self.assertEqual(duplicate['id'],first['id'])
        self.assertEqual(self.sql('SELECT publication_event_id FROM active_publication')[0]['publication_event_id'],second['id'])
        self.assertEqual(self.sql('SELECT count(*) AS n FROM publication_events')[0]['n'],2)

    def test_approved_temporary_failure_retry_preserves_approval(self):
        self.worker.execute(self.payload());self.new_candidate(warnings=True)
        response=self.command('approve');self.assertEqual(response.status_code,202,response.text)
        original=self.sql('SELECT * FROM approvals WHERE version_id=%s',(self.version,))[0]
        original_get=self.storage.client.get_object;self.storage.sleep=lambda _:None
        self.storage.client.get_object=lambda **_:(_ for _ in ()).throw(EndpointConnectionError(endpoint_url='synthetic'))
        self.worker.execute(self.payload());self.assertEqual(self.row()['status'],'publication_failed')
        self.assertIsNone(self.row()['finished_at'])
        failed=self.sql('SELECT * FROM failure_warnings WHERE run_id=%s',(self.run,))[0]
        self.assertEqual(failed['code'],'storage_temporary')
        # A second Admin retries. Historical publication attribution must still
        # name the first approving Admin, not the recovery actor.
        self.sql("INSERT INTO local_users(id,username,password_hash,role) VALUES ('retry_admin','retry_admin',%s,'admin')",(self.hashes['admin'],))
        login=self.client.post('/api/v1/auth/login',json={'username':'retry_admin','password':self.passwords['admin']})
        self.admin={'Authorization':'Bearer '+login.json()['access_token']}
        key=str(uuid4());response=self.command('publication-retry',key=key)
        self.assertEqual(response.status_code,202,response.text)
        replay=self.command('publication-retry',key=key,etag='"candidate-0"')
        self.assertEqual(replay.status_code,200,replay.text);self.assertTrue(replay.json()['replayed'])
        self.storage.client.get_object=original_get;event=self.worker.execute(self.payload())
        self.assertEqual(event['approval_id'],original['id']);self.assertEqual(event['actor_id'],original['approved_by'])
        self.assertEqual(self.row()['publication_generation'],1)
        self.assertEqual(self.sql('SELECT actor_id FROM api_commands WHERE idempotency_key=%s',(key,))[0]['actor_id'],'retry_admin')
        self.assertEqual(self.sql('SELECT * FROM approvals WHERE version_id=%s',(self.version,))[0],original)

    def test_integrity_failure_discard_and_new_refresh(self):
        path=self.report.root/'data/national.parquet';raw=path.read_bytes();path.write_bytes(b'changed')
        self.worker.execute(self.payload());path.write_bytes(raw)
        self.assertEqual(self.command('publication-retry').status_code,409)
        detail=self.client.get(f'/api/v1/candidates/{self.version}',headers=self.admin)
        self.assertEqual(detail.status_code,200,detail.text)
        actions={item['action']:item['enabled'] for item in detail.json()['actions']}
        self.assertFalse(actions['publication_retry']);self.assertTrue(actions['discard'])
        # Corrupt evidence blocks retry of this candidate. The publisher has
        # stopped, so an Admin can instead abandon it through run recovery.
        self.assertTrue(actions['rerun']);self.assertTrue(actions['delete_warning'])
        self.assertEqual(self.command('discard').status_code,200);self.assertTrue(path.exists())
        self.assertIsNone(self.worker.execute(self.payload()))
        self.assertIsNone(self.sql('SELECT publication_event_id FROM active_publication')[0]['publication_event_id'])
        response=self.client.post('/api/v1/refresh-runs',json={},headers={**self.admin,'Idempotency-Key':str(uuid4())})
        self.assertEqual(response.status_code,202,response.text)

    def test_authority_etags_replay_and_body(self):
        self.worker.execute(self.payload());self.new_candidate(warnings=True)
        for role in ('viewer','analyst'):
            for action in ('approve','discard','publication-retry'):
                self.assertEqual(self.command(action,headers=self.login(role)).status_code,403)
        self.assertEqual(self.command('approve',headers={}).status_code,401)
        self.assertEqual(self.command('approve',body={'actor':'test_admin'}).status_code,422)
        self.assertEqual(self.command('approve',etag='*').status_code,422)
        self.assertEqual(self.command('approve',etag='"candidate-0"').status_code,412)
        key=str(uuid4());response=self.command('approve',key=key);self.assertEqual(response.status_code,202,response.text)
        self.assertEqual(self.command('discard',key=key).status_code,409)
        self.sql("UPDATE local_users SET role='viewer' WHERE id='test_admin'")
        self.assertEqual(self.command('approve',key=key).status_code,403)

    def test_operator_lock_guards_repeat_and_retry(self):
        PublicationService(self.database).claim(self.payload())
        code,value=self.operator('--inspect');self.assertEqual((code,value['outcome']),(0,'inspected'))
        args=('--expected-generation','0','--expected-fence',str(value['execution_fence']))
        self.assertEqual(self.operator(*args)[1]['reason_code'],'lease_not_expired');self.expire()
        lock=self.root/f'{self.run}.lock'
        with lock.open('rb') as held:
            fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(self.operator(*args)[1]['reason_code'],'lock_held')
        old=lock.with_suffix('.old');lock.rename(old)
        self.assertEqual(self.operator(*args)[0],3);lock.touch(mode=0o600)
        self.assertEqual(self.operator(*args)[1]['reason_code'],'lock_replaced')
        lock.unlink();old.rename(lock)
        code,value=self.operator(*args);self.assertEqual((code,value['outcome']),(0,'recovered_failure'))
        self.assertTrue(value['retry_eligible']);before=self.row()
        self.assertEqual(self.operator(*args)[1]['outcome'],'already_failed');self.assertEqual(self.row(),before)
        self.assertEqual(self.command('publication-retry').status_code,202)
        self.assertEqual(self.operator(*args)[1]['reason_code'],'stale_target')
        self.assertIsNotNone(self.worker.execute(self.payload()))
        self.assertEqual(self.operator('--expected-generation','1','--expected-fence','0')[1]['outcome'],'already_published')

    def test_commit_rejection_rolls_back_and_keeps_claim_consumed(self):
        # Defer rejection until COMMIT to prove every final write rolls back.
        self.sql("""CREATE FUNCTION publication_test_reject() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'test commit rejection' USING ERRCODE='23514'; END $$;
            CREATE CONSTRAINT TRIGGER publication_test_reject AFTER INSERT ON publication_events
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION publication_test_reject()""")
        try:
            with self.assertRaises(Problem):self.worker.execute(self.payload())
            self.assertEqual(self.row()['status'],'publishing')
            self.assertEqual(self.sql('SELECT count(*) AS n FROM publication_events')[0]['n'],0)
            self.assertIsNone(self.sql('SELECT publication_event_id FROM active_publication')[0]['publication_event_id'])
            self.assertEqual(self.sql('SELECT holder_run_id FROM refresh_control')[0]['holder_run_id'],self.run)
            self.assertEqual(self.sql("SELECT status FROM refresh_steps WHERE stage='publish'")[0]['status'],'running')
        finally:
            self.sql('DROP TRIGGER publication_test_reject ON publication_events; DROP FUNCTION publication_test_reject()')
        with patch('trinity.publication.service.load_candidate') as verifier:
            self.worker.execute(self.payload());verifier.assert_not_called()
        self.expire();run=self.row()
        self.assertEqual(self.operator('--expected-generation','0','--expected-fence',str(run['execution_fence']))[0],0)

    def test_each_final_write_rollback_and_lost_commit_response(self):
        from contextlib import contextmanager
        from trinity.refresh.evidence import load_candidate
        from trinity.publication.custody import custody
        service=PublicationService(self.database)
        with custody(self.root,self.row()):
            claim,_=service.claim(self.payload())
            evidence=load_candidate(self.report.root,self.digest,self.storage)
            original=service.transaction
            # Inject inside the real transaction after each final effect. The
            # database must roll all of them back, not only the failed statement.
            for needle in ('INSERT INTO publication_events','UPDATE active_publication',
                           'UPDATE refresh_steps SET status=', 'UPDATE refresh_runs SET status=',
                           'UPDATE data_versions SET revision=', 'UPDATE refresh_control SET holder_run_id='):
                class FailingConnection:
                    def __init__(self,connection):self.connection=connection
                    def execute(self,statement,parameters=()):
                        value=self.connection.execute(statement,parameters)
                        if needle in statement:raise RuntimeError('injected write failure')
                        return value
                @contextmanager
                def failing(*args,**kwargs):
                    with original(*args,**kwargs) as c:yield FailingConnection(c)
                with patch.object(service,'transaction',failing):
                    with self.assertRaises(RuntimeError):service.finish(claim,evidence)
                self.assertEqual(self.sql('SELECT count(*) AS n FROM publication_events')[0]['n'],0)
                self.assertEqual(self.row()['status'],'publishing')
                self.assertEqual(self.sql("SELECT status FROM refresh_steps WHERE stage='publish'")[0]['status'],'running')
                self.assertEqual(self.sql('SELECT holder_run_id FROM refresh_control')[0]['holder_run_id'],self.run)
            event=service.finish(claim,evidence)
            self.assertEqual(service.finish(claim,evidence)['id'],event['id'])
        # A lost response from a committed final transaction resolves by event.
        self.new_candidate()
        original_finish=PublicationService.finish
        def lost(instance,*args):
            original_finish(instance,*args)
            raise Problem(503,'dependency_unavailable')
        with patch.object(PublicationService,'finish',lost):
            resolved=self.worker.execute(self.payload())
        self.assertEqual(resolved['version_id'],self.version)

    def test_recorded_missing_mixed_and_approval_fail_closed(self):
        from trinity.publication.checks import recorded
        from trinity.adapters.postgres import Deadline
        from trinity.publication.service import locked
        # Corrupt only a rolled-back test transaction. Disable the relevant
        # freeze trigger inside it, then restore automatically by rollback.
        changes=(
            ("validation_results","DELETE FROM validation_results WHERE check_code='V01'",()),
            ("validation_results","DELETE FROM validation_results WHERE check_code='D01'",()),
            ("validation_results","UPDATE validation_results SET check_revision=2",()),
            ("validation_results","UPDATE validation_results SET status='fail',failed_count=1 WHERE required",()),
            ("dataset_artifacts","DELETE FROM dataset_artifacts",()),
            ("data_versions","UPDATE data_versions SET contract_version='unsupported'",()),
        )
        for table,statement,parameters in changes:
            trigger={'validation_results':'refresh_frozen_result','data_versions':'refresh_frozen_version','dataset_artifacts':'refresh_frozen_artifact'}[table]
            try:
                with self.database.transaction(Deadline()) as c:
                    c.execute(f'ALTER TABLE {table} DISABLE TRIGGER {trigger}')
                    c.execute(statement,parameters)
                    _,run,version,_=locked(c,self.run)
                    with self.assertRaises(Problem):recorded(c,run,version)
                    raise RuntimeError('rollback fixture corruption')
            except RuntimeError:pass
        self.assertIsNotNone(self.worker.execute(self.payload()))
        self.new_candidate(warnings=True);self.assertEqual(self.command('approve').status_code,202)
        self.sql('UPDATE approvals SET manifest_sha256=%s WHERE version_id=%s',('a'*64,self.version))
        self.worker.execute(self.payload())
        self.assertEqual(self.row()['status'],'publication_failed')
        self.assertEqual(self.command('publication-retry').status_code,409)

    def test_operator_invalid_unknown_host_access_and_database_outcomes(self):
        import os
        from psycopg.types.json import Jsonb
        code,value=self.operator('--expected-generation','0')
        self.assertEqual((code,value['outcome']),(2,'invalid_input'))
        code,value=self.operator('--inspect');self.assertEqual(code,0)
        args=('--expected-generation','0','--expected-fence',str(self.row()['execution_fence']))
        ref=self.row()['worker_execution_ref']
        self.sql('UPDATE refresh_runs SET worker_execution_ref=%s WHERE id=%s',(Jsonb(ref|{'host':'other-host'}),self.run))
        self.assertEqual(self.operator(*args)[1]['reason_code'],'wrong_host')
        self.sql('UPDATE refresh_runs SET worker_execution_ref=%s WHERE id=%s',(Jsonb(ref),self.run))
        os.chmod(self.root,0o755)
        try:self.assertEqual(self.operator(*args)[1]['reason_code'],'access_denied')
        finally:os.chmod(self.root,0o700)
        from trinity.publication.recovery import PublicationRecovery
        service=PublicationRecovery(self.database)
        with patch.object(service,'transaction',side_effect=Problem(503,'dependency_unavailable')):
            self.assertEqual(service.reconcile(self.run,self.root,inspect=True)['outcome'],'dependency_unavailable')

    def test_ordering_supersedes_older_and_rejects_narrower_coverage(self):
        from trinity.refresh.evidence import load_candidate
        from trinity.publication.custody import custody
        service=PublicationService(self.database)
        # Prepare A without publishing it, then release only fixture admission
        # to model delayed old work alongside a newer already published run.
        old_run,old_version,old_payload,old_storage=self.run,self.version,self.payload(),self.storage
        self.sql('UPDATE refresh_control SET holder_run_id=NULL')
        self.new_candidate();new_event=self.worker.execute(self.payload())
        self.sql('UPDATE refresh_control SET holder_run_id=%s',(old_run,))
        old=self.sql('SELECT * FROM refresh_runs WHERE id=%s',(old_run,))[0]
        with custody(self.root,old):
            service.execute(old_payload,self.root,old_storage)
        self.assertEqual(self.sql('SELECT status FROM refresh_runs WHERE id=%s',(old_run,))[0]['status'],'superseded')
        self.assertEqual(self.sql('SELECT publication_event_id FROM active_publication')[0]['publication_event_id'],new_event['id'])
        self.new_candidate()
        # An otherwise valid new candidate cannot shrink the active window.
        # Modify only the previous fixture coverage with its freeze trigger
        # disabled in a disposable transaction, not the candidate being checked.
        with self.database.transaction(Deadline()) as c:
            c.execute('ALTER TABLE data_versions DISABLE TRIGGER refresh_frozen_version')
            c.execute("UPDATE data_versions SET coverage_start=coverage_start-1 WHERE id=%s",(new_event['version_id'],))
            # Complete the existing deferred identity checks before changing
            # trigger configuration in this disposable corruption fixture.
            c.execute('SET CONSTRAINTS ALL IMMEDIATE')
            c.execute('ALTER TABLE data_versions ENABLE TRIGGER refresh_frozen_version')
        self.worker.execute(self.payload())
        self.assertEqual(self.row()['error_code'],'coverage_regression')
        self.assertEqual(self.command('publication-retry').status_code,409)
        self.assertEqual(self.sql('SELECT publication_event_id FROM active_publication')[0]['publication_event_id'],new_event['id'])

    def test_automatic_retry_rechecks_changed_bytes_and_retains_failure_history(self):
        original_get=self.storage.client.get_object;self.storage.sleep=lambda _:None
        self.storage.client.get_object=lambda **_:(_ for _ in ()).throw(EndpointConnectionError(endpoint_url='synthetic'))
        old=self.payload();self.worker.execute(old)
        self.assertEqual(self.command('publication-retry').status_code,202)
        self.storage.client.get_object=original_get
        key=f'versions/{self.version}/data/national.parquet'
        raw=self.storage.client.objects.pop(key)
        with patch('trinity.publication.service.load_candidate',wraps=load_candidate) as verifier:
            self.worker.execute(old);verifier.assert_not_called()
            self.worker.execute(self.payload());self.assertEqual(verifier.call_count,1)
        self.storage.client.objects[key]=raw
        self.assertEqual(self.row()['error_code'],'evidence_missing')
        self.assertEqual(self.command('publication-retry').status_code,409)
        warnings=self.sql('SELECT * FROM failure_warnings WHERE run_id=%s ORDER BY created_at',(self.run,))
        self.assertEqual(len(warnings),2);self.assertEqual(warnings[0]['resolution'],'publication_retry')
        self.assertIsNone(warnings[1]['resolved_at'])
        self.assertEqual(self.sql('SELECT count(*) AS n FROM approvals')[0]['n'],0)

    def test_command_rollback_and_current_session_checks(self):
        self.worker.execute(self.payload());self.new_candidate(warnings=True)
        self.sql("""CREATE FUNCTION publication_test_reject() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'test command rejection' USING ERRCODE='23514'; END $$;
            CREATE CONSTRAINT TRIGGER publication_test_reject AFTER INSERT ON api_commands
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION publication_test_reject()""")
        try:
            for action in ('approve','discard'):
                response=self.command(action);self.assertEqual(response.status_code,503,response.text)
                self.assertEqual(self.row()['status'],'awaiting_approval')
                self.assertEqual(self.sql('SELECT count(*) AS n FROM approvals')[0]['n'],0)
                self.assertEqual(self.sql('SELECT count(*) AS n FROM job_outbox WHERE run_id=%s',(self.run,))[0]['n'],0)
        finally:self.sql('DROP TRIGGER publication_test_reject ON api_commands; DROP FUNCTION publication_test_reject()')
        key=str(uuid4());self.assertEqual(self.command('approve',key=key).status_code,202)
        self.client.post('/api/v1/auth/logout',json={},headers=self.admin)
        self.assertEqual(self.command('approve',key=key).status_code,401)
        self.admin=self.login('admin')
        self.sql("UPDATE local_sessions SET created_at=now()-interval '1 hour',expires_at=now()-interval '1 second'")
        self.assertEqual(self.command('approve',key=key).status_code,401)

    def test_operator_exit_codes_and_failure_transaction_rollback(self):
        import subprocess
        import sys
        help_result=subprocess.run([sys.executable,'-m','trinity.workers','publication-recover','--help'],capture_output=True,text=True)
        self.assertEqual(help_result.returncode,0);self.assertIn('--expected-fence',help_result.stdout)
        self.assertEqual(self.operator('--inspect',overrides={'TRINITY_DATABASE_URL':'postgresql://invalid@127.0.0.1:1/missing'})[0],4)
        original=self.run;self.run=uuid4()
        self.assertEqual(self.operator('--inspect')[0],2);self.run=original
        before=self.row();args=('--expected-generation','0','--expected-fence',str(before['execution_fence']))
        self.sql("""CREATE FUNCTION publication_test_reject() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'test recovery rejection' USING ERRCODE='23514'; END $$;
            CREATE CONSTRAINT TRIGGER publication_test_reject AFTER INSERT ON failure_warnings
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION publication_test_reject()""")
        try:
            code,value=self.operator(*args)
            self.assertEqual((code,value['outcome']),(4,'outcome_unknown'))
            self.assertEqual(self.row(),before)
            self.assertEqual(self.sql('SELECT count(*) AS n FROM failure_warnings')[0]['n'],0)
        finally:self.sql('DROP TRIGGER publication_test_reject ON failure_warnings; DROP FUNCTION publication_test_reject()')
        self.assertEqual(self.operator(*args)[0],0)
        self.assertEqual(self.command('discard').status_code,200)
        self.assertEqual(self.operator(*args)[1]['outcome'],'not_applicable')

    def test_storage_configuration_failure_is_recorded_and_not_retryable(self):
        from trinity.config import ConfigurationError
        def invalid():raise ConfigurationError('synthetic configuration unavailable')
        self.worker.storage_factory=invalid
        self.worker.execute(self.payload())
        self.assertEqual(self.row()['error_code'],'storage_configuration')
        self.assertEqual(self.row()['status'],'publication_failed')
        self.assertEqual(self.command('publication-retry').status_code,409)

    def test_stale_owner_cannot_finish_fail_or_release_new_retry(self):
        from trinity.publication.custody import custody
        service=PublicationService(self.database)
        with custody(self.root,self.row()):
            old,_=service.claim(self.payload())
            evidence=load_candidate(self.report.root,self.digest,self.storage)
        self.expire();self.operator('--expected-generation','0','--expected-fence',str(self.row()['execution_fence']))
        self.assertEqual(self.command('publication-retry').status_code,202)
        with custody(self.root,self.row()):
            current,_=service.claim(self.payload());before=self.row()
            self.assertGreater(current[2]['deadline_at'],old[2]['deadline_at'])
            with self.assertRaises(Problem):service.fail(old,'storage_temporary')
            with self.assertRaises(Problem):service.finish(old,evidence)
            self.assertEqual(self.row(),before)
            self.assertEqual(self.sql('SELECT holder_run_id FROM refresh_control')[0]['holder_run_id'],self.run)
            self.assertEqual(service.finish(current,evidence)['version_id'],self.version)

    def test_automatic_storage_retry_succeeds_with_fresh_complete_verification(self):
        original=self.storage.client.get_object;self.storage.sleep=lambda _:None
        self.storage.client.get_object=lambda **_:(_ for _ in ()).throw(EndpointConnectionError(endpoint_url='synthetic'))
        self.worker.execute(self.payload())
        version_before=self.sql('SELECT * FROM data_versions WHERE id=%s',(self.version,))[0]
        self.assertEqual(self.command('publication-retry').status_code,202)
        self.storage.client.get_object=original
        with patch('trinity.publication.service.load_candidate',wraps=load_candidate) as verify:
            self.assertIsNotNone(self.worker.execute(self.payload()));self.assertEqual(verify.call_count,1)
        version_after=self.sql('SELECT * FROM data_versions WHERE id=%s',(self.version,))[0]
        self.assertEqual({k:v for k,v in version_before.items() if k!='revision'},
                         {k:v for k,v in version_after.items() if k!='revision'})
        self.assertEqual(self.sql('SELECT count(*) AS n FROM approvals')[0]['n'],0)
        self.assertEqual(self.sql("SELECT attempt FROM refresh_steps WHERE stage='publish' ORDER BY attempt"),
                         [{'attempt':1},{'attempt':2}])

    def test_permanent_failure_is_not_reclassified_when_deadline_crosses(self):
        from datetime import UTC, datetime, timedelta
        def failure(instance,claim,evidence):
            # Model an integrity/order check finishing at the deadline edge.
            # The known permanent cause must win over an elapsed-clock inference.
            claim[2]['deadline_at']=datetime.now(UTC)-timedelta(seconds=1)
            raise Problem(409,'coverage_regression')
        with patch.object(PublicationService,'finish',failure):self.worker.execute(self.payload())
        self.assertEqual(self.row()['error_code'],'coverage_regression')
        self.assertEqual(self.command('publication-retry').status_code,409)

    def test_operator_does_not_infer_stop_from_legacy_empty_ownership(self):
        # Empty legacy owner/lease fields alone are not a stopped-attempt record.
        self.sql("UPDATE refresh_runs SET status='publication_failed',worker_owner_id=NULL,lease_until=NULL WHERE id=%s",(self.run,))
        code,value=self.operator('--expected-generation','0','--expected-fence',str(self.row()['execution_fence']))
        self.assertEqual((code,value['outcome'],value['reason_code']),(3,'blocked','state_unknown'))
        self.assertEqual(self.sql("SELECT count(*) AS n FROM refresh_steps WHERE stage='publish'")[0]['n'],0)
