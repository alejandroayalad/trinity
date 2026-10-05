"""Read and change the singleton `shared_settings` row on a caller's transaction.

The service owns the transaction, permission checks and lock order. These
functions only run SQL on the connection they receive. They never commit.
"""
from trinity.errors import Problem
from trinity.settings.schedule import valid_timezone


def read_settings(connection):
    """Treat absent/corrupt shared state as failure, never fresh setup.

    A stored timezone must be an exact IANA name in this runtime. A row
    that fails this check is corrupt state, so the result is 503, not a
    silent fallback to UTC or to "not set up".
    """
    row = connection.execute("SELECT * FROM shared_settings WHERE id=1").fetchone()
    if row is None:
        raise Problem(503, "dependency_unavailable")
    if row["setup_completed_at"] is not None and not valid_timezone(row["schedule_timezone"]):
        raise Problem(503, "dependency_unavailable")
    return row


def lock_settings(connection):
    """Lock the settings row for a write and return it.

    FOR UPDATE makes a second writer, or a refresh admission that needs a
    share lock, wait until this transaction ends. The caller compares the
    revision only after this lock, so two saves cannot both succeed.
    """
    connection.execute("SELECT id FROM shared_settings WHERE id=1 FOR UPDATE")
    return read_settings(connection)


def share_settings(connection):
    """Lock the settings row against writes and return it.

    FOR SHARE lets other readers continue but makes PUT /settings wait.
    Refresh admission uses it so the revision it freezes cannot change
    before its transaction commits.
    """
    connection.execute("SELECT id FROM shared_settings WHERE id=1 FOR SHARE")
    return read_settings(connection)


def database_now(connection):
    """Return the current PostgreSQL time as an aware datetime.

    clock_timestamp() gives the real time at this statement. now() would
    give the transaction start time. PostgreSQL is the only clock for the
    schedule, so the API and the scheduler cannot disagree.
    """
    return connection.execute("SELECT clock_timestamp() AS now").fetchone()["now"]


def write_settings(connection, values, actor_id, now):
    """Store a changed schedule as the next revision and return the new row.

    Input: validated SettingsRequest values, the session's local user ID and
    the PostgreSQL time. The caller already holds lock_settings and has
    checked the revision and that the values changed.

    COALESCE keeps an existing setup time. The first save sets it to the
    same instant as updated_at; later saves never change it.
    """
    return connection.execute("""
        UPDATE shared_settings
        SET schedule_enabled=%s, daily_time=%s, schedule_timezone=%s,
            revision=revision+1, updated_at=%s, updated_by=%s,
            setup_completed_at=COALESCE(setup_completed_at, %s)
        WHERE id=1 RETURNING *""",
        (values.schedule_enabled, values.daily_time, values.timezone, now, actor_id, now)).fetchone()
