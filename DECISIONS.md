# Decisions — Trinity

Status: documentation and data-contract specification, October 2, 2026. Accepted means the author selected the choice. A9 is an AI-authored specification produced under the user's request to finalize the contract; individual new defaults have not been separately reviewed by the author. Neither status means implemented or tested.

This is the main decision record. A1–A4 were moved from `First Aproximation.md` without changing their accepted scope. Use one file with unique IDs and Product / business or Technical / code categories. Keep the history when a later decision changes an earlier one.

## Accepted decisions

| ID  | Category           | Choice                                                                                                          |
| --- | ------------------ | --------------------------------------------------------------------------------------------------------------- |
| A1  | Technical / code   | One decision document with categories.                                                                          |
| A2  | Product / business | Scheduled and manual Admin refreshes, with validation before publication.                                       |
| A3  | Product / business | One initial account setup; editable shared schedule and publication mode.                                       |
| A4  | Technical / code   | PostgreSQL for application state; Apache DataFusion for outage queries over Parquet.                            |
| A5  | Product / business | Validation controls publication; no user warning for the known facility count issue after required checks pass. |
| A6  | Technical / code   | Background workers run the full refresh pipeline using BullMQ and Redis, with bounded concurrency.              |
| A7  | Technical / code   | PostgreSQL `job_outbox` records dispatch requests with application changes; retries must be safe.               |
| A8  | Technical / code   | Clerk handles authentication; the backend enforces application permissions.                                  |

### A1 — arrangement of decisions: closed

Status: accepted by alayala on October 1, 2026.

Choice: use one root `DECISIONS.md` with unique decision IDs and these categories:

- **Product / business:** user needs, business rules, product behavior, and scope.
- **Technical / code:** architecture, data handling, security, implementation, and verification choices.

Rejected alternative: separate product and technical decision files with a root index.

Reason: one file keeps Arkham's required decisions easy to find. Categories distinguish the two kinds of decisions without separate logs or a second index.

Record each decision once. If it affects both categories, use both labels on the same entry.

### A2 — refresh and publication policy: closed

Category: **Product / business**. Related technical choices remain open.

Status: accepted by alayala on October 1, 2026.

**Choice:** Support both scheduled automatic refreshes and manual refreshes triggered by an Admin. Both use the same fetch and validation process. Publication means making a prepared dataset available for user queries. A3 updates the publication policy: the shared account setting selects automatic publication or Admin approval after validation. Admins control manual refreshes and investigate failures.

| Control | Accepted policy |
|---|---|
| Trigger | Both are selected: scheduled automatic refreshes and manual refreshes requested by an Admin. A3 defines initial schedule configuration, with daily as the default. |
| Validation | Run automatic checks before publication. A5 clarifies the result for the known facility count issue. The exact required checks and failure thresholds remain to be defined. |
| Publication | Required checks must pass and the complete version must be ready. Then follow the shared mode selected under A3: publish automatically or wait for Admin approval. |
| Failure recovery | Keep the previous valid version available. Report the failure so an Admin can investigate and retry after correction. Do not allow an approval action to bypass failed required checks. |

**User-facing behavior:**

1. A scheduled or Admin-triggered refresh fetches from EIA and prepares a new data version.
2. Users continue to query the previous published version while preparation and validation run.
3. After validation passes, publish the complete new version automatically or hold it for Admin approval, according to A3. Keep the previous published version active while approval is pending.
4. A failed refresh leaves the previous published version active and reports the failure.
5. Show the last successful publication time and latest observation date. Do not report success while the replacement is only partly loaded.

On the first load, there may be no previous valid version. The app must report that data is unavailable until the first successful publication.

**Earlier decision, updated by A3:** A2 originally rejected a separate Admin approval step. A3 adds a business need for team-controlled publication. Approval is now an available mode, not a requirement for every account.

**Reason:** Scheduled refreshes keep data updated without a manual request each time. Manual refreshes let an Admin request an update before the next scheduled run. A3 lets teams choose when validated data becomes available. Admin control supports investigation of failures.

