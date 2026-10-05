"""Exercise recovery SQL in the existing disposable PostgreSQL fixture.

These opt-in tests inject failure after each actual write and at commit. The
failure prerequisite has no spawned child: it exercises trusted database state,
not real process termination. Writer/queue races remain separate runtime cases.
"""
from contextlib import contextmanager
from copy import deepcopy
import unittest
from uuid import UUID, uuid4

from postgres_fixture import DSN, PostgresFixture
from trinity.errors import Problem
from trinity.refresh.execution import ExecutionService
from trinity.refresh.recovery import RecoveryService


class WriteFailureDatabase:
    """Inject one failure after SQL executes inside the real transaction."""

    def __init__(self, database, fail_after=None):
        self.database, self.fail_after = database, fail_after
        self.writes = 0

    @contextmanager
    def transaction(self, *args, **kwargs):
        """Force even the counting probe to roll back its otherwise valid work."""
        with self.database.transaction(*args, **kwargs) as connection:
            outer = self

            class Connection:
                def execute(self, sql, params=()):
                    """Fail after the selected write, so that write also needs rollback."""
                    result = connection.execute(sql, params)
                    if sql.lstrip().split()[0] in ('INSERT','UPDATE','DELETE'):
                        outer.writes += 1
                        if outer.writes == outer.fail_after:
                            raise Problem(503,'dependency_unavailable')
                    return result

            yield Connection()
            # The initial probe counts all writes without publishing fixture
            # changes. The normal Database context rolls the whole probe back.
            raise Problem(503,'dependency_unavailable')


