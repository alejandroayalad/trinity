# Design: Build Publication — first delivery

Date: October 4, 2026. Status: **approved scope; Tasks 1–6 implementation authorized**.
Approval: October 4, 2026, under [A24](../../DECISIONS.md#a24--build-publication-first-delivery).
Implementation: [Tasks 1–6](tasks.md); current results are in the linked acceptance record.
Related: [reduced specification](spec.md), [original proposal](proposal.md).

**Subsequent authorization:** alayala authorized complete implementation of Tasks 1–6
and disposable local checks without intermediate approval stops. Earlier statements
below about unstarted work or missing implementation authorization are historical
planning text. Current code, measured gates and remaining limits are in the
[implementation/acceptance record](../../ai/sessions/2026-10-04-publication-implementation-acceptance.md).
No live/retained change, commit, push or PR is authorized.

## Human

**Input →** one registered candidate and automatic intent or exact Admin approval.
**Flow →** one worker verifies the saved proof and files, then commits the visible
version change in one transaction. Warnings wait for approval before this work.
**Output →** one publication; new requests use it, existing requests keep theirs.
**Failure →** the previous publication stays available and the candidate blocks
refresh. An Admin can retry the same eligible candidate after a recoverable failure.
After a crash, an operator first proves stop and reconciles the outcome; this action
does not start a retry. Each Admin retry verifies all evidence and files again.

Example: storage remains unavailable after its bounded read retries. Keep the old
publication and record failure. An Admin retries the same candidate after storage
recovers, preserving its evidence and original approval without fetching EIA again.
Changed bytes instead produce a nonretryable integrity failure.

## Basis and decision status

Inspected source is `b018784` on `feat/refresh-publication`, including committed
Refresh Task 5 and `0007_refresh_registration`. The original proposal, P2 and
other uncommitted documentation were preserved. No runtime tests were rerun.

The [approved scope and D1/O1](spec.md#approved-scope-and-decision-history) and
[A24](../../DECISIONS.md#a24--build-publication-first-delivery) govern this design. D1 accepts manual
publication recovery in place of the broader A9/A15 automatic recovery requirement.
**D2 is withdrawn:** deliver same-candidate retry as A16/A19 require. O1 selects
one host and a cooperative 300s work deadline per authorized attempt. The concrete
CLI/access design and its tests are required to complete this slice. P2 remains
superseded history. Approval authorizes task preparation, not implementation.

## Inspected implementation facts and reuse

Paths below are relative to `backend/src/trinity/` unless a migration is named.

| Inspected fact | Reuse or necessary extension |
|---|---|
| `refresh.registration.persist_candidate` registers exact evidence, queues schema-1 `publish_version` for zero warnings, otherwise waits for approval, and clears the preparation lease. | Consume its existing obligation and retained receipt custody; do not register or prepare again. |
| `refresh.evidence.load_candidate` calls existing local/remote verifiers; `connector.pipeline.verify_stored_candidate` reads each bundle member and the bundle. `adapters.s3.StorageOperation.verify` caps temporary read attempts at three; SDK retries are disabled. | One invocation uses those existing checks/retries. No second verifier, per-GET permit table or automatic whole-verifier retry loop. A new explicit attempt invokes the verifier anew. |
| `refresh.dispatch.DispatchService` persists enqueue attempts/leases; `adapters.queue.RefreshQueue` uses BullMQ, one consumer slot and `attempts=1`. Both are explicitly refresh-only. | Add a small publication job-kind adapter and state-specific dispatch handler using that pattern. Do not feed publication payloads to the current refresh parser or use `fail_run`, which sets terminal `failed`. |
| `workers.refresh.RefreshWorker.execute` holds a recorded local run-lock inode; `workers.recovery.RecoveryService.once` checks host/inode and exclusive acquisition before SQL recovery. | Reuse this lock protocol and trusted root. Publication holds the same inode exclusively after preparation ends. Existing recovery handles `running`, not `publishing`; the executable publication-recover mode specified below is required new work. |
| `refresh_runs` already has owner, lease, fence and publication generation; `refresh_steps` has stage, work key, attempt, deadline and unique attempt identity. Migration 0005 freezes selected validation steps; 0006/0007 freeze preparation/registration budgets. | Reuse run ownership and a new publish step, leaving preparation custody/deadlines and the selected validation step untouched. No new execution/operation tables or columns are proposed. |
| `publication.repository` and `publication.diagnostics` read publication/evidence; `refresh.candidates.read_candidate` and `refresh.service.admin_context` derive status/actions. | Preserve reader pinning; add publication service writes and align approval/retry/discard eligibility across all projections. Current action eligibility alone does not implement those commands. |

`rg --files backend/src/trinity/publication` returned only `__init__.py`,
`repository.py`, `diagnostics.py`: no publication command service or worker there.
These are source observations, not evidence that the proposed reuse works at runtime.

## Challenge each mechanism

| Mechanism | First-delivery choice | Reason and limit |
|---|---|---|
| Generations | Retain/check the existing publication and dispatch fields; add no generation model. | Only an accepted Admin retry increments publication generation. Queue transport, recovery and discard cannot authorize a new attempt; they can invalidate dispatch authority. |
| Fence | Reuse `refresh_runs.execution_fence` for claim and invalidation. | Local serialization does not replace database authority; stale success/failure writes must fail. |
| Lease | Reuse `refresh_runs.lease_until`, fixed to the publish step's accepted 300s deadline; no heartbeat renewal. | Reject late publication. Expiry never authorizes another verifier or slot release. Preparation's 30s/5s lease/heartbeat remains unchanged. |
| Supervision | One synchronous verifier in the worker process, using the existing thread adapter where needed; no new child supervisor. | Keep the lock inside that actual execution until it ends. Cancellation of an async wrapper does not prove its thread stopped. No hard wall-clock exit guarantee. |
| Retries | Existing S3 per-read retries and durable enqueue retries only. | One committed claim permits one verifier invocation per generation. Crashes consume that attempt; only explicit Admin retry grants a new budget. No automatic final-commit retry loop. |
| Recovery | Executable operator stop-proof reconciliation; separate Admin retry or discard. | Crash/queue-loss safety remains required; unattended recovery, resume and failover are deferred under D1. |

## Operating model and persistence

Support one configured worker host identity with the same persistent local root as
Refresh, and one publication consumer with concurrency one. No NFS lock semantics,
second worker host, host migration or replacement of lock files is supported.
The host/root topology must be verified in the eventual deployment; separate
container hostnames must not be assumed equivalent to the recorded host identity.

Keep BullMQ/Redis and `job_outbox` under A6/A7. Add publication-specific payload
validation and queue routing within the existing adapter/worker arrangement, not
a second dispatch framework. A separate queue name can isolate the publication
consumer while using the same Redis service and pinned dependency.

Preserve producer fields: schema version, `publish_version`, run/version UUIDs and
both generations. Load paths, policy and authority from trusted state, never jobs.
Use a stable colon-free version/generation queue ID. Retain enqueue's existing
three-attempt count, 10s call bound, 60s dispatch lease and 1s/3s waits; acknowledgments
remain token/generation-conditional. Pending/unacknowledged enqueue may exhaust that
same budget after restart; do not repair delivered jobs automatically in this slice.
An explicit Admin retry resets enqueue attempts only for its new publication generation.

Before dispatch, check preparation released its recorded run lock; defer dispatch
without consuming an attempt while it is held. The publisher then acquires that
same inode exclusively before claim, outside SQL. Lock contention before claim
starts no verification; a lost notification requires explicit reconciliation.

The claim transaction creates one `refresh_steps` row: `stage=publish`,
`work_key=publication`, `attempt=publication_generation+1`, next per-run `step_seq`,
and immutable `deadline_at=database_now+300s`. Its existing unique key prevents a
second invocation for that generation. Set a new owner, increment the run fence
and set the run lease to that step deadline. A present step, even interrupted,
forbids another verification in that generation. A new Admin retry uses the next
generation/attempt and a fresh deadline; old steps remain immutable history.
A rolled-back claim leaves no marker. An ambiguous
claim outcome starts no I/O; a committed marker then requires reconciliation.

Preserve `worker_execution_ref` as preparation provenance, including receipt hash,
version and original host/lock inode. Change only current owner/fence/lease fields
on the run; do not call preparation's claim/reclaim methods, reset its deadlines
or update its frozen validation step. Publication uses the new step's deadline.
No new schema is expected from this design; verify existing constraints during
implementation rather than promising migration-free compatibility without tests.

## Approval, verification and atomic activation

Feature services own transactions; worker/queue adapters delegate. Add the small
publication service/checks/command boundary under the existing publication feature.
Reuse the existing candidate detail endpoint. Approval/retry/discard inherit current
Admin authorization, request parsing, exact ETags, receipt replay and errors from
[API commands](../../docs/api-contract.md#commands-and-concurrency) and
[OpenAPI](../../docs/openapi.json). No inline remote work. Retry is exposed only
when the same service eligibility checks permit it; all three commands recheck
current authority and state under locks, regardless of previously enabled actions.

1. **Accept approval where required.** In one transaction store the exact approval,
   transition to publishing, insert the unique obligation/receipt and increment
   public revisions. Keep admission. Zero-warning registration already supplies intent.
2. **Claim once and verify.** Parse identities; an existing version event is an
   idempotent result before obsolete ownership/file checks. Otherwise claim under
   locks as above, then call `load_candidate` once with original receipt hash/root
   and remaining deadline. Compare returned evidence to all frozen database bindings.
3. **Commit once.** Lock `refresh_control` → run → candidate → active publication,
   followed by the publish step and warning/command/outbox rows as applicable.
   Recheck owner/fence/lease, state, slot, verified identities, exact approval and
   ordering/coverage. Commit event, pointer, successful step/run, public revisions,
   lease clearing and owned-slot release together. Bound SQL by remaining time.
4. **Handle a failed or unknown outcome.** Do not automatically repeat verification or final commit.
   Look up the unique event after an ambiguous commit. If state cannot be resolved,
   leave the blocker for operator reconciliation; do not write a contradictory failure.

Use the existing unique version event and stable `publish:<version_id>` effect
identity. The UUID event column can use the prior deterministic UUIDv5 mapping
(`NAMESPACE_URL`, `urn:trinity:publish:<canonical version UUID>`); no new ID layer.
Automatic events have no approval/actor; approval events reference the bound approval
and approving Admin. Later logout does not rewrite historical authorization.

Require a greater run sequence, candidate start no later and end no earlier than
active coverage. Supersede older unpublished work safely; reject coverage regression.
Never move the pointer on duplicate completion or change old published dispositions.
Keep all frozen proof/old data. S3 readback does not prove immutability: trusted local
custody and actual remote overwrite/delete protection remain activation prerequisites.

## Failure and explicit recovery

When synchronous verification has returned unsuccessfully, the owner still holding
the lock records a finished failed publish step, `publication_failed` with null run
finish time, safe warning and revised public state. Clear execution lease and
invalidate the fence, but retain admission/evidence. A failure may be recorded
after the work deadline only with the same owner/fence and stop proof; publication
may not. Dispatch exhaustion records an equivalent failed step only if no publisher
claimed it, after the same stop/state checks. Never call Refresh's terminal fail helper.

### Admin retry is a new attempt, not crash recovery

`POST /api/v1/candidates/{version_id}/publication-retry` accepts `{}`, the canonical
UUID idempotency key and exact candidate ETag. Reuse current `refresh:recover`
Admin authorization and command receipt handling. Matching authorized replay
returns the original receipt before stale-ETag comparison; a new retry requires a
new key. Keep authentication/transport behavior in the API contract.

Under common transaction locks, require `publication_failed`, no live writer,
owned slot, active validated unpublished candidate, current revision, intact
recorded evidence, unresolved recoverable warning and the original exact approval
when needed. Inspect prior publish steps/warnings as well as current state: a known
integrity/coverage/contract violation permanently disables retry for that candidate,
even if someone later restores the bytes. Unknown failure causes deny retry.

In one transaction resolve the warning as `publication_retry` with the retrying
Admin/time; transition the run to `publishing`, clear its current error and increment
publication generation, execution fence and run/candidate revisions. Rearm the same
outbox row as `pending` with both current generations in its payload, new dispatch
generation, zero enqueue count and current availability time; clear its old dispatch
lease/acknowledgment/error and store the queued command receipt. Clear stale run
ownership/lease; the worker claims new authority. Preserve errors in attempt/warning
history.
Keep slot, candidate, frozen evidence and original approval. Return 202 only after
commit. Another exhausted failure creates a new warning; prior resolved warnings
and finished attempts remain. The retry actor never replaces the approving actor.

The worker inserts `attempt=publication_generation+1` and reruns complete local
and remote verification against the original hashes. No cached verification result,
new extraction, replacement evidence or resumed old attempt is allowed. The unique
step plus state/fence/generation checks keep duplicate/new-old queue deliveries
from repeating verification. This makes per-GET resume bookkeeping unnecessary.

### Failure classification required for safe retry

`load_candidate` currently maps every exception to generic `dependency_unavailable`;
the S3 adapter also collapses missing/denied/exhausted reads into `object_read_failed`.
These inspected facts mean their generic codes **cannot** grant retry eligibility.
Add a small typed internal failure result through the existing verifier/adapter,
keeping Refresh's outward safe errors unchanged. Do not duplicate validation rules
or infer causes from raw exception text. Persist safe causes in existing publish
step/warning fields; use one eligibility rule for reads and commands.

| Recorded cause | Retry policy |
|---|---|
| Positively classified temporary storage/queue exhaustion, known rolled-back transient database failure, deadline exhaustion after stop proof | Admin retry may start a new generation if all recorded evidence/approval requirements hold. Existing per-call automatic attempts stay bounded by A19. |
| Confirmed interrupted publisher with no committed event and no recorded permanent violation | Operator records an operational interruption; Admin may retry, but the worker must verify all bytes again. Recovery does not assert that the files are intact. |
| Missing/changed evidence or files, invalid/mixed validation, unsupported contract, stale approval, coverage regression | No retry or approval bypass. Preserve cause/history; discard/new work is the recovery option. |
| Denied access, invalid configuration, unclassified errors or unresolved execution/commit state | No optimistic retry. Known permission/configuration errors fail without automatic retry; unknown ownership remains blocked. |

A generic dependency wrapper must never turn integrity failures into recoverable
ones. Tests must exercise the actual wrapper and adapter, not only a mocked classifier.

### Operator interface — required executable delivery

From `backend/`, implement this mode in the existing worker entrypoint. The syntax
below is the required interface, **not a command available before implementation**:

```sh
uv run --locked python -m trinity.workers publication-recover --run-id <UUID> --inspect
uv run --locked python -m trinity.workers publication-recover --run-id <UUID> --expected-generation <N> --expected-fence <F>
```

`--inspect` is read-only and returns the current publication generation/fence for
that run, state, version/event/warning IDs and recorded retry eligibility. Its
output is not stop proof. The second form explicitly requests reconciliation of
that observed target; both expected values are mandatory. No `--force`, arbitrary
root/path, actor, SQL, replacement checksum or override option is accepted.

Required access: run as the trusted worker OS service account on the recorded
host, with access to its private durable `TRINITY_REFRESH_ROOT`, the locked runtime,
and configured `TRINITY_DATABASE_URL`/worker database privileges. This is a local
operator capability, not an HTTP Admin session or a database-superuser requirement.
Keep configured credentials out of arguments/output. Require neither EIA nor S3
nor Redis configuration/access: route this CLI branch before `serve()` initializes
those dependencies. Merely exposing today's recovery role would not satisfy this.

Reconciliation is one bounded operation, not a daemon or retry loop. Use existing
bounded database transactions and nonblocking lock acquisition. Its rules are:

1. Resolve the target run/version from PostgreSQL. A valid existing same-version
   event returns `already_published` with no mutation, even if a later publication
   is active. An already safely failed target in the expected generation returns
   the read-only result described in rule 4. For new effects, open the original
   recorded lock with no-follow and
   **without creating it**; verify host/inode and acquire it exclusively. Hold it
   through the transaction. A held/missing/replaced/wrong-host lock denies mutation.
2. Use canonical SQL locks; recheck the event and expected generation/fence. If
   another Admin retry advanced the generation, return `blocked` with reason
   `stale_target`; never fail that new attempt. Require interrupted `publishing`,
   owned slot, active candidate
   and expired execution/dispatch leases where present. Expiry is an additional
   guard, never proof of stop. An in-flight database commit must resolve under the
   locks before absence of an event can justify failure.
3. If no event committed, invalidate old owner/fence and dispatch generation, clear
   execution/dispatch leases, and set the outbox to `pending` with null lease token
   and acknowledgment time. Update its payload dispatch generation; preserve the
   enqueue count. The failed run is ineligible for dispatch, so this does not enqueue
   work. Finish or create the single failed publish step, and record
   `publication_failed` plus one unresolved
   warning and revised public state atomically. Preserve all existing permanent
   error evidence. Keep candidate, approval and admission; do not change publication
   generation, enqueue work, verify files, discard, or release the slot.
4. Repeating recovery for the same generation already safely failed returns
   `already_failed` without another warning or revision. That read-only outcome and
   `already_published` need no new stop proof; every mutation does. After an uncertain
   CLI commit, report uncertainty and let a repeat reconcile the recorded outcome.
   A changed generation always prevents a failure mutation, including delayed calls.

Emit one sanitized JSON result on stdout (except `--help`): `outcome`, `run_id`,
`run_status`, nullable `version_id`, `publication_generation`, `execution_fence`,
`publication_event_id`, `warning_id`, `retry_eligible`, and safe `reason_code`.
Unknown fields are null, not invented. No credentials, storage paths or traceback.

| Exit | Outcomes | Meaning |
|---|---|---|
| 0 | `inspected`, `recovered_failure`, `already_failed`, `already_published` | Inspection or reconciliation completed. Only the existing-event outcome establishes prior publication; recovery never means new publication. |
| 2 | `invalid_input`, `not_found`, `not_applicable` | No mutation; invalid arguments/target or a state outside this operation. |
| 3 | `blocked` | No mutation; reason identifies access denial, lock held/unknown, lease not expired, or stale target. Operator restores the required conditions and inspects again. |
| 4 | `dependency_unavailable`, `outcome_unknown` | No success claim. PostgreSQL/configuration unavailable or commit outcome uncertain; retain the blocker and reconcile after access returns. |

The trusted operator must be able to inspect, invoke, read the result, and complete
this path using the delivered executable and help text. A manual database edit,
PID check, lease wait alone, runbook-only workaround or untested future CLI is not
acceptance. The CLI does not terminate processes. A still-running/hung worker must
end under the host operator's normal service controls before exclusive lock proof
is possible; no public cancellation or automated hard-kill capability is promised.

Once recovery records a safely stopped recoverable failure, the Admin explicitly
requests retry via the API above, or discards via its canonical command. Operator
access alone cannot approve data or select an Admin retry. Same-host stop proof,
fences, exact attempt guards and transaction checks remain required even though
automatic crash recovery and multi-host failover are deferred.

## Validation and remaining review

[Essential E01–E10](spec.md#essential-acceptance--must-pass-before-delivery) keep
transaction, crash-stop, duplicate and reader safety as release gates. Use existing
locked unittest/disposable PostgreSQL/Redis tools from [backend README](../../backend/README.md);
extend them only during authorized implementation. Record actual query-container
checks separately from injected executors, and synthetic storage separately from
live S3 protection. No new runtime results are claimed by these approved documents.

Automatic multi-crash recovery, per-operation resume accounting and multi-host/
hard-deadline tests are deferred **with their capabilities**. The operator CLI,
same-candidate retry and their real subprocess/database tests are release gates.
No uninterrupted availability, automatic slot release or full A16 recovery claim
remains. Maintain data evidence — ongoing; no findings are added by this revision.

Done: scope/design approved and reconciled under A24; bounded tasks drafted.
Pending: task review and executable acceptance; storage custody/topology remain unverified.
Blocker for implementation: separate implementation authorization.

Next: [ME] review [Task 1](tasks.md#task-1--maintain-data-evidence--ongoing).
