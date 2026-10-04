# Specification: One-table read-only SQL

Date: 2026-10-04
Status: Approved October 4, 2026 when alayala requested design/tasks after clarifying Viewer exclusion. D01–D03 are recorded under A16/A19. Design/tasks are drafted; implementation has not started.
Branch/base: `feat/catalog-permissions`, `fde733b`; existing catalog changes preserved.
Basis: [proposal](proposal.md), A4/A9/A13–A21 in [DECISIONS.md](../../DECISIONS.md), [API contract](../../docs/api-contract.md), [OpenAPI](../../docs/openapi.json), [security contract](../../docs/security-contract.md), [data contract](../../docs/schema.md), and [backend architecture](../../docs/backend.md).
Evidence: [specification session](../../ai/sessions/2026-10-04-single-table-sql-specification.md).

## Human

### Result and boundary

An Analyst or Admin can run one read-only query against one published outage table. Viewer cannot run SQL. Viewer sees no SQL button, menu entry, editor or Run control. A direct SQL-screen URL returns Viewer to the waiting screen before publication or the national dashboard after publication. Direct API submissions are denied independently of the interface, including SQL against national data. SQLGlot checks the entire query and its table before any analytical download. DataFusion executes the approved operation inside a separate container that can read only the authorized files.

Input: the current bearer session and `POST /api/v1/queries` with only a `sql` string. Flow: authorize → validate SQL → pin published data → reserve capacity → download and verify files → execute in isolation → return bounded rows and confirm cleanup. PostgreSQL holds application state; user SQL cannot read it.

Output: ordered column descriptions, row arrays, row count, truncation flag, elapsed milliseconds, publication metadata and permitted diagnostics. Numbers are strings so serialization does not lose precision. Null remains null. Duplicate output labels do not overwrite columns.

Example: `SELECT period, outage FROM national_outages ORDER BY period LIMIT 10` returns at most ten rows from one published version. It does not fetch EIA data or inherit preview filters.

Failure: `SELECT * FROM local_users` returns a safe SQL-policy error before downloads. When no publication exists, a valid query receives `409 data_unavailable`; an invalid query still fails SQL policy first. An engine timeout produces an error, and its capacity slot remains occupied until termination is confirmed.

### Accepted details

The accepted A18/A19 scope remains unchanged. This specification selects a concrete first grammar (D01), a rolling rate window (D02), and predictable SQL result presentation (D03). A16/A19 record their acceptance; they are not verified library behavior. Their detailed rules appear below.

This slice includes the staging, container, shared capacity and recovery needed for safe execution. Preview/dashboard routes, frontend, refresh/publication commands, query history, export and extended SQL remain outside it. The existing catalog operator check remains separate.

## LLM

### Requirements

IDs are local to this slice. Canonical contracts take precedence; D01–D03 are accepted specification details recorded in A16/A19. No endpoint may be enabled with only policy tests passing.

