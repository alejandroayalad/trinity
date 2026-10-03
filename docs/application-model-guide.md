# Application model field guide

Status: explanatory companion, October 3, 2026. Adapted from alayala's Obsidian `Data Contract.md` discussion notes. The canonical fields, keys, types, and behavior are in [data contract v1](schema.md), recorded by [A9](../DECISIONS.md#a9--data-contract-v1-finalized). This guide explains why selected fields exist; it is not a second schema or a record of implemented behavior.

Read [the PostgreSQL model](schema.md#6-postgresql-application-model) for the complete field inventory, including primary keys, constraints, and recovery fields not repeated below. `?` means nullable under the conditions in that contract. Clerk actor IDs are external text identifiers. Historical session notes do not override the current specification. A16 amends the control model for fixed warning-based publication and durable recovery; analytical fields remain unchanged.

## 1. `shared_settings` — How should the application operate?

One shared configuration for the application.

| Field | Why it exists |
| --- | --- |
| `setup_completed_at?` | Records whether initial setup is complete. Prevents scheduled refreshes before configuration. |
| `schedule_enabled` | Lets an Admin pause scheduled refreshes while keeping the schedule. |
| `daily_time?` | Stores the selected daily local time as HH:mm; schedule_timezone supplies its timezone. |
| `schedule_timezone?` | Gives the schedule a timezone. “Run at 08:00” is otherwise ambiguous. |
| `revision` | Detects conflicting edits. If two Admins edit revision 4, the second save must not silently overwrite the first. |
| `updated_at` | Records when settings last changed. |
| `updated_by?` | Records the Clerk user who changed them. |

A16 removes the old shared `publication_mode` field; frozen candidate warnings determine whether approval is required.

## 2. `refresh_runs` — What happened to one complete refresh request?

One row represents the whole operation, from request through publication.

| Field | Why it exists |
| --- | --- |
| `revision`, `publication_generation` | Detect stale Admin actions and distinguish explicit same-candidate publication retries. |
| `rerun_of_run_id?` | Connects a new full refresh to the abandoned failed run; rerun never reopens that old run. |
| `run_seq` | Gives requests a reliable order. Helps prevent an older refresh from replacing a newer publication. |
| `trigger_kind` | Distinguishes a manual request from a scheduled request. |
| `requested_by?` | Identifies the Admin who requested it. Null for scheduled runs. |
| `request_key` | Prevents a repeated HTTP request or scheduled event from creating duplicate runs. |
| `requested_at` | Records when the system accepted the request. |
| `started_at?` | Records when a worker started. The difference from `requested_at` shows queue wait time. |
| `finished_at?` | Records when the run reached a final outcome. |
| `status` | Shows overall progress. The permitted states and transitions are defined in the canonical lifecycle. |
| `settings_revision` | Identifies the settings revision used for this run. |
| `policy_snapshot` | Preserves the actual rules used. Later settings changes must not silently change a pending run. |
| `requested_start` | Defines the first observation date to fetch. |
| `requested_end?` | Defines the last date. The worker discovers and freezes it before extraction. |
| `window_frozen_at?` | Records that the date window has been fixed. Retries must use the same window. |
| `execution_fence` | Identifies the current worker ownership generation. Conditional writes must reject an older generation after takeover. |
| `lease_until?` | Sets when the worker’s temporary ownership expires. Allows recovery after a crash. |
| `error_code?` | Gives software a stable failure identifier, such as `coverage_regression`. |
| `error_summary?` | Gives the Admin a readable explanation of the failure. |

**Why both `request_key` and `execution_fence`?** The first prevents duplicate requests. The second protects an existing run from competing workers.

## 3. `refresh_steps` — Which part ran, failed, or retried?

One row represents **one attempt at one stage**, such as fetching facility data. The stage codes are `extract`, `prepare`, `validate`, and `publish`.

| Field | Why it exists |
| --- | --- |
| `run_id` | Connects the attempt to its complete refresh run. |
| `stage` | Identifies extraction, preparation, validation, or publication. |
| `work_key` | Identifies the work within that stage, such as `facility`. |
| `attempt` | Separates the first attempt from later retries. |
| `status` | Records the outcome of this specific attempt. |
| `execution_fence` | Records which worker ownership generation performed it. |
| `started_at?`, `finished_at?` | Show the duration of the attempt. |
| `error_code?`, `error_summary?` | Explain this attempt’s failure without losing earlier failures. |

For example, the facility fetch can fail twice and succeed on its third attempt. The overall run can still succeed.

## 4. `job_outbox` — Which work must PostgreSQL send to BullMQ?

The run and its dispatch request are saved in the same database transaction. This prevents a crash from leaving a saved run with no recoverable queue request.

| Field | Why it exists |
| --- | --- |
| `run_id` | Connects the dispatch request to its run. |
| `job_kind` | Distinguishes starting the refresh pipeline from publishing a prepared version. |
| `deduplication_key` | Identifies the logical work request so retries do not create another obligation. |
| `payload` | Contains the identifiers and parameters the worker needs. No credentials. |
| `status` | Shows whether dispatch is pending, being attempted, or acknowledged by Redis. |
| `available_at` | Controls when dispatch can next be attempted. Supports delayed retries. |
| `delivered_at?` | Records when Redis acknowledged the job. **This does not mean the refresh finished.** |
| `last_error?` | Explains the latest dispatch failure. |

## 5. `data_versions` — Which dataset snapshot did a run produce?

A run is an operation. A version is its data output. They need separate records because a run can fail before producing a version.

| Field | Why it exists |
| --- | --- |
| `run_id` | Identifies the run that produced this version. |
| `status` | Shows whether the version is being prepared, validated, or rejected. |
| `disposition`, `discarded_at?`, `discarded_by?` | Records permanent abandonment separately from validation. |
| `approval_required?`, `review_warning_count?`, `review_warning_digest?` | Freezes the review condition for this exact candidate after diagnostic completion. |
| `created_at` | Records when the candidate was created. |
| `validated_at?` | Records when required validation completed successfully. |
| `validation_step_id?` | Points to the successful validation attempt. Prevents mixing passing checks from different attempts. |
| `coverage_start`, `coverage_end` | Describe the observation dates included in the version. |
| `latest_observation_date` | Supports showing how recent the source observations are, separately from publication time. |
| `contract_version` | Identifies which data-schema and behavior rules apply. |
| `validation_checkset` | Identifies which collection of checks the version must pass. |

## 6. `dataset_artifacts` — Which physical files belong to a version?

One row per Parquet file. Three datasets can produce more than three files.

| Field | Why it exists |
| --- | --- |
| `version_id` | Connects the file to its version. |
| `dataset_key` | Identifies national, facility, or generator data. |
| `storage_path` | Tells the application where to find the file. |
| `byte_size` | Records its size. Useful for storage reporting and basic integrity checks. |
| `row_count` | Records how many observations it contains. |
| `min_period`, `max_period` | Describe the dates in this particular file. |
| `schema_fingerprint` | Identifies its column names and types so an unexpected schema can be detected. |

`sha256` is the file checksum in the canonical model. It identifies the **contents**. The schema fingerprint identifies the **structure**.

## 7. `validation_results` — Why was this version accepted or rejected?

One row per check and dataset scope within a validation attempt.

| Field | Why it exists |
| --- | --- |
| `version_id` | Identifies the candidate being checked. |
| `step_id` | Identifies the exact validation attempt. |
| `manifest_sha256` | Binds the result to the exact manifest that was checked. |
| `checkset_version` | Records the collection of rules used. |
| `check_code` | Identifies the check, such as unique keys or reconciliation. |
| `check_revision` | Identifies the version of that individual check. |
| `dataset_key` | Identifies the scope: national, facility, generator, or all. |
| `required`, `severity` | Distinguishes required validation from registered info/warning diagnostics; review warnings need approval after required checks pass. |
| `status` | Records pass, fail, or execution error. |
| `checked_count` | Shows how much data the check examined. |
| `failed_count` | Shows how many items failed. |
| `details` | Stores structured evidence, such as a date, expected value, actual value, and difference. |
| `checked_at` | Records when the result was produced. |

**Why not store only `is_valid` on the version?** It would show the result but would not explain a failure or prove that all required checks ran.

## 8. `approvals` — Who authorized this version?

One row records an Admin's approval of one validated, immutable version. This explanation fills the gap in the vault draft; the model already exists in the merged contract.

| Field | Why it exists |
| --- | --- |
| `version_id` | Identifies the exact version being approved. The contract permits one approval per version. |
| `approved_by` | Records the Clerk ID of the Admin authorized at approval time. |
| `approved_at` | Records when the approval occurred. |
| `manifest_sha256`, `validation_step_id`, `review_warning_digest` | Binds approval to exact files, validation and warning classification. |

Approval cannot waive failed validation. The approval, publishing state, and publication outbox request commit together. A worker performs publication afterward; accepting approval is not publication success.

## 9. `publication_events` — What became visible, and when?

One row records a successful publication.

| Field | Why it exists |
| --- | --- |
| `version_id` | Identifies the version made available to users. |
| `previous_publication_event_id?` | Records which publication it replaced. Null for the first publication. |
| `approval_id?` | Connects an approval-mode publication to its authorization. Null in automatic mode. |
| `published_at` | Records when the version became active. |
| `publication_mode` | Records the derived publication outcome, automatic or approved; this is not an account setting. |
| `actor_id?` | Records the human actor for approved publication. Null for automatic publication. |
| `idempotency_key` | Gives repeated publication attempts the stable identity `publish:<version_id>`, as specified in the contract. |

## 10. `active_publication` — Which version should a new query use?

One shared row selects the active publication event. The event identifies a version, and the version identifies its Parquet artifacts.

| Field | Why it exists |
| --- | --- |
| `id` | Identifies the one shared row, present even before first publication. |
| `publication_event_id?` | Selects the active event. Null means no data has been published yet. |
| `revision` | Detects a competing update when used in a conditional write; the counter alone does not enforce concurrency. |

`active_publication → publication_events → data_versions → dataset_artifacts`

Example: query Q1 resolves version 11. Version 12 is published while Q1 runs. Q1 continues using version 11, and a later query uses version 12. V1 retains all published files and evidence, so the old query keeps its files. Selecting a prepared version merely because it has the newest timestamp would bypass validation or approval.

Publication inserts its event, changes the active pointer, and marks the run successful in one database transaction. A failed transaction keeps the prior publication. The full eligibility, run-order, coverage, lease, and retry rules remain in the [canonical lifecycle](schema.md#7-lifecycle-and-publication-consistency).

## A16 recovery records

| Model | Purpose |
|---|---|
| `refresh_control` | Holds the one shared lifecycle slot across active work, review and unresolved failure. |
| `failure_warnings` | Keeps each operational failure warning and its resolution actor/time; clearing the warning preserves history. |
| `api_commands` | Binds a client idempotency key to one authenticated action and receipt; repeated requests cannot duplicate work. |

`publication_failed` is a waiting state that can retry the same candidate. A terminal full-refresh failure requires a new run. Warning deletion, rerun or discard permanently abandons the prior unpublished candidate as specified in A16. The amended canonical schema owns all fields and transition constraints.

## How this guide was reconciled

The vault contained two copies of the same validation-results explanation and no approvals section. This guide keeps one validation explanation and adds the approvals explanation from the merged contract. The later vault closure checklist assessed an older draft; it does not reopen the schema or behavior already specified in PR #1. Runtime implementation and verification remain pending.

See the [session handoff](../ai/sessions/2026-10-03-vault-reconciliation-and-handoff.md) for the comparison, attribution, and next action.
