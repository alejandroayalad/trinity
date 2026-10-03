# Trinity API contract

Status: the supplied high-level API flow is approved by alayala on October 3, 2026, under [A16](../DECISIONS.md#a16--approved-api-flow-and-detailed-contract). Exact schemas below are AI-authored completion work requested by alayala. This is documentation, not a running application. [A17](../DECISIONS.md#a17--dependency-versions-and-update-policy-closed) records approved dependency versions. A18 accepts staged SQL scope; [A19 security contract](security-contract.md) records the agreed security design. Implementation and runtime verification remain pending.

## Human overview

The approved source is `trinity-api-contract-final.md`. Its six-part design is retained here, followed by exact requests, responses, errors, and recovery rules. Publication is fixed by validation and warnings; no Admin chooses a publication mode. A failed lifecycle holds new refreshes until recovery or abandonment. Your downloaded source file is unchanged.

Updated October 3, 2026. All endpoints use `/api/v1` and JSON. The backend verifies identity and permission on every request.

### 1. Roles and app entry

| Role | Access |
| --- | --- |
| **Viewer** | National dashboard and national data only. |
| **Analyst** | All analytical datasets, previews, filters, and read-only SQL. |
| **Admin** | Analyst access, setup, settings, refreshes, and candidate review. |

`GET /me` returns the user's role, capabilities, data readiness, and landing screen. Before the first publication, Viewers and Analysts see a waiting screen. Only Admins can access setup. After setup, Admins can manage the first refresh even while data remains unavailable.

### 2. Setup and settings

| Endpoint | Purpose |
| --- | --- |
| `GET /settings` | Read shared settings and their revision. |
| `PUT /settings` | Complete initial setup or update settings. |
| `GET /settings/schedule-status` | Show the next scheduled check and any current blocker. |

Editable settings are **schedule enabled, daily time, and timezone**. Publication behavior is fixed; there is no selectable publication mode.

The first successful save completes setup. **Start first refresh** is a separate action. Settings saves require the current revision through `If-Match`. A stale revision returns `412`; a missing revision precondition returns `428`.

Schedule changes affect future work and do not cancel accepted work. Blocked or missed occurrences are skipped without a backlog. A nonexistent daylight-saving time is skipped; a repeated time runs once. The next scheduled check does not guarantee that a refresh will start.

### 3. Dashboard and exploration

| Endpoint | Purpose |
| --- | --- |
| `GET /catalog` | Return permitted datasets, schemas, units, metrics, and freshness. |
| `GET /dashboard/national` | Return national summary cards, daily trends, and table values. |
| `GET /metrics/offline-share` | Return the national metric for a date. |
| `GET /datasets/{dataset_key}/preview` | Return filtered, paginated rows. |
| `GET /datasets/{dataset_key}/facilities` | Load facility choices for permitted detailed datasets. |
| `GET /datasets/{dataset_key}/generators` | Load generators for a selected facility. |
| `POST /queries` | Execute permitted read-only SQL for Analysts and Admins. |

Preview filters do not silently modify SQL. Each analytical request uses one published version and identifies it in the response. A publication change during preview pagination requires a restart.

Dashboard presets cover the last 30 days, 90 days, or year, ending at the latest published national observation. Custom ranges are bounded. Summary cards use the same observation date. The dashboard and metric endpoint must agree for the same date and version, using the A9 metric definition.

Missing values remain missing, and charts show gaps for missing days. Observation date and publication time have separate labels. Viewers never receive facility or generator details, including through diagnostics or errors.

Before publication, the catalog may return permitted static schemas; analytical reads return `409 data_unavailable`.

### 4. Refresh and recovery

| Endpoint | Purpose |
| --- | --- |
| `POST /refresh-runs` | Request a new refresh after setup. |
| `GET /refresh-runs` | Return history, current work, and unresolved failure warnings. |
| `GET /refresh-runs/{run_id}` | Return stages, attempts, progress, errors, candidate reference, and allowed actions. |
| `POST /refresh-runs/{run_id}/rerun` | Resolve the failure warning and start a new full refresh atomically. |
| `DELETE /refresh-runs/{run_id}/warning` | Resolve the failure warning without starting work. |

Only one refresh lifecycle is admitted at a time. Temporary failures receive bounded automatic retries. Exhausted or permanent failures produce a persistent warning that blocks manual and scheduled refreshes.

An Admin can choose **Run again** or **Delete warning**. Both preserve history and permanently abandon any unpublished candidate from the failed work. Run again creates a new run; it does not resume the old run. These actions are checked atomically against concurrent requests.

The screen polls while work progresses. Closing it does not stop workers. A failed refresh does not reset setup or remove the current publication.

### 5. Candidate review and publication

Candidates open in a **side panel on the refresh run page**. The run exposes its candidate reference and review status. Only Admins can access this flow.

| Endpoint | Purpose |
| --- | --- |
| `GET /candidates/{version_id}` | Return coverage, checks, warnings, approval, publication progress, and allowed actions. |
| `POST /candidates/{version_id}/approval` | Record approval and queue publication. |
| `POST /candidates/{version_id}/publication-retry` | Retry publication of the same eligible candidate, reusing approval when required. |
| `POST /candidates/{version_id}/discard` | Permanently prevent publication and preserve history. |

| Validation or publication result | Behavior |
| --- | --- |
| All checks pass, no warnings | Publish automatically. |
| Required checks pass, warnings exist | Show **Review required** on the run page; require Admin approval. |
| Required checks fail or remain incomplete | Block publication. |
| Publication fails | Offer publication retry when eligible, or abandonment. |
| Candidate is discarded or superseded | Forbid publication. |

Approval and publication retries apply to the exact validated candidate. They cannot authorize changed files. Retrying a failed automatic publication does not introduce an approval requirement.

Pending review and unresolved publication failures block another refresh. An allowed discard permanently abandons the candidate and clears its review or publication-failure block, including the associated unresolved failure warning. Recovery actions cannot revive a discarded candidate.

### 6. Shared guarantees

Approval and its publication work request are saved together in PostgreSQL. Refresh requests and their work requests follow the same durable pattern. The outbox sends committed work to BullMQ. Workers publish one candidate at a time.

Repeated requests cannot create duplicate work. Conflicting actions are checked atomically. An older candidate cannot replace a newer publication.

Accepted background work returns **`202 Accepted`** with a tracking reference. Acceptance does not mean publication succeeded. Invalid state changes return **`409 Conflict`**; settings revision errors follow Section 2. Errors use safe messages and stable codes.

Users continue seeing the current publication until the next version becomes active. Unpublished candidates remain unavailable to analytical reads.

The following sections complete the field and HTTP specification. Implementation and runtime verification remain pending.

## Endpoint inventory

All 20 approved operations are represented in [openapi.json](openapi.json). Role names denote minimum capabilities, with dataset restrictions applied separately.

| Method and path | Minimum role | Request body | Response |
|---|---|---|---|
| `GET /me` | viewer | none | MeResponse; 200. |
| `GET /settings` | admin | none | SettingsResponse; 200. |
| `PUT /settings` | admin | SettingsRequest | SettingsResponse; 200. |
| `GET /settings/schedule-status` | admin | none | ScheduleStatus; 200. |
| `GET /catalog` | viewer | none | CatalogResponse; 200. |
| `GET /dashboard/national` | viewer | none | DashboardResponse; 200. |
| `GET /metrics/offline-share` | viewer | none | MetricResponse; 200. |
| `GET /datasets/{dataset_key}/preview` | viewer | none | PreviewResponse; 200. |
| `GET /datasets/{dataset_key}/facilities` | analyst | none | FacilityOptions; 200. |
| `GET /datasets/{dataset_key}/generators` | analyst | none | GeneratorOptions; 200. |
| `POST /queries` | analyst | QueryRequest | QueryResponse; 200. |
| `POST /refresh-runs` | admin | EmptyRequest | ActionReceipt; 202 on new background acceptance, 200 replay. |
| `GET /refresh-runs` | admin | none | RunList; 200. |
| `GET /refresh-runs/{run_id}` | admin | none | Run; 200. |
| `POST /refresh-runs/{run_id}/rerun` | admin | EmptyRequest | ActionReceipt; 202 on new background acceptance, 200 replay. |
| `DELETE /refresh-runs/{run_id}/warning` | admin | none | ActionReceipt; 200. |
| `GET /candidates/{version_id}` | admin | none | Candidate; 200. |
| `POST /candidates/{version_id}/approval` | admin | EmptyRequest | ActionReceipt; 202 on new background acceptance, 200 replay. |
| `POST /candidates/{version_id}/publication-retry` | admin | EmptyRequest | ActionReceipt; 202 on new background acceptance, 200 replay. |
| `POST /candidates/{version_id}/discard` | admin | EmptyRequest | ActionReceipt; 200. |

## Detailed API contract

The supplied design fixes user-visible behavior. The field schemas, names, bounded defaults, command receipts, and additional persistence fields below are AI-authored completion details under alayala's request to fill missing requests and responses. They have not been independently runtime-tested or selected one by one. They must preserve the approved flow. A19 selects current Clerk verification, the SQL function set and per-query containers in the separate [security contract](security-contract.md). Detailed token/parser/container configuration still requires implementation and verification.

[openapi.json](openapi.json) is the exact machine-readable HTTP shape, using OpenAPI 3.1.1. The field reference below is generated from that file. This prose defines cross-field and transaction rules that JSON Schema alone cannot establish. [A16](../DECISIONS.md#a16--approved-api-flow-and-detailed-contract) records precedence; [schema.md](schema.md) defines persistence and unchanged analytical semantics. A17 remains the sole dependency-version decision.

### Shared transport and values

All paths below are relative to `/api/v1`. Require a verified Clerk identity and server-side permission for every operation. Use HTTPS outside localhost. JSON bodies use `application/json`; errors use `application/problem+json`. Reject unknown body fields and unsupported query parameters. Reject a nonempty body on GET or the warning DELETE. Empty-body command POSTs require `{}`. Limit JSON input to 64 KiB and SQL to 16 KiB encoded UTF-8. These are accepted input limits under A19, not performance measurements.

Every response includes a server-generated `X-Request-ID` and `Cache-Control: no-store`. For a permitted cross-origin frontend, expose `ETag`, `Location`, `Retry-After`, and `X-Request-ID`; allow the required `Authorization`, `Content-Type`, `If-Match`, and `Idempotency-Key` request headers and GET/PUT/POST/DELETE/OPTIONS methods. OPTIONS is transport preflight, not an additional product operation; the origin allowlist remains part of security configuration. IDs are UUID strings, except Clerk IDs and preserved EIA IDs. Dates are `YYYY-MM-DD`; event times are UTC RFC 3339 with `Z`. Revision and potentially large counts are decimal strings. Exact measurements and SQL numeric results are decimal strings; booleans remain JSON booleans. Null is never replaced with zero. Reject unsupported nested/binary SQL output instead of lossy conversion. Response times/counts used only for bounded UI controls are JSON integers as declared in OpenAPI.

Every analytical response contains one `Publication` object with publication and version IDs, observation bounds, latest observation date, and publication time. Resolve the active publication once. Catalog readiness/freshness and `/me` must describe a consistent publication snapshot within that request. A public caller cannot choose a storage path or arbitrary historical version.

### App entry and capabilities

`GET /me` has no request body or parameters. `data_ready` means an active publication exists; `publication` is null exactly when `data_ready` is false. A dependency outage returns an error, not a false claim that the application has no publication.

| Role and state | `landing_screen` | `admin_context` |
|---|---|---|
| Viewer or Analyst, no publication | `waiting` | null |
| Admin, setup incomplete | `setup` | Shared setup status, blocker, current active run, and actions. |
| Admin, setup complete and no publication | `refresh_runs` | First refresh/recovery controls remain available. |
| Viewer, published data | `national_dashboard` | null |
| Analyst or Admin, published data | `explorer` | Admin only; null for Analyst. |

Capabilities are server-derived stable strings. Viewer receives `national:read`, `catalog:read`, and `preview:national`. Analyst adds `preview:detail` and `sql:execute`. Admin adds `settings:read`, `settings:write`, `refresh:read`, `refresh:start`, `refresh:recover`, and `candidate:review`. A capability permits an action type; current run state may still disable it. `actions` always includes the relevant action with `enabled` and a nullable `reason_code`. The server rechecks on submission; action flags are not authority.

### Setup and daily schedule

`PUT /settings` accepts exactly `schedule_enabled` (boolean), `daily_time` (`HH:mm`), and `timezone` (valid IANA name). All three are required even when scheduling is disabled. No `publication_mode` is accepted. Invalid legacy fields return `422 invalid_request`. `GET /settings` returns these values, setup timestamp, revision, update timestamp and actor. Before setup, schedule is disabled, time/timezone/setup timestamp and actor are null, and revision is `"0"`.

GET returns `ETag: "settings-<revision>"`; PUT requires the same value in `If-Match`. Missing is `428 precondition_required`, stale is `412 revision_mismatch`. Compare-and-swap, setup completion, revision increment, and actor attribution commit in one transaction. Setup completion is written only once. PUT never enqueues a refresh. If the response is lost, GET settings and reconcile; blindly replaying a stale revision must not overwrite later changes.

`GET /settings/schedule-status` returns the current settings revision, next scheduled check in UTC and local offset form, timezone, evaluation time, eligibility now, and one blocker. When setup is complete and scheduling enabled, compute `next_check_at` strictly after `evaluated_at` even if a run/warning currently blocks work. Otherwise both next-check values are null. `eligible_now` excludes the clock-due test; it means setup/enabled/admission conditions currently permit work. A next-check value is not a promise of refresh acceptance.

For a single blocker choose this order: `setup_required`, `schedule_disabled`, then the current lifecycle/failure blocker. Admission blockers are `refresh_active`, `review_required`, `publication_in_progress`, or `failure_unresolved`. A publication failure's unresolved warning takes precedence over a generic active-work label. Reevaluate under the admission lock when an occurrence is actually due. Skip blocked/missed occurrences without recording a successful run or building a backlog. Use the first UTC occurrence of a repeated local time; skip a nonexistent local time. Settings changes affect future occurrences only.

### Catalog and national dashboard

`GET /catalog` returns only permitted dataset definitions, typed columns, units, daily keys, filters, the national metric definition, and freshness. Before publication it still returns those permitted static definitions with `data_ready: false` and `publication: null`. Viewer freshness contains only global refresh status/times; no candidate IDs, actor IDs, facility/generator counts, raw diagnostics, or run error details.

`GET /dashboard/national` accepts either `preset=30d|90d|1y` or both `start` and `end`. Omitting all parameters defaults to `30d`. Combining preset with custom dates, supplying only one custom bound, reversing dates, or exceeding 366 inclusive custom dates returns `422`. For this detailed contract `1y` is a rolling **365-day** window; label it “Last 365 days” in the UI. Presets end at `publication.latest_observation_date`. Custom ranges are not silently clipped to published coverage. Bounds outside coverage yield missing display points.

`summary` represents the requested range's **end date** for all cards: `capacity`, `outage`, source `percentOutage`, and calculated `offline_share_percent`. `days` has exactly one display point per calendar date, ascending, including null points for missing dates. These display points are not fabricated stored analytical rows. Summary must equal the matching last day point. Do not silently substitute a different date or pool several dates into a daily metric. National diagnostics only are exposed here.

`GET /metrics/offline-share?period=YYYY-MM-DD` returns the same national calculated metric as the dashboard at that date and publication. Calculate `100 × outage / capacity` using decimal arithmetic and round only the displayed percentage, half-up to two places. Preserve signed/out-of-range observations and national diagnostics. Missing date: null value with `not_reported`. Zero capacity: null value with `zero_capacity`, while capacity/outage source values remain available on the dashboard. No publication: `409 data_unavailable`, not an empty successful metric.

### Preview and filter choices

Preview accepts `start`, `end`, exact `facility`, exact `generator`, `limit` and `cursor`. Defaults are the last 30 dates ending at the latest observation; a missing individual bound uses the respective default and still must produce an ordered range of at most 366 dates. `limit` defaults to 100, maximum 1,000. Facility filters require a detailed dataset. A generator filter requires `generator_outages` and an exact facility. Unknown entity IDs produce empty results. Unsupported filters return `422`. Unknown or unauthorized dataset keys return the same safe `404 dataset_not_found`.

Rows are arrays aligned with ordered `columns`, not objects that would lose duplicate SQL labels. Preview includes every A9 column for that dataset in contract order. Every row length equals column count and every cell agrees with its column type/nullability. Sort by the complete A9 daily key ascending using fixed binary string ordering for source IDs. Use typed engine expressions for filter values, never string concatenation. `returned_rows` equals row-array length; `reason` is `not_reported` only when an empty preview reflects no matching observations. A nonempty preview has null reason.

For next-page detection read at most `limit + 1`, return at most `limit`, and include `next_cursor` only when another row exists. Sign/authenticate the opaque cursor; bind purpose, dataset, resolved bounds/filters, page size, last daily key, and publication ID. It is not an authorization token. Reauthorize every page. Tampered/mismatched cursors return `422 invalid_cursor`; changed active publication returns `409 publication_changed` with an instruction to restart. No arbitrary publication selection through cursor fields.

Facility choices are available only for `facility_outages` and `generator_outages`. Generator choices only for `generator_outages`, with required `facility`. These endpoints are Analyst/Admin only. They use the same bounded date defaults and published version as preview. Facility `search` is an optional literal case-insensitive substring of ID or name, maximum 100 characters; wildcard characters are ordinary text. Option pages default to 50 and cap at 100. Sort by exact source ID; retain leading zeros. Use the latest non-null facility name within the range; no matching name means null. The opaque choice cursor additionally binds search/parent facility. No entity registry is inferred beyond observations in that published range.

### SQL request and response

`POST /queries` accepts only `{ "sql": "..." }` for Analyst/Admin. Preview selections and dashboard filters do not alter this text. A Viewer is denied before SQL parsing or file access. Reject blank SQL. The query result returns ordered column metadata, rows, `returned_rows`, `truncated`, elapsed milliseconds, publication, and permitted diagnostics. No query-history/export feature is introduced.

Return at most 1,000 rows and set `truncated` only if an extra row exists after the query's own LIMIT. No SQL result pagination is defined. Cap columns at 128 and encoded analytical output at 5 MiB. An empty SQL result is a successful empty result; do not label it missing source data merely because a predicate matched nothing. Parse/permission/limit failures return a safe problem, never partial successful data. [A18](../DECISIONS.md#a18--sql-scope-by-stage-closed) accepts single-table SELECT for required v1, with joins/CTEs/subqueries optional only after the core works and tests pass. [A19](security-contract.md#sql-policy) selects functions, arithmetic/CASE and container isolation; exact parser/type configuration and enforcement still require implementation and verification. An API schema is not authorization to execute arbitrary SQL.

### Analytical limits and retries

A19 selects these **provisional analytical limits**, pending local measurements: 1,000 SQL output rows, 5 MiB encoded response, 30 seconds including trusted file download/read time and query execution, 1 GiB per query container, two active analytical requests per user and four across the deployment. Apply relevant limits to SQL, previews, national dashboard/metric calculations and analytical filter choices; preserve each endpoint's pagination. The SQL output cap must not cap the rows used for aggregates. Time, memory or output-size failure returns an error without partial results.

Accepted input/rate limits: 64 KiB JSON body, 16 KiB SQL input measured as encoded UTF-8, and initially 30 analytical requests per user per minute across processes. Progress/status polling is excluded from that analytical rate counter, but still requires authentication and authorization. Excess rate or active concurrency returns the existing `429 rate_limited` busy response with `Retry-After`; it does not enqueue analytical work. Limit settings are server-controlled. PostgreSQL transactions reserve shared query slots; release only after execution has ended or been stopped. See [shared admission](security-contract.md#shared-query-admission) for recovery and cleanup rules.

Temporary external failures allow at most three total attempts, with waits of one and three seconds before attempts two and three. All attempts and waits fit the operation's existing deadline; retries never reset the analytical deadline. Do not retry invalid SQL, denied access, or failed validation. Retried effects reuse the same durable identity. This automatic policy does not change the explicit Admin rerun/publication-retry rules below. Refresh-stage deadlines remain to be selected; the 30-second analytical deadline is not a full-refresh deadline.

### Refresh history and progress

`POST /refresh-runs` takes `{}` and a required UUID `Idempotency-Key`. It accepts no actor, policy, window, queue, or file path. Use A9's supported start and newest-national end strategy; discovery occurs in the worker. Require setup and no current lifecycle/failure blocker. Atomically reserve the shared admission slot, create run, record command receipt and enqueue intent in PostgreSQL. Return `202` only after commit, with `Location` equal to `status_url` and an initial polling interval. Redis dispatch can follow later.

`GET /refresh-runs` paginates summaries by descending `run_seq`, default 20, cap 100. A cursor binds the first page's maximum sequence and last returned sequence so newly created runs do not shift history pages. Current active run, unresolved warning, blocker and actions are returned independently on every page; they must not disappear because history pagination excludes newer runs. Return nulls for absent current objects.

`GET /refresh-runs/{run_id}` returns full run fields, its current candidate reference, warning, actions and a bounded page of step attempts. `steps_limit` defaults/caps at 100; `steps_cursor` continues ascending immutable per-run `step_seq` order. The cursor binds run, page limit, last sequence, and the first page's maximum step sequence; later attempts require restarting attempt pagination. Current run/candidate/warning/actions remain fresh on every read. Failed attempts are never overwritten by a later retry. The run ETag changes on any public state/action/progress change. Unknown totals remain null; never turn the source facility advertised total into a trusted progress denominator.

`poll_after_seconds` is 2 while `requested`, `running`, or `publishing`, otherwise null. The client polls the same run URL and stops polling on waiting/failure/terminal states; user-triggered refresh of status is still possible. Closing the screen does not cancel the run. A failed refresh does not reset setup or remove the published version. No cancellation endpoint is added.

### Candidate side panel and warnings

`GET /candidates/{version_id}` is Admin-only and supplies the run page side panel. It returns coverage, validation state, the complete 16 required-check slots when available, diagnostic summaries, frozen warning count/digest, review status, approval, publication generation/attempt/outcome, associated operational failure warning, disposition, and action eligibility. Before checks finish, `checks` contains only actual persisted results and `passed_required_count` is measured; a missing slot remains missing and cannot authorize publication.

Distinguish two meanings of warning. **Data-quality warnings** belong to a successfully validated immutable candidate and require review. **Failure warnings** record exhausted/permanent operational failures and block a new lifecycle until resolved. Resolving an operational warning never changes source values, validation checks, or data-quality warnings.

`approval_required` is null until required checks and the diagnostic pass have completed and frozen for the exact candidate; then it is true exactly when review warnings exist. `review_status` becomes `required`, `not_required`, or `approved` accordingly. A candidate with no warnings queues publication automatically. A reviewable candidate holds the admission slot while it awaits approval. Never offer an approval that could bypass a required failure, missing check, changed manifest, discarded/superseded disposition, or already published version.

Diagnostics are grouped by registered code and dataset scope, at most 32 summaries; include exact affected counts. Do not truncate a set in a way that hides review warnings. A registry change exceeding this bound needs a versioned schema/checkset change. Long/raw evidence stays in protected storage, not these APIs. The diagnostic severity rules and A5's suppressed known metadata issue are in [schema.md](schema.md#5-validation-and-readiness). Freeze warning classification with the validation attempt; approval binds manifest, validation attempt, and warning digest.

### Commands and concurrency

Every Admin command POST and warning DELETE requires a UUID `Idempotency-Key`. Candidate commands additionally require the candidate's exact `If-Match: "candidate-<revision>"`; run recovery commands require `If-Match: "run-<revision>"`. Missing precondition is `428`; stale state is `412`. A present malformed ETag is `422`; a valid tag for another resource or a wildcard is not accepted. Settings keep their own revision rule. These preconditions supplement state/permission checks.

Within one transaction, check the shared admission row, target run/version, and operation receipt in a consistent order. Claims and worker commits use the same lock/fence rules. Verify current actor authority before accessing any stored receipt. A unique idempotency key is bound to actor, action, target, and canonical body fingerprint. Same key and intent returns the original operation ID/acceptance time/tracking reference, with `replayed: true` and `200`, before checking an obsolete ETag. Conflicting reuse returns `409 idempotency_conflict` without exposing another actor's resource. Retain receipts throughout v1 history; no time-based duplicate window is selected. A failed transaction stores neither receipt nor effects. In-progress conflicting execution waits only within a bounded DB lock timeout, then returns retryable `503`.

A new `202` response has `result: queued` and `replayed: false`. A completed warning resolution or discard returns `200` with `result: warning_resolved` or `discarded`. The receipt describes the accepted action; `status_url` gives current state and must be polled rather than interpreting receipt replay as fresh work. New retry intent requires a new key. No actor ID is accepted in any command body.

| Command | Preconditions | Atomic result |
|---|---|---|
| Run again | Failed refresh or publication-failed run, unresolved operational warning, no other lifecycle, current run revision. | Resolve warning with `rerun`, abandon old unpublished candidate, release old slot, create new run linked by `rerun_of_run_id`, reserve new slot and write refresh outbox/receipt. Return new run ID. |
| Delete warning | Unresolved warning on failed or publication-failed work; no active writer; current run revision. | Soft-resolve warning with actor/time, abandon unpublished candidate and release admission slot. Preserve all history; start no work. |
| Approve | Required review, exact validated manifest/checkset/warning digest, no publication already underway, current candidate revision. | Save one approval, transition to publishing, queue publication and receipt together. Keep slot. |
| Publication retry | `publication_failed`, intact validated candidate, correct bound approval if needed, current candidate revision, no writer. | Resolve current warning as `publication_retry`, increment publication generation/fence, rearm publication outbox, transition to publishing, keep slot. Do not extract or rebuild files. |
| Discard | `awaiting_approval` or `publication_failed`, unpublished active disposition, current candidate revision, no writer. | Mark candidate discarded permanently, mark run discarded, resolve any associated warning and release slot. No physical deletion. |

Publication retry requires intact validated evidence and a recoverable operational error; a recorded integrity/coverage/contract violation disables it and requires abandonment/new work. The worker rechecks actual files after acceptance. Forbid discard while work is actively publishing/preparing and after publication. If a worker crashes, durable recovery must first establish the old lease/fence is no longer authoritative. Deleting a warning and run-again must increment/invalidate any old execution fence before abandoning the candidate. Two simultaneous Admin actions cannot both win. Recheck eligibility under the transaction lock; do not trust a previously rendered enabled button.

Warning resolution does not disable the daily schedule. After a delete/discard releases the blocker, a future scheduled check may admit new work. Do not auto-start missed occurrences. If retry publication fails again, create a new unresolved warning; the previously resolved warning and its actor/time remain in history. Automatic publication retries remain automatic, without introducing a new approval requirement.

### Lifecycle and action eligibility

| Run state | Meaning | Allowed recovery/review commands |
|---|---|---|
| `requested` / `running` | Refresh accepted or preparing/validating. | None. Automatic bounded retries and fenced recovery only. |
| `awaiting_approval` | Required checks passed; frozen review warnings exist. | Approve or discard. |
| `publishing` | Publication accepted/queued/running. | None while publication is active. |
| `publication_failed` | Publication attempt budget exhausted; run retains the eligible frozen candidate and slot. | Publication retry if eligible; run again; delete warning; discard. |
| `failed` | Full refresh/preparation failure; run is terminal and warning blocks new work. | Run again or delete warning while warning unresolved. |
| `succeeded` / `discarded` / `superseded` | Terminal outcome. | No new mutation. Same-key receipt replay remains safe. |

`publication_failed` has null run `finished_at`; its failed attempt has its own finished time. A full refresh failure is terminal; rerun creates a new run, never reopens it. Abandoning a publication-failed run through warning deletion or rerun closes it as `failed`; direct candidate discard closes it as `discarded`. A previously failed run keeps its failure status even after warning resolution. Published versions never become discarded.

The singleton admission slot remains held through validation, required review, publication, and unresolved failure. At most one unresolved operational warning exists globally. Releasing the slot, resolving the warning, and abandoning the candidate happen atomically. Successful publication commits the event, pointer, run success, and slot release together. Queue-wide concurrency settings alone do not prove this business invariant.

### Safe errors and precedence

Use RFC 9457 fields plus `code`, `request_id`, `errors`, `blocker`, and `current_revision`. Empty field-error lists are `[]`; absent blocker/revision is null. Field errors name a field and safe reason, never rejected values. Authentication and permission checks precede protected resource lookup; an unknown role returns `403`. Unknown resources return `404` only after applicable capability checks. Validate bounded syntax before analytical reads; no publication returns `409 data_unavailable` after authorization and applicable SQL policy checks.

| Status | Stable codes and client action |
|---|---|
| 400 / 415 / 422 | `invalid_json` / `unsupported_media_type` / `invalid_request`, `invalid_cursor`, `sql_not_allowed`, `idempotency_key_required`; correct the input. |
| 401 / 403 / 404 | `authentication_required`, `invalid_session` / `forbidden` / `resource_not_found`, `dataset_not_found`; sign in or stop the forbidden lookup. |
| 409 | `data_unavailable`, `publication_changed`, `setup_required`, `refresh_blocked`, `idempotency_conflict`, `action_not_allowed`, `candidate_ineligible`; use readiness/state information or restart pagination. |
| 412 / 428 / 413 | `revision_mismatch` / `precondition_required` / `request_too_large`; reload target state, supply ETag, or reduce input. |
| 429 / 500 / 503 / 504 | `rate_limited` / `internal_error` / `auth_unavailable`, `dependency_unavailable`, `query_resource_limit` / `query_timeout`; obey retry guidance. `query_failed` uses 422 for a safe user-correctable engine expression/type error. |

Return `WWW-Authenticate: Bearer` with 401 and `Retry-After` with 429. Provide bounded retry seconds on 503 only when known. Never include raw SQL, SQL-engine suggestions about hidden tables, credentials, object paths, raw source responses, or stack traces. A dependency outage after an accepted command must not be described as loss of its durable request. Unexpected errors fail closed.

### Synthetic request and response examples

These values illustrate JSON transport only; they are not EIA evidence, real users, or runtime test results. The same examples also appear in OpenAPI.

#### Complete setup request

```json
{
  "schedule_enabled": true,
  "daily_time": "08:00",
  "timezone": "America/Merida"
}
```

#### Saved settings response

```json
{
  "setup_completed_at": "2026-10-03T12:00:00Z",
  "schedule_enabled": true,
  "daily_time": "08:00",
  "timezone": "America/Merida",
  "revision": "1",
  "updated_at": "2026-10-03T12:00:00Z",
  "updated_by": "user_example_admin"
}
```

#### Viewer waiting for first publication

```json
{
  "user_id": "user_example_viewer",
  "role": "viewer",
  "capabilities": [
    "national:read",
    "catalog:read",
    "preview:national"
  ],
  "data_ready": false,
  "landing_screen": "waiting",
  "publication": null,
  "admin_context": null
}
```

#### Accepted refresh response

```json
{
  "operation_id": "00000000-0000-4000-8000-000000000003",
  "action": "start_refresh",
  "accepted_at": "2026-10-03T12:00:00Z",
  "run_id": "00000000-0000-4000-8000-000000000004",
  "version_id": null,
  "status_url": "/api/v1/refresh-runs/00000000-0000-4000-8000-000000000004",
  "result": "queued",
  "replayed": false
}
```

#### Blocked refresh error

```json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "Resolve the failed refresh before starting another.",
  "code": "refresh_blocked",
  "request_id": "00000000-0000-4000-8000-000000000005",
  "errors": [],
  "blocker": {
    "code": "failure_unresolved",
    "message": "Review the failed refresh.",
    "run_id": "00000000-0000-4000-8000-000000000004",
    "version_id": null,
    "warning_id": "00000000-0000-4000-8000-000000000006"
  },
  "current_revision": null
}
```

#### National preview response

```json
{
  "publication": {
    "publication_event_id": "00000000-0000-4000-8000-000000000001",
    "version_id": "00000000-0000-4000-8000-000000000002",
    "published_at": "2026-10-03T12:00:00Z",
    "coverage_start": "2024-10-02",
    "coverage_end": "2026-10-02",
    "latest_observation_date": "2026-10-02"
  },
  "dataset_key": "national_outages",
  "range": {
    "start": "2026-10-02",
    "end": "2026-10-02"
  },
  "columns": [
    {
      "name": "period",
      "type": "date",
      "nullable": false,
      "unit": null
    },
    {
      "name": "capacity",
      "type": "decimal",
      "nullable": false,
      "unit": "MW"
    },
    {
      "name": "outage",
      "type": "decimal",
      "nullable": false,
      "unit": "MW"
    },
    {
      "name": "percentOutage",
      "type": "decimal",
      "nullable": true,
      "unit": "percent"
    }
  ],
  "rows": [
    [
      "2026-10-02",
      "100.000000",
      "25.000000",
      "25.000000"
    ]
  ],
  "returned_rows": 1,
  "next_cursor": null,
  "reason": null,
  "diagnostics": []
}
```

#### SQL request

```json
{
  "sql": "SELECT period, outage FROM national_outages ORDER BY period LIMIT 10"
}
```

#### Metric response

```json
{
  "publication": {
    "publication_event_id": "00000000-0000-4000-8000-000000000001",
    "version_id": "00000000-0000-4000-8000-000000000002",
    "published_at": "2026-10-03T12:00:00Z",
    "coverage_start": "2024-10-02",
    "coverage_end": "2026-10-02",
    "latest_observation_date": "2026-10-02"
  },
  "period": "2026-10-02",
  "metric": {
    "value": "25.00",
    "reason": null
  },
  "diagnostics": []
}
```

## Exact field reference

This reference is generated from [OpenAPI](openapi.json). All response object fields are required unless marked optional; nullable is separate from optional. Objects reject unspecified fields in this version. Domain constraints below supplement JSON Schema.

### EmptyRequest

| Field | Type | Required | Constraints |
|---|---|---|---|

### Publication

| Field | Type | Required | Constraints |
|---|---|---|---|
| `publication_event_id` | string | yes | format=uuid |
| `version_id` | string | yes | format=uuid |
| `published_at` | string | yes | pattern=Z$; format=date-time |
| `coverage_start` | string | yes | format=date |
| `coverage_end` | string | yes | format=date |
| `latest_observation_date` | string | yes | format=date |

### Action

| Field | Type | Required | Constraints |
|---|---|---|---|
| `action` | ActionName | yes | See type definition and endpoint rules. |
| `enabled` | boolean | yes | See type definition and endpoint rules. |
| `reason_code` | BlockCode or null | yes | See type definition and endpoint rules. |

### Blocker

| Field | Type | Required | Constraints |
|---|---|---|---|
| `code` | BlockCode | yes | See type definition and endpoint rules. |
| `message` | string | yes | maxLength=512 |
| `run_id` | string or null | yes | See type definition and endpoint rules. |
| `version_id` | string or null | yes | See type definition and endpoint rules. |
| `warning_id` | string or null | yes | See type definition and endpoint rules. |

### RefreshSummary

| Field | Type | Required | Constraints |
|---|---|---|---|
| `run_id` | string | yes | format=uuid |
| `status` | RunStatus | yes | See type definition and endpoint rules. |
| `requested_at` | string | yes | pattern=Z$; format=date-time |
| `finished_at` | string or null | yes | See type definition and endpoint rules. |

### Freshness

| Field | Type | Required | Constraints |
|---|---|---|---|
| `latest_observation_date` | string or null | yes | See type definition and endpoint rules. |
| `published_at` | string or null | yes | See type definition and endpoint rules. |
| `last_refresh` | object or null | yes | See type definition and endpoint rules. |

### AdminContext

| Field | Type | Required | Constraints |
|---|---|---|---|
| `setup_completed` | boolean | yes | See type definition and endpoint rules. |
| `refresh_blocker` | Blocker or null | yes | See type definition and endpoint rules. |
| `active_run` | RefreshSummary or null | yes | See type definition and endpoint rules. |
| `actions` | array of Action | yes | maxItems=6 |

### MeResponse

| Field | Type | Required | Constraints |
|---|---|---|---|
| `user_id` | string | yes | maxLength=128 |
| `role` | string | yes | enum=['viewer', 'analyst', 'admin'] |
| `capabilities` | array of Capability | yes | maxItems=11 |
| `data_ready` | boolean | yes | See type definition and endpoint rules. |
| `landing_screen` | string | yes | enum=['waiting', 'setup', 'refresh_runs', 'national_dashboard', 'explorer'] |
| `publication` | Publication or null | yes | See type definition and endpoint rules. |
| `admin_context` | AdminContext or null | yes | See type definition and endpoint rules. |

### SettingsRequest

| Field | Type | Required | Constraints |
|---|---|---|---|
| `schedule_enabled` | boolean | yes | See type definition and endpoint rules. |
| `daily_time` | DailyTime | yes | See type definition and endpoint rules. |
| `timezone` | Timezone | yes | See type definition and endpoint rules. |

### SettingsResponse

| Field | Type | Required | Constraints |
|---|---|---|---|
| `setup_completed_at` | string or null | yes | See type definition and endpoint rules. |
| `schedule_enabled` | boolean | yes | See type definition and endpoint rules. |
| `daily_time` | DailyTime or null | yes | See type definition and endpoint rules. |
| `timezone` | Timezone or null | yes | See type definition and endpoint rules. |
| `revision` | Counter | yes | See type definition and endpoint rules. |
| `updated_at` | string | yes | pattern=Z$; format=date-time |
| `updated_by` | string or null | yes | See type definition and endpoint rules. |

### ScheduleStatus

| Field | Type | Required | Constraints |
|---|---|---|---|
| `settings_revision` | Counter | yes | See type definition and endpoint rules. |
| `schedule_enabled` | boolean | yes | See type definition and endpoint rules. |
| `next_check_at` | string or null | yes | See type definition and endpoint rules. |
| `next_check_local` | string or null | yes | See type definition and endpoint rules. |
| `timezone` | Timezone or null | yes | See type definition and endpoint rules. |
| `evaluated_at` | string | yes | pattern=Z$; format=date-time |
| `eligible_now` | boolean | yes | See type definition and endpoint rules. |
| `blocker` | Blocker or null | yes | See type definition and endpoint rules. |

### Column

| Field | Type | Required | Constraints |
|---|---|---|---|
| `name` | string | yes | maxLength=128 |
| `type` | string | yes | enum=['string', 'date', 'timestamp', 'decimal', 'integer', 'boolean'] |
| `nullable` | boolean | yes | See type definition and endpoint rules. |
| `unit` | string or null | yes | See type definition and endpoint rules. |

### MetricDefinition

| Field | Type | Required | Constraints |
|---|---|---|---|
| `key` | string | yes | enum=['offline_share_percent'] |
| `label` | string | yes | maxLength=512 |
| `unit` | string | yes | enum=['percent'] |
| `formula` | string | yes | See type definition and endpoint rules. |
| `null_reasons` | array of string | yes | maxItems=2 |
| `display_decimal_places` | integer | yes | minimum=2; maximum=2 |

### Dataset

| Field | Type | Required | Constraints |
|---|---|---|---|
| `key` | DatasetKey | yes | See type definition and endpoint rules. |
| `label` | string | yes | maxLength=512 |
| `description` | string | yes | maxLength=512 |
| `daily_key` | array of string | yes | maxItems=3 |
| `columns` | array of Column | yes | maxItems=7 |
| `available_filters` | array of string | yes | maxItems=4 |

### CatalogResponse

| Field | Type | Required | Constraints |
|---|---|---|---|
| `datasets` | array of Dataset | yes | maxItems=3 |
| `metrics` | array of MetricDefinition | yes | maxItems=1 |
| `data_ready` | boolean | yes | See type definition and endpoint rules. |
| `publication` | Publication or null | yes | See type definition and endpoint rules. |
| `freshness` | Freshness | yes | See type definition and endpoint rules. |

### Diagnostic

| Field | Type | Required | Constraints |
|---|---|---|---|
| `code` | string | yes | pattern=^D[0-9]{2}$ |
| `severity` | string | yes | enum=['info', 'warning'] |
| `scope` | string | yes | enum=['national', 'facility', 'generator', 'all'] |
| `message` | string | yes | maxLength=512 |
| `affected_count` | Counter | yes | See type definition and endpoint rules. |

### MetricValue

| Field | Type | Required | Constraints |
|---|---|---|---|
| `value` | string or null | yes | See type definition and endpoint rules. |
| `reason` | string or null | yes | See type definition and endpoint rules. |

### MetricResponse

| Field | Type | Required | Constraints |
|---|---|---|---|
| `publication` | Publication | yes | See type definition and endpoint rules. |
| `period` | string | yes | format=date |
| `metric` | MetricValue | yes | See type definition and endpoint rules. |
| `diagnostics` | array of Diagnostic | yes | maxItems=32 |

### NationalDay

| Field | Type | Required | Constraints |
|---|---|---|---|
| `period` | string | yes | format=date |
| `capacity` | Decimal or null | yes | See type definition and endpoint rules. |
| `outage` | Decimal or null | yes | See type definition and endpoint rules. |
| `percentOutage` | Decimal or null | yes | See type definition and endpoint rules. |
| `offline_share_percent` | string or null | yes | See type definition and endpoint rules. |
| `reason` | string or null | yes | See type definition and endpoint rules. |

### DateRange

| Field | Type | Required | Constraints |
|---|---|---|---|
| `start` | string | yes | format=date |
| `end` | string | yes | format=date |

### DashboardResponse

| Field | Type | Required | Constraints |
|---|---|---|---|
| `publication` | Publication | yes | See type definition and endpoint rules. |
| `range` | DateRange | yes | See type definition and endpoint rules. |
| `summary` | NationalDay | yes | See type definition and endpoint rules. |
| `days` | array of NationalDay | yes | maxItems=366 |
| `diagnostics` | array of Diagnostic | yes | maxItems=32 |
| `freshness` | Freshness | yes | See type definition and endpoint rules. |

### PreviewResponse

| Field | Type | Required | Constraints |
|---|---|---|---|
| `publication` | Publication | yes | See type definition and endpoint rules. |
| `dataset_key` | DatasetKey | yes | See type definition and endpoint rules. |
| `range` | DateRange | yes | See type definition and endpoint rules. |
| `columns` | array of Column | yes | maxItems=7 |
| `rows` | array of array of Cell | yes | maxItems=1000 |
| `returned_rows` | integer | yes | minimum=0; maximum=1000 |
| `next_cursor` | string or null | yes | See type definition and endpoint rules. |
| `reason` | string or null | yes | See type definition and endpoint rules. |
| `diagnostics` | array of Diagnostic | yes | maxItems=32 |

### FacilityOption

| Field | Type | Required | Constraints |
|---|---|---|---|
| `facility` | SourceID | yes | See type definition and endpoint rules. |
| `facilityName` | string or null | yes | See type definition and endpoint rules. |

### GeneratorOption

| Field | Type | Required | Constraints |
|---|---|---|---|
| `facility` | SourceID | yes | See type definition and endpoint rules. |
| `generator` | SourceID | yes | See type definition and endpoint rules. |

### FacilityOptions

| Field | Type | Required | Constraints |
|---|---|---|---|
| `publication` | Publication | yes | See type definition and endpoint rules. |
| `range` | DateRange | yes | See type definition and endpoint rules. |
| `items` | array of FacilityOption | yes | maxItems=100 |
| `next_cursor` | string or null | yes | See type definition and endpoint rules. |

### GeneratorOptions

| Field | Type | Required | Constraints |
|---|---|---|---|
| `publication` | Publication | yes | See type definition and endpoint rules. |
| `range` | DateRange | yes | See type definition and endpoint rules. |
| `facility` | SourceID | yes | See type definition and endpoint rules. |
| `items` | array of GeneratorOption | yes | maxItems=100 |
| `next_cursor` | string or null | yes | See type definition and endpoint rules. |

### QueryRequest

| Field | Type | Required | Constraints |
|---|---|---|---|
| `sql` | string | yes | maxLength=16384 |

### QueryResponse

| Field | Type | Required | Constraints |
|---|---|---|---|
| `publication` | Publication | yes | See type definition and endpoint rules. |
| `columns` | array of Column | yes | maxItems=128 |
| `rows` | array of array of Cell | yes | maxItems=1000 |
| `returned_rows` | integer | yes | minimum=0; maximum=1000 |
| `truncated` | boolean | yes | See type definition and endpoint rules. |
| `execution_ms` | integer | yes | minimum=0 |
| `diagnostics` | array of Diagnostic | yes | maxItems=32 |

### FailureWarning

| Field | Type | Required | Constraints |
|---|---|---|---|
| `warning_id` | string | yes | format=uuid |
| `run_id` | string | yes | format=uuid |
| `version_id` | string or null | yes | See type definition and endpoint rules. |
| `stage` | string | yes | enum=['extract', 'prepare', 'validate', 'publish', 'dispatch'] |
| `code` | string | yes | maxLength=64 |
| `message` | string | yes | maxLength=512 |
| `created_at` | string | yes | pattern=Z$; format=date-time |
| `resolved_at` | string or null | yes | See type definition and endpoint rules. |
| `resolution` | string or null | yes | See type definition and endpoint rules. |
| `resolved_by` | string or null | yes | See type definition and endpoint rules. |

### Progress

| Field | Type | Required | Constraints |
|---|---|---|---|
| `processed_count` | Counter | yes | See type definition and endpoint rules. |
| `total_count` | Counter or null | yes | See type definition and endpoint rules. |
| `unit` | string | yes | enum=['rows', 'files', 'checks', 'tasks'] |

### Step

| Field | Type | Required | Constraints |
|---|---|---|---|
| `step_id` | string | yes | format=uuid |
| `step_seq` | Counter | yes | See type definition and endpoint rules. |
| `stage` | string | yes | enum=['extract', 'prepare', 'validate', 'publish'] |
| `work_key` | string | yes | maxLength=128 |
| `attempt` | integer | yes | minimum=1 |
| `status` | string | yes | enum=['pending', 'running', 'succeeded', 'failed', 'abandoned'] |
| `started_at` | string or null | yes | See type definition and endpoint rules. |
| `finished_at` | string or null | yes | See type definition and endpoint rules. |
| `progress` | Progress | yes | See type definition and endpoint rules. |
| `error_code` | string or null | yes | See type definition and endpoint rules. |
| `error_summary` | string or null | yes | See type definition and endpoint rules. |

### CandidateRef

| Field | Type | Required | Constraints |
|---|---|---|---|
| `version_id` | string | yes | format=uuid |
| `review_status` | string | yes | enum=['not_ready', 'not_required', 'required', 'approved', 'discarded'] |
| `publication_status` | string | yes | enum=['not_started', 'queued', 'publishing', 'failed', 'published', 'blocked'] |

### Run

| Field | Type | Required | Constraints |
|---|---|---|---|
| `run_id` | string | yes | format=uuid |
| `run_seq` | Counter | yes | See type definition and endpoint rules. |
| `revision` | Counter | yes | See type definition and endpoint rules. |
| `trigger_kind` | string | yes | enum=['manual', 'scheduled', 'rerun'] |
| `requested_by` | string or null | yes | See type definition and endpoint rules. |
| `rerun_of_run_id` | string or null | yes | See type definition and endpoint rules. |
| `requested_at` | string | yes | pattern=Z$; format=date-time |
| `started_at` | string or null | yes | See type definition and endpoint rules. |
| `finished_at` | string or null | yes | See type definition and endpoint rules. |
| `status` | RunStatus | yes | See type definition and endpoint rules. |
| `settings_revision` | Counter | yes | See type definition and endpoint rules. |
| `workflow_policy` | string | yes | enum=['warnings-v1'] |
| `requested_start` | string | yes | format=date |
| `requested_end` | string or null | yes | See type definition and endpoint rules. |
| `candidate` | CandidateRef or null | yes | See type definition and endpoint rules. |
| `warning` | FailureWarning or null | yes | See type definition and endpoint rules. |
| `actions` | array of Action | yes | maxItems=6 |
| `steps` | array of Step | yes | maxItems=100 |
| `next_steps_cursor` | string or null | yes | See type definition and endpoint rules. |
| `poll_after_seconds` | integer or null | yes | See type definition and endpoint rules. |

### RunList

| Field | Type | Required | Constraints |
|---|---|---|---|
| `items` | array of RefreshSummary | yes | maxItems=100 |
| `next_cursor` | string or null | yes | See type definition and endpoint rules. |
| `active_run` | RefreshSummary or null | yes | See type definition and endpoint rules. |
| `unresolved_warning` | FailureWarning or null | yes | See type definition and endpoint rules. |
| `blocker` | Blocker or null | yes | See type definition and endpoint rules. |
| `actions` | array of Action | yes | maxItems=6 |

### ValidationCheck

| Field | Type | Required | Constraints |
|---|---|---|---|
| `code` | string | yes | pattern=^V[0-9]{2}$ |
| `scope` | string | yes | enum=['national', 'facility', 'generator', 'all'] |
| `status` | string | yes | enum=['pass', 'fail', 'error'] |
| `checked_count` | Counter | yes | See type definition and endpoint rules. |
| `failed_count` | Counter | yes | See type definition and endpoint rules. |
| `checked_at` | string | yes | pattern=Z$; format=date-time |
| `message` | string | yes | maxLength=512 |

### Validation

| Field | Type | Required | Constraints |
|---|---|---|---|
| `status` | string | yes | enum=['pending', 'running', 'passed', 'failed', 'incomplete'] |
| `step_id` | string or null | yes | See type definition and endpoint rules. |
| `checkset` | string | yes | enum=['trinity-data-v1'] |
| `expected_required_count` | integer | yes | minimum=16; maximum=16 |
| `passed_required_count` | integer | yes | minimum=0; maximum=16 |
| `checks` | array of ValidationCheck | yes | maxItems=16 |

### Approval

| Field | Type | Required | Constraints |
|---|---|---|---|
| `approval_id` | string | yes | format=uuid |
| `approved_by` | string | yes | maxLength=128 |
| `approved_at` | string | yes | pattern=Z$; format=date-time |
| `manifest_sha256` | string | yes | pattern=^[0-9a-f]{64}$ |
| `validation_step_id` | string | yes | format=uuid |
| `review_warning_digest` | string | yes | pattern=^[0-9a-f]{64}$ |

### PublicationProgress

| Field | Type | Required | Constraints |
|---|---|---|---|
| `status` | string | yes | enum=['not_started', 'queued', 'publishing', 'failed', 'published', 'blocked'] |
| `generation` | Counter | yes | See type definition and endpoint rules. |
| `attempt` | integer | yes | minimum=0 |
| `error_code` | string or null | yes | See type definition and endpoint rules. |
| `error_summary` | string or null | yes | See type definition and endpoint rules. |
| `published_at` | string or null | yes | See type definition and endpoint rules. |
| `publication_event_id` | string or null | yes | See type definition and endpoint rules. |

### Candidate

| Field | Type | Required | Constraints |
|---|---|---|---|
| `version_id` | string | yes | format=uuid |
| `run_id` | string | yes | format=uuid |
| `revision` | Counter | yes | See type definition and endpoint rules. |
| `validation_status` | string | yes | enum=['preparing', 'validating', 'validated', 'rejected'] |
| `disposition` | string | yes | enum=['active', 'discarded', 'superseded'] |
| `created_at` | string | yes | pattern=Z$; format=date-time |
| `coverage` | DateRange | yes | See type definition and endpoint rules. |
| `latest_observation_date` | string | yes | format=date |
| `manifest_sha256` | string or null | yes | See type definition and endpoint rules. |
| `validation` | Validation | yes | See type definition and endpoint rules. |
| `diagnostics` | array of Diagnostic | yes | maxItems=32 |
| `review_warning_count` | Counter or null | yes | See type definition and endpoint rules. |
| `review_warning_digest` | string or null | yes | See type definition and endpoint rules. |
| `review_status` | string | yes | enum=['not_ready', 'not_required', 'required', 'approved', 'discarded'] |
| `approval_required` | boolean or null | yes | See type definition and endpoint rules. |
| `approval` | Approval or null | yes | See type definition and endpoint rules. |
| `publication` | PublicationProgress | yes | See type definition and endpoint rules. |
| `failure_warning` | FailureWarning or null | yes | See type definition and endpoint rules. |
| `discarded_at` | string or null | yes | See type definition and endpoint rules. |
| `discarded_by` | string or null | yes | See type definition and endpoint rules. |
| `actions` | array of Action | yes | maxItems=6 |

### ActionReceipt

| Field | Type | Required | Constraints |
|---|---|---|---|
| `operation_id` | string | yes | format=uuid |
| `action` | ActionName | yes | See type definition and endpoint rules. |
| `accepted_at` | string | yes | pattern=Z$; format=date-time |
| `run_id` | string | yes | format=uuid |
| `version_id` | string or null | yes | See type definition and endpoint rules. |
| `status_url` | string | yes | pattern=^/api/v1/refresh-runs/[0-9a-f-]{36}$ |
| `result` | string | yes | enum=['queued', 'warning_resolved', 'discarded'] |
| `replayed` | boolean | yes | See type definition and endpoint rules. |

### FieldError

| Field | Type | Required | Constraints |
|---|---|---|---|
| `field` | string | yes | maxLength=128 |
| `code` | string | yes | maxLength=64 |
| `message` | string | yes | maxLength=512 |

### Problem

| Field | Type | Required | Constraints |
|---|---|---|---|
| `type` | string | yes | format=uri-reference |
| `title` | string | yes | maxLength=512 |
| `status` | integer | yes | minimum=400; maximum=599 |
| `detail` | string | yes | maxLength=512 |
| `code` | ErrorCode | yes | See type definition and endpoint rules. |
| `request_id` | string | yes | format=uuid |
| `errors` | array of FieldError | yes | maxItems=20 |
| `blocker` | Blocker or null | yes | See type definition and endpoint rules. |
| `current_revision` | Counter or null | yes | See type definition and endpoint rules. |

## Security contract boundary

[Security contract](security-contract.md) is authoritative for the accepted A19 authentication, SQL, container isolation, storage access, resource/admission limits and retry rules. This document owns API behavior, endpoints, request/response fields, pagination, errors and recovery. [OpenAPI](openapi.json) describes HTTP shapes; its security extensions are specifications, not an implemented enforcement layer.

The earlier security proposals are superseded where A19 differs; their text is preserved in the [contract split session](../ai/sessions/2026-10-03-security-contract-and-api-split.md#superseded-security-proposals). Remaining implementation details are listed in the security contract. No control is runtime-verified.

## Verification required

The artifacts specify behavior. No application endpoint, database migration, provider setup, worker, or query runtime has been implemented by this task.

| Scenario | Required result |
|---|---|
| Viewer/Analyst before initial publication | Waiting landing; permitted static catalog; analytical reads return data_unavailable. |
| Admin completes setup | Settings save succeeds with ETag; first refresh remains a separate action. |
| Two settings saves use the same ETag | One wins; the other gets 412 with no overwrite. |
| Viewer requests hidden dataset or diagnostics | No detail data, schema, identifiers, or storage reads leak. |
| Dashboard and metric same period/version | Identical offline-share calculation, rounding and missing-value reason. |
| Leap date, reversed/custom range, missing day | Bounded explicit date semantics; no silent clipping or zero-filling. |
| Preview/facility/generator cursor crosses publication | 409 publication_changed; restart with current authorization. |
| Preview filters followed by SQL | SQL executes only its own text, without hidden preview predicates. |
| Duplicate action key, lost HTTP response | Same receipt/target, no duplicate run, approval, or outbox work. |
| Concurrent rerun/delete/discard/retry | One valid state transition wins; loser receives conflict/precondition result. |
| Required checks fail or are incomplete | No automatic publication and no approval bypass. |
| Required checks pass with frozen warnings | Review required; one bound approval enables publication. |
| Required checks pass without warnings | Automatic publication, including automatic-path publication retry. |
| Exhausted publication failure | Persistent warning and slot remain; same-candidate retry can rearm outbox safely. |
| Run again / delete warning / discard | History preserved; prior unpublished candidate permanently ineligible. |
| Redis loss or stale worker completion | Durable recovery works; stale generation/fence cannot resurrect or publish discarded work. |
| Browser closes / query times out | Background refresh continues; isolated query execution terminates under its supervisor. |

Still open: exact token configuration, SQL AST/type compatibility, executable DDL, refresh-stage deadlines, container hardening and supervision details, S3 policies, dependency compatibility, and runtime tests. A19 selects the security design and retry count; no control is proven merely by producing OpenAPI.

Sources for HTTP/schema conventions: [OpenAPI 3.1.1](https://spec.openapis.org/oas/v3.1.1.html), [RFC 9110 HTTP semantics](https://www.rfc-editor.org/rfc/rfc9110.html), and [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457.html). Product behavior comes from alayala's supplied approved design; completion defaults are attributed above.
