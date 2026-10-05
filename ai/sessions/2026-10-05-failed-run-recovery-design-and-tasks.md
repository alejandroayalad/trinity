# Failed-run recovery design and tasks

Date: 2026-10-05

## Objective and authority

[ME] Accepted P01, requested committing/pushing the acceptance, then design/tasks. [YOU] recorded the accepted choice under A16, committed `7d6199b` and pushed it to `pending-endpoints-frontend` before drafting these artifacts. Design/tasks are local drafts; implementation and runtime recovery remain unauthorized.

## Source tracing and contributions

[YOU] inspected `RefreshService.start`, `refresh.service._authorize`, `refresh.repository.accept_run`, `PublicationCommands.command`, `publication.service.locked`, `publication.checks.stopped_failure`, `RefreshExecution.fail/owned/reclaim_stopped`, `DispatchService` and `fail_run`, the settings reader, transport guard, PostgreSQL transaction adapter and migration constraints. See [design](../../sdd/failed-run-recovery/design.md) and [tasks](../../sdd/failed-run-recovery/tasks.md).

Current code acquires authority/control locks in different orders across manual start and candidate commands. The design proposes control-first consistency and requires a complete lock graph check; this observation alone does not establish a runtime deadlock. Refresh failure retains owner metadata and uses `child_stopped` evidence, unlike publication stopped-failure. The design therefore distinguishes proof by producer and leaves ambiguous paths disabled. Exact owner/fence evidence binding must be verified during implementation.

Schema section Failure resolution and abandonment already selects `disposition=discarded`; this corrects the earlier specification's open disposition-mapping design note without changing the product rule. Existing outbox statuses do not include cancellation; generation fencing and terminal-state claim rejection preserve history. No new table or dependency is proposed; migration need remains conditional on evidence discovered during implementation.

[ME] supplied policy acceptance and delivery order. [YOU] authored D01–D07 and five bounded task steps mapped to R01–R12/S01–S12. No understanding is attributed to the user without a later observed explanation. Maintain data evidence — ongoing; no source observations were fetched.

## Verification and boundary

Document checks passed: 32 local links/anchors, fences/whitespace in five files, unique D01–D07 and five ordered task steps. The six-file documentation scope was reviewed and `git diff --check` passed. No backend test, build, migration, EIA/S3 call, retained recovery or implementation ran. Acceptance commit/push is complete; the subsequent design/tasks remain drafts for review.

Done: accepted policy delivered and design/tasks drafted. Pending: design review and Step 2 authorization. Blocker: none for planning.

Next: [ME] review the design's transaction and stopped-execution rules.
