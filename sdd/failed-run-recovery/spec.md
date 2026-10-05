# Specification: Failed-run recovery commands

Date: 2026-10-05
Status: Accepted for design/tasks on October 5, 2026, including P01. Acceptance commit/push authorized on `pending-endpoints-frontend`; implementation and runtime recovery remain unauthorized.
Basis: [Proposal](proposal.md), A9/A16/A19/A20/A22–A24 in [DECISIONS](../../DECISIONS.md), [API command contract](../../docs/api-contract.md#commands-and-concurrency), [OpenAPI](../../docs/openapi.json), [security contract](../../docs/security-contract.md) and [schema](../../docs/schema.md).

## Human

### Outcome and flow

An Admin resolves failed work through **Run again** or **Resolve warning**. Run again starts a complete new refresh with a new ID. Resolve warning removes the operational blocker without starting work. Both preserve history and the last valid publication. Neither changes source observations, validation results or data-quality review warnings.

Input → flow → output: Admin supplies the failed run ID, its revision and a command key → server checks authority and safely stopped failure state → one transaction resolves the warning, abandons unpublished old work and records the result → server returns a tracking receipt. Rerun also creates and queues a linked new run within that transaction.

Example: run A fails while publication P stays available. Run again creates B with `rerun_of_run_id=A`; A stays failed and P stays visible until a new version validly publishes. Resolve warning creates no B. The daily schedule remains enabled if it was enabled before.

Failure case: two Admins submit Run again and Resolve warning for the same revision. One succeeds; the other reloads after a conflict or stale revision error. It must not release the new run's slot or create another run.

Existing **Retry publication** reuses the same eligible validated candidate and its required approval. Existing **Discard** abandons a candidate through its current endpoint. These are separate from the two new operations.

UI implementation, Plant filter, scheduler implementation, automatic operator recovery and changes to publication rules are outside this slice. Maintain data evidence — ongoing; synthetic recovery fixtures do not establish source anomalies.

## LLM

### HTTP contract

Paths have prefix `/api/v1`. Both commands require current Admin authority (`refresh:recover`), UUID `Idempotency-Key`, and `If-Match: "run-<revision>"` for the target run. Actor identity comes from the verified session.

| Operation | Body | New success | ActionReceipt semantics |
|---|---|---|---|
| `POST /refresh-runs/{run_id}/rerun` | Exactly `{}` | `202` | `action=rerun`, `result=queued`, new run ID and tracking URL. |
| `DELETE /refresh-runs/{run_id}/warning` | No body | `200` | `action=delete_warning`, `result=warning_resolved`, original run ID and tracking URL. |

Use the canonical ActionReceipt fields, including operation ID, acceptance time, nullable version ID and replay flag. Matching replay returns the original receipt identity and tracking reference with `replayed=true` and `200`. A receipt describes acceptance; poll `status_url` for current execution state.

### Requirements

| ID | Requirement |
|---|---|
| R01 | Authorize before protected lookup or replay. Recheck current actor authority under the transaction discipline. Reject Viewer/Analyst, expired/revoked/inactive sessions and unknown roles. |
| R02 | Validate run UUID, command key, exact run ETag, body and query shape. Reject unknown fields/queries and every nonempty DELETE body. Missing precondition is `428 precondition_required`; malformed ETag is `422`; stale revision is `412 revision_mismatch`. Wildcards and other-resource tags are not accepted. |
| R03 | New intent requires an unresolved operational warning on `failed` or `publication_failed` work and proof that no old writer can commit. Rerun also needs completed setup and no competing lifecycle. Active work, awaiting approval, successful work and unknown stop state are ineligible. |
| R04 | Bind keys to actor, action, target and canonical body fingerprint. After authorization and valid syntax, matching replay precedes obsolete revision/state checks. Conflicting reuse returns safe `409 idempotency_conflict`. Retain receipts throughout v1 history. |
| R05 | Rerun atomically resolves the warning as `rerun` with actor/time, invalidates old execution authority, abandons any old unpublished candidate, creates a linked `trigger_kind=rerun` run, transfers admission, and writes the new refresh outbox intent and receipt. |
| R06 | Warning deletion atomically soft-resolves the warning using the canonical resolution value with actor/time, invalidates old authority, abandons any unpublished candidate, releases only the old run's admission ownership and stores a receipt. Create no run or outbox work. |
| R07 | Preserve attempts, approvals, warning history, immutable artifacts and stored bytes. A failed run stays failed; abandoned publication-failed work closes as failed with a terminal time. Never abandon published versions or revive discarded/superseded candidates. |
| R08 | Recheck eligibility under admission/target locks and fence late workers/deliveries. Lease expiry and missing PIDs are not stop proof. Preserve A24 operator reconciliation; unknown execution remains blocked. |
| R09 | Roll back all effects and receipt together on failure. No EIA/S3/Redis calls belong inside the command transaction. Dispatch through the existing durable outbox. Bound lock waits; exhaustion returns safe retryable `503`. |
| R10 | Apply common eligibility rules to enforcement and Admin projections in `/me`, run list/detail and shared context. Return accurate `rerun`/`delete_warning` enabled flags and reasons. Change run ETag when public state/actions change. Buttons never grant permission. |
| R11 | Preserve active publication and schedule. A future scheduled check may admit work after resolution; warning deletion neither triggers work nor catches up missed occurrences. Existing retry/discard rules remain intact. |
| R12 | Use canonical safe errors: `401` authentication, `403` permission, `404` authorized unknown target, `409` conflict/ineligible state and the input/precondition errors above. Do not expose secrets, raw payloads, storage paths or stack traces. |

### Accepted run-policy choice

**P01 accepted October 5, 2026; canonical record: A16 in DECISIONS:** snapshot current committed shared settings and the current approved refresh policy when accepting the new run. Preserve the failed run's original snapshot. This fits a complete new refresh and the existing `accept_run` snapshot pattern. Concurrent settings changes must yield one coherent revision.

Copying the failed run's old settings was rejected because it can repeat obsolete configuration. Exact lock ordering, schedule-settings integration, abandonment disposition mapping and migration constraints belong in design and must follow the canonical contracts.

### Acceptance scenarios

| ID | Given / When / Then |
|---|---|
| S01 | Given non-Admin or invalid sessions, deny either command and replay before protected lookup; write nothing. Include role-change/logout races. |
| S02 | Given malformed IDs/keys/tags, absent preconditions, unknown fields/queries, nonempty DELETE body or unknown target, return safe canonical errors without writes. Include wildcard and wrong-resource tags. |
| S03 | Given safely stopped failed work with unresolved warning, rerun creates exactly one linked run/outbox/receipt and transfers the slot. Cover failures with and without a candidate. |
| S04 | Given the same safe failure, warning deletion preserves resolution history, releases only its slot and creates no run/outbox. Schedule and publication stay unchanged. |
| S05 | Given safely stopped publication failure, either operation closes the old run as failed and prevents old candidate publication. New intent rejects active, published, discarded/superseded, resolved and unknown-writer states. |
| S06 | Given a lost successful response, identical same-key replay with an old ETag returns the original operation/target and `200` without new effects. Conflicting actor/action/target/body reuse fails safely. |
| S07 | Given injected failures at every mutation through receipt insertion, the entire warning/candidate/fence/admission/run/outbox/receipt transaction rolls back. |
| S08 | Given concurrent rerun/delete/discard/publication retry/publication commit, only a valid transition wins. Late queue deliveries and worker commits cannot revive abandoned work. |
| S09 | Given concurrent manual start or due scheduler admission, preserve one owner and never clear the winner's slot. Settings races use one coherent snapshot under accepted P01. |
| S10 | Given changed eligibility, `/me`, run list/detail and command enforcement agree; revisions change and stale submissions fail safely. |
| S11 | Given accepted rerun and temporary queue outage, retain and later dispatch its durable intent without duplicate run effects. Warning deletion emits no dispatch. |
| S12 | Given lock exhaustion or database failure, return safe dependency errors without partial effects. Replaying an accepted receipt remains an acceptance record after the new run progresses. |

### Verification and handoff

Run focused offline checks, then disposable PostgreSQL transaction/race tests and loopback HTTP/outbox acceptance. Use real stopped-writer and stale-delivery checks; mocks alone cannot prove those guarantees. Regress existing start, publication retry/discard, auth and Admin projections. Retained-Admin acceptance is a separate operator gate with separately authorized setup.

Current source evidence: `refresh.router` exposes start/list/detail; `refresh.service.admin_context` disables both new actions; `refresh.repository.accept_run` hard-codes manual trigger and receipt semantics. `PublicationCommands.command` and `publication.checks.stopped_failure` supply existing receipt and stop patterns. Design must reconcile their locks and migration constraints. No new dependency is specified.

Done: specification and P01 accepted for design. Pending: design/tasks and their review. Blocker: none for planning.
