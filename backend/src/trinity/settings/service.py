"""Read and change the shared daily schedule, and describe its next check.

This feature owns three Admin operations:

- `get_settings` reads the singleton settings row.
- `SettingsService.update` saves the schedule with an optimistic revision
  check. The client sends `If-Match: "settings-<revision>"` from its last
  read. A stale revision fails with 412, so one Admin cannot overwrite
  another Admin's newer save. Saving never starts a refresh.
- `schedule_status` calculates the next daily check and the one reason
  that blocks refresh admission now. It reads only; it reserves nothing.

The clock rules live in `settings/schedule.py`. PostgreSQL supplies "now".
The scheduler worker, not this module, admits scheduled refreshes.
"""
import json
import re

from pydantic import ValidationError

from trinity.auth.permissions import require
from trinity.auth.schemas import Blocker
from trinity.errors import Problem
from trinity.settings.repository import database_now, lock_settings, read_settings, write_settings
from trinity.settings.schedule import local_text, next_check
from trinity.settings.schemas import ScheduleStatus, SettingsRequest, SettingsResponse

# A strong ETag is a quoted string. The pattern accepts "settings-0" and
# "settings-12". It rejects W/"settings-1" (weak), "settings-01" (leading
# zero), * (wildcard) and tags of other resources such as "candidate-1".
_SETTINGS_ETAG = re.compile(r'"settings-(0|[1-9][0-9]*)"')

# Fixed, safe text for each blocker code. Run error details never appear here.
BLOCKER_MESSAGES = {
    "setup_required": "Complete setup before refreshes can run.",
    "schedule_disabled": "The daily schedule is off. Manual refresh is still available.",
    "refresh_active": "A refresh is running.",
    "review_required": "A candidate is waiting for Admin review.",
    "publication_in_progress": "A publication is in progress.",
    "failure_unresolved": "A failed refresh needs Admin action.",
}


def _response(row):
    """Project a settings row into the public response model."""
    return SettingsResponse(setup_completed_at=row["setup_completed_at"],
                            schedule_enabled=row["schedule_enabled"], daily_time=row["daily_time"],
                            timezone=row["schedule_timezone"], revision=str(row["revision"]),
                            updated_at=row["updated_at"], updated_by=row["updated_by"])


def get_settings(principal, connection):
    """Authorize before loading the protected settings row."""
    require(principal, "settings:read")
    return _response(read_settings(connection))


def parse_settings_command(raw, if_match, pairs):
    """Check the precondition and body of PUT /settings before any state read.

    Input: the raw body bytes, every If-Match header value and the query pairs.
    Result: (expected revision as int, validated SettingsRequest).

    Order matters. A missing precondition is 428 even when the body is also
    invalid, because the client must first learn which revision it edits.
    Failures: 428 precondition_required, 422 invalid_request, 400 invalid_json.
    """
    if pairs:
        raise Problem(422, "invalid_request")
    if not if_match:
        raise Problem(428, "precondition_required")
    # Two headers, or one header with two comma-separated tags, are both
    # rejected: the client must name exactly one revision.
    match = _SETTINGS_ETAG.fullmatch(if_match[0]) if len(if_match) == 1 else None
    if match is None:
        raise Problem(422, "invalid_request")
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise Problem(400, "invalid_json") from None
    try:
        values = SettingsRequest.model_validate(body)
    except ValidationError:
        raise Problem(422, "invalid_request") from None
    return int(match.group(1)), values


def _unchanged(row, values):
    """Return True when the request repeats the stored schedule exactly.

    The booleans compare by value; time and timezone compare as exact
    strings. Before setup the stored time is null, so this is always False.
    """
    return (row["schedule_enabled"] == values.schedule_enabled
            and row["daily_time"] == values.daily_time
            and row["schedule_timezone"] == values.timezone)


class SettingsService:
    """Save the shared schedule in one PostgreSQL transaction."""

    def __init__(self, database):
        self.database = database

    def update(self, token, raw, if_match, pairs=()):
        """Save the schedule, or return the current row for a no-op save.

        Flow, in this order:

        1. Check the session and `settings:write` without locks.
        2. Check If-Match and the body (parse_settings_command). Nothing
           has read settings yet.
        3. Lock the user and session, then the settings row. A concurrent
           role change, logout or second save must wait.
        4. A stale revision fails with 412 and writes nothing. This check
           comes before the no-op check, so a stale client never gets 200.
        5. Identical values return the current row. Revision, updated_at
           and updated_by stay unchanged, so a due scheduled check stays due.
        6. Other values become the next revision with the PostgreSQL time.

        The response is built only after the transaction commits. A commit
        failure becomes 503 and the client must GET settings to reconcile.
        """
        from trinity.adapters.postgres import Deadline
        from trinity.refresh.service import _authorize
        try:
            with self.database.transaction(Deadline(), error_code="dependency_unavailable") as connection:
                _authorize(connection, token, "settings:write")
                expected, values = parse_settings_command(raw, if_match, pairs)
                actor = _authorize(connection, token, "settings:write", lock=True)
                row = lock_settings(connection)
                if row["revision"] != expected:
                    raise Problem(412, "revision_mismatch")
                if not _unchanged(row, values):
                    row = write_settings(connection, values, actor.user_id, database_now(connection))
            return _response(row)
        except Problem as error:
            if error.status == 503 and error.code == "dependency_unavailable":
                raise Problem(503, error.code, retry_after=1) from None
            raise


def choose_blocker(row, context):
    """Return the one blocker for the status page, or None.

    Priority: setup_required, then schedule_disabled, then the lifecycle
    blocker that refresh admission already computes (`admin_context`).
    A disabled schedule hides a lifecycle blocker on this page only;
    manual Start still uses `admin_context` directly.
    """
    if row["setup_completed_at"] is None:
        code, source = "setup_required", None
    elif not row["schedule_enabled"]:
        code, source = "schedule_disabled", None
    elif context.refresh_blocker is not None:
        code, source = context.refresh_blocker.code, context.refresh_blocker
    else:
        return None
    return Blocker(code=code, message=BLOCKER_MESSAGES[code],
                   run_id=source.run_id if source else None,
                   version_id=source.version_id if source else None,
                   warning_id=source.warning_id if source else None)


def schedule_status(principal, connection):
    """Describe the next daily check and the current blocker from one snapshot.

    The caller supplies the read-only REPEATABLE READ transaction that
    authenticated the request. Settings, lifecycle state and the clock are
    therefore read from one consistent view. Nothing is locked or written.
    """
    from trinity.refresh.repository import read_context
    from trinity.refresh.service import admin_context
    require(principal, "settings:read")
    row = read_settings(connection)
    run, version, warning, approval, step = read_context(connection)
    context = admin_context(row, run, version, warning, approval, step)
    now = database_now(connection)
    blocker = choose_blocker(row, context)
    upcoming = next_check(now, row)
    return ScheduleStatus(
        settings_revision=str(row["revision"]),
        schedule_enabled=row["schedule_enabled"],
        next_check_at=upcoming,
        next_check_local=None if upcoming is None else local_text(upcoming, row["schedule_timezone"]),
        timezone=row["schedule_timezone"],
        evaluated_at=now,
        eligible_now=blocker is None,
        blocker=blocker,
    )
