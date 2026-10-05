"""Define strict refresh commands and safe tracking responses from A16."""
from datetime import date, datetime
from dataclasses import dataclass
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
    action: Literal['start_refresh','approve','publication_retry','discard','rerun','delete_warning']
    accepted_at: datetime
    run_id: UUID
    version_id: UUID | None
    status_url: str = Field(pattern=r'^/api/v1/refresh-runs/[0-9a-f-]{36}$')
    result: Literal['queued','discarded','warning_resolved']
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


@dataclass(frozen=True)
class RecoveryCommand:
    """Keep validated command identity separate from current database state."""

    run_id: UUID
    key: UUID
    action: Literal['rerun', 'delete_warning']
    revision: str


def parse_recovery_command(run_id, action, raw, key_headers, etags, pairs=()):
    """Validate one recovery request after the caller authorizes the Admin.

    Accept a run UUID, action, raw body and all command-header values. Return
    immutable identity and the expected revision, without reading any state.
    Rerun requires an empty JSON object; warning deletion requires zero bytes.
    Reject missing preconditions with 428 and malformed inputs with safe errors.
    The caller must compare the revision only after checking receipt replay.
    This parser neither authorizes the actor nor enables a mutation route.
    """
    if not etags:
        raise Problem(428, 'precondition_required')
    # A revision is a decimal counter, not a weak tag or list of alternatives.
    # For example, "run-12" is valid; "run-012" and "candidate-12" are not.
    match = (re.fullmatch(r'"run-(0|[1-9][0-9]*)"', etags[0])
             if len(etags) == 1 else None)
    if match is None:
        raise Problem(422, 'invalid_request')
    try:
        parsed_run = UUID(run_id)
        if len(run_id) != 36 or str(parsed_run) != run_id.lower():
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise Problem(422, 'invalid_request') from None
    if action not in ('rerun', 'delete_warning'):
        raise Problem(422, 'invalid_request')
    # Hashing may use the same empty intent for both actions, but an actual
    # DELETE body is forbidden. Do not silently treat supplied {} as no body.
    if action == 'delete_warning' and raw != b'':
        raise Problem(422, 'invalid_request')
    key = parse_command(b'{}' if action == 'delete_warning' else raw, key_headers, pairs)
    return RecoveryCommand(parsed_run, key, action, match.group(1))


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
