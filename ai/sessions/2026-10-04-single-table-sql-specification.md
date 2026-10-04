# One-table read-only SQL — specification

Date: 2026-10-04 (America/Merida)
Branch/base: `feat/catalog-permissions`, `fde733b`; no remote refresh.
Status: Specification drafted for review; design and implementation not authorized in this step.

## Objective and contributions

[ME] Alayala replied “continue” to the explicit question whether to approve the SQL proposal and draft its specification. This approves the proposal scope and authorizes specification drafting.

[YOU] AI drafted the [Human/LLM specification](../../sdd/single-table-sql/spec.md) with R01–R23 and S01–S28, using the current API/security/schema/backend contracts and existing catalog SDD format. Updated the proposal's status, appended its authorization history, added the README specification link and recorded this NOTES contribution. Existing uncommitted catalog work remains untouched.

## Evidence and refinements

Rechecked repository status, the SQL proposal and proposal session, catalog specification structure, query request/response schemas, Column/Cell/Diagnostic/Problem schemas, SQL status inventory, API error precedence, A19 requirements and current errors/manifest source. Prior-turn code tracing remains baseline evidence; no SQL runtime has appeared or been tested in this task.

The API explicitly requires applicable SQL-policy checks before returning no-publication. The specification makes this order observable: valid SQL without a publication returns data_unavailable, while disallowed SQL still fails policy. Whole-input validation precedes any manifest/data download and file registration.

D01 proposes exact first SQL syntax within A18/A19, including canonical identifiers, literal predicates, arithmetic, searched CASE and the selected function forms; unlisted syntax remains rejected. D02 proposes a rolling 60-second cross-process counter and explicit counted/excluded outcomes. D03 proposes execution timing, unit/label handling and default sort/null behavior. These are draft refinements, not accepted decisions or verified library capabilities. Their acceptance would require updating DECISIONS.md and relevant canonical prose. Numeric precision, parser configuration, persistence and container mechanics remain design/compatibility obligations.

No new dependencies, runtime implementation, migrations, retained database actions, containers, cloud requests, commits, pushes or branch changes occurred. The proposal authorization does not establish alayala's observed understanding of the implementation.

## Verification

Passed: 21 local Markdown file targets across the SQL proposal/specification and sessions; balanced fences and whitespace; unique sequential R01–R23 and S01–S28; QueryResponse field inventory and named error codes against OpenAPI; and `git diff --check`. Reviewed the new specification and focused supporting diff. SHA-256 checks confirmed all pre-existing files outside the four intended documentation edits are unchanged; prior NOTES and proposal-session content remain exact prefixes. Review clarified that the trusted runtime input can carry the approved SQL/local mapping, while public responses, runtime errors and logs must not expose them. No application tests ran because this is a documentation-only step. No engine, PostgreSQL, Docker, storage, operator or end-to-end SQL result is claimed.

Maintain data evidence — ongoing; synthetic examples are acceptance fixtures, not new outage observations or permission to publish live data.

## Review checkpoint

Done: draft specification, traceable acceptance scenarios and explicit proposed refinements.
Pending: alayala's specification review, followed by design/tasks if requested.
Blocker: none for this review; runtime compatibility and missing A19 execution foundations remain implementation gates.

Next: [ME] approve or correct the specification, including D01–D03.

## Viewer SQL restriction clarified

[ME] Alayala explicitly reaffirmed the catalog-style boundary: Viewer must not see the SQL button and must not be able to do anything that runs user-submitted SQL. [YOU] AI checked A16’s accepted Viewer navigation refinement, PRODUCT, API prose and `auth.permissions`: the existing policy excludes `sql:execute` from Viewer while retaining national dashboard support. No new role policy or canonical decision is needed.

Updated the proposal and Human specification, strengthened R02/S03, and added R24/S29. The specification now has 24 requirements and 29 scenarios; S29’s UI portion is explicitly later frontend acceptance. It requires no SQL button/menu/editor/Run control, denial of direct screen access, and separate 403 API denial before SQL parsing, rate accounting, slots, downloads or execution. Valid Viewer national dashboard/preview reads remain permitted.

This is a requested specification correction, not blanket approval of D01–D03, design or implementation. No source code, Docker files, dependency, database or remote state was changed. Existing concurrent work was preserved. Passed: focused diff review, local link targets, balanced fences/whitespace, unique R01–R24/S01–S29, `git diff --check`, unchanged hashes for all unrelated files, and exact preservation of prior appended history. No application or frontend tests ran because this correction changes requirements only.

## Specification approval and design/tasks authorization

[ME] Alayala requested continuation with tasks and design after the Viewer clarification. This approves the corrected specification, including D01–D03 and the UI/API restriction. [YOU] Recorded those refinements under A16/A19, aligned canonical API/security prose and drafted [design](../../sdd/single-table-sql/design.md) and [tasks](../../sdd/single-table-sql/tasks.md). Earlier pending-status entries remain historical. The [design/tasks session](2026-10-04-single-table-sql-design-tasks.md) records evidence and remaining gates; code, builds and runtime actions are not authorized by this request.
