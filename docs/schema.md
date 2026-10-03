# Trinity data contract v1

Status: finalized specification, October 2, 2026 (America/Merida). Prepared by AI at alayala's request to finalize the data contract. These are implementation requirements, not implemented behavior or new runtime findings. [A9](../DECISIONS.md#a9--data-contract-v1-finalized) records the choice, alternatives, and limits. A1–A8 remain in force.

## 1. Boundary and data flow

Input: the three EIA API v2 nuclear-outage routes. Output: one validated, immutable version containing all three analytical datasets and a PostgreSQL record of its publication. PostgreSQL holds application state; DataFusion reads the permitted published Parquet files. Outage rows are not copied into PostgreSQL.

Flow: record refresh and outbox request together → fetch a fixed window → parse and prepare files → validate the exact manifest → publish automatically or wait for Admin approval. A manifest lists the exact files and their checksums. Required failure at any stage keeps the candidate unpublished and leaves the previous publication available. Before the first publication, analytical data is unavailable.

This document closes the logical data model and publication invariants. It does not select a language, web framework, SQL parser, allowed SQL grammar, queue tuning, or migration library. The original challenge PDF and source exports are absent from this repository; scope follows the current project documents.

## 2. Analytical datasets and keys

Names below are the canonical analytical table names. `dataset_key` in application records uses `national`, `facility`, or `generator`.

| Table | EIA route below `/v2/nuclear-outages/` | Meaning of one row | Unique key within one version |
|---|---|---|---|
| `national_outages` | `us-nuclear-outages/data/` | One national observation for one date | `period` |
| `facility_outages` | `facility-nuclear-outages/data/` | One facility observation for one date | `(period, facility)` |
| `generator_outages` | `generator-nuclear-outages/data/` | One generator within one facility for one date | `(period, facility, generator)` |

Across versions, the identifier is `(version_id, daily key)`. The same source key can have revised values in a later version. The version belongs to the artifact manifest; it is not a fabricated EIA column. No globally unique generator ID or sequential generator numbering is assumed.

| Column | Tables | Parquet logical type | Null allowed? | Meaning and parsing rule |
|---|---|---|---|---|
| `period` | All | `DATE` (Arrow `Date32`) | No | Strict `YYYY-MM-DD` calendar date. Keep the source date; do not apply a timezone conversion. |
| `facility` | Facility, generator | `STRING` | No | Source identifier. Preserve case and leading zeros. Reject empty or whitespace-only IDs; do not trim, renumber, or convert to an integer. |
| `generator` | Generator | `STRING` | No | Source identifier within its facility. Same preservation rule as `facility`. |
| `facilityName` | Facility, generator | `STRING` | Yes | Source label, preserved when provided. A missing or blank label becomes null and is recorded as a diagnostic. Never use a label as a key. |
| `capacity` | All | `DECIMAL(24,6)` | No | Reported capacity in MW. Must be finite and nonnegative. Zero remains zero. |
| `outage` | All | `DECIMAL(24,6)` | No | Reported outage in MW. Must be finite. Retain signed values; unusual ranges are diagnostic checks below. |
| `percentOutage` | All | `DECIMAL(24,6)` | Yes | Source percentage, kept separately from the calculated metric. Absent/null/blank means unknown. Nonempty invalid numeric text fails parsing. |

All columns exist in each applicable schema even when an optional column is entirely null. Unknown source columns are preserved in sanitized evidence but are not automatically added to the public tables. Removed required fields or changed units fail validation. EIA documents string data values; parse decimal text directly, never through a binary float. A numeric JSON identifier or measurement outside that documented form fails the schema check instead of being silently reformatted.

The decimal type is Trinity's explicit storage limit, not an EIA guarantee. Precision 24 means at most 24 total digits; scale 6 means at most six fractional digits after removing insignificant trailing zeros. Values must fit exactly. Overflow or loss of a nonzero fractional digit blocks the candidate. Do not round source MW to make it fit. Preserve the original lexical value in evidence.

### Analytical relationships

