# Figma mockups, brand and planned Claude handoff

## Objective and authority

On October 4, 2026, alayala supplied eleven interface screenshots and one Trinity
brand board. He stated that he made the mockups himself in Figma, that the earlier
brand was created with ChatGPT, and that he plans to pass both to Claude. He asked
for this workflow and attribution to appear in Engineering Notes and project
documentation. This task authorizes documentation and preservation of the supplied
references; it does not authorize frontend implementation or remote delivery.

## Contributions and evidence limits

[ME] Alayala created the Figma mockups himself, supplied the screenshots and brand
reference, and selected the planned handoff. Authorship is recorded from his
explicit statement. The screenshots show the supplied design; the native Figma
file, editing history and earlier ChatGPT conversation were not inspected.

[YOU] ChatGPT contributed the earlier brand reference, as reported by alayala.
Codex inspected the current repository and documentation, recorded this attribution,
retained exact copies of the supplied images, and linked the current guidance.
Claude is the planned recipient. No Claude adaptation or implementation was
supplied or verified in this session.

## Supplied references

The image numbers match the order in alayala's message. Repository copies retain
the original bytes and use descriptive names for a portable handoff.

| Image | Reference | Attribution |
|---|---|---|
| 1 | [Schedule settings](../../docs/design-reference/2026-10-04/01-settings.png) | Alayala, Figma |
| 2 | [Refresh run and candidate review](../../docs/design-reference/2026-10-04/02-refresh-review.png) | Alayala, Figma |
| 3 | [Refresh history](../../docs/design-reference/2026-10-04/03-refresh-history.png) | Alayala, Figma |
| 4 | [SQL Explorer with table panel](../../docs/design-reference/2026-10-04/04-sql-tables.png) | Alayala, Figma |
| 5 | [SQL Explorer results](../../docs/design-reference/2026-10-04/05-sql-results.png) | Alayala, Figma |
| 6 | [Plant preview and missing outage](../../docs/design-reference/2026-10-04/06-plant-preview.png) | Alayala, Figma |
| 7 | [Catalog](../../docs/design-reference/2026-10-04/07-catalog.png) | Alayala, Figma |
| 8 | [Dashboard with facility contributions](../../docs/design-reference/2026-10-04/08-analyst-dashboard.png) | Alayala, Figma |
| 9 | [National dashboard with Viewer navigation](../../docs/design-reference/2026-10-04/09-viewer-dashboard.png) | Alayala, Figma |
| 10 | [Local account login](../../docs/design-reference/2026-10-04/10-login.png) | Alayala, Figma |
| 11 | [No publication state](../../docs/design-reference/2026-10-04/11-no-publication.png) | Alayala, Figma |
| 12 | [Trinity brand board](../../docs/design-reference/2026-10-04/12-trinity-brand.png) | Created with ChatGPT, per alayala |

The brand board shows the Trinity symbol and wordmark, “Nuclear Outage Explorer,”
“Three levels. One clear view.” and national/facility/generator labels. Its printed
palette is `#243237`, `#F8642B`, `#1E1D1D`, and `#F0F0F0`. These are the labels on
the supplied board, not sampled pixel values or a complete production token set.
No font family, editable vector asset or separate photograph source was supplied.

## Handoff and decision boundaries

[A25](../../DECISIONS.md#a25--figma-design-and-brand-handoff) records the selected
direction. Preserve alayala's layouts and flows while applying the supplied brand.
Record any later Claude design changes and generated code as separate contributions.
Follow [AGENTS.md](../../AGENTS.md#design-authorship-across-documents) for attribution
across documents and [NOTES.md](../../NOTES.md#figma-mockups-brand-and-claude-handoff--october-4-2026)
for the evaluator-facing record.

A9/A16/A19/A20 and the current contracts retain authority over schemas, roles,
missing observations, SQL and publication. For example, the SQL screenshots show
`facility_name` in the query and `facilityName` in the table panel. Read
[the canonical schema](../../docs/schema.md) and [API contract](../../docs/api-contract.md)
to resolve names before implementation; do not copy inconsistent mock labels into
an API or query contract. This is a handoff observation, not a runtime defect.

Dates, row counts, outage values, durations and publication/run IDs in the mockups
are illustrative. They are not new EIA findings, complete state coverage or proof
that the pictured interactions work. Final styling, frontend framework and
responsive/accessibility behavior remain to be specified and verified.

## Corrections and verification

The product note previously left visual styling wholly open. It now identifies
the selected references while retaining the open status of final styling and
frontend technology. Historical sessions and unrelated data/backend documents
retain their original scope; shared instructions apply the attribution rule to
all future documents that describe this work.

All twelve repository image copies matched their supplied originals by SHA-256.
All 40 added local links and heading anchors resolved; accepted decision IDs are
unique. The final documentation diff was reviewed and `git diff --check` passed.
No application, browser, Figma or accessibility test is claimed. No code, dependency,
API schema, data finding or remote state was changed.

## Checkpoint

Done: human/AI attribution, selected reference direction and portable image inventory.
Pending: alayala's handoff to Claude and review of the resulting branded design.
Blocker: none for this documentation task.

Next action: [ME] Give Claude this session record together with the Figma source.

## Subsequent Git delivery authorization

[ME] Alayala subsequently requested commit and push to the branch. [YOU] confirmed
the current branch is `frontend` and reviewed the complete documentation diff.
The attribution updates and twelve reference images form one focused delivery
commit. This supersedes the earlier remote-delivery restriction for this change;
frontend implementation and a pull request remain outside this task.
