# Session — Clerk and proposed application data models

Date: October 2, 2026. Scope: planning and documentation. This is an AI-written summary, not a transcript or runtime evidence.

## Objective and contributions

[ME] Alayala selected Clerk and requested the application data models. [YOU] AI recorded [A8](../../DECISIONS.md#a8--clerk-for-authentication-closed), checked current Clerk documentation, and drafted the models below from the product flows and A2–A7. Only the provider choice is newly accepted. The schema, field names, types, and constraints below are proposals for review, not implemented or accepted decisions.

## Ownership

Clerk owns authentication identities and sessions. Proposed application identity: Clerk user ID plus a trusted Viewer, Analyst, or Admin role. No local password, session, or users table is proposed solely for login. The backend validates identity and authorizes every path; it must not trust a role submitted in a request body. Actor IDs are external text identifiers, not PostgreSQL foreign keys to Clerk. Keep historical actor references if an identity is removed; display-name retention remains open.

DataFusion supplies analytical table and column information and executes previews, permitted SQL, and US-08 over published Parquet. Access rules belong to backend policy; physical schema introspection does not establish units, metric meaning, or permissions. Those definitions belong in the analytical contract/configuration. PostgreSQL identifies the published version and its artifacts; outage rows do not go into application tables.

## Proposed PostgreSQL models

Types: internal IDs are UUID; external IDs and codes are text; event times are timestamptz; observation bounds are date; counters are integer or bigint. Status values use constrained text unless a later implementation decision chooses enums. Required fields, defaults, indexes, and deletion policies still need final DDL review. JSONB is reserved for structured details, not relationships that need foreign keys.

| Model / app need | Proposed main fields | Keys and rules |
|---|---|---|
| `shared_settings`: configure once and edit | `id`, `setup_completed_at`, `schedule_enabled`, `schedule_expression`, `schedule_timezone`, `publication_mode`, `revision`, `updated_at`, `updated_by` | Singleton row. Mode is automatic or approval. Validate timezone and supported schedule. Revision prevents silent concurrent edits. |
| `refresh_runs`: accept refresh and show overall progress | `id`, `trigger_kind`, `requested_by`, `request_key`, `requested_at`, `started_at`, `finished_at`, `status`, `settings_revision`, `policy_snapshot`, `requested_start`, `requested_end`, `error_code`, `error_summary` | Unique request key deduplicates one manual request or scheduled occurrence. Human trigger requires an actor; scheduled trigger does not. Snapshot records policy actually used. |
| `refresh_steps`: explain stage attempts and failures | `id`, `run_id`, `stage`, `work_key`, `attempt`, `status`, `started_at`, `finished_at`, `heartbeat_at`, `processed_count`, `error_code`, `error_summary` | FK to run. Unique `(run_id, stage, work_key, attempt)`. Work key distinguishes simultaneous route or partition tasks. Attempts are distinct from outbox delivery attempts. |
| `job_outbox`: recover queue dispatch | `id`, `run_id`, `job_kind`, `deduplication_key`, `payload`, `status`, `available_at`, `dispatch_attempts`, `lease_token`, `lease_until`, `delivered_at`, `last_error` | FK to run; unique deduplication key. Payload contains identifiers and parameters, never credentials. Claim lease and conditional updates protect concurrent dispatchers. Delivered means accepted by queue, not completed work. |
| `data_versions`: identify one prepared snapshot | `id`, `run_id`, `status`, `created_at`, `validated_at`, `coverage_start`, `coverage_end`, `latest_observation_date`, `contract_version` | Proposed unique FK `run_id`: zero or one logical version per run. Candidate can exist before preparation finishes. Once validated, artifacts are immutable; a changed candidate needs renewed validation and approval. |
| `dataset_artifacts`: locate and describe Parquet output | `id`, `version_id`, `dataset_key`, `storage_path`, `checksum`, `byte_size`, `row_count`, `min_period`, `max_period`, `schema_fingerprint` | FK to version; unique `(version_id, storage_path)`. Dataset key is national, facility, or generator. Three logical datasets can use many files. Publication requires a complete manifest for all three. |
| `validation_results`: explain readiness | `id`, `version_id`, `step_id`, `check_code`, `check_revision`, `dataset_key`, `required`, `status`, `checked_count`, `failed_count`, `details`, `checked_at` | FKs to version and validation attempt. Preserve attempt evidence. Required checks must all exist and pass for the exact candidate and applicable check set; no results must never count as a pass. |
| `approvals`: record sign-off for a candidate | `id`, `version_id`, `approved_by`, `approved_at` | FK to immutable validated version. Proposed one approval per version; approver must be an authorized Admin. Approval cannot override validation. Rejection/comment workflow is not yet selected. |
| `publication_events`: keep publication history | `id`, `version_id`, `previous_version_id`, `approval_id`, `published_at`, `publication_mode`, `actor_id`, `idempotency_key` | Version and optional previous-version/approval FKs; unique transition key. In approval mode the approval must match this version. Automatic publication has no human actor requirement. |
| `active_publication`: locate the live snapshot | `id`, `publication_event_id`, `revision` | Singleton pointer to a publication event. No active event before first publication. Update the pointer and insert its event in one database transaction. Version identity comes through the referenced event. |

`refresh_steps` records application progress and evidence; it does not copy all BullMQ internals. Queue job IDs may be added as diagnostic references, but queue status must not replace the application outcome.

## Relationships and behavior

A refresh run has many step attempts and outbox requests, and zero or one candidate version under this proposal. Each version has many artifact and validation records, zero or one approval, and publication history. The active publication points to one event and therefore one complete version. Republish/rollback policy remains open; the model does not add a rollback UI.

Proposed run lifecycle: requested → running → awaiting approval → succeeded, with automatic mode skipping awaiting approval and terminal failures recorded as failed. A stage retry remains within a running run and records another attempt. A separate Admin retry after a terminal failure should create a new run under this proposal. Superseded runs, cancellation, lost workers, and settings changes while awaiting approval still need explicit transition rules. Download completion alone is not overall success.

1. An authorized refresh request writes `refresh_runs` and `job_outbox` in one PostgreSQL transaction. Scheduled occurrences use a stable occurrence key to prevent duplicate runs.
2. Dispatchers claim committed outbox work; workers record stage attempts and produce candidate artifacts under bounded concurrency. A delivered outbox can coexist with failed validation.
3. Required validation results refer to the exact candidate. Failed or incomplete checks block publication. A validated candidate either follows automatic mode or waits for an Admin approval under the applicable policy.
4. Publication verifies validation, approval when required, and publication ordering under a lock or equivalent conditional update; it writes the event and active pointer atomically. Older concurrent candidates must not silently replace a newer publication. The ordering rule is still open.
5. Each analytical request resolves and retains one active version, authorizes its datasets, and registers only the permitted artifacts from that version. File retention must protect requests already using an older version. PostgreSQL transactions alone do not make Parquet writes atomic.

Example to test later: queue delivery succeeds; facility validation fails. The outbox remains delivered, the validation attempt and run record the failure, and the active publication does not change. This is a designed failure case, not an observed runtime result.

## Analytical model boundary

The daily Parquet datasets remain national, facility, and generator. Proposed keys from FINDINGS are `period`, `(period, facility)`, and `(period, facility, generator)`. `period` is a date; `capacity` and `outage` are MW; `percentOutage` is percent. Exact numeric precision and identifier representations remain open. US-08 uses the same day's outage divided by capacity times 100; denominator-zero and missing-value handling must be specified. Relationships and totals observed in the exports are evidence for validation, not database-enforced foreign keys in Parquet.

## Corrections and open questions

The prior table omitted `job_outbox`, marked approvals as unsupported despite A3, and equated three datasets with three physical files. The revised draft addresses these points and separates queue dispatch, execution attempts, validation, and publication.

Open: confirm model responsibilities before finalizing fields; decide stage granularity, retry ownership, settings-change policy, overlap ordering, exact validation contract, and artifact retention. Clerk role storage is proposed, not silently selected as part of choosing the provider. No extra end-user features are introduced by this draft.

## Checks and evidence limits

Read README, PRODUCT, DECISIONS, FINDINGS, NOTES, original planning notes, and the latest worker/outbox session. The documentation folder is not a Git repository. Reviewed a unified diff against pre-edit snapshots; checked decision IDs, local links/anchors, preserved sections, and Markdown whitespace. The save script checks original hashes and exact saved bytes. No application code, schema migration, dependency installation, provider account/configuration, EIA call, or runtime test is included. No commit, push, or remote mutation occurred.

Source: [Clerk role metadata guide](https://clerk.com/docs/guides/secure/basic-rbac); current [decisions](../../DECISIONS.md), [product scope](../../PRODUCT.md), and [data evidence](../../FINDINGS.md).

Next: review whether the proposed models cover the app flows before specifying the `refresh_runs` and `refresh_steps` state transitions.
