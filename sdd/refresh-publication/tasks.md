# Tasks: Build Refresh

Date: October 4, 2026. Status: **tasks 2–4 implemented; task 5 routing/recovery integration pending**.
Related: [proposal](proposal.md), [spec](spec.md), [design](design.md),
[integration contract](integration-contract.md).

Implementation authorized after the Preview compatibility corrections. No live EIA/S3,
retained-database migration or PR was requested. The later delivery request authorizes
incremental commits and push for the existing tasks 1–4 and registration foundation.
The subsequent Task 5 integration must remain uncommitted and unpushed.

## Review checkpoint

Done: persistence, initial verified registration, Admin admission, durable dispatch and fenced preparation.
Pending: task 5 successful-receipt routing, candidate detail and completed-receipt recovery.
Blocker: none for continued authorized coding; setup writes and publisher remain product dependencies.

## Bounded implementation sequence — authorized

| Task | Scope and order | Acceptance / review evidence |
|---|---|---|
| 1. Maintain data evidence — ongoing; prepare persistence | Reconcile approved details into `DECISIONS.md`/`docs/schema.md`. Add reviewed 0005/0006 migrations, including worker deadline/ownership fields. Preserve history; no new EIA finding from synthetic fixtures. | S18; integration IC21/IC22. Empty install, 0004_preview_evidence upgrade, invalid direct writes and unchanged historical rows in disposable PostgreSQL. Review migration diff before use elsewhere. |
| 2. Accept and reserve Admin refresh | Add strict request schema/route, writable command service with current session resolution, setup/admission guards, atomic run/control/outbox/receipt and replay. Add run tracking reads necessary for returned URL. | S01–S06 and S17. Real HTTP/DB rollback at commit; two-process same/different-key races; no EIA/S3/Redis in request transaction. |
| 3. Dispatch durable intent | Add queue adapter and outbox/recovery loop for refresh jobs, leases/generations and bounded attempts. Reuse pinned BullMQ; validate compatibility before adding dependencies. | S07–S08. Real disposable Redis plus PostgreSQL; crash before/after enqueue, retained duplicate job and queue loss; no second run. |
| 4. Connect fenced preparation worker | Add discovery, window freeze, reserved version, persisted budgets/ownership, supervised existing preparation and durable stage/attempt mapping. Import failed/partial evidence without readiness. | S09–S10, S12, S15–S16, S20. Synthetic transport/storage with real child processes; stop/kill confirmation, stale fence, immutable bounds, failure journaling and finite retries. |
| 5. Persist and route candidate | Implement strict receipt loading/verification, candidate/artifact/result persistence and atomic publication intent or review transition. Complete candidate detail projection and safe completed-receipt recovery. | S11–S14, S19; relevant IC01–IC13/IC20/IC23/IC24. Full offline integration + disposable PostgreSQL/Redis. No publisher invocation or pointer change. |

After each task: explain input → processing → output and one failure case; inspect
the focused diff; run smallest relevant repository checks. Support an alayala code
walkthrough without claiming understanding unless he demonstrates it. Do not mark
the task complete when its transaction/process evidence is still missing.

## Verification plan

Use the existing `unittest` layout and locked environment described in
[backend README](../../backend/README.md). At implementation time, add focused
modules for refresh HTTP/admission, outbox, worker supervision and evidence import;
run each module first, then the full documented backend suite once the slice integrates.
Exact focused commands depend on the files actually created; do not claim nonexistent
test modules ran. No formatter/linter/type checker is configured in the inspected
`backend/pyproject.toml`; use any repository tooling added before implementation.

Real database/Redis acceptance must run separately from offline mocks. Keep opt-in
skips visible. Inspect migration head, resource cleanup, retained failed evidence,
secret-safe output and diff scope. Never use production publication metadata or
delete stored candidates to make acceptance pass.

Live/full-history acceptance is a later explicit gate: [ME] runs the EIA-key command
using existing private storage and records the exact exit/evidence. Until then,
report synthetic preparation and database/queue proof separately. No setup writes,
approval/recovery commands or publication completion are established by this SDD.

Next: [YOU] implement task 5 successful-receipt routing and completed-receipt recovery.

## Implemented boundary and verification

Task 1 persistence is implemented by `0005_refresh_evidence` and
`0006_refresh_dispatch`, after `0004_preview_evidence`. Maintain data evidence remains
ongoing. Task 5 has its successful-candidate registration boundary implemented in
`refresh/evidence.py` and `refresh/registration.py`. Tasks 2–4 now add Admin routes,
durable BullMQ dispatch, supervised preparation and failed/partial import. The
successful worker retains custody for task 5; its routing/recovery wiring and the
publisher remain pending. The following initial-writer results are historical.

- Five offline loader tests passed: exact reconstruction, child-only completion,
  retained-hash mismatch, changed detail/remote bytes and contradictory failure.
- Nine disposable PostgreSQL 17.11 tests passed: clean migration chain, upgrade
  from 0004 preserving Preview evidence, ownership/attempt rejection, rollback,
  immutable accepted bindings, automatic/review routing and exact replay.
- Compatibility uses the new writer, a clearly marked synthetic publication effect,
  actual `PreviewService.execute`, and production frozen-diagnostics reading.
  Its injected executor does not run containers or prove the future publisher.
- Full offline discovery: 452 tests collected, 368 passed and 84 opt-in checks skipped.
  Broader PostgreSQL regression results are recorded in the implementation session.

These tests cover parts of S11/S13/S18/S19 and the two reported compatibility defects;
the later worker/HTTP/concurrency results are recorded below. Test commands and limitations:
[implementation session](../../ai/sessions/2026-10-04-refresh-evidence-implementation.md).


### Tasks 2–4 continuation

Task 2 already had uncommitted route/service/tracking code. The missing admission
acceptance module now covers authentication, setup, strict input, current-authority
replay, other-actor conflict, all blocking states, each write/commit rollback,
independent-process races and authenticated history pagination.

Task 3 uses the existing BullMQ pin. Real Redis/PostgreSQL acceptance covers actual
process death before/after enqueue, stale acknowledgment, retained completed IDs,
queue loss and generation repair, three-attempt exhaustion, and a worker claim racing
with dispatch failure. Neither repair nor duplicate delivery creates a second run.

Task 4 persists discovery, one reserved version, execution/stage budgets, ownership,
external-attempt counts, validation UUID mapping and measured progress. Synthetic
transport/storage use the actual child pipeline. Tests cover lease loss, terminate/
kill confirmation, stale fences, frozen bounds, actual post-discovery and validation
crashes, incomplete/corrupt journal import, denied storage and finite temporary retries.
S20 generates the full accepted calendar window and uses a reduced trusted object limit to exercise the same guard;
full-history capacity and live EIA/S3 remain explicitly unverified.

Successful preparation returns `prepared` and keeps the candidate unvalidated with
admission retained. Recovery returns `receipt_pending` for retained custody. Task 5
must verify/import it using the original deadline and identities before granting
readiness. No publication pointer change occurs in tasks 3–4.

Final checks: 40 refresh integration tests passed without skips; a separate real
loopback HTTP commit/acceptance/replay test also passed; 371 offline tests
passed (117 opt-in skips); 55 broader PostgreSQL tests passed (17 query-image skips).
Commands, fixes and boundaries:
[dispatch/worker evidence](../../ai/sessions/2026-10-04-refresh-dispatch-and-worker.md).
