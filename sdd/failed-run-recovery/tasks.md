# Tasks: Failed-run recovery commands

Date: 2026-10-05
Status: Steps 2–3 authorized and implemented locally October 5, 2026. Step 2 understanding check passed; Step 3 offline results and runtime boundaries are in the [implementation record](../../ai/sessions/2026-10-05-failed-run-recovery-step-3.md). Step 3 is pushed as `bff8446` and `da8be15`. Step 4 disposable acceptance is authorized; current evidence and remaining integration are in the [Step 4 record](../../ai/sessions/2026-10-05-failed-run-recovery-step-4.md).
Basis: [specification](spec.md), [design](design.md), [proposal](proposal.md), A16/P01 and A15/A19/A20/A23/A24 in [DECISIONS](../../DECISIONS.md).

## Human

Work in five bounded steps. The first remains ongoing. Each implementation step needs authorization and its stated check; passing a document check does not satisfy a runtime gate. Current design uses current settings for a new run and preserves the failed run's snapshot.

## LLM

### Step 1 — Maintain data evidence — ongoing

- [ ] [YOU] Preserve selected anomalies, original observations and existing publication. Keep synthetic operational failures separate from EIA findings. Update FINDINGS only if new source evidence actually appears.
- [x] [ME] Accepted the specification/P01 and authorized design/tasks after acceptance commit/push.
- [x] [YOU] Recorded P01 under A16 and pushed acceptance commit `7d6199b`; drafted design/tasks from current source.
- [x] [ME] Accepted the design and requested starting tasks; Step 2 is the bounded first implementation step.

Gate: agreed scope and worktree, current schedule-settings integration baseline, and preserved user changes. Do not mark ongoing data evidence closed.

### Step 2 — Parsing, eligibility and shared contracts

Coverage: R01–R04, R08, R10, R12; S01–S02, S05–S06, S10.

- [x] [YOU] Explain input → flow → output and one failure case before code. Inspect latest CONTRIBUTING, migration head, schedule-settings helpers and repository status.
- [x] [YOU] Implement strict command parsing, run ETag/key/body validation and canonical receipt literals. Add pure tests for DELETE body rejection, repeated headers, wrong-resource tags, unknown query/fields and malformed IDs.
- [x] [YOU] Trace every failure producer and define shared stopped-state eligibility for dispatch, preparation/validation and publication. Test contradictory/missing evidence, retained Refresh owner, active work and discarded/published candidates. Keep unknown states disabled.
- [x] [YOU] Reconcile the mutation lock graph in D03 with auth/logout, settings/scheduler, dispatch and publication. Confirm durable evidence binds the failed execution; document any narrow migration need before adding it.
- [x] [YOU] Run focused tests and record exact results.
- [x] [ME] Explained that lease expiry does not prove termination and `execution_fence` rejects writes from an obsolete generation. [YOU] clarified that separate stop proof is still required for file/S3 writers.

Gate evidence: 29 new tests included in 175 discovered affected-suite tests: 61 passed, 114 opt-in runtime skips, zero failures/errors. No new mutation route exposed. Lock-order reconciliation is documented; candidate commands must change order in Step 3 before mutations are enabled. Ambiguous stop evidence remains disabled. Human explanation passed; the subsequent explicit “proceed” authorized Step 3.

### Step 3 — Atomic recovery and API integration

Coverage: R01–R12; S03–S07, S10, S12.

- [x] [ME] Authorized Step 3 with “proceed” after explaining leases/fences. [YOU] Implement one service-owned transaction, common lock order and existing receipt replay; align candidate-command order without changing its outcomes.
- [x] [YOU] Add repository abandonment and explicit rerun admission inputs. Freeze current settings/policy, preserve A, create B/outbox/receipt atomically, and fence stale old work. Delete creates no new work. Preserve manual/scheduled admission identities.
- [x] [YOU] Add the two exact HTTP routes and required transport/injection hooks. Update common Admin projections and models. Assert canonical OpenAPI method/path/schema/headers and route inventory.
- [x] [YOU] Add rollback-at-each-write tests and service/HTTP tests for acceptance, replay, safe errors and authority changes. Test old-run target versus new-run receipt linkage.
- [x] [YOU] Run focused and affected auth/Refresh/Publication offline regressions; review the diff and report skipped checks separately.
- [ ] [ME] Explain what remains unchanged when the outbox insert fails.

