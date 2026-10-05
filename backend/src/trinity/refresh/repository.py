"""Read lifecycle state and persist admission or recovery in the caller's transaction.

Services hold the shared admission and authority locks before mutation helpers.
These helpers never commit, fetch source/storage data or send queue messages.
Run, warning, candidate, outbox and receipt effects remain one database unit.
"""
from trinity.errors import Problem


def lock_control(connection):
    """Serialize every admission on the existing shared lifecycle row."""
    row = connection.execute('SELECT * FROM refresh_control WHERE id=1 FOR UPDATE').fetchone()
    if row is None:
        raise Problem(503,'dependency_unavailable')
    return row


def read_command(connection, key):
    """Read a receipt only after the service authorizes the current actor."""
    return connection.execute('SELECT * FROM api_commands WHERE idempotency_key=%s',(key,)).fetchone()


# All admission paths freeze one policy together with the locked settings
# revision. The failed run's snapshot is never reused for a new full refresh.
POLICY = {'workflow_policy':'warnings-v1','diagnostic_registry':'warnings-v1',
          'contract_version':'trinity-data-v1','validation_checkset':'trinity-data-v1',
          'requested_start':'2024-10-02','end_strategy':'latest_national'}


def _insert_run(connection, trigger_kind, actor_id, request_key, settings, *, rerun_of_run_id=None):
    """Insert a run, transfer admission and retain one queue obligation.

    The caller holds admission and a shared settings lock in its transaction.
    A rerun links its predecessor but takes a fresh policy/settings snapshot.
    No commit or queue request occurs here. Any later receipt failure must
    roll back these writes and the caller's preceding abandonment writes.
    """
    from datetime import date
    from uuid import uuid4
    from psycopg.types.json import Jsonb
    run_id = uuid4()
    policy = {'settings_revision':settings['revision'], **POLICY}
    run = connection.execute("""INSERT INTO refresh_runs(id,trigger_kind,requested_by,request_key,
        requested_at,status,settings_revision,policy_snapshot,requested_start,rerun_of_run_id)
        VALUES(%s,%s,%s,%s,clock_timestamp(),'requested',%s,%s,%s,%s) RETURNING *""",
        (run_id,trigger_kind,actor_id,request_key,settings['revision'],Jsonb(policy),
         date.fromisoformat(POLICY['requested_start']),rerun_of_run_id)).fetchone()
    connection.execute('UPDATE refresh_control SET holder_run_id=%s,revision=revision+1 WHERE id=1',(run_id,))
    connection.execute("""INSERT INTO job_outbox(id,run_id,job_kind,deduplication_key,payload)
        VALUES(%s,%s,'refresh_pipeline',%s,%s)""",
        (uuid4(),run_id,f'refresh:{run_id}',Jsonb({'schema_version':1,'run_id':str(run_id),
         'version_id':None,'job_kind':'refresh_pipeline','dispatch_generation':0})))
    return run


def accept_run(connection, actor_id, key, fingerprint, settings, *, rerun_of_run_id=None):
    """Accept manual or rerun intent and store its original tracking receipt.

    Manual callers keep their existing identity. A rerun receipt targets the
    old run, while its tracking URL and run_id identify the new run. The new
    version_id is null because preparation has not produced a candidate yet.
    """
    from uuid import uuid4
    action = 'rerun' if rerun_of_run_id is not None else 'start_refresh'
    run = _insert_run(connection, 'rerun' if rerun_of_run_id is not None else 'manual',
                      actor_id, key, settings, rerun_of_run_id=rerun_of_run_id)
    return connection.execute("""INSERT INTO api_commands(id,idempotency_key,actor_id,action,target_id,
        request_fingerprint,accepted_at,run_id,result,status_url)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'queued',%s) RETURNING *""",
        (uuid4(),key,actor_id,action,rerun_of_run_id,fingerprint,run['requested_at'],run['id'],
         f'/api/v1/refresh-runs/{run["id"]}')).fetchone()


