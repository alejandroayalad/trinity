"""Turn a due daily-schedule occurrence into one scheduled refresh run.

The `scheduler` worker role calls SchedulerService.once() every 15 seconds.
Each call reads the shared settings row and the PostgreSQL time. When an
occurrence T is due (settings.schedule.due_occurrence), one write
transaction admits it:

1. Lock `refresh_control`, then take the settings row FOR SHARE. This is
   the same lock order as manual Start, so the two cannot deadlock.
2. Read settings and the time again. Skip with outcome `changed` when the
   revision changed or T is no longer due.
3. Derive the run key from (revision, T). Skip with outcome `duplicate`
   when a run with that key exists.
4. Read the lifecycle context. Skip with outcome `blocked` when a run
   holds the slot or a failure is unresolved.
5. Insert the run, slot and outbox row with the code that manual Start
   uses. The outcome is `admitted` only after the commit.

A skip writes nothing, and no skip is retried later. The next poll can see
the same T again only while T is still inside its 300-second window; the
run key then prevents a second run.

This role reads only TRINITY_DATABASE_URL. It loads no EIA key, no S3
credential and no Redis URL. The existing outbox worker dispatches the
admitted run to the refresh queue later.

Each outcome is one log line with fixed fields: outcome, revision,
occurrence and, when present, the blocker code and run ID. Exception text
is never logged, because a database error can contain the database URL.
"""
import asyncio
from dataclasses import dataclass
from datetime import datetime
import logging
import sys
from uuid import UUID

from trinity.adapters.postgres import Deadline
from trinity.errors import Problem
from trinity.refresh import repository as refresh_repository
from trinity.refresh.service import admin_context
from trinity.settings.repository import database_now, read_settings, share_settings
from trinity.settings.schedule import DUE_WINDOW_SECONDS, due_occurrence, occurrence_key

LOG = logging.getLogger("trinity.scheduler")

# D03 requires an evaluation at least every 30 seconds. 15 seconds keeps
# every occurrence well inside its 300-second window, even after one
# failed poll.
POLL_SECONDS = 15


@dataclass(frozen=True)
class Outcome:
    """Describe the result of one evaluation without any setting secret.

    code: idle, changed, duplicate, blocked, admitted or error.
    revision and occurrence identify the occurrence when one was due.
    reason is a fixed code: the lifecycle blocker for `blocked`, or the
    Problem code for `error`. run_id is the admitted or existing run.
    """
    code: str
    revision: int | None = None
    occurrence: datetime | None = None
    reason: str | None = None
    run_id: UUID | None = None


class SchedulerService:
    """Evaluate the saved schedule against the PostgreSQL clock.

    clock receives the open connection and returns an aware datetime.
    Production uses database_now (clock_timestamp()). Tests pass a function
    that returns fixed instants; there is no other clock override.
    """

    def __init__(self, database, *, clock=database_now, window=DUE_WINDOW_SECONDS):
        self.database = database
        self.clock = clock
        self.window = window

    def once(self) -> Outcome:
        """Evaluate once and return the outcome after any commit.

        Raise Problem(503) when PostgreSQL fails or the stored state is
        corrupt. The caller logs that as outcome `error`. A failure at any
        point rolls back the whole admission, so no run, slot or outbox row
        remains from this call.
        """
        # Step 0: a read-only check. It takes no lock, so the frequent idle
        # polls never wait for, or delay, manual Start or a settings save.
        with self.database.transaction(Deadline(), readonly=True, error_code="dependency_unavailable") as connection:
            row = read_settings(connection)
            due = due_occurrence(self.clock(connection), row, self.window)
        if due is None:
            return Outcome("idle")

        with self.database.transaction(Deadline(), error_code="dependency_unavailable") as connection:
            # Step 1: the lock order is refresh_control, then settings.
            # PUT /settings waits on the share lock until this commit, so the
            # revision read below cannot change before the run is inserted.
            refresh_repository.lock_control(connection)
            current = share_settings(connection)
            # Step 2: a save can commit between step 0 and the locks. Check
            # again with a new time: the same revision must still make the
            # same T due. Otherwise skip; the next poll uses the new values.
            again = due_occurrence(self.clock(connection), current, self.window)
            if current["revision"] != row["revision"] or again != due:
                result = Outcome("changed", current["revision"], due)
            else:
                # Step 3: the same (revision, T) gives the same key in every
                # process. A run with this key means that another scheduler,
                # or this one before a restart, already admitted T.
                key = occurrence_key(current["revision"], due)
                existing = refresh_repository.find_run_by_key(connection, key)
                if existing is not None:
                    result = Outcome("duplicate", current["revision"], due, run_id=existing)
                else:
                    # Step 4: the same lifecycle rules as manual Start. A
                    # blocked occurrence is skipped and never retried later.
                    context = admin_context(current, *refresh_repository.read_context(connection))
                    if context.refresh_blocker is not None:
                        result = Outcome("blocked", current["revision"], due,
                                         reason=context.refresh_blocker.code)
                    else:
                        # Step 5: run, slot and outbox row in this transaction.
                        run = refresh_repository.accept_scheduled_run(connection, key, current)
                        result = Outcome("admitted", current["revision"], due, run_id=run["id"])
        # The commit happens when the block above exits. Return only after it,
        # so `admitted` is never reported for a rolled-back run.
        return result


def log_outcome(outcome: Outcome) -> None:
    """Write one key=value line with fixed fields; never exception text.

    Idle polls are logged at DEBUG only, so the default log shows one line
    per due occurrence instead of one line every 15 seconds.
    """
    stamp = outcome.occurrence.strftime("%Y-%m-%dT%H:%M:%SZ") if outcome.occurrence else "-"
    level = logging.DEBUG if outcome.code == "idle" else logging.WARNING if outcome.code == "error" else logging.INFO
    LOG.log(level, "scheduler outcome=%s revision=%s occurrence=%s reason=%s run_id=%s",
            outcome.code, "-" if outcome.revision is None else outcome.revision, stamp,
            outcome.reason or "-", outcome.run_id or "-")


def configure_logging() -> None:
    """Send scheduler lines to stderr without changing other loggers.

    Python shows only WARNING and above by default. The scheduler logger gets
    its own INFO handler and does not pass records to the root logger, so
    library loggers keep their existing filters and levels.
    """
    if not LOG.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False


async def run(service, stop, interval=POLL_SECONDS):
    """Evaluate every interval seconds until stop is set.

    once() uses blocking database calls, so it runs in a worker thread. The
    stop signal then stays responsive. An exception becomes outcome `error`
    with a fixed reason code. The loop continues; the next poll can still
    admit an occurrence that is inside its window.
    """
    while not stop.is_set():
        try:
            outcome = await asyncio.to_thread(service.once)
        except Problem as error:
            outcome = Outcome("error", reason=error.code)
        except Exception:
            # Never log the exception: database URLs can contain credentials.
            outcome = Outcome("error", reason="unexpected")
        log_outcome(outcome)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
