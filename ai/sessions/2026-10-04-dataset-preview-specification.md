# Dataset preview specification — October 4, 2026

## Objective and contributions

[ME] Alayala approved the preview proposal by asking “Write the spec.” SQL implementation continues in another terminal. This request authorizes specification drafting only.

[YOU] AI rechecked repository status, the approved proposal, current API/OpenAPI and A9/A16/A19 contracts, existing catalog/SQL SDD patterns and the proposal record. It drafted [spec.md](../../sdd/dataset-preview/spec.md) with 24 requirements and 31 traceable acceptance scenarios. It updated the proposal status and README index, and appended NOTES and this evidence record. No SQL or other production code was changed by this workstream.

Inspected branch: `feat/catalog-permissions`; HEAD `e851e28`. Concurrent SQL work now includes an analytical-admission migration/repository and publication-pinning changes. The proposal's absence inventory was historical; this specification explicitly refreshes that observation without treating new files as verified runtime implementation. No shared implementation was edited or reset.

## Specification result

Input → flow → output: authenticated dataset request and strict scalar date/entity/page fields → current authorization, shared rate policy, authenticated cursor and one publication → reserved isolated file execution → exact bounded PreviewResponse and safe continuation. Failure: a previously authorized Analyst cursor does not grant detail access after a downgrade to Viewer.

The existing API already determines the endpoint, roles, columns, date defaults, page caps, complete-key order, source-value preservation, signed cursor/publication binding and canonical errors. The specification makes them testable, and distinguishes a published empty match from no publication, missing files or a broken continuation.

Three AI-authored refinements remain proposed for human review:

- D01: strict scalar query shape, duplicate rejection and exact date/page-size interpretation, with exact source ID preservation.
- D02: debit the shared rolling analytical counter after current permission and primitive shape checks, before semantic filter/cursor/publication checks. The full table states which failures retain the debit. This does not change SQL's accepted counting rule.
- D03: equivalent effective request settings, publication comparison before default-dependent matching, no time-only cursor expiry, stable key across restart, retired key rejection, and current authorization on every page.

No refinement was added to DECISIONS.md as accepted. Approval will precede the canonical A16/A19 update and design/tasks. Cursor cryptography/encoding, runtime message construction, shared provenance and concrete executor integration remain design work. No new dependency was selected.

## Verification and evidence boundaries

Documentation checks passed: `git diff --check`; 18 local links/anchors and balanced fences across four preview artifacts; unique R01–R24/S01–S31 IDs and coverage of every requirement; calendar-default/leap-year examples; the six query parameters and nine required response fields against OpenAPI. Focused review checked scope, rate/error ordering, cursor/publication races, keyset continuity and evidence boundaries. No application tests, HTTP/database calls, engine execution, container operations, migrations, builds, credential prompts or cloud actions ran for this specification. The scenario matrix describes future checks, not test results.

Offline tests, real database/HTTP/container checks and alayala's retained-account operator check remain three separate evidence categories. Database or catalog success alone cannot prove preview isolation or timeout cleanup. The existing operator check had no active publication; it does not establish returned outage records.

Maintain data evidence — ongoing. No data was fetched and no anomaly/coverage claim changed. No commit, push, PR, source-code or existing SQL SDD change was performed by this workstream. Unrelated working changes and concurrent SQL work were preserved.

## Checkpoint

Done: detailed preview specification, 24 requirements and 31 acceptance scenarios, with three proposed refinements explicit.
Pending: review/approval of D01–D03 and the specification, then design/tasks.
Blocker: none for specification drafting. Runtime delivery still requires verified shared execution and an authorized publication.
Next: [ME] approve or correct the preview specification.

## Specification acceptance

Alayala confirmed D01–D03 after the specification review request: strict inputs and compatible entity filters; one shared SQL/preview request counter with a debit retained after later filter/cursor failure; and stable filter/publication pagination with fresh permissions and no time-only cursor expiry. “Installation” maps to the existing `facility` field when selecting a specific `generator`; the API name and unfiltered detailed-dataset permission remain unchanged.

[YOU] Recorded acceptance under existing A16/A19, aligned API/security prose and specification/proposal/README status, and preserved the earlier proposed wording above as history. Acceptance does not authorize design/tasks, implementation or runtime actions by itself. SQL code and SDD in the other terminal were not edited. No OpenAPI field, dependency or permission matrix changed. Acceptance-update checks passed: `git diff --check`; 15 local preview links/anchors and balanced fences; preserved 24 requirements/31 scenarios; accepted-status consistency and unique A16/A19 placement. The focused diff review confirmed documentation-only edits for this turn. No runtime test was run for this decision-recording change.

Done: specification and D01–D03 accepted and reconciled with canonical contracts.
Pending: preview design/tasks authorization and later implementation/runtime proof.
Blocker: none for the accepted rules.
Next: [ME] request preview design/tasks when ready.

## Subsequent design/tasks authorization

Alayala requested continuation after D01–D03 acceptance. The [design/tasks session](2026-10-04-dataset-preview-design-tasks.md) records the two drafted artifacts and their checks. Earlier pending statements retain their stage history; implementation and runtime actions are still not authorized.
