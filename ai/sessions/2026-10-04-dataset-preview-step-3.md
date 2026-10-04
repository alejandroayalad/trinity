# Dataset preview Step 3 — October 4, 2026

## Objective and authority

[ME] Alayala first requested Steps 3–4, then corrected the scope to **Step 3 only**. He requested comments about behavior and specific details. [YOU] Implemented shared typed execution and endpoint integration on `feat/catalog-permissions`, starting from clean HEAD `fa766e1`. Read current README, CONTRIBUTING, preview specification/design/tasks, applicable A9/A15/A16/A19 rules, product scope, findings and Step 2 evidence before editing.

Comments explain behavior, boundaries and specific failure rules. No comment records author, ticket or change history. No dependency, credentials, retained database state, cloud object or existing candidate evidence was changed. No commit, push, image build, live EIA/S3 call, migration execution or Step 4 acceptance was performed.

References: [tasks](../../sdd/dataset-preview/tasks.md), [design](../../sdd/dataset-preview/design.md), A9/A15/A16/A19–A21 in [DECISIONS](../../DECISIONS.md). Maintain data evidence — ongoing. All new engine and producer inputs are synthetic; no new anomaly or completeness claim is established.

## Input, flow, output and failure

Input: current session, public dataset, raw decoded query pairs, optional body and cursor. Flow: current identity/dataset authorization → primitive shape → committed shared rate debit → semantic filters/authenticated cursor → fresh identity and pinned publication/defaults/provenance → shared capacity → verified evidence and files → typed isolated operation → exact page/cursor → confirmed owned cleanup. Metadata transactions close before external reads. Preview starts its 30-second analytical budget immediately before capacity admission; preflight is separately bounded.

Output: canonical columns and exact date/decimal/text/null cells, at most the requested page size, optional signed continuation and permitted frozen dataset notes. Diagnostic counts describe the complete frozen dataset, not an invented page count. No direct API-process engine fallback exists.

Failure: Viewer requests facility preview with a copied cursor or malformed limit. Dataset authorization returns the safe 404 before cursor configuration, debit, publication, storage or engine access. Duplicate limits fail before debit; an otherwise valid generator filter without facility fails after one committed debit. An invalid output binding or signing failure still follows owned cleanup. Unconfirmed termination retains capacity.

## Implemented code

| Component | Result |
|---|---|
| `contracts/queries.py`, shared staging and runtime entrypoint | Closed versioned/tagged SQL and preview envelopes, exact digest/request/version binding and cross-kind/version rejection. SQL still independently revalidates its existing policy. API and runtime image must match. |
| `queries/runtime/preview.py` and shared `engine.py` | Typed DataFusion date/ID/full-key predicates, binary ascending keys, bounded lookahead and shared restricted context/scalar encoding. No client SQL expression or file path in preview operations. |
| `publication/repository.py`, `publication/diagnostics.py` | Same-snapshot publication/validation/approval pinning; bounded bundle/summary reads; complete 16 required and 23 diagnostic evaluation verification; detail hashes and frozen warning identity checked before dataset-only projection. Never emits D09 or raw details. |
| `queries/service.py`, `queries/router.py`, `errors.py`, `main.py` | Required debit/semantic/publication ordering, duplicate-preserving query handling, shared disconnect owner, lazy signing and runner configuration. The default app keeps `enable_preview=False`. Tests explicitly inject their adapters. |
| `queries/client.py`, `preview_schemas.py` | Closed runtime batch validation, cursor signing from the last returned key, complete response limit and common lifecycle cleanup. Attach transport close failure cannot skip owned cleanup. |

## Proven linkage gap and migration boundary

