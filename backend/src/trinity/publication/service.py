"""Publish one registered candidate through a fenced, atomic state change.

The worker retains the original host lock for this entire operation. Claim one
attempt before reading storage. Verify outside SQL, then recheck frozen evidence,
authority and ordering in the final transaction. A duplicate returns its existing
event without moving the pointer. Unknown commits retain admission for recovery.
"""
from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from trinity.adapters.postgres import Deadline
from trinity.adapters.s3 import StorageError
from trinity.config import ConfigurationError
from trinity.errors import Problem
from trinity.publication.checks import recorded
from trinity.refresh.evidence import load_candidate, EvidenceError
from trinity.refresh.repository import lock_control


def locked(connection, run_id):
    """Acquire common lifecycle locks before any publication mutation."""
    control = lock_control(connection)
    run = connection.execute('SELECT * FROM refresh_runs WHERE id=%s FOR UPDATE', (run_id,)).fetchone()
    if not run:
        raise Problem(404, 'resource_not_found')
    version = connection.execute('SELECT * FROM data_versions WHERE run_id=%s FOR UPDATE', (run_id,)).fetchone()
    active = connection.execute('SELECT * FROM active_publication WHERE id=1 FOR UPDATE').fetchone()
    if not active:
        raise Problem(503, 'dependency_unavailable')
    return control, run, version, active


def event_for(connection, version):
    """Resolve committed success before testing obsolete execution ownership."""
    return connection.execute('SELECT * FROM publication_events WHERE version_id=%s',
                              (version['id'],)).fetchone() if version else None


def fail_stopped(connection, run, version, code):
    """Retain evidence and admission after verified stop; caller owns the lock.

    This differs from a terminal Refresh failure: publication_failed has no run
    finish time. Clearing the owner is durable proof that no writer remains.
    """
    step = connection.execute("""SELECT * FROM refresh_steps WHERE run_id=%s AND stage='publish'
        AND work_key='publication' AND attempt=%s FOR UPDATE""",
        (run['id'],run['publication_generation']+1)).fetchone()
    if step is None:
        connection.execute("""INSERT INTO refresh_steps(id,run_id,step_seq,stage,work_key,attempt,
            status,execution_fence,started_at,finished_at,progress_unit,error_code,error_summary)
            VALUES(%s,%s,(SELECT COALESCE(max(step_seq),0)+1 FROM refresh_steps WHERE run_id=%s),
            'publish','publication',%s,'failed',%s,clock_timestamp(),clock_timestamp(),'tasks',%s,
            'Publication could not complete.')""",
            (uuid4(),run['id'],run['id'],run['publication_generation']+1,run['execution_fence'],code))
    else:
        # A prior permanent error must survive operator reconciliation.
        code = step['error_code'] or code
        connection.execute("""UPDATE refresh_steps SET status='failed',finished_at=clock_timestamp(),
            error_code=%s,error_summary='Publication could not complete.' WHERE id=%s""",(code,step['id']))
    connection.execute("""INSERT INTO failure_warnings(id,run_id,version_id,stage,code,message,created_at)
        VALUES(%s,%s,%s,'publish',%s,'Publication could not complete.',clock_timestamp())""",
        (uuid4(),run['id'],version['id'],code))
    connection.execute("""UPDATE refresh_runs SET status='publication_failed',finished_at=NULL,
        worker_owner_id=NULL,lease_until=NULL,execution_fence=execution_fence+1,revision=revision+1,
        error_code=%s,error_summary='Publication could not complete.' WHERE id=%s""",(code,run['id']))
    connection.execute('UPDATE data_versions SET revision=revision+1 WHERE id=%s',(version['id'],))