def lock_recovery_target(connection, run_id):
    """Load recovery rows after admission, authority and settings locks.

    Keep the same run → candidate → active pointer order as publication. The
    pointer lock and common admission lock exclude a concurrent publication.
    Lock warning, steps and outbox rows before testing stop evidence or writing.
    """
    run = connection.execute('SELECT * FROM refresh_runs WHERE id=%s FOR UPDATE',(run_id,)).fetchone()
    if run is None:
        raise Problem(404, 'resource_not_found')
    version = connection.execute('SELECT * FROM data_versions WHERE run_id=%s FOR UPDATE',(run_id,)).fetchone()
    active = connection.execute('SELECT * FROM active_publication WHERE id=1 FOR UPDATE').fetchone()
    if active is None:
        raise Problem(503, 'dependency_unavailable')
    warning = connection.execute("""SELECT * FROM failure_warnings
        WHERE run_id=%s AND resolved_at IS NULL FOR UPDATE""",(run_id,)).fetchone()
    connection.execute('SELECT id FROM refresh_steps WHERE run_id=%s ORDER BY id FOR UPDATE',(run_id,)).fetchall()
    connection.execute('SELECT id FROM job_outbox WHERE run_id=%s ORDER BY id FOR UPDATE',(run_id,)).fetchall()
    return run, version, warning


def abandon_failed(connection, actor_id, action, run, version, warning):
    """Resolve safely stopped work without deleting its retained evidence.

    Call only after locked eligibility succeeds. Fence old execution and queue
    acknowledgements before releasing this run's slot. A later admission or
    receipt failure rolls back this entire operation in the service transaction.
    """
    resolved = connection.execute("""UPDATE failure_warnings SET resolved_at=clock_timestamp(),
        resolution=%s,resolved_by=%s WHERE id=%s AND resolved_at IS NULL RETURNING id""",
        (action,actor_id,warning['id'])).fetchone()
    if resolved is None:
        raise Problem(409, 'action_not_allowed')
    if version:
        connection.execute("""UPDATE data_versions SET disposition='discarded',
            discarded_at=clock_timestamp(),discarded_by=%s,revision=revision+1 WHERE id=%s""",
            (actor_id,version['id']))
    # Keep a terminal failure's original time. Publication failure becomes a
    # terminal failed run here; its earlier failed attempt remains untouched.
    connection.execute("""UPDATE refresh_runs SET status='failed',
        finished_at=COALESCE(finished_at,clock_timestamp()),execution_fence=execution_fence+1,
        worker_owner_id=NULL,lease_until=NULL,revision=revision+1 WHERE id=%s""",(run['id'],))
    # A dispatching row cannot have empty lease fields under the current DDL.
    # Move it to pending while invalidating its generation. Claimers skip this
    # terminal run; an already sent old notification also fails worker checks.
    connection.execute("""UPDATE job_outbox SET dispatch_generation=dispatch_generation+1,
        payload=jsonb_set(payload,'{dispatch_generation}',to_jsonb(dispatch_generation+1)),
        status=CASE WHEN status='dispatching' THEN 'pending' ELSE status END,
        lease_token=NULL,lease_until=NULL WHERE run_id=%s""",(run['id'],))
    released = connection.execute("""UPDATE refresh_control SET holder_run_id=NULL,revision=revision+1
        WHERE id=1 AND holder_run_id=%s RETURNING id""",(run['id'],)).fetchone()
    if released is None:
        raise Problem(409, 'action_not_allowed')


def record_warning_resolution(connection, actor_id, command, fingerprint, version):
    """Retain deletion acceptance with the original run's tracking reference."""
    from uuid import uuid4
    return connection.execute("""INSERT INTO api_commands(id,idempotency_key,actor_id,action,target_id,
        request_fingerprint,accepted_at,run_id,version_id,result,status_url)
        VALUES(%s,%s,%s,'delete_warning',%s,%s,clock_timestamp(),%s,%s,'warning_resolved',%s)
        RETURNING *""", (uuid4(),command.key,actor_id,command.run_id,fingerprint,command.run_id,
                          version['id'] if version else None,
                          f'/api/v1/refresh-runs/{command.run_id}')).fetchone()


def run_history(connection, maximum, after, limit):
    """Read one descending page within the first page's greatest sequence."""
    if maximum is None:
        maximum = connection.execute('SELECT COALESCE(max(run_seq),0) AS n FROM refresh_runs').fetchone()['n']
    rows = connection.execute("""SELECT id,run_seq,status,requested_at,finished_at FROM refresh_runs
        WHERE run_seq<=%s AND (%s::bigint IS NULL OR run_seq<%s)
        ORDER BY run_seq DESC LIMIT %s""",(maximum,after,after,limit+1)).fetchall()
    return rows,maximum


