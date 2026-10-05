# Proposal: Build Publication

**Historical proposal:** the original text below is preserved. October 4, 2026
approval under [A24](../../DECISIONS.md#a24--build-publication-first-delivery) supersedes conflicting
operating/recovery proposals and this document's former review gate. The approved
[specification](spec.md), [design](design.md) and [tasks](tasks.md) govern the first
delivery; implementation remains unauthorized.

Date: October 4, 2026. Status: **draft for review; implementation not authorized**.
Inspected baseline: `4ce9a8f`, branch `feat/refresh-publication`.
This is a separate slice from [Build Refresh](../refresh-publication/proposal.md).

## Human

Make one verified candidate available to readers without exposing partial data.
Refresh prepares and registers the candidate. Publication decides whether that
exact candidate can become active and records the change in PostgreSQL.

Input: a registered, validated candidate with frozen files, check results and
diagnostics, plus durable publication intent. If review warnings exist, a current
Admin must first approve that exact candidate.

Flow: accept automatic intent or bound approval → dispatch publication work →
verify evidence and stored bytes → recheck eligibility under database locks →
commit publication event, active pointer, run success and slot release together.

Output: new analytical requests use the new publication. Requests already executing
keep their pinned version. A Preview continuation across a publication change
returns the existing `publication_changed` response and must restart pagination.

Failure example: storage becomes unavailable while the publisher verifies a
candidate. The previous publication remains active. After bounded retries are
exhausted, the run becomes `publication_failed` with an unresolved warning. An
eligible Admin retry reuses the candidate and any original approval. Changed or
missing candidate bytes cannot be approved or retried into eligibility.

### Proposed scope

| Work | Observable result |
|---|---|
| Reuse registered evidence | Complete matching validation and frozen diagnostics are required; no new validation engine or replacement candidate is created. |
| Dispatch and execute publication | Consume `publish_version` obligations with durable attempts, generations, worker fencing and restart recovery. Duplicate delivery has one publication effect. |
| Approve a candidate | Canonical Admin approval command records the exact approval, run transition, publication obligation and command receipt atomically. |
| Activate a version | Record a unique publication event, change `active_publication`, finish the run and release its slot in one transaction. Readers never see a partial transition. |
| Retry or discard | Implement canonical candidate publication-retry and discard commands, preserve history, and prevent stale work from reviving abandoned candidates. |

Approval, retry and discard use the existing `/api/v1/candidates/{version_id}`
command paths, permissions, empty request bodies, idempotency keys, exact candidate
ETags and receipts from the API contract. Publication progress and eligibility must
remain visible through existing run/candidate reads; reuse Task 5's detail endpoint.
No frontend is included.

### Dependencies and boundaries

Refresh Task 5 must first demonstrate successful worker-to-registration routing,
safe completed-receipt recovery and candidate detail reads. At inspection, its
[task record](../refresh-publication/tasks.md) still marked integration pending.
This proposal can be reviewed in parallel; it does not claim that gate passed.

Outside this slice: source extraction, preparation/validation rewrites, setup and
schedule writes, daily scheduling, frontend, publication rollback, republishing an
already published version, and cancellation of active work. Refresh Run again and
warning-deletion commands remain separately tracked dependencies; candidate discard
provides the abandonment path for this slice's review/publication-failure states.
Do not claim the complete A16 recovery surface until those separate commands exist.

Live EIA/S3 work, retained-database migrations, live activation and retained-account
operator checks require a separate deployment gate. A fresh installation still
needs setup writes. No production dependency is proposed.

## LLM — authority and implementation constraints

[DECISIONS.md](../../DECISIONS.md), especially A9/A16/A19/A20/A22/A23, remains the
decision record. Use [schema.md](../../docs/schema.md),
[api-contract.md](../../docs/api-contract.md), [OpenAPI](../../docs/openapi.json),
[security-contract.md](../../docs/security-contract.md) and
[backend.md](../../docs/backend.md) as the canonical contracts. The
[integration contract](../refresh-publication/integration-contract.md) supplies
the receipt/attempt mapping; its broader publication cases remain applicable.

### Current source and reuse

`persist_candidate` in `backend/src/trinity/refresh/registration.py` already records
Preview-compatible evidence and either creates `publish_version` intent or selects
`awaiting_approval`. It releases the preparation lease but retains admission.
The publisher therefore needs its own claim, deadline and execution ownership;
it must not reuse an expired preparation lease or reset the preparation budget.

At the inspected baseline, `backend/src/trinity/publication/` contains only
`__init__.py`, `repository.py` and `diagnostics.py`. The repository functions read
publication state; the diagnostics module reads frozen evidence. There is no
publication command service or worker in that directory. Refresh dispatch is
explicitly limited to refresh jobs. These are source observations, not deployment
or runtime conclusions. Recheck the final Task 5 handoff before writing code.

Preserve `data_versions.evidence_bundle_sha256`, `validation_attempt_id`, the
selected validation step and receipt/manifest bindings. Preserve the existing
migration chain through `0006_refresh_dispatch`; append any justified migration
after the actual head at implementation time. Never fabricate historical evidence.

### Required guarantees

1. **Eligibility:** require active disposition, the correct run and publication
   generation, complete same-attempt required results, complete frozen diagnostics,
   intact evidence/files, and exact approval when warnings require it. Reuse the
   existing verification rules. Approval cannot waive failed or missing checks.
2. **Authority and command replay:** resolve current Admin/session authority before
   protected state or receipt access. Matching actor/action/target/body replays the
   original receipt before stale-ETag checks. Conflicting reuse and concurrent
   approval/retry/discard must follow the canonical error and transaction rules.
3. **Publication consistency:** return an existing event for the same version on
   duplicate completion without moving the pointer. For a new event, enforce run
   ordering and nonregressing coverage. Verify remote bytes outside the final
   transaction, then recheck state under the canonical lock order. Immutable storage
   must preserve those verified bytes through commit. Record the approving actor
   and derived automatic/approval outcome correctly.
4. **Durable recovery:** separate queue repair generation from explicit publication
   retry generation. Persist external-attempt accounting across redelivery; apply
   A19's three-total-attempt ceiling for temporary failures. Do not retry denied
   access, integrity failures or validation failures. Expired ownership alone does
   not prove execution stopped. Unknown execution state retains the blocker.
5. **Failure and abandonment:** exhausted/permanent publication failure retains the
   slot and evidence, sets `publication_failed`, and leaves run `finished_at` null.
   Retry resolves the old warning, rearms the existing obligation and retains original
   approval; another failure creates new warning history. Discard requires no active
   publisher, invalidates stale work, records permanent abandonment and releases the
   slot atomically. Discard does not delete files or audit records.

Feature services own transactions. Keep publication rules in the publication
feature; worker/queue adapters delegate to them. Preserve existing readers and
Refresh behavior. No HTTP command performs remote verification or publication inline.

## Acceptance evidence required

| Scenario group | Required proof |
|---|---|
| Automatic and approved paths | Real registration feeds the real publisher; zero warnings publishes without approval; warnings wait for exact authorized approval. Failed/incomplete/mixed evidence never activates. |
| Transaction and concurrency | Inject failure at each final write and commit; previous pointer and slot/state remain consistent. Race approvals, retry/discard and workers in separate processes. Replays create one event and no pointer regression. |
| Queue and execution recovery | Disposable PostgreSQL/Redis and real worker lifecycle checks cover queue loss, duplicate delivery, restart before/after commit, stale fences, bounded attempts and deadline exhaustion. |
| Integrity and ordering | Alter or remove evidence/files, supply stale approval, discard a candidate, deliver older work and attempt smaller coverage. Each takes the canonical rejection/supersession path without changing the active valid version. |
| Reader compatibility | A production publication transaction enables actual Catalog/Preview/SQL readers. Verify initial readiness, all three roles, an in-flight pinned read and Preview pagination across a switch. Test fixtures may create source data, but must not insert publication events to simulate this slice's success. |

Use repository test commands and disposable services. Separate synthetic storage
evidence from live S3 guarantees, and isolated reader tests from real query-container
acceptance. Retained-account acceptance is a later deployment check. Maintain data
evidence — ongoing; synthetic cases do not establish new EIA findings.

## Decisions needed in specification and design

Define publication-specific finite deadlines, lease/heartbeat rules, stop/reclaim
proof, temporary-error classification and durable retry accounting. Reconcile the
publication job payload with existing outbox generation fields. Choose any necessary
schema additions only after inspecting Task 5's final migration head and evidence
custody. These are open implementation details, not permission to weaken contracts.

## Review gate

Done: Publication scope, dependencies, failure behavior and acceptance expectations
are proposed from the inspected source and accepted contracts.
Pending: user review; then a Publication specification, design and bounded tasks.
Blocker for implementation: separate implementation authorization and verified
Refresh Task 5 handoff. No publication runtime tests were run for this document.

Next: [ME] review this proposal. Approval advances the specification gate only;
it does not authorize code, migrations, live activation, commits or push.
