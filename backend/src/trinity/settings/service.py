"""Read authorized shared settings without allowing mutation."""
from trinity.auth.permissions import require
from trinity.settings.repository import read_settings
from trinity.settings.schemas import SettingsResponse


def get_settings(principal, connection):
    """Authorize before loading the protected settings row."""
    require(principal, "settings:read")
    row = read_settings(connection)
    return SettingsResponse(setup_completed_at=row["setup_completed_at"],
                            schedule_enabled=row["schedule_enabled"], daily_time=row["daily_time"],
                            timezone=row["schedule_timezone"], revision=str(row["revision"]),
                            updated_at=row["updated_at"], updated_by=row["updated_by"])