Gate: local service/HTTP/projection tests and affected offline checks pass. The six PostgreSQL cases subsequently passed in Step 4, including rollback after every write and deferred commit failure. See the Step 4 record for measured writer boundaries. No live recovery or retained database edits.

### Step 4 — Real transaction, race and delivery acceptance

Coverage: all S01–S12, especially S07–S09 and S11–S12.

- [x] [ME] Authorized Step 3 commit/push and continuation with disposable Step 4 checks. No retained build or deployment is included. [YOU] Reuse existing PostgreSQL/Refresh fixtures and runners; isolate resources and cleanup only test-owned state.
- [x] [YOU] Prove full rollback with real PostgreSQL and race rerun/delete against each other, candidate retry/discard/commit, manual start, logout and role change. Verify one owner and no stale slot release. Scheduled admission primitive and settings-row writer races also passed.
- [ ] [YOU] After the separate settings/scheduler slice is integrated, repeat races through its actual mutation endpoint and scheduler admission path. Those implementations are absent here; primitive-level results do not close this integration check.
- [x] [YOU] Exercise confirmed-stop preparation/publication paths and pre-claim failures. Send stale dispatcher acknowledgements, queue deliveries and worker commits after abandonment; assert no revival or file publication.
- [x] [YOU] Use real HTTP to lose/replay a success response, recheck current authority, and verify changed revisions/actions. Use real outbox/Redis to test accepted rerun during queue failure and subsequent single-run dispatch; deletion emits none.
- [x] [YOU] Run relevant broader regressions, report pass/fail/skip counts per boundary and retain sanitized reproducible evidence. Do not sum overlapping suites as unique tests.

Gate: all essential cases pass with measured database/HTTP/queue evidence. Fixture success does not prove retained deployment or full-history extraction.

### Step 5 — Review and retained operator handoff

- [x] [YOU] Review final diff, comments/docstrings, contract consistency and links; reconcile proposal/spec/design status with measured results. Record limitations in NOTES and a unique session record.
- [ ] [ME] In separately authorized retained setup, inspect a genuine safe failed run as Admin; use one recovery action and verify the old publication/history remain. Live EIA calls and builds stay with [ME].
- [ ] [YOU] Record observed operator result without credentials. Do not fabricate a failure or change retained state merely to complete the checklist. If prerequisites are missing, record the exact boundary and leave this check open.
- [x] [ME] Authorized slice delivery with “wrap it up and deliver this slice.” [YOU] Committed and pushed runtime tests as `2812ab9`; verified the remote head. Delivery preserves incremental history. Merge and retained deployment remain separate.

Gate: distinguish automated acceptance, retained operator acceptance and Git delivery. None implies deployment of the others.

## Planned commands and evidence

From `backend/`, use the existing `.venv/bin/python -m unittest discover -s tests -p 'test_refresh_recovery*.py' -v` for the planned recovery tests, then the affected Refresh/Publication/auth modules. The new test file now exists. This worktree has no local virtual environment; Step 2 reused the existing sibling interpreter with this worktree explicitly selected through PYTHONPATH. Exact invocation and results are in the evidence record. Reuse `tests/run_local_refresh_checks.py` for disposable PostgreSQL/Redis acceptance after adding the new cases to its delegated runner. Review runner prerequisites before executing; builds and retained actions require the operator boundary above.

At every gate record command, environment, result count, failures/skips, cleanup and remaining boundary. Document-only checks do not run backend suites.

Done: implementation and runtime tests committed/pushed; 75 focused recovery checks and 25 PostgreSQL auth checks pass. Combined Refresh/Publication: 120 passed, 1 query-image-dependent skip, zero failures. Pending: actual settings/scheduler integration, and Step 5 retained operator acceptance. Blocker: this checkout has no settings mutation endpoint or scheduler loop; shared database primitives are tested. The human failure-case explanation remains unobserved; explicit continuation was authorized.
