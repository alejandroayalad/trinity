# Design: Filtered, paginated dataset previews

Date: 2026-10-04
Status: Design drafted under alayala's request to continue after specification approval. Implementation and runtime actions are not authorized by this document.
Branch/inspection: `feat/catalog-permissions`, HEAD `e851e28`; the SQL workstream is changing shared files concurrently.
Basis: [approved specification](spec.md), [tasks](tasks.md), A9/A15/A16/A19–A21 in [DECISIONS.md](../../DECISIONS.md), [backend architecture](../../docs/backend.md), [API](../../docs/api-contract.md), [security](../../docs/security-contract.md) and [schema](../../docs/schema.md).
Evidence: [design/tasks session](../../ai/sessions/2026-10-04-dataset-preview-design-tasks.md).

## Human

### What will change

Add the existing preview API contract to the shared query feature. The API checks the caller, filters and page cursor. Trusted code pins a publication and stages only its permitted dataset. The same isolated runner used by SQL executes a typed preview operation. The API validates the result, creates a next cursor when necessary and returns only after execution and cleanup are confirmed.

The cursor is a signed bookmark, not permission. It remembers the full last row key, filters, page size and publication. Restarting the API keeps the configured signing key. Publishing a new version requires starting pagination again. Every page checks the current account and role.

Example: facility rows for one date can span pages. Saving only the date would skip the remaining facilities. The cursor instead stores `(period, facility)` and continues strictly after that pair. Generator pages use `(period, facility, generator)`. The cursor stores the last returned key, not the extra row used to detect another page.

Failure: Viewer sends a valid facility cursor copied from Analyst. The API returns the same `404 dataset_not_found` as an unknown dataset before publication reads, rate debit, files or containers. If an allowed preview times out, the supervisor confirms execution stopped before returning its capacity to the shared pool.

### Delivery boundary

Reuse authentication, schema metadata, publication pinning, rate/capacity tables, staging, Docker supervision and cleanup. Extend their operation and response handling for preview. Keep user SQL parsing and its accepted grammar unchanged. No new production package is proposed; cursor authentication uses Python's standard library.

There are two integration dependencies: the shared runner must pass its own real runtime checks, and preview must read complete frozen diagnostic evidence for the pinned publication. The current SQL response model permits only empty diagnostics; that cannot substitute for preview's evidence requirement. Missing evidence fails closed and stays a delivery blocker, rather than being hidden behind `diagnostics=[]`.

## LLM

### Inspected baseline, not a completion claim

| Component | Observed code and required integration |
|---|---|
| `QueryService.prepare` in queries/service.py | Authenticates, debits `reserve_rate`, validates SQL, rechecks identity, pins publication and reserves capacity. Preview needs its own preparation order from D02; never call it with generated SQL. |
| `queries/repository.py` and migration 0003 | Supply shared rate/capacity lifecycle state and ownership fencing. Reuse these final interfaces/tables; no per-preview counter or reservation store. Presence is not proof that migrations/runtime checks passed. |
| `read_pinned_publication` | Supplies public metadata, manifest hash and contract version from one snapshot. Preview needs the same binding plus complete frozen diagnostic provenance; public catalog metadata alone is insufficient. |
| `stage_query` / PublishedReader | Select files by an internal dataset key, verify immutable manifest/checksums/schema, and stage a request. The request envelope is currently SQL-policy-specific. Generalize serialization while preserving the file-authority checks. |
| `QueryExecution.execute` / runtime entrypoint | Bind request/version/policy digest, supervise termination/cleanup and build QueryResponse. Add typed operation dispatch and a PreviewResponse builder; do not duplicate lifecycle machinery. |
| `ValidatedQuery` / runtime engine | SQL message retains original SQL and policy result; engine revalidates it. Preview requires a separate closed typed operation and must not pass through that SQL policy path. |
| `queries/schemas.py` | QueryResponse has SQL-only fields and an empty-only diagnostics list. Keep its wire behavior while adding the separate closed preview response. |

Source was inspected during active SQL edits. Before implementing, record the final agreed shared interfaces and current passing evidence. Do not overwrite work in the other terminal based on this snapshot. The source examples above identify integration points, not review findings or authorization to refactor SQL now.

### Component responsibilities

