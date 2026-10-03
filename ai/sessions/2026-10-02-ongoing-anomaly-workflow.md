# Session log — Ongoing anomaly workflow

Date: October 2, 2026. Scope: agent working instructions and evidence documentation.

## Objective and contributions

[ME] Alayala replaced the idea of closing the data-evidence step with an ongoing process for recording and investigating potential anomalies. [YOU] AI added the process to [AGENTS.md](../../AGENTS.md#ongoing-anomaly-workflow), updated the status and pointer in [FINDINGS.md](../../FINDINGS.md), and recorded authorship in NOTES.md.

## Selected workflow

Notice a potential issue, check for an existing entry, record an unverified candidate, reproduce it, review the result with alayala, then promote a selected anomaly with evidence and product implications. Recording candidates requires no separate approval. Previously selected anomalies need no repeat approval. Rejected candidates are not reopened without new evidence.

The planning label is now “Maintain data evidence — ongoing.” Three documented anomalies meet the numerical minimum but do not end discovery or remove the remaining submission requirements. Completed checks can be reported as completed. An unverified candidate is not automatically a reason to stop other work; identify its actual effect on a decision or required validation.

## Decision references and corrections

A1–A5 remain unchanged. The workflow links behavior changes to the single DECISIONS.md record instead of silently changing policies. A5 still governs validation and publication for the known facility count issue. No new application architecture or permission was selected. The earlier wording that treated data evidence as a phase to close was corrected.

## Verification and limits

Checked the document diff, relative links, code fences, and preservation of the three existing anomaly entries and all prior AGENTS.md rules. Saved files are verified against staged drafts. No new candidate was invented, no existing anomaly was removed, and no API request or application code change occurred. Runtime tests are not applicable. Git status reports that the data workspace is not a Git repository; no commit, push, or remote change was made.

## Handoff

Use the workflow when new evidence appears. No empty candidate section or extra candidate registry was created. Exact required validation checks and other planning decisions remain open.

Next: define the required validation checks while keeping data evidence ongoing.
