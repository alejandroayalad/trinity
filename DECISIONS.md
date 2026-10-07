# Decisions — Trinity

Status: documentation and data-contract specification, October 3, 2026. Accepted means the author selected the choice. A9 is an AI-authored specification produced under the user's request to finalize the contract; individual new defaults have not been separately reviewed by the author. Neither status means implemented or tested.

This is the main decision record. A1–A4 were moved from `First Aproximation.md` without changing their accepted scope. Use one file with unique IDs and Product / business or Technical / code categories. Keep the history when a later decision changes an earlier one.

## Accepted decisions

| ID  | Category           | Choice                                                                                                          |
| --- | ------------------ | --------------------------------------------------------------------------------------------------------------- |
| A1  | Technical / code   | One decision document with categories.                                                                          |
| A2  | Product / business | Scheduled and manual Admin refreshes, with validation before publication.                                       |
| A3  | Product / business | One initial account setup and editable shared schedule; A16 replaces selectable publication mode.                                       |
| A4  | Technical / code   | PostgreSQL for application state; Apache DataFusion for outage queries over Parquet.                            |
| A5  | Product / business | Validation controls publication; no user warning for the known facility count issue after required checks pass. |
| A6  | Technical / code   | Background workers run the full refresh pipeline using BullMQ and Redis, with bounded concurrency.              |
| A7  | Technical / code   | PostgreSQL `job_outbox` records dispatch requests with application changes; retries must be safe.               |
| A8  | Technical / code   | Historical Clerk selection; superseded for the challenge by A20. |
| A10 | Technical / code   | Python for the backend API and background workers.                                                           |
| A11 | Technical / code   | FastAPI for the Python backend HTTP API.                                                                      |
| A12 | Technical / code   | Psycopg 3 for PostgreSQL access and Alembic for schema migrations.                                              |
| A13 | Technical / code   | PyArrow for Parquet preparation, datafusion-python for queries, and SQLGlot for SQL inspection.                 |
| A14 | Technical / code   | Application-owned persisted outage data in S3; exploration does not fetch live EIA data.                       |
| A15 | Technical / code   | Feature-based backend package with separate query execution and explicit ownership, validation, and recovery. |
| A16 | Product / business and Technical / code | Approved API flow, fixed warning-based publication, serialized refresh/recovery and detailed HTTP schemas. |
| A17 | Technical / code   | Exact dependency versions and locked installation/update policy; compatibility checks remain pending. |
| A18 | Technical / code   | Required v1 single-table SQL; joins, CTEs, and subqueries are optional after the core works and its tests pass. |
| A19 | Technical / code | Security contract: trusted server-side roles (local authentication under A20), selected SQL functions, per-query containers, shared admission, bounded retries and local Docker Compose. |
| A20 | Technical / code | Seeded local authentication for the challenge; unchanged server-side permissions; Clerk deferred to future production work. |
| A24 | Technical / code | Publication first delivery: one worker host, executable operator reconciliation and separate Admin same-candidate retry; automatic crash recovery deferred. |
| A25 | Product / business | Alayala's Figma mockups and the ChatGPT-created Trinity brand are the inputs for the planned Claude design handoff, with separate authorship records. |
| A26 | Technical / code | React, TypeScript and Vite for the web frontend in `frontend/`; other packages need separate approval; exact versions under A17. |
| A27 | Technical / code | Compress new JSON evidence with versioned storage identities; keep existing stored versions readable and retain all integrity checks. |
| A28 | Technical / code | First EC2 deployment hosts both frontend and backend; Caddy serves the compiled frontend and proxies the API. |

### A1 — arrangement of decisions: closed

Status: accepted by alayala on October 1, 2026.

Choice: use one root `DECISIONS.md` with unique decision IDs and these categories:

- **Product / business:** user needs, business rules, product behavior, and scope.
- **Technical / code:** architecture, data handling, security, implementation, and verification choices.

Rejected alternative: separate product and technical decision files with a root index.

Reason: one file keeps Arkham's required decisions easy to find. Categories distinguish the two kinds of decisions without separate logs or a second index.

Record each decision once. If it affects both categories, use both labels on the same entry.

### A2 — refresh and publication policy: closed