| ID | Required behavior |
|---|---|
| R01 | Add only `POST /api/v1/queries` for this slice. Accept an application/json object containing exactly one nonblank string field, `sql`; reject unknown fields and query parameters. The client cannot supply role, actor, version, paths, credentials, engine configuration or resource limits. |
| R02 | Check the current active account, valid local session and stored role on each request. Require `sql:execute` before SQL parsing or protected publication/artifact reads. Viewer and unknown roles receive no SQL access. A Viewer SQL request must not invoke SQL parsing/validation, analytical rate accounting, slot reservation, downloads, file registration or execution. Previously accepted authorized work may finish after a later role change, as A19 allows. |
| R03 | Bound the JSON body to 65,536 bytes and decoded SQL to 16,384 UTF-8 bytes independently of character count. Preserve existing transport bounds. Malformed, oversized and unauthorized requests never start analytical work. Bound parser depth/work; length alone is not a CPU or recursion guarantee. |
| R04 | Use one whole-input SQLGlot policy in `queries/runtime/sql_policy.py`, called by the trusted path before downloads. Require exactly one supported read-only SELECT with one permitted physical table; inspect all descendants, statement modifiers, table forms and functions. Fail closed on unrecognized nodes or arguments. |
| R05 | Resolve canonical public table names through `DATASETS` and the shared role policy. Do not accept internal short keys as extra tables, application tables, hidden catalogs, client paths, table functions or unpublished candidates. Table aliasing does not introduce a second physical table. |
| R06 | Support the accepted filters, sorting, grouping, arithmetic, CASE and eight functions through the explicit reviewed grammar. Reject writes, DDL, JOINs, CTEs, subqueries, multiple statements, external readers/URLs, custom functions and any syntax outside that grammar. Parsing success alone never enables an engine feature. |
| R07 | Check allowed and rejected SQL against the pinned SQLGlot/DataFusion versions. Bind execution to the exact approved operation and table mapping. No reparsing/rewrite or runtime message may widen the authorization; unknown or inconsistent messages fail closed. |
| R08 | After authorization and applicable SQL-policy checks, resolve one valid active publication. An existing empty pointer gives `409 data_unavailable`; missing/inconsistent state gives a safe dependency failure. Pin publication metadata and immutable artifact authority for the entire request. Never use a candidate, latest refresh or live EIA as a fallback. |
| R09 | Derive all files for the selected table from the pinned immutable manifest authority. Verify manifest/version binding, dataset identity, safe relative paths, recorded byte sizes, SHA-256 checksums and canonical schema fingerprints before execution. Missing, extra-authority, mismatched or incomplete required artifacts fail; never query a successful subset. |
| R10 | Reserve shared analytical capacity atomically in PostgreSQL before staging. Enforce two active requests per user and four deployment-wide across API/supervisor processes. Unknown execution state still occupies capacity; unavailable admission storage never permits unreserved work. |
| R11 | Apply the cross-process analytical rate limit of 30 per user per minute, separate from login throttling and active slots. Return 429 with bounded Retry-After when rate/capacity is unavailable; do not enqueue the query. D02 specifies the accepted counting boundary. |
| R12 | Start one 30-second analytical deadline before the first download. All download attempts, waits, staging, container startup, execution and result collection share its remaining budget. Timeout cancels work and initiates stop confirmation; returning an HTTP error does not release capacity. Bound pre-download parsing and supervisor I/O separately in design. |
| R13 | Trusted code stages only authorized published files into a request-specific location. The query container receives a read-only mount and no network, database/S3 credentials, Docker control, unpublished data or unrelated host resources. Runtime imports must not initialize privileged API/worker state. |
| R14 | Launch one separate container per query with the 1 GiB memory ceiling and remaining deadline. DataFusion registers only the authorized local table files and cannot use SQL to register readers, catalogs, stores or functions. Apply runtime restrictions independently of SQLGlot. |
| R15 | Return the exact QueryResponse shape and scalar types below. Enforce 128 columns, 1,000 rows and 5,242,880 encoded response bytes. Buffer/validate bounded output before sending successful response headers; failures cannot become partial successful data. Bound internal messages, stdout/stderr and supervisor memory too. |
| R16 | Detect truncation from an extra row after the submitted query's own LIMIT. The output cap must not limit rows used for aggregation, filtering, grouping or ordering. Empty SQL results are successful results, not evidence of missing source observations. |
| R17 | Preserve A9 source decimals and nulls. Serialize integer/decimal results as strings without conversion through float or forced six-place formatting of calculated results. Define and verify calculation precision, rounding, overflow and division behavior before enabling each supported form. Reject unsupported output instead of silent loss or nonfinite JSON. |
| R18 | Confirm execution ended or stop it, remove request-owned temporary resources, and conditionally release only its reservation. Persist enough ownership/container identity for crash recovery. Lease expiry, disconnect, timeout or lost DB connection alone never proves termination. Cleanup must not delete published objects or retained evidence. |
| R19 | On supervisor restart, reconcile recorded execution: identify and confirm its container stopped, or stop it, before releasing capacity. Resolve launch/recording races and duplicate recovery safely. If execution status is unknown, retain the reservation and deny capacity as needed. |
| R20 | Retry only classified temporary external failures, at most three total attempts with 1s and 3s waits inside the same deadline. Denied access, invalid SQL, identity/validation failures and user expression errors are not retried. Internal retries do not consume extra user rate entries. |
| R21 | Use canonical safe errors, request IDs and no-store headers. HTTP responses, runtime error/output messages and logs expose no credentials, raw SQL, hidden schemas, private paths, engine suggestions or traces. The trusted bounded runtime input necessarily carries the approved operation and authorized local-file mapping; it must not be logged or forwarded to clients. Only safe identifiers, outcome and bounded diagnostic metadata may be recorded. |
| R22 | Preserve existing auth/catalog/settings/health behavior and selected dependency pins. No live publication, EIA operation, production dependency addition or cloud reconfiguration is part of this slice. Any necessary persistence changes must match A9 and be reviewed in design. |
| R23 | Prove the production request path using offline tests, real DataFusion/Parquet fixtures, real PostgreSQL/HTTP tests and real container isolation/recovery tests. Distinguish each evidence category from retained-account operator checks and live published-storage proof. |
| R24 | Preserve A16’s accepted dashboard-only Viewer interface: no SQL navigation, button, editor, Run control or other user-submitted-SQL action. Deny direct SQL-screen access and return Viewer to the permitted waiting/dashboard screen. Analyst/Admin retain SQL access. This is a later frontend acceptance requirement; this backend slice must prove direct API denial under R02. Viewer national dashboard/preview support remains permitted. |

