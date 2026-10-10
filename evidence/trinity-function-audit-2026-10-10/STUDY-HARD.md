# Trinity study list — score 5 and 4 (production only)

Tests, tools, and migrations are excluded.
Score is review effort from length + cyclomatic complexity + nesting — not a defect count.

- **44** functions at score **5** (Very high)
- **56** functions at score **4** (High)
- For each: what it does, why it is hard to study, and metrics.

## Score 5 — Very high

### 1. `_Policy.scalar`

- **Score:** 5 · **CC:** 68 · **Nesting:** 4 · **LOC:** 110
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/runtime/sql_policy.py:164`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/runtime/sql_policy.py#L164-L273)
- **What it does:** Walks one SQL expression tree and decides if each node is an allowed scalar (columns, literals, ops, aggregates).
- **Why it is hard:** Huge branch table over SQLGlot node types; one wrong case changes what user SQL can do. (CC=68 (many branches), 110 lines)

### 2. `recorded`

- **Score:** 5 · **CC:** 61 · **Nesting:** 2 · **LOC:** 93
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/publication/checks.py:12`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/publication/checks.py#L12-L104)
- **What it does:** Rebuilds required/diagnostic check outcomes from immutable DB rows; no remote I/O.
- **Why it is hard:** Must mirror connector rules exactly without a second registry; many incomplete/mixed-proof cases. (CC=61 (many branches), 93 lines)

### 3. `verify_validation`

