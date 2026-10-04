# Parquet preparation — SDD proposal

Date: 2026-10-03 (America/Merida)
Mode: discovery and proposal; no implementation.

## Objective and contributions

[ME] Alayala requested an SDD folder and a branch for the Parquet slice. He supplied the intended scope: schemas, strict parsing, candidate files, manifest freeze, all eight required checks, diagnostics, immutable S3 storage, one preparation command, tests and instructions. He asked to follow the Obsidian proposal pattern.

[YOU] AI inspected the clean repository at `fc7375a` on `main`, current contracts and connector code, then created local branch `feat/parquet-preparation` and [the proposal](../../sdd/parquet-preparation/proposal.md). It used the vault's `IX-13417/SDD/proposal.md` and `LocalPerf/SDD/proposal.md` as structure references: draft/approval status, Human/LLM sections, scope, evidence, risks and staged progression. No vault files were changed or copied into this repository.

## Discovery and boundaries

Read `README.md`, `AGENTS.md`, relevant A9/A13–A17 decisions, `FINDINGS.md`, `PRODUCT.md`, `docs/schema.md`, `docs/backend.md`, relevant S3/security rules and the latest connector session. Inspected `retrieve_all`, retrieval records, the extraction command, page validation, dependency pins and test inventory.

Existing extraction returns sanitized evidence and successful collections. The typed Parquet/manifest/validation/S3 modules selected by A15 are absent from the inspected `backend/src/trinity/` inventory; no existing `sdd/` or `SDD/` directory was present. The proposal records the exact expected module paths and discovery evidence. No implementation defect review was requested.

The source of truth is current `docs/schema.md`, not the older vault contract. Eight required checks produce 16 result rows in one attempt. A16 warnings/publication rules remain unchanged. A14 keeps application-owned S3; local staging is not a replacement storage decision. PyArrow and boto3 are already pinned, so no new dependency is proposed.

Correction/clarification: proposal is the first authored SDD artifact for this slice after discovery. The requested implementation list defines its scope; it does not mark any feature implemented. Unlike older memory, the current repository already contains bounded extraction and local-authentication contracts. No old connector SDD was restored.

Concurrent update: final inspection found existing commit `9fc0497` in the shared checkout, after initial discovery at `fc7375a`. It adds the [first live-run evidence](../../evidence/2026-10-03-first-live-eia-run.md). AI read and preserved those changes and corrected this proposal's evidence baseline: the separate run records 59 offline tests, two live checks and a successful one-day extraction. This task did not execute that run or create its commit. Full-window validation remains pending; the underlying JSONL was not inspected here.

## Checks and results

- Before edits: clean working tree on `main`; separate local-authentication worktree identified and left untouched.
- Proposal consistency: mapped the supplied scope to A9's types/nullability, V01–V08, 16-row requirement, D01–D09, manifest freeze and immutable-storage boundaries.
- Documentation checks: local links/anchors, Markdown fences, changed-file whitespace and final diff review passed. No backend code, dependencies or canonical contracts changed.
- No runtime tests ran for this documentation-only change. The prior connector session reports 59 passing offline tests; that historical result is not a new test run.
- This task made no live EIA request, S3 operation, credential access, commit, push, PR or merge. The concurrent pre-existing live-run commit is distinguished above.

## Open questions and next action

At the initial handoff, proposal review was pending; approval and specification follow below. Exact command/window semantics, canonical manifest/fingerprint encoding, durable failure handling, stage budgets and S3 protection/configuration remain design work. Full-window preparation and real S3 verification remain pending after implementation; the separate one-day extraction is already recorded.

Done: local branch, proposal, index and authorship/evidence notes.
Pending: alayala's proposal review, then specification/design/tasks and implementation.
Blocker: none for proposal review.

Initial next action: [ME] review the proposal's Human section and accept or correct its scope. Completed by the approval below.

## Proposal approved; specification drafted

[ME] Alayala stated, “proposal reviewed and agreed continue with spec please”. This approves the proposal's scope and direction and requests the next SDD artifact. It does not claim demonstrated implementation understanding or executed validation.

[YOU] AI preserved the uncommitted proposal work on `feat/parquet-preparation`, reread the current contract and inspected the vault's `IX-13417/SDD/spec.md` for the established structure. It updated the proposal status and drafted [spec.md](../../sdd/parquet-preparation/spec.md) with Human/LLM sections, R01–R14 requirements, S01–S38 acceptance scenarios, per-scenario traceability and required evidence. No vault content was modified. Existing accepted decisions remain canonical; no new decision ID was added.

Clarifications: warning-bearing candidates may complete preparation/storage while awaiting later Admin publication approval. Required validation needs exactly 16 matching result rows. A pre-manifest parsing failure cannot fabricate a successful attempt. Partial uploads, incomplete diagnostics and interrupted validation never count as success. Canonical encoding, exact command syntax, additional numeric lexical forms, persistence protocol and S3 write mechanism remain design work.

