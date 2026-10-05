# Proposal: Failed-run recovery commands

Date: 2026-10-05
Status: Planning only; separate commit/push authorized, implementation not authorized.
Basis: A9/A16/A19/A20/A22–A24 in [DECISIONS.md](../../DECISIONS.md), [command contract](../../docs/api-contract.md#commands-and-concurrency), [OpenAPI](../../docs/openapi.json), [security contract](../../docs/security-contract.md) and [Publication design](../publication/design.md).
Order: after [Dashboard](../national-dashboard/proposal.md), [Schedule settings](../schedule-settings/proposal.md) and [Plant filter](../plant-filter/proposal.md).

## Human

### Outcome and flow

An Admin resolves an operational failure without losing history or replacing the valid publication. “Run again” starts a new full refresh. “Resolve warning” removes the admission blocker without starting work. Neither action repairs data-quality warnings or resumes an old run.

| New endpoint, under `/api/v1` | Input | Atomic result |
|---|---|---|
| `POST /refresh-runs/{run_id}/rerun` | Admin session, UUID `Idempotency-Key`, current `If-Match: "run-<revision>"`, `{}` | Resolve warning as `rerun`, permanently abandon old unpublished candidate if present, invalidate old execution authority, create a linked new run and reserve its slot with outbox/receipt. New acceptance is `202`; replay is `200`. |
| `DELETE /refresh-runs/{run_id}/warning` | Admin session, UUID `Idempotency-Key`, current run `If-Match`, no body | Soft-resolve warning with actor/time, abandon any unpublished candidate, invalidate old execution authority and release the old slot. Return `200` with a warning-resolution receipt; start no work. |

Input → flow → output: verify current Admin authority → parse command identity → lock shared admission and relevant run/candidate/receipt state consistently → replay matching prior intent or check current revision and safe eligibility → commit all effects and receipt together → return `ActionReceipt`. Redis dispatch occurs later through the existing durable outbox.

Example: a failed run blocks admission while an older publication remains available. The Admin selects Run again. The failed run remains in history; the new run has a different ID and `rerun_of_run_id` points to the old one. The old publication stays visible until the new run legitimately publishes.

Failure case: two Admins act on the same run revision, one rerunning and one resolving its warning. Only one transaction may take effect. The other receives a stale-state or ineligible-state response and reloads; it must not create a second run or release the new run's slot.

### Accepted distinctions

| Action | What it means |
|---|---|
| Run again | New extraction/preparation/validation lifecycle with new identity. The old unpublished candidate cannot be revived. |
| Resolve warning | Preserve the failed outcome and warning history, remove the blocker, create no run. A future scheduled check may start work if enabled. |
| Existing Retry publication | Keep the same validated candidate and original approval when required, with a new publication attempt and full verification. Do not re-extract. |
| Existing Discard | Permanently abandon an eligible candidate. Its existing endpoint and terminal-state rules remain authoritative. |

Operational failure warnings and candidate data-quality warnings are different. Resolving the first never changes source values, validation results or review requirements. A terminal failed run stays failed. Abandoning `publication_failed` work closes that run as failed; direct candidate discard closes it as discarded. Published versions cannot be abandoned.

No action may run while an old writer can still commit. Expired leases or missing PIDs alone are not stop proof. Preserve A24's operator reconciliation and existing worker custody rules. Unknown execution state stays blocked; do not add a public operator-stop endpoint.

## LLM

### Reuse and current evidence

`RefreshService.start` and `refresh.repository.lock_control/read_command/accept_run` provide existing admission, receipt and outbox patterns. `PublicationCommands.command` already supports current-actor checks, receipt replay before revision checks, candidate action eligibility and atomic warning/disposition effects. Reuse reviewed primitives and consistent lock ordering rather than cloning candidate commands into an independent recovery path.

`refresh.repository.accept_run` currently hard-codes manual trigger and `start_refresh` receipt semantics. Rerun needs an explicit new-run path with `trigger_kind='rerun'` and `rerun_of_run_id`; do not call manual start after resolving the warning in a separate transaction. Preserve settings/policy snapshots and shared admission invariants. Specify whether/how current versus failed-run settings are used before implementation; the old run must remain unchanged.

`refresh.service.admin_context` currently sets `rerun` and `delete_warning` to false. The slice must update read-side action eligibility in `/me`, run lists and details as well as enforce it inside commands. Visible buttons are descriptions, never authorization. Reuse `publication.checks` stopped-failure evidence and existing refresh/publication recovery paths where applicable.

Absence evidence: inspect `backend/src/trinity/refresh/{router,service,repository}.py`, `publication/commands.py`, and search registered routes with `rg -n '@router\.' backend/src/trinity`. Refresh has start/list/detail; candidates have detail/approval/retry/discard; no rerun or warning-delete handler exists. The existing migrations already declare rerun links, trigger kinds, warning resolution fields and command receipts. Whether further constraints are needed belongs in design, not an assumed new schema.

### Transaction and retry requirements

Require current `refresh:recover` authority before protected lookup or replay. Bind the idempotency key to actor, action, target and canonical body. Matching retries return the same original receipt with `replayed=true` and `200` before checking an obsolete ETag. Conflicting reuse returns `409 idempotency_conflict`; receipt history has no time-based duplicate window. Never expose another actor's resource through a conflict.

Missing precondition is `428`, malformed is `422`, stale is `412`. Reject unsupported fields/queries and any warning DELETE body. Use canonical errors and bounded database lock waits. A failed transaction writes neither effects nor receipt. A lost HTTP response does not grant permission to create another run: replay the same intent/key.

On accepted abandonment, invalidate old fences and ensure late queue deliveries/worker updates cannot act on the old candidate. Release only the old run's owned slot; rerun reserves the new one in the same transaction. Preserve immutable evidence, approval/attempt history and stored bytes. No S3 deletion or queue call occurs inside the command transaction.

Resolve the precise lock order across session/user, admission, run, candidate, warning, outbox and receipt during design, including races with logout, publishers and scheduler admission. Do not treat a rendered enabled action as proof that the state is still eligible.

### Bounded sequence and acceptance

1. **Maintain data evidence — ongoing.** Keep failure evidence and selected anomalies. Recovery is operational state handling, not permission to alter observations or validation rules.
2. Specify request validation, eligibility, receipt replay, state transitions and run-policy selection.
3. Design the shared transaction/lock/fence path and read-side action projection against current migrations and operator recovery.
4. After separate authorization, implement commands and regression tests, including rollback and late-worker races.
5. Verify real PostgreSQL/HTTP/outbox behavior and a separate retained-Admin recovery flow without fabricating publication state.

| Acceptance area | Required cases |
|---|---|
| Access/input | Viewer/Analyst/expired session denied; authority rechecked on replay; malformed IDs, keys, ETags, bodies and unknown targets produce safe errors. |
| Replay/atomicity | Same intent returns original receipt; conflicting intent rejected; stale ETag replay works; failure at each mutation rolls back warning, disposition, fences, slot, run, outbox and receipt. |
| Eligibility/history | Failed run with/without candidate; publication failure; resolved warning; active/unknown writer; published/discarded candidate; old run outcome and evidence remain intact. |
| Races | Rerun versus delete-warning, discard, publication retry, publication commit, manual start, due scheduler, role change and logout; one winner; late worker/outbox delivery cannot revive abandoned work. |
| Output/runtime | Correct statuses/receipt targets, new run linked to old, read-side actions refresh, no immediate work for warning deletion, old publication and schedule preserved, real outbox dispatch for rerun. |

Done: source-grounded proposal. Pending: specification/design and explicit policy/locking details. Blocker: none for planning. No implementation or live recovery was performed.
