# Next slice: Step 5 — Refresh and publication

Date: 2026-10-04. Mode: decision recording. Authority: A16 and A9.

[ME] Alayala selected the publication lifecycle as the next slice and confirmed its four behaviors: record candidate/validation results; automatically publish a passing candidate without review warnings; require Admin approval when review warnings exist; switch the active version in one database transaction so readers never observe partial publication.

[YOU] Recorded this sequencing choice in DECISIONS.md under A16. The behavior already follows A16/A9; no new publication mode or permission is introduced. Required failures or incomplete validation still prevent publication. Candidate artifacts and diagnostics must be complete and frozen before eligibility is accepted. The final publication transaction records the event, changes the pointer and commits consistent lifecycle state; readers see one complete old or new version. This does not put remote file transfers inside the database transaction.

The production source inspection in the preceding review found only publication readers and candidate preparation ending in stored_unpublished. Synthetic tests create publication state directly through their fixture. Therefore a production publication lifecycle is separate implementation work, not a remaining SQL compatibility/isolation test. Catalog remains complete; SQL is implemented with recorded verification gaps; preview remains plan-only.

Updated current README/task handoffs without changing historical session claims. Checked local documentation targets and whitespace. No application test rerun was needed for this documentation-only change. No new code, dependency, migration, publication, retained-account action or cloud operation ran.

Done: Step 5 and its publication behavior are recorded as the next implementation slice.
Pending: bounded proposal/specification/design/tasks for that slice under the repository's SDD gates.
Blocker: production publication activation is still absent until that work is implemented and verified.
Next: [ME] begin the Refresh and publication SDD gate.