| File/location | Planned responsibility |
|---|---|
| `queries/router.py` | Add GET preview using raw Request query pairs and the existing bearer dependency; preserve duplicate detection and disconnect propagation. Reuse the existing cancellation/supervision pattern. |
| `queries/service.py` | Add PreviewService with short preparation transactions and the exact D02 order. Share admission and supervision, not SQL-specific policy. |
| `queries/preview.py` — new | Pure primitive/semantic filter validation, publication-based date defaults, canonical request tuple and full-key continuation checks. No database, storage or engine authority. |
| `queries/cursors.py` — new | Bounded authenticated cursor encoding/decoding and exact binding checks. Trusted API only; key material never enters query messages or runtime. |
| `queries/schemas.py` | Add closed PreviewResponse, range and diagnostic models; reuse canonical Column metadata and exact cell validation where compatible. |
| `contracts/queries.py` | Add versioned PreviewOperation and tagged request/result envelopes. Preserve ValidatedQuery and independent SQL revalidation. |
| `queries/runtime/preview.py` — new | Independently validate the typed operation and build DataFusion expressions for filtering, full-key order and lookahead. Reuse the restricted context and exact scalar serializer from engine.py. |
| publication repository / query staging | Pin frozen provenance in PostgreSQL; verify the manifest and stage only the selected dataset. Share existing code and record any necessary A9 persistence migration separately. |
| query client / runtime entrypoint | Dispatch trusted operation kinds and validate kind-specific results while using one container/admission/cleanup path. |

No frontend, entity choices, dashboard calculations, refresh/publication writer or SQL grammar change is introduced. Function/module names above are design targets; rebase them onto the agreed final shared interfaces before coding.

### Request flow and transaction boundaries

| Phase | Work and ordering | Database/file boundary |
|---|---|---|
| A — identity | Existing bounded transport checks; resolve current session/active role; authorize public dataset through canonical mapping and the applicable preview capability. | Short read-only transaction. Denials do not load cursor configuration or protected publication state. |
| B — primitive shape | Inspect all query pairs; reject unknown/duplicate keys, nonempty GET body and D01 lexical/range-of-value errors. Preserve exact decoded ID text. | Pure bounded work; no analytical rate debit. |
| C — rate | Commit one shared trusted-user `reserve_rate` attempt. Return 429 if denied. | Separate short write transaction; later failure does not roll it back. |
| D — semantic input/cursor | Validate dataset/filter combinations and explicit range when available. Authenticate/decode cursor and validate its purpose/key schema. | No file access; count retained on rejection. |
| E — authority/publication | Recheck the same session/user and current dataset authority; read the active publication in one snapshot. Compare cursor publication before default-dependent checks; resolve defaults and effective request equality, then pin artifact/diagnostic provenance. | Short read-only snapshot; a role downgrade here still denies before staging. Accepted work may finish after a later role change under A19. |
| F — admission | Resolve required trusted runner configuration; start one 30-second monotonic budget immediately before reserving shared capacity. Capture its database deadline once. | Short write transaction; its small admission time also consumes that budget. No transaction remains open through I/O. |
| G — execution | Stage/verify selected data, launch the shared isolated container, receive and validate bounded output, construct/sign a next cursor and build the exact response. | Deadline never resets. All file reads/startup/retries/output assembly are inside it. |
| H — finish | Confirm exit or terminate, clean request resources, conditionally release owned capacity, then return the validated response. | Cleanup can continue after analytical timeout; bounded cleanup/recovery must not claim capacity is free prematurely. |

Use bounded preflight/authentication deadlines before F; do not reuse an expired authentication snapshot during staging. Preserve the SQL service's timing/behavior; if a shared helper must change, include SQL regression proof in the coordinated change. Configuration failures produce safe dependency errors and retain any already-committed rate debit.

Normalize only types and omitted defaults. Dates use exact ISO date text and real calendar parsing; limit is canonical ASCII integer 1–1000; entity IDs retain case, spaces and leading zeros after one URL decode. A specific generator requires facility; unfiltered generator browsing remains allowed for Analyst/Admin. Enforce the approved 366-inclusive-date boundary. Query values are never SQL, paths or a request to discover an unknown entity.

### Cursor format and key lifecycle

Use a compact authenticated token `pv1.<kid>.<payload>.<tag>` with unpadded base64url payload/tag. HMAC-SHA-256 authenticates the ASCII prefix/version/key ID plus the encoded payload; compare the full 32-byte MAC in constant time. The allowed algorithm is fixed by the server, never supplied by the client. Use `hmac`, `hashlib`, `base64` and `json`; no JWT or encryption dependency. Base64 is not encryption: the payload contains only already-authorized request/position/publication values and confers no access.

Canonical payload has exactly: version=1, purpose=dataset-preview, public dataset, publication_event_id, start, end, nullable facility/generator, integer limit, and after (the complete daily-key array). Use compact sorted-key UTF-8 JSON with ensure_ascii=False and allow_nan=False. Reject duplicate/extra fields and malformed Unicode; require byte-for-byte canonical re-encoding after authentication. No timestamps, user roles, file paths, arbitrary expressions or secret values appear in the payload. Cross-account use succeeds only with independent current permission and identical settings.