@unittest.skipUnless(DSN, 'Use the disposable PostgreSQL runner with --refresh')
class RecoveryPostgresTests(PostgresFixture, unittest.TestCase):
    """Check actual constraints, linkage and all-or-nothing database effects."""

    def failure(self, *, candidate=True):
        """Produce terminal failure through the real fenced service, with no child.

        Only the dispatch-attempt precondition is seeded. This fixture launches
        no preparation process; recording its stop is therefore deterministic.
        It must not be presented as measured process-stop evidence.
        """
        self.setup_done()
        self.admin = self.login('admin')
        response = self.client.post('/api/v1/refresh-runs',json={},
                                   headers=self.admin | {'Idempotency-Key':str(uuid4())})
        self.assertEqual(response.status_code,202,response.text)
        self.run_id = UUID(response.json()['run_id'])
        self.sql('UPDATE job_outbox SET dispatch_attempts=1 WHERE run_id=%s',(self.run_id,))
        payload = self.sql('SELECT payload FROM job_outbox WHERE run_id=%s',(self.run_id,))[0]['payload']
        owner = uuid4()
        execution = ExecutionService(self.database)
        run = execution.claim(payload,owner)
        self.assertIsNotNone(run)
        self.fence = run['execution_fence']
        if candidate:
            execution.freeze(self.run_id,owner,self.fence,run['requested_start'],{})
        execution.reference(self.run_id,owner,self.fence,{'owner':str(owner),'child_stopped':True})
        execution.fail(self.run_id,owner,self.fence,'refresh_failed')
        detail = self.client.get(f'/api/v1/refresh-runs/{self.run_id}',headers=self.admin)
        self.assertEqual(detail.status_code,200,detail.text)
        self.etag = detail.headers['etag']
        self.key = str(uuid4())

    def recover(self, action='rerun', *, key=None, etag=None):
        """Call the real HTTP adapter with a fresh or replayed intent."""
        headers=self.admin | {'Idempotency-Key':key or self.key,'If-Match':etag or self.etag}
        if action=='rerun':
            return self.client.post(f'/api/v1/refresh-runs/{self.run_id}/rerun',json={},headers=headers)
        return self.client.delete(f'/api/v1/refresh-runs/{self.run_id}/warning',headers=headers)

    def snapshot(self):
        """Compare all recovery-owned records, including revisions and fences."""
        return {table:self.sql(f'SELECT * FROM {table} ORDER BY id') for table in (
            'refresh_runs','data_versions','failure_warnings','refresh_control',
            'job_outbox','api_commands','active_publication','shared_settings')}

    def test_rerun_preserves_old_snapshot_and_admits_current_revision(self):
        self.failure()
        old=deepcopy(self.sql('SELECT * FROM refresh_runs WHERE id=%s',(self.run_id,))[0])
        self.sql('UPDATE shared_settings SET revision=6')
        response=self.recover()
        self.assertEqual(response.status_code,202,response.text)
        new_id=UUID(response.json()['run_id'])
        self.assertNotEqual(new_id,self.run_id)
        new=self.sql('SELECT * FROM refresh_runs WHERE id=%s',(new_id,))[0]
        self.assertEqual((new['trigger_kind'],new['rerun_of_run_id'],new['settings_revision']),('rerun',self.run_id,6))
        self.assertEqual(new['policy_snapshot']['settings_revision'],6)
        retained=self.sql('SELECT * FROM refresh_runs WHERE id=%s',(self.run_id,))[0]
        self.assertEqual(retained['policy_snapshot'],old['policy_snapshot'])
        self.assertEqual(retained['finished_at'],old['finished_at'])
        self.assertEqual(retained['execution_fence'],old['execution_fence']+1)
        self.assertEqual(self.sql('SELECT holder_run_id FROM refresh_control')[0]['holder_run_id'],new_id)
        self.assertEqual(self.sql('SELECT disposition FROM data_versions')[0]['disposition'],'discarded')
        receipt=self.sql('SELECT * FROM api_commands WHERE idempotency_key=%s',(self.key,))[0]
        self.assertEqual((receipt['target_id'],receipt['run_id'],receipt['version_id']),(self.run_id,new_id,None))
        replay=self.recover(etag='"run-0"')
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json(),response.json() | {'replayed':True})
        self.assertEqual(len(self.sql('SELECT id FROM refresh_runs')),2)

    def test_delete_keeps_history_without_new_run_or_queue_obligation(self):
        self.failure(candidate=False)
        before=self.snapshot()
        response=self.recover('delete_warning')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['result'],'warning_resolved')
        after=self.snapshot()
        self.assertEqual(len(after['refresh_runs']),len(before['refresh_runs']))
        self.assertEqual(len(after['job_outbox']),len(before['job_outbox']))
        self.assertIsNone(after['refresh_control'][0]['holder_run_id'])
        self.assertEqual(after['failure_warnings'][0]['resolution'],'delete_warning')
        self.assertEqual(after['shared_settings'],before['shared_settings'])
        self.assertEqual(after['active_publication'],before['active_publication'])
        replay=self.recover('delete_warning',etag='"run-0"')
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json(),response.json() | {'replayed':True})

    def rollback_every_write(self, action):
        """Discover write count, then abort after every individual real statement."""
        self.failure()
        before=self.snapshot()
        token=self.admin['Authorization'][7:]
        args=(token,str(self.run_id),action,b'{}' if action=='rerun' else b'',
              [self.key],[self.etag])
        probe=WriteFailureDatabase(self.database)
        with self.assertRaises(Problem):
            RecoveryService(probe).command(*args)
        self.assertGreater(probe.writes,0)
        self.assertEqual(self.snapshot(),before)
        for position in range(1,probe.writes+1):
            with self.subTest(write=position):
                failing=WriteFailureDatabase(self.database,position)
                with self.assertRaises(Problem):
                    RecoveryService(failing).command(*args)
                self.assertEqual(failing.writes,position)
                self.assertEqual(self.snapshot(),before)

    def test_rerun_rollback_after_each_write(self):
        self.rollback_every_write('rerun')

    def test_warning_resolution_rollback_after_each_write(self):
        self.rollback_every_write('delete_warning')

    def test_deferred_receipt_failure_rolls_back_at_commit(self):
        self.failure()
        before=self.snapshot()
        self.sql("""CREATE FUNCTION reject_recovery_receipt() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'synthetic commit failure'; END $$""")
        self.sql("""CREATE CONSTRAINT TRIGGER reject_recovery_receipt AFTER INSERT ON api_commands
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION reject_recovery_receipt()""")
        try:
            response=self.recover()
            self.assertEqual(response.status_code,503,response.text)
            self.assertEqual(self.snapshot(),before)
        finally:
            self.sql('DROP TRIGGER reject_recovery_receipt ON api_commands')
            self.sql('DROP FUNCTION reject_recovery_receipt()')

    def test_stale_outbox_lease_is_invalidated_without_constraint_violation(self):
        self.failure()
        self.sql("""UPDATE job_outbox SET status='dispatching',lease_token=%s,
            lease_until=now()+interval '1 minute',delivered_at=NULL WHERE run_id=%s""",(uuid4(),self.run_id))
        old=self.sql('SELECT * FROM job_outbox WHERE run_id=%s',(self.run_id,))[0]
        response=self.recover('delete_warning')
        self.assertEqual(response.status_code,200,response.text)
        new=self.sql('SELECT * FROM job_outbox WHERE run_id=%s',(self.run_id,))[0]
        self.assertEqual((new['status'],new['lease_token'],new['lease_until']),('pending',None,None))
        self.assertEqual(new['dispatch_generation'],old['dispatch_generation']+1)
        self.assertEqual(new['dispatch_attempts'],old['dispatch_attempts'])
        from trinity.refresh.dispatch import DispatchService
        self.assertFalse(DispatchService(self.database,None).acknowledge(old,succeeded=True))
        self.assertIsNone(ExecutionService(self.database).claim(old['payload'],uuid4()))
