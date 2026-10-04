"""Define closed catalog responses and validate safe snapshot metadata."""

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import Field, field_validator, model_validator

from trinity.auth.schemas import Publication, RunStatus, StrictModel

DatasetKey = Literal["national_outages", "facility_outages", "generator_outages"]
FilterName = Literal["start", "end", "facility", "generator"]


def utc_timestamp(value: datetime) -> datetime:
    """Reject missing timezone information and normalize recorded times to UTC."""
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("Invalid recorded timestamp")
    return value.astimezone(timezone.utc)


class Column(StrictModel):
    """Describe a column without exposing storage details."""
    name: str = Field(min_length=1, max_length=128)
    type: Literal["string", "date", "timestamp", "decimal", "integer", "boolean"]
    nullable: bool
    unit: Literal["MW", "percent"] | None


class Dataset(StrictModel):
    """Describe one permitted analytical dataset."""
    key: DatasetKey
    label: str = Field(min_length=1, max_length=512)
    description: str = Field(min_length=1, max_length=512)
    daily_key: list[str] = Field(min_length=1, max_length=3)
    columns: list[Column] = Field(min_length=1, max_length=7)
    available_filters: list[FilterName] = Field(max_length=4)


class MetricDefinition(StrictModel):
    """Describe the national calculation without computing a value."""
    key: Literal["offline_share_percent"]
    label: str = Field(min_length=1, max_length=512)
    unit: Literal["percent"]
    formula: str
    null_reasons: list[Literal["not_reported", "zero_capacity"]] = Field(max_length=2)
    display_decimal_places: Literal[2]


class LastRefresh(StrictModel):
    """Expose only the newest refresh attempt's status and recorded times."""
    status: RunStatus
    requested_at: datetime
    finished_at: datetime | None

    @field_validator("requested_at", "finished_at")
    @classmethod
    def normalize_times(cls, value):
        """Preserve null finish times and normalize recorded timestamps."""
        return None if value is None else utc_timestamp(value)

    @model_validator(mode="after")
    def validate_completion(self):
        """Require a finish time exactly for terminal refresh states."""
        terminal = self.status in ("succeeded", "failed", "discarded", "superseded")
        if terminal != (self.finished_at is not None):
            raise ValueError("Invalid refresh completion state")
        return self


class Freshness(StrictModel):
    """Keep published observation dates separate from the latest attempt."""
    latest_observation_date: date | None
    published_at: datetime | None
    last_refresh: LastRefresh | None

    @field_validator("published_at")
    @classmethod
    def normalize_time(cls, value):
        """Normalize a present publication time without fabricating one."""
        return None if value is None else utc_timestamp(value)


class CatalogResponse(StrictModel):
    """Return one complete catalog and internally consistent publication state."""
    datasets: list[Dataset] = Field(min_length=1, max_length=3)
    metrics: list[MetricDefinition] = Field(min_length=1, max_length=1)
    data_ready: bool
    publication: Publication | None
    freshness: Freshness

    @field_validator("publication")
    @classmethod
    def validate_publication(cls, value):
        """Validate the coverage range and normalize publication time."""
        if value is None:
            return None
        if not value.coverage_start <= value.latest_observation_date <= value.coverage_end:
            raise ValueError("Invalid publication coverage")
        return value.model_copy(update={"published_at": utc_timestamp(value.published_at)})

    @model_validator(mode="after")
    def validate_snapshot(self):
        """Reject duplicate definitions and conflicting readiness or dates."""
        if len({dataset.key for dataset in self.datasets}) != len(self.datasets):
            raise ValueError("Duplicate catalog definition")
        if self.data_ready != (self.publication is not None):
            raise ValueError("Inconsistent publication readiness")
        expected_date = self.publication.latest_observation_date if self.publication else None
        expected_time = self.publication.published_at if self.publication else None
        if (self.freshness.latest_observation_date != expected_date
                or self.freshness.published_at != expected_time):
            raise ValueError("Inconsistent publication freshness")
        return self
