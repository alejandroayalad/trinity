"""Public shared-settings response."""
from datetime import datetime
from pydantic import Field
from trinity.auth.schemas import StrictModel


class SettingsResponse(StrictModel):
    """Expose the canonical settings fields and string revision."""
    setup_completed_at: datetime | None
    schedule_enabled: bool
    daily_time: str | None
    timezone: str | None
    revision: str = Field(pattern=r"^(0|[1-9][0-9]*)$")
    updated_at: datetime
    updated_by: str | None
