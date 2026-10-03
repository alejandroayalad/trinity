# Session Security contract and API split

Date: October 3, 2026. Branch: `docs/backend-decisions-architecture`.

## Objective and contributions

[ME] Alayala selected role metadata, current identity checks, SQL functions, one network-disabled container per query, trusted S3 download/read-only mounting, SHA-256 evidence, limits, PostgreSQL query admission, bounded retries and local Docker Compose. He requested the API/security split, reference repair, A16 acceptance and preservation of superseded decisions.

[YOU] AI inspected current documents and preserved existing local edits. A16 was already accepted in the latest working tree, so it was retained and linked rather than assigned a second ID. AI recorded A19 for security and local execution, split the documents, aligned schema/OpenAPI/backend guidance and checked the challenge delivery requirements. No code, package, container, commit, push or remote mutation was authorized or performed.

## Decisions and corrections

A16 owns API flow and fixed warning-based publication. A19 refines A8/A13/A15/A18 and retains A9 SHA-256 evidence and A17 dependencies. The earlier combined document's limits, role field, direct runtime object access and unselected SQL functions are superseded, not implementation evidence. Historical references are updated to current destinations without rewriting historical claims.

The 30-second analytical deadline includes trusted file download/read time. PostgreSQL slot recovery must confirm execution has ended; a timeout or lease expiry alone cannot release capacity. These explain the selected boundaries rather than claim tested behavior.

## Challenge delivery evidence

Inspected `Software Engineer - Technical Challenge.pdf` in the parent workspace with pypdf: all eight pages, especially Live Session and Deliverables on page 7 and Submission & Questions on page 8. Page 7 requires local execution before the live session and source runnable locally from README; page 8 asks for the repository link. Searched the extracted full text for public URL, deployment, hosting and local-execution wording. No public application URL requirement appears in the supplied brief. No claim is made about separate recruiter correspondence. Docker Compose is the selected local direction; AWS/hosting remains undecided. The PDF remains outside Git, unchanged.

## Checks and results

Passed: reviewed the task diff against a pre-edit snapshot; 205 local Markdown links and 70 anchors resolve, fences are balanced and all 19 decision IDs are unique. The old API filename is absent from document/JSON references and A16 links resolve. Targeted stdlib OpenAPI checks cover 20 operations on 18 paths, 57 schemas, 358 internal references and 33 schema/media examples. Operation inventory, parameters, request bodies and response shapes are preserved; descriptions/security extensions now record selected limits and publication rules. These are structural/example checks, not a full external OpenAPI conformance validation.

A17's decision text, analytical/metric/window definitions and FINDINGS are byte-identical to the task snapshot. Earlier security proposal text is archived below; history edits elsewhere only route renamed references. No configured project formatter/linter/test runner or Compose file was found by `rg --files` with pyproject.toml, package.json, Makefile, compose, test and lint patterns. `git diff --check` passed. Runtime/security checks and local measurements remain unrun because implementation is outside this documentation task.

Review corrected two leftover API sentences that still called moved security rules proposals below. Current API prose now links to A19; unselected earlier token and pool defaults remain historical/proposed, not accepted.

## Next action

[ME] Review the security contract's query-container flow and remaining implementation details.

## Superseded security proposals

The following is the prior combined document's proposal text, retained as historical evidence. It is not current policy. A19 supersedes its role key, SQL function set, direct runtime storage access, analytical limits and process/admission choices. Exact token defaults not selected by A19 remain unaccepted. Database execution/pool defaults also remain proposals. Links below route to the current documentation where applicable.

### Earlier proposal record

The approved source requires identity and permission checks on every request. It does not select the exact token-validation implementation, Clerk lookup/cache strategy, SQL grammar, or runtime sandbox. The following earlier proposals remain available for review and are not silently accepted by the API-flow approval. API wire limits specified above remain part of the delegated HTTP completion; runtime capacity limits below are still proposed.

### Authentication and authorization

