# Tasks: Schedule settings, initial setup and daily scheduled admission

Date: 2026-10-05
Status: Alayala approved the design and tasks and authorized Step 2 on October 5, 2026. Step 2 code and offline checks are recorded below; one of his two Step 2 explanations is pending. He authorized Step 3 on October 5, 2026 with that explanation still open; Step 3 results are recorded below. He authorized Step 4 on October 5, 2026; Step 4 results are recorded below. He authorized Step 5 on October 5, 2026; it is in progress.
Branch: `feat/schedule-settings`.
Basis: [approved specification](spec.md), [design](design.md), A16/A19, and the [session record](../../ai/sessions/2026-10-05-schedule-settings-specification.md).

## Human

The slice has four implementation steps after ongoing evidence work. Each step needs its own authorization and must pass its checks before the next one starts. Offline tests, real database/HTTP/worker checks and alayala's retained-account check are separate kinds of evidence; one cannot replace another.

| Step | What it delivers | Main risk it closes |
|---|---|---|
| 2 | Pure clock rules and request models | Wrong next time around DST; wrong due window |
| 3 | Save and status routes | Lost updates; stale client gets `200`; setup written twice |
| 4 | Scheduler role and shared run insert | Duplicate or missing scheduled runs; manual Start changed by mistake |
| 5 | Real acceptance and operator check | Offline tests passing while real locks or dispatch fail |

## LLM

### Step 1 — Maintain data evidence — ongoing

- [ ] [YOU] Keep FINDINGS and source values current if later work touches real data. This slice adds no EIA evidence; synthetic schedules and runs are not anomalies.
- [x] [ME] Approved the specification with D01–D03 and requested design and tasks. [YOU] Recorded the decisions under A16/A19 and the API contract, traced settings, refresh admission, migrations, transport and workers, and drafted this plan. This checkbox does not authorize implementation.

### Step 2 — Pure clock rules and request models

Scope: R03–R04, R12–R13, D01 window, R18 key. No route, database or worker change.

- [x] [ME] Authorized Step 2. [YOU] Explained input → flow → output and the March 8 gap failure case before edits.
- [x] [YOU] Add `settings/schedule.py`: `valid_timezone`, `occurrence`, `next_check`, `due_occurrence`, `occurrence_key`, `local_text`.
- [x] [YOU] Add `SettingsRequest` and `ScheduleStatus` to `settings/schemas.py`.
- [x] [YOU] Add `tests/test_schedule_unit.py`: every clock example row (S11), D01 edges, `T ≤ updated_at`, key stability across calls, S03 body cases and S04 timezone cases at the model level.
- [x] [YOU] Follow CONTRIBUTING for comments and docstrings. Run the new tests and the existing auth unit tests. Record counts.
- [x] [ME] Explained the March 8 gap: New York clocks jump from 01:59:59 to 03:00:00, so 02:30 never exists; the scheduler must not invent a 02:30 check or move it to 03:00; the next real check is March 9, 2026 at 02:30 EDT (06:30Z). Correct.
- [ ] [ME] Explain why a no-op save keeps a due occurrence due.

Gate: pure tests pass; [ME] explanation recorded.

Result (October 5): 16 new tests passed. The full offline suite ran 567 tests: all passed, 176 skipped (opt-in PostgreSQL, Docker and live classes). This worktree has no `.venv`; the checks used the Python 3.14.8 environment of the sibling `trinity` worktree with `PYTHONPATH=src`. Its `uv.lock` and `pyproject.toml` are identical to this branch. This is not a fresh locked install. Additions beyond the planned function list: `parse_daily_time` (shared `HH:mm` parser) and `DUE_WINDOW_SECONDS`. `settings/schemas.py` keeps `SettingsResponse` unchanged. The [ME] gap explanation is recorded; the no-op explanation is still open.

### Step 3 — Save and status routes

Scope: R01–R11, R08a, R14–R16, R22–R23.

- [x] [ME] Authorized Step 3. [YOU] Explained input → flow → output and the concurrent-save failure case before edits.
- [x] [YOU] `settings/repository.py`: tighten `read_settings` with `valid_timezone`; add `lock_settings`, `share_settings`, `database_now`, `write_settings`.
- [x] [YOU] `settings/service.py`: `parse_settings_command`, `SettingsService.update` with the design's phases A–H, `schedule_status`, `choose_blocker`, `BLOCKER_MESSAGES`.
- [x] [YOU] `settings/router.py`: PUT and status routes; `main.py`: `settings_service` injection; `errors.py`: `415` for PUT; `tests/test_health.py`: route inventory.
- [x] [YOU] Add `tests/test_settings_service.py` (offline): R07 order with no settings read before phase D, S01, S03, S05, S09, S10, headers and exact OpenAPI shape (S18 offline part).
- [x] [YOU] Add `tests/test_settings_postgres.py` (opt-in, disposable database only): S02, S06, S07, S08, S12, real headers.
- [x] [YOU] Run auth, catalog, refresh and publication regressions. Record skips as pending, never as passes.

