# One-table read-only SQL — proposal

Date: 2026-10-04 (America/Merida)
Inspected branch/base: `feat/catalog-permissions`, `fde733b`; no remote refresh.
Status: Proposal drafted; scope review pending.

## Objective and contributions

[ME] Alayala selected the next slice: one-table read-only SQL, with SQLGlot checking the request before downloads and DataFusion executing it.

[YOU] AI treated “start this slice” as the proposal stage under the existing SDD workflow and stated that assumption. AI traced current permissions, publication metadata, dataset schemas, S3 adapter, route registration and migration inventory, then drafted the [Human/LLM proposal](../../sdd/single-table-sql/proposal.md). No specification, design, implementation or new accepted decision is claimed.

## Evidence and scope

Read repository instructions, README, CONTRIBUTING, PRODUCT, applicable A9/A15–A21 contracts, SQL API/OpenAPI, security/backend/schema sections, current FINDINGS context and catalog proposal/implementation records. Earlier memory was used only to locate SQL/security context; current files control this proposal.

Confirmed: current permissions already grant Analyst/Admin SQL authority; current schemas define all three public tables. `read_publication` supplies metadata but not query staging. `StorageOperation.verify` hashes downloaded candidate bytes without saving query files. `create_app` registers no query route.

Absence checks: backend file inventory and `rg --files backend/src/trinity backend/tests` show no `queries/` implementation or SQL tests; backend inventory contains no query Dockerfile. Migration table declarations contain no analytical reservation/rate or artifact-manifest tables. These observations identify implementation scope; no runtime defect or exploit is claimed.

Recommendation: carry the existing A19 staging, container, admission, output and recovery requirements into this SQL slice before enabling its endpoint. Policy/engine compatibility can be implemented and tested first, but is only partial completion. Exact parser grammar, artifact lookup, reservation/rate mechanics and container configuration remain specification/design work.

The proposal preserves the user-selected one-table scope and accepted function list. It does not add preview/frontend/refresh features or change publication rules. No new production dependency is proposed.

## Preservation and verification

Existing catalog changes remain on the same branch. This task adds the proposal and this session, one README index row and an appended NOTES contribution. No branch switch, commit, push, cloud request, retained-database operation or source-code change occurred.

Passed: eight local Markdown targets in the new documents, the three added README/NOTES links, balanced fences, new-document whitespace and `git diff --check`. Reviewed the proposal and the focused README/NOTES diff. SHA-256 comparison confirmed every pre-existing file other than README/NOTES is unchanged; README differs only by the new index row and prior NOTES content remains an exact prefix. Application tests were not run because this task changes documentation only. No engine, container or end-to-end SQL evidence is claimed. Maintain data evidence — ongoing; no source-data observation was produced.

## Review checkpoint

Done: proposal with current-code evidence, flow, failure examples and acceptance boundaries.
Pending: alayala's scope review; specification drafting if approved.
Blocker: none for proposal review; execution requires the missing A19 runtime foundations.

Next: [ME] approve or correct the proposed SQL scope before specification drafting.

## Subsequent specification authorization

[ME] Alayala replied “continue” to the explicit proposal-approval question. This approves the proposal scope and supersedes the pending-proposal checkpoint above. [YOU] AI drafted the [specification](../../sdd/single-table-sql/spec.md); the [specification session](2026-10-04-single-table-sql-specification.md) records the new requirements, proposed refinements and documentation checks. Design, tasks and implementation remain later authorization stages.