### D01 — Accepted first SQL grammar

This accepted subset refines A18/A19. Design must map its user-visible behavior to an exact parser dialect and AST allowlist and verify compatibility. A compatibility failure requires an explicit correction, not silent widening or loss of a required form.

| Area | Supported forms |
|---|---|
| Statement | One SELECT with one FROM table and optional single table alias. Optional WHERE, GROUP BY, ORDER BY and a nonnegative integer literal LIMIT, including zero. Whitespace, ordinary comments and one terminal semicolon are allowed; comments/terminators cannot hide another statement. |
| Names and projection | Exact canonical public table/column names; optional double quotes preserve their exact spelling, including `percentOutage` and `facilityName`. Keywords/functions are case-insensitive. Column references may use the one table name or alias as qualifier. Support `*`, that table/alias's `*`, scalar expressions and explicit `AS` output aliases. |
| Values and expressions | Finite integer/fixed-point decimal literals, string literals, NULL, TRUE/FALSE, `DATE 'YYYY-MM-DD'`, column references, parentheses, unary plus/minus, and `+`, `-`, `*`, `/`. Date literals must represent real calendar dates. No scientific notation, arbitrary casts, intervals or parameters in this first grammar. |
| Predicates and CASE | `=`, `<>`, `!=`, `<`, `<=`, `>`, `>=`, AND, OR, NOT, IS NULL/IS NOT NULL, [NOT] BETWEEN and [NOT] IN with nonempty literal lists; searched `CASE WHEN predicate THEN expression ... [ELSE expression] END`. No subquery forms or simple `CASE value WHEN ...` in this subset. |
| Grouping and ordering | GROUP BY canonical column references; ORDER BY column references or a unique output alias, each optionally ASC/DESC and NULLS FIRST/LAST. No positional ordinals; ambiguous aliases fail safely. Default is ASC and NULLS LAST (D03), without changing identifier/string values. |

Function forms:

| Function | Supported arguments |
|---|---|
| COUNT | `COUNT(*)` or `COUNT(expression)`; normal null handling. No DISTINCT, FILTER or window form. |
| SUM, AVG | One numeric scalar expression; no nested aggregate. |
| MIN, MAX | One supported orderable scalar expression; no nested aggregate. |
| ROUND | Numeric expression and optional integer literal decimal-place argument. Exact supported range and numeric behavior must be verified and documented in design. |
| COALESCE, NULLIF | COALESCE with at least two type-compatible scalar expressions; NULLIF with exactly two comparable scalar expressions. Scalar functions may wrap aggregate outputs when grouping is valid. |

