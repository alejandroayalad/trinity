# Proposal: Schedule settings and initial setup

Date: 2026-10-05
Status: Planning proposal only. Alayala authorized separate proposal commits and a push to `pending-endpoints-frontend`; implementation is not authorized.
Basis: A2/A3/A16/A19/A20/A22–A24 in [DECISIONS.md](../../DECISIONS.md), [API contract](../../docs/api-contract.md#setup-and-daily-schedule), [OpenAPI](../../docs/openapi.json), [data contract](../../docs/schema.md) and [backend architecture](../../docs/backend.md).
Order: after [Dashboard](../national-dashboard/proposal.md), before Plant filter and failed-run recovery.

## Human

### Outcome and flow

An Admin completes shared setup once and edits the daily schedule later. The page shows the next scheduled check and why refresh admission is currently blocked. Saving settings does not start a refresh.

| Endpoint, under `/api/v1` | Input | Result |
|---|---|---|
| Existing `GET /settings` | Admin session | Current fields and `ETag: "settings-<revision>"`. Preserve this behavior. |
| New `PUT /settings` | Admin session, current `If-Match`, exactly `schedule_enabled`, `daily_time`, `timezone` | Updated `SettingsResponse` and revision. First successful save completes shared setup once. |
| New `GET /settings/schedule-status` | Admin session | `ScheduleStatus`: revision, evaluation time, next UTC/local check, timezone, eligibility and one blocker. |

Input → flow → output: authenticate the Admin → validate the three fields and revision → lock current shared state → compare revision and atomically save values, setup marker and trusted actor → return the committed settings. Status reads compute the next occurrence from the saved daily time/timezone and describe admission without reserving work.

Example: save enabled, `06:15`, `America/New_York` using the revision returned by GET. The page shows the next check in local time and UTC. It does not show a newly started run merely because Save succeeded.

Failure case: two Admins read revision `3`. The first saves and obtains revision `4`. The second sends `If-Match: "settings-3"`; return `412 revision_mismatch` without overwriting the first change. The second Admin reloads settings before deciding what to save.

### Rules already accepted

All fields are required even when disabled; the time is `HH:mm` and timezone is a valid IANA name. Reject unknown fields and `publication_mode`. Missing precondition is `428`; stale revision is `412`. Follow the canonical transport/error schemas for invalid requests and authorization. The body cannot supply an actor, revision or setup timestamp.

Setup completion is written once for the shared account, not once per Admin. PUT uses revision-based compare-and-swap rather than command idempotency receipts. If the response is lost, GET and reconcile; do not blindly replay an old revision. Preserve the existing publication and all accepted work.

When setup is complete and scheduling enabled, `next_check_at` is strictly after `evaluated_at`, even when another run blocks admission. Otherwise both next-check values are null. `eligible_now` means setup/enabled/admission conditions permit work; it does not mean the clock is due. Blocker priority is setup required, schedule disabled, then lifecycle/failure state, with unresolved publication failure taking precedence over a generic active label.

Skip nonexistent daylight-saving times; use the first UTC occurrence of a repeated local time. Skip blocked/missed occurrences without a backlog. Changes affect future occurrences and never cancel accepted work.

### Scope recommendation

Plan the two public endpoints together with their daily scheduler integration. This completes the meaning of the Schedule page. Keep HTTP saves separate from due-time admission; both scheduled and manual runs must enter the same protected refresh pipeline. Do not add a public “scheduler tick” endpoint.

Exact scheduler ownership, durable occurrence identity, evaluation interval, restart rules and database changes belong in the specification/design. They remain proposed details. Do not silently select them from a queue example or claim that a status calculation proves scheduling works.

## LLM

### Existing flow and reuse

`settings.router.settings` calls `get_settings`, which requires `settings:read` and projects `read_settings` into `SettingsResponse`. The repository already validates saved timezone data with standard-library `ZoneInfo`. Reuse this feature, current permissions and database transactions; no production dependency is proposed.

`RefreshService.start` locks `refresh_control`, rechecks current authority, reads shared settings and lifecycle context, and calls `refresh.repository.accept_run`. That method atomically writes run, slot, outbox and receipt, but currently hard-codes `trigger_kind='manual'`. Scheduled admission needs an explicit trusted trigger path; it must not impersonate an Admin HTTP request. Preserve frozen settings revisions and policy snapshots.

Static absence evidence: inspect `backend/src/trinity/settings/{router,service,repository,schemas}.py` and list `backend/src/trinity/workers/`. `rg -n '@router\.|scheduled|schedule'` across those directories and `refresh/` finds only GET settings, manual admission and declared scheduled trigger types; no settings-write/status route or daily scheduling worker is present. This is source evidence, not a deployed failure.

### Bounded sequence

1. **Maintain data evidence — ongoing.** Schedule metadata is not new EIA evidence; preserve findings and publication rules.
2. Specify exact write/status schemas, validation, preconditions, timezone behavior and scheduler occurrence semantics.
3. Design shared admission, lock order, durable occurrence deduplication and restart handling; identify any necessary migration before code.
4. After separate implementation authorization, add HTTP behavior and scheduled admission through the existing outbox/worker pipeline.
5. Verify concurrency, clock behavior and real scheduled dispatch before claiming delivery.

### Acceptance to specify

| Area | Required cases |
|---|---|
| Authorization and setup | Viewer/Analyst denied before protected reads/writes; expired session; first setup versus subsequent edits; actor derived from session; failed transaction leaves no partial setup. |
| Input and concurrency | Invalid time/timezone, missing/extra fields, disabled-but-incomplete body, missing/stale/malformed ETag, two concurrent saves, response loss and GET reconciliation. |
| Clock/status | Disabled/unconfigured state, exact due instant, next strictly future instant, DST gap/fold, settings change, blocker precedence and no implicit refresh on GET/PUT. |
| Scheduled admission | Duplicate evaluators admit once; concurrent manual start admits one lifecycle; blocked/missed ticks create no backlog; restart does not duplicate accepted work; outbox failure rolls back admission. |
| Runtime and regression | Disposable PostgreSQL/HTTP and existing queue worker prove actual dispatch; preserve manual refresh/auth/settings reads. Retained-user scheduling is a separate operator gate. |

Done: source-grounded proposal. Pending: specification/design and scheduler-detail decisions. Blocker: none for planning. No backend tests or live actions were run for this document.
