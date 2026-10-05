"""Public shared-settings request and response models.

The models are closed: extra fields fail validation. StrictModel also turns
off type coercion, so the JSON string "true" is not accepted as a boolean.
"""
from datetime import datetime
from pydantic import Field, field_validator, model_validator
from trinity.auth.schemas import Blocker, StrictModel
from trinity.catalog.schemas import utc_timestamp
from trinity.settings.schedule import valid_timezone

COUNTER = r"^(0|[1-9][0-9]*)$"
DAILY_TIME = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"


class SettingsResponse(StrictModel):
    """Expose the canonical settings fields and string revision."""
    setup_completed_at: datetime | None
    schedule_enabled: bool
    daily_time: str | None
    timezone: str | None
    revision: str = Field(pattern=COUNTER)
    updated_at: datetime
    updated_by: str | None


class SettingsRequest(StrictModel):
    """Accept exactly the three editable schedule fields for PUT /settings.

    All three fields are required, also when schedule_enabled is false.
    The client cannot send a revision, actor, setup time or publication_mode;
    those names are extra fields and fail validation.
    """
    schedule_enabled: bool
    daily_time: str = Field(pattern=DAILY_TIME)
    timezone: str = Field(min_length=1, max_length=100)

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value):
        """Reject names that are not exact IANA names in this runtime."""
        if not valid_timezone(value):
            raise ValueError("Unknown timezone")
        return value


class ScheduleStatus(StrictModel):
    """Describe the next daily check and the one current refresh blocker.

    The validators keep two contract rules true in every response:
    both next-check fields are null together, and eligible_now is true
    exactly when no blocker exists.
    """
    settings_revision: str = Field(pattern=COUNTER)
    schedule_enabled: bool
    next_check_at: datetime | None
    next_check_local: str | None = Field(max_length=40)
    timezone: str | None
    evaluated_at: datetime
    eligible_now: bool
    blocker: Blocker | None

    @field_validator("next_check_at", "evaluated_at")
    @classmethod
    def normalize_times(cls, value):
        """Keep null next checks and normalize recorded times to UTC."""
        return None if value is None else utc_timestamp(value)

    @model_validator(mode="after")
    def consistent_fields(self):
        """Reject a half-filled next check or a blocker that disagrees with eligibility."""
        if (self.next_check_at is None) != (self.next_check_local is None):
            raise ValueError("Next check fields must be set together")
        if self.next_check_at is not None and self.next_check_at <= self.evaluated_at:
            raise ValueError("Next check must be after evaluation time")
        if self.eligible_now != (self.blocker is None):
            raise ValueError("eligible_now must match the blocker")
        return self
