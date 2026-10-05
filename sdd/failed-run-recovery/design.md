# Design: Failed-run recovery commands

Date: 2026-10-05
Status: Steps 2–3 authorized and implemented locally October 5, 2026. See [Step 2 evidence](../../ai/sessions/2026-10-05-failed-run-recovery-step-2.md) and [Step 3 implementation](../../ai/sessions/2026-10-05-failed-run-recovery-step-3.md). Runtime acceptance remains pending.
Branch: `pending-endpoints-frontend`.
Basis: [accepted specification](spec.md), [proposal](proposal.md), [tasks](tasks.md), A15/A16/A19/A20/A23/A24 in [DECISIONS](../../DECISIONS.md), [backend responsibilities](../../docs/backend.md), [API contract](../../docs/api-contract.md#commands-and-concurrency) and [schema abandonment rules](../../docs/schema.md#failure-resolution-and-abandonment).

## Human

### Proposed behavior

Use the existing Refresh feature for both commands. An Admin sends the failed run ID, revision and command key. The service verifies that the failure is safe to resolve, then commits all changes together. Run again starts a new full refresh with current settings, as accepted in P01. Resolve warning releases the blocker without starting work.

Example: A failed with settings revision 4; settings are now revision 6. Run again creates B using revision 6, with `rerun_of_run_id=A`. A retains revision 4. The existing published dataset remains available.

Failure example: inserting B's outbox record fails. The transaction rolls back B, the warning resolution, old candidate abandonment and the slot transfer. A still blocks refresh, and the Admin can retry the same command key.

### Important distinction from the current code

Refresh failure can retain `worker_owner_id` after confirmed child stop. Publication failure uses a different stopped-failure record and clears ownership. A single rule such as “owner must be null” would incorrectly disable some safe Refresh failures. This design uses evidence appropriate to each failure path, and rejects unknown execution state.

No new dependency, background service or public operator-stop endpoint is proposed. Design and test plans below are not runtime proof.

## LLM

### D01 — Feature ownership and file scope

| File | Proposed responsibility |
|---|---|
| `backend/src/trinity/refresh/router.py` | Add exact rerun POST and warning DELETE routes; preserve threadpool service calls, status codes and safe tracking responses. |
| `backend/src/trinity/refresh/schemas.py` | Add strict recovery request parsing and extend receipt action/result literals to canonical values. |
| `backend/src/trinity/refresh/recovery.py` (new) | Recovery command service and shared eligibility calculation; service owns one transaction and coordinates repositories. |
| `backend/src/trinity/refresh/repository.py` | Target recovery reads/locks, abandonment writes and explicit rerun admission support. No independent commits. |
| `backend/src/trinity/refresh/service.py`, `tracking.py`, auth app-entry integration | Replace hard-coded disabled action flags with the shared recovery eligibility; preserve consistent read snapshots. |
| `backend/src/trinity/publication/commands.py` | Align command lock acquisition where required; preserve publication behavior and replay semantics. |
| `backend/src/trinity/errors.py`, `main.py` | Only necessary transport/route injection changes, backed by exact-route tests. |

Use existing `Database.transaction`, `Deadline`, `_authorize`, `_receipt`, `lock_control`, `read_command`, Publication stopped-failure checks and durable outbox. Avoid importing the new service into a repository or introducing circular imports through `refresh.service`; extract only the small shared authorization/receipt helper if required by the dependency graph.

Before implementation, rebase the design mechanically against the delivered schedule-settings helpers. Reuse its settings snapshot and admission entry points; do not duplicate the scheduler or overwrite concurrent settings work.

### D02 — HTTP validation and replay

Initial authorization precedes target/receipt lookup. Enforce bounded transport input using existing limits. POST requires JSON `{}`; DELETE accepts no body, including `{}`. Reject query parameters, repeated command headers, noncanonical IDs and malformed run ETags. Validate header presence/syntax before replay, but compare the revision only for new intent. Replaying a valid old ETag remains allowed.

Canonical fingerprint inputs contain the endpoint's fixed empty intent; action and target are separately bound in `api_commands`. For DELETE, use one defined empty-intent representation consistently (canonical `{}` for hashing), without treating a supplied JSON body as valid. The global unique key must conflict across actors/actions/targets. Reuse neither another actor's receipt nor its resource details.

For rerun, the receipt `target_id` is A while `run_id` and `status_url` identify B. `version_id` is null because B has no candidate at acceptance. Warning resolution targets and tracks A; preserve its candidate ID in the nullable receipt field when present. Always return only after transaction commit. New rerun returns 202, Location and existing polling guidance; new delete and authorized replay return 200. Do not convert a post-commit dispatch outage into a failed acceptance.

### D03 — Common locking and transaction order

Proposed shared mutation order is:

1. Authorize without row locks and parse bounded syntax. Lock `refresh_control` first.
2. Lock/recheck the current user and session through existing authorization helpers. Read the command receipt; replay or conflict before target revision checks.
3. For new rerun intent, lock `shared_settings` for share and read the current coherent snapshot. For delete, do not require a settings change or new policy snapshot.
4. Lock target `refresh_runs`, its optional `data_versions`, then `active_publication`, matching the lifecycle order used by `publication.service.locked`. Inspect publication events before abandonment. Lock the unresolved warning and relevant step/outbox rows in stable order.
5. Check revision, admission ownership and shared eligibility; apply mutations and insert receipt; commit.

Existing `RefreshService.start` locks control before locking current authority, while `PublicationCommands.command` currently locks authority first. Align candidate commands to the proposed control-first order as part of this slice; do not add a third order. Audit settings writes, scheduler admission, logout, role changes, worker claims, publication commit and dispatch acknowledgement for reverse dependencies. Any path holding settings/user/session locks must not then wait for control in reverse order. Document the resulting lock graph and prove contention behavior in PostgreSQL before claiming acceptance.

Workers without user authority keep control → run → candidate → active pointer as applicable. Querying an existing receipt needs no mutation of the receipt; shared admission serializes these command insertions, and the unique key remains the database backstop. Reuse existing bounded transaction/lock timeouts, without adding retry loops that reset the deadline. A failed or deadlocked transaction returns the safe dependency error and leaves no effects.

### D04 — Eligibility and stopped execution

New commands require A to own the retained admission slot, an unresolved operational warning, failed/publication-failed state, no published event for its candidate, and an active candidate disposition if one exists. Reject unexpected ownership or inconsistent state rather than clearing another run's slot. Rerun also requires completed setup. A valid matching receipt can replay after these states have changed.

| Failure path | Required evidence before new intent |
|---|---|
| Dispatch failure before worker claim | Terminal failed run, null owner/lease, no worker execution reference or started preparation, and retained dispatch failure evidence. A late notification must still fail run-state/fence checks. |
| Preparation/validation failure | Terminal failed run and null lease; durable `worker_execution_ref.child_stopped=true` from the current failed execution. Check its recorded owner/fence binding against the run and actual failure path. Retained owner alone is not a running writer. |
| Publication failure | Reuse `publication.checks.stopped_failure`: null owner/lease plus finished failed publish step for the current publication generation. |
| Legacy, contradictory or unknown evidence | Disabled action and command conflict; existing operator recovery must establish proof first. Do not infer stop from elapsed time or missing PID. |

Trace every `fail_run` caller when implementing the predicate, including discovery rejection before worker claim. Extend the table only with observed durable proof; do not broadly accept every `failed` row. Read projections and mutation enforcement must call the same rule, with command checks repeated on locked rows. If the existing evidence cannot distinguish a safe path, add a narrow durable proof through the producing failure path and an append-only migration only if needed; keep that path disabled until proven.

### D05 — Atomic state changes

| Object | Rerun | Resolve warning |
|---|---|---|
| Warning | Set resolution `rerun`, actor/time. | Set resolution `delete_warning`, actor/time. |
| Old unpublished candidate | Set `disposition=discarded`, `discarded_by/at`, increment revision. Preserve status, evidence and files. | Same. |
| Old run | Increment execution fence and revision; clear obsolete execution authority after stop proof. Preserve failed outcome/time, or close publication_failed as failed with finish time. Retain errors/history. | Same. |
| Old outbox | Invalidate dispatch generation; clear lease token/lease and change dispatching to pending together to satisfy the existing lease constraint. Preserve delivered status/time where present and all attempt counts. Old terminal run/discarded candidate must be excluded from claim/recovery paths. | Same. |
| New run/outbox | Allocate fresh run/operation IDs, `trigger_kind=rerun`, link A, accepted current settings/policy snapshot; insert one refresh intent. | None. |
| Admission | Transfer ownership A → B in the same transaction. | Clear only ownership held by A. |
| Receipt | Store action/target/fingerprint and B tracking reference. | Store action/target/fingerprint and A tracking reference. |

Do not physically delete old outbox rows or invent a new outbox status: the current constraint permits pending/dispatching/delivered. Preserve generation fencing and make claim/recovery predicates exclude abandoned work. A stale network enqueue may still arrive; worker admission must reject it. Test stale acknowledgement, delivery and commit separately.

Generalize `accept_run` with explicit trigger/link/action/target inputs, preserving manual defaults and the schedule slice's scheduled identity. It must use the caller's transaction, frozen settings and one policy builder. Do not call `start()` after a separately committed warning deletion. Reset only new-run budgets; old deadlines and attempts remain historical. No storage or queue I/O occurs here.

### D06 — Schema and projections

Inspected migrations already provide `rerun_of_run_id`, rerun trigger kind, candidate discard actor/time, warning resolution values, API command target/receipt fields and outbox generation. Baseline: no new table or dependency. Check actual current migration head and constraints before code; never rewrite applied migration history.

Extend receipt literals (`rerun`, `delete_warning`, `warning_resolved`) and exact OpenAPI contract assertions. Update read-side state loading to supply stop evidence without external I/O. `/me`, list and detail must derive the same action reasons within their existing snapshots. Relevant state changes increment run/candidate revisions; old approval/history remains visible but cannot authorize discarded bytes. Keep Viewer/Analyst responses free of protected recovery state.

### D07 — Validation and delivery

Use new focused parser/eligibility/service tests, then existing Refresh/Publication/auth regressions. Add disposable PostgreSQL rollback injection after each write and true concurrent connections for command races. Exercise real HTTP response loss/replay, updated route inventories, headers and JSON serialization. Reuse the existing Refresh runner and fixtures for Redis/outbox delivery; do not build a second queue stack.

Acceptance covers specification S01–S12, including real stopped-writer evidence and stale deliveries. Measure results separately for offline, database, HTTP, queue and retained-operator checks. A test-created failure is not a retained deployment result. No live EIA key, retained state mutation, build or deployment is needed to draft this design.

Done: design accepted and Step 2 parsing/eligibility implemented. Pending: human explanation, Step 3 authorization and later runtime lock/stop verification. Blocker: none for the completed offline slice.

### Step 2 source reconciliation

Current migration head is `0007_refresh_registration`; Step 2 needs no migration. The `job_outbox` constraint requires dispatching rows to retain token/lease, so a later abandonment write that clears those fields must also change dispatching to pending atomically. Retain the old row and exclude it by terminal run state.

`ExecutionService.fail` checks current owner/fence and `child_stopped`, then marks unfinished steps abandoned, the candidate rejected, and the run failed. The JSON has an owner but no separate fence. The helper checks owner binding and relies on those fenced producing writes; it does not invent a JSON fence requirement. Recovery's `reclaim_stopped` changes both retained owner and JSON owner. A present JSON version ID must match the candidate; an absent one is possible when freezing succeeds but output-root reservation fails before reference enrichment.

`fail_run` has four call sites: `DispatchService.claim` and `DispatchService.recover` for exhausted attempts; `ExecutionService.claim` for policy rejection before worker start; and `ExecutionService.fail` after confirmed child stop. Pre-claim eligibility requires no candidate, owner, reference, fence increment or step, plus matching outbox attempts. Started failure requires confirmed stop and no running step. Unknown records remain disabled.

| Path inspected | Current acquisition order | Step 3 consequence |
|---|---|---|
| Refresh start | control → user share → session update → settings share | Preserve this order. |
| Candidate command | user share → session update → control → run → candidate → active pointer → warning → outbox | Must align control first before wiring recovery. Same-session concurrent commands can otherwise form reversed waits; runtime race proof is pending. |
| Settings update in active sibling worktree | user share → session update → settings update; no control lock | Compatible with proposed order because it never waits for control. Recheck its delivered version before integration. |
| Scheduler in active sibling worktree | control → settings share → admission writes | Compatible; reuse its `POLICY`/`_insert_run` and `accept_scheduled_run` work rather than replacing it. |
| Logout / login / seed | session only / user then session creation / seed advisory lock and identity writes; no control | No observed control dependency; role mutation tests must still hold user locks. There is no runtime role-editor path inspected here. |
| Refresh worker, dispatch, registration | control before run/candidate/step/outbox as applicable | No user/settings acquisition observed after these locks. |
| Publication worker/recovery | common control → run → candidate → active pointer before step/outbox | Preserve common ordering; operator holds lifetime custody outside the database proof. |

This is source-derived lock analysis, not a measured deadlock test. No command lock was changed in Step 2. `recovery_actions` is read-only and not wired into public action projections yet. Its caller must provide coherent trusted rows and use the established service authorization boundary.

### Step 3 implementation reconciliation

`RecoveryService.command` now owns the transaction. `RefreshService.recover` preserves the existing route service-injection boundary, so `main.py` needs no new injection. Both routes declare strict command parameters/body shapes and return committed receipts. Transport defers semantic query/body rejection on only those exact recovery method/path combinations to the authorized service.

`PublicationCommands.command` now checks authority without locks, then locks control, then rechecks and locks current authority before receipt lookup. Recovery uses the same control-first order. `lock_recovery_target` locks run/candidate/active pointer/warning/steps/outbox in the documented order. `abandon_failed` keeps old failure time/history, discards only the eligible candidate, increments execution/dispatch fences, changes dispatching outbox rows to pending while clearing leases, and conditionally releases the owned slot. Rerun admission and its receipt commit in the same transaction.

`POLICY` and `_insert_run` use the same factoring/signature shape inspected in the active schedule branch, with an optional rerun predecessor. Existing manual-call signatures remain valid. No schedule code was copied or changed in that worktree; its eventual merge still needs integration review. The recovery read projection now evaluates the shared helper inside `read_context`; `/me`, history and detail use those flags and historical runs cannot inherit another holder's enabled actions.

The Step 2 source-reconciliation table above describes the earlier baseline; the candidate command's reversed lock order is now corrected in source. Actual PostgreSQL deadlock/rollback/writer-race proof remains pending. Six opt-in database tests cover linkage, no-work deletion, every-write rollback, deferred commit failure and stale outbox state. Their presence is not a passed runtime check.