- **Score:** 5 · **CC:** 60 · **Nesting:** 3 · **LOC:** 95
- **Theme:** EIA connector / validate
- **Where:** [`backend/src/trinity/connector/validate.py:817`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/connector/validate.py#L817-L911)
- **What it does:** Rechecks a passing validation receipt and files before a later stage uses them.
- **Why it is hard:** Offline handoff guard: many ways data or evidence can change or go incomplete after success. (CC=60 (many branches), 95 lines)

### 4. `_Policy.normalize`

- **Score:** 5 · **CC:** 54 · **Nesting:** 5 · **LOC:** 95
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/runtime/sql_policy.py:275`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/runtime/sql_policy.py#L275-L369)
- **What it does:** Turns a validated SELECT into the closed column/alias list Trinity stores and executes.
- **Why it is hard:** Many projection/alias edge cases; output must stay exact for later cursors and schema checks. (CC=54 (many branches), nesting=5, 95 lines)

### 5. `_source_complete`

- **Score:** 5 · **CC:** 50 · **Nesting:** 3 · **LOC:** 85
- **Theme:** EIA connector / validate
- **Where:** [`backend/src/trinity/connector/validate.py:283`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/connector/validate.py#L283-L367)
- **What it does:** Decides if EIA retrieval finished (progress, stable totals, empty-page exhaustion).
- **Why it is hard:** Completion mixes attempt status, route, totals, and page exhaustion—easy to misread. (CC=50 (many branches), 85 lines)

### 6. `supervise`

- **Score:** 5 · **CC:** 44 · **Nesting:** 7 · **LOC:** 139
- **Theme:** EIA connector / validate
- **Where:** [`backend/src/trinity/connector/prepare.py:247`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/connector/prepare.py#L247-L385)
- **What it does:** Parents a prepare child with stage/overall deadlines and retained evidence.
- **Why it is hard:** Deep nested stage machine plus deadlines and fsync handoffs; wrong order breaks custody. (CC=44 (many branches), nesting=7, 139 lines)

### 7. `read_verified_diagnostics`

- **Score:** 5 · **CC:** 41 · **Nesting:** 2 · **LOC:** 115
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/publication/diagnostics.py:41`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/publication/diagnostics.py#L41-L155)
- **What it does:** Verifies bundle/member hashes and complete evaluations before keeping diagnostic notes.
- **Why it is hard:** Hash identity plus embedded summaries; must reject incomplete evaluations without remote repair. (CC=41 (many branches), 115 lines)

### 8. `NationalChart`

- **Score:** 5 · **CC:** 37 · **Nesting:** 3 · **LOC:** 142
- **Theme:** Frontend UI
- **Where:** [`frontend/src/pages/dashboard/NationalChart.tsx:26`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/frontend/src/pages/dashboard/NationalChart.tsx#L26-L167)
- **What it does:** Renders the national outage SVG chart, selection, and responsive width mapping.
- **Why it is hard:** Long UI function mixing layout math, selection state, and series rendering. (CC=37 (many branches), 142 lines)

### 9. `DashboardData`

- **Score:** 5 · **CC:** 36 · **Nesting:** 2 · **LOC:** 54
- **Theme:** Frontend UI
- **Where:** [`frontend/src/pages/dashboard/Dashboard.tsx:95`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/frontend/src/pages/dashboard/Dashboard.tsx#L95-L148)
- **What it does:** Composes dashboard chart/table view, day selection, and contribution panel wiring.
- **Why it is hard:** Many UI branches for role, view mode, selection, and updating states in one component. (CC=36 (many branches))

### 10. `_validate_page`

- **Score:** 5 · **CC:** 34 · **Nesting:** 4 · **LOC:** 79
- **Theme:** EIA connector / validate
- **Where:** [`backend/src/trinity/connector/client.py:174`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/connector/client.py#L174-L252)
- **What it does:** Validates one sanitized EIA JSON page into typed source rows and metadata.
- **Why it is hard:** Many shape/window/unit/key checks; API error vs client error boundaries matter. (CC=34 (many branches), 79 lines)

### 11. `_Policy.__init__`

- **Score:** 5 · **CC:** 34 · **Nesting:** 2 · **LOC:** 38
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/runtime/sql_policy.py:113`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/runtime/sql_policy.py#L113-L150)
- **What it does:** Tokenizes SQL and rejects disallowed shapes before deeper policy walks.
- **Why it is hard:** Dense early rejects (tokens, keywords, nesting flags); easy to miss which gate failed. (CC=34 (many branches))

### 12. `_bound_results`

- **Score:** 5 · **CC:** 34 · **Nesting:** 3 · **LOC:** 34
- **Theme:** EIA connector / validate
- **Where:** [`backend/src/trinity/connector/validate.py:142`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/connector/validate.py#L142-L175)
- **What it does:** Checks check-result list identity (count, types, version/attempt/manifest binding) before status.
- **Why it is hard:** Strict structural predicates; failure modes look similar until you compare every field. (CC=34 (many branches))

### 13. `SafeTransport.__call__`

- **Score:** 5 · **CC:** 33 · **Nesting:** 2 · **LOC:** 71
- **Theme:** Errors / transport
- **Where:** [`backend/src/trinity/errors.py:72`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/errors.py#L72-L142)
- **What it does:** ASGI middleware that wraps HTTP with request IDs and safe error responses.
- **Why it is hard:** Must handle send-already-started cases without leaking internals. (CC=33 (many branches), 71 lines)

### 14. `read_candidate`

- **Score:** 5 · **CC:** 33 · **Nesting:** 4 · **LOC:** 62
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/refresh/candidates.py:114`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/refresh/candidates.py#L114-L175)
- **What it does:** Authorizes, then reads candidate evidence and actions in one DB snapshot.
- **Why it is hard:** Auth-first then multi-table snapshot; eligibility and evidence must stay consistent. (CC=33 (many branches))

### 15. `_diagnostic`

- **Score:** 5 · **CC:** 31 · **Nesting:** 10 · **LOC:** 80
- **Theme:** EIA connector / validate
- **Where:** [`backend/src/trinity/connector/validate.py:458`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/connector/validate.py#L458-L537)
- **What it does:** Evaluates one diagnostic code/scope and keeps exact observations / not-applicable reasons.
- **Why it is hard:** Deep nesting across diagnostic codes; each code has different applicability rules. (CC=31 (many branches), nesting=10, 80 lines)

### 16. `Docker._verify_isolation`

- **Score:** 5 · **CC:** 31 · **Nesting:** 1 · **LOC:** 22
- **Theme:** Storage / adapters
- **Where:** [`backend/src/trinity/adapters/docker.py:107`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/adapters/docker.py#L107-L128)
- **What it does:** Checks real container image, labels, mounts, and resource limits for query isolation.
- **Why it is hard:** Short but dense: many host/config fields must match the reservation exactly. (CC=31 (many branches))

### 17. `verify_stored_candidate`

- **Score:** 5 · **CC:** 29 · **Nesting:** 1 · **LOC:** 79
- **Theme:** EIA connector / validate
- **Where:** [`backend/src/trinity/connector/pipeline.py:358`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/connector/pipeline.py#L358-L436)
- **What it does:** Rechecks local validation receipt and every remote bundle object before trusting storage.
- **Why it is hard:** Joins local and S3 proofs; missing completion or changed bytes must fail closed. (CC=29, 79 lines)

### 18. `SqlExplorer`

- **Score:** 5 · **CC:** 29 · **Nesting:** 3 · **LOC:** 59
- **Theme:** Frontend UI
- **Where:** [`frontend/src/pages/sql/SqlExplorer.tsx:39`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/frontend/src/pages/sql/SqlExplorer.tsx#L39-L97)
- **What it does:** SQL workspace UI: edit, run, wait, show results/errors with role gating.
- **Why it is hard:** Busy/wait/error/result state machine plus session permissions in one component. (CC=29)

### 19. `PreviewOperation.__post_init__`

- **Score:** 5 · **CC:** 28 · **Nesting:** 2 · **LOC:** 42
- **Theme:** Other backend
- **Where:** [`backend/src/trinity/contracts/queries.py:77`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/contracts/queries.py#L77-L118)
- **What it does:** Validates preview operation fields (dates, IDs, dataset, page size) at construction.
- **Why it is hard:** Many typed rejects packed into post-init; invalid combinations look alike. (CC=28)

### 20. `stage_query`

- **Score:** 5 · **CC:** 27 · **Nesting:** 2 · **LOC:** 70
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/staging.py:98`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/staging.py#L98-L167)
- **What it does:** Verifies pinned manifest and every selected file, then seals a staged query request.
- **Why it is hard:** Path/symlink/digest checks before isolation; one miss opens unpublished data risk. (CC=27, 70 lines)

### 21. `PublicationRecovery.reconcile`

- **Score:** 5 · **CC:** 27 · **Nesting:** 2 · **LOC:** 62
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/publication/recovery.py:40`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/publication/recovery.py#L40-L101)
- **What it does:** Idempotent publication failure recovery under lock; safe to replay lost responses.
- **Why it is hard:** Must not move the active pointer if already published; generation/fence cases stack up. (CC=27)

### 22. `ExecutionService.event`

- **Score:** 5 · **CC:** 27 · **Nesting:** 6 · **LOC:** 61
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/refresh/execution.py:145`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/refresh/execution.py#L145-L205)
- **What it does:** Commits stage/attempt custody for worker events before acknowledging the supervisor.
- **Why it is hard:** Event-kind switch with ownership/fence checks; wrong order breaks refresh custody. (CC=27, nesting=6)

### 23. `verified_chunks`

- **Score:** 5 · **CC:** 27 · **Nesting:** 3 · **LOC:** 59
- **Theme:** Storage / adapters
- **Where:** [`backend/src/trinity/adapters/s3.py:134`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/adapters/s3.py#L134-L192)
- **What it does:** Streams object bytes in bounded chunks and verifies identities before completion.
- **Why it is hard:** Encoding chosen by trusted bundle, not S3 metadata; chunk and total limits interact. (CC=27)

### 24. `read_preview_publication`

- **Score:** 5 · **CC:** 27 · **Nesting:** 2 · **LOC:** 49
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/publication/repository.py:74`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/publication/repository.py#L74-L122)
- **What it does:** Requires complete frozen evidence authority for an already-pinned version.
- **Why it is hard:** Candidate receipt alone is not enough; snapshot coupling with pin read is subtle. (CC=27)

### 25. `DatasetTable`

- **Score:** 5 · **CC:** 26 · **Nesting:** 3 · **LOC:** 86
- **Theme:** Frontend UI
- **Where:** [`frontend/src/pages/catalog/TableView.tsx:24`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/frontend/src/pages/catalog/TableView.tsx#L24-L109)
- **What it does:** Catalog table: filters, paging, facility/generator choices, preview fetch.
- **Why it is hard:** URL search params, React Query cache, and filter state all meet here. (CC=26, 86 lines)

### 26. `_snapshot`

- **Score:** 5 · **CC:** 26 · **Nesting:** 3 · **LOC:** 51
- **Theme:** EIA connector / validate
- **Where:** [`backend/src/trinity/connector/validate.py:540`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/connector/validate.py#L540-L590)
- **What it does:** Reads only declared parquet/source files and keeps per-dataset integrity failures visible.
- **Why it is hard:** Partial integrity across datasets; must not hide one dataset failure behind another. (CC=26)

### 27. `_verify_receipt`

- **Score:** 5 · **CC:** 26 · **Nesting:** 2 · **LOC:** 50
- **Theme:** EIA connector / validate
- **Where:** [`backend/src/trinity/connector/prepare.py:195`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/connector/prepare.py#L195-L244)
- **What it does:** After child exit, matches retained receipt to manifest/bundle/storage completion.
- **Why it is hard:** Parent must trust a small receipt only; many mismatch cases without redoing network I/O. (CC=26)

### 28. `Manifest.__post_init__`

- **Score:** 5 · **CC:** 26 · **Nesting:** 2 · **LOC:** 41
- **Theme:** Other backend
- **Where:** [`backend/src/trinity/contracts/manifest.py:159`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/contracts/manifest.py#L159-L199)
- **What it does:** Validates manifest identity/format/contract fields at construction.
- **Why it is hard:** Many typed invariants; failures collapse to ManifestError codes. (CC=26)

### 29. `build_choice_response`

- **Score:** 5 · **CC:** 25 · **Nesting:** 2 · **LOC:** 38
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/choice_schemas.py:51`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/choice_schemas.py#L51-L88)
- **What it does:** Builds a signed choices page after binding/order/parent/search checks.
- **Why it is hard:** Must not dedupe or drop invalid rows (that can hide truncation bugs). (CC=25)

### 30. `S3Settings.__post_init__`

- **Score:** 5 · **CC:** 25 · **Nesting:** 2 · **LOC:** 31
- **Theme:** Other backend
- **Where:** [`backend/src/trinity/config.py:76`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/config.py#L76-L106)
- **What it does:** Validates S3 bucket/prefix/endpoint settings at startup.
- **Why it is hard:** Strict regex and path-safety rules packed into post-init. (CC=25)

### 31. `main`

- **Score:** 5 · **CC:** 24 · **Nesting:** 3 · **LOC:** 47
- **Theme:** Auth / sessions
- **Where:** [`backend/src/trinity/auth/check.py:154`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/auth/check.py#L154-L200)
- **What it does:** Terminal persona checker: login and optional catalog/preview/schedule probes.
- **Why it is hard:** Role matrix of expected pass/fail; must print only safe summaries. (CC=24)

### 32. `_refresh_stopped`

- **Score:** 5 · **CC:** 24 · **Nesting:** 1 · **LOC:** 42
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/refresh/recovery.py:19`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/refresh/recovery.py#L19-L60)
- **What it does:** Detects only failure shapes written by current Refresh writers.
- **Why it is hard:** Pre-claim vs started failure vs lease/deadline look similar but differ in proof. (CC=24)

### 33. `recovery_actions`

- **Score:** 5 · **CC:** 24 · **Nesting:** 2 · **LOC:** 38
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/refresh/recovery.py:63`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/refresh/recovery.py#L63-L100)
- **What it does:** Computes rerun/delete flags for a retained failed lifecycle.
- **Why it is hard:** Needs matching warning and admission owner; must preserve publications. (CC=24)

### 34. `PublicationService.finish`

- **Score:** 5 · **CC:** 23 · **Nesting:** 1 · **LOC:** 54
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/publication/service.py:131`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/publication/service.py#L131-L184)
- **What it does:** Commits all publication effects together, or leaves every effect absent.
- **Why it is hard:** Idempotent finish under claim/generation; partial commit is forbidden. (CC=23)

### 35. `RunPage`

- **Score:** 5 · **CC:** 23 · **Nesting:** 1 · **LOC:** 33
- **Theme:** Publication / refresh
- **Where:** [`frontend/src/pages/refresh/Refresh.tsx:122`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/frontend/src/pages/refresh/Refresh.tsx#L122-L154)
- **What it does:** Admin run detail: timeline, candidate panel, recovery actions, step paging.
- **Why it is hard:** Many concurrent queries/commands (recovery, steps cursor, cache invalidation). (CC=23)

### 36. `_validate_reserved`

- **Score:** 5 · **CC:** 22 · **Nesting:** 2 · **LOC:** 88
- **Theme:** EIA connector / validate
- **Where:** [`backend/src/trinity/connector/validate.py:727`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/connector/validate.py#L727-L814)
- **What it does:** Runs and persists one reserved validation attempt; keeps failures without repair.
- **Why it is hard:** Long path that binds evidence prefixes, required checks, and diagnostics in one attempt. (CC=22, 88 lines)

### 37. `EIAClient._collect`

- **Score:** 5 · **CC:** 22 · **Nesting:** 3 · **LOC:** 68
- **Theme:** EIA connector / validate
- **Where:** [`backend/src/trinity/connector/client.py:417`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/connector/client.py#L417-L484)
- **What it does:** Pages EIA until empty page; accumulates unique rows or fails with no partial success.
- **Why it is hard:** Pagination, uniqueness, and fail-closed partials; timeout/page-limit interactions. (CC=22)

### 38. `PublishedReader.read_into`

- **Score:** 5 · **CC:** 22 · **Nesting:** 3 · **LOC:** 52
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/staging.py:31`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/staging.py#L31-L82)
- **What it does:** Reads published object bytes using only the trusted bundle encoding descriptor.
- **Why it is hard:** Compressed vs legacy paths; size/digest checks before callers see bytes. (CC=22)

### 39. `check_preview`

- **Score:** 5 · **CC:** 22 · **Nesting:** 4 · **LOC:** 38
- **Theme:** Auth / sessions
- **Where:** [`backend/src/trinity/auth/preview_check.py:60`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/auth/preview_check.py#L60-L97)
- **What it does:** Verifies exact preview pages per role and Viewer detail denial.
- **Why it is hard:** Fixture must be real publication evidence; role matrix is strict. (CC=22)

### 40. `CursorCodec.decode`

- **Score:** 5 · **CC:** 22 · **Nesting:** 1 · **LOC:** 37
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/cursors.py:142`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/cursors.py#L142-L178)
- **What it does:** Decodes signed preview/SQL cursors; rejects bad/extended tokens safely.
- **Why it is hard:** Four-part token parse plus HMAC; all failures share one safe code. (CC=22)

### 41. `timeline.<callback@92>`

- **Score:** 5 · **CC:** 21 · **Nesting:** 9 · **LOC:** 19
- **Theme:** Publication / refresh
- **Where:** [`frontend/src/pages/refresh/Refresh.tsx:92`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/frontend/src/pages/refresh/Refresh.tsx#L92-L110)
- **What it does:** Maps refresh steps into per-stage timeline state and copy.
- **Why it is hard:** Nested stage/attempt rules including the awaiting_approval special case. (CC=21, nesting=9)

### 42. `QueryExecution.execute`

- **Score:** 5 · **CC:** 18 · **Nesting:** 3 · **LOC:** 147
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/client.py:67`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/client.py#L67-L213)
- **What it does:** Stages published files, runs isolated query container, checks output envelope.
- **Why it is hard:** Long lifecycle (reserve → stage → run → cleanup); owned cleanup on every path. (CC=18, 147 lines)

### 43. `store_candidate`

- **Score:** 5 · **CC:** 18 · **Nesting:** 3 · **LOC:** 140
- **Theme:** EIA connector / validate
- **Where:** [`backend/src/trinity/connector/pipeline.py:216`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/connector/pipeline.py#L216-L355)
- **What it does:** Uploads one locally validated candidate and returns a verified storage receipt.
- **Why it is hard:** Long upload/verify sequence with cancel and timeout paths. (CC=18, 140 lines)

### 44. `QueryResponse.exact_cells`

- **Score:** 5 · **CC:** 18 · **Nesting:** 8 · **LOC:** 16
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/schemas.py:39`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/schemas.py#L39-L54)
- **What it does:** Validates SQL result cell types/nullability/row shape before return.
- **Why it is hard:** Compact but dense type matrix; truncation/row-count invariants. (CC=18, nesting=8)

## Score 4 — High

### 1. `PublicationCommands.command`

- **Score:** 4 · **CC:** 21 · **Nesting:** 3 · **LOC:** 87
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/publication/commands.py:23`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/publication/commands.py#L23-L109)
- **What it does:** Applies one candidate action (approve/recover path) or returns an original receipt.
- **Why it is hard:** Auth capability switches by action; fingerprint/ETag replay rules. (CC=21, 87 lines)

### 2. `check_schedule`

- **Score:** 4 · **CC:** 21 · **Nesting:** 2 · **LOC:** 54
- **Theme:** Auth / sessions
- **Where:** [`backend/src/trinity/auth/check.py:61`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/auth/check.py#L61-L114)
- **What it does:** Proves Admin can save schedule without starting a run; others get 403.
- **Why it is hard:** Multi-step ETag/history dance per role; easy to break ordering. (CC=21)

### 3. `admin_context`

- **Score:** 4 · **CC:** 21 · **Nesting:** 5 · **LOC:** 33
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/refresh/service.py:156`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/refresh/service.py#L156-L188)
- **What it does:** Builds admin eligibility codes for UI without granting publish/recover permission.
- **Why it is hard:** Nested status/setup/warning cases; display-only but must stay conservative. (CC=21, nesting=5)

### 4. `SettingsForm`

- **Score:** 4 · **CC:** 20 · **Nesting:** 3 · **LOC:** 41
- **Theme:** Frontend UI
- **Where:** [`frontend/src/pages/settings/Settings.tsx:27`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/frontend/src/pages/settings/Settings.tsx#L27-L67)
- **What it does:** Settings form for schedule/setup with ETag save and notices.
- **Why it is hard:** Setup vs edit modes, cache invalidation, and navigation side effects. (CC=20)

### 5. `parse_preview_input`

- **Score:** 4 · **CC:** 20 · **Nesting:** 5 · **LOC:** 29
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/preview.py:107`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/preview.py#L107-L135)
- **What it does:** Parses URL pairs into PreviewInput before rate debit; keeps duplicates.
- **Why it is hard:** No semantic cross-field checks here—easy to assume too much. (CC=20, nesting=5)

### 6. `execute_preview`

- **Score:** 4 · **CC:** 19 · **Nesting:** 3 · **LOC:** 57
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/runtime/preview.py:17`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/runtime/preview.py#L17-L73)
- **What it does:** Runs a closed preview over staged files; returns ≤ page_size rows plus lookahead.
- **Why it is hard:** Rechecks operation then registers files; typed literals including ID-like values. (CC=19)

### 7. `request`

- **Score:** 4 · **CC:** 19 · **Nesting:** 2 · **LOC:** 52
- **Theme:** Frontend UI
- **Where:** [`frontend/src/api/client.ts:165`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/frontend/src/api/client.ts#L165-L216)
- **What it does:** Frontend HTTP helper: headers, If-Match, credentials, typed ApiResult errors.
- **Why it is hard:** Many option branches (body, etag, parse failures) shared by all pages. (CC=19)

### 8. `Contributions`

- **Score:** 4 · **CC:** 19 · **Nesting:** 3 · **LOC:** 43
- **Theme:** Frontend UI
- **Where:** [`frontend/src/pages/dashboard/Dashboard.tsx:162`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/frontend/src/pages/dashboard/Dashboard.tsx#L162-L204)
- **What it does:** Shows facility contributions for the selected national day with keep-previous behavior.
- **Why it is hard:** Loading/selection races while keeping prior contributions visible. (CC=19)

### 9. `validate_query`

- **Score:** 4 · **CC:** 19 · **Nesting:** 2 · **LOC:** 35
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/runtime/sql_policy.py:372`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/runtime/sql_policy.py#L372-L406)
- **What it does:** Runs the full D01 SQL policy in a bounded subprocess and returns a normalized ValidatedQuery.
- **Why it is hard:** Orchestrates several policy steps; failures must stay safe and non-leaky. (CC=19)

### 10. `_binding`

- **Score:** 4 · **CC:** 19 · **Nesting:** 1 · **LOC:** 26
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/refresh/registration.py:47`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/refresh/registration.py#L47-L72)
- **What it does:** Compares measured candidate evidence to the worker’s frozen expectations.
- **Why it is hard:** Manifest/policy/window fields must all match or handoff fails. (CC=19)

### 11. `FacilityChoices`

- **Score:** 4 · **CC:** 19 · **Nesting:** 1 · **LOC:** 24
- **Theme:** Frontend UI
- **Where:** [`frontend/src/pages/catalog/Choices.tsx:26`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/frontend/src/pages/catalog/Choices.tsx#L26-L49)
- **What it does:** Searchable facility picker bound to preview filters.
- **Why it is hard:** Debounced search, visit/cache keys, and busy disable paths. (CC=19)

### 12. `_owned`

- **Score:** 4 · **CC:** 19 · **Nesting:** 1 · **LOC:** 20
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/refresh/registration.py:25`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/refresh/registration.py#L25-L44)
- **What it does:** Locks control/run/version/step in order; rejects stale writers via fence.
- **Why it is hard:** Canonical lock order plus lease/fence checks; races are subtle. (CC=19)

### 13. `prepare_candidate`

- **Score:** 4 · **CC:** 18 · **Nesting:** 2 · **LOC:** 110
- **Theme:** EIA connector / validate
- **Where:** [`backend/src/trinity/connector/pipeline.py:447`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/connector/pipeline.py#L447-L556)
- **What it does:** End-to-end: extract → freeze → validate → store for one new version.
- **Why it is hard:** Stage orchestration across network, disk, and S3; events and cancellation interleaved. (CC=18, 110 lines)

### 14. `EIAClient._recorded_request`

- **Score:** 4 · **CC:** 18 · **Nesting:** 2 · **LOC:** 77
- **Theme:** EIA connector / validate
- **Where:** [`backend/src/trinity/connector/client.py:579`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/connector/client.py#L579-L655)
- **What it does:** Sends one GET and optionally records sanitized attempt evidence.
- **Why it is hard:** Success and failure both must retain safe evidence without leaking credentials. (CC=18, 77 lines)

### 15. `persist_candidate`

- **Score:** 4 · **CC:** 18 · **Nesting:** 2 · **LOC:** 64
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/refresh/registration.py:75`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/refresh/registration.py#L75-L138)
- **What it does:** Writes verified candidate handoff on the caller’s transaction (no commit here).
- **Why it is hard:** Exact replay rules; must not commit; binding checks precede writes. (CC=18)

### 16. `ChoiceService.prepare`

- **Score:** 4 · **CC:** 18 · **Nesting:** 2 · **LOC:** 52
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/choice_service.py:32`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/choice_service.py#L32-L83)
- **What it does:** Prepares a choices query: auth, pin, debit, then storage/runtime work.
- **Why it is hard:** Metadata transactions must close before storage; counted failures retained. (CC=18)

### 17. `build_preview_response`

- **Score:** 4 · **CC:** 18 · **Nesting:** 1 · **LOC:** 36
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/preview_schemas.py:195`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/preview_schemas.py#L195-L230)
- **What it does:** Builds a bounded wire preview page from ≤ limit+1 encoded rows.
- **Why it is hard:** Cursor/has_more/diagnostics must stay consistent with trusted evidence. (CC=18)

### 18. `serialize_preview_rows`

- **Score:** 4 · **CC:** 18 · **Nesting:** 6 · **LOC:** 34
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/preview_schemas.py:159`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/preview_schemas.py#L159-L192)
- **What it does:** Encodes Arrow-like cell values to wire strings without float rounding.
- **Why it is hard:** Per-column exact encoding; silent conversion would corrupt traces. (CC=18, nesting=6)

### 19. `Dashboard`

- **Score:** 4 · **CC:** 18 · **Nesting:** 2 · **LOC:** 31
- **Theme:** Frontend UI
- **Where:** [`frontend/src/pages/dashboard/Dashboard.tsx:52`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/frontend/src/pages/dashboard/Dashboard.tsx#L52-L82)
- **What it does:** Loads dashboard data for a date range and owns preset/custom range controls.
- **Why it is hard:** Query key and range state interactions; custom vs preset paths are easy to confuse. (CC=18)

### 20. `ChoiceOperation.__post_init__`

- **Score:** 4 · **CC:** 18 · **Nesting:** 3 · **LOC:** 17
- **Theme:** Other backend
- **Where:** [`backend/src/trinity/contracts/choices.py:31`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/contracts/choices.py#L31-L47)
- **What it does:** Validates choice operation protocol fields and reuses preview identity checks.
- **Why it is hard:** Delegates into PreviewOperation then adds choice-specific rejects. (CC=18)

### 21. `GeneratorChoices`

- **Score:** 4 · **CC:** 18 · **Nesting:** 1 · **LOC:** 12
- **Theme:** Frontend UI
- **Where:** [`frontend/src/pages/catalog/Choices.tsx:50`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/frontend/src/pages/catalog/Choices.tsx#L50-L61)
- **What it does:** Generator picker that depends on selected facility/filters.
- **Why it is hard:** Disabled/open state tied to facility presence and query keys. (CC=18)

### 22. `check_persona`

- **Score:** 4 · **CC:** 17 · **Nesting:** 2 · **LOC:** 35
- **Theme:** Auth / sessions
- **Where:** [`backend/src/trinity/auth/check.py:117`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/auth/check.py#L117-L151)
- **What it does:** Logs in a persona and optionally checks catalog/preview/schedule; logout on failure.
- **Why it is hard:** Branchy optional suites; cleanup logout must always be attempted.

### 23. `read_context`

- **Score:** 4 · **CC:** 17 · **Nesting:** 3 · **LOC:** 31
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/refresh/repository.py:206`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/refresh/repository.py#L206-L236)
- **What it does:** Reads occupied refresh lifecycle, candidate, and unresolved warning.
- **Why it is hard:** Several joined tables; absence vs empty warning meanings differ.

### 24. `candidate_view`

- **Score:** 4 · **CC:** 17 · **Nesting:** 5 · **LOC:** 20
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/refresh/tracking.py:48`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/refresh/tracking.py#L48-L67)
- **What it does:** Derives candidate display state; never authorizes publication.
- **Why it is hard:** Eligible/approved/frozen flags combine; easy to confuse with real auth. (nesting=5)

### 25. `execute_local`

- **Score:** 4 · **CC:** 16 · **Nesting:** 4 · **LOC:** 48
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/runtime/engine.py:63`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/runtime/engine.py#L63-L110)
- **What it does:** Revalidates policy, registers one staged dataset, returns a bounded result fragment.
- **Why it is hard:** Supervisor limits are external; engine must preserve exact numbers and labels.

### 26. `partial_results`

- **Score:** 4 · **CC:** 16 · **Nesting:** 2 · **LOC:** 39
- **Theme:** Other backend
- **Where:** [`backend/src/trinity/workers/refresh.py:31`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/workers/refresh.py#L31-L69)
- **What it does:** Loads only complete journal lines with matching detail bytes after a kill.
- **Why it is hard:** Torn last line vs earlier complete evidence; must not invent success.

### 27. `CandidatePanel`

- **Score:** 4 · **CC:** 16 · **Nesting:** 1 · **LOC:** 34
- **Theme:** Publication / refresh
- **Where:** [`frontend/src/pages/refresh/Refresh.tsx:156`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/frontend/src/pages/refresh/Refresh.tsx#L156-L189)
- **What it does:** Shows candidate review actions (approve/discard/retry) for a version.
- **Why it is hard:** Command and query revision coupling; disposition gates which buttons appear.

### 28. `ValidatedQuery.from_bytes`

- **Score:** 4 · **CC:** 16 · **Nesting:** 2 · **LOC:** 25
- **Theme:** Other backend
- **Where:** [`backend/src/trinity/contracts/queries.py:35`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/contracts/queries.py#L35-L59)
- **What it does:** Decodes internal ValidatedQuery bytes; rejects noncanonical/oversized/extended messages.
- **Why it is hard:** Strict key set and canonical JSON; security-sensitive parser.

### 29. `actions`

- **Score:** 4 · **CC:** 16 · **Nesting:** 1 · **LOC:** 24
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/publication/checks.py:119`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/publication/checks.py#L119-L142)
- **What it does:** Returns approve / publication_retry / discard eligibility used by all command paths.
- **Why it is hard:** Conservative flags depend on run, version disposition, warnings, and prior events together.

### 30. `_check_cells`

- **Score:** 4 · **CC:** 16 · **Nesting:** 6 · **LOC:** 24
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/preview_schemas.py:66`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/preview_schemas.py#L66-L89)
- **What it does:** Checks preview row width, nullability, and cell types.
- **Why it is hard:** Nested per-cell validation; dense type rules. (nesting=6)

### 31. `_parse`

- **Score:** 4 · **CC:** 16 · **Nesting:** 3 · **LOC:** 22
- **Theme:** Other backend
- **Where:** [`backend/src/trinity/dashboard/calculation.py:40`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/dashboard/calculation.py#L40-L61)
- **What it does:** Parses dashboard query pairs into scalars after inspecting all occurrences.
- **Why it is hard:** Rejects dict/collapsed inputs; duplicate keys must not silently win.

### 32. `custody`

- **Score:** 4 · **CC:** 15 · **Nesting:** 1 · **LOC:** 37
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/publication/custody.py:34`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/publication/custody.py#L34-L70)
- **What it does:** Exclusive flock on prepare root/lock inodes until SQL completes.
- **Why it is hard:** No symlink follow; missing files unrecreatable; nonblocking flock races.

### 33. `seed_personas`

- **Score:** 4 · **CC:** 15 · **Nesting:** 3 · **LOC:** 30
- **Theme:** Auth / sessions
- **Where:** [`backend/src/trinity/auth/seed.py:22`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/auth/seed.py#L22-L51)
- **What it does:** Creates missing local personas atomically; never overwrites existing ones.
- **Why it is hard:** Read-then-write under transaction; password source side effects.

### 34. `_freeze_reserved`

- **Score:** 4 · **CC:** 14 · **Nesting:** 3 · **LOC:** 73
- **Theme:** EIA connector / validate
- **Where:** [`backend/src/trinity/connector/parquet.py:235`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/connector/parquet.py#L235-L307)
- **What it does:** Freezes source evidence into a newly reserved directory; retains failures.
- **Why it is hard:** Multi-stage freeze (source → parquet); failure retention without repair. (73 lines)

### 35. `load_candidate`

- **Score:** 4 · **CC:** 14 · **Nesting:** 3 · **LOC:** 63
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/refresh/evidence.py:54`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/refresh/evidence.py#L54-L116)
- **What it does:** Loads candidate only if parent completion, hashes, and local/remote bytes match.
- **Why it is hard:** Expected hash comes from durable custody, not a fresh hash of the file.

### 36. `EvidenceCache.read`

- **Score:** 4 · **CC:** 14 · **Nesting:** 3 · **LOC:** 57
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/publication/evidence_cache.py:91`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/publication/evidence_cache.py#L91-L147)
- **What it does:** Joins or owns a bounded evidence fill; returns only the authorized dataset.
- **Why it is hard:** Cache fill races plus deadline checks; failures must not leave bad entries.

### 37. `StorageOperation.put_verified`

- **Score:** 4 · **CC:** 14 · **Nesting:** 4 · **LOC:** 54
- **Theme:** Storage / adapters
- **Where:** [`backend/src/trinity/adapters/s3.py:343`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/adapters/s3.py#L343-L396)
- **What it does:** Create-once put then read-back verify; rejects conflicts and unresolved writes.
- **Why it is hard:** Reservation tokens and conflict stops; ambiguous S3 outcomes are hard.

### 38. `rotate_passwords`

- **Score:** 4 · **CC:** 14 · **Nesting:** 2 · **LOC:** 47
- **Theme:** Auth / sessions
- **Where:** [`backend/src/trinity/auth/rotate.py:49`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/auth/rotate.py#L49-L95)
- **What it does:** Replaces password hashes for named personas in one transaction.
- **Why it is hard:** Per-name password_source errors vs DB update atomicity.

### 39. `StorageOperation.verify`

- **Score:** 4 · **CC:** 14 · **Nesting:** 3 · **LOC:** 43
- **Theme:** Storage / adapters
- **Where:** [`backend/src/trinity/adapters/s3.py:299`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/adapters/s3.py#L299-L341)
- **What it does:** Streamed GET hashed against size and SHA-256 (never ETag).
- **Why it is hard:** Missing-key vs bad-bytes vs retry exhaustion need different outcomes.

### 40. `validate_single_statement`

- **Score:** 4 · **CC:** 14 · **Nesting:** 1 · **LOC:** 39
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/runtime/sql_policy.py:14`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/runtime/sql_policy.py#L14-L52)
- **What it does:** Parses input and requires exactly one nonempty SELECT root.
- **Why it is hard:** Semicolon/comment edge cases; parse errors must map to one safe validation failure.

### 41. `RefreshList`

- **Score:** 4 · **CC:** 14 · **Nesting:** 1 · **LOC:** 30
- **Theme:** Publication / refresh
- **Where:** [`frontend/src/pages/refresh/Refresh.tsx:52`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/frontend/src/pages/refresh/Refresh.tsx#L52-L81)
- **What it does:** Paginated refresh run list with polling for admins.
- **Why it is hard:** Infinite query, refetch interval, and role gate.

### 42. `ChoiceCursorCodec.decode`

- **Score:** 4 · **CC:** 14 · **Nesting:** 1 · **LOC:** 29
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/choices.py:100`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/choices.py#L100-L128)
- **What it does:** Authenticates and decodes choice cursors; rejects other-purpose tokens.
- **Why it is hard:** Same token shape as preview but purpose-bound; mixups are security bugs.

### 43. `PreviewResponse.consistent_page`

- **Score:** 4 · **CC:** 14 · **Nesting:** 2 · **LOC:** 21
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/preview_schemas.py:136`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/preview_schemas.py#L136-L156)
- **What it does:** Post-condition: schema, counts, reason, and cursor agree for a page.
- **Why it is hard:** Many invalid combinations must raise; used as a trust boundary.

### 44. `PreviewService.prepare`

- **Score:** 4 · **CC:** 13 · **Nesting:** 2 · **LOC:** 61
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/service.py:100`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/service.py#L100-L160)
- **What it does:** Debits rate after identity/shape checks, then pins publication and stages work.
- **Why it is hard:** Debit-even-on-later-failure rule; reauth before pin; transaction boundaries.

### 45. `RecoveryService.command`

- **Score:** 4 · **CC:** 13 · **Nesting:** 2 · **LOC:** 59
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/refresh/recovery.py:109`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/refresh/recovery.py#L109-L167)
- **What it does:** Replays authorized recovery intent or atomically resolves the targeted failure.
- **Why it is hard:** Authority, syntax, receipt replay, and obsolete revisions all interact.

### 46. `EIAClient._fetch_page`

- **Score:** 4 · **CC:** 13 · **Nesting:** 1 · **LOC:** 54
- **Theme:** EIA connector / validate
- **Where:** [`backend/src/trinity/connector/client.py:486`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/connector/client.py#L486-L539)
- **What it does:** Fetches one bounded page, strips credentials, and checks source shape.
- **Why it is hard:** Arg checks before HTTP plus response validation; optional tracker adds branches.

### 47. `cli`

- **Score:** 4 · **CC:** 13 · **Nesting:** 1 · **LOC:** 46
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/publication/recovery.py:104`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/publication/recovery.py#L104-L149)
- **What it does:** CLI entry for publication recovery; no Redis/S3/EIA init; no raw exception prints.
- **Why it is hard:** Ops-facing argument/env parsing with strict safe output rules.

### 48. `verify_password`

- **Score:** 4 · **CC:** 13 · **Nesting:** 2 · **LOC:** 38
- **Theme:** Auth / sessions
- **Where:** [`backend/src/trinity/auth/passwords.py:48`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/auth/passwords.py#L48-L85)
- **What it does:** Verifies password in a bounded child process with concurrency slots.
- **Why it is hard:** Acquire/reap/deadline paths; must not leak slots on failure.

### 49. `PublicationService.claim`

- **Score:** 4 · **CC:** 13 · **Nesting:** 1 · **LOC:** 32
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/publication/service.py:83`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/publication/service.py#L83-L114)
- **What it does:** Commits the unique generation marker before verification runs.
- **Why it is hard:** Locking run/version/active together; claim must be unique and replay-safe.

### 50. `parse_choice_input`

- **Score:** 4 · **CC:** 13 · **Nesting:** 3 · **LOC:** 29
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/choices.py:31`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/choices.py#L31-L59)
- **What it does:** Parses choice query pairs; preserves duplicates; search is facilities-only.
- **Why it is hard:** Duplicate/unknown key rules before semantics.

### 51. `_json_value`

- **Score:** 4 · **CC:** 13 · **Nesting:** 2 · **LOC:** 22
- **Theme:** Other backend
- **Where:** [`backend/src/trinity/contracts/manifest.py:30`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/contracts/manifest.py#L30-L51)
- **What it does:** Canonical JSON conversion without float conversion or decimal rounding.
- **Why it is hard:** Decimal/date/finite checks; silent rounding would corrupt evidence.

### 52. `parse_page`

- **Score:** 4 · **CC:** 13 · **Nesting:** 2 · **LOC:** 22
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/refresh/schemas.py:173`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/refresh/schemas.py#L173-L194)
- **What it does:** Parses refresh list/step page params; rejects repeats/unknowns.
- **Why it is hard:** Two modes (runs vs steps) share logic with different param names.

### 53. `PreviewInput.__post_init__`

- **Score:** 4 · **CC:** 13 · **Nesting:** 2 · **LOC:** 15
- **Theme:** SQL / query runtime
- **Where:** [`backend/src/trinity/queries/preview.py:70`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/queries/preview.py#L70-L84)
- **What it does:** Validates preview dates, facility/generator IDs, and limit bounds.
- **Why it is hard:** Packed typed checks; invalid ID vs date failures look similar.

### 54. `candidateCopy`

- **Score:** 4 · **CC:** 13 · **Nesting:** 1 · **LOC:** 12
- **Theme:** Frontend UI
- **Where:** [`frontend/src/lib/copy.ts:70`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/frontend/src/lib/copy.ts#L70-L81)
- **What it does:** Maps candidate disposition/review status to user-facing explanation text.
- **Why it is hard:** Many disposition/status combinations; copy must match publication rules.

### 55. `RefreshCursorCodec._validate`

- **Score:** 4 · **CC:** 13 · **Nesting:** 1 · **LOC:** 10
- **Theme:** Publication / refresh
- **Where:** [`backend/src/trinity/refresh/cursors.py:63`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/backend/src/trinity/refresh/cursors.py#L63-L72)
- **What it does:** Validates refresh cursor body counters against bigint and page size.
- **Why it is hard:** Strict key set plus purpose/target binding in a tiny function.

### 56. `SessionProvider`

- **Score:** 4 · **CC:** 1 · **Nesting:** 0 · **LOC:** 124
- **Theme:** Frontend UI
- **Where:** [`frontend/src/session/SessionProvider.tsx:18`](https://github.com/alejandroayalad/trinity/blob/014f3064689ff8f8fda6be264d9bb17c46497989/frontend/src/session/SessionProvider.tsx#L18-L141)
- **What it does:** Holds login session, me payload, cache clear on sign-out, and auth refresh.
- **Why it is hard:** Long provider: loading/error/reason and cache coupling across the app. (124 lines)

