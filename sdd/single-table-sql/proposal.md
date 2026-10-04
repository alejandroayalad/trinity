# Proposal: One-table read-only SQL

Date: 2026-10-04
Status: Proposal approved October 4, 2026. The [specification](spec.md) is approved and [design](design.md)/[tasks](tasks.md) are drafted; implementation has not started.
Inspected branch/base: `feat/catalog-permissions`, `fde733b`, with uncommitted catalog work preserved.
Basis: A4, A9, A13–A21 in [DECISIONS.md](../../DECISIONS.md).
Evidence: [proposal session](../../ai/sessions/2026-10-04-single-table-sql-proposal.md).

## Human

### Goal and flow

Let an Analyst or Admin submit one read-only query against one published outage table. SQLGlot checks the complete request before any analytical file download. DataFusion runs the approved query over only that table's authorized Parquet files in a separate query container.

Input: `POST /api/v1/queries` with the existing bearer session and only `{ "sql": "..." }`. Preview selections do not change the submitted SQL. Viewer has no SQL permission, including queries against national data. Under A16, Viewer also sees no SQL button, menu entry, editor or Run control. Direct SQL-screen navigation returns to the permitted waiting screen or national dashboard; direct API submissions are denied before SQL work. Frontend implementation/verification remains later work, while backend denial is required in this slice.

1. Verify the current session and role; require `sql:execute`. Pin one active publication and validate the entire SQL input through the shared policy module.
2. Authorize its single physical table, reserve shared query capacity, and start the analytical deadline before downloads.
3. Resolve only that table's files from the pinned publication, download them through trusted code, and verify their recorded SHA-256 identities.
4. Run DataFusion in a separate container with only those files mounted read-only, no network, credentials or Docker control.
5. Return bounded ordered columns and rows with publication metadata. Confirm execution ended, clean temporary resources, and release its slot only after termination is known.

Example request:

```sql
SELECT period, outage
FROM national_outages
ORDER BY period
LIMIT 10
```

Expected output: at most ten rows from one published version, with exact numeric values serialized as strings. This is an acceptance example, not evidence that the query runs today.

Failure example: an Analyst sends `SELECT * FROM local_users`. The table is application state, not an allowed analytical table. Reject it before downloads, file registration or execution, with a safe error that does not reveal the hidden schema. A Viewer sending even the valid example above is denied before SQL parsing.

### Scope

| Deliverable | Completion boundary |
|---|---|
| One-table SQL policy | Exactly one read-only `SELECT` over `national_outages`, `facility_outages`, or `generator_outages`, subject to current permissions. Support filtering, sorting, grouping, arithmetic, `CASE`, and the A19 function list. |
| Published-file execution | Pin a publication, validate before downloads, verify authorized file identities, and execute with DataFusion inside the A19 container boundary. No application tables or unpublished candidates are available. |
| Existing API response | Return ordered column metadata, row arrays, `returned_rows`, `truncated`, `execution_ms`, publication and permitted diagnostics, as specified in OpenAPI. Preserve duplicate column labels, nulls and exact numeric serialization. |
| Lifecycle and limits | Shared PostgreSQL admission and rate accounting, bounded staging/execution/output, safe errors, stop confirmation and crash recovery. These are required before enabling the endpoint. |
| Acceptance evidence | Separate parser/engine tests, real PostgreSQL/HTTP checks, real container isolation/lifecycle checks, and alayala's operator check. Synthetic publication fixtures do not prove live EIA/S3 readiness. |

