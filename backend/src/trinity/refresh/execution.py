"""Own the durable refresh fence, fixed window, stage budgets and failure state.

A queue notification can claim a requested run once. Every later write checks
that run's owner, fence, lease and original deadline. Local stage journals retain
operation details before the child receives permission to proceed. Database
counters survive restart; neither Redis redelivery nor recovery starts extraction
again. Successful preparation retains a receipt for the candidate-routing gate.
"""
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from trinity.adapters.postgres import Deadline
from trinity.adapters.queue import refresh_payload
from trinity.errors import Problem
from trinity.refresh.dispatch import fail_run
from trinity.refresh.repository import lock_control


STAGE_MAP = {
    'discovery': ('extract', 'discover_latest', 'tasks', 60),
    'extract:national': ('extract', 'national', 'rows', 300),
    'extract:facility': ('extract', 'facility', 'rows', 300),
    'extract:generator': ('extract', 'generator', 'rows', 300),
    'freeze': ('prepare', 'files', 'files', 120),
    'validation': ('validate', 'candidate', 'checks', 120),
    'storage': ('prepare', 'storage', 'files', 300),
}


class ExecutionService:
    """Perform short fenced transactions; no external calls occur inside SQL."""
    def __init__(self, database):
        self.database = database

    def transaction(self):
        """Bound connection and statement time for each durable transition."""
        return self.database.transaction(Deadline(), error_code='dependency_unavailable')

    def claim(self, payload, owner):
        """Return a first execution claim; duplicate or repaired-old jobs do nothing."""
        payload = refresh_payload(payload)
        run_id = UUID(payload['run_id'])
        with self.transaction() as connection:
            control = lock_control(connection)
            run = connection.execute('SELECT * FROM refresh_runs WHERE id=%s FOR UPDATE', (run_id,)).fetchone()
            outbox = connection.execute("SELECT * FROM job_outbox WHERE run_id=%s AND job_kind='refresh_pipeline' FOR UPDATE",
                                        (run_id,)).fetchone()
            if (not run or not outbox or control['holder_run_id'] != run_id
                    or run['status'] != 'requested' or run['started_at'] is not None
                    or payload != outbox['payload'] or outbox['dispatch_attempts'] < 1
                    or connection.execute('SELECT id FROM data_versions WHERE run_id=%s', (run_id,)).fetchone()):
                return None
            # A valid queue identity cannot make an unsupported stored policy
            # executable. Admission freezes these values for this implementation.
            expected = {'workflow_policy':'warnings-v1','diagnostic_registry':'warnings-v1',
                        'contract_version':'trinity-data-v1','validation_checkset':'trinity-data-v1',
                        'end_strategy':'latest_national','settings_revision':run['settings_revision'],
                        'requested_start':run['requested_start'].isoformat()}
            if any(run['policy_snapshot'].get(key) != value for key,value in expected.items()):
                fail_run(connection,run_id,'refresh_failed',stage='extract')
                return None
            return connection.execute("""UPDATE refresh_runs SET status='running',
                started_at=clock_timestamp(),execution_fence=execution_fence+1,revision=revision+1,
                worker_owner_id=%s,lease_until=clock_timestamp()+interval '30 seconds',
                execution_deadline_at=clock_timestamp()+interval '1530 seconds'
                WHERE id=%s RETURNING *""", (owner,run_id)).fetchone()

    def owned(self, connection, run_id, owner, fence, *, stopped=False):
        """Require current authority; confirmed-stop failure may outlive its lease."""
        control = lock_control(connection)
        run = connection.execute("""SELECT *,lease_until>clock_timestamp() AS live,
            execution_deadline_at>clock_timestamp() AS in_time
            FROM refresh_runs WHERE id=%s FOR UPDATE""", (run_id,)).fetchone()
        if (not run or control['holder_run_id'] != run_id or run['status'] != 'running'
                or run['execution_fence'] != fence or run['worker_owner_id'] != owner
                or (not stopped and (not run['live'] or not run['in_time']))):
            raise Problem(409, 'candidate_ineligible')
        version = connection.execute('SELECT status,disposition FROM data_versions WHERE run_id=%s FOR UPDATE',
                                     (run_id,)).fetchone()
        if version and (version['disposition'] != 'active' or version['status'] not in ('preparing','validating')):
            raise Problem(409, 'candidate_ineligible')
        return run

    def heartbeat(self, run_id, owner, fence):
        """Renew only a live lease; an expired owner cannot revive itself."""
        with self.transaction() as connection:
            self.owned(connection,run_id,owner,fence)
            connection.execute("UPDATE refresh_runs SET lease_until=clock_timestamp()+interval '30 seconds' WHERE id=%s", (run_id,))
            connection.execute("UPDATE refresh_steps SET heartbeat_at=clock_timestamp() WHERE run_id=%s AND status='running'", (run_id,))

    def reference(self, run_id, owner, fence, changes, *, stopped=False):
        """Retain trusted process/receipt custody without accepting a queue path."""
        with self.transaction() as connection:
            run = self.owned(connection,run_id,owner,fence,stopped=stopped)
            ref = {**(run['worker_execution_ref'] or {}), **changes}
            connection.execute('UPDATE refresh_runs SET worker_execution_ref=%s WHERE id=%s', (Jsonb(ref),run_id))
            return ref

    def freeze(self, run_id, owner, fence, end, discovery):
        """Freeze the measured window and reserve one immutable version together."""
        if type(end) is not date:
            raise ValueError('invalid_discovery')
        with self.transaction() as connection:
            run = self.owned(connection,run_id,owner,fence)
            if not run['requested_start'] <= end <= datetime.now(UTC).date():
                raise ValueError('invalid_discovery')
            version = connection.execute('SELECT * FROM data_versions WHERE run_id=%s', (run_id,)).fetchone()
            if run['requested_end'] is not None:
                # Recovery must reuse the committed end, never silently revise it.
                if run['requested_end'] != end or version is None:
                    raise Problem(409, 'candidate_ineligible')
                return version
            connection.execute("""UPDATE refresh_runs SET requested_end=%s,window_frozen_at=clock_timestamp(),
                revision=revision+1,worker_execution_ref=COALESCE(worker_execution_ref,'{}'::jsonb)||%s
                WHERE id=%s""", (end,Jsonb({'discovery': discovery}),run_id))
            return connection.execute("""INSERT INTO data_versions(id,run_id,status,disposition,created_at,
                coverage_start,coverage_end,latest_observation_date,contract_version,validation_checkset)
                VALUES(%s,%s,'preparing','active',clock_timestamp(),%s,%s,%s,'trinity-data-v1','trinity-data-v1') RETURNING *""",
                (uuid4(),run_id,run['requested_start'],end,end)).fetchone()

    def event(self, run_id, owner, fence, event):
        """Commit stage or attempt custody before the supervisor acknowledges it."""
        kind = event['event']
        if kind not in ('started','finished','attempt','validation_attempt','child_verified','progress'):
            raise ValueError('invalid_worker_event')
        # The supervisor's initial journal event is not an extraction stage.
        if kind == 'started' and 'stage' not in event:
            return
        with self.transaction() as connection:
            run = self.owned(connection,run_id,owner,fence)
            ref = run['worker_execution_ref'] or {}
            active = connection.execute("SELECT * FROM refresh_steps WHERE run_id=%s AND status='running' FOR UPDATE", (run_id,)).fetchone()
            if kind == 'started':
                if active:
                    raise ValueError('stage_already_active')
                stage,key,unit,seconds = STAGE_MAP[event['stage']]
                step = connection.execute("""INSERT INTO refresh_steps(id,run_id,step_seq,stage,work_key,attempt,
                    status,execution_fence,started_at,heartbeat_at,deadline_at,progress_unit)
                    VALUES(%s,%s,(SELECT COALESCE(max(step_seq),0)+1 FROM refresh_steps WHERE run_id=%s),
                    %s,%s,1,'running',%s,clock_timestamp(),clock_timestamp(),
                    LEAST(%s,clock_timestamp()+%s*interval '1 second'),%s) RETURNING *""",
                    (uuid4(),run_id,run_id,stage,key,fence,run['execution_deadline_at'],seconds,unit)).fetchone()
                ref['stage'] = event['stage']
                ref['step_id'] = str(step['id'])
            elif kind in ('finished','attempt','validation_attempt','progress'):
                if not active or active['deadline_at'] <= datetime.now(UTC):
                    raise Problem(409, 'candidate_ineligible')
                if kind == 'finished':
                    if ref.get('stage') != event['stage']:
                        raise ValueError('wrong_stage')
                    status = 'succeeded' if event['status'] in ('success','passed') else 'failed'
                    connection.execute("UPDATE refresh_steps SET status=%s,finished_at=clock_timestamp() WHERE id=%s", (status,active['id']))
                elif kind == 'progress':
                    count, total = event['processed_count'], event['total_count']
                    if (type(count) is not int or count < active['processed_count']
                            or (total is not None and (type(total) is not int or total < count))):
                        raise ValueError('invalid_progress')
                    connection.execute('UPDATE refresh_steps SET processed_count=%s,total_count=%s WHERE id=%s',
                                       (count,total,active['id']))
                elif kind == 'attempt':
                    if type(event.get('attempt')) is not int or not 1 <= event['attempt'] <= 3:
                        raise ValueError('invalid_attempt')
                    ref['operation_count'] = ref.get('operation_count',0)+1
                    ref['last_operation'] = event
                else:
                    if active['stage'] != 'validate' or active['validation_attempt_id'] is not None:
                        raise ValueError('wrong_validation_attempt')
                    attempt = UUID(event['attempt_id'])
                    connection.execute('UPDATE refresh_steps SET validation_attempt_id=%s WHERE id=%s', (attempt,active['id']))
                    connection.execute("""UPDATE data_versions SET status='validating',manifest_sha256=%s,
                        manifest_frozen_at=clock_timestamp(),revision=revision+1 WHERE run_id=%s""", (event['manifest_sha256'],run_id))
                    ref['validation_step_id'] = str(active['id'])
                    ref['validation_attempt_id'] = str(attempt)
            elif kind == 'child_verified':
                ref['receipt_sha256'] = event['receipt_sha256']
            connection.execute('UPDATE refresh_runs SET revision=revision+1,worker_execution_ref=%s WHERE id=%s', (Jsonb(ref),run_id))

    def fail(self, run_id, owner, fence, code, *, results=()):
        """Import measured rows after confirmed stop; never infer readiness."""
        from trinity.contracts.manifest import read_json, sha256
        with self.transaction() as connection:
            run = self.owned(connection,run_id,owner,fence,stopped=True)
            ref = run['worker_execution_ref'] or {}
            if ref.get('child_stopped') is not True:
                raise Problem(409, 'candidate_ineligible')
            version = connection.execute('SELECT * FROM data_versions WHERE run_id=%s FOR UPDATE', (run_id,)).fetchone()
            step_id = ref.get('validation_step_id')
            for result in results:
                if (version is None or str(version['id']) != result.version_id
                        or result.attempt_id != ref.get('validation_attempt_id')
                        or version['manifest_sha256'] != result.manifest_sha256):
                    raise ValueError('wrong_failure_evidence')
                connection.execute("""INSERT INTO validation_results(id,version_id,step_id,manifest_sha256,
                    checkset_version,check_code,check_revision,dataset_key,required,severity,status,
                    checked_count,failed_count,details,details_path,details_sha256,checked_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (uuid4(),version['id'],step_id,result.manifest_sha256,result.checkset_version,
                     result.check_code,result.check_revision,result.dataset_key,result.required,result.severity,
                     result.status,result.checked_count,result.failed_count,Jsonb(read_json(result.details_json)),
                     result.details_path,sha256(result.details_json),result.checked_at))
            connection.execute("""UPDATE refresh_steps SET status='abandoned',finished_at=clock_timestamp(),
                error_code=%s,error_summary='Refresh stopped before stage completion.'
                WHERE run_id=%s AND status='running'""", (code,run_id))
            if step_id and results:
                connection.execute('UPDATE refresh_steps SET processed_count=%s,total_count=39 WHERE id=%s',
                                   (len(results),step_id))
            if version:
                connection.execute("UPDATE data_versions SET status='rejected',revision=revision+1 WHERE id=%s", (version['id'],))
            fail_run(connection,run_id,code,stage=STAGE_MAP.get(ref.get('stage'),STAGE_MAP['discovery'])[0])
