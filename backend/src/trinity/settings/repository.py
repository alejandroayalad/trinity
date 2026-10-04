"""Read shared settings through an authorized service transaction."""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from trinity.errors import Problem


def read_settings(connection):
    """Treat absent/corrupt shared state as failure, never fresh setup."""
    row = connection.execute("SELECT * FROM shared_settings WHERE id=1").fetchone()
    if row is None:
        raise Problem(503, "dependency_unavailable")
    if row["setup_completed_at"] is not None:
        try:
            ZoneInfo(row["schedule_timezone"])
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise Problem(503, "dependency_unavailable") from None
    return row
