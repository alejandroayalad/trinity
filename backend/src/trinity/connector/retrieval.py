"""Credential-free retrieval evidence and per-call counters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
import json
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    # Type checkers need the collection name. Runtime avoids a circular import
    # because client.py imports these evidence types too.
    from trinity.connector.client import EIACollection


RetrievalStatus = Literal["success", "failed", "cancelled", "skipped"]


def utc_now() -> datetime:
    """Return the current time with an explicit UTC timezone."""
    return datetime.now(UTC)


# frozen=True prevents field replacement; evidence values are set at construction.
@dataclass(frozen=True)
class RetrievalAttempt:
    """One actual HTTP attempt, including failures; never contains request secrets."""

    offset: int
    requested_length: int
    attempt_number: int
    started_at: datetime
    completed_at: datetime
    http_status: int | None
    api_status: str
    api_version: str | None
    advertised_total: int | str | None
    actual_row_count: int | None
    error_code: str | None
    sanitized_response: str | None
    response_sha256: str | None


@dataclass(frozen=True)
class RetrievalMetadata:
    """Final route outcome. Counts are evidence, not a successful partial dataset."""

    dataset: str
    route: str
    started_at: datetime
    completed_at: datetime
    pages_fetched: int
    records_fetched: int
    retries: int
    final_status: RetrievalStatus
    error_message: str | None
    error_code: str | None
    requested_start: date | None
    requested_end: date | None
    frequency: str
    sort_fields: tuple[str, ...]
    attempts: tuple[RetrievalAttempt, ...]

    def to_dict(self, *, include_attempts: bool = True) -> dict:
        """Return JSON-ready evidence; omit attempts for a compact route summary."""
        # Keep sanitized_response unchanged so its UTF-8 bytes still match the hash.
        # asdict copies nested dataclasses; removing attempts does not change this record.
        result = asdict(self)
        if not include_attempts:
            result.pop("attempts")
        # Encode dates/times as ISO text and tuples as JSON arrays, then return a dict.
        return json.loads(json.dumps(result, default=lambda value: value.isoformat()))


@dataclass
class RetrievalTracker:
    """Mutable state belongs to one call, never to the shared HTTP client."""

    dataset: str
    route: str
    start: date | None
    end: date | None
    sort_fields: tuple[str, ...]
    # Factories run for each tracker, so calls share neither timestamps nor attempt lists.
    started_at: datetime = field(default_factory=utc_now)
    pages_fetched: int = 0
    records_fetched: int = 0
    retries: int = 0
    attempts: list[RetrievalAttempt] = field(default_factory=list)

    def finish(
        self, status: RetrievalStatus, *, error_code: str | None = None,
        error_message: str | None = None,
    ) -> RetrievalMetadata:
        """Snapshot this call's evidence with a final status and completion time."""
        # Copy attempts into a tuple so later list appends cannot change the snapshot.
        # Counts on failure describe fetched evidence, not a usable partial dataset.
        return RetrievalMetadata(
            dataset=self.dataset, route=self.route, started_at=self.started_at,
            completed_at=utc_now(), pages_fetched=self.pages_fetched,
            records_fetched=self.records_fetched, retries=self.retries,
            final_status=status, error_message=error_message, error_code=error_code,
            requested_start=self.start, requested_end=self.end,
            frequency="daily", sort_fields=self.sort_fields, attempts=tuple(self.attempts),
        )


@dataclass(frozen=True)
class RetrievalResult:
    """Only successful routes expose a complete collection to the next stage."""

    metadata: RetrievalMetadata
    collection: EIACollection | None = None