**Discussion history:** Alayala first proposed frequent Parquet collection with an on-demand PostgreSQL load. The review identified two different times: data collected and data visible to users. Fresh files alone do not guarantee fresh query results. The accepted policy governs publication independently of the query engine. No performance benefit from adding PostgreSQL has been measured.

**Scope:** A4 records the selected storage and query tools. A2 originally left synchronous or asynchronous execution open; [A6](#a6--background-refresh-with-bullmq-and-redis-closed) now selects background execution for the full refresh pipeline. The brief describes daily observations, not a confirmed source publication schedule. User-triggered refresh remains Admin-only; reloading a dashboard is a separate action.

**Open implementation details:**

- Maximum acceptable age of displayed data. A3 sets daily as the default schedule; the initial Admin chooses its time and timezone.
- Exact validation checks, including which anomalies block publication and which are reported.
- How to publish a consistent version and handle overlapping refresh requests.
- How to verify success, failure, and first-load behavior.

Sources: `Software Engineer - Technical Challenge.pdf`, pages 2, 4, 5, and 7; alayala's explicit selection in the current discussion. The [Databricks expectations documentation](https://docs.databricks.com/aws/en/ldp/expectations) is background on validation behavior, not a selected dependency or implementation guarantee.

### A3 — initial account configuration: closed

Category: **Product / business**.

Status: accepted by alayala on October 1, 2026. This is a committed project feature, not an optional enhancement. Implementation has not started.

**Choice:** Provide a short setup flow for initial account configuration. An Admin completes it once for the shared application/account. Do not repeat setup for each Admin user. Authorized Admins can change the shared settings later.

Scope interpretation: one shared configuration for this challenge application. This does not introduce multiple organizations, separate team accounts, or a new registration flow.

**Product value:** Teams control when data updates and becomes available without developer support.

**Required behavior:**

1. During initial account configuration, an Admin chooses the refresh schedule. Default to daily and let the Admin select the time and timezone.
2. The Admin chooses the publication mode: automatic after required validation passes, or Admin approval after required validation passes.
3. Save these settings for the shared account. Other Admins use the existing configuration rather than completing separate setup.
4. Let authorized Admins change the schedule and publication mode later. The backend must enforce access to these settings.
5. Keep the manual Admin refresh action from A2. Scheduled and manual refreshes use the same validation process and the configured publication mode.

**Publication behavior:** In automatic mode, publish when the required checks pass and the complete version is ready. In approval mode, retain the previous published version until an Admin approves the validated replacement. Failed required checks block publication in both modes. Approval cannot bypass those checks. Before the first publication, report that data is not yet available.

**Rejected alternative:** Fix the schedule and publication mode in developer-managed configuration. That would require developer support for routine changes. Also reject setup repeated for each Admin user, because these settings govern shared data rather than personal preferences.

**Reason:** One initial configuration gives the team a clear shared policy. Editable settings let it change that policy without code changes.

**Relation to A2:** Keep both scheduled and manual refreshes. Replace the automatic-only publication rule with the mode selected here. Daily is the default refresh schedule, not a claim about EIA's publication frequency.

**Details still open:**

- Available schedule frequencies beyond the required daily default, and default time/timezone values.
- Default publication mode before the initial Admin makes a selection.
- Treatment of an existing pending version when settings change or another refresh completes.

Source: alayala's explicit feature request and clarification in this session. This is an alayala-required project feature; it is not presented as an explicit requirement from Arkham's brief.

### A4 — PostgreSQL for state and Apache DataFusion for outage queries: closed

Category: **Technical / code**.

Status: accepted by alayala on October 1, 2026. This records the selected architecture direction. It is not a measured claim that this is the fastest or simplest option.

Closure confirmed on October 2, 2026. Session evidence: [A4 decision session](ai/sessions/2026-10-02-a4-state-and-outage-queries.md).

**Choice:** Use PostgreSQL for persistent application state. Use Apache DataFusion to execute permitted outage queries directly over the published Parquet datasets.

| Component | Responsibility |
|---|---|
| PostgreSQL | Store shared setup settings, refresh schedule and publication mode, refresh outcomes, approval records, and the identity of the published data version. |
| Parquet | Store outage extracts and prepared analytical datasets. Outage records are not copied into PostgreSQL for user queries. |
| Apache DataFusion | Execute allowed SQL against the published Parquet datasets. It is the outage query engine. |
| Backend | Identify users, enforce permissions before reads and query execution, control supported SQL, and coordinate refresh, validation, approval, and publication. |

**Reason:** A2 and A3 need durable settings and publication state. PostgreSQL can group related state changes in transactions. DataFusion can query the required Parquet data directly. This avoids maintaining a second queryable copy of outage records in PostgreSQL.

**Rejected alternative:** PostgreSQL for both state and outage queries. That adds an outage-data loading step and a second copy to keep consistent with Parquet.

**Tradeoff:** Two technologies must be configured, tested, and understood. PostgreSQL transactions cover its database records; they do not make external file writes transactional. The system still needs a defined way to publish complete datasets and keep each query on a consistent version.

**Boundary:** Analyst SQL goes through DataFusion to the permitted outage datasets. It must not expose PostgreSQL application-state tables or unpublished files. DataFusion does not replace backend authorization, scheduling, or the approval workflow.

**Verification still required:**

- Check the selected language binding and supported SQL against challenge requirements.
- Prove access restrictions, write rejection, and result limits.
- Verify publication, failed refresh recovery, and queries that overlap publication.
- Confirm local setup and measure representative query behavior with actual EIA data.

No code or runtime checks have been produced for this choice. [A6](#a6--background-refresh-with-bullmq-and-redis-closed) adds BullMQ and Redis for background work; [A7](#a7--transactional-job_outbox-for-reliable-dispatch-closed) defines the application-to-queue handoff. Backend language, web framework, component versions, deployment structure, and the publication mechanism remain open. Selecting DataFusion does not select Rust.

Sources: alayala's explicit selection in this session; [DataFusion SQL API](https://datafusion.apache.org/library-user-guide/using-the-sql-api.html); [PostgreSQL transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html).

### A5 — Validation decides whether data is ready: closed

Category: **Product / business**.

Status: accepted by alayala on October 2, 2026. Not implemented or runtime-tested.

**Choice:** Pass each downloaded version to the validation service. If its counts and all required data checks pass, mark it ready. If a required check fails or validation cannot finish, keep that version unpublished. Keep the last valid published version available, as required by A2.

For the known facility count problem in AN-03, do not show a user-facing warning after validation passes. EIA's reported total is not a reliable expected facility-row count in this case. Validate the actual records and their expected coverage; matching an unreliable source total is not the pass condition. Keep source response evidence for investigation.

A ready version follows A3: publish automatically or wait for Admin approval, depending on the shared setting. Approval cannot bypass a failed validation. Before the first valid publication, data remains unavailable.

**Business example:** EIA reports three matching rows for Browns Ferry but returns one plant row covering its three generators. If the required record and coverage checks pass, this known metadata issue does not need a warning to the user. If an expected plant record is absent and validation fails, the replacement stays unpublished.

**Rejected alternative:** Publish successfully validated data with a user-facing warning about the known EIA total. Alayala rejected this because the validation service should determine whether the data is usable; a passed version should not retain that warning.

**Scope:** “Validation service” names a responsibility. It does not select a separate deployed service, framework, or execution model. The exact checks, tolerances, and validation implementation remain open. This decision does not waive required checks or establish a rule for unrelated source anomalies.

**History:** Replaces AI's proposed “publish with warning” handling for AN-03. A2–A4 remain in force.

Evidence: [AN-03 in FINDINGS.md](FINDINGS.md#an-03--the-facility-api-reports-more-rows-than-it-returns) and [the validation decision session](ai/sessions/2026-10-02-validation-publication-rule.md).

### A6 — Background refresh with BullMQ and Redis: closed

Category: **Technical / code**.

Status: accepted by alayala on October 2, 2026. Documentation only; not implemented or runtime-tested.

**Choice:** Use background workers for the full refresh pipeline, with BullMQ managing jobs in Redis. This covers extraction, preparing Parquet datasets, required validation, and publication when A3 and A5 permit it. Both scheduled and manual Admin refreshes use this path.

Concurrency must have explicit finite bounds across worker instances and for parallel work started inside a job. Independent work may run concurrently; dependent stages must wait for their prerequisites. The exact bounds, queue layout, and number of active refreshes remain open.

| Responsibility | Owner |
|---|---|
| Application state, refresh outcomes, validation evidence, approvals, and published version identity | PostgreSQL, under A4. |
| Queue state and job scheduling, claiming, and retries | BullMQ using Redis. |
| Execute the full refresh pipeline and record its results | Background workers. |
| Store and query outage data | Parquet and Apache DataFusion, under A4. |

**Reason:** A refresh can continue outside the initiating HTTP request. Explicit concurrency bounds control the amount of work in progress. BullMQ supplies queue mechanics while the application records the refresh outcome and publication state. Alayala selected Redis; its status as BullMQ's default and more established backend is supporting technical context, not a measured performance result for Trinity.

**Rejected alternatives:** Run the whole pipeline synchronously in the initiating request, or move only extraction into a worker. Neither matches alayala's selected scope. PostgreSQL-backed BullMQ was also considered and recommended by AI; alayala selected the Redis-backed option instead.

**Tradeoff:** Redis adds another service to configure and operate. A PostgreSQL application write and a Redis enqueue do not form one shared transaction; A7 addresses that dispatch gap. Queue success alone does not establish that a dataset is valid or published.

**Relationship to A2–A5:** Required validation failures still block publication. A ready version follows automatic publication or Admin approval under A3. Preserve the last valid published version while its replacement is being prepared, awaiting approval, or has failed. Waiting for approval is a workflow state; its pause/resume mechanics remain to be designed.

**Details still open:**

- Backend language, supported BullMQ binding and version, web framework, and deployment layout.
- Job and stage boundaries, queue layout, concurrency values, request-rate limits, and treatment of overlapping refreshes.
- Retry/backoff limits, cancellation, worker recovery, and retention of job history.
- Publication ordering, pending approvals, and consistent visibility of complete versions.

**Validation still required:** Prove that the initiating request can finish while work continues; measure the configured concurrency bounds across workers; exercise worker restart and stage failure; verify validation and approval gates before publication. No queue, database, or worker test has run for this decision.

**History:** Resolves the execution choice left open by A2. Alayala corrected the AI's extraction-focused concurrency proposal to cover the full refresh pipeline. A4's storage and query boundary remains in force.

Sources: alayala's explicit selections in this conversation; [BullMQ backend comparison](https://docs.bullmq.io/guide/postgresql), [global concurrency](https://docs.bullmq.io/guide/queues/global-concurrency), and [safe job retries](https://docs.bullmq.io/patterns/idempotent-jobs). Discussion evidence: [worker and outbox session](ai/sessions/2026-10-02-redis-bullmq-outbox-data-contract.md).

### A7 — Transactional job_outbox for reliable dispatch: closed

Category: **Technical / code**.

Status: accepted by alayala on October 2, 2026. Documentation only; not implemented or runtime-tested.

**Choice:** Include a `job_outbox` table in PostgreSQL. Save the refresh request and its pending job-dispatch record in the same PostgreSQL transaction. A dispatcher sends committed pending requests to BullMQ in Redis and retries failed delivery. Queue messages carry stable identifiers that link them to the application refresh record.

An outbox is a durable list of work requests waiting to be sent. It is application-owned data, separate from BullMQ's queue state.

**Required flow:**

1. Commit the application refresh record and its `job_outbox` request together. If the transaction rolls back, neither record is saved and that request must not be dispatched.
2. The dispatcher sends the committed request to BullMQ and records the delivery outcome. A failed delivery remains available for retry.
3. The worker executes the requested pipeline work and records its outcome in PostgreSQL. Receiving the same request again must not duplicate the refresh's effects or publish the same transition twice.

**Failure example:** PostgreSQL commits a refresh request, then the application crashes before Redis receives its job. The pending outbox record survives. After recovery, the dispatcher can send it. If enqueue succeeds but the dispatcher crashes before recording delivery, it may send the same request again; stable identity and duplicate-safe processing must handle that case.

**Reason:** An accepted refresh request should remain recoverable when dispatch to the queue fails. The outbox makes the refresh request and the obligation to dispatch it one database commit. It does not promise exactly-once delivery or make Redis and PostgreSQL one transaction.

**Rejected alternative:** Save the refresh request and then enqueue directly, with no durable record of pending dispatch. A crash between those operations can leave a saved request with no queued work and no reliable way to resume delivery.

**Tradeoff:** Add an outbox table and a dispatcher, plus retry, retention, and recovery rules. Duplicate delivery remains possible. Jobs must be safe to retry, as required by the chosen failure handling.

**Details still open:**

- Columns, field types, constraints, dispatch status values, payload shape, and stable identifier rules.
- Safe claiming by concurrent dispatchers, delivery retry/backoff limits, and retention.
- How to detect and recover work lost after Redis acknowledged delivery, including Redis persistence and application/queue reconciliation.
- Which later pipeline actions enqueue new jobs, and how retries avoid duplicate files, state transitions, or publication.

**Validation still required:** Exercise transaction rollback, Redis unavailable during dispatch, dispatcher crash before and after enqueue, duplicate delivery, concurrent dispatchers, worker retry, and Redis restart. Confirm that required validation and Admin approval still govern publication. None of these runtime checks has run.

**History:** Alayala accepted `job_outbox` after selecting PostgreSQL + Redis + BullMQ and explicitly requested that it be added to this decision record. This completes the queue handoff choice; the detailed data contract remains open.

Sources: alayala's acceptance in this conversation; [AWS transactional outbox guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html) and [BullMQ idempotent jobs](https://docs.bullmq.io/patterns/idempotent-jobs). The AWS example explains the pattern; it does not select an AWS deployment or Amazon SQS for Trinity. Discussion evidence: [worker and outbox session](ai/sessions/2026-10-02-redis-bullmq-outbox-data-contract.md).

### A8 — Clerk for authentication: closed

Category: **Technical / code**.

Status: accepted by alayala on October 2, 2026. Provider selected; integration and test users are not implemented.

**Choice:** Use Clerk as the external authentication provider. The backend remains responsible for enforcing Viewer, Analyst, and Admin access on every protected path, as required by A4. Selecting Clerk does not select a backend language or framework.

**Reason:** Delegate login and identity management to an external provider while Trinity implements its data-access rules. Alayala selected Clerk after the provider discussion.

**Rejected alternative:** Implement local credentials and login management for this challenge. A local `users` table is not required solely to authenticate users with Clerk; application-specific profile or role needs must be assessed separately.

**Proposed integration, not a completed schema decision:** Store the application role in metadata users cannot edit, validate the Clerk session in the backend, and record the Clerk user identifier for human actions such as refresh requests and approvals. Clerk documents a metadata-based role approach without Organizations. Exact claims, token validation, role-change propagation, and actor retention rules still need a contract. Do not store authentication secrets in application history or outbox payloads.

**Tradeoff:** Login depends on an external provider and its configuration. Local evaluator setup needs working provider configuration and a test identity for each persona. No provider account, paid plan, registration flow, or organization model is selected by this decision.

**Verification still required:** Provision Viewer, Analyst, and Admin test identities; verify login and invalid/expired-session rejection; prove permissions on catalog, previews, SQL, refresh, settings, and approval. Missing or unknown roles must not grant access. No authentication runtime test has run.

Sources: alayala's explicit selection in this conversation; [Clerk metadata-based access control](https://clerk.com/docs/guides/secure/basic-rbac). Supporting record and proposed models: [Clerk and application models session](ai/sessions/2026-10-02-clerk-and-application-models.md).

## Finalized specifications

### A9 — Data contract v1: finalized

Category: **Technical / code** and **Product / business**.

Status: finalized by AI on October 2, 2026, under alayala's instruction, “finalize the data contract.” This delegates the specification work; it is not a claim that alayala independently chose or verified every new default. No application implementation or runtime test is included. A1–A8 remain accepted.

**Choice:** Use [data contract v1 and its schema diagrams](docs/schema.md) as the canonical analytical and application-state specification. It defines daily natural keys, source IDs as text, exact decimal storage, null behavior, same-day percentage calculations, validation gates, immutable manifests, the ten application models, and publication ordering.

**New v1 defaults:** `DECIMAL(24,6)` with exact-fit parsing; history from 2024-10-02 through the newest national observation pinned by the worker before extraction; full-window refresh to capture source revisions; exact zero-MW reconciliation tolerance; policy frozen per run; monotonic run order plus non-regressing coverage for publication; and retention of all published artifacts. These are Trinity scope and implementation rules, not promises made by EIA. Missing entity observations stay “not reported.”

**Reason and evidence:** [F1–F5 and AN-01–AN-03](FINDINGS.md) support the daily keys, same-date metric, changes in membership/capacity, and the need to validate independently of the facility API's misleading total. Immutable versions and one complete validation attempt keep mixed or partial data from becoming visible. The outbox preserves both initial refresh dispatch and publication dispatch. Newer publications cannot be replaced by late approval of older candidates.

**Rejected alternatives:**

- Generator-only identifiers or plant names as keys: the source reuses generator labels across plants, and names are descriptive.
- Binary floats, averaged percentages, or zero-filled missing rows: these can change source values or the metric's meaning.
- Incremental append-only history: it assumes that older source values never change, which has not been established.
- Treating the facility advertised total as the expected count: AN-03 directly contradicts that rule.
- Combining passing checks from different attempts or updating live files in place: neither guarantees that queries use the complete validated candidate.
- Applying edited settings to pending versions or approving old versions without ordering: this can change the agreed workflow or move users back to older data.

**Tradeoffs:** Full-window fetches and retaining published snapshots use more network and disk. Strict zero-tolerance reconciliation can hold back legitimate future source rounding changes; investigate and revise the rule explicitly instead of changing the evidence. The selected decimal precision is a storage boundary. No performance claim follows from these choices.

**History and precedence:** The October 2 Clerk/model session remains an unchanged historical proposal. This specification replaces its proposed fields where they differ. Earlier “open” implementation lists in A2–A8 describe their original decision scope; A9 closes the logical fields, validation, policy snapshots, recovery obligations, and publication invariants covered by the contract. Finite worker/request limits, DDL, supported SQL, parser/table authorization, role-token details, and a product stale-age threshold remain separate implementation decisions. A9 does not close all Arkham decision topics.

**Verification required:** Implement and execute the contract's acceptance scenarios, including exact decimals, all required checks in one attempt, missing data, Redis loss, worker fencing, approval ordering, and readers that overlap publication. Restore self-contained reproduction inputs and scripts. Historical evidence was not rerun and no permission boundary was runtime-tested in this task.

Supporting record: [data-contract session](ai/sessions/2026-10-02-data-contract-v1.md).

## Arkham decision topics still to complete

The brief requires a choice, a rejected alternative, and a reason for each topic. This table tracks coverage; it does not close missing choices.

| Required topic | Current status |
|---|---|
| Natural keys for national, facility, and generator data | Specified by A9: `period`; `(period, facility)`; `(period, facility, generator)`. Implementation and new extraction checks remain pending. |
| Meaning of kept current and how refresh achieves it | A2–A3 plus A9 specify schedule, supported history, full-window revision capture, and separate source/publication times. A product stale-age threshold remains open. |
| Missing facilities and generator/facility disagreement | A9 specifies “not reported” for absent observations, exact cross-grain checks, blocked publication on required failure, and retained evidence. Common source omissions remain a limit. |
| Synchronous or asynchronous refresh | Accepted in A6: the full pipeline runs in background workers with bounded concurrency. A7 defines reliable dispatch. Detailed execution mechanics and verification remain open. |
| Supported and rejected SQL | Open. Selecting DataFusion does not select the allowed SQL subset. |
| Finding every referenced table before permission checks | Open. No detection or authorization implementation exists. |
| At least one additional decision shaping the solution | A3 and A4 record additional choices. Implementation and verification remain pending. |

Source: `Software Engineer - Technical Challenge.pdf`, pages 6–7. See [FINDINGS.md](FINDINGS.md) for data evidence and [NOTES.md](NOTES.md) for AI use.
