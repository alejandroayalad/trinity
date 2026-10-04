# Catalog and permissions — SDD proposal

Date: 2026-10-04 (America/Merida)
Inspected branch/base: local `main`, `fde733b`; no remote refresh performed.
Working branch: `feat/catalog-permissions`, created from that base after alayala requested a branch.
Status: Proposal drafted; human review pending.

## Objective and authorization

[ME] Alayala asked whether step 5 completes the Analyst requirement, reviewed a proposed four-slice division, and requested the SDD proposal for slice 1: catalog and permissions. The selected outcome is national-only metadata for Viewer and all three analytical datasets for Analyst/Admin.

[YOU] AI traced the current source, canonical contracts and prior local-auth handoff, then drafted [the proposal](../../sdd/catalog-permissions/proposal.md) in the existing Human/LLM format. The current request covers the proposal only. It does not authorize specification, design, tasks, application implementation, commits or remote writes.

[ME] Alayala subsequently requested a branch for this change. [YOU] AI ran `git switch -c feat/catalog-permissions`; creation succeeded. This local branch request does not expand the proposal-only artifact boundary.

## Discovery and preservation

Repository status showed existing changes in FINDINGS, NOTES, connector normalization and two test files, plus untracked live-storage/decimal-fix sessions and live preparation evidence. Preserve this work. This task adds a proposal, this supporting session, a README index entry and an appended NOTES contribution; it does not modify application code. The requested branch was created in the same worktree, so unrelated changes remain visible and uncommitted there; branch creation does not isolate or include them in a commit.

Inspected `README.md`, `PRODUCT.md`, `CONTRIBUTING.md`, repository instructions, applicable A9/A15–A17/A19–A21 entries, API/OpenAPI/security/schema/backend contracts, existing SDD proposals and local-auth session records. Source inspection covered app registration, permissions, authentication dependencies/service, the dataset registry, publication and refresh readers, the database snapshot boundary, app-entry migration and relevant test scenarios.

`rg --files backend/src/trinity backend/tests` found no catalog package or catalog tests. `rg -n 'catalog' backend/src/trinity backend/tests` found only auth capability/schema references. `create_app` registers no catalog router. Current shared role checks, analytical schemas and publication metadata reads are reusable; their presence is not catalog acceptance evidence.

## Scope and corrections

A9 governs dataset metadata; A15 supplies the catalog location; A16/OpenAPI governs the response; A19 supplies role filtering and safe metadata; A20/A21 supplies implemented local authentication. The initial draft changed no canonical contract or accepted decision; the later navigation refinement below records the subsequent authorized update.

The public keys are `national_outages`, `facility_outages`, and `generator_outages`; internal registry and permission keys are shorter. The proposal requires an explicit mapping and preservation of the single permission policy. Catalog works before publication, without file downloads or analytical execution. It must distinguish no publication from a dependency failure.

The `last_refresh` selection rule needs specification review. AI recommends greatest `run_seq`, including an unfinished/failed run, while readiness remains tied to the active publication. This interpretation is proposed, not accepted. Query publication pinning and container isolation remain later slices; this slice needs only a consistent metadata snapshot.

## Checks and evidence limits

Passed: 11 local Markdown targets across the two new documents and new README/NOTES links; new-document whitespace and balanced fences; public dataset names and catalog/freshness field inventory against OpenAPI; `git diff --check`. Reviewed the proposal and supporting changes. These are documentation checks, not endpoint or full OpenAPI validation.

The first preservation check stopped because FINDINGS changed concurrently after the initial inspection. Later status/diff also showed concurrent README, backend README and live-evidence updates. No rollback was attempted. A focused check confirmed all three pre-existing changed source/test files remain byte-identical to the inspection baseline, and all prior NOTES content remains an unchanged prefix. The task's README edit is only the catalog proposal index row; other changes are not attributed to this proposal.

No application tests, PostgreSQL commands, migrations, builds, cloud requests or persona provisioning ran for this proposal. Historical test results were not rerun. Maintain data evidence — ongoing; this task produced no new anomaly evidence.

## Review checkpoint

Done: bounded catalog proposal with baseline evidence, acceptance examples and explicit exclusions.
Pending: human review, then specification if approved.
Blocker: none for proposal review; `last_refresh` ordering remains a proposed detail for specification review.

Next: [ME] review the Human section of the proposal and approve or correct its scope.

## Accepted Viewer navigation refinement

[ME] Alayala requested that Viewer see data through the national dashboard without a Catalog button, then explicitly asked to update the proposal after AI recommended retaining national metadata API access. [YOU] AI clarified that national data includes one row per date and the dashboard includes cards, trends and table values. The user authorized this navigation update; the full proposal and later SDD artifacts remain under review.

[YOU] Updated the proposal's Human explanation, API example, acceptance boundary and LLM guidance. Recorded the accepted presentation refinement under A16 and linked it from PRODUCT and the API human overview. Viewer retains `catalog:read` and `preview:national`; API shapes and server permissions do not change. Frontend navigation and direct-screen access checks remain later work. No frontend or backend code changed.

Validation passed: four newly introduced local links/anchors, edited-line whitespace, balanced fences and `git diff --check`. Reviewed the six-file diff against the start-of-turn copies. SHA-256 comparison confirmed seven untouched files, including the existing source/test changes and OpenAPI, remain unchanged. No application or browser tests ran because this update changes documentation only.

## Subsequent specification authorization

[ME] Alayala requested “continue with specs please.” This authorizes the next SDD artifact and supersedes the proposal-review-pending checkpoint above. [YOU] AI updated the proposal status and drafted the [specification](../../sdd/catalog-permissions/spec.md). The [specification session](2026-10-04-catalog-permissions-specification.md) records checks and remaining review details. This authorization does not extend to design, tasks or implementation.
