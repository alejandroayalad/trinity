# Trinity security contract

Status: agreed design, October 3, 2026, under [A20](../DECISIONS.md#a20--seeded-local-authentication-for-the-challenge-closed) for local authentication and [A19](../DECISIONS.md#a19--security-contract-and-local-execution-closed). No implementation, dependency installation, container launch, or security test is claimed. Analytical capacity limits are provisional. [API contract](api-contract.md) owns endpoints and wire behavior; [schema](schema.md) owns data and state invariants. A16, A17 and A18 remain in force with the explicit refinements below.

## Roles and authorization

| Role | Access |
|---|---|
| Viewer | National dashboard/data only; no SQL or facility/generator detail through any product path. |
| Analyst | All analytical datasets, previews, filters and permitted read-only SQL. |
| Admin | Analyst access plus setup, shared settings, refresh, candidate review, approval, publication recovery and discard. |

Authorize before protected data reads, file downloads or query execution. Apply the same policy to direct API calls, catalogs, previews, dashboards, metadata, diagnostics and errors. Frontend controls never replace backend checks. A rendered action button and a stored command receipt are not authority; check current identity before protected lookup or replay.

## Authentication and trusted roles

Implementation update, October 4: [A21](../DECISIONS.md#a21--local-auth-implementation-settings) selects and records the tested local hash/session/throttle/database settings. [The implementation session](../ai/sessions/2026-10-04-fastapi-local-auth-implementation.md) distinguishes native PostgreSQL/HTTP evidence from still-unverified Compose, frontend and later feature routes. Earlier pending-detail statements below retain their original contract context; A21 closes only the listed local-auth defaults.

A20 replaces Clerk with seeded local authentication for the challenge. Use accounts named `viewer`, `analyst`, and `admin`, one per persona. `auth/service.py` verifies credentials and issues opaque, unpredictable bearer session tokens. Store salted password hashes and session-token digests, never plaintext passwords or reusable tokens. The evaluator supplies seed passwords locally; no real credentials belong in Git, examples or logs. Exact hash library/parameters remain implementation details.

Keep accounts and sessions in PostgreSQL as application state, unavailable to user SQL. Read the active account, unexpired/unrevoked session and current role on every authenticated product request, including polling. Do not cache session-status or role authority in v1. Roles are `viewer`, `analyst` and `admin`, assigned only by trusted seed/administrative code. Clients cannot supply authoritative roles or actor IDs. Derive action actors from the verified local identity; workers retain internal service authority.

Use the API's bearer-session transport. Login accepts credentials only and returns a new server-issued session; logout revokes that session. Invalid credentials receive a generic denial without identifying whether an account exists. Invalid/inactive/expired/revoked sessions are denied; missing/unknown roles grant no product access. If authentication storage is unavailable, return `503 auth_unavailable` and perform no protected action. Account deactivation and role changes apply to subsequent requests; already-authorized accepted work may finish.

Seeding is repeatable: create missing personas without silently resetting existing passwords, roles or identities. Keep stable local actor IDs and retained action history. No registration, password recovery, role-selection login or public role-management endpoint is added. Exact session lifetime, password-verification library, browser token handling and login throttling settings must be selected and tested during implementation. Never return password hashes or token digests through product APIs.

Clerk is future production work behind `auth/service.py`, requiring explicit provider configuration, identity mapping and equivalent permission verification. It is not installed or contacted for challenge login, and no automatic provider fallback may bypass failed authentication.

Design references: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) and [session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html). These support implementation controls, not a claim that Trinity already enforces them.

## SQL policy

Required v1: exactly one read-only `SELECT` over one permitted physical analytical table. Support filtering, sorting, grouping, arithmetic, `CASE`, and only these selected functions:

| Kind | Allowed functions |
|---|---|
| Aggregate | `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` |
| Calculation/null handling | `ROUND`, `COALESCE`, `NULLIF` |

Reject multiple statements, writes, schema changes, JOINs, CTEs, subqueries, external file readers, URLs, custom functions, and any construct outside the implemented allowlist. `ABS` from the older proposal is not selected. Application-state tables and unpublished candidates are unavailable. The three analytical names remain `national_outages`, `facility_outages`, and `generator_outages`, subject to role permissions; Viewer cannot use SQL even against the national table.

Use SQLGlot to inspect the entire input and every physical table reference before protected files are downloaded or registered. Keep one policy implementation in `queries/runtime/sql_policy.py`; the trusted supervisor uses that same module for pre-download validation, not a second parser policy. The container receives only the operation covered by validation and its authorized local-file mapping. SQLGlot success is not DataFusion compatibility: verify allowed/rejected fixtures against both before enabling execution.

The function names and feature scope are selected; exact dialect, AST nodes, argument forms/types, comparison predicates and numeric/error semantics remain implementation details to verify. Do not silently enable an engine function because parsing succeeds. SQL `AVG` keeps its ordinary query meaning; it does not replace A9's capacity-weighted national metric. Preserve decimal values and the API's exact numeric serialization.

**October 4 SQL specification refinement:** [A19](../DECISIONS.md#a19--security-contract-and-local-execution-closed) now accepts D01’s exact grammar and D02’s rolling rate-accounting boundary in the [SQL specification](../sdd/single-table-sql/spec.md); A16 records D03 presentation. These supersede the open status of those details above. Viewer is denied before SQL parsing, analytical rate/slot accounting, downloads or execution, including national-table SQL; no SQL UI controls are exposed. The [design](../sdd/single-table-sql/design.md) specifies proposed parser, staging and runtime mechanics; none is runtime proof.

## Published data and S3 access

Pin one published version for the complete analytical request. Clients cannot choose storage paths, connections or credentials. Resolve only permitted entries of its immutable manifest. Preserve API pagination and publication-change restart rules; authorize every continuation request.

| Component | Authority |
|---|---|
| Browser | API access only; no direct S3 access. |
| Trusted file downloader | Read only authorized publication objects for the request, verify their recorded SHA-256 checksums, and stage those files for the query. No candidate creation or publication authority through this role. |
| Query container | Read authorized staged Parquet files through a read-only mount. No S3 access, credentials, network access or Docker control. |
| Refresh worker | Create and validate unpublished candidates; cannot overwrite published files or activate candidates. |
| Publication worker | Verify eligibility/approval and activate the exact candidate through application state; cannot change its data. |

S3 stays private. Separate reading, candidate creation and publication permissions. Publication is a PostgreSQL state transition, not a permission to rewrite objects. Every refresh creates a new version. Exact S3 policies, local S3 configuration/provider and trusted credential delivery remain to be implemented; no AWS hosting choice is implied.

## Query containers and supervision

Use a separate container for each analytical query, including preview/dashboard calculations that execute analytical reads. Keep the runtime in the same backend codebase. A trusted supervisor outside the query container owns downloads, launch, deadlines, stop confirmation and cleanup.

The analytical flow is:

1. Verify identity/role, authorize the operation, pin publication and validate SQL where applicable using the single policy module.
2. Reserve a shared query slot. Start the 30-second analytical deadline before downloading any data for the request.
3. Download only authorized published files, verify SHA-256 identities and prepare a request-specific read-only data mount.
4. Start a separate query container with the approved operation/local mapping, no network, no credentials and no Docker socket/control. Enforce the 1 GiB container limit and the remaining deadline.
5. Collect bounded output; confirm execution ended or stop it, remove temporary containers/staged resources, and release the reservation only when no execution remains.

Mount no unrelated datasets, unpublished files or host service resources. The trusted supervisor retains Docker control; it is never passed to untrusted query execution. File staging does not become a result cache or authorize future requests. Runtime imports must not initialize privileged API/worker integrations.

A timeout HTTP response alone does not prove execution stopped. The supervisor must stop execution and verify termination. Temporary resources are removed after use; published S3 objects and retained evidence are not deleted by query cleanup. Exact image, user/capability/security-profile settings, mount protection, message transport and local Docker behavior remain to be implemented and tested. Selecting a container is not proof of a complete sandbox.

## Shared query admission

Use PostgreSQL transactions to reserve query capacity across processes: at most two active analytical requests per user and four across the deployment. A request holds its reservation during staging, execution and stop confirmation. This query capacity is separate from A16's one-refresh-lifecycle admission rule.

Release a slot only after its query process has ended or been stopped. A launch failure may release it after confirming no query process exists. Do not free capacity merely because an HTTP request ended, a supervisor lease expired or a database connection was lost. Supervisor crash recovery must identify the associated container, confirm it ended or stop it, clean up temporary resources and conditionally release the recorded reservation. Unknown execution status continues to occupy capacity.

Do not start unreserved work when PostgreSQL admission is unavailable. Exact reservation tables, ownership tokens and crash reconciliation are implementation details; they must preserve this lifecycle. Releasing one request must not release another's slot. Rate accounting must also cover processes consistently. A19’s October 4 refinement selects the rolling 60-second window and counting boundary; its physical storage/locking implementation remains to be verified.

## Limits

### Provisional analytical capacity

| Limit | Initial value |
|---|---|
| SQL output | 1,000 rows |
| Encoded analytical response | 5 MiB (5,242,880 bytes) |
| Analytical execution | 30 seconds including trusted downloads, file reads and execution; retries share the deadline |
| Memory | 1 GiB (1,073,741,824 bytes) per query container |
| Active requests | Two per user; four across the deployment |

Apply relevant limits to SQL, previews, national dashboard/metric calculations and analytical filter choices. Keep endpoint-specific pagination. The SQL row cap limits output, not aggregate input rows. Return `truncated: true` only when another result row exists after the query's own limit. Time, memory or response-size failures return an error without partial successful results. Excess concurrency returns the API's existing `429 rate_limited` busy response.

These values need local cold-start, preview, dashboard and grouped-SQL measurements. Four query containers can use up to 4 GiB combined, plus supervisor/download buffers and other services. Keep values in server configuration, outside client control. Adjust deliberately after recording measurements.

### Accepted input and initial rate limits

| Control | Rule |
|---|---|
| JSON request body | Maximum 64 KiB (65,536 bytes). |
| SQL text | Maximum 16 KiB (16,384 encoded UTF-8 bytes), checked independently of JSON/character length. |
| Analytical request rate | Initially 30 requests per user per minute across processes. |
| Polling | Progress/status polling is excluded from that analytical counter; authentication/authorization still apply. |

A19 also accepts preview D02 in the [preview specification](../sdd/dataset-preview/spec.md): preview and SQL share one trusted-user rolling 60-second counter. An authorized preview request that passes primitive shape checks consumes one admitted attempt even if later filter/cursor/publication checks or execution fail. Malformed/unauthorized and rate-denied requests add no debit; each page counts separately and internal retries add none. Preserve the specification’s validation order and SQL’s existing counting boundary. Preview D03 requires fresh authorization for every cursor use; possession of a cursor grants no role or dataset access.

Preserve the API's `413 request_too_large` and `429 rate_limited` responses and retry guidance. Internal external-call retries do not become new client analytical requests.

## External failure retries

Allow up to **three total attempts**, not three retries, for temporary external failures. Wait one second before attempt two and three seconds before attempt three. All attempts and waits remain within the operation's deadline; do not begin another attempt when its deadline has expired. The analytical budget does not restart after a download failure.

Do not retry invalid SQL, denied access or failed validation. Invalid credentials/session/role are denials, not temporary provider outages. Do not blindly replay external writes: retries use the same durable operation/object identity and existing duplicate-safe rules. Recovery of an uncertain write first checks its recorded outcome. Queue redelivery is not permission to reset an exhausted attempt budget.

Authentication and refresh-stage deadlines, and concrete temporary-error classification, remain to be implemented. Do not apply the 30-second query deadline to the entire refresh. Exhausted/permanent refresh failures follow A16's failure-warning and Admin recovery rules. Explicit Admin Run again creates a new run; publication retry reuses the exact eligible candidate and its original approval requirement.

## File identity and publication

Keep A9's SHA-256 file checksums and deterministically ordered manifest digest. Validate the exact frozen files; bind approval to `manifest_sha256`, `validation_step_id` and `review_warning_digest`. Changed files require new validation and, when required, new approval. Under the existing schema, changing a validated candidate requires a new run/version, not mutation of approved bytes.

| Evidence | Publication authority |
|---|---|
| All required checks pass; no review warnings | Automatic publication. |
| All required checks pass; review warnings exist | Admin approval bound to the exact evidence. |
| Any required check fails or is incomplete | No publication; no Admin override. |

Incomplete diagnostics cannot be treated as zero warnings. Keep A5's known facility-total metadata issue informational after required checks pass. Review warnings and operational failure warnings remain different records.

The publication worker rechecks file identity, required evidence, approval when needed, active candidate disposition and current worker ownership before activation. Preserve the schema's atomic publication event/pointer/run transition and nonregressing coverage. No configurable publication mode remains. `publication_events.publication_mode` is only a derived historical outcome, not an editable setting.

A16's single refresh lifecycle remains reserved during preparation, review, publication and unresolved failures. Approval/discard cannot both succeed. Duplicate requests reuse recorded work; stale workers cannot change state or publish. Preserve settings/action revisions, durable command receipts, outbox dispatch, same-candidate publication retry and permanent discard. Queries keep using the previous publication until the new version is active.

## Exposure and deployment

Viewer catalogs, data, diagnostics and errors contain national information only. Public errors expose no hidden schemas, storage paths, credentials or internal traces. Logs record actor, action, outcome and request/run ID; exclude tokens, raw SQL and raw source payloads. Use `Cache-Control: no-store` for authenticated responses. Any future result cache needs separate permission and invalidation rules.

Prepare local execution with **Docker Compose first**. No Compose file or runnable command is supplied by this documentation change. AWS and public hosting remain undecided. The local challenge PDF was inspected: page 7 requires a locally running solution and source runnable from README; page 8 requests a repository link. No public application URL requirement was found in the supplied brief. This does not establish whether a separate submission message adds requirements.

Use HTTPS outside local development and only configured frontend origins. Enforce backend authorization regardless of origin. Keep secrets in environment/deployment configuration and commit placeholders only in `.env.example`. PostgreSQL, Redis and query containers have no public access. Apply the same role/data rules locally. Preserve A17's locked dependency versions and perform compatibility and known-security-issue checks before delivery; this contract does not reselect versions.

## Optional extensions

| Extension | Gate |
|---|---|
| JOINs, CTEs, subqueries | Core works and its tests pass; prove authorization finds all physical tables, including nested references, before enabling. |
| Trinity role-management screen | Only if time remains; Admin-only backend authorization and role-change audit trail. |
| Query-result cache | Separate authorization and invalidation rules; not part of required v1. |

## Verification required

| Test area | Required evidence |
|---|---|
| Identity and roles | Direct API calls for all personas; denied access before reads/downloads; invalid/inactive sessions and unknown roles denied; role changes apply; local auth-storage outages block protected actions; fresh-clone login needs no Clerk configuration; seed reruns preserve accounts; credentials and role/actor tampering are rejected. |
| SQL | Allowed arithmetic/CASE/function fixtures agree between SQLGlot and DataFusion; whole-input rejection of unsupported constructs, writes, hidden tables, file readers and URLs; exact decimal behavior. |
| Isolation and cleanup | Container cannot reach network, S3, credentials, Docker control, unrelated mounts or unpublished files; mounts reject writes; timeout stops execution; memory bound holds; temporary resources are removed. |
| Admission and limits | Cross-process user/global reservations; no slot release before termination; supervisor crash recovery; byte/row limits and truncation; 30/minute counter excludes polling; no partial results on resource failure. |
| Publication and recovery | Required failures/incompletion block; changed files invalidate approval; no double approval/publication or publication after discard; stale ownership rejected; settings revisions and failed-run recovery preserved. |

Also test the three-attempt external failure schedule within deadlines, denied/invalid/validation non-retries, Viewer-safe errors and sanitized logs. Measure cold downloads, previews, dashboard calculations and grouped SQL locally. Run main flows with all three test accounts before the live session. None of these tests has run for this design update.

## Remaining implementation details

1. Password-hash library/parameters, session lifetime, browser token handling, login throttling and seed commands; local account/session storage and current role checks are specified under A20.
2. SQL dialect/AST forms, argument/type/numeric semantics and parser/engine compatibility fixtures; function names are selected.
3. Container hardening, supervisor protocol/crash cleanup, S3 policies/local configuration and temporary-file handling; no-network read-only data access is selected.
4. Query-slot physical schema, rate-window accounting and authentication/refresh-stage deadlines/error classification; slot authority, limits and attempt schedule are selected.
5. Dependency compatibility and local capacity measurements; hosting remains undecided and no public application URL is required by the supplied brief.

Source: alayala's agreed security rules and explicit follow-up choices. Read-only challenge evidence and documentation checks: [contract split session](../ai/sessions/2026-10-03-security-contract-and-api-split.md). This specification is not security validation.
