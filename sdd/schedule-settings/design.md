# Design: Schedule settings, initial setup and daily scheduled admission

Date: 2026-10-05
Status: Approved by alayala on October 5, 2026, when he authorized Step 2. Only Step 2 is authorized; see [tasks](tasks.md). Runtime activation is not authorized.
Branch: `feat/schedule-settings`; inspected HEAD `8746bb8`.
Basis: [approved specification](spec.md) (R01–R24, R08a, D01–D03), A15/A16/A19/A20/A23 in [DECISIONS.md](../../DECISIONS.md), [backend structure](../../docs/backend.md#scheduling-dispatch-and-recovery), [API contract](../../docs/api-contract.md#setup-and-daily-schedule) and [schema](../../docs/schema.md).
Evidence: [specification session](../../ai/sessions/2026-10-05-schedule-settings-specification.md).

## Human

### What will change

The existing `settings/` feature gets a save route, a status route and one pure module for clock rules. A new `workers/scheduler.py` role turns a due occurrence into a scheduled run. Manual Start and the scheduler use the same run-insert code in `refresh/repository.py`, so both create the same run, slot and outbox row. No migration and no new dependency.

Input → flow → output (save): `PUT /api/v1/settings` with `If-Match: "settings-4"` and a body → check session and `settings:write` → check `If-Match` shape → parse the body → lock the user and session, then the settings row → stale tag gives `412` → identical values return the current row → otherwise update the row with the PostgreSQL time → `200` with the new `ETag`.

Input → flow → output (scheduler): every 15 seconds → read settings and the database time → if an occurrence is due, lock `refresh_control`, then settings → recheck everything → derive the run key from (revision, `T`) → insert one `scheduled` run, slot and outbox row, or skip → log the outcome code.

Example: settings revision `4`, `06:15`, `America/New_York`. At 10:15:12Z the scheduler sees `T = 10:15:00Z` due. Its key is the same UUID for every process, so a second scheduler finds the run and skips.

Failure: an Admin presses Start at 10:15:05Z. The manual run holds the slot. At 10:15:12Z the scheduler takes the lock, sees `refresh_active` and writes nothing. It does not retry this occurrence later.

### Delivery boundary

- No migration. The existing unique `refresh_runs.request_key` enforces the occurrence identity (R18).
- No dependency. Standard-library `zoneinfo`, `uuid` and `logging` only.
- `errors.py:SafeTransport` gets one necessary change: the `415` media-type check covers PUT as well as POST.
- Docker Compose has no worker services on this branch. Adding the `scheduler` service to Compose is outside this slice; the role is run with the existing worker command.
- The frontend Schedule page is outside this slice.

## LLM

### Inspected baseline

Paths are relative to `backend/src/trinity/`.

| Component | Observed behavior and use |
|---|---|
| `settings/router.py`, `settings/service.py:get_settings`, `settings/repository.py:read_settings` | GET only, through `require_capability("settings:read")`. `read_settings` returns `503` for a missing row and checks the stored timezone with `ZoneInfo(...)`, which accepts case variants on macOS (spec R04 evidence). |
| `auth/service.py:AuthService.authenticated` | Opens one read-only `REPEATABLE READ` transaction for identity and app-state reads. The status route uses this snapshot. |
| `refresh/service.py:RefreshService.start` | Order: unlocked authorize → parse → `lock_control` → locked authorize (`local_users FOR SHARE`, session lock) → receipt replay → `shared_settings FOR SHARE` → `read_context` → `admin_context` → `accept_run`. |
| `refresh/service.py:admin_context` | Returns the lifecycle blocker code and holder IDs. `publication_failed` maps to `failure_unresolved`. It has no `schedule_disabled` code. Not changed. |
| `refresh/repository.py:accept_run` | Inserts the run with hard-coded `trigger_kind='manual'`, moves the slot, inserts the outbox row and the `api_commands` receipt. `request_key` is the client `Idempotency-Key`. |
| `migrations/versions/0002_app_entry.py` | `shared_settings` CHECK: before setup all null and disabled; after setup time, timezone and actor are required. `refresh_runs` CHECK: `scheduled` ⇔ `requested_by IS NULL`. `request_key uuid NOT NULL UNIQUE`. |
| `migrations/versions/0006_refresh_dispatch.py` | `api_commands.actor_id NOT NULL`, so a scheduled run cannot have a receipt (spec R17). |
| `adapters/postgres.py:Database` | Session `timezone=UTC`; `transaction(Deadline, readonly=…)` sets statement, lock and transaction timeouts and maps database errors to `503`. |
| `errors.py:SafeTransport` | Buffers at most 64 KiB (`413`). Rejects any query string and any GET body for routes other than preview and refresh reads (`422`), before authentication. Checks `Content-Type` only for POST. |
| `workers/__main__.py`, `workers/outbox.py` | Fixed role list; every non-publication role creates `RefreshQueue(TRINITY_REDIS_URL)` before branching. `outbox.run` loops with a 1-second wait and swallows exceptions without logging their text. |
| `catalog/schemas.py:utc_timestamp` | Existing helper that normalizes datetimes to UTC. Reused for new timestamp fields. |

### Component responsibilities

| File | Planned responsibility |
|---|---|
| `settings/schedule.py` — new, pure | `valid_timezone(name)`: exact member of a cached `zoneinfo.available_timezones()` and loadable. `occurrence(day, daily_time, zone)`: `None` for a gap, first instant (`fold=0`) for a fold. `next_check(now, row)`: first occurrence strictly after `now`, or `None` when not set up or disabled. `due_occurrence(now, row, window=300)`: the single `T` with `T ≤ now < T + window` and `T > row.updated_at`, or `None`. `occurrence_key(revision, instant)`: `uuid5(SCHEDULE_NAMESPACE, f"scheduled:{revision}:{instant:%Y-%m-%dT%H:%M:%SZ}")`. `local_text(instant, zone)`: RFC 3339 with offset and seconds. |
| `settings/schemas.py` | Add `SettingsRequest` (strict: bool, `HH:mm` pattern, timezone 1–100 plus `valid_timezone`) and `ScheduleStatus`. Reuse `auth.schemas.Blocker`. Normalize timestamps with `utc_timestamp`. |
| `settings/repository.py` | `read_settings` uses `valid_timezone` (R04). Add `lock_settings(connection)` (`FOR UPDATE`), `share_settings(connection)` (`FOR SHARE`), `database_now(connection)` (`SELECT clock_timestamp()`), `write_settings(connection, values, actor_id, now)` (one UPDATE: values, `revision = revision + 1`, `updated_at = now`, `updated_by = actor`, `setup_completed_at = COALESCE(setup_completed_at, now)`, `RETURNING *`). |
| `settings/service.py` | Keep `get_settings`. Add `parse_settings_command(raw, if_match, pairs)`, `SettingsService.update(token, raw, if_match, pairs)`, `schedule_status(principal, connection)`, `choose_blocker(row, context)` and `BLOCKER_MESSAGES` (spec table). |
| `settings/router.py` | Add `PUT /settings` (raw body, `request.headers.getlist('if-match')`, query pairs, `run_in_threadpool`, set `ETag`) and `GET /settings/schedule-status` (`require_capability("settings:read")`). Settings service injectable through `app.state`, like `refresh_service`. |
| `refresh/repository.py` | Move the run, slot and outbox inserts from `accept_run` into a private `_insert_run(connection, trigger_kind, actor_id, request_key, settings)`. `accept_run` calls it with `'manual'` and then writes its receipt, with unchanged SQL and results. Add `accept_scheduled_run(connection, request_key, settings)` that calls it with `'scheduled'`, `None`, and writes no receipt. One `POLICY` constant serves both. |
| `workers/scheduler.py` — new | `SchedulerService(database, clock=database_now, window=300)` with `once() -> outcome`; `run(service, stop, interval=15)` loop modeled on `outbox.run`. |
| `workers/__main__.py` | Add `scheduler` to the role list. Handle it before any queue, EIA or S3 setting is read: open only `Database(load_api_settings())`. |
| `main.py` | Register the extended settings router; add `settings_service=None` to `create_app` and store it in `app.state`. |
| `errors.py` | Apply the `415` check to PUT. |
| `tests/test_health.py` | Add the two routes to the exact route inventory. |

Dependency direction: `workers/scheduler.py` imports `settings/` and `refresh/`; `settings/service.py` imports `refresh.service.admin_context`, `refresh.service._authorize` and `refresh.repository.read_context`. `refresh/` does not import `settings/service.py`. `_authorize` is reused as it is; it is not copied.

### PUT flow and transaction

| Phase | Work | Result on failure |
|---|---|---|
| T — transport | `SafeTransport`: size, query string, PUT `Content-Type`. | `413`, `422`, `415` |
| A — identity | One write transaction (`Deadline()`): `_authorize(connection, token, 'settings:write')`. | `401`/`403`; no settings read |
| B — precondition | `if_match` list empty → `428`. Not exactly one value matching `^"settings-(0\|[1-9][0-9]*)"$` → `422`. | No state read |
| C — body | `json.loads` → `400 invalid_json`; `SettingsRequest.model_validate` → `422`. | No state read |
| D — locks | `_authorize(..., lock=True)` (user `FOR SHARE`, session lock), then `lock_settings` (`FOR UPDATE`). | `503` on lock timeout |
| E — revision | Tag revision ≠ row revision → `412 revision_mismatch`. | Nothing written |
| F — no-op | `row.schedule_enabled == body.schedule_enabled and row.daily_time == body.daily_time and row.schedule_timezone == body.timezone` → return the current row (R08a). Before setup the stored time is null, so this cannot match. | — |
| G — write | `now = database_now(connection)`; `write_settings(...)`. | Rollback; nothing written |
| H — respond | Build `SettingsResponse` after the transaction exits, then set `ETag`. A commit failure maps to `503` and nothing is returned. | `503` |

Lock order across writers, with no cycle:

| Writer | Order |
|---|---|
| Manual Start | `refresh_control` → `local_users` (share) and session → `shared_settings` (share) |
| Scheduler | `refresh_control` → `shared_settings` (share) |
| PUT settings | `local_users` (share) and session → `shared_settings` (update) |

PUT never waits for `refresh_control`, and no writer that holds `refresh_control` waits for anything PUT holds except the settings row. Share locks on `local_users` do not conflict. The settings `FOR UPDATE` serializes PUT against the share lock held by Start and the scheduler. A PUT that commits during an admission waits or goes after it. The admission therefore always freezes one consistent revision.

### Status flow

Uses the auth snapshot (`REPEATABLE READ READ ONLY`): `read_settings` → `read_context` (existing `503` rules) → `admin_context` → `database_now` → `next_check` and `choose_blocker`. `choose_blocker`: not set up → `setup_required`; disabled → `schedule_disabled`; otherwise the code from `admin_context.refresh_blocker`, with its IDs. The message comes from `BLOCKER_MESSAGES`, not from `admin_context`. `eligible_now = blocker is None`. A query string or GET body is already rejected by `SafeTransport` (R05). Nothing is written or locked.

### Scheduler flow

`once()`:

1. Read-only transaction: `read_settings`, `now = clock(connection)`, `T = due_occurrence(now, row)`. No `T` → outcome `idle`. This step takes no lock, so idle polling does not contend with Start.
2. Write transaction: `lock_control` → `share_settings` → `read_settings` again → `now2 = clock(connection)`. If `due_occurrence(now2, row2)` is not the same `T` with the same revision → `changed`.
3. `key = occurrence_key(row2.revision, T)`. If a `refresh_runs` row with that `request_key` exists → `duplicate`.
4. `read_context` → `admin_context`. Any blocker → `blocked`.
5. `accept_scheduled_run(connection, key, row2)` → `admitted` after commit.

`run()` calls `once()` every 15 seconds until stopped. An exception becomes outcome `error`. The log has only the outcome, revision and `T`, never exception text, because database URLs can hold credentials (the same rule as `outbox.run`).

Why it holds:

| Risk | Control |
|---|---|
| Two schedulers | Both serialize on `refresh_control`; the second sees the run (`duplicate`) or the slot (`blocked`). The unique `request_key` is the final guard. |
| Restart within 300 seconds | Same `T` and revision give the same key; the step 3 check prevents a second run. |
| Commit failure | The whole transaction rolls back; the next poll inside the window may admit once. |
| Save during evaluation | PUT waits for the settings share lock; the step 2 recheck catches a save that committed between steps 1 and 2. |
| Clock skew | Both steps use PostgreSQL time (D03). |
| No-op save | `updated_at` is unchanged, so `T > updated_at` still holds (D02). |

Known limit: manual runs use the client `Idempotency-Key` as `request_key`. An Admin could send a key equal to a future occurrence key. The scheduled insert would then fail on the unique constraint; the transaction rolls back and logs `error`, and that occurrence is skipped. Only an Admin can do this, and the same Admin can turn the schedule off. Accepted as a documented limit; no migration is proposed for it.

### Test clock

`SchedulerService` takes `clock` as a constructor argument; production uses `database_now`. Tests pass a function that returns fixed instants. HTTP status has no clock override. Exact clock rows (spec S11) are tested on the pure `settings/schedule.py` functions; HTTP tests check relations (`next_check_at > evaluated_at`, null cases, blockers).

### Verification approach

| Layer | Plan |
|---|---|
| Offline pure | `tests/test_schedule_unit.py`: every clock example row, DST gap and fold, the D01 window edges (`T`, `T+299.999s`, `T+300s`), `T ≤ updated_at`, key stability, timezone cases from S04, request model cases from S03. |
| Offline service | `tests/test_settings_service.py`: R07 order with controlled adapters (no settings read before phase D), `If-Match` cases (S05), no-op and stale-no-op (S09), blocker choice and messages (S10), route headers and OpenAPI shape through `TestClient`. |
| Real PostgreSQL/HTTP | `tests/test_settings_postgres.py` with `PostgresFixture` (opt-in `TRINITY_TEST_DATABASE_URL`): first setup and later edits (S02), concurrent PUT (S06), rollback (S07), PUT during each lifecycle state (S08), status writes nothing (S12), real headers (S18). |
| Real scheduler | `tests/test_scheduler_postgres.py`: scheduler examples with a test clock (S13), two processes plus manual Start (S14), commit fault (S15), outbox row consumed by the existing outbox worker with the disposable Redis from `run_local_refresh_checks.py` (S16), log content and role start without EIA/S3/Redis settings (S17). |
| Image | Check `ZoneInfo` and `available_timezones()` inside the built API image (S19). |
| Operator | Alayala's retained Admin check (S20). |

## Review gate

Done: draft design with no migration and no dependency; one shared run-insert path; lock order and scheduler outcomes defined.
Pending: Steps 3–5, each separately authorized. Step 2 results are in the [tasks](tasks.md).
Blocker: none.
Next: [ME] Step 2 explanation, then authorize Step 3.