These are validation relationships inside one version, not PostgreSQL foreign keys. Every facility row must have at least one generator row for that date; every generator row must match a facility row. A day can have a different set of facilities or generators than the previous day.

```mermaid
erDiagram
    direction TB
    NATIONAL_OUTAGES ||--|{ FACILITY_OUTAGES : "same period"
    FACILITY_OUTAGES ||--|{ GENERATOR_OUTAGES : "same period and facility"
    NATIONAL_OUTAGES {
        date period PK
        decimal capacity
        decimal outage
        decimal percentOutage
    }
    FACILITY_OUTAGES {
        date period PK
        string facility PK
        string facilityName
        decimal capacity
        decimal outage
        decimal percentOutage
    }
    GENERATOR_OUTAGES {
        date period PK
        string facility PK
        string generator PK
        string facilityName
        decimal capacity
        decimal outage
        decimal percentOutage
    }
```

## 3. Metric and missing observations

For US-08, use the national row for the selected date:

`offline_share_percent = 100 × outage / capacity`

For an aggregate within one grain and date, first sum MW, then divide: `100 × sum(outage) / sum(capacity)`. Never average source percentages, add different grains together, use a fixed fleet capacity, or pool dates into the daily metric. MW is power; it is not MWh or daily energy lost.

Calculate with decimal arithmetic. Round the final displayed percentage to two decimal places, using half-up rounding. Calculations and checks use the unrounded ratio. Public numeric transport must preserve exact decimals, for example as decimal strings; choosing a client library must not silently change source precision.

- A zero denominator returns null with reason `zero_capacity`. It does not return zero percent or infinity.
- A requested date outside the published window, or an absent entity/date, returns no observation with reason `not_reported`. It does not create an analytical row.
- A missing required MW value blocks the replacement version. A user never receives a partial aggregate that silently omits that row.
- A ratio outside 0–100 remains the calculated value and carries a data-quality diagnostic. Never clamp it to a plausible value.
- Use source `percentOutage` only as source data and a diagnostic comparison. It is not the input to US-08.