Gate: offline tests pass; PostgreSQL tests pass on a disposable database.

Result (October 5): gate passed.

- Offline: 20 new tests in `test_settings_service.py` passed. Full offline suite: 596 ran, all passed, 185 skipped (opt-in classes).
- PostgreSQL 17.11 disposable cluster (`tests/run_local_auth_checks.py`): 99 auth, catalog and settings tests passed, including 9 new `test_settings_postgres.py` tests (S02, S06, S07, S08, S09, S12, R04 corrupt row, S01 denial).
- Refresh and publication regressions (`tests/run_local_refresh_checks.py`, disposable PostgreSQL and Redis 8.10.2 container): 93 ran, all passed, 1 skipped (`test_publication_runtime`: query image not built). The skip is pending, not a pass.
- Environment: the sibling `trinity` worktree's Python 3.14.8 environment with `PYTHONPATH=src`; lock files identical. Not a fresh locked install.

Scope correction: `tests/run_local_auth_checks.py` now also discovers `test_settings*.py`, so the new PostgreSQL tests run in the existing disposable runner. This file was not in the design list. No other file outside the design list changed.

### Step 4 — Scheduler role and shared run insert

Scope: R17–R21, D03.

- [x] [ME] Authorized Step 4 ("complete task 4 for the acceptance"). [YOU] Explained input → flow → output and the commit-failure case before edits.
- [x] [YOU] `refresh/repository.py`: extract `_insert_run` and `POLICY`; keep `accept_run` SQL and results unchanged; add `accept_scheduled_run`.
- [x] [YOU] Add `workers/scheduler.py` (`SchedulerService.once`, `run`) and the `scheduler` role in `workers/__main__.py`, handled before any queue, EIA or S3 setting is read.
- [x] [YOU] Add `tests/test_scheduler_postgres.py`: S13 with a test clock, S14 (two scheduler processes plus manual Start), S15 commit fault, S17 logs and secret-free start.
- [x] [YOU] Run the existing refresh admission and dispatch tests to prove manual Start is unchanged.

Gate: scheduler tests and refresh regressions pass on disposable services.

Result (October 5): gate passed.

- `tests/run_local_refresh_checks.py` (disposable PostgreSQL 17.11 and Redis 8.10.2 container): 112 ran, all passed, 1 skipped (`test_publication_runtime`: query image not built; pending, not a pass). This includes the 19 new scheduler tests and the unchanged refresh admission (8) and dispatch (4) tests, so manual Start behavior is unchanged.
- `tests/test_scheduler_postgres.py`, 15 tests: every scheduler example row (S13) with a test clock; the D02 no-op save through real HTTP; a save committed between the check and the locks (`changed`); a PUT that waits for the admission share lock and cannot change the run's revision; insert and deferred-commit faults leave no run, slot or outbox row, then one retry admits (S15); two scheduler processes plus manual Start, three attempts (S14). Winners: manual, manual, scheduler (the third attempt delays manual Start by 0.5 seconds so that the scheduler-wins branch runs). The real worker process with the PostgreSQL clock and only `TRINITY_DATABASE_URL` admits one `scheduled` run and logs one fixed-field line (S17).
- `tests/test_scheduler_unit.py`, 4 offline tests: fixed log fields; exception text with a synthetic password never reaches the log; the role starts with only an unreachable database URL, logs `reason=dependency_unavailable`, hides the URL and stops with exit code 0 on SIGTERM (S17).
- Full offline suite: 615 ran, all passed, 200 skipped (opt-in classes). `tests/run_local_auth_checks.py`: 99 passed.
- Environment: same borrowed Python 3.14.8 environment as Steps 2–3.

Scope corrections:

- `tests/test_scheduler_unit.py` was not in the design list. It gives the offline (O) evidence that S15/S17 require.
- `tests/run_local_sql_checks.py --refresh` now also discovers `test_scheduler*.py`, so the scheduler tests run with the refresh regressions.
- Added `refresh/repository.py:find_run_by_key` for scheduler step 3.
- Design correction: the documented limit (a manual `Idempotency-Key` equal to a future occurrence key) gives outcome `duplicate`, not `error`. Scheduler step 3 finds the manual run before the insert. The occurrence is still skipped. Test: `test_manual_key_equal_to_occurrence_key_is_skipped_as_duplicate`.
- Idle polls are logged at DEBUG only; admitted and skipped occurrences are logged at INFO and errors at WARNING (R21).

Understanding check (observed): [ME] Alayala explained that the 06:15 occurrence was skipped while the failed run held the slot, that Trinity does not queue missed occurrences, and that resolving the failure at 09:00 only makes later occurrences eligible. Correct. [YOU] Added one detail: the scheduler keeps no skip record. At 09:00, 06:15 is outside its 300-second window, so `due_occurrence` returns None. The result is the same if the scheduler never evaluated 06:15.

### Step 5 — Real acceptance and operator check

Scope: R24, S16, S19, S20.