Checks: local Markdown links/anchors, fences/whitespace, unique requirement/scenario IDs, scenario-to-requirement coverage and final diff review passed. Canonical contracts, backend code, dependency files, existing live-run evidence and data findings were unchanged. No runtime tests or acceptance scenarios ran for this documentation-only work.

Done: proposal approval recorded; draft specification and index/authorship updates.
Pending: specification review, then design.
Blocker: none for specification review; runtime acceptance remains untested.

Next: [ME] review the specification's Human section and expected outcomes.

## Full-window coverage clarification

[ME] Alayala requested explicit equality of all three dataset date sets to the full requested window before specification approval. He also requested a minimal `design.md` and small, independently testable implementation steps.

[YOU] AI clarified R07: the distinct saved-file date sets must each equal every date in the inclusive requested window, as measured under R06. S12 now includes both detail datasets omitting October 2 from an October 1–3 request while national retains that day; V04 must fail even though the detail date sets match. The scenario also covers full coverage, national-only omission, individual detail omissions, all-route omission and an extra date. Per-entity daily presence is still not required. This makes the existing canonical V04 requirement explicit; no accepted decision changed.

The design handoff records the requested minimal scope and testable steps. No design, implementation or runtime acceptance test was performed in this clarification. Specification approval remains pending.

Checks: canonical V04 consistency, local links/anchors, Markdown fences, whitespace, unique R01–R14/S01–S38 IDs and the focused diff against saved pre-edit files passed. Runtime tests were not run because only documentation changed.

Next: [ME] confirm that the clarified R07 and S12 express the intended coverage rule.

## Minimal design with coverage clarification pending

[ME] Alayala requested rolling back the full-window clarification, expressed approval of the specification and asked to continue with design. His earlier constraints remain: minimal design and small, independently testable implementation steps.

[YOU] AI traced the requested rollback against `docs/schema.md`: V04 requires national to cover every requested day and detail date sets to equal national; V07 requires both detail totals to reconcile with national each day. Matching detail date sets alone cannot satisfy those requirements when both omit a national day. AI asked whether to retain rejection or revise coverage/reconciliation, and left the dependent text unchanged pending the answer. This is a clarification of conflicting intended outcomes, not a refusal to proceed or an inferred approval gate.

[YOU] AI drafted [design.md](../../sdd/parquet-preparation/design.md) for the independent mechanisms: one command reusing extraction, exact conversion, canonical identities, saved-file validation, immutable storage, durable failure evidence and finite budgets. Five proposed implementation steps map to existing acceptance scenarios. Coverage remains expressly unresolved. Command syntax, lexical grammar, writer options, storage protocol and resource defaults are proposed design details, not separately accepted decisions or tested capabilities.

Read current AGENTS/README, specification/proposal, schema/backend/security contracts, applicable decisions, findings/product context and connector code. Reviewed official Arrow writer and AWS conditional-write/policy documentation, linked in the design. No storage provider was chosen, credential accessed, cloud object written, code implemented, test run, commit made or remote state changed.

Checks: 110 local links/anchors across touched documents, balanced fences, whitespace and unique R01–R14/S01–S38 IDs passed. Reviewed the new design and focused pre-edit diff, including preserving the unresolved coverage text. Runtime acceptance remains pending; no backend tests ran for this documentation-only change.

Next: [ME] answer whether a shared missing detail day should still fail the candidate under the existing contract.

## Coverage confirmed; specification approved

[ME] Alayala supplied an image with the explicit October 1–3 example: national contains days 1, 2 and 3; facility and generator contain days 1 and 3. Its stated outcome is “This must fail.” The image distinguishes dataset-level daily coverage from individual facility/generator membership. This resolves the prior rollback ambiguity in favor of full-window coverage and completes his previously expressed specification approval.

[YOU] AI retained the approved R07/S12 and canonical A9/V04/V07. It completed the design algorithm: generate the inclusive requested date set, compare each saved dataset's distinct dates, report missing/extra dates per dataset and require one national row per day. Updated current approval/gate text in proposal, specification, design and README; preserved earlier discussion as history. The image was read in the conversation and not copied into the repository. This is confirmation of the existing rule, not a new decision or source-data anomaly.

Checks: 120 local links/anchors, Markdown fences/whitespace, unique requirement/scenario IDs, current coverage status and focused diff review passed. No runtime tests ran because this update changes documentation only.

Done: coverage resolved; specification approved; design ready for review.
Pending: design review, then tasks and implementation. Acceptance scenarios remain unexecuted.
Blocker: none for design review.

Next: [ME] review the Human section of `sdd/parquet-preparation/design.md`.

## Step 1 implementation handoff

Alayala authorized schemas/exact parsing only, with three design clarifications and a human diff review before Step 2. The [Step 1 session](2026-10-03-parquet-schemas-exact-parsing-step-1.md) records the bounded implementation, 17 focused/76 total passing offline tests and the current review gate. [tasks.md](../../sdd/parquet-preparation/tasks.md) derives the five existing steps. Prior draft-stage statements above are historical; later steps remain unimplemented.