Bound the complete token to 4096 characters, payload bytes to 3000 and key ID to 1–32 ASCII letters/digits/underscore/hyphen. Restrict token segments to the unpadded base64url alphabet, exactly four segments and a 32-byte decoded tag. Bound lengths before allocation/decoding. Use a shallow exact schema; deeply nested/oversized data is invalid_cursor. Reject invalid Unicode scalar strings before canonical encoding. Authenticate before trusting payload fields or publication selection. Unknown/retired key IDs return invalid_cursor when configuration is otherwise valid; missing/broken server configuration returns dependency_unavailable.

Design configuration: `TRINITY_PREVIEW_CURSOR_ACTIVE_KEY_ID` and secret `TRINITY_PREVIEW_CURSOR_KEYS_JSON` mapping allowed key IDs to base64url-encoded, independently generated 32-byte random keys. Parse with bounded size/count (at most four verification keys), reject duplicate IDs and invalid key lengths, and hold values with secret-safe representations. Never generate a new signing key on API startup. No real key is written to examples, logs, evidence or Git. Docker deployment must explicitly supply the configured secret to trusted API code only; runtime images/containers receive none. Actual secret entry remains an operator action during implementation setup.

Normal restart retains configured keys. During rotation, configure old/new verification keys on all API replicas, then switch the active signing ID consistently. Retain old keys while existing pages should remain usable; retiring a key deliberately invalidates its cursors with 422 invalid_cursor. No time-only expiry or mutable cursor row is added. Key-loss recovery requires new configuration and page-one restart, never an unsigned fallback. The cursor is signed before final response-size validation; sign/config errors follow the same cleanup path as execution errors.

For a valid cursor, compare its publication with the freshly read pointer before resolving default-dependent request matching. A changed/empty valid pointer returns publication_changed; broken state returns dependency_unavailable. Repeating original omitted defaults and explicitly providing their equivalent resolved values are both valid while publication is unchanged. Effective ID filters and nondefault limit must be repeated. Copying a cursor never expands role or dataset access.

### Typed runtime operation and result

Add a frozen PreviewOperation with exact protocol version/kind, internal dataset key, publication event ID, version ID, resolved start/end, nullable facility/generator, page_size and optional after key. The trusted API constructs it only after authorization and cursor checks. It contains no cursor, signing key, SQL string or arbitrary filename. Its canonical bytes produce a SHA-256 operation digest covering every field.

Integrate a tagged, versioned common envelope containing request_id, version_id, operation_kind, operation and operation_digest. Coordinate producer, staging writer, runtime entrypoint and result reader together; pin the matching runtime image digest. Existing ValidatedQuery remains the SQL payload with its original independent policy validation. Do not infer kinds from payload fields, try SQL after a preview decoding failure, or silently tolerate mixed protocol versions. Unknown kind/version fails closed. Existing SQL API request/response fields and accepted grammar do not change.

The runtime checks canonical bounded envelope, IDs, digest and kind; the preview branch independently validates dataset, columns, date range, entity combinations, limit and key types/bounds. It does not import cursor/configuration, auth, storage or database clients. The supervisor chooses files; the operation cannot supply new paths. Register only canonical schema/table for the supplied dataset under the fixed authorized mount.

DataFusion flow is table → typed date/exact-ID predicates → optional full-key greater-than predicate → fixed ascending complete-key sort → limit(page_size + 1) → bounded stream collection. Use Arrow date32 scalars and string literals, not SQL interpolation. Internal keys remain present because preview selects every canonical column. Extract only enough result rows for lookahead; stop iteration without accumulating full tables. Match binary string order in cursor predicates and sorting; compatibility tests must prove this for ASCII, case, leading zeros and Unicode with the pinned engine.

Return a closed PreviewBatch with canonical columns, at most page_size returned rows and has_more boolean. The runtime observes the extra row but does not return it or mint a cursor. Echo request/version/kind/digest bindings in the shared envelope. API validates schema, cell types/nullability, exact decimals, order/unique full keys, date/entity/after predicates, returned count and `has_more ⇒ returned_count=page_size`. A non-null after with empty rows is the spec's dependency failure. Build the next cursor from the last accepted returned key only. A malformed engine reply is never transformed into a successful empty page.

Share the restricted DataFusion context and exact scalar serializer with SQL; do not call `execute_local(ValidatedQuery)` for preview. Serialize stored decimal values as fixed six-place strings without rounding; dates as YYYY-MM-DD and text/null unchanged. Verify encoded byte limits on the full UTF-8 public JSON envelope, including metadata, diagnostics and signed cursor. An internal stream budget may reserve bounded envelope space, but the final complete-response check is authoritative. No HTTP success headers or partial rows are sent before validation and cleanup.

