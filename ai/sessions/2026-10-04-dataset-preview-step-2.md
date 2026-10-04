# Dataset preview Step 2 — October 4, 2026

## Objective and authority

[ME] Alayala authorized Step 2: input validation, signed cursors and response models. An active publication is not needed for this work. He explicitly retained publication linkage as a prerequisite for real preview data and required the candidate to remain unpublished until that integration is implemented and verified.

[YOU] Implemented pure components and offline tests on `feat/catalog-permissions`, inspected HEAD `d8210b4`. Existing evidence-correction edits were preserved. Existing SQL source/tests, routes, migrations, dependencies and saved preparation evidence were not changed. No commit, push, database/cloud call, actual secret configuration or publication mutation occurred.

References: A9/A16/A19 and accepted D01–D03 in the [specification](../../sdd/dataset-preview/spec.md); [design](../../sdd/dataset-preview/design.md); [tasks](../../sdd/dataset-preview/tasks.md). Maintain data evidence — ongoing. Synthetic test records are not new findings or completeness proof.

## Input, flow, output and failure

Input: decoded query pairs plus a currently authorized principal, or a cursor with explicitly supplied test keys and publication metadata. Flow: primitive parsing → future committed shared rate debit → semantic checks → authenticated cursor and publication comparison → resolved filters → validated exact response. Output: immutable typed input, an authenticated complete-key position, or a bounded closed preview response. The service, actual debit and publication read are not wired yet.

Failure example: two `limit` parameters fail primitive parsing before the future debit. A well-shaped generator filter without its facility parses, then fails semantic validation after the future debit. An altered cursor fails authentication before its JSON payload is parsed. These tests establish helper boundaries, not actual PostgreSQL rate accounting.

## Implementation

| File | Responsibility and evidence |
|---|---|
| [preview.py](../../backend/src/trinity/queries/preview.py) | Shared dataset authorization; duplicate-preserving strict parsing; independent missing-date defaults; semantic filter/range checks; exact IDs and complete-key ordering. |
| [cursors.py](../../backend/src/trinity/queries/cursors.py) | Bounded canonical HMAC-SHA-256 cursors; MAC before JSON; exact purpose/schema/publication/filter bindings; lazy bounded secret-safe key configuration; restart/rotation without time-only expiry. |
| [preview_schemas.py](../../backend/src/trinity/queries/preview_schemas.py) | Closed response/diagnostic models; canonical columns; decimal/date/null preservation; lookahead and last-returned-key continuation; full-response byte cap; explicit diagnostic input. |
| [test_preview_unit.py](../../backend/tests/test_preview_unit.py) | 28 offline tests with synthetic roles/publications/keys; malformed and tampered input, Unicode and size bounds, page/key boundaries, exact decimal context behavior, diagnostic privacy and configuration-free imports. |

Design refinement: preview response models live in `queries/preview_schemas.py`, leaving existing SQL `queries/schemas.py` unchanged. No production dependency was added. Response diagnostics reuse the existing code/scope/message registry and reject Admin-only D09. Passing a diagnostics list does not establish frozen provenance; a future trusted reader must verify it.

`read_pinned_publication` in `publication/repository.py` joins active publication → publication event → version → refresh run and returns public metadata, manifest hash and contract version. Its result currently contains no bundle/attempt/checkset or diagnostic projection. That is the integration boundary, not proof of absent stored evidence. Reuse the [existing frozen evidence](../../evidence/live-preparation/2026-10-04-october-1-2/README.md); verify its connection to publication and preview in Step 3. No new live readback was performed.

## Checks and results

Commands from the repository root used the existing backend virtual environment (no fresh lockfile installation was performed):

```sh
backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_preview_unit.py' -v
env -u TRINITY_TEST_DATABASE_URL -u TRINITY_TEST_QUERY_IMAGE backend/.venv/bin/python -m unittest discover -s backend/tests -v
```

- Focused result: 28 tests passed in 0.632 seconds, no skips. The first run had one test setup error: a JSON-parser guard also intercepted configuration loading. Constructing the codec before installing that guard fixed the test; cryptographic behavior did not change.
- Regression result: 372 tests discovered/run, 320 passed and 52 skipped, 40.496 seconds. Runtime opt-ins were explicitly unset. The skipped database/container tests remain pending evidence; they are not passes. The existing offline auth/catalog/SQL tests passed alongside preview.
- Python compilation of the three new production modules passed. No formatter/linter/type-check command is configured in `backend/pyproject.toml`.
- Final diff review and `git diff --check` passed. All five new files passed whitespace checks; the four new Python files passed AST parsing. Across ten changed/new documents, all 330 local links/anchors and code fences passed. Existing tracked backend source files and dependency files have no diff.

These are pure/offline results. Existing temporary-file and engine fixtures in the broader suite do not prove preview container isolation, real PostgreSQL accounting, HTTP integration or retained-account operator behavior. No preview route, PreviewService, runtime operation or deployment was added.

## Human continuation example — review pending

For synthetic generator rows `(2026-09-03, 01, 1)` and `(2026-09-03, 01, 10)`, page size one returns the first key and signs that full key as the continuation position. Repeating the same filters, size and publication returns the second row. Changed publication returns `publication_changed`; a Viewer still receives `dataset_not_found` for the generator dataset even with that authentic cursor. A cursor supplies position, never permission. The automated example passed; no human explanation or operator check is claimed.

## Checkpoint

Done: Step 2 implementation and offline tests; existing frozen evidence preserved.
Pending: human review, authorized Step 3 service/runtime/publication integration, then real runtime and operator checks.
Blocker: none for Step 2. Publication linkage must be implemented and verified before real preview serving; the candidate remains unpublished and untouched by this work.
Next: [ME] review the continuation example and the separate evidence boundaries above.
