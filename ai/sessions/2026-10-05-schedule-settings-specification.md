# Schedule settings: specification, design and tasks

Date: 2026-10-05
Branch: `feat/schedule-settings` (worktree `trinity-schedule-settings`), based on `8746bb8`.

## Objective

Complete the Schedule settings proposal on its own branch: specification first, then design and tasks. Planning only; no implementation authorized.

## Human and AI contributions

[ME] Alayala rejected merging `frontend` into the proposal branches. He asked to complete each of the three idle proposals in its own branch, starting with Schedule settings and its specification.

[YOU] Claude (OpenCode) created the worktree, traced `settings/`, `refresh/service.py:RefreshService.start`, `admin_context`, `refresh/repository.py:accept_run`, migrations `0002` and `0006`, `errors.py:SafeTransport` and `workers/`, and drafted the [specification](../../sdd/schedule-settings/spec.md) with D01–D03.

[ME] Accepted D01 (300-second due window; occurrence must be after the last effective save).

[ME] Rejected the AI recommendation for D02 (new revision on every save). He chose the no-op rule: identical values return the current settings and revision with no write and no change to the save time used by the scheduler. He also set the order: check `If-Match`, `412` if stale, then compare values, then return the current record or write the next revision. His reason: otherwise a stale client could receive `200`, which weakens optimistic concurrency. He agreed that a no-op save cannot occur before setup.

[ME] Accepted D03 (PostgreSQL clock as the only clock; separate `scheduler` role every ≤ 30 seconds without EIA, S3 or Redis secrets). Then he asked to record the decisions and start design and tasks.

[YOU] Recorded D01–D03 under A16, the scheduler secret boundary under A19, and a refinement note in the API contract. Drafted the [design](../../sdd/schedule-settings/design.md) and [tasks](../../sdd/schedule-settings/tasks.md).

## Corrections and evidence

- The unmerged `frontend` branch (`0ee652d`) already contains an AI-authored implementation of these routes. The specification does not adopt its choices; it was not merged, by alayala's decision.
- Local macOS check: `ZoneInfo('america/new_york')` loads, but `zoneinfo.available_timezones()` (598 names) does not contain it. The current `read_settings` would accept the case variant. Linux image not checked.
- Clock example rows were computed with local Python `zoneinfo`. They are examples, not runtime evidence.
- `api_commands.actor_id` is `NOT NULL`, so scheduled runs have no receipt. The unique `refresh_runs.request_key` can enforce occurrence identity without a migration.
- `SafeTransport` checks `Content-Type` only for POST; the design adds PUT.

## Checks

Document consistency and local links reviewed. No backend code or tests were changed or run.

## Open questions

Compose wiring for worker roles, including `scheduler`, is outside this slice.

## Next action

[ME] Review the design and tasks; authorize Step 2 if accepted.

## Step 2 — pure clock rules (implementation)

[ME] Alayala approved the design and tasks and authorized Step 2. [YOU] Claude (OpenCode) explained the input, flow, output and the March 8 gap failure case before edits. Then it added `backend/src/trinity/settings/schedule.py` (`valid_timezone`, `parse_daily_time`, `occurrence`, `next_check`, `due_occurrence`, `occurrence_key`, `local_text`), added `SettingsRequest` and `ScheduleStatus` to `settings/schemas.py` (with `SettingsResponse` unchanged) and added `backend/tests/test_schedule_unit.py`.

Checks: 16 new tests passed. The full offline suite ran 567 tests: all passed, 176 skipped. The checks used the sibling `trinity` worktree's Python 3.14.8 environment with `PYTHONPATH=src`, because this worktree has no `.venv`. Its `uv.lock` and `pyproject.toml` are identical to this branch's. No route, database or worker code changed.

[ME] Explained the March 8 gap in his own words: clocks jump from 01:59:59 to 03:00:00, 02:30 never exists, the scheduler must not invent a 02:30 check or move it to 03:00, and the next real check is March 9, 2026 at 02:30 EDT. [YOU] Confirmed it matches the tested rule (`occurrence` returns None; `next_check` returns 2026-03-09T06:30:00Z).

Pending: [ME] explanation of why a no-op save keeps a due occurrence due.

## Step 3 — save and status routes (implementation)

[ME] Alayala authorized Step 3 without first giving the second Step 2 explanation; it stays open in the tasks. [YOU] Claude (OpenCode) explained the input, flow, output and the concurrent-save failure case before edits.

[YOU] Changed `settings/repository.py` (exact-name timezone check in `read_settings`; `lock_settings`, `share_settings`, `database_now`, `write_settings`), `settings/service.py` (`parse_settings_command`, `SettingsService.update`, `choose_blocker`, `BLOCKER_MESSAGES`, `schedule_status`), `settings/router.py` (PUT and status routes), `main.py` (`settings_service` injection), `errors.py` (`415` check for PUT), `tests/test_health.py` (route inventory) and `tests/run_local_auth_checks.py` (discovers `test_settings*.py`). Added `tests/test_settings_service.py` and `tests/test_settings_postgres.py`.

Checks: full offline 596 ran, all passed, 185 skipped. Disposable PostgreSQL 17.11: 99 auth/catalog/settings tests passed. Refresh and publication with a disposable Redis container: 93 ran, all passed, 1 skipped (query image not built). Same environment note as Step 2.

Pending: [ME] the Step 2 no-op explanation; Step 4 authorization.

## Step 4 — scheduler role and shared run insert (implementation)

[ME] Alayala authorized Step 4 ("complete task 4 for the acceptance please and handoff to me"). [YOU] Claude (OpenCode) explained the input, flow, output and the commit-failure case before edits.

[YOU] Changed `refresh/repository.py` (`POLICY`, `_insert_run`, `accept_run` now calls it, `accept_scheduled_run`, `find_run_by_key`) and `workers/__main__.py` (`scheduler` role, handled before any Redis, EIA or S3 setting). Added `workers/scheduler.py` (`SchedulerService.once`, `run`, `log_outcome`, `configure_logging`), `tests/test_scheduler_postgres.py` and `tests/test_scheduler_unit.py`. `tests/run_local_sql_checks.py --refresh` now discovers `test_scheduler*.py`.

Checks: refresh runner 112 ran, all passed, 1 skipped (query image). Auth runner 99 passed. Full offline 615 ran, all passed, 200 skipped. S14 winners over three attempts: manual, manual, scheduler.

Correction: the design's known limit said a colliding manual key makes the scheduled insert fail with `error`. Observed: step 3 finds the manual run first and returns `duplicate`. Design text corrected; the occurrence is still skipped.

Pending: [ME] the Step 2 no-op explanation; [ME] a Step 4 understanding check; Step 5 authorization.

## Step 5 — acceptance (in progress)

[ME] Alayala gave the Step 4 understanding check (correct; recorded in tasks) and authorized Step 5. [YOU] S16 passed. S19 found the `localtime` defect in the Linux image; [ME] he approved one explicit guard and one test; [YOU] added them, proved the test fails without the guard, rebuilt the image and S19 passed. Regression after the fix: offline 617/201 skipped, auth 99, refresh 113/1 skipped. Evidence note: [implementation evidence](2026-10-05-schedule-settings-implementation.md). [YOU] Read-only observation: the retained Compose database is at migration `0002_app_entry`, settings not set up, no runs.

[ME] S20 passed after the retained password rotation; see the [tasks](../../sdd/schedule-settings/tasks.md).

Pending: [ME] the Step 2 no-op explanation.
