# Specification: Filtered, paginated dataset previews

Date: 2026-10-04
Status: Specification approved October 4, 2026 when alayala confirmed D01–D03. A16 records strict preview inputs and cursor continuity; A19 records shared rate accounting. The [design](design.md) and [tasks](tasks.md) are drafted under the subsequent continuation request. Step 2 is now separately authorized and implemented offline; see [implementation evidence](../../ai/sessions/2026-10-04-dataset-preview-step-2.md). Later stages remain pending.
Branch: `feat/catalog-permissions`; inspected HEAD `e851e28`. Concurrent SQL work is preserved.
Basis: [approved proposal](proposal.md), [API contract](../../docs/api-contract.md#preview-and-filter-choices), [OpenAPI](../../docs/openapi.json), [data contract v1](../../docs/schema.md), [security contract](../../docs/security-contract.md), [backend structure](../../docs/backend.md), and A9/A15–A21 in [DECISIONS.md](../../DECISIONS.md).
Evidence: [specification session](../../ai/sessions/2026-10-04-dataset-preview-specification.md).

## Human

### Result

An authenticated user can read a bounded page of actual published outage records, filtered by dates and applicable entity IDs. Viewer can read national records for the dashboard. Analyst and Admin can read all three datasets. This endpoint adds no Viewer Catalog/SQL navigation and accepts no submitted SQL.

Input: `GET /api/v1/datasets/{dataset_key}/preview` with the existing session and optional `start`, `end`, `facility`, `generator`, `limit`, `cursor`. Flow: authorize the dataset → validate the request and cursor → pin one publication → reserve shared capacity → stage verified files → run a typed preview in the isolated DataFusion runtime → return exact rows and a next cursor when needed → confirm cleanup before releasing capacity.

Output: every column of the selected dataset in canonical order, matching row arrays, resolved date bounds, one publication, returned row count, permitted diagnostics and an optional next-page cursor. Numeric source values remain decimal strings. Missing optional values remain null. No publication is `409 data_unavailable`, not a successful empty preview.

Example: an Analyst requests generator data for September, facility `46`, generator `1`, with `limit=10`. The response contains the first ten matching daily records, if present. Following the cursor with the same filters gives the next records. If publication changes between pages, the next request returns `409 publication_changed`; restart from page one.

Failure example: an Analyst gets a facility cursor, then their stored role becomes Viewer. The next page returns `404 dataset_not_found` before file access. A cursor cannot preserve old permissions.

### Accepted refinements

| Detail | Accepted behavior |
|---|---|
| D01 — Strict inputs | Reject duplicate parameters, blank values, noncanonical dates/page-size text and invalid entity-filter combinations. Keep exact entity strings unchanged. |
| D02 — Shared rate accounting | Count one authorized, well-shaped preview attempt before semantic filter/cursor/publication checks. Subsequent failures retain the debit. Use SQL's same per-user rolling budget, not a second preview quota. |
| D03 — Cursor lifecycle | Defaults come from the pinned publication. A valid continuation requires the same active publication and effective filters. Cursors have no time-only expiry while their publication and signing key remain valid; reauthorize every use. |

Alayala confirmed these refinements; they are recorded under A16/A19. His term “installation” refers to the existing `facility` field: selecting a specific `generator` requires its `facility`. This does not make a facility filter mandatory for an unfiltered generator-dataset preview. Existing role, page-size, publication and isolation rules remain mandatory. Cursor encoding/signing now has offline Step 2 implementation; deployment and endpoint integration remain pending.

## LLM

### Requirements

IDs are local to this slice. D01–D03 are accepted specification rules recorded under A16/A19. Their acceptance does not establish implementation or runtime correctness.

| ID | Required behavior |
|---|---|
| R01 | Add only `GET /api/v1/datasets/{dataset_key}/preview`. Accept the six query parameters above and no nonempty body. Reject unknown parameters and client role, actor, SQL, storage path, version, sorting or column-selection inputs. Preserve existing transport limits. |
| R02 | Resolve the current active account, valid session and trusted role on every page. Require the applicable preview capability and shared dataset permission before protected analytical work. Never cache role/session authority or use the cursor as authorization. |
| R03 | Map the three exact public dataset names to canonical internal keys. Unknown and unauthorized datasets return the same safe 404. Viewer gets only national rows, columns, diagnostics and mounted files; Analyst/Admin get only the requested dataset per operation. |
| R04 | Apply D01's strict scalar request shape, valid calendar dates, bounded strings and page-size parsing. Duplicate/unknown parameters and nonempty GET bodies fail before analytical work. |
| R05 | Apply inclusive date bounds. For each omitted bound independently, default start to latest observation minus 29 days and end to latest observation from the pinned publication. Require start ≤ end and 1–366 inclusive dates; do not silently swap, clamp or extend bounds. |
| R06 | Use exact case-preserved facility/generator strings without numeric conversion, trimming, wildcard interpretation or Unicode normalization. Facility filters require a detailed dataset; generator filters require the generator dataset and an explicit facility. Unknown IDs return no matching records. |
| R07 | Use complete A9 daily-key ascending order with fixed binary string ordering. Continue strictly after the last returned full key, never by row offset or period alone for detailed datasets. |
| R08 | Default limit to 100 and allow 1–1,000. Collect at most limit + 1 result rows, return at most limit and emit a cursor exactly when the lookahead row exists. Bind the cursor to the last returned key, never the lookahead key. |
| R09 | Authenticate a bounded opaque cursor; bind purpose, dataset, resolved bounds/filters, page size, complete last key and publication ID. Validate payload shape/types, signature and request agreement. Follow D03; never use cursor data to choose historical or arbitrary files. |
| R10 | Pin public publication metadata and the immutable authorized artifact/diagnostic identity through trusted state. Keep files, rows, diagnostics and response metadata on that publication even if another becomes active during execution. Recheck current active publication on each later page. |
| R11 | An empty active pointer on the first page is 409 data_unavailable. Missing/inconsistent required publication state is 503 dependency_unavailable. A valid continuation to a different/no-longer-active publication is 409 publication_changed under D03. Candidate storage does not make data ready. |
| R12 | Build typed runtime predicates for dates, exact IDs and full-key continuation; use fixed sort and bounded collection. Do not concatenate client values into SQL, submit generated text to the SQL API or expand the public SQL grammar. |
| R13 | Return exactly PreviewResponse and canonical Column/Publication/Diagnostic shapes. Derive ordered columns, types, nullability, units and keys from the existing dataset/catalog contracts. Validate all rows and the whole encoded response before successful delivery. |
| R14 | Preserve exact DECIMAL(24,6) source values, nullable text/percentage fields and source percentOutage. Use decimal strings, ISO dates and source ID strings. No float conversion, rounding source values, calculated replacement percentages or fabricated zero/missing rows. |
| R15 | Empty matching data returns 200, empty rows, returned_rows=0, next_cursor=null and reason=not_reported. Nonempty data has reason=null. Failures, missing artifacts and broken continuations are never reported as not_reported. |
| R16 | Diagnostics describe only the authorized dataset/scope from the pinned published state, subject to Viewer national privacy and the existing maximum of 32 entries. Never serialize Admin candidate/raw-error payloads or infer an empty diagnostic set from missing required provenance. |
| R17 | Apply shared per-user rolling analytical rate accounting under D02. Each page is a request. Use the same counter as SQL and other analytical operations, separate from login throttling. Return 429 with Retry-After when denied. |
| R18 | Use shared PostgreSQL admission: at most two active analytical requests per user and four deployment-wide, including simultaneous SQL/preview work. Never execute without a reservation or enqueue excess requests. Keep metadata transactions short and release them before staging/execution. |
| R19 | Stage only authorized files of the pinned publication through trusted storage code, verify SHA-256, and supply a request-specific read-only mount to the shared per-query runtime. No live EIA fallback, unpublished data, application tables, extra mounts, storage credentials, network or Docker control are available inside execution. |
| R20 | Enforce 30 seconds including trusted downloads/reads, retries, startup and execution; 1 GiB container memory; and 5 MiB encoded response. Keep preview pagination independent of SQL's output schema. No partial successful output on limit failure. |
| R21 | On normal completion, timeout, disconnect, launch failure or supervisor crash, confirm execution ended or stop it before releasing its owned reservation. Unknown execution state retains capacity. Recover/clean request resources without deleting published data or evidence. |
| R22 | Preserve safe errors, X-Request-ID and Cache-Control: no-store. Reject corrupt runtime output, provenance or schema instead of passing it through. Logs/errors contain no secrets, cursor payloads, hidden IDs/counts, private paths, raw SQL or internal traces. |
| R23 | Preserve existing auth/catalog/SQL behavior and dependency pins. Integrate with the shared runtime once reviewed and verified, without copying it or using an in-process fallback. This document changes no SQL pairing gate or code. |
| R24 | Prove the endpoint through offline tests, real PostgreSQL/HTTP and container acceptance, and a distinct retained-account operator check. Maintain data evidence — ongoing. Frontend, filter-choice endpoints, dashboard aggregates and live publication setup remain outside this slice. |

### Dataset permissions and ordered data

| Public dataset | Internal key | Required capability and roles | Full key / ordered ascending |
|---|---|---|---|
| national_outages | national | preview:national; Viewer, Analyst, Admin | period |
| facility_outages | facility | preview:detail; Analyst, Admin | period, facility |
| generator_outages | generator | preview:detail; Analyst, Admin | period, facility, generator |

Apply `require_dataset` or the same shared dataset policy before detailed capability checks can distinguish a hidden dataset from an unknown one. Unknown stored roles still fail closed. Generic transport failures may occur before authentication; once transport is accepted, authentication precedes resource-specific validation and cursor processing. Unauthorized requests perform no publication/artifact read, analytical rate debit, capacity reservation, staging or execution.

| Dataset | Exact column order |
|---|---|
| national_outages | period, capacity, outage, percentOutage |
| facility_outages | period, facility, facilityName, capacity, outage, percentOutage |
| generator_outages | period, facility, generator, facilityName, capacity, outage, percentOutage |

Column.type is date for period, string for IDs/name, decimal for measurements. Only facilityName and percentOutage are nullable. Units are MW for capacity/outage, percent for percentOutage, and null otherwise. Each Column contains exactly name, type, nullable and unit. Source percentOutage remains distinct from the calculated offline-share metric.

### D01 — Accepted strict request interpretation

Decode URL parameters once through the bounded HTTP layer. Inspect all occurrences before constructing a scalar model; never silently choose the first/last duplicate. Unknown names, any duplicate (even equal values), empty values and a nonempty GET body produce 422 invalid_request. Parameter names and dataset names are case-sensitive. Path aliases such as national are not public dataset names.

| Parameter | Lexical shape and primitive validation | Semantic use |
|---|---|---|
| start, end | Exactly YYYY-MM-DD, valid Gregorian date; no datetime, surrounding spaces or alternate date notation. | Inclusive range. Each absent bound uses its respective publication-based default. |
| facility, generator | String of 1–128 characters; not empty or entirely whitespace. Preserve all supplied characters after one URL decode. | Exact equality with source ID; no trim/case-fold/numeric conversion. A valid but unknown ID yields no observations. |
| limit | ASCII digits matching [1-9][0-9]* and numeric value ≤ 1000. No sign, leading zero, whitespace, decimal/exponent notation or boolean text. | Default 100 when absent. |
| cursor | Nonempty, non-whitespace string, at most 4096 characters. | Authenticate/decode separately; malformed encoding/signature is invalid_cursor, not a usable position. |

Primitive-validation failures return 422 invalid_request before the rate debit. After those checks, unsupported combinations also return invalid_request: any facility/generator on national; generator on facility data; generator without an explicit facility; start after end; more than 366 inclusive dates. Their rate behavior follows D02. Percent escapes/plus characters follow the HTTP query encoding once; clients encode a literal plus as %2B. Do not interpret an ID again as URL syntax, SQL or a wildcard pattern.

For a publication whose latest observation is 2026-10-02, defaults are start=2026-09-03 and end=2026-10-02. Supplying only start=2026-09-20 resolves end to October 2; supplying only end=2026-09-10 resolves start to September 3. Supplying only end=2026-09-01 is invalid after defaults because it reverses the range. The inclusive leap-year range 2024-01-01 through 2024-12-31 is valid (366 dates); extending it through 2025-01-01 is invalid (367).

Explicit valid ranges may extend outside publication coverage; preserve the requested resolved range and return only matching published observations. Do not clamp the response range or infer zero outside coverage. An unknown entity is not a request for live discovery or a fallback to an unfiltered dataset.

### D02 — Accepted preview rate debit and deterministic validation order

Use the existing shared rolling window: at trusted time T, at most 30 counted requests for the authenticated user in (T − 60 seconds, T], across processes and analytical endpoints. One accepted rate debit persists if later work fails. A denied rate attempt does not append another debit. Internal retries do not add client requests. Preview does not alter SQL's already accepted counting rule.

| Order | Check/action | Counted? |
|---|---|---|
| 1 | Existing transport bounds, session/active account/role, known permitted dataset. | No debit for rejection. |
| 2 | Known unique parameter names, empty body, primitive D01 shapes/lengths/values. | No debit for rejection. |
| 3 | Atomically attempt one shared rate debit. | Yes if admitted; no new debit if denied with 429. |
| 4 | Dataset/filter combinations, explicit cross-field ranges where both dates exist; authenticate cursor format, purpose, schema and full key. | Debit retained on semantic invalid_request or invalid_cursor. |
| 5 | Read consistent active-publication metadata. For a valid cursor, compare its publication ID before resolving default-dependent matching. | Debit retained on data_unavailable, publication_changed or dependency failure. |
| 6 | Resolve omitted bounds, validate final range, compare effective request tuple with cursor; bind permitted published artifacts/diagnostics. | Debit retained on invalid_request, invalid_cursor or dependency failure. |
| 7 | Reserve shared capacity, start staging/execution deadline, stage, execute and collect bounded output. | Debit retained on busy/timeout/other failure; no new debit for retries. |

No file download or container launch occurs before these validation/admission checks. Rate storage and capacity storage failure both fail closed. No-publication and busy responses do not refund an admitted request. Polling unrelated status endpoints is not a preview page and does not use this debit. Exact transaction layout and locking remain design details; there must be no long-held database transaction while the client/runtime is working.

### D03 — Accepted cursor continuation and lifecycle

The authenticated payload binds a preview-specific purpose/version, canonical public dataset, resolved start/end, facility or null, generator or null, effective page size, publication event ID and the complete last returned daily key. Values use their strict typed representation. Bind absent optional entity filters as null, not empty strings. The public cursor remains an opaque string; encoding, signature primitive and bounded decoding are design choices. Authentication must cover the entire payload.

Every page repeats the same effective request settings. The client may repeat the original omitted bounds/default limit, or supply their equivalent resolved values. Both normalize identically while the publication is unchanged. A cursor alone does not carry forward an omitted facility/generator or a nondefault limit; omitting one changes the request and yields invalid_cursor (unless earlier request-combination checks already make it invalid_request). Query-parameter order has no meaning.

After verifying signature/payload structure, read the current active pointer. If it differs from the cursor's publication event ID, return 409 publication_changed, including when the valid pointer is now empty. If the pointer/state itself is missing or inconsistent, return 503 dependency_unavailable instead. Only then resolve default-dependent bounds and compare the effective request tuple. A valid cursor with different effective settings returns 422 invalid_cursor. A failed/newer refresh with the same active publication does not invalidate the cursor.

Reject a wrong-purpose token, malformed key, invalid date/ID in the key, dataset/key arity mismatch, key outside the cursor range or inconsistent entity key as invalid_cursor. Never deserialize arbitrary objects, trust a payload before authentication, echo its decoded fields, or read data to rescue an invalid cursor. Overlength input fails primitive validation before decoding. A valid signed key cannot expand authorization even when copied between accounts: the receiving account must independently have current access.

Accepted lifetime: no elapsed-time-only expiration while the same publication and signing key remain valid. Application restart preserves the configured key. Key retirement/rotation may invalidate old tokens with invalid_cursor and requires page-one restart; never fall back to an unsigned cursor. Key configuration and rotation procedure are design tasks. No endpoint can work with an absent/unavailable signing key by disabling authentication; fail safely. Cursor material itself is not logged. Secrets are never stored in the repository or sent to clients.

### Page mechanics and response invariants

A detailed dataset continues by lexicographic full key. For last key (p, f, g), select period > p OR (period = p AND facility > f) OR (period = p AND facility = f AND generator > g), in addition to all original filters. These are typed expressions, not concatenated SQL. Facility uses the first two key fields; national uses period alone. Fixed binary string comparison orders IDs such as 01, 1, 10, 2 by bytes rather than numeric magnitude. Test source case and Unicode handling against the chosen engine configuration; do not inherit locale-dependent behavior.

Apply filters and continuation, order by the full key, and collect at most limit + 1 result rows. The engine may scan more input rows; resource limits still apply. Return the first limit rows. When a lookahead exists, sign the last returned full key. If no lookahead exists, next_cursor is null, including when the page contains exactly limit rows. Reusing a cursor with unchanged publication/settings returns the same page; it does not consume or advance server-side state.

Immutable published keys make valid continuation deterministic. A cursor is emitted only after observing a later row. An empty continuation under the same immutable publication therefore signals inconsistent artifact/operation state and fails with dependency_unavailable; it must not claim no observations. Empty first-page results with valid artifacts and no matching observations return not_reported. Partial storage failures or an absent expected dataset are never successful empty results.

| PreviewResponse field | Required result |
|---|---|
| publication | Exactly publication_event_id, version_id, published_at, coverage_start, coverage_end, latest_observation_date from the pinned state. UUID IDs; YYYY-MM-DD dates; UTC timestamp ending Z. Never null on success. |
| dataset_key | The exact requested permitted public dataset. |
| range | Exactly resolved inclusive start and end, unchanged by rows missing within/outside coverage. |
| columns | Exactly the dataset's ordered canonical Column objects (4, 6 or 7). |
| rows | Array of arrays with one cell per column; at most limit and 1000 rows. Dates/IDs/text/decimals are strings, optional missing values null. No binary float or nested cell. |
| returned_rows | JSON integer equal to len(rows). |
| next_cursor | Null or authenticated opaque string ≤ 4096 characters; emitted only with an observed next row. |
| reason | not_reported for successful empty first-page matches; null for nonempty success. |
| diagnostics | Array of at most 32 permitted pinned Diagnostic objects. Empty is valid only when trusted provenance establishes no applicable diagnostic. |

Diagnostics retain exactly code, severity, scope, message, affected_count with the canonical type/bounds. Viewer never receives facility/generator/all-scope details or counts that reveal hidden data; only national-safe diagnostics may be returned. All roles receive diagnostics applicable to the authorized requested dataset. Do not load hidden analytical files to calculate diagnostics for a national request. Exact storage/projection and bounded diagnostic selection must be designed against the frozen published evidence; this specification does not create new diagnostic codes.

No total_rows, offset, arbitrary sort, calculated metric, SQL truncated flag or execution_ms field is added. Preserve source signs and optional nulls. Decimal strings must represent stored values exactly; fixed six-place or equivalent exact decimal formatting must follow the shared serializer selected in design, with no exponent/rounding surprises for consumers. Public schema mismatch, malformed output, wrong request/publication binding or forbidden nested data causes a safe error before any successful response is sent.

### Failure, isolation and lifecycle contract

| Condition | HTTP / code and effect |
|---|---|
| Missing/invalid/expired/revoked session; inactive account | Existing 401 contract; no analytical work. Unknown role fails closed through the existing role policy. |
| Unknown or unauthorized dataset | 404 dataset_not_found; identical safe shape with no lookup hints. |
| Unsupported/duplicate/invalid query parameter, filter combination, range or GET body | 422 invalid_request. Existing transport overflow retains its 413 response. |
| Bad authenticated cursor, mismatched settings/purpose/key or retired signing key | 422 invalid_cursor. Never use an unverified cursor to select files. |
| No publication on first page | 409 data_unavailable. Stored/unpublished candidates do not qualify. |
| Valid cursor publication no longer active | 409 publication_changed; safe restart guidance, no replacement data inside an error. |
| Shared rate/capacity exhausted | 429 rate_limited with positive bounded Retry-After; no queue or unreserved execution. |
| Analytical deadline | 504 query_timeout, no partial success; termination and capacity cleanup remain required. |
| Container memory/output resource bound | 503 query_resource_limit, no partial success; same termination/cleanup obligations. |
| Broken publication/artifact integrity, unavailable admission/storage, invalid runtime provenance | 503 dependency_unavailable; auth-storage failure retains 503 auth_unavailable. Unexpected internal defects retain safe 500 internal_error. |

Timeout spans trusted downloads, verification, retries, container startup and reads/execution/output collection. Maximum response is 5,242,880 encoded bytes for the complete JSON envelope, not rows alone. Memory is 1,073,741,824 bytes per query container. Relevant temporary external failures allow three total attempts with one- and three-second waits inside the existing 30-second deadline; no retries for permission/validation failures. Bounds are server-controlled and provisional under A19, not targets measured by this document.

The shared supervisor owns Docker control, staging, deadlines, stop confirmation and cleanup. The query container has no network, credentials, S3/PostgreSQL access, Docker socket or unrelated data mounts; only the authorized published Parquet mount is read-only. Typed filters reduce input risk but do not replace this boundary. No in-process engine fallback is allowed when Docker, admission or shared runner components are unavailable.

On timeout or client disconnect, HTTP cancellation alone cannot free capacity. Stop and confirm the actual execution, clean request resources and conditionally release only the matching reservation. Crash recovery fences stale owners and identifies the real container; an expired lease or lost database connection is not proof of termination. If cleanup/termination is uncertain, retain capacity and report a safe failure. Do not return success while execution is still running or output remains unverified. Preserve all published objects and retained evidence.

### Acceptance scenarios

Scenario labels are independent of SQL's A/B examples. None has run for this specification. O=offline; R=real database/HTTP/runtime; H=human operator. A scenario listing multiple categories requires each relevant form of evidence, not one interchangeable check.

| ID | Scenario and expected observation | Requirements | Evidence |
|---|---|---|---|
| S01 | All three roles preview national; Analyst/Admin preview facility and generator. Exact dataset/schema/rows and role-safe diagnostics. | R01–R03, R13, R16 | O/R/H |
| S02 | Viewer asks for either hidden dataset; authorized caller asks for unknown/short alias. Same safe 404; guards observe zero analytical reads/admission. | R02–R03, R22 | O/R/H |
| S03 | Missing/expired/revoked session, inactive account, unknown role and role downgrade before continuation. No retained cursor authority. | R02–R03, R09 | O/R |
| S04 | Unknown/duplicate parameters (same and different values), GET body, client SQL/version/path/role fields. 422 with no staging. | R01, R04 | O/R |
| S05 | Blank/space-only values; malformed dates; limits 0/1001/01/+1/1.0/1e2; overlength IDs/cursor. Strict shape rejection with no rate debit. | R04, R17 | O/R |
| S06 | Publication latest=2026-10-02: default and one-bound examples above resolve exactly, including reversed default-bound failure. | R05 | O/R |
| S07 | 366 inclusive leap-year dates accepted; 367/reversed rejected. Explicit range outside coverage is unchanged and contains only matching observations. | R05, R15 | O/R |
| S08 | Facility filter on national; generator on facility; generator without facility. 422 before download. | R06, R17 | O/R |
| S09 | Same generator ID in two facilities; leading-zero/mixed-case/Unicode IDs, quotes and wildcard-like characters. Exact typed matching; no cross-facility mixing or expression execution. | R06, R12, R14 | O/R |
| S10 | Zero, one, limit−1, limit, limit+1 and many matches at limits 1/100/1000. Exact row count and cursor boundary. | R07–R08, R15 | O/R/H |
| S11 | Several facilities/generators share one date and span pages. Concatenated pages equal the complete filtered full-key ordered fixture, without gaps/duplicates. | R07–R09 | O/R/H |
| S12 | Replay the same valid cursor with equivalent effective filters/defaults and reordered query parameters. Identical page and publication. | R08–R10 | O/R |
| S13 | Alter cursor bytes; wrong purpose/dataset/key shape/type; invalid bounds/entity relation; change dates/filter/limit or omit prior nondefault settings. Safe invalid_cursor or earlier declared shape/combination error; zero downloads. | R04, R09 | O/R |
| S14 | Valid token copied to a permitted account succeeds only with that account's own current authority/rate limit; copied detail token gives Viewer safe 404. | R02–R03, R09, R17 | O/R |
| S15 | Publication changes after request pin. Rows, diagnostics, mounted files and returned metadata remain on the original publication. | R10, R16, R19 | R |
| S16 | Active publication changes between pages; valid pointer becomes empty; new failed refresh leaves pointer unchanged. Respect D03's changed/unchanged outcomes and default-resolution order. | R09–R11 | O/R/H |
| S17 | First-page empty pointer versus candidate-only state versus missing/broken pointer/join. Distinguish data_unavailable from dependency failure. | R10–R11 | O/R |
| S18 | Unknown ID/no matching date, optional null name/percentage, negative outage and exact high-precision values. No zero fill, percentage replacement or float loss. | R13–R15 | O/R/H |
| S19 | Wrong row width/type/nullability, wrong publication/request, duplicate/out-of-order keys or oversized complete output. Reject without partial success. | R07, R13–R14, R20, R22 | O/R |
| S20 | Valid continuation unexpectedly has no rows under the same immutable artifacts. Safe dependency failure, not not_reported. | R08–R10, R15 | O/R |
| S21 | Viewer diagnostics/errors/logs seeded with detail canaries; national request mounts only national data. No detail values, counts, schemas, files or secrets escape. | R03, R16, R19, R22 | O/R |
| S22 | Shared 30-request rolling window with mixed SQL/preview across processes; boundary at T−60, retry and denial cases. Match D02's debit table; login/polling remain separate. | R17 | O/R |
| S23 | Mixed SQL/preview reaches two active per user/four total; next request gets 429. Admission outage never starts work. | R18 | R |
| S24 | Checksum/path/manifest mismatch, inaccessible published file or partial read. No unverified execution, candidate/EIA fallback or empty success. | R10–R11, R19, R22 | O/R |
| S25 | Real query container attempts network/external file/application state/unmounted hidden data and write access. All denied; no credentials or Docker control available. | R19, R23 | R |
| S26 | Slow download/start/read/query, memory pressure and response-size failure. Bound elapsed behavior, reject partial output, observe actual termination before slot release. | R20–R21 | R |
| S27 | Client disconnect, supervisor crash, expired lease, unknown termination, ownership takeover and stale release. Retain capacity until correctly owned stop/cleanup proof. | R18, R21 | R |
| S28 | Temporary external failures at attempts 1/2/3; one/three-second waits fit remaining budget. Denied/invalid/checksum failures do not retry. | R19–R21 | O/R |
| S29 | Restart keeps configured cursor key/publication; prior cursor still works. Retired key gives invalid_cursor; unavailable signing configuration fails closed. | R09, R22 | O/R |
| S30 | Actual HTTP serialized success/problem responses match OpenAPI, exact counts/column order, headers and no unapproved fields; existing auth/catalog/SQL regressions remain passing. | R01, R13, R22–R24 | O/R |
| S31 | Retained Viewer/Analyst/Admin privately authenticate and exercise known published rows, a next page, a literal entity filter and Viewer detail denial; record safe results. | R24 | H |

### Integration, evidence and remaining design work

The proposal's absent-module inventory described its inspection time. During this specification inspection, concurrent SQL work had added `queries/repository.py`, `0003_query_admission.py` and changes to publication pinning. Their presence is not runtime acceptance and this workstream neither edits nor reviews them as completed delivery. Reinspect their final interfaces before design. Reuse the shared runner, admission and serialization path once authorized and verified; never install a duplicate preview executor or parallel rate/capacity tables.

**Confirmed saved-evidence baseline:** the [October 1–2 live preparation record](../../evidence/live-preparation/2026-10-04-october-1-2/README.md) includes 16 required passes, 23 completed/frozen diagnostics, zero review warnings and recorded independent verification of 50 objects. It explicitly remains unpublished. Reuse existing frozen evidence; verify its connection to publication and preview. The existence of saved evidence is established; active-publication binding and preview runtime acceptance remain separate checks.

Design must choose bounded cursor encoding/authentication and deployment key handling, strict transport parsing, typed preview runtime messages/expressions, shared artifact/diagnostic resolution and supervision interfaces. It must prove the selected DataFusion ordering/decimal semantics with the pinned libraries. Any new migration, dependency, shared contract change or security setting needs its concrete justification and the applicable authorization before execution. No library defaults are silently accepted here.

| Evidence category | Required scope | Current preview result |
|---|---|---|
| Offline | Synthetic filter/cursor/page/serializer tests, malformed-state/error guards and deterministic scenarios. | Not implemented or run for this specification. |
| Real database/HTTP/runtime | Current-role and publication reads/races, shared cross-process admission, real DataFusion/Parquet, Docker isolation/deadline/cleanup. Record each component separately. | Pending. Catalog/API health results do not prove row execution. |
| Local operator | Alayala's retained accounts against a known valid publication, private credentials, all roles and page/filter behavior. | Pending. Existing catalog operator run had no publication and is not preview evidence. |

Maintain data evidence — ongoing. Synthetic fixtures do not establish source completeness or live EIA/S3 success. Real operator publication setup needs separate authorization; do not publish retained candidate data simply to make S31 pass. Preview frontend rendering/navigation, choice-list endpoints, dashboard aggregates, export and user SQL policy remain outside this slice.

## Review gate

Done: approved preview specification and D01–D03, recorded under A16/A19, with 24 requirements and 31 traceable scenarios.
Pending: review of the drafted design/tasks and implementation authorization. Runtime results remain unverified.
Blocker: no specification drafting blocker. Endpoint delivery depends on verified shared execution and published artifact availability.
Next: [ME] review design/tasks and authorize a bounded implementation stage.
