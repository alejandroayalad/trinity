# Publication specification and design

Date: October 4, 2026. Mode: documentation; branch `feat/refresh-publication`.
Inspected HEAD: `4ce9a8f`, plus concurrent uncommitted Refresh Task 5 work.

## Objective and contributions

[ME] Alayala supplied the Build Publication proposal and requested specification
and design now, with tasks after his review. This explicit request advances both
document gates. It does not authorize implementation, commits or live activation.

[YOU] Read AGENTS/CONTRIBUTING, README/PRODUCT, A9/A16/A19/A20/A22/A23, schema,
API/OpenAPI, security and backend ownership, the Refresh integration contract and
current source. Drafted [specification](../../sdd/publication/spec.md) and
[design](../../sdd/publication/design.md); recorded provisional choices under P2
in DECISIONS.md and attribution in NOTES.md.

The supplied proposal was not present on disk: `rg --files sdd` listed the existing
Refresh SDD but no Publication folder, and `cat sdd/publication/proposal.md` returned
No such file. The prior proposal session and NOTES linked that expected artifact.
Saved the user's supplied proposal at [its existing linked destination](../../sdd/publication/proposal.md).
Preserved its historical status/gate text; the newer authorization and dependency
status are explicit in the specification/design and P2.

## Source corrections and decisions

Publication cannot reuse preparation claims: the original execution/registration
deadlines and selected validation step are immutable. The design proposes separate
publication-generation ownership and durable operation records, retaining source
receipt custody. The logical publication effect key is text while the existing
event column is UUID; the design specifies a deterministic UUID conversion.

`load_candidate` and the S3 read adapter currently collapse distinct failures into
generic safe errors. The design requires typed internal classification while
preserving existing outward behavior; generic dependency errors must not enable
retry of changed evidence. These are design integration requirements, not code
fixes made by this task.

During drafting, the concurrent [Task 5 handoff](2026-10-04-refresh-task5-receipt-routing.md)
was completed. It records 63 disposable-service checks and the migration chain
through uncommitted 0007. Updated the new documents to acknowledge that evidence
instead of continuing to claim the old pending integration status. No concurrent
backend changes or prior session history were edited. Task 5 results were not
independently rerun. Runtime publication and live source/storage remain separate.

## Checks and limits

Checks passed across seven authored/updated documents: 282 existing local Markdown
link targets, trailing whitespace/newlines and balanced code fences. Confirmed
20 unique ordered requirement IDs, 23 acceptance IDs, three command paths/actions
against local OpenAPI, a single P2 entry and no Publication `tasks.md`. The source-only
AST migration inventory has one head, `0007_refresh_registration`; no migration was
imported or executed. `git diff --check` passed. Reviewed the new documents and the
tracked diff, preserving concurrent Task 5 entries. Link checks cover file targets,
not external URLs or heading anchors.

Planned PUB-S01–23 are acceptance requirements, not executed tests. No backend test,
build, database, Redis, EIA/S3, retained migration or remote Git operation ran for
this task. No user understanding, implementation approval or live readiness is claimed.

## Review checkpoint

Done: proposal preserved; specification/design drafted; proposed choices recorded.
Pending: alayala reviews these documents before tasks are created.
Blocker for implementation: separate authorization; recheck the recorded Task 5
handoff against the final implementation baseline.

Next: [ME] review the proposed choices in the Publication design.
