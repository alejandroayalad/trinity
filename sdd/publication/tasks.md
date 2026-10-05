# Tasks: Build Publication — first delivery

Date: October 4, 2026. Status: **Tasks 1–6 local delivery complete; all essential acceptance gates passed**.
Authority: [A24](../../DECISIONS.md#a24--build-publication-first-delivery).
Related: [specification](spec.md), [design](design.md), [historical proposal](proposal.md),
[Refresh handoff](../../ai/sessions/2026-10-04-refresh-task5-receipt-routing.md).

**Subsequent authorization:** alayala authorized complete implementation of Tasks 1–6
and disposable local checks without intermediate approval stops. Earlier statements
below about unstarted work or missing implementation authorization are historical
planning text. Current code, measured gates and remaining limits are in the
[implementation/acceptance record](../../ai/sessions/2026-10-04-publication-implementation-acceptance.md).
Subsequently, focused commits and push were authorized; live/retained changes and a PR remain excluded. See the acceptance record for the delivery authorization.

## Current delivery checkpoint

Done: Task 1 bounded foundation and Tasks 2–6; PUB-E01–E10 passed in disposable local
PostgreSQL/Redis, independent processes and actual query containers. The combined
suite passed 92 tests; the final Publication suite passed 30 tests with no skips.
Pending: separately authorized deployment and retained-account evidence.
Blocker: none for the approved local delivery. Maintain data evidence — ongoing.

The [acceptance record](../../ai/sessions/2026-10-04-publication-implementation-acceptance.md)
contains exact commands, measured results, corrections and remaining limitations.

## Human

**Input →** one registered candidate, frozen evidence, automatic intent or bound
Admin approval. **Flow →** claim one publication attempt, verify exact bytes and
atomically activate the version. **Output →** new requests use that publication;
existing requests keep their pinned version.

Storage timeout example: keep the previous publication and retain the failed
candidate/slot. An Admin retries the same eligible candidate with its original
approval and fresh verification. If the worker crashed, an operator first uses the
delivered recovery CLI to prove stop and reconcile the outcome. Recovery itself
starts no work. Changed/missing evidence cannot be approved or retried into eligibility.

**Historical planning boundary (superseded by the authorization above):**
These tasks described future work. All implementation items were unstarted. Approval
of the scope and preparation of these tasks does not authorize code, migration
execution, builds, live activation, commits, push or a PR. Each task must record
actual checks and limitations before it can be called complete.

## Bounded sequence

| Task | Depends on | Reviewable result |
|---|---|---|
| 1. Maintain data evidence — ongoing | Approved A24; recheck final Refresh handoff | Evidence/ownership mapping and reusable verification with safe failure classification. |
| 2. Implement atomic publication service | Task 1 | A real registered candidate can activate through one duplicate-safe transaction; failed work keeps the old publication. |
| 3. Route and execute one attempt | Tasks 1–2 | Existing outbox/queue infrastructure feeds one fenced publisher invocation per generation on one host. |
| 4. Deliver Admin approval, retry and discard | Tasks 1–3 | Canonical commands and truthful reads; retry preserves candidate/approval and re-verifies bytes. |
| 5. Deliver executable operator recovery | Tasks 1–4 | Guarded CLI proves stop and reconciles outcomes without starting a retry; real subprocess tests pass. |
| 6. Close integrated acceptance | Tasks 1–5 | PUB-E01–E10 pass with evidence separated by offline, disposable services, query container and later deployment. |

Task 1's data-evidence obligation continues throughout all tasks. No task enables
live publication independently. Tasks 4 and 5 are both required first-delivery
capabilities, not optional hardening after Task 6.

## Task 1 — Maintain data evidence — ongoing

**Bounded work:** recheck the actual branch/migration head and Task 5 handoff before
code. The inspected baseline is `b018784` with committed `0007_refresh_registration`;
this is an inspection fact, not permission to assume the implementation-time head.

- Trace real registration into `publish_version`: receipt hash/root, manifest/bundle,
  validation attempt/selected step, 16 required passes, 23 completed diagnostics,
  warning digest and both generations. Preserve Preview's evidence identities.
- Verify reuse of existing run owner/fence/lease, publish-step unique identity and
  immutable deadline, outbox, warning and command receipt fields. Exercise actual
  constraints in disposable PostgreSQL. If a correction requires DDL, explain it
  and append after the actual head; never rewrite old migrations, fabricate legacy
  evidence or create P2's superseded execution/operation tables.
- Extend the existing loader/verifier/S3 error boundary with safe typed causes.
  Preserve Refresh's outward safe errors and reuse its checks. Distinguish temporary
  exhaustion from denied access, missing/changed bytes, invalid validation/contract
  and unknown causes. A generic dependency wrapper must not enable retry.
- Establish one recorded-evidence/approval/failure-history eligibility rule for
  publication services and action reads. Retry checks recorded state synchronously;
  full remote verification belongs in each worker attempt, never HTTP.
- Extend existing disposable test discovery to include new publication modules;
  keep ordinary offline tests credential-free. Record ongoing data-evidence limits;
  synthetic fixtures are not EIA findings and do not alter FINDINGS without evidence.

**Review/exit evidence:** source mapping plus focused actual-wrapper/adapter tests;
missing/altered/mixed evidence and unknown causes fail closed. Demonstrate current
migration compatibility or the minimal justified correction on fresh/upgrade test
databases, preserving frozen historical fields. Task 1's bounded preparation can
finish; “Maintain data evidence — ongoing” cannot be marked permanently closed.
Covers PUB-R01/R08/R09 foundations; PUB-E02 and classification portions of E07/E10.

## Task 2 — Implement atomic publication service

**Bounded work:** place eligibility and transaction ownership in `publication/`;
reuse repository/diagnostic readers and registered evidence. Implement publication
success, safe failure and canonical supersession service paths before queue routing.

- Return an existing same-version event before stale ownership/file checks without
  changing the active pointer, even after a newer version becomes active.
- Verify exact local/remote bytes outside final SQL; retain the verified identities.
  Under control → run → candidate → active publication → publish step → related rows,
  recheck current fence/generation/lease, slot, active disposition, complete evidence,
  exact approval, run ordering and nonregressing coverage.
- Commit unique event, active pointer, successful step/run, revisions, lease clearing
  and owned-slot release together. Preserve automatic versus approval outcome and
  original approving actor; use the design's stable effect identity.
- Record stopped permanent/exhausted failure with a finished failed step, unresolved
  safe warning, `publication_failed` and null run `finished_at`; keep candidate/slot.
  Resolve uncertain commit by event lookup; unavailable/unknown state stays blocked.
  Do not retry final commit automatically or use Refresh's terminal failure helper.

**Review/exit evidence:** real registration feeds this service. Inject each final
write and commit failure in disposable PostgreSQL; prove event/pointer/run/step/slot
atomicity and no pointer regression on duplicate completion. Cover first-publication
failure, stale approval, older-run supersession, smaller coverage and original actor
attribution. Storage immutability/custody remains a separately measured deployment
gate; checksum verification alone is not that proof. Covers PUB-R01/R04/R05 and
PUB-E01–E03 foundations.

## Task 3 — Route and execute one attempt

**Bounded work:** specialize existing dispatch/queue/worker adapters for
`publish_version`. No parallel dispatch framework, new dependency, multi-host
failover, heartbeat loop or publication child supervisor.

- Validate schema-1 kind/IDs/generations against trusted PostgreSQL state; load no
  storage paths/policy/authority from queue input. Preserve existing colon-free
  stable job identity, enqueue lease/token acknowledgment and durable retry counts.
- Support one configured host/root and one publication consumer with concurrency one.
  Acquire the original retained lock inode exclusively after preparation releases
  it. Inside the lock, commit the unique publish step with attempt = generation + 1,
  next step sequence, new run owner/fence and fixed database-now + 300s deadline/lease.
- A present claim step consumes that generation: duplicates, restart or ambiguous
  claim completion cannot invoke verification again. Invoke the existing full
  verifier once with remaining time. Keep the lock in actual synchronous execution;
  cancelling its async wrapper does not release ownership while its thread runs.
- Retain three total enqueue attempts with 10s calls, 60s dispatch leases and 1s/3s
  waits, and the existing S3 per-read retry bound. Resume only bounded unacknowledged
  transport; never automatically repair delivered publication jobs or resume a
  crashed verifier. Exhaustion uses publication-specific safe failure semantics.
- Fence all late success/failure/release writes. Preserve preparation provenance,
  selected validation step and original preparation/registration budgets. Expired
  deadlines forbid publication; they do not prove stop or guarantee slot release.

**Review/exit evidence:** real Redis/PostgreSQL and worker lifecycle tests cover
before/after enqueue, duplicates, restart before/after claim/commit, lost delivered
work, stale payload/fence, temporary read/dispatch limits and a timed-out live thread.
No second invocation per generation; old publication stays usable. Tests that require
operator reconciliation are completed through the real CLI in Task 5, not direct SQL.
Covers PUB-R03/R04/R05 and PUB-E03/E05/E06.

## Task 4 — Deliver Admin approval, retry and discard

**Bounded work:** implement the three canonical candidate command paths, permissions,
empty bodies, UUID keys, exact ETags and receipts from [API commands](../../docs/api-contract.md#commands-and-concurrency).
Reuse existing Task 5 candidate/run reads; do not add frontend or alternate endpoints.

- Resolve current Admin/session before protected state/receipt access. Matching
  actor/action/target/body replay returns the original receipt before stale-ETag
  checks. Keep errors and race behavior canonical; HTTP performs no remote I/O.
- Approval atomically records the exact version/manifest/validation-step/warning
  binding, publishing transition, outbox, revisions and receipt. Zero warnings use
  registration's automatic intent without creating an approval.
- Retry only a safely failed recoverable candidate: resolve old warning, transition
  to publishing, increment publication generation/fence/revisions and rearm the same
  outbox with current payload/new dispatch generation and reset enqueue count, all
  with its receipt. Keep slot, evidence and original approval. A new worker attempt
  must reverify all bytes; another failure records new warning history. The retry
  actor does not replace the approving actor. Recorded permanent violations remain
  ineligible even after bytes are restored.
- Discard only an unpublished review/safely failed candidate with no active publisher.
  Atomically invalidate old work, record permanent abandonment, finish run, resolve
  warning, release slot and store receipt. Delete no evidence/history. Reuse existing
  start-refresh afterward; do not implement Run again or warning deletion here.
- Align `/me` and candidate/run status, action eligibility, revisions and ETags with
  service rules. Deferred/unimplemented actions stay disabled; no direct-command
  bypass exists when a prior read showed an action enabled.

**Review/exit evidence:** real HTTP/PostgreSQL tests for all three personas, expired/
revoked authority, replay/conflicting keys, ETags and rollback. Separate-process
approval/approval, approval/discard, retry/retry and retry/discard races have one
effect. Automatic and approved candidates both survive temporary failure → explicit
retry → real worker fresh verification → success without EIA calls. Changed bytes
before execution fail permanently and disable further retry. Covers PUB-R02/R07–R09
and PUB-E01/E04/E07/E10.

## Task 5 — Deliver executable operator recovery

**Bounded work:** implement `publication-recover` in the existing worker entrypoint
and a publication-owned reconciliation service. Follow the [approved CLI contract](design.md#operator-interface--required-executable-delivery)
exactly; a runbook without the tested executable cannot complete this task.

- Deliver `--run-id <UUID> --inspect` and the guarded mutation form with mandatory
  `--expected-generation <N> --expected-fence <F>`. Inspection is read-only. Route
  before Redis/S3 initialization; require trusted worker OS account, recorded host,
  private retained root and worker database privileges, without EIA/S3/Redis access.
- Prove stop by no-follow/no-create opening of the original host/inode and exclusive
  nonblocking lifetime lock held through the SQL transaction. Deny missing, replaced,
  wrong-host or held locks. Require locked generation/fence/state/lease rechecks;
  lease expiration, PID inspection and manual SQL do not authorize recovery.
- Reconcile an existing event as already published with no pointer movement. Otherwise
  atomically record safely stopped publication failure, invalidate old execution and
  dispatch authority and retain history, approval and slot. Never increment publication
  generation, reverify bytes, enqueue, approve or discard. A delayed operator call
  cannot fail an Admin's newer retry generation.
- Deliver sanitized JSON fields and exact exit codes 0/2/3/4, including already-failed,
  already-published, blocked/stale-target and uncertain-outcome results. Repeated or
  concurrent recovery has no extra warning/revision/effect; unknown state stays blocked.
- Provide tested `--help` and backend usage examples explaining the operator → Admin
  handoff. The CLI does not kill processes. A hung worker must end under host service
  controls; only actual lock proof allows mutation. No manual database fallback.

**Review/exit evidence:** invoke the actual CLI in subprocesses against disposable
PostgreSQL with real held/released locks. Test access denial, malformed input and all
outcomes/exit codes, missing/replaced/wrong-host lock, unexpired leases, dead process,
live timed-out thread, commit uncertainty, concurrent operators, stale target after
Admin retry and repeated/lost-response recovery. Kill real workers around claim,
verification and commit; committed publication survives. Require no EIA/S3/Redis
configuration or calls for CLI execution. Recover → Admin retry → publish succeeds
through production paths. Covers PUB-R06 and PUB-E06/E09/E10.

## Task 6 — Close integrated acceptance

**Bounded work:** execute the complete [PUB-E01–E10 gate](spec.md#essential-acceptance--must-pass-before-delivery)
and report each result with its actual environment. Fix only defects needed to meet
the approved scope; new operational capabilities require a new decision.

- Real registration → actual dispatch/worker/publication transaction → Catalog,
  Preview and SQL readers. Tests may create synthetic source fixtures but must not
  insert publication events/pointers to simulate this slice's success.
- Verify initial readiness, role restrictions, real in-flight request pinning and
  Preview cursor restart across a switch. Run actual query-container acceptance
  separately from mocked/injected executors; skipped container tests do not pass it.
- Close crash, transaction, command and recovery races in separate processes with
  disposable PostgreSQL/Redis. Confirm the operator executable and same-candidate
  retry work as a usable sequence, not just isolated helpers.
- Run relevant Refresh, evidence, S3, auth, Catalog, Preview and SQL regressions using
  repository commands. Report counts, skips, exact commands and unresolved limits.
  No new live EIA finding follows from synthetic source/storage tests.
- Update implementation status/usage only to the verified boundary. Keep live storage
  protection, host/root custody, retained migrations, live activation and retained-
  account acceptance behind a separate deployment authorization. Do not claim full
  A16 recovery: setup/schedule writes, Run again and warning deletion remain separate.

**Review/exit evidence:** an acceptance matrix for every E01–E10 result, actual
commands and preserved prior behavior. Automatic publication crash recovery,
multi-host failover and hard process deadlines stay deferred with their tests.
No runtime delivery claim until every essential gate has passed.

## Requirement and acceptance coverage

| Approved contract | Owning task(s) |
|---|---|
| PUB-R01 exact verified evidence | 1, 2, 3, 6 |
| PUB-R02 automatic intent and bound approval | 2, 4, 6 |
| PUB-R03 per-generation invocation and durable dispatch | 3, 4, 6 |
| PUB-R04 atomic, ordered, duplicate-safe activation | 2, 3, 6 |
| PUB-R05 safe failure and retained publication/slot | 2, 3, 5, 6 |
| PUB-R06 executable stop-proof recovery | 5, 6 |
| PUB-R07 safe permanent discard | 4, 6 |
| PUB-R08 pinned readers and truthful protected reads | 1, 4, 6 |
| PUB-R09 explicit same-candidate retry | 1, 3, 4, 5, 6 |
| PUB-E01 automatic/approved registration-to-reader paths | 2, 3, 4, 6 |
| PUB-E02 integrity, evidence and ordering | 1, 2, 6 |
| PUB-E03 atomicity, duplicate effects and uncertain commits | 2, 3, 5, 6 |
| PUB-E04 command authority/replay/concurrency | 4, 6 |
| PUB-E05 retry ceilings and per-generation invocation | 3, 4, 6 |
| PUB-E06 process crashes, lock proof and stale writes | 3, 5, 6 |
| PUB-E07 discard, status and refresh readmission | 4, 6 |
| PUB-E08 actual reader/container compatibility | 6 |
| PUB-E09 executable operator contract | 5, 6 |
| PUB-E10 same-candidate retry and permanent integrity failure | 1, 4, 5, 6 |

## Verification commands and evidence boundaries

Use the existing [backend commands](../../backend/README.md#refresh-dispatch-and-preparation--tasks-24)
and locked environment. From `backend/`, after authorized implementation:

```sh
uv run --locked python -m unittest discover -s tests -p 'test_publication*.py' -v
uv run --locked python tests/run_local_refresh_checks.py --failfast
uv run --locked python -m unittest discover -s tests -v
```

**Historical command-planning note:**
The first test-file prefix was the proposed convention, not then-existing runnable tests.
The disposable runner exists but currently selects Refresh tests; extend its shared
selection in Task 1/6 to include Publication before claiming coverage. Reuse its private
PostgreSQL cluster and disposable Redis container. Do not point reset-capable test
variables at retained data. Enable actual query-container tests through the existing
[Preview/runtime instructions](../../backend/README.md#preview-acceptance--step-4)
and record prerequisites/skips rather than inventing a passing result.

No command above was run for these planning documents. Documentation consistency,
local links, OpenAPI validity and the diff are the checks appropriate to this change.

## Historical planning checkpoint

Done: approved scope mapped to six bounded tasks and all PUB-R/PUB-E requirements.
Pending: review Task 1, then separately authorize a bounded implementation scope.
Blocker: code/runtime work is not authorized by this task-writing request.

Next: [ME] review Task 1's handoff and evidence boundaries.