### Publication and diagnostic provenance

Extend the trusted preview pinning read, keeping existing catalog behavior unchanged. Pin publication event/version, immutable manifest hash/contract, successful validation step and diagnostics frozen identity from one snapshot. Validate artifact schema/identity through the shared manifest reader. No arbitrary candidate or historical lookup is exposed. Reauthorize before pinning and keep the snapshot closed during downloads.

The canonical persistence source is A9 `validation_results` bound to version, successful step, manifest hash and checkset, together with data_versions' frozen diagnostic state/digest. Use an existing implementation if the refresh/publication workstream supplies it; otherwise the exact required read model/migration is a coordinated prerequisite, not an invented empty adapter. The inspected auth/app-entry/query-admission migrations do not create validation_results. A new migration number must be allocated against current HEAD; do not hardcode a number that concurrent work can take. No migration is executed under this design request.

Require complete applicable diagnostic evaluation and the frozen binding; missing/error/incomplete evidence is dependency_unavailable. A completed evaluation with no observed applicable condition legitimately yields []. Do not derive absence from missing rows or rely on SQL's current empty-only diagnostics field. Do not compute quality notes by downloading another dataset or mutate publication state during preview. A synthetic test fixture may seed complete evidence only in its disposable test database.

Project permitted public summaries from the frozen Dxx registry: canonical code/severity/scope/count and bounded trusted message templates, never raw details. Diagnostic D01–D09 names are unrelated to this slice's decision labels D01–D03. Suppress Admin-only D09 and all hidden/all-scope detail for Viewer. Select only the requested dataset's permitted scope, aggregate canonical summaries by code/scope, sort stably, and enforce the existing 32-entry bound without silently dropping an overflow. Counts describe the frozen publication/dataset summary, not newly invented per-page counts; message wording must make that scope clear when relevant. No extra response field is added.

Before implementation of this reader, verify the authoritative producer's complete evaluation/summary representation against A9, including known zero/not-applicable cases and the exact frozen digest. If that producer does not yet exist, pure request/cursor/runtime tests can progress, but real preview delivery remains blocked at the provenance gate. Do not broaden this slice into implementing refresh/publication commands or activating a candidate.

### Shared isolation, admission and cleanup

Use the existing PostgreSQL shared-user counter and deployment capacity. Count each preview page per D02, including later filter/cursor/publication failures. Reuse ownership/generation checks, stable request/container identity and crash recovery. A failed preview cannot release a SQL reservation. A slow SQL request can occupy the same user's shared slots; the preview must see the busy state.

The trusted stager downloads only the selected dataset from the pinned verified manifest. Preserve bounded manifest/object/file-count/total-stage limits in the shared runner; classify missing required dataset/provenance as dependency failure, distinct from actual resource excess. Refactor request serialization without relaxing symlink/path/checksum/schema checks. An existing S3 reader is trusted staging infrastructure, never runtime configuration.

Run with the shared immutable query image, network disabled, authorized read-only data mount, no credentials/control sockets, non-root and the established restricted container configuration. Enforce 1 GiB memory, 5 MiB full response and the 30-second analytical budget beginning before downloads. Keep the same three-attempt temporary-error retry schedule with one/three-second waits inside that budget. Provenance/validation/checksum and permission failures are not retried.

Propagate disconnect/cancellation into the same execution owner. Return no capacity until container termination and required cleanup are confirmed; normal HTTP completion, expiry and DB loss are insufficient. When Docker create/start outcome is ambiguous or cleanup fails, retain durable ownership and use the shared recovery path. Never delete published S3 objects during query cleanup. Measure stop/recovery latency separately from the analytical timeout; a quick timeout response is not proof that work stopped.

### Verification and delivery conditions

Map all acceptance scenarios through [tasks](tasks.md). Offline tests cover D01/D02 ordering with controlled adapters, MAC and payload boundaries, defaults, exact scalar output and keyset pagination. Real engine fixtures prove filtered rows and ordering; they do not prove container isolation. PostgreSQL/HTTP tests prove current-role and publication snapshots plus shared rate/capacity; real container tests prove file/network isolation and termination/cleanup. The retained-account operator run is a separate final evidence category.

Do not enable preview execution on synthetic adapters or missing provenance. Shared SQL runtime files/tests are present but were not executed or approved by this design turn. Coordinated integration must rerun relevant SQL regression checks and produce mixed-operation evidence. No new dependency, deployment, database mutation or user-visible behavior beyond the approved specification is authorized here.

Done: concrete preview integration, cursor and typed-operation design.
Pending: implementation authorization, shared-interface alignment, provenance availability and all preview runtime evidence.
Blocker: no design drafting blocker; complete frozen diagnostics and verified shared execution are delivery dependencies.