For Millstone on 2026-08-04, `100 × 863.4 / 2108.4` displays as 40.95%. The simple average of its two generator percentages would incorrectly give 50%. [F1](../FINDINGS.md#f1--calculate-percentages-from-capacity-and-outage) records this example.

Before Palisades first appears, its observations are `not_reported`. Additions, removals, and gaps are retained as source membership changes, not filled with zero and not automatically described as closures or failures. Record changes for investigation. The contract does not claim an independent inventory that can detect an omission shared by all three routes.

## 4. Window, revisions, and extraction evidence

The v1 supported history starts at **2024-10-02**, the start of the wider inspected export. Request creation freezes the start and the end strategy, `latest_national`. The background worker discovers the newest national observation date with a bounded latest-row request. It then sets `requested_end` and `window_frozen_at` once, conditionally on its execution fence, before extracting any route. All retries reuse that fixed window. No EIA request is required in the initiating HTTP transaction. Reject an invalid/future date or an end earlier than the active version's end. A future date means later than the UTC date at discovery; this check does not reinterpret historical `period` values. Do not silently shorten the range to hide a lagging route. An end before the supported start is a failed run.

Re-fetch the entire supported range on every refresh. This captures revisions anywhere in the supported history without an unverified lookback assumption. Do not fetch or claim all history back to 2007. The fixed start is a v1 scope choice, not a claim that EIA starts there. A historical reproduction run can use the `fixed` end strategy with an explicit end in its request snapshot; the worker validates and freezes it before extraction. It must not replace a wider or newer active window. Publication rechecks coverage under its lock, because the active window can change after discovery.

Use daily frequency and request all three measurement fields. Sort ascending by every field in the daily key. Use JSON pages of at most 5,000 rows. Start at offset zero; advance by the actual returned count. After a short page, probe its next offset and require zero rows before treating the route as exhausted. A nonempty probe continues collection. Detect duplicate keys, repeated pages, non-progress, HTTP errors, and API-body errors; none is successful exhaustion. Reaching a configured request/time limit fails the run, not the dataset silently.

The facility route's advertised `total` is evidence only. It neither sets the expected facility count nor determines completion. For national and generator routes, disagreement between a stable advertised total and returned rows is a required failure. Changing totals during collection fail the attempt. Explicit sorting is required but does not provide a source snapshot transaction. A cross-route mismatch can reflect a source revision during collection; fail and retry a new extraction attempt instead of repairing the numbers.

For each attempt preserve: route; frequency; date bounds; sort fields; offset and requested length; request/response times in UTC; HTTP/API status; API version; advertised total; actual row count; and a checksum of the sanitized response. Preserve source field values and unit metadata. Remove API keys, authorization headers, cookies, and credential-bearing echoed request parameters **before** writing evidence, exceptions, or logs. Hash the sanitized saved bytes, not a secret-bearing payload.

`latest_observation_date`, `published_at`, and `last refresh outcome` are different facts. Expose them separately. A successful refresh with unchanged source dates is not a new source observation. The schedule remains A3's daily default with Admin-selected time/timezone. An age-based stale threshold and source publication SLA are not inferred from daily frequency and remain a separate product decision.

## 5. Validation and readiness

Freeze the file manifest before validation. Its SHA-256 digest covers a deterministically ordered list of dataset keys, relative paths, file checksums, schema fingerprints, row counts, and date bounds, plus contract version. No path or file can change after freezing. Retrying preparation creates a new candidate manifest before validation; after a version is validated, any changed candidate needs a new run and version.

The required check set is `trinity-data-v1`. Store the check-set version, manifest digest, expected checks, result rows, and validation-attempt ID. A complete successful attempt for this exact manifest is the only readiness proof. Never combine passing rows from different attempts. Missing, failed, interrupted, skipped, or unfinished required checks block publication. Zero result rows never mean success.

| Code | Required pass condition | Failure behavior |
|---|---|---|
| V01 `source_complete` | All three routes succeeded and reached documented exhaustion for the fixed request window; no unstable/non-progressing pages; stable national/generator totals agree where supplied. | Reject candidate; keep evidence. |
| V02 `schema_units` | Daily dates, required fields, exact parsable types, supported precision, and metadata confirming MW/MW/percent. | Reject candidate; no silent conversion or row dropping. |
| V03 `unique_keys` | Every daily key is present and unique in its table. | Reject even identical duplicates; do not silently deduplicate. |
| V04 `date_coverage` | Exactly one national row for every requested date; facility and generator date sets equal that national date set; no out-of-window rows. | Reject partial windows. |
| V05 `facility_coverage` | Facility `(period, facility)` pairs exactly equal generator groups. | Reject missing counterpart groups, regardless of source `total`. |
| V06 `facility_reconciliation` | For every facility/date, generator sums exactly equal facility capacity and outage. | Reject and record both values and the difference. |
| V07 `national_reconciliation` | For every date, facility sums and generator sums each exactly equal national capacity and outage. | Reject and record both values and the difference. |
| V08 `artifact_integrity` | All three datasets have a complete readable Parquet manifest; paths are within the version root; checksums, schema, counts, and bounds agree with validation input. | Reject missing, changed, unreadable, or unexpected artifacts. |

V06/V07 use exact decimal arithmetic and **zero-MW tolerance**. This is a conservative v1 publication policy supported by the inspected exports, not a promise about EIA's future behavior. A legitimate source rounding difference still blocks v1 until investigated and an explicit new rule is recorded. Admin approval cannot waive it.

Non-blocking diagnostic checks record missing labels/source percentages, negative outage, outage above capacity, percentages outside 0–100, membership changes, and a source percentage differing from the computed ratio by more than **0.0051 percentage points**. The last threshold comes from the inspected export's comparison, not a confirmed EIA rounding specification. Preserve these values and expose relevant quality notes with the analytical result; Viewer notes may describe national data only. These cases do not excuse a required-check failure.

AN-01's capacity change and AN-02's entity addition do not fail merely because values or membership changed. AN-03's known facility total mismatch is retained in Admin evidence but gets no user warning after required checks pass, as A5 requires. Do not assume future anomalies have the same handling.

## 6. PostgreSQL application model

Notation: fields are required unless suffixed `?`. Every `id` is its table's primary key. IDs are UUID except singleton `id = 1`, positive monotonic `run_seq`, and external text actor IDs. Event times are `timestamptz`; observation bounds are `date`; counters/revisions are nonnegative `bigint`. Statuses and codes are constrained text. `details`, `policy_snapshot`, and sanitized payloads are JSONB. These are logical constraints; migrations must enforce row-local rules and transaction rules must enforce cross-row invariants.

| Model | Fields | Keys and constraints |
|---|---|---|
| `shared_settings` | `id`, `setup_completed_at?`, `schedule_enabled`, `schedule_expression?`, `schedule_timezone?`, `publication_mode?`, `revision`, `updated_at`, `updated_by?` | Singleton `id=1`. Before setup: scheduling disabled and policy unset. After setup: valid mode `automatic/approval`, IANA timezone and supported expression; actor required for Admin edits. Revision is the compare-and-swap token for edits. |
| `refresh_runs` | `id`, `run_seq`, `trigger_kind`, `requested_by?`, `request_key`, `requested_at`, `started_at?`, `finished_at?`, `status`, `settings_revision`, `policy_snapshot`, `requested_start`, `requested_end?`, `window_frozen_at?`, `execution_fence`, `lease_until?`, `error_code?`, `error_summary?` | Unique `run_seq` and `request_key`. Manual actor required; scheduled actor null. Freeze policy/start/end strategy at creation. End and window-freeze time are null only before successful window discovery; set both once before extraction. Then start ≤ end and the bounds cannot change. A changed request cannot reuse its request key. Terminal states require finish time; failed requires sanitized error. |
| `refresh_steps` | `id`, `run_id`, `stage`, `work_key`, `attempt`, `status`, `execution_fence`, `started_at?`, `finished_at?`, `heartbeat_at?`, `processed_count`, `error_code?`, `error_summary?` | FK to run; unique `(run_id, stage, work_key, attempt)`; attempt ≥1. Stages `extract/prepare/validate/publish`; work key distinguishes route/partition work. States `pending/running/succeeded/failed/abandoned`. Finished states require finish time. A stale execution fence cannot commit outcomes. |
| `job_outbox` | `id`, `run_id`, `job_kind`, `deduplication_key`, `payload`, `status`, `available_at`, `dispatch_attempts`, `dispatch_generation`, `lease_token?`, `lease_until?`, `delivered_at?`, `last_error?` | FK to run; unique deduplication key and `(run_id, job_kind)`. Kinds `refresh_pipeline/publish_version`. Payload includes a schema version and stable run/version IDs, never credentials. States `pending/dispatching/delivered`. Dispatching requires lease token and expiry. Delivered requires acknowledgment time; it does not mean pipeline success. |
| `data_versions` | `id`, `run_id`, `status`, `created_at`, `manifest_frozen_at?`, `manifest_sha256?`, `validated_at?`, `validation_step_id?`, `coverage_start`, `coverage_end`, `latest_observation_date`, `contract_version`, `validation_checkset` | Unique FK `run_id` (zero or one version per run). States `preparing/validating/validated/rejected`. Validating requires frozen manifest. Validated requires one successful validation step for this version, manifest, and check set. Coverage equals fixed run bounds. |
| `dataset_artifacts` | `id`, `version_id`, `dataset_key`, `storage_path`, `sha256`, `byte_size`, `row_count`, `min_period`, `max_period`, `schema_fingerprint` | FK to version; unique `(version_id, storage_path)`. Relative normalized path under the version root; no traversal, URL, or arbitrary user path. Dataset key constrained to the three values. Counts positive for data files. Date bounds within version. Many files per dataset are allowed. |
| `validation_results` | `id`, `version_id`, `step_id`, `manifest_sha256`, `checkset_version`, `check_code`, `check_revision`, `dataset_key`, `required`, `status`, `checked_count`, `failed_count`, `details`, `checked_at` | FKs to version and validation step; unique `(version_id, step_id, check_code, dataset_key)`. Dataset scope `national/facility/generator/all`, never null. Status `pass/fail/error`; pass has zero failed count. Step's run must own version. Exact expected rows are defined below. |
| `approvals` | `id`, `version_id`, `approved_by`, `approved_at` | Unique FK `version_id`. Only an authorized Admin can approve a validated, immutable, eligible candidate. The version's immutable manifest binds the approval. No approval bypass or separate rejection/comment feature. |
| `publication_events` | `id`, `version_id`, `previous_publication_event_id?`, `approval_id?`, `published_at`, `publication_mode`, `actor_id?`, `idempotency_key` | Unique FK `version_id` and unique idempotency key. Previous-event self-FK is null only for first publication. Approval mode requires matching approval/version and its Admin actor; automatic mode has null approval and actor. |
| `active_publication` | `id`, `publication_event_id?`, `revision` | Singleton `id=1`, created empty at bootstrap. Nullable FK to event; null until first publication. Insert event, update pointer, and succeed run in one transaction. |

Expected required result rows: V01/V02/V03/V08 each once for each of `national`, `facility`, `generator`; V04/V05/V06/V07 each once with scope `all`. There are **16 required result rows** per completed validation attempt. V08's three rows together verify the complete manifest and dataset-key set. Diagnostic results use separate `Dxx` codes with `required=false`; they cannot substitute for these rows. Persist a failed/error result when a check cannot run; a failed attempt cannot establish readiness.

The immutable policy snapshot contains `settings_revision`, `publication_mode`, `contract_version`, `validation_checkset`, `requested_start`, `end_strategy`, and `explicit_end` only for the fixed strategy. It agrees with the corresponding run/version columns. Resolved bounds live on the run and are frozen separately by the worker; no candidate version can be created before that freeze. Changing the deployed contract cannot reinterpret an existing candidate; a worker must execute its recorded contract version or fail it as unsupported. A pass on a later check set cannot authorize an older candidate implicitly. Candidate bounds are expectations during preparation and must match measured artifact bounds at validation. A validated version requires non-null `validated_at`, manifest digest, and successful validation-step ID.

Clerk IDs remain text references without local password/session/user tables solely for login. They are not database foreign keys to Clerk. Keep historical actor IDs if a Clerk user is removed. Never take `requested_by`, `approved_by`, or a role from an untrusted request body. Role-claim storage, token validation, and role-change propagation remain the separate authentication implementation contract.

### Application relationships

Split diagrams show one shared model. Repeated entities refer to the same table. Application FKs connect metadata, never outage rows. Delete cascades must not remove published evidence or actors' historical actions.

```mermaid
erDiagram
    direction TB
    REFRESH_RUNS ||--o{ REFRESH_STEPS : attempts
    REFRESH_RUNS ||--o{ JOB_OUTBOX : dispatches
    REFRESH_RUNS ||--o| DATA_VERSIONS : prepares
    DATA_VERSIONS ||--o{ DATASET_ARTIFACTS : contains
    DATA_VERSIONS ||--o{ VALIDATION_RESULTS : checked_by
    REFRESH_STEPS ||--o{ VALIDATION_RESULTS : records
```

```mermaid
erDiagram
    direction TB
    DATA_VERSIONS ||--o| APPROVALS : may_require
    DATA_VERSIONS ||--o| PUBLICATION_EVENTS : published_once
    APPROVALS |o--o| PUBLICATION_EVENTS : authorizes
    PUBLICATION_EVENTS |o--o| ACTIVE_PUBLICATION : selected_by
    PUBLICATION_EVENTS |o--o| PUBLICATION_EVENTS : previous_event
```

`shared_settings` has one current row. A run stores its revision and a complete immutable policy snapshot; the snapshot is deliberately not a foreign key to a historical settings row. `active_publication` has one row even before it points to an event. Additional required fields and relationships are in the model table, not omitted from the contract because they are absent from a compact diagram.

## 7. Lifecycle and publication consistency

Run transitions:

| From | To | Condition |
|---|---|---|
| `requested` | `running` | Worker claims a durable run lease and a new execution fence. |
| `running` | `awaiting_approval` | Exact candidate passed validation and the frozen policy requires approval. Worker lease is released. |
| `running` | `publishing` | Exact candidate passed validation in automatic mode; commit its publication outbox request with this state change. |
| `awaiting_approval` | `publishing` | Authorized Admin approval and publication outbox request commit together with this state change. |
| `publishing` | `succeeded` | Publication worker commits the event and active pointer. |
| `requested/running/awaiting_approval/publishing` | `superseded` | A higher `run_seq` has already published; this older candidate must not replace it. |
| `requested/running/publishing` | `failed` | Required validation failed, publication would regress coverage, or operational recovery exhausted its finite attempt budget. |

Retries within an active run add step attempts. A worker restart reclaims the run with a higher fence after lease expiry; stale workers cannot mutate current state. A validated candidate waiting for approval is not a lost worker and is not re-enqueued for extraction. A publishing run resumes publication of its frozen version, not extraction. A required data-check failure sets the version to rejected and the run to failed; a transient check error can retry the unchanged manifest within the finite recovery budget. A new Admin retry after terminal failure creates a new run/request key. Cancellation, rollback, republishing a version, and rejection UI are outside v1. Terminal run states are immutable.

1. **Request:** require completed setup and valid Admin authorization or a valid scheduled occurrence. In one PostgreSQL transaction, freeze the current policy/start/end strategy and insert the run and outbox. The worker resolves and freezes the end before extraction. A scheduled occurrence key includes settings revision and the intended UTC occurrence time. A duplicate manual key with identical actor and requested parameters returns the existing run; conflicting reuse is rejected. Deduplication does not depend on a date that has not yet been discovered.
2. **Dispatch:** claim the outbox with a lease. Enqueue a stable logical run ID; condition delivery updates on the lease token. On crash or lease expiry, retry safely. Redis can accept the job before PostgreSQL records acknowledgment, so duplicate delivery is expected.
3. **Recovery:** periodically reconcile requested/running/publishing runs with durable progress. After a worker lease expires, reclaim through PostgreSQL and redispatch the unfinished job kind if needed. Increment dispatch generation when recovering a missing/stale queue job; a retained completed BullMQ job must not suppress needed recovery. Duplicate safety comes from PostgreSQL run state, fences, and unique effects, not queue job IDs alone. Do not replay terminal or awaiting-approval runs. When rearming an outbox, clear its current delivery/lease fields and retain delivery-attempt evidence in structured diagnostic records.
4. **Files:** each run/attempt writes isolated paths. Build only one selected candidate manifest. After freezing, retries validate the same bytes; superseded/stale attempts cannot attach their outputs. All selected files must be durable and readable by the query process before publication begins.
5. **Publish:** automatic readiness or Admin approval writes `publish_version` outbox work and the publishing state atomically; approval additionally writes its approval record. Release the completed preparation worker's lease in the same handoff transaction. Return request acceptance, not publication success. The publication worker claims its own lease/fence while retaining the publishing state and locks the singleton active-publication row. First return an existing event for the same version as an idempotent retry. Otherwise recheck validated manifest/check-set results, policy, required approval, current execution fence, publishing state, and monotonic `run_seq`. A candidate whose sequence is not greater than the active event's run is superseded. Also require candidate start ≤ active start and candidate end ≥ active end; a coverage regression fails publication with `coverage_regression`. Insert event, active-pointer update, and run success atomically. The final conditional run update must still match the publication fence; otherwise roll back the whole transaction. Use `publish:<version_id>` as the stable idempotency key. No HTTP approval path performs the file/publication pipeline outside workers.
6. **Read:** resolve the active event once at request start. Authorize the requested datasets, then register only this version's permitted manifest paths in DataFusion. Keep that version for the full query/response. Publication during a query cannot switch any of its tables.

Settings edits apply to newly created runs only. A pending version keeps its frozen mode: changing from approval to automatic does not release it; changing automatic to approval does not retroactively hold it. The Admin screen must show the candidate's policy. Permission is checked when the Admin actually approves, not copied from an old role claim stored with the run.

Repeated authorized approval of an already approved version returns its existing acceptance, failure, or publication outcome; it never creates a second approval/outbox record. A redelivered `refresh_pipeline` job that finds publishing state performs no extraction. Only `publish_version` may continue that phase. A worker must compare job kind and run state before any file or state mutation.

For v1, keep all published versions and their evidence. Automatic deletion of published artifacts is disabled. This protects readers using an older snapshot. Storage grows over time; bounded garbage collection with reader protection is later work. Staging cleanup must not delete any file referenced by a frozen candidate, validation, or publication.

## 8. Verification required during implementation

These are acceptance scenarios, not tests that have run:

| Input or failure | Required result |
|---|---|
| Generator `1` at two different facilities | Two separate identities; joins include facility and date. |
| Duplicate daily key, missing MW, decimal overflow, or changed unit | Candidate blocked; source evidence retained. |
| Capacity zero and outage zero | Preserve row; metric null with `zero_capacity`. |
| Missing Palisades row before first appearance | `not_reported`, never synthetic zero outage. |
| Facility API total equals generator count | Required coverage/reconciliation decides readiness; no known-total warning after pass. |
| One facility/date differs by 0.000001 MW | Exact v1 reconciliation fails; no auto-correction. |
| Sixteen required passes spread across two failed attempts | Candidate remains unpublished. Only one complete passing attempt qualifies. |
| Crash before enqueue, after enqueue, or Redis data loss | Durable request recovers; duplicate workers cannot publish twice. |
| Publish candidate B, then approve older candidate A | A is superseded; B stays active. |
| A higher-sequence candidate has an earlier end than the active version | Publication fails with `coverage_regression`; active coverage does not shrink. |
| Worker crashes after end discovery, before extraction | Retry uses the frozen end; it does not discover a different window. |
| Change settings while A waits for approval | A retains its frozen policy; new runs use the new revision. |
| File missing after validation but before publication | Integrity recheck blocks publication; pointer remains unchanged. |
| Query overlaps publication | All its tables come from one retained version. |
| Viewer tries detail through catalog, preview, SQL, or quality notes | Reject access; no facility/generator detail leaks. |
| First refresh fails | No active event; show data unavailable and failed refresh outcome. |

The detailed SQL grammar, resource limits, table-reference detection, and authentication checks need their own implementation contract and tests. A schema diagram does not prove SQL isolation. Clean-clone reproduction still needs sanitized source inputs/request definitions and analysis scripts; this document does not supply the missing historical exports.

## Sources and evidence limits

- [FINDINGS.md](../FINDINGS.md): candidate keys, decimal reconciliation, changing capacity, entity membership, and facility count anomaly. Historical checks were not rerun for this contract.
- [Prior model draft](../ai/sessions/2026-10-02-clerk-and-application-models.md): application flows and the ten-model baseline. This contract supersedes its proposed fields where they differ.
- [EIA API documentation](https://www.eia.gov/opendata/documentation.php): string values, multi-column sorting, pagination, metadata, and credential-bearing request echoes. It does not establish nuclear-specific value bounds or guarantee snapshot consistency.
- [Parquet logical types](https://parquet.apache.org/docs/file-format/types/logicaltypes/) and [Arrow Parquet mappings](https://arrow.apache.org/docs/cpp/parquet.html): decimal, date, and string representation. The chosen precision and validation thresholds are Trinity decisions.

Maintain data evidence — ongoing. Source methodology and omissions common to all routes remain evidence limits. No API data extraction, migration, worker, query, or authentication test was executed while authoring this specification.
