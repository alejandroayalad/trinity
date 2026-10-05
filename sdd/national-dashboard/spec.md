# Specification: National dashboard and offline-share metric

Date: 2026-10-05
Status: Specification approved October 5, 2026 when alayala accepted D01–D03. A16 records D01 inputs, D02 and D03; A19 records D01 rate accounting. This document does not authorize implementation, dependencies, migrations or runtime activation.
Branch: `feat/national-dashboard`; based on `37a8a27`.
Basis: [proposal](proposal.md) with the accepted range-end cards, [API contract](../../docs/api-contract.md#catalog-and-national-dashboard), [OpenAPI](../../docs/openapi.json), [data contract v1](../../docs/schema.md), [security contract](../../docs/security-contract.md), [backend structure](../../docs/backend.md), the [preview specification](../dataset-preview/spec.md) and A9/A15–A20 in [DECISIONS.md](../../DECISIONS.md).
Evidence: [planning session](../../ai/sessions/2026-10-05-dashboard-backend-priority.md).

## Human

### Result

Any signed-in user (Viewer, Analyst or Admin) can open the national dashboard. One request returns the cards, the chart and the daily table for one date range of one published version. A second endpoint returns the national offline share for one date. Both endpoints use the same calculation, so they always agree for the same date and publication.

Input: `GET /api/v1/dashboard/national` with no parameters, `preset=30d|90d|1y`, or both `start` and `end`. `GET /api/v1/metrics/offline-share` with `period`. Flow: authenticate → validate the request → count one analytical request → pin one publication and its freshness → reserve shared capacity → read national Parquet rows in the isolated runtime → calculate the metric with exact decimals → fill missing dates with empty points → confirm cleanup → respond.

Output: the dashboard returns the publication, the resolved range, one point for each date, `summary` (the point for the range's end date), national diagnostics and freshness. The metric endpoint returns the publication, the date, the metric value or a null reason, and national diagnostics. No publication returns `409 data_unavailable`.

Example: the latest published observation is 2026-10-02. With no parameters, the range is 2026-09-03 to 2026-10-02 (30 dates). The national row for October 2 has capacity `1000` MW and outage `125` MW. Then `summary.offline_share_percent` is `12.50`, and `GET /metrics/offline-share?period=2026-10-02` also returns `12.50`.

Card example (accepted): the user selects Jan 1–31. The cards show January 31, labeled “Range end: Jan 31.” If January 31 has no national row, the cards show “not reported.” They do not show January 30 or the latest date.

Failure example: a user sends `preset=30d&start=2026-09-01&end=2026-09-30`. The server returns `422 invalid_request`. It does not pick one option for the user.

### Accepted refinements

| ID | Accepted behavior (alayala, October 5, 2026) |
|---|---|
| D01 — Validation and rate limit | Dashboard and metric use the same strict input checks and shared analytical rate-limit order as preview. Each admitted dashboard or metric request consumes one analytical attempt. |
| D02 — Rounding | Use decimal `ROUND_HALF_UP` to two places. Halfway negative values round away from zero: `-12.345 → -12.35`. Serialize rounded zero as `0.00`, never `-0.00`. |
| D03 — Diagnostics and freshness | Both endpoints return the national diagnostics bound to the pinned publication. Diagnostics do not change with the selected date. Read publication and freshness from the same database snapshot, so one response cannot mix two publication states. |

Reason: D01 reuses the accepted preview D01/D02 rules, so all analytical reads behave the same way. D02 is needed because the contract says “half-up” but does not define negative values; negative results come only from negative source outage (diagnostic D03 in `schema.md`), because capacity is never negative. D03 uses the scope the national preview already uses; date-filtered diagnostics would need evidence data that does not exist.

## LLM

### Requirements

IDs are local to this slice. They do not replace the preview R-numbers or frontend R-numbers. D01–D03 are accepted specification rules recorded under A16/A19. Their acceptance does not establish implementation or runtime correctness.

| ID | Required behavior |
|---|---|
| R01 | Add only `GET /api/v1/dashboard/national` and `GET /api/v1/metrics/offline-share`. Accept only `preset`, `start`, `end` on the dashboard and only `period` on the metric. Reject client version, path, role, SQL, dataset or entity inputs. Preserve existing transport limits. |
| R02 | Resolve the active account, valid session and stored role on every request. Require `national:read`, which Viewer, Analyst and Admin have. Unknown roles fail closed. Auth failure does no rate debit, publication read, admission, staging or execution. |
| R03 | Apply D01 strict scalar input: no duplicate or unknown parameters, no blank values, no GET body. Dates are exactly `YYYY-MM-DD` and valid Gregorian dates. `preset` is exactly `30d`, `90d` or `1y` (case-sensitive). `period` is required. |
| R04 | Dashboard range rules: no parameters means `30d`. `preset` with any custom date, only one custom date, `start > end`, or more than 366 inclusive custom dates returns 422 `invalid_request`. Never swap, clip or extend dates. |
| R05 | Presets end at `publication.latest_observation_date` of the pinned publication. `30d`, `90d` and `1y` cover 30, 90 and 365 inclusive dates. Custom ranges outside published coverage stay unchanged and give null points. |
| R06 | Apply D01's shared rolling analytical limit: 30 requests per user per 60 seconds, the same counter as SQL and preview. Each dashboard and each metric request counts once. Return 429 `rate_limited` with `Retry-After`. |
| R07 | Pin one active publication and its national file authority in one short read-only snapshot, using the preview's reauthorization and pinning pattern. Read freshness in the same snapshot (D03). Keep files, rows, diagnostics and response metadata on that publication, even if a newer one becomes active during execution. |
| R08 | No active publication returns 409 `data_unavailable`. Missing or inconsistent publication state returns 503 `dependency_unavailable`. A candidate, a stored but unpublished version, or a failed newer refresh does not change the result. No live EIA or S3 fallback. |
| R09 | Use the shared PostgreSQL admission: two active analytical requests per user and four per deployment, shared with SQL and preview. Never run without a reservation and never queue. Close metadata transactions before staging and execution. |
| R10 | Stage only the pinned national Parquet files through trusted storage code and verify SHA-256. Execute in the shared per-query container with a read-only national mount only. No facility or generator files, network, credentials, application tables or Docker control. Do not send generated SQL through `POST /queries` and do not call the preview route internally. |
| R11 | Read national rows with typed predicates `start ≤ period ≤ end`. At most one row per date and at most 366 rows. A duplicate date, a row outside the range or more rows than dates is a broken artifact: 503 `dependency_unavailable`, never a partial result. |
| R12 | One shared calculation serves both endpoints: `offline_share_percent = 100 × outage / capacity` from the same national row. Use exact decimal arithmetic with a correct rounding decision (no float, no double rounding). Round only the output, per D02, to exactly two places. |
| R13 | Capacity `0` gives a null metric with reason `zero_capacity`; the dashboard still returns the source capacity and outage. A missing date gives null capacity, outage, `percentOutage` and metric with reason `not_reported`. A present row with positive capacity has reason `null`. |
| R14 | Preserve source values exactly. `capacity`, `outage` and `percentOutage` are exact decimal strings with the same serializer as preview. A null source `percentOutage` stays null and does not change the metric. Preserve negative outage and values above 100 percent. Never average percentages, pool dates or replace a missing value with zero. |
| R15 | `days` has exactly one point per calendar date from `range.start` to `range.end`, ascending, including leap days. Null points are display points, not stored rows. `summary` equals `days[-1]` field by field, including when it is a `not_reported` point. |
| R16 | The metric response for `period = P` equals the dashboard point for `P` from the same publication: same `value` and same `reason`. `period` may be outside coverage; that gives `not_reported`, not an error. |
| R17 | Diagnostics follow D03: only national-scope diagnostics of the pinned publication, at most 32, through the existing trusted evidence reader. Never return facility, generator or `all` scope details, counts or Admin error text. Never infer an empty list from missing evidence. |
| R18 | Freshness follows the A16 catalog rule. `freshness.latest_observation_date` and `freshness.published_at` equal the pinned publication's values. `last_refresh` describes the latest run, including a failed or unfinished run, with only `status`, `requested_at` and `finished_at`. |
| R19 | Enforce A19 limits: 30 seconds for downloads, retries, startup and execution; 1 GiB container memory; 5 MiB encoded response. Retry temporary external failures three times in total (waits of 1 and 3 seconds) inside the same deadline. No partial success. |
| R20 | On success, timeout, disconnect, launch failure or supervisor crash, confirm the execution ended before releasing its reservation. Unknown execution state keeps the slot. Do not delete published data or evidence. |
| R21 | Return exactly `DashboardResponse` and `MetricResponse` from OpenAPI, with no extra fields. Validate the whole response before sending it. Every response has `X-Request-ID` and `Cache-Control: no-store`. Errors are safe Problem Details with no SQL, paths, secrets or traces. |
| R22 | Preserve existing auth, catalog, SQL and preview behavior and dependency pins. No new dependency or migration unless design proves the need and alayala approves it. |
| R23 | Prove the slice through offline tests, real PostgreSQL/HTTP/container checks and a retained-account operator check by alayala. Maintain data evidence — ongoing. Frontend work, facility ranking and the other three pending endpoint slices stay outside this slice. |

### D01 — Accepted input rules and validation order

Decode query parameters once. Inspect every occurrence before building a scalar value. Any duplicate (even with the same value), unknown name, empty value or nonempty GET body returns 422 `invalid_request`. Parameter names are case-sensitive.

| Order | Check or action | Counted? |
|---|---|---|
| 1 | Transport limits, session, active account, role, `national:read`. | No debit on rejection. |
| 2 | Known unique parameter names, empty body, primitive shapes: date format and validity, `preset` value, `period` present. | No debit on rejection. |
| 3 | Atomically attempt one shared rate debit. | Yes when admitted; a 429 adds no debit. |
| 4 | Dashboard combinations: preset with dates, one custom date only, `start > end`, more than 366 custom dates. | Debit kept on 422. |
| 5 | Reauthorize, pin the publication, freshness and national evidence authority in one snapshot. | Debit kept on 409 or 503. |
| 6 | Resolve preset dates from the pinned latest observation. | Debit kept. |
| 7 | Reserve capacity, start the 30-second deadline, stage, execute, collect, calculate, validate the response. | Debit kept on 429 busy, 503 or 504; retries add no debit. |

Date examples, with latest observation 2026-10-02:

| Request | Resolved range |
|---|---|
| no parameters or `preset=30d` | 2026-09-03 to 2026-10-02 (30 dates) |
| `preset=90d` | 2026-07-05 to 2026-10-02 (90 dates) |
| `preset=1y` | 2025-10-03 to 2026-10-02 (365 dates; UI label “Last 365 days”) |
| `start=2024-01-01&end=2024-12-31` | unchanged; 366 dates, valid |
| `start=2024-01-01&end=2025-01-01` | 422; 367 dates |
| `start=2026-10-01` only | 422; one custom date |

### D02 — Accepted rounding rule

| National row (outage / capacity) | Exact ratio × 100 | Output |
|---|---|---|
| 125 / 1000 | 12.5 | `12.50` |
| 863.4 / 2108.4 (F1 Millstone figures, used here as plain numbers) | 40.9504… | `40.95` |
| 123.45 / 1000 | 12.345 | `12.35` |
| -123.45 / 1000 | -12.345 | `-12.35` |
| -0.001 / 1000 | -0.0001 | `0.00` |
| 0 / 0 | undefined | `null`, `zero_capacity` |

The rounding decision must use the exact ratio. A limited-precision division followed by a second rounding is not acceptable unless design proves it gives the same result for all `DECIMAL(24,6)` inputs.

### D03 — Accepted diagnostics and freshness

Diagnostics come from the pinned publication's frozen national evidence, the same source the national preview uses. They are the same for every date and for both endpoints. Freshness is read in the same snapshot as the publication pin, so `publication` and `freshness` cannot describe two different versions.

### Response invariants

| Field | DashboardResponse rule |
|---|---|
| `publication` | Exactly the six `Publication` fields of the pinned version; never null on success. |
| `range` | The resolved inclusive `start` and `end`. |
| `days` | `(end − start) + 1` points, 1–366, ascending, no gaps or duplicates. |
| `summary` | Equal to the last element of `days`. |
| `diagnostics` | D03 national-scope list, at most 32. |
| `freshness` | R18; consistent with `publication`. |

| Field | MetricResponse rule |
|---|---|
| `publication` | Same rule as the dashboard. |
| `period` | The requested date, unchanged. |
| `metric` | `{value, reason}` equal to the dashboard point for that date. |
| `diagnostics` | Same D03 list as the dashboard for the same publication. |

`offline_share_percent` and `metric.value` match `^-?(0|[1-9][0-9]*)\.[0-9]{2}$` or are null. `reason` is `null`, `not_reported` or `zero_capacity`. A null metric always has a non-null reason, and a non-null metric always has a null reason.

### Errors

| Condition | HTTP and code |
|---|---|
| Missing, invalid, expired or revoked session; inactive account | Existing 401 contract. Unknown role: 403. |
| Unknown, duplicate or invalid parameter; GET body; invalid preset/date combination or range | 422 `invalid_request` |
| No active publication | 409 `data_unavailable` |
| Rate limit or shared capacity full | 429 `rate_limited` with `Retry-After` |
| Deadline exceeded | 504 `query_timeout` |
| Memory or output limit | 503 `query_resource_limit` |
| Broken publication state, artifact, checksum, evidence, admission or runtime output | 503 `dependency_unavailable` (auth storage: 503 `auth_unavailable`) |
| Unexpected defect | 500 `internal_error` |

These routes have no 404 or `publication_changed` case: they have no dataset path and no cursor.

### Acceptance scenarios

Steps 2–3 have pure and controlled-adapter/HTTP evidence in the [implementation record](../../ai/sessions/2026-10-05-dashboard-pure-and-service-implementation.md). S03–S11 passed at the pure level; the record distinguishes other offline coverage from pending real acceptance. O = offline; R = real database, HTTP and container; H = alayala's retained-account check. Subsequent authorized Step 4 real acceptance passed 101 combined tests with zero skips; the [runtime/operator handoff](../../ai/sessions/2026-10-05-dashboard-runtime-and-operator-handoff.md) maps measured scenarios and their boundaries. Retained H/S21 remains blocked by the missing publication and older API.

| ID | Scenario and expected result | Requirements | Evidence |
|---|---|---|---|
| S01 | Viewer, Analyst and Admin call both endpoints on a valid publication. Same body for all roles; national data only. | R01–R02, R17, R21 | O/R/H |
| S02 | Missing, expired or revoked session; inactive account; unknown role. Correct 401/403; no debit, read or admission. | R02, R06 | O/R |
| S03 | Duplicate, unknown, blank and malformed parameters; `preset=30D`; `period` missing; GET body. 422 before the debit. | R03, R06 | O/R |
| S04 | Preset with dates; one custom date; reversed dates; 367 dates. 422 after the debit. | R04, R06 | O/R |
| S05 | The D01 date table resolves exactly, including the leap year. | R04–R05, R15 | O/R |
| S06 | Custom range fully or partly outside coverage. Unchanged range; null `not_reported` points; summary matches the last point. | R05, R13, R15 | O/R |
| S07 | Missing dates inside the range, including the end date. Gaps stay null; summary is `not_reported`; no other date is used. | R13, R15 | O/R/H |
| S08 | Zero capacity with zero outage; zero outage with positive capacity. `zero_capacity` versus `0.00`. | R12–R13 | O/R |
| S09 | Every D02 rounding row, negative outage, outage above capacity and high-precision `DECIMAL(24,6)` values. Exact output; no float loss. | R12, R14 | O |
| S10 | Null source `percentOutage` on a valid row. It stays null; the metric is still calculated. | R14 | O/R |
| S11 | For every date in a fixture range, the metric endpoint equals the dashboard point for the same publication. | R12, R16 | O/R |
| S12 | No publication; candidate only; broken pointer or evidence. 409 versus 503. | R07–R08 | O/R |
| S13 | A newer publication becomes active during execution. Rows, diagnostics, freshness and metadata stay on the pinned version. | R07, R17–R18 | R |
| S14 | A newer refresh failed. Old publication still served; `last_refresh.status` shows the failure. | R08, R18 | O/R |
| S15 | Facility and generator canaries in evidence, files and logs. A dashboard request mounts only national data and leaks no detail. | R10, R17, R21 | O/R |
| S16 | Duplicate date, row outside range or extra rows in a test artifact. 503; no partial body. | R11, R21 | O/R |
| S17 | Mixed SQL, preview, dashboard and metric requests across processes hit the 30-per-60-seconds limit and the 2/4 slot limit. 429; no queue. | R06, R09 | O/R |
| S18 | Checksum mismatch, missing file, slow download, memory pressure, timeout, disconnect and supervisor crash. Correct error; slot released only after confirmed stop. | R10, R19–R20 | R |
| S19 | The query container tries network, hidden files, writes and application state. All denied. | R10 | R |
| S20 | Real HTTP responses match OpenAPI exactly, including headers; existing auth, catalog, SQL and preview tests still pass. | R21–R22 | O/R |
| S21 | Alayala signs in with retained Viewer and Analyst accounts against a legitimately published version. Checks the default range, a custom historical range with range-end cards and one metric date. Records safe results. | R23 | H |

### Design notes and open work

The pinned publication and the preview's typed national read already cover most of the flow. Design should check whether a national preview operation with a page size above 366 can serve the dashboard read without a new runtime operation kind; the metric calculation can then run once in trusted API code. If design adds an operation kind instead, it must be closed, typed and bound to the publication like `PreviewOperation`. Design must also choose the exact rounding method for D02 and the file placement under `docs/backend.md`.

Maintain data evidence — ongoing. Synthetic fixtures do not prove EIA completeness or live S3 success. Do not publish retained candidate data only to make S21 pass; real publication setup needs separate authorization.

## Review gate

Done: approved specification with 23 requirements, 21 scenarios and D01–D03, recorded under A16/A19.
Pending: retained-account acceptance (S21). Both Step 2 explanations and the Step 4 local runtime results are recorded; see [tasks](tasks.md).
Blocker: no active retained publication and an installed API without national/preview routes or the preview switch. Local acceptance does not establish deployed readiness.
Next: [ME] review the handoff and decide the scope of retained preparation.
