# Catalog, SQL and preview branch reconciliation

Date: 2026-10-04. Decisions: A9, A16, A19–A21.

## Request and contributions

[ME] Alayala requested reconciliation of `feat/catalog-permissions` with its delivery branch, retention of committed/pushed catalog and SQL work, and one clean continuation branch for preview.

[YOU] Inspected both histories and the dirty source checkout. Preserved 39 changed/new files in a local safety snapshot and Git stash before merging. Merge `f503f60` retains both parents: SQL history through `765df37` and catalog delivery through `a7e9099`, including newer main Docker/live-data commits. No rebase, squash, force push or main-branch merge is part of this task.

Six conflicts required reconciliation: both routes in `main.create_app`, both paths in the route inventory, SQL tables in the shared PostgreSQL fixture reset, the catalog auth-fixture refactor, and both README/NOTES histories. Two focused health checks passed immediately after resolution. The catalog code and original catalog evidence from the dirty snapshot match the delivered files byte-for-byte. Preview SDD and its accepted refinements were restored separately, rather than replacing newer delivery documents with older copies. The old uncommitted Docker note described a distinct catalog-inclusive run, so its exact contents are retained under `2026-10-04-docker-catalog-initial-verification.md`; the newer Docker-only verification remains in the original path.

## Continuation organization

Use **`feat/catalog-permissions`** for subsequent work. The delivery branch is synchronized to the same final commit for comparison and retained history; it is no longer a separate workstream. The original working directory remains the continuation checkout. No branch or worktree is deleted.

- Catalog: `sdd/catalog-permissions/README.md` and its implementation/tests.
- SQL: `sdd/single-table-sql/tasks.md`, `backend/SQL.md` and committed policy/runtime/service/tests.
- Preview: `sdd/dataset-preview/{proposal,spec,design,tasks}.md`; planning is preserved, preview code has not been implemented by this reconciliation.
- History: `ai/sessions/README.md` includes the catalog, SQL and preview themes while retaining dated filenames.

## Preview kickoff boundary

The first implementation gate is the request/cursor/response groundwork in preview tasks Step 2. Input is current identity plus strict date/entity/page/cursor fields; processing binds normalized filters and continuation to one publication; output is a typed preview operation and an authenticated next cursor. A Viewer presenting a facility cursor must receive the permitted safe denial before protected data access.

The existing design identifies complete frozen diagnostic provenance as a delivery dependency: current SQL response models permit empty diagnostics only and existing migrations do not provide the full `validation_results` producer/read model. This does not prevent pure preview parsing/cursor work, but it must be resolved before endpoint delivery. Existing SQL crash-race, deployed Compose and retained live-read evidence limits remain documented; a clean branch does not close those runtime gates. Viewer Catalog/SQL controls remain hidden by requirement and unimplemented in the later frontend slice.

No preview endpoint, signing key, cloud action, retained migration or new source-data finding was added. Maintain data evidence — ongoing. The local safety stash is retained as a recovery copy, not as uncommitted work on the continuation branch.

## Checks

Combined verification passed on the reconciled checkout:

| Check | Result |
|---|---|
| Full offline unittest discovery | 344 discovered; 292 passed, 52 opt-in checks skipped; 50.899 seconds. |
| Disposable PostgreSQL auth/catalog runner | All 70 checks passed, no skips; 82.126 seconds. |
| Disposable PostgreSQL + loopback HTTP + Docker SQL runner | All 11 checks passed, no skips; 26.511 seconds. |
| Immediate route/health check | Both checks passed; catalog and SQL are registered. |
| Documentation | 422 local links/anchors passed before the final evidence update; final link and whitespace checks repeated before commit. |
| Preservation | All 39 original changed/new paths are accounted for. SQL implementation, image definition and SQL migration match `765df37`; catalog implementation/tests match the delivered branch. |

Only owned disposable test clusters/containers were used. Five standalone real-container probes were skipped by offline discovery; they were not rerun in this reconciliation. The SQL integration runner did exercise real query execution and expired-container recovery. Earlier standalone container evidence remains in the SQL delivery record.

 The pre-existing `evidence/live-preparation/2026-10-04-october-1-2/tested-code.patch` has two whitespace-only patch-context lines. They are preserved as historical evidence; whitespace checks exclude only that unchanged imported artifact.


Done: histories merged, catalog/SQL checks passed, preview plans and both Docker records preserved.
Pending: preview Step 2 implementation kickoff; complete diagnostic provenance and existing runtime gates still apply to later delivery.
Blocker: none for a clean Git continuation; no preview implementation is claimed.
Next: [ME] continue on `feat/catalog-permissions` from preview tasks Step 2.
