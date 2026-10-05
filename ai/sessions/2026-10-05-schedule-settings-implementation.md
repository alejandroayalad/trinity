# Schedule settings — implementation evidence

Date: 2026-10-05
Branch: `feat/schedule-settings` (worktree `trinity-schedule-settings`), HEAD `8746bb8` plus uncommitted work. Nothing is committed.
Plan: [spec](../../sdd/schedule-settings/spec.md), [design](../../sdd/schedule-settings/design.md), [tasks](../../sdd/schedule-settings/tasks.md). Decisions D01–D03 under A16/A19 in [DECISIONS.md](../../DECISIONS.md). Planning history: [specification session](2026-10-05-schedule-settings-specification.md).

## What exists now

| Part | Files (under `backend/src/trinity/`) |
|---|---|
| Clock rules (pure) | `settings/schedule.py` |
| `PUT /api/v1/settings`, `GET /api/v1/settings/schedule-status` | `settings/{schemas,repository,service,router}.py`, `main.py`, `errors.py` (`415` for PUT) |
| Shared run insert | `refresh/repository.py` (`POLICY`, `_insert_run`, `accept_run`, `accept_scheduled_run`, `find_run_by_key`) |
| `scheduler` worker role | `workers/scheduler.py`, `workers/__main__.py` |

No migration and no new dependency. Docker Compose has no scheduler service; the role is started with `python -m trinity.workers scheduler`.

## Human and AI contributions

- [ME] Alayala approved the spec, design and tasks; chose D01–D03 (D02 against the AI recommendation); authorized Steps 2–5 one at a time; approved the `localtime` guard; gave the Step 4 understanding check (correct).
- [YOU] Claude (OpenCode) wrote the code and tests, ran every check below and found the `localtime` defect during S19 and the design correction in Step 4.

## Checks and results

All database and queue checks used disposable services: a PostgreSQL 17.11 cluster on a private Unix socket and a Redis 8.10.2 container. Python: the sibling `trinity` worktree's CPython 3.14.8 environment with `PYTHONPATH=src`; lock files identical, not a fresh locked install.

| Check | Command (from `backend/`) | Result |
|---|---|---|
| Full offline suite | `python -m unittest discover -s tests -p 'test_*.py'` | 623 ran, all passed, 203 skipped (opt-in) |
| Auth, catalog, settings on PostgreSQL | `python tests/run_local_auth_checks.py` | 105 passed (includes the `--schedule` checker over real HTTP, also on a database at `0002_app_entry`) |
| Refresh, scheduler, publication on PostgreSQL and Redis | `python tests/run_local_refresh_checks.py` | 113 ran, all passed, 1 skipped (run before the `--schedule` checker change, which the refresh runner does not exercise) |
| API image timezones (S19) | `docker build -t trinity-api:schedule-settings-check backend`, then `docker run --rm --network none --entrypoint python …` | Passed after the `localtime` fix |

Scenario coverage: S01–S12, S18 in `test_schedule_unit.py`, `test_settings_service.py`, `test_settings_postgres.py`; S13–S15, S17 in `test_scheduler_postgres.py` and `test_scheduler_unit.py`; S16 in `test_scheduler_postgres.SchedulerDispatchTests`; S19 in the image. Details and counts per step are in the [tasks](../../sdd/schedule-settings/tasks.md).

## Corrections found during implementation

- Design: a manual `Idempotency-Key` equal to a future occurrence key makes the scheduler return `duplicate`, not `error`. The occurrence is still skipped.
- Defect (fixed): the Linux image lists `localtime` in `available_timezones()`, so `valid_timezone` accepted it. An explicit guard now rejects it; a test reproduces the image's list.
- Scope: added the `--schedule` mode to `trinity.auth.check` for S20 (approved by alayala).
- Scope: added `tests/test_scheduler_unit.py`, runner patterns in `run_local_auth_checks.py` and `run_local_sql_checks.py --refresh`, and `find_run_by_key`. Not in the design file list.

## Retained check (S20)

Passed on October 5 after the [password rotation](2026-10-05-retained-persona-password-rotation.md): revision 0 → 1, next check `2026-10-06T06:15:00-04:00`, no blocker, refresh runs unchanged (0). Details in the [tasks](../../sdd/schedule-settings/tasks.md).

## Not proven

- `test_publication_runtime` was skipped: the query image was not built.
- Scheduled dispatch against retained data, a running scheduler service in Compose, and a real EIA refresh started by the schedule are outside this slice.
- The retained Compose database is at migration `0002_app_entry` (observed read-only on October 5). It has no `job_outbox` table, so a scheduled admission cannot run there until it is migrated. Migrating it is a separate operator decision.
