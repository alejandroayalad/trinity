# Specification: Build Publication — first delivery

Date: October 4, 2026. Status: **approved scope; Tasks 1–6 implementation authorized**.
Approval: October 4, 2026, under [A24](../../DECISIONS.md#a24--build-publication-first-delivery).
Implementation: [Tasks 1–6](tasks.md); current results are in the linked acceptance record.
Related: [design](design.md), [original proposal](proposal.md).

**Subsequent authorization:** alayala authorized complete implementation of Tasks 1–6
and disposable local checks without intermediate approval stops. Earlier statements
below about unstarted work or missing implementation authorization are historical
planning text. Current code, measured gates and remaining limits are in the
[implementation/acceptance record](../../ai/sessions/2026-10-04-publication-implementation-acceptance.md).
No live/retained change, commit, push or PR is authorized.

## Human

**Input:** one registered candidate, its frozen evidence and publication request.
**Flow:** wait for Admin approval only if review warnings exist → verify the exact
evidence and files once per authorized attempt → atomically make that version active.
**Output:** new analytical requests use it; requests already running finish on
their original version. Old Preview page cursors return `publication_changed`.

**Failure example:** storage times out while publishing B. A stays available and
B retains the refresh slot. After a safely recorded recoverable failure, an Admin
retries B with its original evidence and approval; no EIA extraction repeats.
After a crash, the operator must first prove stop and reconcile the outcome.
Missing or changed files block publication and cannot be waived by retry.

## Approved scope and decision history

Alayala approved this smaller delivery, not completion of all A16 recovery.
[A24](../../DECISIONS.md#a24--build-publication-first-delivery) records the approval and supersession;
[schema](../../docs/schema.md), [API](../../docs/api-contract.md) and
[security](../../docs/security-contract.md) reflect it. P2 remains historical.
The scope below is selected; implementation and runtime acceptance remain pending.

| Keep / Simplify / Defer | Scope and reason | Guarantee or capability affected |
|---|---|---|
| **Keep** | Exact evidence verification, warning approval, atomic event/pointer/run/slot transition, ordering and pinned readers. | Publication correctness is unchanged. |
| **Simplify** | One worker host, one verification invocation per publication generation; reuse outbox, run fence/lease, step and local lifetime lock. | No new execution tables or per-object retry ledger; duplicates never restart an attempt. An explicit Admin retry creates the next generation. |
| **Simplify** | Existing bounded S3 read retries and outbox enqueue attempts only. | Remove whole-verifier and final-commit retry loops; service interruptions may require an operator. |
| **Defer — D1** | Automatic repair of lost delivered publication jobs and resumption after a publisher crash. Explicit stop-proof reconciliation replaces them. | Accepted A24 narrowing of A9/A15 recovery through `schema.md` and `backend.md`; no unattended publication recovery promise. Refresh recovery stays unchanged. |
| **Keep — D2 withdrawn** | Deliver operator recovery, Admin same-candidate retry, approval and discard, each with acceptance tests. | Retry preserves valid data and the original approval, restoring A16/A19 behavior. Operator recovery alone never authorizes another attempt. |

**Accepted operating model O1:** one supported worker host with Refresh's retained local
evidence and lock files; a fixed 300-second publication work deadline, without a
new heartbeat loop or child-process supervisor. This replaces unaccepted P2
settings. The deadline is fresh only for an explicitly authorized new attempt.
Deadline expiry forbids publication; it does not prove process exit or
promise the slot is released within 300 seconds. See the design's stop-proof rules.

Setup/schedule writes, scheduling, frontend, Run again/warning deletion, rollback,
republishing and cleanup remain outside this delivery. Unimplemented actions must
stay disabled in `/me` and run/candidate reads. No new public recovery endpoint.

## Essential requirements

PUB-R01–R08 retain the reduced core; PUB-R09 adds explicit same-candidate retry.
Transport/authentication details are inherited by reference, not removed.

| ID | Required behavior |
|---|---|
| PUB-R01 | Only an active registered validated candidate can publish. Verify original receipt, manifest/bundle and all referenced local/remote bytes against retained trust anchors; compare database artifacts/results to the same successful validation step and connector attempt. Require all 16 required passes and 23 completed known diagnostic evaluations, exact frozen warning count/digest, supported contract/checkset and frozen coverage. No missing/mixed/changed evidence or approval bypass. |
| PUB-R02 | Zero warnings use existing automatic intent; warnings wait for current Admin approval bound to version, manifest, validation step and warning digest. Approval, transition to `publishing`, outbox obligation, revisions and command receipt commit together. No file verification or publication inside HTTP commands. |
| PUB-R03 | Reuse durable `publish_version` intent and validate its IDs/kind/generations against PostgreSQL. Commit one claim marker per publication generation before verification; duplicate delivery cannot invoke that attempt again, even after restart. Only an authorized Admin retry advances publication generation and permits fresh verification. Keep bounded transport retries and shared run fence; no automatic resume, in-place budget reset or late commit. |
| PUB-R04 | Verify outside the final SQL transaction. Under canonical locks, first return an existing same-version event without pointer changes. Otherwise require current owner/fence/lease, publishing state, owned slot, active disposition, matching verified evidence/approval, newer run sequence and nonregressing coverage. Atomically insert the event, update active pointer, succeed run and publish step, update revisions and release its slot/lease. Any failed write or commit leaves no partial publication. |
| PUB-R05 | A completed unsuccessful verification records a failed publish step, `publication_failed` with null run `finished_at`, safe unresolved warning and retained candidate/slot. Unknown commit outcome first requires event lookup. Database unavailability or unknown execution leaves the blocker in place; never assume success, failure persistence or safe release. Prior publication remains usable; first-publication failure leaves readiness false. |
| PUB-R06 | Deliver the executable operator interface specified in the design, with tested access, outputs and exit codes. Reconcile interrupted publication only after same-host exclusive acquisition of the original retained process-lock inode and a locked state/fence recheck. Existing event means success already committed. Otherwise invalidate old execution/dispatch authority and record stopped publication failure, preserving any known permanent failure. Do not advance publication generation, rerun verification, approve, discard or release admission. Missing/wrong-host/replaced/held lock proves nothing and permits no recovery mutation. |
| PUB-R07 | Admin discard is allowed only for an unpublished active candidate in `awaiting_approval` or safely stopped `publication_failed`. Atomically invalidate old work, record discarded actor/time, finish run as `discarded`, resolve associated warning, increment revisions, release the owned slot and store receipt. Preserve evidence/history. Afterward the existing start-refresh action creates a new run; no automatic new extraction. Discard while publishing or after publication is forbidden. |
| PUB-R08 | Preserve one pinned version per analytical request, role restrictions, Preview continuation behavior and truthful existing status/action reads. Retain old published data. Approval/retry/discard inherit current authorization, exact candidate ETags, idempotency replay and safe errors from the canonical command contract. Reads and direct commands must agree on current retry eligibility; unknown failure causes are not automatically recoverable. |
| PUB-R09 | Implement Admin `POST /api/v1/candidates/{version_id}/publication-retry`. Require safely stopped `publication_failed`, owned slot, current revision, active validated unpublished candidate, intact recorded evidence, original bound approval if needed, unresolved recoverable warning and no recorded integrity/coverage/contract violation. Atomically resolve warning as `publication_retry`, transition to `publishing`, advance publication generation/fence and public revisions, rearm the existing outbox with a new dispatch generation and receipt; keep slot, candidate and approval. The new attempt rechecks all exact local/remote evidence before publication. Another failure creates a new warning; replay creates no new attempt. |

An older unpublished run takes the canonical supersession path without changing
the pointer; a newer candidate with narrower coverage fails `coverage_regression`.
Never mark an already published version discarded or superseded. Frozen storage
must prevent changes between verification and commit; hashes alone do not supply
that protection. Live protection/custody verification remains a deployment gate.

## Who clears a blocked refresh?

| Observed state | Who can act | Required proof and result |
|---|---|---|
| Waiting for review | Current Admin | Approve the exact eligible candidate, or discard it. Approval retains the slot; discard releases it. |
| Normal recorded publication failure | Current Admin | Retry a recoverable failure on the same candidate and original approval, retaining the slot; or discard and release it. Integrity/unknown failures do not enable retry. |
| Crash, lost delivered job or uncertain commit | Worker-host operator, then Admin if needed | The required reconciliation mode proves no execution via the existing lock, checks for an event and rechecks authority under SQL locks. A committed event is preserved; otherwise record stopped failure. Admin may then retry if eligible or discard. |
| Ownership or database state cannot be established | Neither actor can bypass it | Keep the blocker. Restoring the original host/custody/database is required; lease expiry, a PID check or manual SQL clearing is not proof. |

The operator records a technical outcome; the operator does not approve data or
discard a candidate. This maintenance path is not a user cancellation action.
The command, safe repeat behavior, and real subprocess/database tests are mandatory
first-delivery acceptance. Documenting a procedure alone does not satisfy PUB-R06.
The command is specified here for implementation; it is not runnable today.

## Essential acceptance — must pass before delivery

These are planned tests, not results. E01–E10 replace the previous PUB-S01–23 list
as the first-delivery gate; deferred resilience is separated below.

| ID | Required evidence |
|---|---|
| PUB-E01 | Real registration → real publisher for zero warnings and bound Admin approval. All three readers use the resulting event; tests must not insert publication events/pointers to simulate success. |
| PUB-E02 | Missing/failed/mixed checks, incomplete diagnostics, altered/missing files, stale approval and unsupported contract never activate. Older-run supersession and coverage regression never move the pointer backward. |
| PUB-E03 | Real PostgreSQL write/commit failure injection proves event/pointer/run/step/slot atomicity. Duplicate delivery, lost commit response and replay after a newer publication create no extra event or pointer regression. |
| PUB-E04 | Approval/retry/discard use inherited current-authority, replay and ETag behavior. Independent-process approval/discard and retry/discard races have one winner. Viewer/Analyst/invalid sessions cannot mutate; request replay with an obsolete ETag returns the original receipt without another generation. |
| PUB-E05 | Real Redis duplicate/unacknowledged delivery plus process restart invokes verification at most once per publication generation; only a new Admin retry permits another invocation. Existing enqueue and S3 read attempt limits hold; failure/deadline preserves the old publication and blocks refresh. No resumed invocation resets counts. |
| PUB-E06 | Kill the publisher before/after claim, during verification and around commit. Explicit reconciliation preserves committed success or records stopped failure without rerun. Held/missing/replaced/wrong-host locks and a still-running timed-out thread cannot be reclaimed. Stale writes cannot fail, publish or release another owner's work. |
| PUB-E07 | Admin discards a safely failed candidate, preserving files/approvals/warnings; a new refresh is then admitted. Stale queue work cannot revive it. Verify actual status, ETag, correct retry eligibility and first-publication failure behavior. |
| PUB-E08 | Real publisher enables Catalog/Preview/SQL with role restrictions. A request overlapping publication retains its original files/diagnostics; new reads use the new version and old Preview cursors return `publication_changed`. Actual query-container acceptance remains required, separate from isolated-reader mocks. |
| PUB-E09 | Run the actual operator CLI as subprocesses with disposable PostgreSQL and real held/released lifetime locks. Test inspect-only behavior, OS/database access failure, exact generation/fence targeting, stale target after Admin retry, two concurrent operators, repeated/lost-response recovery, database failure and all documented exit codes. Recovery works without EIA/S3/Redis configuration or calls. Its failure transaction preserves history/slot and has no partial effect on rollback. A help page or manual SQL is not acceptance. |
| PUB-E10 | Real publication temporary failure → Admin retry → fresh verification → success, for automatic and warning-approved candidates. Preserve candidate/evidence/approval bytes and approving actor; record retrying actor separately. Change/remove bytes before retry execution: no publication, permanent failure and retry disabled, even if bytes are later restored. Verify original warning resolution/new warning history, new generation/deadline, no EIA calls, stale-delivery rejection and one invocation per explicit attempt. |

## Deferred operational resilience

| Later capability | Tests deferred with that capability; no first-delivery promise |
|---|---|
| Automatic queue repair and crashed-verifier continuation | Repeated Redis loss and autonomous resume across multiple crashes with durable per-operation accounting. Operator recovery and crash safety remain E05/E06/E09; explicit retry remains E10. |
| Multi-host failover and hard process deadlines | Ownership transfer to another host, automated child kill/reclaim, heartbeat renewal and throughput under repeated stalls. First delivery retains unknown ownership instead. |

## Historical specification review gate

Inspected HEAD: `b018784`, branch `feat/refresh-publication`; Refresh Task 5 and
migrations through 0007 are now committed. Its [handoff](../../ai/sessions/2026-10-04-refresh-task5-receipt-routing.md)
records 63 disposable-service checks; they were not rerun here and do not prove
publication. The design names inspected methods and distinguishes reuse from new work.
Maintain data evidence — ongoing; no synthetic test establishes an EIA finding.

Done: scope approved; A24 and canonical contracts reconciled; bounded tasks drafted.
Pending: task review and later implementation/acceptance evidence.
Blocker for implementation: separate implementation authorization.

Next: [ME] review [Task 1](tasks.md#task-1--maintain-data-evidence--ongoing).