- Severity and scope: delivery prerequisite in the committed baseline; the new read path and migration draft are uncommitted.
- Expected: `read_preview_publication` must derive a trusted immutable bundle hash and connector validation-attempt ID from the active version's application-state snapshot.
- Observed: `0002_app_entry` supplies manifest, validation-step/checkset and frozen warning fields. It has neither the bundle hash nor connector attempt UUID. `0003_query_admission` adds only shared admission/lifecycle tables. Existing `read_pinned_publication` returns manifest/public metadata only. The saved bundle itself already exists.
- Evidence: inspected `backend/migrations/versions/` (`0001_local_auth.py`, `0002_app_entry.py`, `0003_query_admission.py` at baseline), `publication/repository.py`, connector validation/storage producers and retained bundle inventory. Searched migrations/contracts/producer code for `bundle`, `validation_step`, `diagnostics_frozen`, `validation_checkset`, `review_warning` and `attempt_id`. Expected durable bundle/attempt reference columns were absent; the actual retained bundle carries an independent attempt UUID. This proves a missing index/read connection, not missing evidence persistence.
- Failure scenario: an active version has a validated manifest but no authoritative bundle index. Serving `diagnostics=[]` would treat unknown evidence as an empty result. The new reader instead returns `dependency_unavailable` before staging.
- Recommended correction implemented as a draft: `0004_preview_evidence` adds nullable paired `evidence_bundle_sha256` and `validation_attempt_id` to `data_versions`. It does not move/regenerate evidence, backfill a version or publish anything. The separate publication writer must verify and freeze these references with the matching validation step/manifest/checkset/warning identity before activation.
- Validation still required: migration application and constraints against disposable PostgreSQL, then separately approved retained migration/publication integration. The retained candidate remains unpublished. This turn did not inspect or mutate the live pointer. The recorded October 1–2 readback was not repeated.

## Checks and results

Commands ran from the repository root using the existing virtual environment:

```sh
backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_preview_*.py' -q
env -u TRINITY_TEST_DATABASE_URL -u TRINITY_TEST_QUERY_IMAGE backend/.venv/bin/python -m unittest discover -s backend/tests -v
```

Focused result: **64 passed**, no skips, 1.825 seconds. This includes the 28 existing Step 2 checks and 36 new checks. A separate early SQL-engine run passed all 10 checks.

Final regression result: **408 discovered/run, 356 passed, 52 skipped**, 41.710 seconds. Database/container opt-ins were explicitly unset. The skipped checks remain pending evidence, not passes. Existing offline SQL/auth/catalog checks passed.

Coverage includes actual temporary Parquet/DataFusion for all schemas, same-day entity paging, Unicode/leading-zero IDs, exact decimals/nulls, literal SQL-like IDs, protocol confusion, bound output, closed diagnostic evidence, current authority and debit ordering with controlled adapters, TestClient routing/headers, disconnect signaling and fake-supervisor cleanup failures. An existing connector freeze/validate/store run creates a synthetic bundle that the new reader accepts unchanged. That test uses an in-memory storage adapter, not real S3. A fresh interpreter verifies that the runtime imports no trusted auth, cursor/key, storage or PostgreSQL modules.

Initial test corrections: closed batch validation now rejects null `has_more`; a TestClient fixture needed a correctly shaped synthetic bearer; the synthetic producer temporary root needed `.resolve()` because macOS `/var` is a symlink; the existing route inventory now includes the implemented preview route. The first full run had only that stale route-inventory failure (404 discovered, 52 skipped). No failure was hidden by skipping a required test. The existing Starlette/httpx deprecation warning remains; no package was added or updated.

No formatter/linter/type checker is configured in `backend/pyproject.toml`. AST parsing and whitespace checks passed for all 23 changed/new Python files. `git diff --check` passed. All 309 local links/anchors and code fences passed across the seven changed/new Markdown documents. Final scoped diff review completed; existing evidence, decisions, findings and dependency files have no diff. A fresh locked installation was not performed.

## Delivery and understanding boundaries

Step 3 **code and offline integration** are implemented. Its retained authoritative-publication gate remains open: the index is not applied/populated and the separate writer is not supplied by preview. The default route cannot start a container. Step 4 real PostgreSQL, loopback HTTP, multi-process accounting/races, matching-image isolation/resource/cleanup acceptance and Step 5 retained-account operator evidence remain pending. Existing SQL container test expectations were aligned to the new envelope, but those tests were not run.

The common envelope also affects SQL: an old query image must fail closed until the matching image is built and explicitly tested. SQL grammar and public response are unchanged; source/offline regression evidence is not deployed SQL compatibility proof.

Human check, not yet observed: with generator keys `(2025-01-01, 01, 01)` and `(2025-01-01, 01, 10)` and limit one, the continuation stores the first complete key and returns the second row. It carries position, not permission. A Viewer still cannot use it for generator detail. No user understanding is claimed.

Done: Step 3 code, focused tests and scoped documentation; existing evidence preserved.
Pending: human diff review, retained provenance integration, and separately authorized Step 4 acceptance.
Blocker: preview delivery stays disabled until its migration/publication and matched-runtime prerequisites pass.
Next: [ME] review `PreviewService.prepare` in `backend/src/trinity/queries/service.py`.
