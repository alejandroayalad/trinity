# Dataset preview SDD proposal — October 4, 2026

## Objective and scope

[ME] Alayala requested SDD for filtered, paginated national, facility and generator records after the catalog first slice passed. He stated that SQL implementation continues in another terminal. The preceding request to implement the single-statement helper is not work for this preview turn.

[YOU] AI inspected current repository status, instructions, README, PRODUCT, applicable A9/A15/A16/A19–A21 contracts, FINDINGS, API/OpenAPI, backend structure, current auth/catalog/publication code, migration inventory and latest SQL pairing records. It drafted the [preview proposal](../../sdd/dataset-preview/proposal.md) using the existing Human/LLM format. Current branch was `feat/catalog-permissions`; inspected HEAD was `7d2e001`. Other work in the shared checkout remains outside this scope.

## Findings that shape the proposal

- Existing API behavior already fixes the preview route, roles, date/entity filters, default/max page size, complete daily-key ordering, authenticated cursors, publication-change restart and exact row-array response. No new product decision is recorded as accepted.
- Viewer keeps national preview API permission for dashboard support, with no Catalog/SQL navigation. Analyst/Admin can preview all three datasets. Hidden and unknown dataset keys both use the safe 404 response.
- The runtime boundary is broader than catalog: actual Parquet reads require the A19 shared rate/admission, checksum staging, isolated DataFusion container, deadline, confirmed stop and cleanup. Catalog's passing operator check had no active publication and proves none of those controls.
- SQL policy files are present and changing concurrently. Inspected `queries/` lacked the shared client, engine and container entrypoint; `main.create_app` had no preview router. The two migrations covered auth/app-entry, not analytical admission/artifact manifests. This is a time-bounded inventory, not a claim that the SQL terminal has done no work.
- Preview accepts typed filters, not user SQL. Its implementation must coordinate with the shared runner without editing or bypassing the user's SQL pairing gates. Entity-choice endpoints, dashboard aggregates and frontend work stay separate.

## Proposal boundaries and unresolved details

Input → flow → output: session and typed preview filters → dataset authorization and one active-publication snapshot → authenticated continuation and shared isolated execution → exact bounded row arrays plus optional next cursor. Failure example: Viewer asks for facility data and receives `404 dataset_not_found` before downloads, even with a copied cursor.

The proposal lists cursor configuration, preview rate-counting/error order, duplicate parameter handling, persisted artifact/diagnostic provenance and shared-runner readiness as later specification/design details. Existing contract requirements are not reopened as optional alternatives. No dependency or implementation mechanism was silently selected.

Three evidence categories stay separate: offline behavior tests; real database/HTTP/runtime tests with explicit container evidence; and alayala's retained-account operator check over a known publication. Passing one does not prove the others. No synthetic or retained candidate will be published merely to pass an operator check.

## Contributions, verification and limits

Changed files are only the new preview proposal, this unique session, the README index and the appended NOTES entry. No SQL source, tests or SDD, catalog behavior, canonical decision/API/security/schema contract, Docker configuration or findings file was edited by this workstream. Shared SQL commits/edits may continue independently.

Document verification passed: `git diff --check`; 6 local links/anchors and balanced code fences across both new documents; exact PreviewResponse field inventory and referenced error-code consistency; README/NOTES index targets. The focused review checked role/privacy boundaries, complete keys, default dates, cursor/publication semantics, shared limits and the separate evidence gates. No backend tests or runtime operations were run for this document-only request; planned acceptance is not an implementation result. Maintain data evidence — ongoing; no new source observation or anomaly arose. No commit, push, PR, build, migration, provisioning or cloud action was performed.

## Checkpoint

Done: preview proposal grounded in current contracts, with role/filter/page/publication rules and explicit shared-executor dependency.
Pending: proposal review, then detailed specification; design/tasks and implementation remain later gates.
Blocker: none for proposal drafting. Safe row execution depends on future verified shared runtime work and published artifacts.
Next: [ME] approve the preview proposal to authorize its specification.

## Subsequent specification authorization

Alayala requested “Write the spec,” approving the proposal and authorizing the [specification](../../sdd/dataset-preview/spec.md). The [specification session](2026-10-04-dataset-preview-specification.md) records the result. Earlier pending statements above describe the proposal handoff. Design/tasks and implementation remain later gates.