Use the official Clerk Python SDK to verify **session tokens only**, explicitly configuring the accepted token type. API authentication accepts `Authorization: Bearer ...`; reject missing or multiple credentials and do not fall back to cookies. The frontend obtains tokens through Clerk, without application-managed persistent token storage. Configure exact permitted frontend origins for CORS and Clerk `authorized_parties`; allow only the necessary methods and headers. CORS is a browser control, not authorization.

Validate the signature with trusted instance keys, the `RS256` algorithm only, exact issuer, expiration and not-before times with at most 5 seconds of clock skew, `sub`, `sid`, and an allowed `azp`. For this browser application require `azp`, even where a general provider integration permits it to be absent. Accept only active session tokens. Validate `aud` if the instance is configured to issue an application audience; do not assume Clerk's default tokens contain it. Never fetch keys from a token-supplied URL. Bound key-refresh requests and fail closed when verification cannot finish.

Store `trinity_role` as `viewer`, `analyst`, or `admin` in Clerk public metadata, writable only through trusted administration. Never use `unsafeMetadata`, a request field, or an Organization role for this shared-account model. Provision the three personas through Clerk administration; no Trinity role-management endpoint is included.

**Proposed simple revocation rule:** after local token verification, read the current Clerk user and session through the Backend API on every authenticated product request, without a role/session-status cache. Require an active session belonging to `sub` and a non-disabled existing user; obtain the current metadata role. Lookup failure returns `503 auth_unavailable`, with no product data or mutation. Role changes and session revocations therefore affect requests after Clerk reports the change; already-authorized work is not retroactively cancelled. Admin actions check immediately before their local transaction; no cross-system atomicity is claimed. Tradeoff: two bounded provider reads per request add latency and provider rate-limit dependence. A later cached design must explicitly choose its revocation delay.

Take action actor IDs only from the verified identity. Apply the same central permission policy to catalog, preview, metrics, SQL, status, settings, and approval. SQL is Analyst/Admin only; a Viewer cannot use SQL to access detail. Workers use internal service authority, never a saved user token. Logs record action, actor ID, outcome, and request/run ID; redact credentials and avoid raw SQL or source payloads.

