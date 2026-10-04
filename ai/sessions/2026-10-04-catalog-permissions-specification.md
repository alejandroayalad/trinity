# Catalog and permissions — specification draft

Date: 2026-10-04 (America/Merida)
Branch: `feat/catalog-permissions`
Inspected base: `fde733b`, with existing working changes retained.
Status: Specification drafted for review; no implementation.

## Objective and contributions

[ME] Alayala requested “continue with specs please” after reviewing the proposal and selecting dashboard-only Viewer navigation. This authorizes specification drafting. It does not authorize design, tasks, code, migrations, runtime services, commits, pushes or a PR.

[YOU] AI read the current proposal, latest supporting record, existing Human/LLM specification format, repository status, API/OpenAPI/security/data contracts and relevant current auth/transport/publication/dataset code. Drafted [spec.md](../../sdd/catalog-permissions/spec.md), updated the proposal's authorization status and README index, and recorded contributions in NOTES. No canonical decision or API schema was changed by this drafting step.

## Requirements and corrections

R01–R15 specify the authenticated catalog endpoint, shared permissions, public/internal key mapping, canonical columns/units/filters, national metric metadata, consistent publication/freshness, safe failures and no analytical work. S01–S24 define evidence; S24 belongs explicitly to the later frontend slice. A9/A15–A17/A19–A21 remain authoritative, including the accepted A16 Viewer navigation refinement.

The catalog's lack of a visible Viewer button does not remove national metadata API permission. No publication remains a successful static catalog response; database failure cannot masquerade as that state. Catalog metadata consistency does not claim query-runtime publication pinning or container isolation.

D01 carries forward the proposed `last_refresh` interpretation: greatest `run_seq`, including failed/unfinished runs. It remains pending specification review, distinct from the already accepted navigation rule. A stable national/facility/generator output order is an AI-authored specification detail. No unreviewed freshness interpretation was added to DECISIONS as accepted.

The current transport rejects query strings and nonempty GET bodies before route authentication. The spec preserves that ordering rather than demanding an incompatible error precedence for requests with multiple faults. It also distinguishes offline route tests from real PostgreSQL snapshot/session evidence and synthetic state from live publication.

## Preservation and checks

The worktree already contains unrelated findings, live-preparation evidence, parser/test changes and their documentation. This step is limited to the new specification/session plus proposal, README, NOTES and prior-session handoff updates. No backend source, tests, dependency, lockfile or canonical API response was edited.

Passed: 14 new local Markdown links; changed-line whitespace and balanced fences; unique sequential R01–R15/S01–S24 IDs; scenario coverage of every requirement; response-field, dataset-key and error-code inventory checks against OpenAPI; `git diff --check`. Reviewed the new specification/session and focused supporting-document diffs. SHA-256 comparison confirmed nine untouched files, including the canonical contracts and unrelated parser/test changes, still match the start-of-turn snapshot. These checks are static documentation validation, not full schema or runtime acceptance.

No application test, migration, real database command, browser check, EIA/S3 request or container execution ran for this specification.

## Review checkpoint

Done: catalog specification with requirement and scenario IDs; proposal approval and links recorded.
Pending: specification review, including D01; design follows only after authorization.
Blocker: none for reviewing the draft; D01 must be settled before implementation.

Next: [ME] review the Human section and D01 in the specification.

## Subsequent approval and design/tasks authorization

[ME] Alayala requested “continue with design and tasks, approve it.” The specification and D01 are now approved, superseding the pending-review checkpoint above. [YOU] AI recorded the freshness refinement under A16 and drafted the next two artifacts. The [design/tasks session](2026-10-04-catalog-permissions-design-tasks.md) records this stage. Implementation remains a separate authorization; historical drafting checks are not new runtime evidence.