Allowed functions: `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `ROUND`, `COALESCE`, `NULLIF`. `AVG` retains normal SQL meaning; it does not become the capacity-weighted national metric.

Reject multiple statements, writes, schema changes, JOINs, CTEs, subqueries, external readers, URLs, custom functions and every construct outside the implemented allowlist. A self-join remains a JOIN even if both references name the same table.

Outside this slice: preview/dashboard endpoints, frontend SQL editor, joins/CTEs/subqueries, query history, export, autocomplete, result caching, refresh/publication implementation and cloud configuration changes. Existing authentication and catalog behavior remain in place.

### Acceptance examples

| Scenario | Required result |
|---|---|
| Analyst/Admin submits an allowed query | Execute only its authorized table from the pinned publication. Allowed SQLGlot and DataFusion fixtures agree. |
| Viewer, invalid session, deactivated account or lost SQL role | Deny before parsing or analytical file access; current stored authority controls each request. |
| Multiple statements, hidden table, nested query or external reader | Reject the complete input before any analytical download or registration. Parsing only the first statement cannot pass. |
| No publication, or inconsistent publication metadata | Return the contract's unavailable-data or dependency error, respectively; never fall back to a candidate or live EIA. |
| Publication changes during execution | Continue with the original pinned version for files, rows and response metadata. |
| Query has 1,001 result rows, or its own `LIMIT 10` | Return 1,000 with `truncated=true` in the first case; at most ten with `truncated=false` in the second. Aggregates still read all qualifying input rows. |
| Checksum, deadline, memory or output-size failure | Safe error without partial success; no execution on unverified files. Keep capacity reserved until no execution remains. |
| Supervisor dies while a query runs | Recovery confirms termination or stops the associated container before conditional slot release. Unknown execution state occupies capacity. |
| Empty result, null measurement or duplicate output labels | Successful empty rows, preserved null, or ordered row arrays respectively; no invented zero values or dropped columns. |

### Recommendation and review gate

Proceed with this backend SQL slice using the existing A19 execution boundary. Begin implementation later with policy/engine compatibility tests, but do not expose an execution endpoint before staging, isolation and admission are verified. No new production dependency is proposed: SQLGlot and DataFusion are already pinned in `backend/pyproject.toml`.

Alayala approved this proposal by requesting continuation to the specification. Alayala subsequently approved the corrected [specification](spec.md), including Viewer exclusion, and requested [design](design.md)/[tasks](tasks.md). D01–D03 are accepted under A16/A19. Implementation remains a separate authorization stage.

## LLM

### Inspected baseline

| Component | What current source establishes |
|---|---|
| `auth.permissions.require`, `capabilities`, `permitted_dataset_keys` | Analyst/Admin have `sql:execute`; Viewer does not. Internal dataset keys are `national`, `facility`, `generator`; use `DatasetDefinition.table_name` for their public SQL names. Do not create a second role matrix. |
| `auth.dependencies.authenticated` | Current identity and application reads use a supplied database transaction. Analytical downloads/execution need a deliberate transaction boundary; do not hold that read transaction open through the entire query by copying the catalog route unchanged. |
| `publication.repository.read_publication` | Resolves active publication metadata; distinguishes an empty pointer from missing/inconsistent state. It does not resolve or authorize all analytical artifact paths. |
| `contracts.datasets.DATASETS` | Canonical table names, ordered Arrow schemas, decimal measurements and daily keys already exist. |
| `adapters.s3.S3Storage` / `StorageOperation.verify` | Existing adapter supports candidate writes and checksum readback. Readback hashes/discards chunks; it is not query-file staging and does not establish a least-privilege query reader. |
| `main.create_app` | Registers auth, settings, catalog and health. No query router is registered. |

Absence evidence: `rg --files backend/src/trinity backend/tests` and the backend file inventory contain no `queries/` runtime, SQL policy tests or query Dockerfile. `rg -n 'CREATE TABLE|create_table' backend/migrations/versions/*.py` finds local-auth and app-entry tables, but no analytical reservation/rate or artifact-manifest tables. The expected modules are selected in [backend architecture](../../docs/backend.md), not implemented in this inspected tree. These are scope observations, not claims of a regression.

The catalog handoff records prior automated results and a pending operator check. Those tests were not rerun for this proposal and do not establish SQL behavior.

### Contracts and required mechanics

Use [API/OpenAPI](../../docs/api-contract.md) and [wire schemas](../../docs/openapi.json) for the request, output, error codes and headers; [A9 schema](../../docs/schema.md) for publication/artifact identity; and [A19 security](../../docs/security-contract.md) for policy, isolation, admission and retries.

Keep one policy implementation in `queries/runtime/sql_policy.py`, imported by the trusted pre-download path. Parse the complete input and inspect every physical reference. A successful parse alone never authorizes a function or engine operation. Bind the validated operation, table mapping, request and publication to the runtime message; client SQL cannot select paths or connections. Runtime imports must not initialize API/worker configuration or privileged integrations.

Use the A15 responsibilities: `queries/service.py` owns permissions and publication pinning, `queries/client.py` owns supervision, `queries/runtime/engine.py` registers authorized local files, and `contracts/queries.py` defines the bounded message. Exact implementations remain design work.

Preserve current limits: 64 KiB JSON body, 16 KiB UTF-8 SQL text, 128 columns, 1,000 output rows, 5 MiB encoded response, 30 seconds including downloads, 1 GiB per query container, two active requests per user, four deployment-wide, and 30 analytical requests per user per minute across processes. Capacity values are provisional under A19; measure before changing them. Polling is excluded from the analytical rate counter.

Reject unsupported nested/binary results instead of lossy conversion. Detect truncation after the submitted query's own limit, without limiting aggregate input. Errors and logs must not reveal credentials, raw SQL, private paths, hidden schemas or traces. Authenticated responses retain no-store and correlation headers.

Downloads use at most three attempts for temporary external failures, with one- and three-second waits within the original deadline. Invalid SQL, authorization denial and validation failures are not retried. Staging cannot widen the pinned manifest or become a result cache. Release reservations only after confirmed termination, including cancellation, launch failure, lost connections and recovery.

### Details to resolve in specification and design

| Detail | Required resolution before execution is enabled |
|---|---|
| SQL grammar and engine agreement | Exact dialect, AST node allowlist, predicates, aliases/quoting, argument forms, ordering/grouping, limits, decimal arithmetic and failure semantics. Test each selected form with the pinned SQLGlot/DataFusion versions; do not implicitly enable extra syntax. |
| Publication artifact authority | Define the trusted lookup from the pinned publication to immutable manifest entries and checksums. Existing publication metadata alone is insufficient. Any required migration must remain consistent with A9. |
| Admission and supervision | Define transaction boundaries, reservation ownership, durable container identity, recovery, rate-window algorithm, request cancellation and slot-release races. Reuse PostgreSQL; auth login throttling is a separate policy. |
| Container protocol and hardening | Select exact image, user, capabilities, read-only mount rules, bounded transport, output accounting and stop/cleanup behavior. Prove no network, secrets, unrelated files or Docker control. |
| Evidence and delivery | Use synthetic published fixtures for local acceptance without activating live candidates. Separate real container/storage evidence from doubles and from alayala's operator walkthrough. |

### Verification boundary

Planned acceptance includes complete-input adversarial SQL tests with forbidden-I/O guards, real DataFusion execution over temporary typed Parquet, precision/null/grouping/CASE tests, output bounds and truncation tests, real PostgreSQL cross-process admission/recovery, authenticated HTTP role changes, and real container isolation/termination checks. Include known grammar bypass shapes such as table functions, catalog-qualified names, hidden subqueries and trailing statements. Unsupported forms must fail closed.

These checks have not run. SQLGlot/DataFusion compatibility, container isolation, live published storage and end-to-end SQL remain unverified. Maintain data evidence — ongoing; synthetic SQL fixtures do not create outage findings or replace the selected anomalies.