def run_steps(connection, run_id, maximum, after, limit):
    """Read retained attempts ascending, without allowing later attempts to shift a page."""
    if maximum is None:
        maximum = connection.execute('SELECT COALESCE(max(step_seq),0) AS n FROM refresh_steps WHERE run_id=%s',
                                     (run_id,)).fetchone()['n']
    rows = connection.execute("""SELECT * FROM refresh_steps WHERE run_id=%s
        AND step_seq<=%s AND (%s::bigint IS NULL OR step_seq>%s) ORDER BY step_seq LIMIT %s""",
        (run_id,maximum,after,after,limit+1)).fetchall()
    return rows,maximum


def run_detail(connection, run_id):
    """Read one run and its safe-projection inputs in the caller's snapshot."""
    run = connection.execute('SELECT * FROM refresh_runs WHERE id=%s',(run_id,)).fetchone()
    if run is None:
        raise Problem(404,'resource_not_found')
    version = connection.execute('SELECT * FROM data_versions WHERE run_id=%s',(run_id,)).fetchone()
    warning = connection.execute("""SELECT * FROM failure_warnings WHERE run_id=%s
        ORDER BY (resolved_at IS NULL) DESC,created_at DESC,id DESC LIMIT 1""",(run_id,)).fetchone()
    approval = publish_step = event = None
    if version:
        approval = connection.execute('SELECT * FROM approvals WHERE version_id=%s',(version['id'],)).fetchone()
        event = connection.execute('SELECT id FROM publication_events WHERE version_id=%s',(version['id'],)).fetchone()
        publish_step = connection.execute("""SELECT status FROM refresh_steps WHERE run_id=%s
            AND stage='publish' ORDER BY step_seq DESC LIMIT 1""",(run_id,)).fetchone()
    return run,version,warning,approval,publish_step,event


def read_last_refresh(connection):
    """Read only the public status and times of the greatest-sequence attempt."""
    return connection.execute("""
        SELECT status, requested_at, finished_at
        FROM refresh_runs ORDER BY run_seq DESC LIMIT 1
        """).fetchone()


def read_context(connection):
    """Read the occupied lifecycle, candidate and unresolved warning."""
    control = connection.execute("SELECT holder_run_id FROM refresh_control WHERE id=1").fetchone()
    if control is None:
        raise Problem(503, "dependency_unavailable")
    warning = connection.execute("SELECT * FROM failure_warnings WHERE resolved_at IS NULL").fetchone()
    run = version = approval = step = None
    if control["holder_run_id"] is not None:
        run = connection.execute("SELECT * FROM refresh_runs WHERE id=%s", (control["holder_run_id"],)).fetchone()
        if run is None or run["status"] in ("succeeded", "discarded", "superseded"):
            raise Problem(503, "dependency_unavailable")
        version = connection.execute("SELECT * FROM data_versions WHERE run_id=%s", (run["id"],)).fetchone()
        if version:
            approval = connection.execute("SELECT * FROM approvals WHERE version_id=%s", (version["id"],)).fetchone()
            if version["validation_step_id"]:
                step = connection.execute("SELECT * FROM refresh_steps WHERE id=%s", (version["validation_step_id"],)).fetchone()
    if warning and (run is None or warning["run_id"] != run["id"]):
        raise Problem(503, "dependency_unavailable")
    if run and run["status"] in ("failed", "publication_failed") and warning is None:
        raise Problem(503, "dependency_unavailable")
    if run and version:
        from trinity.publication.checks import actions
        run['_publication_actions'] = actions(connection,run,version,warning)
    if run and run['status'] in ('failed', 'publication_failed'):
        from trinity.refresh.recovery import recovery_actions
        from trinity.settings.repository import read_settings
        # Use the same snapshot as the holder/warning reads. The command repeats
        # this predicate on locked rows; these flags cannot grant authority.
        run['_recovery_actions'] = recovery_actions(
            connection, read_settings(connection), control, run, version, warning)
    return run, version, warning, approval, step