Reject every unlisted form, including SELECT DISTINCT, HAVING, OFFSET/FETCH, set operations, windows/OVER, aggregate FILTER, grouping sets, LIKE/regular-expression operators, arbitrary CAST, schema/catalog qualification, hints, locks, SELECT INTO, table sampling, table-valued functions and extra function modifiers. An `IN` literal list is allowed; `IN (SELECT ...)` is not. A typed DATE literal is the only accepted date-construction syntax and does not grant arbitrary CAST authority even if a parser represents it internally as a cast.

Exactly one physical table is required even for a constant or aggregate query: `SELECT 1` is rejected; `SELECT 1 FROM national_outages LIMIT 1` is permitted. A self-join is rejected. Public table identifiers are exact registry names; unknown names receive the same safe SQL-policy failure without lookup suggestions. D01 deliberately does not rely on an engine's default identifier folding.

### Publication and file authority

Use a trusted consistent snapshot to obtain the current identity, pinned publication and version-bound artifact authority. SQL policy must complete before reporting no publication. Do not keep the existing auth read transaction open throughout downloads/execution; design must separate short metadata/admission transactions from long analytical work without mixing publication versions.

The existing `publication.repository.read_publication` is a metadata baseline, not a complete artifact reader. Link the pinned version to its frozen manifest digest and ordered entries using A9 authority. If the manifest itself must be downloaded, that download also follows SQL validation, reservation and the same analytical deadline. Read all required files for the selected table, including multiple files when the manifest contains them; do not mount the other two datasets merely because the manifest lists them.

Check path confinement and actual file identity. Reject traversal, absolute paths, URLs, path collisions and symlink escape during staging/mount preparation. No user SQL or request field determines an S3 location or local mount. Checksums alone do not establish that a file belongs to an authorized publication. Query cleanup removes only its own staging/container resources, never published objects or existing evidence.

A publication change during execution does not invalidate this query: its response uses the original pinned files and publication fields. SQL has no continuation cursor and no client-selected historical version. A retained published version may remain readable for its already-pinned request even after the active pointer changes.

### D02 — Accepted rate-accounting behavior

Use a rolling 60-second window keyed by trusted user ID across processes. At a shared authoritative time T, admit at most 30 counted requests in `(T - 60 seconds, T]`; do not reset at minute boundaries. Design chooses persistence/locking details and proves atomicity.

Count a request once after transport/body shape and role authorization succeed, before SQL parsing. Thus policy failures, no-publication responses, capacity denials and later execution/dependency failures consume the already-counted attempt. This prevents repeated invalid SQL from avoiding the analytical rate policy. Rate-denied requests do not add entries or extend the window. Missing/invalid sessions, Viewer denials, malformed bodies and polling do not count. Internal retries do not count again.

Rate and capacity are separate: an accepted rate entry does not grant a slot. Rate denial may precede SQL parsing; an under-rate Viewer is still denied before parsing or analytical accounting. Retry-After for rate denial reflects the earliest relevant expiry with a positive rounded-up second value. For capacity denial use safe bounded retry guidance; it is not a promise that another query will end then. No queue is introduced.

### Output and D03 accepted presentation rules

| Field | Required value |
|---|---|
| `publication` | Exact pinned `publication_event_id`, `version_id`, `published_at`, `coverage_start`, `coverage_end`, `latest_observation_date`; never null on success. |
| `columns` | Ordered metadata with exactly `name`, `type`, `nullable`, `unit`. Names have 1–128 characters; types are string/date/timestamp/decimal/integer/boolean; unit is MW, percent or null. At most 128 columns. |
| `rows` | Arrays aligned with columns. Every row has exactly the column count. Dates/timestamps/identifiers/numbers are strings; booleans remain booleans and null stays null. At most 1,000 rows. |
| `returned_rows`, `truncated`, `execution_ms` | Row-array length as integer; exact extra-row flag as boolean; nonnegative integer elapsed milliseconds. No SQL pagination token. |
| `diagnostics` | At most 32 safe diagnostics with only code, severity, scope, message, affected_count, as OpenAPI specifies. Use actual permitted evidence; never invent a diagnostic from synthetic examples or leak candidate/Admin detail. |

