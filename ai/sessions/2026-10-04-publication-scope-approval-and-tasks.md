# Publication scope approval and implementation tasks

Date: October 4, 2026. Mode: decisions and documentation.
Inspected branch: `feat/refresh-publication`; HEAD `b018784`.

## Objective and contributions

[ME] Alayala approved the revised Publication scope, explicitly including manual
operator recovery, Admin same-candidate retry and one supported worker host. He
requested affected decisions/canonical documents and implementation tasks, while
forbidding code, commits, push and a PR.

[YOU] Inspected existing dirty documents, current specification/design, canonical
contracts, Refresh Task 5 history and worker entrypoints/recovery. Snapshotted all
tracked and nonignored untracked file hashes before editing. Recorded [A24](../../DECISIONS.md#a24--build-publication-first-delivery),
updated affected contracts, marked the SDD scope approved and drafted [six tasks](../../sdd/publication/tasks.md).
This records the actual approval, not user code understanding or implementation authority.

## Decisions and preserved history

D1 now narrows A9/A15 automatic publication crash/queue-loss recovery to executable
operator reconciliation. A23 Refresh recovery remains unchanged. D2's removal of
same-candidate retry is withdrawn; A16/A19 retry remains required. O1 selects one
host, one verifier invocation per generation and the 300-second cooperative attempt
deadline. The original proposal and P2 remain historical with explicit supersession.
P2's 600-second budget, repeated verifier starts, renewal heartbeat, additional
operation records and child supervision are not first-delivery requirements.

Operator recovery proves stop and reconciles the event; it cannot start new work.
The Admin separately authorizes another attempt for the same eligible candidate,
preserving evidence/approval and rechecking all bytes. Unknown causes and recorded
permanent integrity/coverage/contract violations do not grant retry eligibility.
Required CLI subprocess/database tests and integrated retry tests are assigned to
Tasks 5/6, not deferred as a runbook or future capability.

## Inspection facts and limits

`workers.__main__.serve` currently initializes the Refresh queue and its recovery
role loads S3 configuration. `workers.recovery.RecoveryService.once` handles expired
`running` work and checks the original host/inode plus an exclusive nonblocking
lifetime lock. A Publication CLI must branch before those dependencies and delegate
to publication-specific reconciliation. It cannot simply expose the existing loop.
Existing disposable runners select Refresh tests; task preparation requires extending
that selection during implementation, not claiming current Publication coverage.

The previous Task 5 runtime results were not rerun. These source observations guide
reuse; they do not prove the planned publisher, operator interface or schema mapping.
No data findings were added. Maintain data evidence — ongoing.

## Verification

Checks passed: 510 local Markdown links and heading anchors; newly added whitespace,
final newlines and code fences; unique decision IDs; six ordered tasks with complete
PUB-R01–R09 and PUB-E01–E10 coverage. OpenAPI parses and its only semantic changes
are the retry description and publication-policy metadata; request/response shapes
are unchanged. `git diff --check` passed and the documentation diff was reviewed.
The original proposal and P2 body remain verbatim below supersession notices; prior
NOTES content remains intact. Snapshot comparison confirms 16 affected documentation
files (including two new files), with the other 285 files unchanged. No backend
source, tests, migrations or dependency files changed.
No backend tests, build, migration, database/Redis service, EIA/S3 request or Git
mutation ran for this approval/task-writing work. Runtime and live storage/host
custody acceptance remain separate from document consistency.

## Checkpoint

Done: approved scope recorded, conflicting proposals superseded with history, tasks drafted.
Pending: review Task 1 and authorize a bounded implementation scope separately.
Blocker: implementation and deployment remain unauthorized.

Next: [ME] review Task 1's handoff and evidence boundaries.