Sources: [Clerk verification](https://clerk.com/docs/guides/sessions/manual-jwt-verification), [metadata access rules](https://clerk.com/docs/guides/users/extending), and [Backend API](https://clerk.com/docs/reference/backend-api). The no-cache lookup policy is a Trinity proposal, not a provider requirement. SDK signatures and error handling must be checked against the pinned release.

### SQL policy

A18 accepts the staged scope: required v1 uses single-table SELECT, filters, sorting, grouping and approved aggregates. Joins, CTEs and subqueries are optional only after the core works and tests pass. The following dialect, expression and function details remain proposals; A18 does not independently approve every grammar entry.

| Area | Proposed allowed form |
|---|---|
| Statement | Exactly one `SELECT`, optionally ending with one semicolon, from exactly one physical dataset with an optional alias. |
| Tables and identifiers | Only unqualified `national_outages`, `facility_outages`, or `generator_outages`, checked against server permissions. Allow unquoted identifiers and double-quoted exact column names such as `"percentOutage"`. |
| Clauses | Projection or `*`, `WHERE`, `GROUP BY`, `HAVING`, `ORDER BY`, and a nonnegative integer `LIMIT`. |
| Expressions | Columns, string/decimal/boolean/null/date literals, parentheses, arithmetic `+ - * /`, comparisons, `AND/OR/NOT`, `IS NULL`, `BETWEEN`, and `IN` with literal lists. |
| Functions | Only `COUNT`, `SUM`, `MIN`, `MAX`, `AVG`, `ABS`, `ROUND`, `COALESCE`, and `NULLIF`; argument counts/types must be checked. |

Everything else is rejected, including joins, subqueries, CTEs, set operations, windows, `SELECT INTO`, DDL/DML, `EXPLAIN`, `SHOW`, session commands, system catalogs, external/file table functions, URLs, comments/hints, and user-defined functions. A name containing a path or catalog qualifier is never a dataset. No dynamic extensions or arbitrary function registration.

Parse the **entire input** with SQLGlot's PostgreSQL dialect as the syntax baseline; this does not connect SQL to PostgreSQL or promise full PostgreSQL syntax. Reject parser warnings, fallback command nodes, extra statements, and every AST node or argument not in the explicit policy. Walk every table node and require exactly one ordinary allowed dataset. Reject unsupported nested constructs regardless of whether their tables would be permitted. Produce a canonical statement from the validated AST, reparse it, and execute only that statement. Do not validate one string and execute a different original. Verify the supported intersection with DataFusion using a shared fixture corpus; parser success alone does not prove engine agreement.

Allowed example: `SELECT period, SUM(outage) AS outage_mw FROM generator_outages WHERE facility = '46' GROUP BY period ORDER BY period LIMIT 100`. This is illustrative, not a claim about source facility membership. Reject `SELECT * FROM job_outbox`, `SELECT * FROM read_parquet('s3://bucket/file')`, a CTE containing either, and `SELECT * FROM national_outages; DROP TABLE x` before registering files. An unknown table gets a generic `sql_not_allowed`, without schema suggestions.

SQL `AVG` has ordinary SQL meaning; it must not be presented as US-08. The metric endpoint retains A9's capacity-weighted definition. Decimal arithmetic, aggregates, rounding, and division-by-zero behavior require fixtures on the selected engine; return a safe error instead of coercing an unsupported result into a float.

Sources: [SQLGlot parsing and AST documentation](https://sqlglot.com/sqlglot.html) and [DataFusion SQL options](https://datafusion.apache.org/python/autoapi/datafusion/index.html). Neither parser selection nor a SELECT check alone establishes a sandbox.

### Execution limits and isolation

These are proposed starting limits, not measured capacity: 64 KiB total JSON request body, 16 KiB SQL text, preview 1,000 rows, SQL 1,000 rows, 2 MiB encoded analytical response, 15 seconds total analytical execution including object reads, 512 MiB DataFusion memory budget, and 1 GiB total query-process memory. Over-limit output or memory fails the request without a partial result. Enforce limits while reading/producing data, not after collecting an unbounded result.

Allow at most two active analytical requests per application instance and one per user; return `429` when saturated rather than building an unbounded queue. Rate-limit authenticated analytical requests to 30 per user per minute. Use one API process in the initial deployment so local admission limits are meaningful; multiple replicas require a shared limiter before scale-out. Run one refresh pipeline globally, with finite separately supervised publication work; this does not replace A9's worker fences.

Create a fresh isolated query execution context per request. The trusted parent supplies protocol version, request ID, validated operation, pinned publication IDs, permitted artifact descriptors, and server limits; never forward the public body as an internal capability. Responses bind the request/publication IDs and contain typed bounded columns/rows or a sanitized code. Reject mismatches and unknown message fields. The internal channel must be private to the supervising parent; no public runtime endpoint and no Python pickle for messages.

The runtime receives read access only to that request's permitted published objects. It has no PostgreSQL, EIA, Clerk-management, or S3-write credentials. It cannot discover other versions, access arbitrary host files, use cloud metadata credentials, or reach arbitrary network destinations. Disable DataFusion DDL, DML, and statement operations as defense in depth. The supervisor enforces memory, deadline, termination, and cleanup, including client disconnect. A timeout response is not proof the process stopped.

**Deployment gate:** exact Linux/container controls, internal framing, per-request S3 capability delivery, image digests, and teardown verification remain required before executing untrusted SQL. This proposal defines the security properties and limits; it does not claim an OS sandbox exists. Restricting Python environment variables alone is insufficient. A9's finite EIA retries and worker recovery budgets also remain a separate execution specification.


### Proposed database execution model

Async FastAPI handlers and Psycopg `AsyncConnectionPool`, 1–5 connections per process with a 5-second acquisition deadline, remain proposed execution choices. A17 approves package versions, not these concurrency settings. Services still own explicit transactions under A15; external calls must not keep a long database transaction open.
