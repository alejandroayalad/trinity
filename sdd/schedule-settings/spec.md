# Specification: Schedule settings, initial setup and daily scheduled admission

Date: 2026-10-05
Status: Specification approved October 5, 2026. Alayala accepted D01 and D03 and chose the no-op rule for D02, including the check order in R07/R08a. A16 records D01–D03; A19 records the D03 scheduler secret boundary. This document does not authorize implementation, dependencies, migrations or runtime activation.
Branch: `feat/schedule-settings`; based on `8746bb8`.
Basis: [proposal](proposal.md), [API contract](../../docs/api-contract.md#setup-and-daily-schedule), [OpenAPI](../../docs/openapi.json) (`SettingsRequest`, `SettingsResponse`, `ScheduleStatus`, `Blocker`), [data contract](../../docs/schema.md) (`shared_settings`, `refresh_runs`, admission rules), [security contract](../../docs/security-contract.md), [backend structure](../../docs/backend.md#scheduling-dispatch-and-recovery) and A2/A3/A15/A16/A19/A20/A23 in [DECISIONS.md](../../DECISIONS.md).
Evidence: [specification session](../../ai/sessions/2026-10-05-schedule-settings-specification.md).
Related work: the unmerged `frontend` branch (`0ee652d`) contains an AI-authored implementation of these routes. This specification does not adopt its choices. Design may compare against it.

## Human

### Result

An Admin completes shared setup once. Later, any Admin can edit the daily schedule. The Schedule page shows the next check in local time and UTC, and the one reason that blocks a refresh now. Saving never starts a refresh. When the saved time arrives, a background scheduler starts a refresh through the same protected admission as the manual Start button.

Input: `PUT /api/v1/settings` with `If-Match: "settings-<revision>"` and exactly `schedule_enabled`, `daily_time`, `timezone`. `GET /api/v1/settings/schedule-status` with no input. Existing `GET /api/v1/settings` stays as it is.

Flow (save): authenticate the Admin → check the precondition and body → lock the settings row → compare the revision → write values, revision, time, actor and (first time only) setup time in one transaction → return the committed settings with a new `ETag`.

Flow (status): authenticate the Admin → read settings and lifecycle state in one snapshot → calculate the next occurrence → choose one blocker → respond. Nothing is reserved or written.

Flow (scheduler): a trusted worker reads the clock → finds a due occurrence for the current settings revision → locks admission → rechecks setup, schedule and blockers → creates one `scheduled` run with its slot and outbox row, or skips.

Example: the Admin reads revision `3` and saves enabled, `06:15`, `America/New_York`. The response has revision `4`. At `2026-10-05T12:00:00Z` the status shows `next_check_at = 2026-10-06T10:15:00Z` and `next_check_local = 2026-10-06T06:15:00-04:00`. No run appears because of the save.

Failure example: two Admins read revision `3`. The first saves and gets revision `4`. The second sends `If-Match: "settings-3"` and gets `412 revision_mismatch`. The first change stays. The second Admin reloads before saving again.

### Decisions (settled)

These are not settled by the contract. Each has one recommendation. The Status column records alayala's answer.

| ID | Question | Recommendation | Why | Status |
|---|---|---|---|---|
| D01 — Due window | When is an occurrence "missed" instead of late? | An occurrence at UTC instant `T` is due only while `T ≤ now < T + 300 seconds`, and only if `T` is later than the current settings `updated_at`. After the window it is missed and skipped, with no record and no backlog. | A short scheduler restart near `T` still starts the run. A long outage does not start a surprising late run. The `updated_at` rule implements "changes affect future occurrences only." | Accepted by alayala, October 5, 2026. |
| D02 — No-op save | A PUT with the same values as stored: new revision or no change? | AI recommended: always a new revision. Alayala chose the no-op rule instead (see Status). | Alayala's rule keeps a no-op save from changing the effective save time, so it cannot cancel a due occurrence under D01. | Changed by alayala, October 5, 2026: if `schedule_enabled`, `daily_time` and `timezone` are identical to the stored values, return the current settings and current revision. Do not create a new revision and do not change the effective save time (`updated_at`) used by the scheduler. |
| D03 — Clock and scheduler role | Which clock, and which process evaluates the schedule? | PostgreSQL `clock_timestamp()` is the only clock for `evaluated_at`, due tests, `updated_at` and `setup_completed_at`. A separate worker role `scheduler` evaluates at least every 30 seconds. It loads no EIA key, S3 credential or Redis URL; dispatch stays with the existing outbox worker. | One clock across API and worker avoids skew between status and admission. 30 seconds is well inside the 300-second window. The role cannot do external work. | Accepted by alayala (both parts), October 5, 2026. |

## LLM

### Requirements

IDs are local to this slice. They do not replace frontend R-numbers. Any requirement marked "per D0x" changes if alayala chooses differently.

| ID | Required behavior |
|---|---|
| R01 | Add only `PUT /api/v1/settings`, `GET /api/v1/settings/schedule-status` and a non-HTTP scheduler role. Preserve `GET /api/v1/settings` exactly, including `ETag: "settings-<revision>"`. Do not add a public scheduler tick, run-now or cancel endpoint. |
| R02 | Resolve the active account, valid session and stored role on every request. PUT requires `settings:write`; status requires `settings:read`. Only Admin has them. Viewer and Analyst get `403` before any settings or lifecycle read. Unknown roles fail closed. |
| R03 | PUT body: JSON object with exactly the three fields, all required even when `schedule_enabled` is false. `schedule_enabled` is a JSON boolean (no `"true"`, `1` or null). `daily_time` matches `^([01][0-9]\|2[0-3]):[0-5][0-9]$`. Unknown fields, including `publication_mode`, `revision`, `updated_by` and `setup_completed_at`, return `422 invalid_request`. |
| R04 | `timezone` is 1–100 characters and is an exact, case-sensitive member of `zoneinfo.available_timezones()` in the running image. Reject paths, `posix/` or `right/` prefixes, `localtime`, and case variants such as `america/new_york` even if the file system resolves them. Store the submitted name unchanged. |
| R05 | Status has no query parameters and no body. Any query parameter or a nonempty body returns `422 invalid_request`. |
| R06 | Precondition: missing `If-Match` returns `428 precondition_required`. More than one value, a wildcard, a weak tag, or a value that is not exactly `"settings-<Counter>"` returns `422 invalid_request`. A well-formed tag that differs from the stored revision returns `412 revision_mismatch` and writes nothing. |
| R07 | Validation order for PUT: (1) transport size and media type (`413`, `415`); (2) session, account, role, `settings:write`; (3) `If-Match` presence and shape; (4) JSON parse (`400 invalid_json`) and body schema (`422`); (5) lock the settings row and compare the revision (`412` if stale); (6) compare the three values; if identical, return the current record without writing (R08a); (7) otherwise write the new revision (R08). Steps 1–4 read no settings or lifecycle state. Alayala confirmed steps 5–7 on October 5, 2026: the revision check comes before the no-op check, so a stale client never receives `200`. |
| R08 | Successful PUT, in one transaction: set the three values, increase `revision` by exactly 1, set `updated_at` and `updated_by` to the session's local user ID. If `setup_completed_at` is null, set it to the same instant as `updated_at`; otherwise never change it. Return `200` with `SettingsResponse` and the new `ETag` only after commit. |
| R08a | No-op save (D02): after the revision check passes (R06, R07 step 5), compare the three submitted values with the stored values. `schedule_enabled` by boolean value; `daily_time` and `timezone` as exact strings. If all three are equal, write nothing: `revision`, `updated_at`, `updated_by` and `setup_completed_at` stay unchanged. Return `200` with the current `SettingsResponse` and the current `ETag`. A no-op save is impossible before setup, because the stored time and timezone are null. A stale `If-Match` still returns `412`, even when the values match (accepted by alayala). |
| R09 | PUT never creates a run, slot, outbox row or command receipt. It never cancels, edits or re-freezes accepted work. Existing runs keep their frozen `settings_revision` and policy snapshot. It is allowed while a run is active, awaiting review or blocked by a failure. |
| R10 | A failed or rolled-back PUT leaves no partial change: no revision step, no setup time and no actor change. A lost response is handled by GET and reconcile; the server does not accept a replay of the old revision (R06). |
| R11 | Status, in one read-only snapshot: read settings and lifecycle context with the existing `read_settings` and `read_context` rules and the D03 clock. Return exactly `ScheduleStatus`: `settings_revision`, `schedule_enabled`, `next_check_at`, `next_check_local`, `timezone`, `evaluated_at`, `eligible_now`, `blocker`. |
| R12 | `next_check_at` and `next_check_local` are non-null only when setup is complete and scheduling is enabled. Then `next_check_at` is the first occurrence (R13) strictly after `evaluated_at`, even while a blocker exists. Otherwise both are null. `next_check_local` is the same instant in RFC 3339 with the zone offset and seconds, for example `2026-10-06T06:15:00-04:00`. `next_check_at` uses `Z`. |
| R13 | Occurrence rule: for each local calendar date in the saved timezone, the occurrence is that date at `daily_time`. If the local time does not exist (spring-forward gap), that date has no occurrence. If it occurs twice (fall-back fold), use only the first UTC instant. Status and scheduler use the same function. |
| R14 | Blocker choice, one only: `setup_required` (setup not complete); else `schedule_disabled`; else the lifecycle blocker from the existing admission context: `refresh_active`, `review_required`, `publication_in_progress` or `failure_unresolved`. An unresolved failure warning on a `publication_failed` run is reported as `failure_unresolved`, not as an active-work label. |
| R15 | `eligible_now` is true exactly when `blocker` is null. It does not test whether the clock is due. A true value is not a promise that a refresh will be accepted. |
| R16 | Blocker fields: `setup_required` and `schedule_disabled` have null `run_id`, `version_id`, `warning_id`. Lifecycle blockers carry the holder run, its candidate and its unresolved warning IDs when present. `message` is a fixed safe text per code (see the table below), never run error details. |
| R17 | Scheduler admission: when an occurrence `T` is due per D01, open one transaction. Lock `refresh_control`, take the settings row `FOR SHARE`, reread settings, and recheck setup, enabled, current revision, `T > updated_at`, and no lifecycle blocker. If any check fails, skip with no database write. If all pass, insert one run with `trigger_kind='scheduled'`, `requested_by` null, the current `settings_revision` and the same policy snapshot as a manual run, reserve its slot and insert its `refresh_pipeline` outbox row. No `api_commands` receipt (it requires a human actor). No EIA, S3 or Redis call inside the transaction. |
| R18 | Occurrence identity is the pair (settings revision, `T` in UTC), as `schema.md` requires. At most one run exists for one identity, even with two scheduler processes, a restart, or a retry after a commit error. Design must show how the existing unique `request_key` (or another existing constraint) enforces this; a new migration needs a design reason and alayala's approval. |
| R19 | No backlog: a blocked, missed or skipped occurrence is never retried later. A scheduler that was down for a day starts at most the occurrence still inside its window (D01), never one run per missed day. Manual and scheduled requests compete for the same slot; exactly one lifecycle wins. |
| R20 | Changing the schedule affects only occurrences after the save instant (D01). It does not cancel a run already admitted from an earlier revision. A save cannot make an already admitted occurrence run twice. |
| R21 | The scheduler role writes safe structured logs for admitted and skipped occurrences (identity, outcome code). It never logs secrets or setting values beyond time and timezone. Skips create no run or warning row. |
| R22 | Responses match OpenAPI exactly, with no extra fields. Every response has `X-Request-ID` and `Cache-Control: no-store`. PUT and GET return `ETag`. Errors are safe Problem Details. Settings endpoints do not use the analytical rate counter. |
| R23 | Preserve existing auth, `/me`, manual refresh start, publication and recovery behavior, migrations and dependency pins. `/me` reflects setup only after the PUT commits. No new dependency. Confirm the runtime image has the IANA database (R04); do not add `tzdata` without approval. |
| R24 | Prove the slice with offline tests, real PostgreSQL/HTTP checks, a real scheduler-to-outbox check with a test clock, and a retained-account check by alayala. Maintain data evidence — ongoing: this slice adds no EIA evidence and must not change findings or publication rules. |

### Blocker messages

| Code | `message` |
|---|---|
| `setup_required` | "Complete setup before refreshes can run." |
| `schedule_disabled` | "The daily schedule is off. Manual refresh is still available." |
| `refresh_active` | "A refresh is running." |
| `review_required` | "A candidate is waiting for Admin review." |
| `publication_in_progress` | "A publication is in progress." |
| `failure_unresolved` | "A failed refresh needs Admin action." |

The messages are AI-proposed copy. The frontend may show its own handoff text keyed by `code`.

Note: `schedule_disabled` hides a lifecycle blocker that also exists. Manual Start still uses the existing refresh context, which does not consider the schedule.

### Clock examples

All rows use the D03 clock. Values were computed with Python `zoneinfo` on the local machine; they are examples, not runtime evidence.

| Settings | `evaluated_at` | `next_check_at` | `next_check_local` |
|---|---|---|---|
| `06:15`, `America/New_York` | 2026-10-05T12:00:00Z | 2026-10-06T10:15:00Z | 2026-10-06T06:15:00-04:00 |
| `06:15`, `America/New_York` | 2026-10-05T10:15:00Z (exact instant) | 2026-10-06T10:15:00Z (strictly after) | 2026-10-06T06:15:00-04:00 |
| `08:00`, `America/Merida` | 2026-10-05T15:00:00Z | 2026-10-06T14:00:00Z | 2026-10-06T08:00:00-06:00 |
| `02:30`, `America/New_York` | 2026-03-08T06:00:00Z | 2026-03-09T06:30:00Z (March 8 02:30 does not exist) | 2026-03-09T02:30:00-04:00 |
| `01:30`, `America/New_York` | 2026-11-01T04:00:00Z | 2026-11-01T05:30:00Z (first 01:30, EDT) | 2026-11-01T01:30:00-04:00 |
| `01:30`, `America/New_York` | 2026-11-01T05:45:00Z | 2026-11-02T06:30:00Z (second 01:30 skipped) | 2026-11-02T01:30:00-05:00 |
| setup incomplete, or disabled | any | null | null |

### Scheduler examples (per D01)

| Situation | Result |
|---|---|
| Occurrence 06:15, scheduler evaluates at 06:15:20, no blocker | One `scheduled` run. |
| Two scheduler processes evaluate the same occurrence | One run; the second finds the identity taken and writes nothing. |
| Scheduler restarts at 06:18 | Still inside 300 seconds; one run if none exists for that identity. |
| Scheduler restarts at 06:25 | Missed; no run, no record. Next is tomorrow. |
| A failed run holds the slot at 06:15 | Skipped. Resolving the warning at 09:00 does not start a late run. |
| Admin saves new time 06:20 at 06:16 after the 06:15 run was admitted | 06:20 is a new identity; it runs if no blocker exists then (normally blocked by the 06:15 run). |
| Admin re-saves the same values at 06:15:10, before the scheduler evaluated | No-op save (D02): `updated_at` does not change, so the 06:15 occurrence is still due and runs once. |
| Admin changes only the timezone at 06:15:10, before the scheduler evaluated | Real change: new revision and `updated_at`. The old 06:15 occurrence is not after the save; skipped. The next occurrence uses the new timezone. |
| Admin presses Start at 06:15:05; scheduler evaluates at 06:15:20 | Manual run holds the slot; scheduled occurrence skipped. |

### Errors

| Condition | HTTP and code |
|---|---|
| Missing, invalid, expired or revoked session; inactive account | Existing `401` contract |
| Viewer, Analyst or unknown role | `403` |
| Body too large / wrong media type | `413 request_too_large` / `415 unsupported_media_type` |
| Malformed JSON | `400 invalid_json` |
| Unknown or missing field, wrong type, bad time, invalid timezone, malformed `If-Match`, status query or body | `422 invalid_request` |
| No `If-Match` on PUT | `428 precondition_required` |
| Stale revision | `412 revision_mismatch` |
| Missing or corrupt settings row, broken lifecycle state, lock timeout | `503 dependency_unavailable` with `Retry-After` |
| Unexpected defect | `500 internal_error` |

### Acceptance scenarios

None has run. O = offline; R = real PostgreSQL, HTTP and worker; H = alayala's retained-account check.

| ID | Scenario and expected result | Requirements | Evidence |
|---|---|---|---|
| S01 | Viewer and Analyst call PUT and status; expired and revoked sessions. `403`/`401`; the settings repository is never read. | R02, R07 | O/R |
| S02 | First save from revision `0`: setup time set, revision `1`, actor from the session. A second save keeps the setup time and gives revision `2`. | R08 | O/R/H |
| S03 | Body cases: each field missing, extra `publication_mode`, `revision`, `updated_by`; `"true"` as string; null values; disabled body without time. All `422`, no write. | R03, R07 | O/R |
| S04 | Time and timezone cases: `24:00`, `6:15`, `06:60`, `America/Nowhere`, `america/new_york`, `posix/America/New_York`, `/etc/localtime`, 101 characters. All `422`. `UTC` and `America/Merida` succeed. | R03–R04 | O/R |
| S05 | Precondition cases: missing (`428`), `*`, `W/"settings-1"`, two tags, `"candidate-1"`, `"settings-01"` (`422`), stale (`412`). No write in any case. | R06–R07 | O/R |
| S06 | Two concurrent PUTs with the same revision: one `200`, one `412`; final row equals the winner. | R06, R08 | R |
| S07 | Database failure after the values update and before commit: no revision change, no setup time. | R10 | O/R |
| S08 | PUT while a run is active, awaiting review and failed. `200`; no run, slot, outbox row or receipt created; the run keeps its frozen revision. | R09, R20 | O/R |
| S09 | No-op save (D02): identical values with the current `If-Match` return `200`, the same revision and `ETag`, and unchanged `updated_at` and `updated_by`. The same values with a stale `If-Match` return `412`. A change to only one field (for example disabled → enabled) creates a new revision. A due occurrence still runs after a no-op save. | R08a, R20 | O/R |
| S10 | Status for not set up, disabled, enabled-idle, each lifecycle blocker, and `publication_failed` with warning. Blocker, IDs, message and `eligible_now` match R14–R16. | R11, R14–R16 | O/R |
| S11 | Every row of the clock examples table, using a fixed test clock. | R12–R13 | O |
| S12 | Status sends no write and reserves nothing: row counts and `refresh_control` revision unchanged. | R11 | R |
| S13 | Every row of the scheduler examples table with a test clock. | R17–R20, D01 | O/R |
| S14 | Two scheduler processes and a manual Start race at the same instant. Exactly one lifecycle; at most one run for the occurrence identity. | R17–R19 | R |
| S15 | Commit failure during scheduled admission: no run, slot or outbox row; the next evaluation inside the window may admit once. | R17–R18 | O/R |
| S16 | A scheduled run reaches the existing outbox worker and is dispatched to the refresh queue (test queue, no EIA call). | R17, R24 | R |
| S17 | Scheduler logs contain identity and outcome only; no secrets. The role starts without EIA, S3 and Redis settings. | R21, D03 | O/R |
| S18 | Real HTTP responses match OpenAPI exactly, including headers; existing auth, `/me`, refresh, publication and settings-read tests still pass. | R22–R23 | O/R |
| S19 | The runtime image resolves `America/New_York` and `America/Merida`, and `available_timezones()` is not empty. | R04, R23 | R |
| S20 | Alayala signs in as retained Admin, saves a schedule, sees the next check, and confirms no run started. Scheduled dispatch against retained data is a separate operator gate. | R24 | H |

### Design notes and open work

Design must decide: the settings lock order relative to `refresh_control` (manual start already takes `refresh_control` then settings `FOR SHARE`); how the scheduler derives a stable `request_key` from the occurrence identity without a migration; how a test clock is injected without a production override; how the scheduler role is started under the existing `workers/__main__.py` and Docker Compose; and file placement under `docs/backend.md` (`settings/service.py`, `workers/scheduler.py`). It must also say whether `admin_context` changes, because `start_refresh` is enabled only when no run holds the slot.

R04 evidence (local macOS, Python `zoneinfo`, October 5): `ZoneInfo('america/new_york')` loads on the case-insensitive file system, but `available_timezones()` (598 names) does not contain it, `posix/America/New_York` or `localtime`. The existing `read_settings` check uses `ZoneInfo(...)` only, so it would accept the case variant. The Linux image was not checked.

Frontend pages are outside this slice. The frontend uses `Intl.supportedValuesOf('timeZone')`, which can differ from the server's list; the server list (R04) decides validity.

## Review gate

Done: approved specification with 25 requirements (R01–R24 and R08a), 20 scenarios and D01–D03, recorded under A16/A19.
Pending: implementation Steps 3–5 per the approved [design](design.md) and [tasks](tasks.md); Step 2 is implemented offline. No code, test or runtime check was run for this document.
Blocker: none for the specification.
Next: see [tasks](tasks.md).