D03 requires that `execution_ms` measure the analytical budget interval from immediately before downloads through bounded result collection, including retries and startup; it excludes authentication/parsing and post-execution resource cleanup. Record timeout/cleanup evidence separately without adding public fields. A response cannot be reported as successful while execution is still running or its output is unverified.

D03 also requires: direct column references, including aliases and `*`, retain canonical units; calculated/aggregate expressions use unit=null rather than inferring dimensional meaning. Type/nullability comes from the validated output schema and must cover every returned cell. Preserve explicit aliases exactly. Give unaliased expressions stable bounded labels generated by trusted code; never use raw engine expression text that could echo SQL literals. Duplicate labels remain separate ordered columns. Labels exceeding the public bound fail safely rather than truncate or collide silently.

No ordering is promised without ORDER BY. Under D03, omitted direction means ASC and omitted null order means NULLS LAST for either direction; text sorting uses fixed binary ordering without locale-dependent normalization. These behaviors require parser/engine fixtures. Ties need not be ordered unless the submitted keys make them unique.

Scalar output must retain computed precision rather than assume the stored decimal(24,6) scale. Type-invalid expressions, overflow, division by zero, incompatible CASE/function branches and unsupported output fail with safe `query_failed`; no partial results, implicit zero or nonfinite value. Design must record the supported result precision/scale and ROUND tie behavior from compatibility checks before enabling these expressions. If a permitted form cannot satisfy the agreed semantics, report the conflict for review rather than quietly accepting float loss.

Truncation examples: 1,001 result rows → return 1,000/true; exactly 1,000 → 1,000/false; LIMIT 10 → at most 10/false; LIMIT 0 → zero/false with column metadata. `COUNT(*)` over 2,001 qualifying input rows returns `"2001"` in one row, not a count capped at 1,000. Empty aggregate input follows ordinary verified SQL null/count semantics. The final encoded envelope, including metadata and diagnostics, must fit 5 MiB.

### Errors and precedence

Transport rejection may precede authentication. After valid transport/body shape: current role authorization precedes SQL parsing and protected lookup; D02 rate admission precedes parsing; whole-input SQL policy precedes no-publication handling and all downloads. Known column/grammar failures should be caught against canonical schemas before downloads; engine type/execution failures remain safe failures. A syntactically valid unsupported table gets `sql_not_allowed`, not a schema-disclosing engine error or a new query-specific 404.

| Trigger | Result |
|---|---|
| Invalid JSON / unsupported content type | `400 invalid_json` / `415 unsupported_media_type`. |
| Missing/nonstring/blank SQL, extra fields, query parameters | `422 invalid_request`; no analytical work. |
| JSON or SQL UTF-8 byte bound exceeded | `413 request_too_large`. |
| Missing session / invalid, expired, revoked or inactive identity | `401 authentication_required` / `401 invalid_session`; include WWW-Authenticate: Bearer. |
| Viewer or unknown role | `403 forbidden`; no SQL parsing or protected lookup. |
| SQL parse failure, disallowed syntax/function/table/column | `422 sql_not_allowed`; no raw SQL or engine suggestions. |
| Valid authorized SQL, existing empty publication pointer | `409 data_unavailable`; no staging/container. |
| User-correctable engine expression/type/output incompatibility | `422 query_failed`; sanitize completely. |
| Rate or active-capacity limit | `429 rate_limited` with Retry-After; no unreserved staging or query queue. |
| Auth storage / publication-artifact-admission dependency failure | `503 auth_unavailable` / `503 dependency_unavailable`, according to failing boundary. File identity failure never executes. |
| Memory, column or encoded-output ceiling | `503 query_resource_limit`; row limit alone instead uses successful truncation. |
| Analytical deadline expires | `504 query_timeout`; stop confirmation and reservation ownership remain required. |
| Unexpected internal error or invalid internal runtime message | Safe `500 internal_error`; no partial success or authority widening. |

