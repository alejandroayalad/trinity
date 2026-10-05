"""Validate closed national responses without reading publication or source data.

The builders supply exact source strings and calculated metrics. These models
check dates, null reasons and complete response consistency. They do not prove
the provenance of rows or diagnostics; the shared preview reader owns that work.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from trinity.auth.schemas import Publication, StrictModel
from trinity.catalog.schemas import Freshness, utc_timestamp
from trinity.queries.preview import strict_date
from trinity.queries.preview_schemas import PreviewDiagnostic

DecimalText = Annotated[str, Field(pattern=r'^-?(0|[1-9][0-9]*)(\.[0-9]+)?$')]
PercentText = Annotated[str, Field(pattern=r'^-?(0|[1-9][0-9]*)\.[0-9]{2}$')]
Reason = Literal['not_reported', 'zero_capacity']


def _metric_reason(value, reason):
    """Require a reason exactly when the metric is absent; normalize no values."""
    if (value is None) != (reason is not None) or value == '-0.00':
        raise ValueError('Invalid metric reason')


class DateRange(StrictModel):
    """Keep 1–366 inclusive dates without clamping them to source coverage."""
    model_config = ConfigDict(revalidate_instances='always')
    start: date
    end: date

    @field_validator('start', 'end', mode='before')
    @classmethod
    def exact_dates(cls, value):
        """Reject compact ISO dates that Python would otherwise accept."""
        return strict_date(value) if isinstance(value, str) else value

    @model_validator(mode='after')
    def ordered(self):
        """Accept a full leap year, but reject a 367-date range."""
        if not 0 <= (self.end - self.start).days < 366:
            raise ValueError('Invalid national range')
        return self


class NationalDay(StrictModel):
    """Preserve one source row or represent one absent observation explicitly."""
    model_config = ConfigDict(revalidate_instances='always')
    period: date
    capacity: DecimalText | None
    outage: DecimalText | None
    percentOutage: DecimalText | None
    offline_share_percent: PercentText | None
    reason: Reason | None

    @field_validator('period', mode='before')
    @classmethod
    def exact_date(cls, value):
        """Accept only a calendar date or its exact public spelling."""
        return strict_date(value) if isinstance(value, str) else value

    @model_validator(mode='after')
    def consistent_values(self):
        """Distinguish missing observations from present rows with zero capacity."""
        _metric_reason(self.offline_share_percent, self.reason)
        if self.reason == 'not_reported':
            if any(v is not None for v in (self.capacity, self.outage, self.percentOutage)):
                raise ValueError('Invalid absent observation')
        else:
            if self.capacity is None or self.outage is None or Decimal(self.capacity) < 0:
                raise ValueError('Invalid present observation')
            if (Decimal(self.capacity) == 0) != (self.reason == 'zero_capacity'):
                raise ValueError('Invalid capacity reason')
        return self


class MetricValue(StrictModel):
    """Carry the shared two-place calculation and its explicit null reason."""
    model_config = ConfigDict(revalidate_instances='always')
    value: PercentText | None
    reason: Reason | None

    @model_validator(mode='after')
    def consistent_reason(self):
        """Reject a fabricated number for a missing or zero-capacity row."""
        _metric_reason(self.value, self.reason)
        return self


class _NationalResponse(StrictModel):
    """Check shared publication metadata and national diagnostic privacy."""
    model_config = ConfigDict(revalidate_instances='always')
    publication: Publication
    diagnostics: list[PreviewDiagnostic] = Field(max_length=32)

    @field_validator('publication')
    @classmethod
    def valid_publication(cls, value):
        """Recheck supplied instances and keep publication time in UTC."""
        value = Publication.model_validate(value.model_dump())
        if not value.coverage_start <= value.latest_observation_date <= value.coverage_end:
            raise ValueError('Invalid publication coverage')
        return value.model_copy(update={'published_at': utc_timestamp(value.published_at)})

    @field_validator('diagnostics')
    @classmethod
    def national_diagnostics(cls, value):
        """Allow only unique national summaries; never expose detail scopes."""
        if any(item.scope != 'national' for item in value) or len({i.code for i in value}) != len(value):
            raise ValueError('Invalid national diagnostics')
        return value


class DashboardResponse(_NationalResponse):
    """Return every selected date and cards for exactly the selected end date."""
    range: DateRange
    summary: NationalDay
    days: list[NationalDay] = Field(max_length=366)
    freshness: Freshness

    @field_validator('freshness')
    @classmethod
    def valid_freshness(cls, value):
        """Recheck nested timestamps even when the caller supplies an instance."""
        return Freshness.model_validate(value.model_dump())

    @model_validator(mode='after')
    def consistent_dashboard(self):
        """Reject gaps, reordered points, substitute cards or mixed metadata."""
        count = (self.range.end - self.range.start).days + 1
        if len(self.days) != count or any(
            point.period != self.range.start + timedelta(days=index)
            for index, point in enumerate(self.days)
        ):
            raise ValueError('Invalid dashboard dates')
        if self.summary != self.days[-1]:
            raise ValueError('Invalid dashboard summary')
        if (self.freshness.latest_observation_date != self.publication.latest_observation_date
                or self.freshness.published_at != self.publication.published_at):
            raise ValueError('Invalid dashboard freshness')
        return self


class MetricResponse(_NationalResponse):
    """Return the same metric as the dashboard for one requested date."""
    period: date
    metric: MetricValue

    @field_validator('period', mode='before')
    @classmethod
    def exact_date(cls, value):
        """Do not accept timestamps or compact date strings."""
        return strict_date(value) if isinstance(value, str) else value
