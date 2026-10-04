"""Strict HTTP models for local credentials and application entry."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

Role = Literal["viewer", "analyst", "admin"]
Capability = Literal["national:read", "catalog:read", "preview:national", "preview:detail", "sql:execute",
                     "settings:read", "settings:write", "refresh:read", "refresh:start", "refresh:recover",
                     "candidate:review"]
BlockCode = Literal["setup_required", "schedule_disabled", "refresh_active", "review_required",
                    "publication_in_progress", "failure_unresolved", "candidate_ineligible",
                    "candidate_discarded", "candidate_superseded", "already_published",
                    "no_unresolved_warning", "not_applicable", "dependency_unavailable"]
RunStatus = Literal["requested", "running", "awaiting_approval", "publishing", "publication_failed",
                    "succeeded", "failed", "discarded", "superseded"]


class StrictModel(BaseModel):
    """Reject unspecified fields and implicit input coercion."""
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class LoginRequest(StrictModel):
    """Accept only username and a nonlogged password."""
    username: str = Field(min_length=1, max_length=128)
    password: SecretStr

    @field_validator("password")
    @classmethod
    def password_length(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if not 1 <= len(password) <= 1024:
            raise ValueError("Invalid password length")
        password.encode("utf-8")
        return value

    @field_validator("username")
    @classmethod
    def username_encoding(cls, value: str) -> str:
        value.encode("utf-8")
        return value


class EmptyRequest(StrictModel):
    """Require an explicit empty JSON object."""


class LoginResponse(StrictModel):
    """Return the new token once, after its digest commits."""
    access_token: str = Field(repr=False)
    token_type: Literal["Bearer"] = "Bearer"
    expires_at: datetime


class Publication(StrictModel):
    """Describe one pinned active publication without storage locations."""
    publication_event_id: UUID
    version_id: UUID
    published_at: datetime
    coverage_start: date
    coverage_end: date
    latest_observation_date: date


class Action(StrictModel):
    """Describe business eligibility; this is never mutation authority."""
    action: Literal["start_refresh", "rerun", "delete_warning", "approve", "publication_retry", "discard"]
    enabled: bool
    reason_code: BlockCode | None


class Blocker(StrictModel):
    """Describe only the current Admin-visible lifecycle blocker."""
    code: BlockCode
    message: str = Field(max_length=512)
    run_id: UUID | None
    version_id: UUID | None
    warning_id: UUID | None


class RefreshSummary(StrictModel):
    """Expose bounded current-run metadata to Admin."""
    run_id: UUID
    status: RunStatus
    requested_at: datetime
    finished_at: datetime | None


class AdminContext(StrictModel):
    """Describe shared setup and refresh eligibility."""
    setup_completed: bool
    refresh_blocker: Blocker | None
    active_run: RefreshSummary | None
    actions: list[Action] = Field(max_length=6)


class MeResponse(StrictModel):
    """Describe current identity and one consistent application snapshot."""
    user_id: str = Field(min_length=1, max_length=128)
    role: Role
    capabilities: list[Capability] = Field(max_length=11)
    data_ready: bool
    landing_screen: Literal["waiting", "setup", "refresh_runs", "national_dashboard", "explorer"]
    publication: Publication | None
    admin_context: AdminContext | None
