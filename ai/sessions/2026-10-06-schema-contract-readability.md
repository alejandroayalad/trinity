# Data contract readability revision — docs/schema.md

Date: October 6, 2026. Mode: documentation implementation and review.

## Objective and contributions

- [ME] Alayala asked to make `docs/schema.md` better.
- [YOU] OpenCode read the full contract, its inbound links, the related decisions and the registration code. It restructured the document for reading without changing analytical fields, keys, metrics, checks, models or lifecycle rules, apart from the stale-text corrections below.
- Assumption that affects the result: "better" means easier to read and navigate, with every rule preserved. A9 remains the canonical contract. No decision is added or changed.

## Changes

| Change | Reason |
|---|---|
| Replaced the dense status paragraph with a status note and an amendment/precedence table (A9, A16, A19, A20, A22/A23/A27, A24). | Readers could not see quickly which decision changed which part. Each original statement remains in the table. |
| Added a contents line and a terms table (candidate, manifest, check set, validation attempt, review warning, admission slot, fence, generations, disposition, `not_reported`). | The contract uses these terms throughout without defining them in one place. Each definition restates existing contract text. |
| Added a Section 1 flow diagram and a Section 7 run-state diagram. | The flow and transition table were text-only. The state diagram has one edge for each table transition; the table remains the authority. |
| Split the 16-row Section 6 model table into five responsibility groups and gave the shared rules after it their own heading. | One table with very long cells was hard to scan. Rows are unchanged and keep their original order. |
| Moved the A23 execution and 0007 registration sections from after "Sources" into a new "Physical implementation amendments" subsection with A22 and A27. Moved application relationships and analytical admission before them. | Implementation addenda were appended after the sources list, outside their section. |

## Corrections of stale text

- **Registration budget.** The 0007 section said the registration deadline is "thirty seconds" from the first verification. The [A23 October 5 amendment](../../DECISIONS.md#a23--durable-refresh-dispatch-and-one-fenced-preparation-execution) raised it to 150 seconds. `CandidateRegistration.register` in `backend/src/trinity/refresh/registration.py` saves `LEAST(execution_deadline_at, clock_timestamp() + REGISTRATION_SECONDS)` once, with `REGISTRATION_SECONDS = 150`, and caps attempts at three. The contract now says 150 seconds and cites the amendment.
- **Source exports.** Section 1 said the source exports are absent from the repository. The reviewed two-year exports are bundled in `evidence/findings/inputs/`. The challenge PDF is still absent. The sentence now says both and also notes that A10–A13 and A17–A19 record the technology choices this document does not make.
- **Verification table.** Section 8 now says that it defines required behavior and does not report results.

## Verification

| Check | Result |
|---|---|
| Section reorder | A temporary script moved blocks by exact heading and stopped unless every original nonblank line remained. Result: 359 nonblank lines preserved. |
| Line preservation after all edits | Every original nonblank line remains except seven reviewed original lines: the status paragraph, the Section 1 boundary sentence, the Section 8 intro, two registration-budget lines and two demoted headings. |
| Inbound anchors | All 6 anchors that other repository files link to still resolve: sections 2, 5, 6, 7, `compressed-evidence-storage` and `failure-resolution-and-abandonment`. |
| Links inside the contract | 38 relative links and fragments resolved. |
| Formatting | Code fences balanced; `git diff --check` passed. |

Mermaid rendering was not checked with a renderer; the mermaid CLI is not installed and was not downloaded for this documentation edit. The two new diagrams use standard `flowchart` and `stateDiagram-v2` syntax. Check them in the GitHub preview. No application code, test, service or data changed.

## Next action

[ME] Authorized commit and push together with Vercel preparation on October 7.
[YOU] Rechecked line preservation, the 150-second constant and bundled inputs;
40 relative links/fragments across schema and deployment documents resolved.

Next: [ME] preview `docs/schema.md` on GitHub, especially the two new diagrams.