**Current rule:** [A16](#a16--approved-api-flow-and-detailed-contract) supersedes the selectable publication policy and recovery behavior recorded below. Setup edits only the daily schedule; publication is automatic without review warnings and requires approval with warnings. The following original rationale is historical where it conflicts with A16.

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

**Current rule:** [A16](#a16--approved-api-flow-and-detailed-contract) supersedes the selectable publication policy and recovery behavior recorded below. Setup edits only the daily schedule; publication is automatic without review warnings and requires approval with warnings. The following original rationale is historical where it conflicts with A16.

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

**Current scope / supersession:** A16 supersedes references below to configurable publication mode; PostgreSQL state and DataFusion analytical separation are unchanged.

Category: **Technical / code**.

Status: accepted by alayala on October 1, 2026. This records the selected architecture direction. It is not a measured claim that this is the fastest or simplest option.

Closure confirmed on October 2, 2026. Session evidence: [A4 decision session](ai/sessions/2026-10-02-a4-state-and-outage-queries.md).

**Choice:** Use PostgreSQL for persistent application state. Use Apache DataFusion to execute permitted outage queries directly over the published Parquet datasets.

| Component | Responsibility |
|---|---|
| PostgreSQL | Store shared setup/schedule, refresh outcomes, frozen warning policy, approvals, failure recovery and published-version identity; A16 removes a selectable account publication mode. |
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

**Current scope / supersession:** A16 supersedes only the shared publication-mode reference below: required checks plus no review warnings publish automatically; review warnings require approval. The known facility-total issue remains informational after required checks pass.

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

**Current scope / supersession:** A16 closes refresh admission at one lifecycle, including pending review and unresolved failure. A19 selects external-failure attempts and analytical limits; earlier open-count/policy text below is historical.

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

**Current scope / supersession:** A20 rolls back Clerk for the challenge and replaces this choice with seeded local authentication. The original selection and reaffirmation below are historical, not current setup requirements. Clerk is future production work; no dual-provider implementation is required.

Category: **Technical / code**.

Status: accepted by alayala on October 2, 2026. Provider selected; integration and test users are not implemented.

**Choice:** Use Clerk as the external authentication provider. The backend remains responsible for enforcing Viewer, Analyst, and Admin access on every protected path, as required by A4. Selecting Clerk does not select a backend language or framework.

**Reason:** Delegate login and identity management to an external provider while Trinity implements its data-access rules. Alayala selected Clerk after the provider discussion.

**Reaffirmation:** Alayala considered local login and retained Clerk to follow the approach he would use in a professional team: delegate authentication and own Trinity's authorization and data behavior. This is his engineering rationale, not a claim that a provider earns a higher evaluation score. See the [October 3 handoff](ai/sessions/2026-10-03-vault-reconciliation-and-handoff.md).

**Rejected alternative:** Implement local credentials and login management for this challenge. A local `users` table is not required solely to authenticate users with Clerk; application-specific profile or role needs must be assessed separately.

**Proposed integration, not a completed schema decision:** Store the application role in metadata users cannot edit, validate the Clerk session in the backend, and record the Clerk user identifier for human actions such as refresh requests and approvals. Clerk documents a metadata-based role approach without Organizations. Exact claims, token validation, role-change propagation, and actor retention rules still need a contract. Do not store authentication secrets in application history or outbox payloads.

**Tradeoff:** Login depends on an external provider and its configuration. Local evaluator setup needs working provider configuration and a test identity for each persona. No provider account, paid plan, registration flow, or organization model is selected by this decision.

**Verification still required:** Provision Viewer, Analyst, and Admin test identities; verify login and invalid/expired-session rejection; prove permissions on catalog, previews, SQL, refresh, settings, and approval. Missing or unknown roles must not grant access. No authentication runtime test has run.

Sources: alayala's explicit selection in this conversation; [Clerk metadata-based access control](https://clerk.com/docs/guides/secure/basic-rbac). Supporting record and proposed models: [Clerk and application models session](ai/sessions/2026-10-02-clerk-and-application-models.md).

### A10 — Python for the backend API and workers: closed

Category: **Technical / code**.

Status: accepted by alayala on October 3, 2026. Language selected; implementation and runtime verification pending.

**Choice:** Use Python for the backend API and the background workers that execute A6's full refresh pipeline. Keep PostgreSQL for application state, DataFusion for published Parquet queries, BullMQ with Redis for background jobs, and seeded local authentication under A20. A4 and A6–A7 remain unchanged.

**Reason:** Python fits the proposed PyArrow file preparation and DataFusion Python query path and lets the API and refresh workers share one application language. This is a design rationale, not a compatibility or performance result. Concrete packages and versions still need selection and verification.

**Flow and failure example:** A request presents a local session token; the backend verifies identity, resolves a trusted role, and authorizes the operation. Permitted analytical reads capture one active publication and use only authorized files from that version. Decimal results preserve A9's exact-value contract. An Analyst query referencing PostgreSQL `job_outbox` must be rejected before execution. Selecting Python does not implement table-reference detection or authorization.

**Alternative not selected:** Use separate application languages for the API and data workers. A single language avoids adding a second application toolchain for this scope. No comparative benchmark or user rejection of a specific competing language is claimed.

**Tradeoff and verification:** BullMQ's current Python development source exposes `setGlobalConcurrency`; that is not evidence that a chosen release works correctly across workers. Pin a compatible release, verify two workers respect a queue-wide limit of one active job, and exercise worker restart and duplicate-safe recovery. Verify DataFusion/PyArrow decimal compatibility and SQL isolation separately. No dependency installation or runtime test has run for this decision.

**Still open:** Python and dependency versions; frontend; authentication integration; API contracts; SQL subset and table-reference detection; execution and row limits. A11 selects FastAPI; A12 selects Psycopg 3 and Alembic; A13 selects PyArrow, datafusion-python, and SQLGlot. A14 clarifies the application-owned storage boundary.

**History:** Resolves the backend-language question left open in A4, A6, A8, and the October 3 handoff. It does not reopen A9 or authorize implementation or Git publication.

Sources: alayala's acceptance in this conversation; [DataFusion Python concepts](https://datafusion.apache.org/python/user-guide/basics.html); [BullMQ Python source](https://github.com/taskforcesh/bullmq/blob/master/python/bullmq/queue.py). Supporting record: [Python decision session](ai/sessions/2026-10-03-python-backend-selection.md).

### A11 — FastAPI for the backend HTTP API: closed

Category: **Technical / code**.

Status: accepted by alayala on October 3, 2026. Framework selected; not installed or runtime-tested.

**Choice and reason:** Use FastAPI for A10's Python HTTP API. Its request validation and generated OpenAPI documentation support the required catalog, preview, query, and Admin contracts. This selects the framework, not the endpoint schemas or security policy.

**Flow and failure example:** A preview request passes field validation and backend identity/permission checks before accessing a permitted published dataset. The API returns JSON under the eventual response contract. A Viewer requesting generator detail must be denied before DataFusion execution. FastAPI validates request structure; Trinity must implement local session verification, role enforcement, SQL authorization, and resource limits.

**Alternative not selected:** Assemble request validation and API documentation separately around a smaller HTTP framework. FastAPI provides these facilities together; no comparative performance claim is made.

**Tradeoff and boundaries:** Request/response models must stay aligned with the API contract, including exact decimal serialization. Framework defaults are not proof of correct authentication or SQL isolation. Refresh work continues through PostgreSQL outbox dispatch to BullMQ workers under A6–A7; selecting FastAPI does not replace that path with in-process background tasks.

**Verification still required:** Pin compatible Python/FastAPI dependencies; verify request validation, generated API schemas, decimal responses, local authentication, role denials, and error handling. Dependency versions, API contracts, SQL rules, and limits remain open. A12 selects the PostgreSQL driver and migration tool; A13 selects the query binding and parser.

Source: alayala's acceptance in this conversation; [FastAPI official features](https://fastapi.tiangolo.com/features/). Supporting record: [backend selection session](ai/sessions/2026-10-03-python-backend-selection.md#fastapi-follow-up).

### A12 — Psycopg 3 and Alembic for PostgreSQL: closed

Category: **Technical / code**.

Status: accepted by alayala on October 3, 2026. Tools selected; dependencies and migrations not installed or executed.

**Choice and reason:** Use Psycopg 3 for PostgreSQL application-state access and Alembic for versioned schema migrations. Psycopg's explicit transaction blocks fit A7/A9's atomic state changes. Alembic tracks ordered schema revisions so the database definition can be reproduced and evolved with the application.

**Flow and failure example:** An authorized Admin refresh request inserts `refresh_runs` and `job_outbox` in one PostgreSQL transaction. If the outbox insert fails, both inserts roll back; the API must not report the request as accepted. After commit, the dispatcher can enqueue the durable request under A7. Alembic supplies the schema migrations before the application uses these tables; it does not execute user outage queries.

**Alternative not selected:** Build a custom migration runner around manually ordered SQL files. Alembic provides revision tracking without maintaining that mechanism ourselves. The selection does not claim that other PostgreSQL drivers cannot implement the transaction contract.

**Tradeoff and scope:** Alembic adds SQLAlchemy as a dependency. This does not select ORM models for application queries; explicit parameterized SQL through Psycopg remains the proposed access style. Migration code still needs review and testing. Outage rows and user SQL remain in DataFusion over published Parquet under A4.

**Verification still required:** Pin compatible Python, Psycopg, Alembic, SQLAlchemy, and PostgreSQL versions. Create and test migrations against A9, including constraints and clean-database setup. Prove run/outbox rollback, duplicate-safe requests, publication transactions, and connection cleanup. Pooling and sync/async execution details remain open.

Sources: alayala's acceptance in this conversation; [Psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html); [Alembic documentation](https://alembic.sqlalchemy.org/en/latest/) and [dependencies](https://alembic.sqlalchemy.org/en/latest/front.html#dependencies). Supporting record: [database tools follow-up](ai/sessions/2026-10-03-python-backend-selection.md#database-tools-follow-up).

### A13 — PyArrow, datafusion-python, and SQLGlot: closed

**Current scope / supersession:** A18/A19 select single-table SQL, arithmetic, CASE and the exact function names. Whole-input SQLGlot validation remains in one module before protected reads; DataFusion compatibility still requires tests.

Category: **Technical / code**.

Status: accepted by alayala on October 3, 2026. Libraries selected; not installed or runtime-tested.

**Choice:** Use PyArrow to prepare typed Parquet under A9; use `datafusion-python` to execute permitted analytical queries; use SQLGlot to parse and inspect SQL before execution. Trinity owns the grammar allowlist, table authorization, function restrictions, and result/resource limits. SQLGlot is not itself the security boundary.

**Reason:** These libraries cover the existing Python preparation and DataFusion query responsibilities and provide structural SQL inspection. No existing application implementation is replaced by this selection.

**Alternative not selected:** Detect table references with text matching or regular expressions. SQL structure, aliases, and any supported nested queries need structured inspection rather than matching names in raw text.

**Flow and failure example:** Authenticated SQL input → supported-grammar checks → resolve and authorize all real table references → register only permitted published manifest files → bounded DataFusion execution → exact decimal response. An Analyst's CTE over `job_outbox` must either be rejected as unsupported syntax or denied for its underlying table before any analytical read.

**Tradeoff and open details:** SQLGlot and DataFusion use different parsers. Pin compatible versions and test the chosen subset; a successful SQLGlot parse is not permission to execute. The dialect, allowed grammar/functions, nested-query support, exact detection algorithm, numeric expressions, and limits remain open.

**Verification required:** A9 decimal round trips; accepted/rejected SQL examples; nested table authorization where supported; whole-input multi-statement rejection; file/URL and write rejection; parser/engine agreement; isolation between request contexts. No such runtime checks have run.

Sources: alayala's explicit acceptance; [PyArrow filesystems](https://arrow.apache.org/docs/python/filesystems.html); [DataFusion Python](https://datafusion.apache.org/python/user-guide/data-sources.html); [SQLGlot behavior](https://sqlglot.com/sqlglot.html). Supporting record: [stack clarification](ai/sessions/2026-10-03-backend-stack-review-and-layout.md#author-correction-and-accepted-stack).

### A14 — Application-owned storage and source independence: closed

Category: **Technical / code**.

Status: clarified and selected by alayala on October 3, 2026; not implemented.

**Choice:** Retain S3 from the proposed backend stack as application-owned storage for immutable Parquet versions. Alayala interprets “locally” as data persisted under the application's control, independent of fetching live data from the external EIA source during exploration. It does not impose a same-machine-disk-only storage choice. Local application startup remains a delivery requirement.

**Reason and alternative rejected:** S3 is an internal storage dependency of this application. Reject AI's proposed requirement to replace it with local disk and defer S3 solely because of that interpretation of “locally.” The service that holds application-owned files and the external service that supplies fresh observations have different responsibilities.

**Flow and failure example:** A refresh fetches EIA records and prepares/validates application-owned Parquet objects. Publication updates the PostgreSQL active pointer only after A9's checks and approval rules pass. Catalog, previews, and SQL use that publication without requesting EIA data. If EIA is unavailable, the last valid publication remains queryable when the application's own storage is available.

**Contract boundary:** Keep A9's normalized relative `storage_path`; resolve it against trusted server configuration and the immutable version root. Clients cannot supply bucket names, endpoints, object paths, or unpublished manifests. S3 storage does not replace PostgreSQL publication state or make files immutable automatically.

**Open implementation details:** S3 service/deployment, credentials and access policy, object-write protection, complete-manifest registration, and dependency versions. Verify refresh failure preservation, exact-manifest reads, unauthorized path rejection, and publication/read overlap. No cloud resource or cost is authorized by this documentation choice.

**History:** Withdraws review R1's disk-only conclusion. This is alayala's clarified project interpretation; the AI mistake and correction belong in Engineering Notes, not the EIA data findings.

Evidence: the supplied `Backend Stack.md`, alayala's correction, and the [review session](ai/sessions/2026-10-03-backend-stack-review-and-layout.md#author-correction-and-accepted-stack). A4 and A9 remain authoritative for state/query separation and publication invariants.

### A15 — Backend structure and responsibility boundaries: closed

**Publication refinement — October 4, 2026:** [A24](#a24--build-publication-first-delivery) governs the approved first-delivery operating and recovery scope. Earlier conflicting recovery expectations are historical for Publication; other guarantees remain in force.

**Current scope / supersession:** A19 refines separate query execution to one container per query, with trusted file staging, a read-only authorized Parquet mount, no network/credentials/Docker control, and PostgreSQL query admission. The feature package remains accepted.

**Dashboard feature folder — accepted October 5, 2026:** alayala selected a new `dashboard/` feature package for `GET /dashboard/national` and `GET /metrics/offline-share`, instead of placing them in `queries/` or `catalog/`. It owns the routes, input rules, metric calculation and response models. It uses the shared analytical admission, publication pinning and isolated execution from `queries/` rather than copying them. Catalog keeps metric definitions. See the [dashboard design](sdd/national-dashboard/design.md).

Category: **Technical / code**.

Status: accepted by alayala on October 3, 2026. File structure and the five reviewed refinements selected; implementation pending.

**Choice:** Use alayala's feature-based tree at `backend/src/trinity/`, documented in [docs/backend.md](docs/backend.md). Preserve its `auth`, `catalog`, `queries`, `refresh`, `publication`, `settings`, `adapters`, `workers`, `connector`, and `contracts` responsibilities. API, background workers, and isolated query execution have separate entrypoints in the shared package. Add `workers/recovery.py`.

**Accepted refinements:** The API supplies a pinned publication and permitted dataset set; runtime SQL policy checks all real table references before file registration. The launcher/supervisor enforces process isolation, deadlines, and termination in addition to runtime limits. Services own transactions shared by repositories/outbox helpers; refresh persistence owns candidate versions, artifacts, and validation results. Connector validation covers the exact written files and frozen manifest. A periodic recovery worker delegates durable unfinished-work recovery to feature services.

**Reason:** Keep HTTP contracts, feature rules, persistence, external integrations, and process entrypoints distinguishable while sharing one implementation of the application rules. These boundaries give A9's publication, validation, and recovery requirements explicit owners.

**Alternative not selected:** AI's earlier broad top-level `api/`, `storage/`, and `state/` grouping. Alayala's feature grouping keeps each capability's router, service, repository where applicable, and public schemas together. Also reject relying only on runtime-local timeout/config code for isolation or source-row checks for publication readiness.

**Flow and failure example:** API verifies identity, builds the permitted dataset set, pins one publication, and hands the request to the query runtime. Runtime rejects an unauthorized underlying table before registering files. For refresh, one service transaction saves run/outbox; workers prepare and validate the exact candidate, then publish under A9. If a queued job is lost after dispatch acknowledgment, the recovery worker invokes the durable recovery path.

**Tradeoff and remaining work:** Separate query execution requires a bounded internal protocol and process supervision. Shared package imports must not initialize privileged API/worker state in the runtime. Exact dependency versions, HTTP/SQL/authentication contracts, IPC transport, process topology, access controls, and limits remain open. The selected structure does not prove isolation or runtime correctness.

**Verification required:** Implement and test the responsibilities and failure scenarios listed in [docs/backend.md](docs/backend.md#contracts-and-verification-still-required). No application skeleton or runtime check is included in this documentation decision.

Evidence: alayala's supplied tree and acceptance of the five refinements; [folder review](ai/sessions/2026-10-03-backend-stack-review-and-layout.md#author-folder-proposal-review). Acceptance and documentation checks: [structure session](ai/sessions/2026-10-03-backend-structure-accepted.md).

### A16 — Approved API flow and detailed contract

**Failed-run recovery refinement — accepted October 5, 2026 (P01):** Run again snapshots the current committed shared settings and current approved refresh policy when the new run is accepted. Preserve the failed run's original snapshot. A concurrent settings update must yield one coherent settings revision. Alayala explicitly accepted this recommendation and authorized design/tasks after committing and pushing the acceptance. Copying the failed run's old settings is rejected because a new full refresh should use current configuration rather than repeat obsolete settings. This refines A16 in both **Product / business** and **Technical / code** categories; it does not authorize implementation or live recovery. See the [recovery specification](sdd/failed-run-recovery/spec.md#accepted-run-policy-choice).

**Publication refinement — October 4, 2026:** [A24](#a24--build-publication-first-delivery) governs the approved first-delivery operating and recovery scope. Earlier conflicting recovery expectations are historical for Publication; other guarantees remain in force.

Category: **Product / business** and **Technical / code**.

Status: high-level design accepted by alayala on October 3, 2026, through the supplied `trinity-api-contract-final.md`. Detailed request/response fields, bounded defaults and persistence amendments are AI-authored specification work under his instruction to add missing details. No implementation or runtime verification is claimed.

**A20 amendment:** Local login/logout add two authentication operations. The original product permissions and workflow remain unchanged.

**Catalog freshness refinement — accepted October 4, 2026:** alayala approved the catalog specification and requested design/tasks. `freshness.last_refresh` selects the refresh run with the greatest `run_seq` visible in the request's database snapshot, including unfinished or failed runs; no run means null. Return only its `status`, `requested_at`, and `finished_at`. This matches refresh-history ordering and makes the newest attempt visible instead of hiding it behind the last successful refresh. Publication readiness and publication-derived dates remain tied to the active publication, so a newer failed attempt does not hide usable published data. Timestamps and completion status do not change run selection. This accepts local specification detail D01 without changing the OpenAPI shape or authorizing implementation. The previous proposed wording is retained in the earlier session history. See the [catalog specification](sdd/catalog-permissions/spec.md) and [design/tasks session](ai/sessions/2026-10-04-catalog-permissions-design-tasks.md).

**Viewer navigation refinement — accepted October 4, 2026:** alayala selected a dashboard-only Viewer interface. With published data, Viewer sees national summary cards, daily trends and national table values, without Catalog or SQL navigation. Before publication, retain the waiting screen. Analyst/Admin retain Catalog and SQL navigation. Viewer keeps national-only catalog metadata and preview API permissions so the dashboard can obtain permitted data and definitions; `catalog:read` does not require a visible Catalog button. Server authorization remains mandatory on direct API requests. This refines A16's presentation, not A19/A20 permissions or the OpenAPI contract. Frontend implementation and navigation verification remain pending; include direct attempts to open Catalog/SQL screens in later frontend checks. Source: alayala's explicit request to update the [catalog proposal](sdd/catalog-permissions/proposal.md); [supporting session](ai/sessions/2026-10-04-catalog-permissions-proposal.md).

**Choice:** Use [the approved human overview and detailed API contract](docs/api-contract.md) and [OpenAPI schemas](docs/openapi.json). The original 20 product operations cover role-aware app entry, one-time shared setup, editable daily schedule, national dashboard/metric, filtered previews and entity choices, permitted SQL, refresh history/progress, atomic recovery, and candidate review in a side panel.

**Plant choice search refinement — October 5, 2026:** Alayala authorized direct completion without new SDD after the recommendation to search the exact Plant ID and displayed latest name. Search uses literal Unicode case folding without wildcard expansion or Unicode normalization; older names do not produce matches. Latest non-null labels and exact source IDs remain the existing A16 contract. The implementation resolves same-date label ties by binary ascending name order; this is an AI-selected deterministic detail, not separate human approval. The [implementation record](ai/sessions/2026-10-05-plant-filter-implementation.md) separates automated acceptance from retained deployment and frontend work.

**SQL result refinement — accepted October 4, 2026:** alayala approved the corrected one-table SQL specification by requesting design/tasks. Accept its D03 presentation rules: `execution_ms` measures the analytical interval from before downloads through bounded result collection, including retries/startup and excluding auth/parsing and cleanup; direct columns retain canonical units while expressions use null units; preserve explicit duplicate labels and generate safe bounded labels for unaliased expressions; ORDER BY defaults to ASC/NULLS LAST with fixed binary text ordering. No ordering is promised without ORDER BY. Numeric precision and ROUND compatibility still require measured design/implementation evidence. A19 records D01 grammar and D02 rate accounting. Viewer has no SQL button/menu/editor/Run action or direct API permission; frontend evidence remains separate. These choices change no OpenAPI fields and do not authorize implementation. See the [approved SQL specification](sdd/single-table-sql/spec.md) and [design/tasks session](ai/sessions/2026-10-04-single-table-sql-design-tasks.md).

**Preview input and cursor refinements — accepted October 4, 2026:** alayala confirmed D01 and D03 in the [preview specification](sdd/dataset-preview/spec.md). Strictly validate scalar inputs: reject duplicates, empty values, invalid dates and incompatible filters; a specific `generator` filter requires its exact `facility` (the installation). Continue pages with the same effective filters, page size and active publication; changed publication requires a restart. Reauthorize every page. Cursors have no time-only expiry while publication and signing key remain valid; restart retains the configured key, and retired-key cursors fail safely. The specification defines normalization and error precedence; encoding/key management remain design work. A19 records D02 shared rate accounting. No OpenAPI field, role or SQL grammar changes. Approval is specification evidence, not preview runtime proof or authorization to implement. See the [acceptance record](ai/sessions/2026-10-04-dataset-preview-specification.md#specification-acceptance).

**National dashboard refinements — accepted October 5, 2026:** alayala accepted D01–D03 in the [dashboard specification](sdd/national-dashboard/spec.md). Dashboard cards follow the selected range and show its end date, as `summary` already requires. D01: dashboard and metric use preview's strict input checks. D02: calculate with exact decimals and round with `ROUND_HALF_UP` to two places; halfway negative values round away from zero (`-12.345 → -12.35`); rounded zero is `0.00`, never `-0.00`. D03: both endpoints return the national diagnostics bound to the pinned publication, unchanged by the selected date; publication and freshness come from one database snapshot. A19 records D01 rate accounting. No OpenAPI field, role or endpoint changes. Approval is specification evidence, not runtime proof or authorization to implement. See the [specification session](ai/sessions/2026-10-05-dashboard-backend-priority.md#dashboard-specification-acceptance).

**Next slice — Step 5, Refresh and publication — accepted October 4, 2026:** alayala selected the publication lifecycle as the next implementation slice after confirming the missing production activation path. Record the candidate and its complete frozen validation/diagnostic results; publish automatically only when required checks pass and no review warnings remain; require bound Admin approval when review warnings exist; atomically create the publication event and switch the active version with the associated lifecycle state under A9. Readers retain the previous complete publication or observe the new complete publication, never partially published state. Failed or incomplete required checks remain unpublished even with Admin approval. This confirms existing A16/A9 behavior and changes delivery sequencing: publication is a separate dependency for real-data SQL/preview delivery, not work supplied by SQL T16/T18/T20 tests. Catalog remains complete, SQL implemented with its recorded verification gaps, and preview planning is preserved. This decision does not implement or activate a publication. See the [decision record](ai/sessions/2026-10-04-refresh-publication-next-slice.md).

**Schedule settings refinements — accepted October 5, 2026:** alayala accepted the [schedule settings specification](sdd/schedule-settings/spec.md) and its D01–D03. D01: a daily occurrence at UTC instant `T` is due only while `T ≤ now < T + 300 seconds` and only when `T` is later than the settings `updated_at`; after that window it is missed and skipped with no record or backlog. D02 (alayala's rule, replacing the AI recommendation of a new revision on every save): `PUT /settings` checks `If-Match` first and returns `412` when stale; then, if `schedule_enabled`, `daily_time` and `timezone` equal the stored values, it returns the current settings and revision without writing and without changing `updated_at`; otherwise it creates the next revision. A stale client never receives `200`. D03: PostgreSQL `clock_timestamp()` is the only clock for status, due tests and settings timestamps; a separate `scheduler` worker role evaluates at least every 30 seconds. A19 records the role's secret boundary. Timezones must be exact members of the runtime IANA list. No OpenAPI field, role or endpoint changes. Approval is specification evidence, not runtime proof or authorization to implement. See the [specification session](ai/sessions/2026-10-05-schedule-settings-specification.md).

**Publication and recovery:** Publication behavior is fixed: complete required checks and no review warnings publish automatically; complete required checks with frozen warnings require Admin approval; failed or incomplete checks block publication. No editable publication mode remains. One refresh lifecycle is admitted at a time, including pending review and unresolved failure. Run-again creates a new full run and abandons the old candidate; warning deletion resolves the block without new work; publication retry preserves the same eligible candidate and original approval requirements; discard permanently prevents publication while preserving history.

**Reason and rejected alternatives:** Follow the author's approved UI/API flow and make requests, results and recovery unambiguous. Replace the earlier selectable automatic/approval account mode. Reject resuming a failed full refresh through Run again, deleting failure history when clearing a warning, treating accepted work as publication success, and letting concurrent recovery actions both take effect.

**Flow and failure example:** Admin saves setup with an ETag, then separately starts the first refresh. A validated candidate with warnings occupies the lifecycle slot and opens in the run page side panel. Approval atomically records authorization and publication outbox work. If publication later exhausts its retries, the Admin can retry that exact eligible candidate or abandon it. Simultaneous retry and discard cannot both succeed; transaction locks, revisions and worker fences protect the chosen outcome.

**Precedence and history:** Supersedes A2/A3's selectable publication policy and A9's original recovery exclusions, while preserving analytical keys, measurements, exact reconciliation, immutable files, published-only access and monotonic publication. [schema.md](docs/schema.md) now includes the supporting warning/admission/command records and nonterminal publication_failed state. The original A2/A3 text below their current-status notices is retained as history. A5's known facility-total issue remains informational after required checks pass, not an automatic review warning.

**Delegated completion details:** Exact field names/types/nullability, role landing values, 365-day yearly preset, bounded paging, command idempotency/ETags, diagnostic severity mapping, and added persistence fields are attributed to AI. The supplied design fixes behavior; these completion defaults make it implementable and reviewable without claiming separate author review of every field. A17 versions and A18 staged SQL scope remain accepted independently. Detailed security rules were not accepted by this API-flow approval; A19 now records their separately accepted scope. Exact implementation settings and verification remain pending.

**Validation required:** Check all schema examples, every approved endpoint, safe role-specific responses, dashboard/metric agreement, pagination/version conflicts, concurrent recovery, warning publication gates, lost queues, stale workers, and terminal candidate disposition. Specification checks do not prove endpoint or database behavior. No new commit/push was requested for this expansion.

Source and contributions: [approved API completion session](ai/sessions/2026-10-03-approved-api-contract-expanded.md). The supplied source is preserved unchanged outside the repository; its approved human flow is included in the contract.

### A17 — Dependency versions and update policy: closed

**A20 amendment:** Remove `clerk-backend-api` from challenge dependencies. Its former 7.0.0 pin and compatibility notes below are historical only. No replacement password library/version is selected here; check existing runtime support before adding one. All other selected versions and the lockfile policy remain unchanged.

**October 5, 2026 amendment:** Alayala approved changing the pin to `boto3[crt]==1.43.108`. Reason: the Compose S3 workers use the host `trinity-writer` profile, whose source profile uses `aws login`; botocore raised `MissingDependencyException` without `awscrt`. `uv lock` added only `awscrt` 0.36.0. The backend offline suite passed in the rebuilt image (790 ran, 258 opt-in skips). Advisory review of `awscrt` and credential resolution in the running workers remain unverified.

Category: **Technical / code**.

Status: accepted by alayala on October 3, 2026. Exact versions selected; installation, dependency resolution, advisory review, and runtime compatibility remain unverified.

**Choice:** Use CPython **3.14.8**, regular GIL build, with `requires-python = ">=3.14,<3.15"`, and **uv 0.12.23**. Record the Python patch in `.python-version` and deployment configuration. Use the exact package versions below and a committed `uv.lock` covering transitive dependencies and hashes when implementation begins. CI must install with `uv sync --locked`. Use minimal extras rather than the full FastAPI standard bundle.

| Responsibility | Approved package versions | Reason |
|---|---|---|
| HTTP and schema validation | [fastapi 0.142.2](https://pypi.org/project/fastapi/0.142.2/), [uvicorn 0.54.0](https://pypi.org/project/uvicorn/0.54.0/), [pydantic 2.13.5](https://pypi.org/project/pydantic/2.13.5/), [pydantic-settings 2.15.0](https://pypi.org/project/pydantic-settings/2.15.0/) | Selected API plus server, typed payloads, and environment configuration. |
| PostgreSQL runtime | [psycopg 3.3.6](https://pypi.org/project/psycopg/3.3.6/) with `binary` extra; [psycopg-pool 3.3.3](https://pypi.org/project/psycopg-pool/3.3.3/) | A12 driver and bounded connection reuse. |
| Migrations | [alembic 1.20.0](https://pypi.org/project/alembic/1.20.0/), [SQLAlchemy 2.1.3](https://pypi.org/project/SQLAlchemy/2.1.3/) | Alembic requires SQLAlchemy; restrict its use to migration infrastructure, preserving direct Psycopg repositories. |
| Analytical execution | [pyarrow 25.0.1](https://pypi.org/project/pyarrow/25.0.1/), [datafusion 54.0.0](https://pypi.org/project/datafusion/54.0.0/), [sqlglot 30.21.0](https://pypi.org/project/sqlglot/30.21.0/) | A13 stack; install name is `datafusion`, not `datafusion-python`. |
| Queue | [bullmq 3.3.0](https://pypi.org/project/bullmq/3.3.0/) | Python package under A6; its metadata requires `redis==7.4.1`, `msgpack==1.2.3`, `semver==3.1.0`, and `croniter==2.0.7`. These are package versions, not the Redis server version. |
| External HTTP | [httpx 0.28.1](https://pypi.org/project/httpx/0.28.1/) | Reuse HTTPX for EIA HTTP and bounded timeouts. A20 removes clerk-backend-api from the challenge dependency set. |
| Object storage | [boto3 1.43.108](https://pypi.org/project/boto3/1.43.108/) with `crt` extra | Official AWS SDK for application-owned S3 operations; privileged API/worker adapter only. The `crt` extra adds `awscrt` (locked at 0.36.0), which botocore requires to read `aws login` credentials. |

Server versions: **PostgreSQL 18.6** and **Redis 8.10.2**. The Redis server version is separate from BullMQ's `redis` Python client version. Exact deployment images/digests, frontend packages, and cloud resources remain outside this selection.

**Reason:** Repeatable installations let developers reproduce behavior and review dependency changes. The libraries extend the stack selected in A10–A13 with the HTTP server, configuration, identity, connection pool, HTTP client, and S3 adapters required by those responsibilities. SQLAlchemy supports Alembic migrations; A12's application repositories continue to use Psycopg directly.

**Rejected alternative:** Floating latest packages or images, development-branch dependencies, and automatic major-version upgrades. These can change behavior without a reviewed application change. Update pins and the lockfile deliberately, check advisories, prioritize security fixes, and run affected regression checks.

**Flow and failure example:** A developer installs the selected Python release and committed lockfile. If project requirements and the lock disagree, the locked install fails rather than silently selecting another SQL parser. A parser upgrade must pass the SQL-policy regression corpus before deployment.

**Evidence and verification:** The earlier October 3 public release/metadata lookup established the listed versions and declared constraints. DataFusion 54.0.0 requires PyArrow >=22 for Python >=3.14; 25.0.1 satisfies that declaration. Clerk 7.0.0 requires Pydantic >=2.11.2 and HTTPX >=0.28.1; the selected versions meet those declarations. These comparisons do not resolve the full dependency graph or prove security, native-wheel availability, decimal behavior, authentication, queue concurrency, or recovery. No packages, lockfile, database, or cloud resources have been installed or created. Run resolver, advisory, platform, and integration checks during implementation; report a conflict rather than silently changing an approved pin.

**Scope and history:** This accepts the dependency versions and repeatability policy from the earlier proposal. Alayala explicitly keeps the API and security contracts under review. SQL restrictions, Clerk role/session lookup behavior, async/pool execution choices and their numeric limits, scheduling details, and process isolation are not approved by this dependency decision. The version numbers are unchanged from the reviewed proposal. Alayala also authorized committing and pushing the dependency update on the current branch; no API/security publication, implementation, PR, or merge was requested.

Sources: [Python 3.14.8](https://www.python.org/downloads/release/python-3148/), [uv 0.12.23](https://pypi.org/project/uv/0.12.23/), per-package release links above, [PostgreSQL version policy](https://www.postgresql.org/support/versioning/), [Redis 8.10.2](https://github.com/redis/redis/releases/tag/8.10.2), and [uv locking](https://docs.astral.sh/uv/concepts/projects/sync/). Supporting record: [dependency acceptance session](ai/sessions/2026-10-03-dependency-versions-accepted.md).

### A18 — SQL scope by stage: closed

**Current scope / supersession:** A19 resolves function names and adds arithmetic/CASE. The staged scope and optional-extension gate remain unchanged; earlier statements leaving all functions open are historical.

Category: **Technical / code**.

Status: accepted by alayala on October 3, 2026. Scope selected; implementation and tests pending.

**Choice:**

| Stage | SQL scope |
|---|---|
| Required v1 | Single-table SELECT, filters, sorting, grouping, and approved aggregate functions. |
| Optional extension | Add joins, CTEs (WITH queries), and subqueries after the core works and its tests pass. |

**Reason and alternative:** Establish and test the core query behavior before expanding SQL complexity. Do not require joins, CTEs, or subqueries for v1; these remain optional even after the core passes its tests.

**Flow and failure example:** SQL input → supported-syntax and table-permission checks → DataFusion over permitted published Parquet → query results. In v1, a query joining two otherwise permitted datasets must be rejected before file registration because joins are outside the required scope. A4/A9/A13 retain the application-state and unpublished-file boundaries.

**History and remaining decisions:** Accepts the staged SQL scope previously proposed within A16. It does not accept the rest of A16, the exact aggregate-function allowlist, dialect, detailed expressions, or execution limits. Those details remain under review in [the SQL policy proposal](docs/security-contract.md#sql-policy).

**Verification required:** Core acceptance tests must cover single-table SELECT, filters, sorting, grouping, approved aggregates, and rejection of joins, CTEs, and subqueries. Permission and published-data boundaries must also be tested. Optional extensions need their own syntax and authorization tests before use. No runtime tests have run.

Source: alayala's supplied stage/scope table. Supporting record: [SQL scope session](ai/sessions/2026-10-03-sql-scope-by-stage.md).

### A19 — Security contract and local execution: closed

**Verified evidence cache — accepted October 6, 2026:** Alayala approved a first fix for QA-03: a per-process cache of successfully verified diagnostic summaries, initially 16 entries with a fixed 60-second expiry after verification. These are starting values to revisit with measurements. He additionally requires one download/verification for concurrent requests needing the same evidence. Share verification by the complete pinned publication/evidence identity and trusted storage namespace, including across datasets; return only the caller's authorized dataset projection. Cache immutable safe summaries only, never raw evidence, query rows, authority, failures or partial verification. Every request retains fresh authorization, publication pinning, rate accounting and capacity admission. A changed identity misses immediately; expiry, eviction or process restart requires full verification, with no expired fallback on failure. Each waiter retains its own deadline/cancellation; shared work has the original fill deadline, and its execution owner keeps its slot until it stops. Preserve per-query containers and `Cache-Control: no-store`. Broader result caches remain unselected. The separately approved 64 MiB evidence-read limit is delivered as a prerequisite because the retained validation summary exceeds 4 MiB. See the [measured baseline](ai/sessions/2026-10-05-qa-03-evidence-read-profile.md) and [cache contract](docs/security-contract.md#verified-diagnostic-summary-cache).

**Local read activation — October 5, 2026:** Alayala approved running the SQL runtime (`compose.sql.yaml`) and opening Preview, Dashboard and choice routes on the local retained stack. `trinity.main.app` now passes `enable_preview` from `TRINITY_PREVIEW_ENABLED`; only the exact value `true` opens the routes, and any other value keeps them at 503. Local cursor keys come from the git-ignored `.env`. Accepted local tradeoffs: the read profile is `trinity-writer` (it can also write), the API holds the Docker socket, and cursor keys are visible in `docker inspect`. A separate read-only role and secret delivery remain open for any shared deployment. Alayala also raised `MAX_EVIDENCE_BYTES` (Preview diagnostics summaries) from 4 MiB to 64 MiB: the full-window `validation.json` is 14.9 MB, so every Preview failed with `query_resource_limit`. Each Preview now downloads about 15 MB of evidence; per-version caching remains a possible later improvement.

**Publication refinement — October 4, 2026:** [A24](#a24--build-publication-first-delivery) governs the approved first-delivery operating and recovery scope. Earlier conflicting recovery expectations are historical for Publication; other guarantees remain in force.

Category: **Technical / code**.

Status: accepted by alayala on October 3, 2026. Design selected; analytical capacity limits are provisional and runtime verification is pending.

**Choice:** Adopt [docs/security-contract.md](docs/security-contract.md), separate from the [A16 API contract](docs/api-contract.md). Under A20, use the local account role, writable only by trusted administration, and verify the local session/current account/current role on every authenticated request without a role/session cache. A20 supersedes the original Clerk-specific authentication mechanism only. Deny invalid, inactive, missing or unknown authority; verification outages allow no protected action.

**SQL and isolation:** Retain A18 single-table read-only SELECT; support filters, sorting, grouping, arithmetic, CASE, COUNT, SUM, AVG, MIN, MAX, ROUND, COALESCE and NULLIF. Keep one SQLGlot validation module and verify DataFusion compatibility. Reject unsupported/nested queries, writes and external readers. Run each query in its own container with only authorized published Parquet files mounted read-only, no network, no credentials and no Docker control. A trusted component downloads/checks files; the supervisor enforces limits, stops execution and cleans temporary resources. Separate private S3 read, candidate-create and publication authority. Keep A9 SHA-256 manifests/checksums and exact-file approval binding.

**Limits and recovery:** Provisional analytical limits are 1,000 output rows, 5 MiB responses, 30 seconds including file downloads/reads, 1 GiB per query container, two active analytical requests per user and four deployment-wide. Use PostgreSQL transactions for shared slots; release only after execution ends or is stopped. Accept 64 KiB JSON, 16 KiB UTF-8 SQL and initially 30 analytical requests/user/minute, excluding progress polling. Temporary external failures permit three total attempts with one- and three-second waits within the operation deadline; invalid SQL, denied access and failed validation are not retried. Preserve A16 settings revisions, single-refresh admission and explicit failed-run recovery.

**SQL slice refinements — accepted October 4, 2026:** alayala approved the corrected SQL specification and requested design/tasks. D01 selects the exact one-table grammar in the [SQL specification](sdd/single-table-sql/spec.md): canonical case-preserved identifiers/aliases, explicit projections, literal predicates, searched CASE, arithmetic, the eight selected function argument forms, column grouping, bounded literal LIMIT and ordered output. Its explicit exclusions remain denied; parser acceptance never widens this list. D02 selects a rolling 60-second, cross-process limit of 30 attempts per trusted user, counted after transport/body-shape and role authorization but before parsing. Policy/no-publication/capacity/later failures retain the debit; rate denials, invalid sessions, Viewer denials, malformed bodies, polling and internal retries do not add attempts. D03 output presentation is recorded under A16. This closes those user-visible grammar/rate/presentation choices; exact AST/configuration, numeric compatibility, persistence and container mechanics remain implementation verification. The [design/tasks](sdd/single-table-sql/design.md) request does not authorize code, builds, migrations or live execution. Earlier open-detail statements retain their historical meaning.

**Preview rate refinement — accepted October 4, 2026:** alayala confirmed D02 in the [preview specification](sdd/dataset-preview/spec.md). Preview and SQL share the same trusted-user rolling 60-second analytical counter across processes, capped at 30 admitted attempts. After current permission and primitive request-shape checks, an admitted preview request consumes one attempt even if later semantic filters, cursor checks, publication, capacity or execution fail. Malformed/unauthorized requests and rate-denied attempts add no debit; internal retries add none. Each page is a new request. The specification supplies the exact validation/debit order without changing SQL’s accepted counting boundary. This is separate from login throttling and active execution slots. A16 records D01 strict inputs and D03 cursor continuity. Implementation and mixed SQL/preview runtime verification remain pending.

**National dashboard rate refinement — accepted October 5, 2026:** alayala accepted D01 in the [dashboard specification](sdd/national-dashboard/spec.md). `GET /dashboard/national` and `GET /metrics/offline-share` use the same shared rolling counter and debit order as preview. Each admitted dashboard or metric request consumes one analytical attempt, retained when later range, publication, capacity or execution checks fail. Unauthorized, malformed and rate-denied requests add no debit. Shared slots, deadlines, mounts and cleanup rules apply unchanged. Runtime verification remains pending.

**Deployment:** Prepare Docker Compose local execution first; AWS/hosting remains undecided. The supplied challenge PDF requires local execution and a repository link; no public application URL requirement was found. Exact images, hardening, S3 policies, rate-window/storage mechanics and refresh-stage deadlines remain implementation work. A17 dependencies are unchanged.

**Scheduler role boundary — accepted October 5, 2026:** alayala accepted D03 in the [schedule settings specification](sdd/schedule-settings/spec.md). The `scheduler` worker role uses only the database setting. It loads no EIA key, S3 credential or Redis URL and makes no external call. It writes the scheduled run, its admission slot and its outbox row in one PostgreSQL transaction; the existing outbox worker dispatches the job. Compose service wiring and runtime verification remain pending.

**Reason and rejected alternatives:** Bound query access to explicitly staged files, keep authority current and enforce deployment-wide admission. Reject client-editable roles, cached role/session authority in v1, direct S3 access from query containers, per-API-process concurrency counters as the global guard, and freeing a slot on HTTP timeout alone. Retain immutable validated files instead of allowing approval to authorize changed bytes. Choose local reproducibility before selecting public hosting.

**Flow and failure example:** An authorized Analyst request pins a publication, passes the shared SQL policy, reserves a PostgreSQL slot and receives authorized staged files in a network-disabled query container. If execution exceeds its deadline, the supervisor stops it; its slot remains occupied until termination is confirmed. A restarted API cannot launch a fifth query merely because a prior supervisor lost its connection.

**History and precedence:** Refines A8/A13/A15/A18. Supersedes the combined document's `trinity_role` field, ABS proposal, 2 MiB/15-second/one-user/two-instance analytical limits and direct runtime storage-read capability. The old proposal is preserved in the [split session](ai/sessions/2026-10-03-security-contract-and-api-split.md#superseded-security-proposals). A16 remains accepted for API behavior and supersedes selectable publication modes; `publication_events.publication_mode` is a derived historical outcome only. Earlier token-claim defaults and database pool choices are not silently accepted. Existing A9 SHA-256 identity is reaffirmed.

**Validation required:** Local persona flows, denied-before-read evidence, SQLGlot/DataFusion fixtures, read-only mounts/no-network/no-secret/no-Docker checks, stop/cleanup proof, PostgreSQL multi-process admission/crash recovery, deadline-bounded retries, rate/polling behavior, immutable approval and publication races. Measure cold reads, previews, dashboards and grouped SQL before adjusting provisional limits. No such runtime tests have run.

Source: alayala's explicit security and documentation instructions; [session evidence](ai/sessions/2026-10-03-security-contract-and-api-split.md).

### A24 — Build Publication first delivery

Category: **Technical / code**.

Status: **scope, specification and design approved by alayala on October 4, 2026;
implementation of Tasks 1–6 subsequently authorized; essential local acceptance passed**.

**Choice:** deliver the reduced [Publication specification](sdd/publication/spec.md)
and [design](sdd/publication/design.md). Keep exact evidence/file verification,
warning-free automatic publication, bound Admin approval for review warnings,
atomic duplicate-safe activation and pinned analytical requests. Support one worker
host and one publication consumer, reusing Refresh's retained evidence, lifetime
lock, run fence/lease, step records, outbox and pinned BullMQ/Redis adapters.

**Operating bounds (O1):** one committed verification invocation per publication
generation, with a 300-second cooperative work deadline and no heartbeat renewal.
Retain existing bounded enqueue and S3 read retries. Do not add an automatic
whole-verifier/final-commit retry loop, per-object resume ledger or publication
child supervisor. Only an explicit eligible Admin retry creates the next generation
and fresh attempt budget. These are selected engineering bounds, not measured
throughput or a promise of process termination within 300 seconds.

**Two recovery actions:** the delivered `publication-recover` CLI runs on the
recorded worker host with the trusted worker OS account, database access and private
retained root. It checks expected generation/fence, acquires the original lock inode
exclusively and rechecks state under canonical database locks. Preserve an existing
committed event without moving the pointer; otherwise record safely stopped
`publication_failed`, retaining evidence, approval and admission. No PID check,
lease expiry or manual database edit substitutes for stop proof. Unknown ownership
or commit state keeps the blocker. The CLI cannot retry, approve, discard or fetch data.
The [operator interface](sdd/publication/design.md#operator-interface--required-executable-delivery)
and real subprocess/database tests are required delivery, not future documentation.

A current Admin separately invokes the existing publication-retry command after a
recoverable failure. Preserve candidate, evidence and original bound approval;
resolve the old warning, advance publication generation/fence, rearm the same outbox
and store the receipt atomically. Reverify all exact bytes in the new attempt.
Duplicate delivery cannot repeat that invocation. Recorded integrity/coverage/contract
violations and unknown error causes cannot enable retry. Discard remains the
permanent abandonment path; it preserves history and releases admission safely.

**History and precedence:** D1 is accepted: for Publication's first delivery,
manual reconciliation replaces automatic publishing crash recovery and repair of
lost delivered publication jobs previously required by A9/A15's schema/backend
contracts. Pending/unacknowledged enqueue retains bounded transport recovery;
Refresh preparation/registration recovery under A23 is unchanged. Multi-host
failover and unattended publication recovery are deferred. D2's proposed removal
of same-candidate retry is withdrawn; A16/A19 retry remains required. This decision
supersedes P2's additional execution/operation records, 600-second generation budget,
three verifier starts, renewing 30-second lease/5-second heartbeat and publication
child supervision. P2 and the original proposal remain historical. A6/A7 queue/outbox,
A9 publication invariants, A16 API commands, A19 query isolation and A20 permissions
remain in force. Run again/warning deletion and setup/scheduling remain separately
tracked work; do not claim the entire A16 recovery surface is delivered.

**Reason and rejected alternatives:** discard plus EIA re-extraction wastes valid
candidates after temporary failures. A runbook without a tested executable does not
provide usable recovery. Automatic crash continuation and multi-host ownership add
unneeded first-delivery machinery. Retaining locks/fences and conservative blockers
keeps correctness while accepting operator intervention after crashes.

**Verification and authority:** [bounded tasks](sdd/publication/tasks.md) implement
PUB-R01–R09 and require PUB-E01–E10, including production publication transactions,
real CLI/process/Redis/PostgreSQL tests, retry/integrity races and actual query-container
reader acceptance. The original planning record claimed no runtime results; the
acceptance session below records subsequent implementation evidence.
Live EIA/S3, retained migrations, live activation and retained-account checks remain
separate deployment gates. The original scope approval did not authorize code.
Alayala subsequently authorized all six tasks, code and disposable local migrations/tests,
without intermediate approval stops; commits, pushes, a PR and retained/live changes
remain unauthorized. Current implementation and actual checks are recorded in the
[acceptance session](ai/sessions/2026-10-04-publication-implementation-acceptance.md).

## Finalized specifications

### A20 — Seeded local authentication for the challenge: closed

**Operator password rotation refinement — October 5, 2026:** alayala approved an explicit, terminal-only `python -m trinity.auth.rotate <persona>...` command after he lost the retained persona passwords. It updates only `local_users.password_hash` for named, existing, active personas whose role matches the name, in one transaction under the seed advisory lock, with hidden double entry (15–1024 characters). It does not revoke sessions, reset login limits, change IDs, roles or status, or touch settings, runs or publication state; an unexpired session stays valid until it expires. Seeding still never changes an existing persona, and no recovery endpoint is added. Evidence: [rotation session](ai/sessions/2026-10-05-retained-persona-password-rotation.md).

Category: **Technical / code**.

Status: accepted by alayala on October 3, 2026. The original record was documentation only. The October 4 [implementation slice](ai/sessions/2026-10-04-fastapi-local-auth-implementation.md) now implements local credentials, sessions, seeding, `/me` and settings reads; A21 records defaults and remaining verification limits.

**Choice:** Roll back A8's Clerk selection for the challenge. Use local seeded Viewer, Analyst and Admin accounts with credential verification and server-issued sessions. Preserve A19's server-side roles, permission checks before protected reads, current session/role checks, denied unknown roles, and server-derived actor attribution. No Clerk account, key or network call is required for challenge authentication. Clerk is future production work, not a second challenge mode or automatic fallback.

**Reason and evidence:** The supplied challenge brief permits simplified authentication and requires one seeded test user per persona (page 5), README-based local execution and test-user instructions (pages 3 and 7). Local authentication removes provider setup from that path. Missing Clerk configuration is a delivery risk; the brief does not establish that any external provider automatically fails the Gate.

**Flow and failure example:** Local setup seeds the three accounts. Login verifies the submitted credentials and issues a session. Each protected request resolves the active account and current role from trusted local state before authorization. A Viewer changing a request body's role to admin still cannot refresh or read detailed datasets. Invalid, expired or revoked sessions grant no access; unavailable authentication storage fails closed.

**Contract completion:** Keep bearer transport, backed by opaque revocable sessions and local PostgreSQL account/session records. Add login/logout to A16/OpenAPI. These HTTP/model details are AI-authored documentation completion for the selected local-authentication direction, not observed runtime behavior. Exact password-hash library/parameters, session lifetime, frontend token handling, login throttling and runnable seed commands remain implementation work.

**Rejected alternative and tradeoff:** Requiring evaluator Clerk provisioning adds setup and availability dependencies. Maintaining both local and Clerk implementations adds code and tests before submission. Local login makes Trinity responsible for password hashes, session expiry/revocation and login abuse controls; simplified authentication must not bypass authorization.

**History and scope:** Supersedes A8 and Clerk-specific parts of A10/A11/A15/A17/A19. Amend A9's actor/storage model and A16's authentication transport description while preserving product roles and existing protected operations. Remove the Clerk SDK from challenge dependencies; other dependency pins remain selected. The proposed query/worker simplification was discarded: per-query containers, BullMQ, Redis and job_outbox remain unchanged. Preserve earlier decision and session history.

**Future production work:** Evaluate Clerk integration behind `auth/service.py`, including identity mapping for retained local actor history, user provisioning, session/role freshness and equivalent permission tests. This requires a separate production decision and is not required for challenge delivery.

**Validation required:** Fresh-clone setup without Clerk configuration; repeatable seeding of all personas; valid/invalid login; expired/revoked session rejection; current role/account changes; no client-controlled identity/role; direct API permission denials before reads; login throttling and sanitized failures. No runtime checks have run.

Source and contributions: alayala explicitly requested this rollback and documentation update. [Supporting session](ai/sessions/2026-10-03-seeded-local-authentication.md). See [security contract](docs/security-contract.md) and [API contract](docs/api-contract.md) for the current design.

### A9 — Data contract v1: finalized

**Publication refinement — October 4, 2026:** [A24](#a24--build-publication-first-delivery) governs the approved first-delivery operating and recovery scope. Earlier conflicting recovery expectations are historical for Publication; other guarantees remain in force.

Category: **Technical / code** and **Product / business**.

Status: finalized by AI on October 2, 2026, under alayala's instruction, “finalize the data contract.” This delegates the specification work; it is not a claim that alayala independently chose or verified every new default. No application implementation or runtime test is included. A1–A8 remain accepted.

**Choice:** Use [data contract v1 and its schema diagrams](docs/schema.md) as the canonical analytical and application-state specification. It defines daily natural keys, source IDs as text, exact decimal storage, null behavior, same-day percentage calculations, validation gates, immutable manifests, the original ten application models, and publication ordering. A16 amends the application lifecycle and adds admission, failure-warning and command-receipt records; analytical schema rules remain unchanged.

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

**History and precedence:** A16 later supersedes selectable publication modes and recovery exclusions; read the amended schema lifecycle for current rules. The October 2 Clerk/model session remains an unchanged historical proposal. This specification replaces its proposed fields where they differ. Earlier “open” implementation lists in A2–A8 describe their original decision scope; A9 closes the logical fields, validation, policy snapshots, recovery obligations, and publication invariants covered by the contract. Finite worker/request limits, DDL, supported SQL, parser/table authorization, role-token details, and a product stale-age threshold remain separate implementation decisions. A9 does not close all Arkham decision topics.

**Verification required:** Implement and execute the contract's acceptance scenarios, including exact decimals, all required checks in one attempt, missing data, Redis loss, worker fencing, approval ordering, and readers that overlap publication. Restore self-contained reproduction inputs and scripts. Historical evidence was not rerun and no permission boundary was runtime-tested in this task.

Supporting record: [data-contract session](ai/sessions/2026-10-02-data-contract-v1.md).

### A21 — Local-auth implementation settings

Category: **Technical / code**.

Status: implemented October 4, 2026 under alayala's request to complete, commit and push the local-login slice. Exact defaults are AI-authored implementation completion; no separate human review of each default or evaluator walkthrough is claimed. A20 remains the authentication direction; A19/A16 permissions and workflow are unchanged.

**Choice and reason:** Use Python scrypt (N=131072, r=8, p=1, 16-byte random salt, 64-byte output, 256 MiB maxmem) without a new password dependency. Verify credentials in disposable spawned processes, at most two per API process, with a 15-second overall authentication budget and termination/reaping before releasing capacity. Tokens use 32 random bytes, SHA-256 digests and an absolute eight-hour lifetime. Roles and session status are read on each request.

Use native PostgreSQL 17.11 for verified local acceptance and `postgres:17.11-bookworm` for the supplied database-only Compose configuration. Use synchronous Psycopg work in FastAPI's thread workers, a lazy pool of zero to four connections per API process, five-second connection/acquisition/statement/lock/transaction bounds within the operation budget, and repeatable-read app-entry snapshots. Child termination has a one-second grace before kill; measured normal verification was 0.54 seconds, not a general performance guarantee.

Login throttling is atomic in PostgreSQL, with 60-second windows of five attempts per username, 30 per direct peer and 60 globally. Ignore forwarded peer headers. Counters store digested keys and expire through bounded cleanup. The complete slice runs one API process locally; shared-counter tests also use multiple processes. This login counter does not replace future A19 analytical admission/rate accounting.

**Alternative and tradeoff:** A new Argon2id dependency remains an alternative if measured scrypt behavior is unsuitable; no silent downgrade is allowed. JWT role snapshots and process-only login counters would lose immediate current-role/revocation checks or shared limits. Scrypt consumes roughly 128 MiB per active verification plus process overhead; two simultaneous checks bound that per-process cost. Fixed windows allow boundary bursts. Browser storage, public ingress and authentication recovery flows remain outside this slice.

**Flow and failure case:** login reserves a shared attempt → verifies full-cost credentials → locks and rechecks the user → commits a session digest → returns a token. A deferred database constraint that fails at commit yields `503 auth_unavailable` with no returned token and no committed session. `/me` joins the active publication in the identity transaction; a missing singleton or failed read returns 503 instead of a false waiting state.

**Evidence:** [implementation session](ai/sessions/2026-10-04-fastapi-local-auth-implementation.md), [design](sdd/fastapi-local-auth/design.md), [backend setup](backend/README.md#local-api-and-three-personas). Native PostgreSQL/HTTP and offline tests passed. Docker/Compose startup, a new locked install and evaluator-owned execution remain unverified. Full analytical and refresh routes are separate slices. Reference: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [Python hashlib](https://docs.python.org/3/library/hashlib.html#hashlib.scrypt), [official PostgreSQL image](https://hub.docker.com/_/postgres).

### A22 — Refresh evidence writer and Preview compatibility

Category: **Technical / code**.

Status: initial persistence/registration implementation under alayala's instruction
to correct the Preview compatibility findings and start implementation. This does
not claim completion of Build Refresh or a live publication.

**Choice:** extend merged baseline `aea1eda`, preserving the linear chain through
`0004_preview_evidence`. Add `0005_refresh_evidence` and `0006_refresh_dispatch`.
Reuse `data_versions.evidence_bundle_sha256` and `validation_attempt_id`; bind the
latter to the selected same-run validation step's `validation_attempt_id`.
Retain receipt/summary hashes, analytical artifacts and all check/diagnostic rows.
New verified receipt-bearing records have frozen evidence and deferred selected-step
checks. Legacy Preview rows remain unchanged; migration never fabricates receipts.

**Reason and rejected alternative:** a parallel bundle field leaves Preview's required
column empty, and another 0003 migration creates two heads. Both were flaws in the
original draft. The corrected writer uses the existing reader's identities and
the actual completed migration head. Full legacy hardening and approval/publication
constraints remain later work; do not present this as a new guarantee for old rows.

**Flow and failure:** trusted retained receipt hash → saved/remote evidence verification
outside SQL → fenced ownership check → one transaction for artifacts, results,
Preview identities and review/publication intent. A wrong attempt or commit failure
leaves the candidate unvalidated and the active publication unchanged. Zero warnings
creates publication intent; warnings retain review state. Neither path publishes.

**Evidence and limits:** [implementation record](ai/sessions/2026-10-04-refresh-evidence-implementation.md)
records loader, real PostgreSQL upgrade/rollback and actual Preview-service provenance
checks with a synthetic publication effect. Admission routes, dispatcher, worker,
failed/partial import and publisher remain pending. Worker settings in the SDD remain
proposals until implemented and verified. No new dependency or live EIA/S3 run occurred.

### A23 — Durable refresh dispatch and one fenced preparation execution

Category: **Technical / code**.

**October 7, 2026 EIA timeout amendment:** Alayala explicitly selected 90 seconds
per HTTP attempt within a shared 150-second page budget after retained refresh
failures showed the former 30-second page budget expiring during slow requests
and retries. Each attempt now has a total timer in addition to HTTPX I/O limits;
connection setup remains capped at 10 seconds. Preserve at most three attempts,
one/three-second retry waits, and the existing discovery, route, preparation and
worker deadlines. Parent deadlines can stop attempts earlier; three full
90-second attempts are not promised. This replaces the connector's former
30-second I/O/page settings, not analytical-query or publication limits.
Local implementation and synthetic checks do not establish EC2 deployment or
live EIA completion. See the [implementation record](ai/sessions/2026-10-07-eia-attempt-page-timeout-budgets.md).

Status: implemented under alayala's explicit task 3–4 authorization, with task 2
acceptance closure. Synthetic/disposable verification is recorded in the
[dispatch and worker session](ai/sessions/2026-10-04-refresh-dispatch-and-worker.md).
This is not live full-history acceptance or publication completion.

**Choice:** reuse pinned BullMQ 3.3.0 and Redis. PostgreSQL owns claims and counts.
Use colon-free run/generation queue IDs; three total durable dispatch attempts,
ten seconds per enqueue, one/three-second retry waits and sixty-second crash leases.
Recovery repairs only unclaimed transport and never resets the attempt count.
Once claimed, a run gets one pipeline execution, one frozen discovery end and one
reserved version. Preserve the proposed worker limits: 1,530 seconds total,
sixty-second discovery, 1,440-second preparation with existing stage limits,
thirty-second worker lease and five-second heartbeat. SQL prevents budget resets.
These are initial engineering bounds, not a full-history throughput guarantee.

**Ownership and failure:** parent and child hold shared lifetime locks on the same
trusted local inode. Recovery requires exclusive ownership on the recorded host;
an expired lease or reused PID alone proves nothing. The live supervisor stops,
kills when needed, and confirms child exit on lease loss. Unknown ownership keeps
the slot blocked. Persist each external attempt before allowing it, bind the actual
validation UUID before checking, and import only complete measured journal results.
An incomplete pipeline becomes failed/rejected with one unresolved warning, never
ready. No automatic extraction restart or second candidate is permitted.

**Boundary:** completed preparation retains original receipt custody for task 5.
The initial task 4 boundary retained `receipt_pending` without readiness. Task 5
supersedes that intermediate state: normal worker and proven stopped-worker
recovery call the existing verifier/registration service. Migration 0007 persists
the 30-second registration deadline and caps registration invocations at three;
recovery preserves the original budget and takes a new fence. Changed/missing
evidence or exhausted limits record failure, never publication readiness.
Publisher, setup writes and Admin review/recovery commands remain separate.
The [current tasks](sdd/refresh-publication/tasks.md) state the tested boundary.

**October 5, 2026 amendment:** Alayala raised the registration budget from 30 to
150 seconds (`REGISTRATION_SECONDS` in `refresh/registration.py`). Live run #7
stored and read back 49/49 objects, then failed registration at its 30-second
deadline. A separate read-only readback of the same objects took 14.2 seconds at
best, with five requests over one second. The budget is still saved once per run,
still capped by the execution deadline, and still limited to three invocations.
Tradeoff: a stuck registration can hold the refresh slot up to 150 seconds.

### A25 — Figma design and brand handoff

Category: **Product / business**.

Status: selected by alayala on October 4, 2026 through his supplied mockups, brand reference and request to record the workflow. This is design direction and attribution, not frontend implementation approval.

**Choice:** Use alayala's self-created Figma interface mockups as the layout and flow reference. Use the earlier Trinity brand created with ChatGPT as the visual identity reference. Alayala plans to pass both to Claude to apply the brand. Credit each contribution separately in Engineering Notes, handoffs and subsequent implementation records.

**Reason and alternatives:** Preserve the human interface design and make the use of AI visible to the evaluator. Do not describe the entire design as AI-generated or the brand as entirely handmade. No competing brand or frontend framework was selected in this request.

**Boundary and precedence:** A9/A16/A19/A20 and the current API, data and security contracts govern behavior. The references do not change roles, field names, missing-value handling, SQL scope or publication gates. Reconcile any mismatch before implementation. Final styling and frontend technology remain open; mock values and visible states do not prove runtime behavior. Later refinement: [A26](#a26--frontend-stack) selects the frontend technology on October 4, 2026; final styling remains open.

**Evidence and validation:** [Engineering Notes](NOTES.md#figma-mockups-brand-and-claude-handoff--october-4-2026) and the [reference inventory](ai/sessions/2026-10-04-figma-brand-handoff.md) separate alayala's authorship statement from the supplied screenshots. The native Figma file and earlier ChatGPT conversation were not inspected. Claude's adaptation, asset exports and frontend behavior remain unverified.

**Explorer handoff package — authorship pending, October 5, 2026:** alayala supplied a second package, `design_handoff_trinity_explorer/` (`Trinity.dc.html`, its README, 18 screenshots and 4 logo images), now copied to [docs/design-reference/2026-10-04-explorer-handoff/](docs/design-reference/2026-10-04-explorer-handoff/PROVENANCE.md) without `support.js`. The author of `Trinity.dc.html` and its README is **pending confirmation**. Do not attribute these files to a person or tool without evidence. Alayala reported that design images and design prompts were generated in a Codex chat; that chat was not inspected.

### A26 — Frontend stack

Category: **Technical / code**.

Status: selected by alayala on October 4, 2026, when he answered proposal Q1 ("yes, go with React + TypeScript + Vite") and requested the frontend specification. This is a technology choice, not implementation approval.

**Choice:** Build the web frontend in `frontend/` with React, TypeScript and Vite. On October 5, 2026 alayala confirmed that this approval covers only those three technologies. Every other package, including those the proposal recommends (React Router, TanStack Query, test and lint tools), is listed for separate approval in the [specification](sdd/frontend/spec.md#dependencies-pending-approval). The development server proxies `/api` to the local API, so local work needs no CORS change.

**Reason and alternatives:** The design handoff assumes a React (Vite) codebase, and its prototype is written as React components. No competing framework was proposed.

**Boundary:** A17 governs exact versions and the lockfile. A9/A16/A19/A20 and the current contracts govern data, roles and errors (A25). Spec D01 (accepted October 5): the browser keeps the session token in `sessionStorage`, sends it only in `Authorization: Bearer`, never in a URL, and clears it on sign-out, `401` and expiry. Alayala first answered "memory only" and then corrected it to `sessionStorage`. D02–D04 are accepted in the specification.

**Evidence:** [frontend proposal](sdd/frontend/proposal.md) and [session record](ai/sessions/2026-10-04-frontend-plan-and-spec.md). No frontend code exists or has been tested.

### A27 - Compressed refresh evidence

Category: **Technical / code**.

Status: alayala requested implementation on October 6, 2026 after the measured
compression recommendation. Exact encoding and bundle fields below are AI-selected
implementation details, not separately observed human verification.

**Choice:** compress eligible new JSON/JSONL evidence using deterministic gzip
level 1 when it reduces bytes. New storage bundles use format 2 and bind both
original and stored hashes/sizes. Keep format 1 readable without rewriting it.
Parquet and bootstrap objects remain unchanged. Use the Python standard library;
no dependency, analytical schema, HTTP contract or database migration is added.
The exact [storage format](docs/schema.md#compressed-evidence-storage) is canonical.

**Reason and tradeoff:** run #12 exceeded the 300-second storage budget. Applying
the implemented codec to its 48 planned artifacts reduced 103,338,932 bytes to
4,304,973 bytes (95.83%), with exact original-byte recovery. This is a local
measurement, not an end-to-end latency guarantee or proof of the earlier network
delay. Retain all evidence instead of deleting detail; retain readback checks
instead of trusting upload acknowledgments. Increasing a timeout is not a speedup.

**Boundary:** keep conditional writes, retries, deadlines, permissions and
publication gates. Upgrade all readers before allowing a new writer to produce
format 2. Old binaries cannot read the new format. Existing and failed candidates
are not recompressed in place. Per-request timing, incremental progress and
parallel transfers are outside this compression-only change. Live deployment and
a new refresh are separate operator actions.

**Evidence:** [implementation and verification](ai/sessions/2026-10-06-refresh-evidence-compression.md).

## Proposed decisions

### P1 — Refresh integration and Build Refresh: implementation authorized

[ME] Alayala requested a new branch, an integration contract, and the Build Refresh
SDD before implementation, then authorized implementation after the Preview corrections.
[YOU] AI traced current preparation outputs and
0001/0002 migrations, and proposed explicit receipt/attempt bindings, missing
artifact/result/outbox/command persistence, bounded worker ownership/deadlines and
conservative recovery of a completed receipt. See the [contract](sdd/refresh-publication/integration-contract.md)
and [SDD design](sdd/refresh-publication/design.md) for exact fields, proposed values,
tradeoffs and acceptance cases. A22 records the implemented boundary; other details
remain proposals without changing A9/A16. Setup writes, publication execution, review/recovery
commands and daily scheduling remain separate dependencies. A24 later accepts the
Publication first-delivery design and task preparation; other unaccepted details
remain proposals. This historical entry claims no runtime verification.

A16 accepts the API flow and A19 accepts the security design. Remaining implementation details are listed in [the security contract](docs/security-contract.md#remaining-implementation-details); A21 now records the implemented local API pooling/synchronous execution defaults; other remaining details stay in [backend architecture](docs/backend.md#proposed-database-execution-model). This heading is retained for historical links.

### P2 — Build Publication specification and design: proposed

**Historical proposal — superseded October 4, 2026 by [A24](#a24--build-publication-first-delivery).**
The original proposal below is preserved, including its former authorization gate
and migration snapshot. Its settings are not current requirements. The later
reduction D1 is accepted; D2 is withdrawn; O1 and executable operator recovery plus
Admin same-candidate retry govern the first delivery. Tasks are now requested; code
and Git delivery remain unauthorized.

Category: **Technical / code**.

[ME] Alayala supplied the Publication proposal and explicitly requested both
specification and design, reserving tasks for his subsequent review. This authorizes
documents only. [YOU] Drafted the [specification](sdd/publication/spec.md) and
[design](sdd/publication/design.md) from A9/A16/A19/A20/A22/A23 and current source.
The user-supplied [proposal](sdd/publication/proposal.md) is preserved as the scope
baseline; its earlier specification-only gate is superseded by this direct request.

**Proposed choices:** separate per-generation publication execution and operation
history; 600-second generation budget from first publisher initialization,
300-second maximum verifier pass, at most three verifier starts, 30-second lease,
5-second heartbeat and confirmed terminate/kill waits of 5 seconds each. Preserve
A19's three total temporary external attempts with 1/3-second waits through durable
operation permits. Use a separate publication queue with the existing BullMQ pin,
the producer's schema-1 payload and distinct publication/dispatch generations.
Map logical `publish:<version_id>` to the existing UUID event key using UUIDv5
with `NAMESPACE_URL` and `urn:trinity:publish:<canonical version UUID>`.

**Reason and alternatives:** preparation deadlines/custody and the selected
validation step are immutable after registration. Reusing them would lose evidence
or reset budgets. Nested SDK/job retries could exceed accepted limits. A new random
effect key per delivery would weaken replay identity. These bounds are engineering
proposals, not measured full-history capacity or accepted settings.

**Boundary:** append justified DDL after the actual Task 5 head (currently the
uncommitted `0007_refresh_registration`), without editing its migration. Reuse
verification with safe typed failure causes; generic dependency errors cannot
establish retry eligibility. Existing A9/A16 publication/recovery rules remain
unchanged. The [Task 5 handoff](ai/sessions/2026-10-04-refresh-task5-receipt-routing.md)
now records synthetic/disposable acceptance; it was not rerun for this SDD.
No tasks, implementation, migration execution or publication activation is authorized.

### A28 — EC2 web deployment

Category: **Technical / code**.

Status: alayala selected one AWS EC2 server for the first deployment and requested
implementation of frontend/backend hosting with a choice of Nginx or Caddy.
Codex selected Caddy under that request. No domain is currently available.

**Choice:** Deploy both frontend and backend on the same EC2 Docker host. Use
Caddy 2.11.7 to serve the compiled React/Vite bundle and proxy unchanged
`/api/v1/...` requests to FastAPI. Keep PostgreSQL, Redis and query containers
private. Preserve the existing workers, S3 custody and query supervisor. Node
24.21.0 runs only during the locked frontend build. This hosting choice supersedes
the earlier undecided-hosting statements in A14/A19; their security/data rules
and A24's recovery boundary remain in force.

**Reason and alternative:** Caddy combines static serving, reverse proxying and
automatic domain certificate renewal. Nginx with separate certificate automation
would add operating steps for this single-server demo. No npm/Python dependency
or authentication change is selected. The pinned Caddy image is a new deployment
dependency; its routing and constrained-container checks are recorded separately.

**Initial operating boundary:** Until a public TLS route is configured, bind the
web ports to loopback and use an SSH tunnel. Do not expose plaintext preview
HTTP publicly. Full unattended AWS credentials, backups/restore, Redis persistence,
retained migrations/accounts, query/worker activation and public TLS acceptance
were separate gates. Later amendments below record completed startup and public
TLS checks; backups/restore and full data acceptance remain unverified.

**Approved host-runtime refinement:** After reviewing the OS, package sources,
preservation plan and exact commands, alayala explicitly approved Docker 29.8.2
as a side-by-side static daemon on the existing Amazon Linux host. The native
repository offered no compatible Engine; no Fedora/CentOS repository was added.
The installed Amazon packages and configuration remain intact. The new systemd
override retains external containerd/runc and the original classic `overlay2`
store. Manual security updates are the accepted operating tradeoff. Live Server
API 1.56 and the supervisor constructor check passed. At this gate, deployment
remained stopped; the later staged-rollout approval below superseded that stop.
See the implementation session for proof.

**Approved EC2 identity refinement — October 6, 2026:** Alayala approved using
the attached `trinity-ec2-runtime` role directly. Both named AWS profiles contain
only the region and resolve temporary credentials from instance metadata.
Reject the extra writer-role assumption for this single-host deployment: the
attached role already has candidate-prefix GetObject/PutObject permission.
Both profiles have the same IAM authority, including the trusted query
supervisor; profile names do not provide read/write isolation. This is an
explicit single-host credential-delivery tradeoff to A19's permission-separation
design. The application still restricts published-object selection, and isolated
query executors retain no network or credentials. No static AWS key is stored.
Bounded host/container S3 verification is approved. Exact evidence and remaining
limits are in the runtime audit.

**Approved staged rollout — October 7, 2026:** Alayala authorized the backend
image build and EC2 verification, followed by PostgreSQL/Redis, migrations and
account seeding, then API/Caddy. Verify each stage before enabling workers.
Alayala explicitly selected PostgreSQL 17.11 for this deployment, retaining the
tested A21 Compose configuration instead of A17's 18.6 selection for this host.
This does not authorize an upgrade of an existing database.

**Approved queue persistence — October 7, 2026:** Alayala approved Redis AOF
with `appendfsync everysec` on the retained Redis volume, preserving noeviction
and the existing snapshot defaults. He approved manual worker restarts so
recovery retains its stopped-worker checks. This EC2 overlay resolves the
configuration choice for this host; automatic recovery, backups/restore and
end-to-end data acceptance remain unverified. Every-second sync can lose about
one second of writes after a host failure; it does not guarantee lossless queue
delivery. See [Redis persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/).

**Approved public access — October 7, 2026:** Alayala requested access without
SSH. With no domain available, Codex configured the current EC2 IPv4 address
with Let's Encrypt's `shortlived` ACME profile in the existing Caddy 2.11.7 image.
Use public TCP80 for HTTPS redirects/challenges and TCP443 for TLS, preserving a
separate loopback8080 SSH preview. API, database and Redis ports stay unpublished.
The fifth Compose layer mounts the reviewed non-secret Caddy config read-only;
no frontend rebuild or credential rotation is needed. Caddy retains certificate
state in its existing volume and manages renewal. Initial trusted issuance and
public HTTP/auth checks passed; a future renewal has not yet been observed.
The current address is not an Elastic IP and can change after EC2 stop/start;
revalidate the address/configuration before exposing a replacement address.
See [Let's Encrypt IP certificates](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability)
and [Caddy ACME profiles](https://caddyserver.com/docs/caddyfile/directives/tls).

See [deployment instructions](docs/deployment.md) and
[implementation evidence](ai/sessions/2026-10-06-ec2-caddy-web.md). Sources:
[Caddy SPA/API routing](https://caddyserver.com/docs/caddyfile/patterns),
[automatic HTTPS](https://caddyserver.com/docs/automatic-https).

## Arkham decision topics still to complete

The brief requires a choice, a rejected alternative, and a reason for each topic. This table tracks coverage; it does not close missing choices.

| Required topic | Current status |
|---|---|
| Natural keys for national, facility, and generator data | Specified by A9: `period`; `(period, facility)`; `(period, facility, generator)`. Implementation and new extraction checks remain pending. |
| Meaning of kept current and how refresh achieves it | A2–A3 plus A9 specify schedule, supported history, full-window revision capture, and separate source/publication times. A product stale-age threshold remains open. |
| Missing facilities and generator/facility disagreement | A9 specifies “not reported” for absent observations, exact cross-grain checks, blocked publication on required failure, and retained evidence. Common source omissions remain a limit. |
| Synchronous or asynchronous refresh | Accepted in A6: the full pipeline runs in background workers with bounded concurrency. A7 defines reliable dispatch. Detailed execution mechanics and verification remain open. |
| Supported and rejected SQL | A18 accepts required v1 single-table SELECT, filters, sorting, grouping, and approved aggregates; joins, CTEs, and subqueries are optional after the core works and its tests pass. A19 selects arithmetic, CASE and function names; exact parser/type compatibility and implementation remain pending. |
| Finding every referenced table before permission checks | A19 requires whole-input SQLGlot validation in one module and authorization of every physical table before download/execution. Nested constructs are rejected in v1. Implementation and compatibility tests remain pending. |
| At least one additional decision shaping the solution | A3 and A4 record additional choices. Implementation and verification remain pending. |

Source: `Software Engineer - Technical Challenge.pdf`, pages 6–7. See [FINDINGS.md](FINDINGS.md) for data evidence and [NOTES.md](NOTES.md) for AI use.
