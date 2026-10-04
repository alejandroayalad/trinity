"""Read safe refresh summaries and Admin lifecycle state without commands."""
from trinity.errors import Problem


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
    return run, version, warning, approval, step
