# Refresh/publication integration and Build Refresh SDD

Date: October 4, 2026 (America/Merida).
Baseline: local `main`, `82a4af7`, clean working tree.
Branch: `feat/refresh-publication`. Renamed from `docs/refresh-publication-contract`
at alayala's request after the initial draft.
Initial status: documentation drafted; implementation was not yet authorized.
Continuation: alayala later authorized corrected implementation; see the
[Preview reconciliation and implementation record](2026-10-04-refresh-evidence-implementation.md).

## Objective and contributions

[ME] Alayala requested a branch and an integration contract covering existing outputs,
database mapping/migrations, candidate identity, lifecycle and acceptance review.
He then requested the Build Refresh SDD for Admin admission, single-slot reservation,
transactional outbox, preparation worker and retained candidate/evidence routing.

[YOU] AI inspected current repository guidance, canonical schema/API/security/backend
contracts, preparation/validation/storage code, local-auth reads and 0001/0002 DDL.
AI created the branch and drafted [integration contract](../../sdd/refresh-publication/integration-contract.md),
[proposal](../../sdd/refresh-publication/proposal.md), [specification](../../sdd/refresh-publication/spec.md),
[design](../../sdd/refresh-publication/design.md) and [tasks](../../sdd/refresh-publication/tasks.md).
README indexes the work; P1 in DECISIONS records pending proposals without changing
accepted A9/A16/A19/A20/A21. No approval or human code understanding is claimed.

## Evidence and corrections

Current source proves a stored unpublished candidate is not a publication. The
connector attempt UUID differs from the database step identity. The warning digest
includes the full diagnostic summary set, including informational summaries. The
manifest covers analytical identities; the separately hashed bundle binds stored
evidence. Registration needs both and a trusted retained receipt.

The existing migration creates read dependencies, not all writer tables. Inspection
found only `0001_local_auth.py` and `0002_app_entry.py` under migrations/versions;
no workers directory exists. Exact absence evidence and failure scenario are in
the contract. Current auth dependency is read-only, requiring a service-owned write
transaction for commands. Existing preparation is fresh-only and explicit-window;
discovery, attempt binding and durable worker ownership are planned work.

The draft explicitly distinguishes publication intent from activation. Setup writes,
review/recovery commands, scheduling and publisher execution remain later dependencies.
Proposed one-pipeline-per-run recovery avoids silently rebuilding a frozen candidate.
Review added measured discovery-date initialization for the existing non-null latest
observation field and linked worker deadline/ownership additions into migration scope.
An initial documentation patch failed its NOTES context check and applied no changes;
the corrected patch was applied after verifying the file state.

## Checks and limits

Static validation passed: 9 changed/new documents, 205 existing local Markdown link
targets, new-file whitespace, and unique ordered IC01–IC24 / S01–S20 case IDs.
`git diff --check` passed for tracked changes; the tracked diff was reviewed and the
new documents were inspected against current code and canonical contracts. Link
checks covered local file targets, not external URLs or fragment anchors. The first
check script incorrectly treated the normal `git diff --no-index` difference exit
code as failure; corrected exit handling passed without document changes.
Acceptance scenarios
IC01–IC24 and S01–S20 are planned cases, not executed tests. No backend tests, database
queries/migrations, builds, EIA/S3/Redis calls, cloud changes, commits or Git remote
operations ran. This task changes documentation only. Historical live evidence was
not rerun; current source was used to verify memory-derived implementation pointers.

## Review checkpoint

Done: branch, integration contract and complete four-document Build Refresh SDD.
Pending: alayala's design review and separate implementation authorization.
Blocker: proposed persistence/budgets/recovery remain unapproved; runtime behavior unverified.

Next: [ME] review the strict handoff and conservative worker recovery proposal.