class PublicationService:
    """Own short transactions; never repeat verification or final commit."""
    def __init__(self, database):
        self.database = database

    def transaction(self, seconds=15, *, readonly=False):
        """Apply a bounded database wait within the caller's remaining budget."""
        return self.database.transaction(Deadline(seconds), readonly=readonly, error_code='dependency_unavailable')

    def lookup(self, run_id):
        """Read retained custody without deriving paths from queue data."""
        with self.transaction(readonly=True) as c:
            return c.execute('SELECT * FROM refresh_runs WHERE id=%s',(run_id,)).fetchone()

    def claim(self, payload):
        """Commit the unique generation marker before invoking verification."""
        with self.transaction() as c:
            control,run,version,active = locked(c,UUID(payload['run_id']))
            if not version or str(version['id']) != payload['version_id']:
                return None,None
            event = event_for(c,version)
            if event:
                return None, event
            outbox = c.execute("SELECT * FROM job_outbox WHERE run_id=%s AND job_kind='publish_version' FOR UPDATE",
                               (run['id'],)).fetchone()
            if (not version or control['holder_run_id'] != run['id'] or run['status'] != 'publishing'
                    or str(version['id']) != payload['version_id']
                    or run['publication_generation'] != payload['publication_generation']
                    or not outbox or outbox['payload'] != payload
                    or outbox['dispatch_generation'] != payload['dispatch_generation']):
                return None,None
            existing = c.execute("SELECT id FROM refresh_steps WHERE run_id=%s AND stage='publish' AND attempt=%s",
                                 (run['id'],run['publication_generation']+1)).fetchone()
            if existing:
                return None,None
            owner = uuid4()
            run = c.execute("""UPDATE refresh_runs SET worker_owner_id=%s,execution_fence=execution_fence+1,
                lease_until=clock_timestamp()+interval '300 seconds',revision=revision+1
                WHERE id=%s RETURNING *""",(owner,run['id'])).fetchone()
            step = c.execute("""INSERT INTO refresh_steps(id,run_id,step_seq,stage,work_key,attempt,status,
                execution_fence,started_at,deadline_at,progress_unit)
                VALUES(%s,%s,(SELECT COALESCE(max(step_seq),0)+1 FROM refresh_steps WHERE run_id=%s),
                'publish','publication',%s,'running',%s,clock_timestamp(),%s,'tasks') RETURNING *""",
                (uuid4(),run['id'],run['id'],run['publication_generation']+1,run['execution_fence'],run['lease_until'])).fetchone()
            c.execute('UPDATE data_versions SET revision=revision+1 WHERE id=%s',(version['id'],))
            return (run,version,step),None

    def fail(self, claim, code):
        """Record a stopped failure only for the same still-current owner."""
        original,_,_ = claim
        with self.transaction() as c:
            control,run,version,_ = locked(c,original['id'])
            event = event_for(c,version)
            if event:
                return event
            if (control['holder_run_id'] != run['id'] or run['status'] != 'publishing'
                    or run['worker_owner_id'] != original['worker_owner_id']
                    or run['execution_fence'] != original['execution_fence']
                    or run['publication_generation'] != original['publication_generation']):
                raise Problem(409,'candidate_ineligible')
            fail_stopped(c,run,version,code)

    def finish(self, claim, evidence):
        """Commit all publication effects together, or leave every effect absent."""
        original,original_version,original_step = claim
        # An old successful attempt remains idempotent after its deadline and
        # after a newer version becomes active. It requires no new work budget.
        with self.transaction(readonly=True) as c:
            existing = event_for(c,original_version)
        if existing:
            return existing
        remaining = (original_step['deadline_at']-datetime.now(UTC)).total_seconds()
        with self.transaction(max(.001,remaining)) as c:
            control,run,version,active = locked(c,original['id'])
            event = event_for(c,version)
            if event:
                return event
            step = c.execute('SELECT *,deadline_at>clock_timestamp() AS live FROM refresh_steps WHERE id=%s FOR UPDATE',
                             (original_step['id'],)).fetchone()
            if (control['holder_run_id'] != run['id'] or run['status'] != 'publishing'
                    or run['worker_owner_id'] != original['worker_owner_id']
                    or run['execution_fence'] != original['execution_fence']
                    or run['publication_generation'] != original['publication_generation']
                    or not step or step['status'] != 'running'
                    or step['execution_fence'] != run['execution_fence']
                    or step['attempt'] != run['publication_generation']+1
                    or run['lease_until'] is None):
                raise Problem(409,'candidate_ineligible')
            if not step['live'] or run['lease_until'] <= datetime.now(UTC):
                raise Problem(409,'publication_deadline')
            approval = recorded(c,run,version,evidence=evidence)
            previous = c.execute("""SELECT r.run_seq,v.coverage_start,v.coverage_end FROM publication_events p
                JOIN data_versions v ON v.id=p.version_id JOIN refresh_runs r ON r.id=v.run_id WHERE p.id=%s""",
                (active['publication_event_id'],)).fetchone()
            if previous and run['run_seq'] <= previous['run_seq']:
                c.execute("UPDATE data_versions SET disposition='superseded',revision=revision+1 WHERE id=%s",(version['id'],))
                c.execute("""UPDATE refresh_runs SET status='superseded',finished_at=clock_timestamp(),
                    worker_owner_id=NULL,lease_until=NULL,execution_fence=execution_fence+1,revision=revision+1 WHERE id=%s""",(run['id'],))
                c.execute("UPDATE refresh_steps SET status='abandoned',finished_at=clock_timestamp() WHERE id=%s",(step['id'],))
                c.execute('UPDATE refresh_control SET holder_run_id=NULL,revision=revision+1 WHERE id=1')
                return None
            if previous and (version['coverage_start'] > previous['coverage_start'] or version['coverage_end'] < previous['coverage_end']):
                raise Problem(409,'coverage_regression')
            identity = uuid5(NAMESPACE_URL,f"urn:trinity:publish:{version['id']}")
            event = c.execute("""INSERT INTO publication_events(id,version_id,previous_publication_event_id,
                approval_id,published_at,publication_mode,actor_id,idempotency_key)
                VALUES(%s,%s,%s,%s,clock_timestamp(),%s,%s,%s) RETURNING *""",
                (identity,version['id'],active['publication_event_id'],approval['id'] if approval else None,
                 'approval' if approval else 'automatic',approval['approved_by'] if approval else None,identity)).fetchone()
            c.execute('UPDATE active_publication SET publication_event_id=%s,revision=revision+1 WHERE id=1',(identity,))
            c.execute("UPDATE refresh_steps SET status='succeeded',finished_at=clock_timestamp(),processed_count=1,total_count=1 WHERE id=%s",(step['id'],))
            c.execute("""UPDATE refresh_runs SET status='succeeded',finished_at=clock_timestamp(),
                worker_owner_id=NULL,lease_until=NULL,revision=revision+1 WHERE id=%s""",(run['id'],))
            c.execute('UPDATE data_versions SET revision=revision+1 WHERE id=%s',(version['id'],))
            c.execute('UPDATE refresh_control SET holder_run_id=NULL,revision=revision+1 WHERE id=1')
            return event

    def execute(self, payload, root, storage=None, *, storage_factory=None):
        """Run once while the caller holds the original lifetime lock.

        A database exception may represent a lost commit response. Look for the
        unique event; otherwise leave interrupted state for explicit recovery.
        Never convert an uncertain transaction to an optimistic retryable error.
        """
        claim,event = self.claim(payload)
        if not claim:
            return event
        run,version,step = claim
        try:
            remaining = (step['deadline_at']-datetime.now(UTC)).total_seconds()
            if remaining <= 0:
                return self.fail(claim,'publication_deadline')
            # Initialize storage only after the claim commits. Configuration
            # failure is a stopped, nonretryable outcome, not a lost worker.
            if storage_factory is not None:
                storage = storage_factory()
            evidence = load_candidate(root/str(version['id']),version['preparation_receipt_sha256'],
                                      storage,timeout_seconds=min(300,remaining))
        except EvidenceError as error:
            return self.fail(claim,error.cause)
        except (StorageError, ConfigurationError):
            return self.fail(claim,'storage_configuration')
        except Exception:
            return self.fail(claim,'unknown_failure')
        try:
            return self.finish(claim,evidence)
        except Problem as error:
            if error.status == 409:
                # Never replace a confirmed permanent violation just because
                # the clock crossed the deadline while reporting that error.
                code = error.code if error.code in ('coverage_regression','publication_deadline') else 'evidence_invalid'
                return self.fail(claim,code)
            with self.transaction(readonly=True) as c:
                event = event_for(c,version)
            if event:
                return event
            raise