- [x] [ME] Authorized Step 5 ("continue with step 5").
- [x] [YOU] S16: a scheduled run's outbox row is dispatched by the existing outbox worker to a disposable Redis (`tests/run_local_refresh_checks.py`). No EIA call.
- [x] [YOU] S19: in the built API image, `ZoneInfo('America/New_York')` and `ZoneInfo('America/Merida')` load and `available_timezones()` is not empty.
- [x] [YOU] S20 preparation: [ME] alayala approved a `--schedule HH:MM TIMEZONE` mode for `trinity.auth.check` (not in the design list). It denies Viewer/Analyst save and status, saves an enabled schedule as Admin with the current ETag, checks the stale ETag gets `412`, reads the status, and confirms the run history did not change. It prints only revisions, the next check time, the blocker code and the run count. Tests: 4 offline (`test_settings_service.OperatorScheduleCheckTests`) and 2 real HTTP (`test_settings_postgres`: head schema, and a separate disposable database at `0002_app_entry` like the retained one). Results: offline 623 ran, all passed, 203 skipped; auth/catalog/settings runner 105 passed.
- [x] [ME] S20: sign in as the retained Admin, save a schedule, read the status, confirm no run started. Scheduled dispatch against retained data is a separate operator gate.

S20 result (October 5): [ME] Alayala first rotated the retained persona passwords ([rotation session](../../ai/sessions/2026-10-05-retained-persona-password-rotation.md)), then ran `trinity.auth.check --base-url http://127.0.0.1:8001 --schedule 06:15 America/New_York` against this branch's API on the retained Compose database (migration `0002_app_entry`). Reported line: `admin schedule: revision 0->1; next check 2026-10-06T06:15:00-04:00; blocker none; refresh runs unchanged (0)`. [YOU] Read-only database check afterwards: `shared_settings` revision 1, enabled, `06:15`, `America/New_York`, setup time equal to update time, saved by the admin user; `refresh_runs` 0; `refresh_control`, `active_publication` and `alembic_version` unchanged. No scheduler process ran, and that database has no `job_outbox` table.
- [x] [YOU] Write the implementation evidence note ([evidence](../../ai/sessions/2026-10-05-schedule-settings-implementation.md)); update NOTES (human and AI contributions) and this file with measured results.

Gate: all automated evidence recorded; [ME] check recorded. This does not prove retained scheduled refresh readiness.

S16 result (October 5): `SchedulerDispatchTests.test_scheduled_run_is_dispatched_by_the_existing_outbox_worker` passed through `tests/run_local_refresh_checks.py --pattern test_scheduler_postgres.py` (16 ran, all passed). The scheduler admitted a run; the existing `workers/outbox.run` loop with `DispatchService` delivered it; the BullMQ job `refresh-<run_id>-0` waited in a disposable Redis queue with the outbox payload. No consumer ran, so no EIA call; the run stayed `requested`.

S19 result (October 5): image `trinity-api:schedule-settings-check` (`sha256:317c03c0…`, built from the working tree on HEAD `8746bb8`), run with `--network none`. Python 3.14.8; `available_timezones()` has 599 names; `America/New_York`, `America/Merida` and `UTC` load and pass `valid_timezone`; `america/new_york`, `posix/America/New_York` and `/etc/localtime` are rejected. **Defect: `localtime` is in the image's `available_timezones()` and `valid_timezone('localtime')` returns True.** In the image, `/usr/share/zoneinfo/localtime` links to `/etc/localtime`, so its meaning depends on the container configuration. R04 requires rejection. macOS (598 names) does not list it, so Step 2 tests did not expose it.

S19 fix and recheck (October 5): [ME] Alayala approved one explicit guard and one test. [YOU] `settings/schedule.py:valid_timezone` now rejects the exact name `localtime` before the known-set check. `test_schedule_unit.TimezoneTests.test_localtime_is_rejected_when_the_runtime_lists_it` adds `localtime` to the known set and makes `ZoneInfo` load it, as in the image. The test fails on a temporary copy without the guard (`AssertionError: True is not false`) and passes with it. Focused tests: `test_schedule_unit.py` 17 passed, `test_settings_service.py` 20 passed. Rebuilt image `sha256:3fe881b5…` (`--network none`): `localtime` is still listed (599 names) but `valid_timezone` and `SettingsRequest` reject it; `America/New_York`, `America/Merida` and `UTC` pass; `next_check` for 08:00 `America/Merida` gives `2026-10-06T08:00:00-06:00`. S19 passed.

Regression after the fix: full offline 617 ran, all passed, 201 skipped (the new S16 test is one of the skipped opt-in tests); auth/catalog/settings runner 99 passed; refresh runner 113 ran, all passed, 1 skipped (`test_publication_runtime`: query image not built; pending). S14 winners: manual, manual, scheduler.

## Review gate

Done: Steps 1–5. S20 passed on the retained database.
Pending: [ME] the Step 2 no-op explanation (understanding check only; not a code gate).
Blocker: none.
Next: [ME] commit and integration decision.
