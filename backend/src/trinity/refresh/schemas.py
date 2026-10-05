"""Define strict refresh commands and safe tracking responses from A16."""
from datetime import date, datetime
import json
import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, ValidationError

from trinity.auth.schemas import Action, Blocker, EmptyRequest, RefreshSummary, RunStatus, StrictModel
from trinity.errors import Problem

Counter = Annotated[str, Field(pattern=r'^(0|[1-9][0-9]*)$')]


class ActionReceipt(StrictModel):
    """Describe the original accepted command, not its current execution state."""
    operation_id: UUID
    action: Literal['start_refresh']
    accepted_at: datetime
    run_id: UUID
    version_id: UUID | None
    status_url: str = Field(pattern=r'^/api/v1/refresh-runs/[0-9a-f-]{36}$')
    result: Literal['queued']
    replayed: bool


class FailureWarning(StrictModel):
    """Expose sanitized failure metadata without internal evidence or paths."""
    warning_id: UUID
    run_id: UUID
    version_id: UUID | None
    stage: Literal['extract','prepare','validate','publish','dispatch']
    code: str = Field(max_length=64)
    message: str = Field(max_length=512)
    created_at: datetime
    resolved_at: datetime | None
    resolution: str | None
    resolved_by: str | None


class Progress(StrictModel):
    """Keep unknown totals null and encode large counters without float loss."""
    processed_count: Counter
    total_count: Counter | None
    unit: Literal['rows','files','checks','tasks']


class Step(StrictModel):
    """Keep each attempt separately addressable in immutable sequence order."""
    step_id: UUID
    step_seq: Counter
    stage: Literal['extract','prepare','validate','publish']
    work_key: str = Field(max_length=128)
    attempt: int = Field(ge=1)
    status: Literal['pending','running','succeeded','failed','abandoned']
    started_at: datetime | None
    finished_at: datetime | None
    progress: Progress
    error_code: str | None
    error_summary: str | None


class CandidateRef(StrictModel):
    """Link tracking to one candidate without disclosing its storage identity."""
    version_id: UUID
    review_status: Literal['not_ready','not_required','required','approved','discarded']
    publication_status: Literal['not_started','queued','publishing','failed','published','blocked']


class Run(StrictModel):
    """Return current run metadata and one bounded page of retained steps."""
    run_id: UUID
    run_seq: Counter
    revision: Counter
    trigger_kind: Literal['manual','scheduled','rerun']
    requested_by: str | None
    rerun_of_run_id: UUID | None
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    status: RunStatus
    settings_revision: Counter
    workflow_policy: Literal['warnings-v1']
    requested_start: date
    requested_end: date | None
    candidate: CandidateRef | None
    warning: FailureWarning | None
    actions: list[Action] = Field(max_length=6)
    steps: list[Step] = Field(max_length=100)
    next_steps_cursor: str | None
    poll_after_seconds: Literal[2] | None


class RunList(StrictModel):
    """Keep current admission state visible even on an old history page."""
    items: list[RefreshSummary] = Field(max_length=100)
    next_cursor: str | None
    active_run: RefreshSummary | None
    unresolved_warning: FailureWarning | None
    blocker: Blocker | None
    actions: list[Action] = Field(max_length=6)


def parse_command(raw, key_headers, pairs):
    """Require one UUID key and exactly an empty object after authorization."""
    if len(key_headers) == 0:
        raise Problem(422, 'idempotency_key_required')
    try:
        if len(key_headers) != 1 or pairs or len(key_headers[0]) != 36:
            raise ValueError
        key = UUID(key_headers[0])
        if str(key) != key_headers[0].lower():
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise Problem(422, 'invalid_request') from None
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise Problem(400, 'invalid_json') from None
    try:
        EmptyRequest.model_validate(body)
    except ValidationError:
        raise Problem(422, 'invalid_request') from None
    return key


def parse_page(pairs, *, steps=False, body=b''):
    """Reject repeated/unknown parameters before accepting a bounded bookmark."""
    limit_name, cursor_name = ('steps_limit','steps_cursor') if steps else ('limit','cursor')
    values = {}
    try:
        if body:
            raise ValueError
        for key,value in pairs:
            if key not in (limit_name,cursor_name) or key in values or not value:
                raise ValueError
            values[key] = value
        limit = values.get(limit_name)
        if limit is not None:
            if re.fullmatch(r'[1-9][0-9]{0,2}',limit) is None or int(limit)>100:
                raise ValueError
            limit = int(limit)
        cursor = values.get(cursor_name)
        if cursor is not None and len(cursor)>4096:
            raise ValueError
        return limit, cursor
    except (ValueError, TypeError):
        raise Problem(422, 'invalid_request') from None
