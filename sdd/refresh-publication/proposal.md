# Proposal: Build Refresh

Date: October 4, 2026. Status: **implementation started after Preview compatibility corrections**.
Branch: `feat/refresh-publication`; initial baseline: `82a4af7`; reconciled baseline: `aea1eda`.
Related: [integration contract](integration-contract.md), [specification](spec.md),
[design](design.md), [tasks](tasks.md).

## Human

An Admin starts a refresh. PostgreSQL records the request and reserves the one
refresh slot. A background worker prepares the files, retains validation evidence,
and either queues publication or waits for approval. A failed run retains evidence
and blocks another run until the accepted recovery action resolves it.

Input: authenticated Admin, completed shared setup, `{}` and an idempotency key.
Flow: authorize → reserve slot/run/outbox in one transaction → dispatch → prepare
one fixed-window candidate → persist and verify evidence → route by frozen warnings.
Output: a tracking receipt first; a durable refresh outcome later.

Failure example: Redis is unavailable after the API commits. The request still
exists in PostgreSQL. Dispatch retries within its budget and can recover after a
restart; it must never lose the run or create a second logical run.

### Scope

| User step | Deliverable |
|---|---|
| Accept Admin request | Canonical `POST /api/v1/refresh-runs`, current local permissions, setup guard, safe errors and commit-before-202 behavior. |
| Reserve slot | PostgreSQL admission, command replay/conflict handling, no overlap with review or unresolved failure. |
| Save run and intent | Atomic run/control/command/outbox transaction; bounded BullMQ dispatch and restart recovery. |
| Connect preparation | Fenced worker, newest-national end discovery, fixed window, retained progress, supervised existing pipeline and finite failure handling. |
| Persist candidate/evidence | Strict integration-contract import; pass → publish outbox or review; failure → retained results and unresolved warning. |

Supporting reads are necessary to make the tracking receipt usable: implement the
canonical Admin run list/detail and candidate detail endpoints. They expose safe
persisted summaries, not raw file paths or source payloads. No frontend is included.

Outside this slice: publication execution/active-pointer writes, approval/discard/
rerun/warning-resolution commands, settings writes, daily scheduler, analytical
queries and cloud changes. Preserve their accepted contracts and shared service
boundaries. No additional production dependency is proposed.

**Integration prerequisites:** current setup is read-only; a fresh installation
cannot complete setup through the product yet. A separate settings-write slice is
needed for an evaluator-owned end-to-end run. Disposable tests may seed completed
setup but must label it as a fixture. Passing refreshes intentionally remain queued
or awaiting review until the corresponding later consumers/commands exist. Do not
deploy this slice as a complete refresh/publication product or clear slots manually.

Alayala subsequently authorized implementation after correcting the Preview field
mapping and migration chain. Persistence and verified registration are the first
implemented boundary. The remaining tasks retain their acceptance requirements;
no additional approval is required merely to continue the authorized implementation.
Live EIA commands, retained-database changes and Git delivery remain separate.

## LLM

Follow A9/A12/A15/A16/A19/A20/A21 and current `CONTRIBUTING.md`.
The [canonical schema](../../docs/schema.md) owns logical fields/lifecycle;
[API/OpenAPI](../../docs/api-contract.md) owns the wire contract;
[security](../../docs/security-contract.md) owns authority and retries.
The integration contract adds proposed physical bindings without changing formats.
Use current source over older closure claims. No acceptance test result is claimed.

Confirmed baseline: local authentication, read-only settings, lifecycle read tables,
the supervised preparation command and saved-file verifiers exist. Inspection via
`rg --files backend/src/trinity/workers` reports no such directory. Migration inventory
now includes the merged SQL/Preview 0001–0004 chain; Refresh adds 0005/0006.
The initial draft inventory is retained as historical evidence in the integration contract. `auth.service.AuthService.authenticated` starts a read-only transaction:
the future command service must not attempt inserts through that connection.

Maintain data evidence — ongoing. Synthetic acceptance cases are not EIA findings.
