"""Read safe refresh summaries and Admin lifecycle state without commands."""
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


def accept_run(connection, actor_id, key, fingerprint, settings):
    """Write the run, slot, queue intent and receipt on the supplied transaction.

    The service already holds refresh_control and the settings snapshot lock.
    Nothing here commits or contacts Redis. A failure in the final receipt
    insert must also roll back the earlier slot and outbox writes.
    """
    from datetime import date
    from uuid import uuid4
    from psycopg.types.json import Jsonb
    run_id, operation = uuid4(),uuid4()
    policy = {'settings_revision':settings['revision'],'workflow_policy':'warnings-v1',
              'diagnostic_registry':'warnings-v1','contract_version':'trinity-data-v1',
              'validation_checkset':'trinity-data-v1','requested_start':'2024-10-02',
              'end_strategy':'latest_national'}
    run = connection.execute("""INSERT INTO refresh_runs(id,trigger_kind,requested_by,request_key,
        requested_at,status,settings_revision,policy_snapshot,requested_start)
        VALUES(%s,'manual',%s,%s,clock_timestamp(),'requested',%s,%s,%s) RETURNING *""",
        (run_id,actor_id,key,settings['revision'],Jsonb(policy),date(2024,10,2))).fetchone()
    connection.execute('UPDATE refresh_control SET holder_run_id=%s,revision=revision+1 WHERE id=1',(run_id,))
    connection.execute("""INSERT INTO job_outbox(id,run_id,job_kind,deduplication_key,payload)
        VALUES(%s,%s,'refresh_pipeline',%s,%s)""",
        (uuid4(),run_id,f'refresh:{run_id}',Jsonb({'schema_version':1,'run_id':str(run_id),
         'version_id':None,'job_kind':'refresh_pipeline','dispatch_generation':0})))
    return connection.execute("""INSERT INTO api_commands(id,idempotency_key,actor_id,action,
        request_fingerprint,accepted_at,run_id,result,status_url)
        VALUES(%s,%s,%s,'start_refresh',%s,%s,%s,'queued',%s) RETURNING *""",
        (operation,key,actor_id,fingerprint,run['requested_at'],run_id,
         f'/api/v1/refresh-runs/{run_id}')).fetchone()


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
    return run, version, warning, approval, step