All errors use canonical Problem fields and application/problem+json, X-Request-ID and Cache-Control: no-store. Provide bounded retry seconds on 503 only when known. Do not add candidate blockers, revision state, private filenames or engine exceptions to SQL errors. Hardening failures and missing Docker are dependency failures; there is no in-process execution fallback.

### Acceptance scenarios

These are required future tests, not results. Doubles may prove order/call suppression; they cannot establish real isolation, termination or shared database concurrency.

#### Request, policy and compatibility

| ID | Scenario and required evidence | Requirements |
|---|---|---|
| S01 | Actual HTTP route accepts exactly the SQL body; reject unknown fields, query parameters, null/nonstring/blank input, malformed JSON and wrong content type with the defined codes. | R01, R03, R21 |
| S02 | Byte boundaries: JSON 65,536/65,537 and SQL 16,384/16,385 bytes, including multibyte text. Deep nested expressions fail within the selected parser work bound. | R03 |
| S03 | All three real personas; Viewer and invalid/expired/revoked/inactive/unknown-role sessions never invoke the SQL parser, artifact reader or executor. Viewer requests also leave analytical rate entries and capacity reservations untouched. Stored role changes affect the next request. | R02, R21 |
| S04 | Valid D01 examples against each canonical table, aliases, mixed-case source columns, quoted exact identifiers, comments and terminal semicolon; SQLGlot and real DataFusion agree on allowed forms. | R04–R07 |
| S05 | Every accepted predicate, arithmetic operator, CASE and function form; null inputs, date boundaries, group/order behavior, aliases and D03 null/text ordering. Compare expected typed values to real engine output. | R06, R07, R17 |
| S06 | Multiple statements, trailing writes, semicolons in strings/comments and hidden statements: validate the whole input; reject extra statements before any analytical download. | R04, R06 |
| S07 | JOIN/self-join, CTE, subquery in every expression/clause, set/window forms, unknown modifiers and all explicitly excluded D01 syntax: safe rejection with forbidden-I/O guards. | R04, R06 |
| S08 | File readers, URLs, custom/qualified functions, schema-qualified/application tables, short dataset aliases and unknown columns: safe policy rejection without lookup suggestions or registration. | R05–R07, R21 |
| S09 | Mismatched validated SQL, extra file/table mapping, wrong request/version and malformed/oversized runtime messages fail without authority widening. | R07, R13–R15 |

#### Publication, files and execution

| ID | Scenario and required evidence | Requirements |
|---|---|---|
| S10 | Valid SQL with no publication gives data_unavailable; invalid SQL with no publication gives sql_not_allowed first. Candidates never create readiness; broken metadata gives dependency_unavailable. | R04, R08 |
| S11 | Synchronize publication change during metadata/staging/execution. Every file and returned publication field remains from one pinned version; next request can see the new version. | R08, R09 |
| S12 | Selected table spans several manifest files. All required files contribute; other tables are neither downloaded nor mounted. Missing file, wrong size/hash/schema or manifest/version mismatch prevents execution. | R09, R13 |
| S13 | Traversal, absolute paths, URL paths, collisions and symlink replacement fail confinement; immutable identity and mount protections prevent bytes changing between check and use. | R09, R13 |
| S14 | Real query container cannot reach network, S3/database credentials, Docker control, unrelated host files or unpublished data; attempts to write its data mount fail. No privileged import initialization. | R13, R14 |
| S15 | Temporary download failures use at most three attempts with 1s/3s waits under the original deadline. Denial, corrupt identity and invalid SQL never retry. | R12, R20 |
| S16 | Missing runtime/dependency or unsafe launch configuration gives a safe failure without an in-process fallback. Launch failure confirms no execution remains before release. | R13, R14, R18, R21 |

#### Output, limits and recovery

