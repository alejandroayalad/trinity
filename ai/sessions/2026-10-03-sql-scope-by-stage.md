# Session SQL scope by stage

Date: October 3, 2026. Branch: `docs/backend-decisions-architecture`.

## Objective and contributions

[ME] Alayala requested recording his required-v1 and optional-extension table as a decision. [YOU] AI inspected current decisions, product scope, SQL proposal, repository status, and the dependency acceptance handoff; recorded A18; and aligned current references. Existing local proposal edits were preserved.

## Decision and boundaries

[A18](../../DECISIONS.md#a18--sql-scope-by-stage-closed) is the authoritative staged SQL scope. A16 remains proposed except for this accepted scope; A17 and A9 are unchanged. The exact aggregate-function allowlist and remaining detailed policy still need review. The optional extension is not a required v1 deliverable or authorization to implement it.

Correction: current references now distinguish accepted SQL scope from the still-proposed grammar and API/security details. Earlier session statements remain historical.

## Checks and results

Passed: reviewed the task diff against a pre-edit snapshot, checked 96 local links and 27 anchors across six documents, balanced Markdown fences, 18 unique decision IDs, and exact preservation of the requested table. `git diff --check` passed. Existing local proposal work remains in place. No implementation, runtime test, dependency installation, commit, push, or remote change is part of this task.

## Next action

[ME] Review the proposed aggregate-function allowlist under A16.