| ID | Scenario and required evidence | Requirements |
|---|---|---|
| S17 | Real engine fixtures preserve decimal precision, signed values, nulls and source IDs. Test COUNT/SUM/AVG/MIN/MAX, empty aggregates, CASE/ROUND/COALESCE/NULLIF and safe failures for zero division/overflow/incompatible types. | R07, R17 |
| S18 | Results of 0, 999, 1,000 and 1,001 rows; LIMIT 0/10/1000/1001; aggregate over more than 1,000 inputs. Verify rows, count and truncation without limiting input. | R15, R16 |
| S19 | Duplicate labels, long/empty aliases, literal canaries in unaliased expressions, boolean/date/decimal cells, output types/nullability and units follow OpenAPI/D03; no SQL literal leakage in metadata. | R15, R17, R21 |
| S20 | 128/129 columns and full UTF-8 envelopes at/over 5 MiB, plus oversized child output/stderr. Bounds hold and failures send no partial successful body. | R15, R21 |
| S21 | Real container exceeds deadline or memory cap; prove termination, safe error, cleanup and slot ownership. A simulated timeout alone does not pass. | R12, R14, R18 |
| S22 | Multiple real PostgreSQL processes race for slots: two-per-user and four-global limits hold throughout staging, execution and stop confirmation; failure never launches unreserved work. | R10, R18 |
| S23 | Multiple processes cross D02's rolling-window boundary: at most 30 counted attempts, correct Retry-After, no minute-boundary burst. Verify invalid-SQL/counting/polling/retry exclusions. | R11, R20 |
| S24 | Kill supervisor before/after container creation and before result/release; lose HTTP/DB connections; recover twice concurrently. No orphan grants extra capacity, wrong-owner release or deletion of another request's files. | R18, R19 |
| S25 | Docker status unknown or termination fails: hold reservation. Restore control and prove recovery stops/confirms, cleans and releases only the correct execution. | R10, R18, R19 |
| S26 | Capture response, runtime channel and logs with secret/path/hidden-schema canaries across failures. Verify fixed safe codes, correlation/no-store and 401/429 headers. | R21 |
| S27 | Regress existing health/auth/catalog/settings and confirm no EIA call or live publication mutation. Existing dependency pins and canonical data definitions remain intact. | R22 |
| S28 | Document actual HTTP + PostgreSQL + container execution with synthetic published Parquet, then separately report retained-account operator and live storage evidence. Do not count skipped categories as passed. | R23 |
| S29 | Later frontend: Viewer sees no SQL navigation/button/editor/Run control; direct SQL-screen URL returns to waiting before publication or national dashboard after publication. After an Analyst-to-Viewer role change is observed, remove SQL controls and block new submissions. Independently, a valid direct POST with Viewer’s session gives 403 forbidden and no SQL work (S03). Frontend proof remains outside this backend slice. | R02, R24 |

### Remaining design obligations and gate

A16/A19 now record D01–D03, and the API/security prose is aligned. The [design](design.md) and [tasks](tasks.md) are drafted under alayala’s request; this does not authorize implementation. Design must resolve the exact SQLGlot dialect/AST policy, tested numeric precision/ROUND behavior, parser bounds, immutable artifact lookup and migration needs, PostgreSQL ownership/rate transactions, container/image hardening, message protocol, result labeling, and crash/cleanup races. No new runtime defaults are silently selected by this specification.

Use the repository's unittest workflow and selected dependencies for implementation acceptance, with disposable databases/files/containers. Keep synthetic fixture publication separate from permission to activate real data. Record failures and measured resource behavior before changing provisional A19 limits. Alayala owns builds/clicks, retained-account checks and evaluator demonstration as instructed by AGENTS.md.

Done: approved requirements and acceptance scenarios; design/tasks drafted.
Pending: design/task review and implementation authorization; every runtime acceptance category remains unperformed.
Blocker: none for design/task review; parser/engine compatibility and runtime foundations must be proven before endpoint enablement.

Maintain data evidence — ongoing. This specification creates no new source observation or anomaly selection.
