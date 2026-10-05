# Specification: Build Refresh

Date: October 4, 2026. Status: **implementation authorized; persistence boundary implemented**.
Related: [proposal](proposal.md), [design](design.md), [tasks](tasks.md),
[integration identity/mapping contract](integration-contract.md).

## Human

One accepted request creates one run even when an Admin repeats the request or a
queue delivers twice. Refresh completion is not publication success. A candidate
becomes eligible only when its complete files, checks and diagnostics agree.
Missing or failed evidence remains visible as failure, never an empty success.

## LLM — requirements

| ID | Required behavior |
|---|---|
| R01 | Reuse local session resolution and `refresh:start`. Missing/invalid session returns canonical 401; Viewer/Analyst receives 403 before protected state access; authentication storage failure fails closed. Resolve current actor in the command transaction. No actor/role from the body. |
| R02 | `POST /api/v1/refresh-runs` accepts only `{}` with UUID `Idempotency-Key`; no dates, paths, policy or queue options. Enforce existing transport/body limits and canonical errors. Fresh acceptance returns 202 `ActionReceipt`, `Location=status_url` and initial polling guidance only after commit; exact replay returns 200 with `replayed=true`. |
| R03 | Require shared setup complete and no lifecycle holder/unresolved failure. Current-authority matching command replay precedes new-admission checks, so a request does not conflict with its own run. Same global key with different actor/action/target/body returns safe `409 idempotency_conflict`. Unique constraints arbitrate races. |
| R04 | In one bounded service-owned PostgreSQL transaction reserve control, create run/policy snapshot and refresh outbox, and persist command receipt. Rollback preserves the entire prior state. Never call EIA/S3/Redis while holding this transaction. |
| R05 | Freeze A9 start `2024-10-02`, contract/checkset/registry and newest-national end strategy at admission. Discover newest valid national observation once in the worker, durably store end/window-freeze time, and reuse on recovery. No candidate before window freeze. Empty/invalid discovery fails explicitly. |
| R06 | Outbox dispatch leases only eligible committed work, enqueues stable IDs and generation, and acknowledges only its current lease token. Queue duplicates, dispatcher crash and Redis loss cannot lose durable intent or create duplicate state effects. Delivered is not completed. |
| R07 | Worker claims the correct job kind/run/fence under the common locks. Verify slot, status, generation and disposition before files or stage writes. Only one authorized execution uses a candidate root. Expired leases alone cannot prove a child stopped. |
| R08 | Run existing preparation under a supervisor with explicit finite stage/overall limits and process termination confirmation. Retain current exact parsing, manifest format, required checks and warnings. Use trusted EIA/S3 configuration only in the worker; no secrets in jobs, API receipts, logs or evidence. |
| R09 | Persist append-only step attempts and safe progress with monotonic per-run step sequence. Distinguish extraction routes, freeze, validation and storage. Do not use source advertised facility total as a denominator. Revision changes on public progress/state updates; preserve unknown totals as null. |
| R10 | Implement the integration contract's run/version/connector-attempt/step mapping and all receipt, bundle, file, result, window and diagnostic checks. Store 16 required and 23 diagnostic results for a complete attempt, exact detail identities, and explicit format conversion. No mixed attempt or forged receipt grants readiness. |
| R11 | Register a passing stored candidate atomically with its readiness/route. Complete zero-warning evidence → `publishing` and one publish outbox. Complete warning-bearing evidence → `awaiting_approval` without an approval or publish intent. Retain slot in both. This worker never inserts a publication event or switches the pointer. |
| R12 | Persist available failed/partial evidence before recording bounded failure. Failed required validation/incomplete diagnostics cannot be retried into apparent success or silently discarded. Candidate stays unpublished; permanent/exhausted failure creates one unresolved operational warning and retains slot. No candidate is required when failure occurred before window freeze. |
| R13 | Recovery reconciles durable requested/running work after restart, repairs queue loss, and imports a completed retained receipt when safe. Preserve external retry counters across redelivery. Never rerun the fresh-only CLI into an existing version, revive terminal/review states, or adopt an untrusted prefix. Unknown execution state holds the slot. |
| R14 | Implement canonical Admin `GET /refresh-runs`, `GET /refresh-runs/{run_id}`, `GET /candidates/{version_id}` with actual persisted evidence, revisions/ETags, bounded history/step cursors and 2-second polling only in active states. Preserve `/me` action semantics. Do not expose evidence paths/raw payloads or create missing results. |
| R15 | Preserve the previous active publication for every Refresh outcome. A first failure keeps analytical readiness false. Retain exact source values and evidence; no repair, deletion or publication shortcut. Unsupported contract/checkset is a failure, not an automatic upgrade. |
| R16 | Verify clean/upgrade migrations, HTTP permissions and rollback, concurrent admission, real PostgreSQL/outbox state, queue restart and supervised worker recovery. Offline mocks alone do not establish Redis compatibility, process fencing or live EIA/S3/full-history success. |

## Acceptance scenarios

The first persistence/registration checks are recorded in [tasks](tasks.md).
Unmapped scenarios remain **pending**, not measured results. IC identifiers refer to the
broader integration contract; publication-execution cases stay in the later slice.

| ID | Given / action | Expected evidence | Requirements |
|---|---|---|---|
| S01 | Missing/expired/revoked session, Viewer, Analyst, then current Admin requests refresh. | Unauthorized cases make no protected read/write or external call; eligible Admin reaches admission. | R01 |
| S02 | Setup incomplete; malformed key/body; supplied actor/window/path. | Safe canonical rejection; no run/control/outbox/receipt effect. | R02–R04 |
| S03 | Accept valid request, then replay its key after state advances. | One run and outbox; original operation/time/tracking reference; 202 first, 200 replay. | R02–R04 |
| S04 | Reuse key with different actor/intent; submit two distinct keys concurrently in separate processes. | Safe conflict; at most one lifecycle admitted, no receipt for rejected transaction. | R03–R04 |
| S05 | Existing running/review/publishing/unresolved-failure holder. | New request rejected; no overlap; history unchanged. | R03 |
| S06 | Inject failure at each admission write and at commit. | No partial reservation, run, command or outbox; no 202 before successful commit. | R04 |
| S07 | Redis unavailable at API acceptance; restart dispatcher before/after enqueue acknowledgment. | Accepted run retained; bounded dispatch; duplicate-safe delivery and durable recovery. | R06, R13 |
| S08 | Lose a delivered Redis job while run remains requested. | Recovery advances dispatch generation and dispatches unfinished work; old generation cannot claim. | R06–R07, R13 |
| S09 | Discover date, crash, then EIA newest date advances. | Durable frozen end reused; candidate window unchanged. Empty/malformed discovery fails. | R05 |
| S10 | Observe route/freeze/validation/storage progress with unknown source totals. | Ordered durable steps; increasing revisions; null unknown denominator; storage recorded as prepare, not publish. | R09, R14 |
| S11 | Complete zero-warning and warning-bearing synthetic bundles. | Exact evidence persisted; publish outbox versus awaiting approval; pointer unchanged. IC01–IC03. | R10–R11, R15 |
| S12 | Required failure, interrupted validation, mixed attempt/manifest, altered bytes, unknown diagnostics. | Actual partial/failed rows retained; no eligibility; unresolved warning/slot; IC04–IC08. | R10, R12 |
| S13 | Rollback candidate registration after results; replay same receipt; change receipt. | No partial readiness/routing; exact replay duplicate-safe; changed binding rejected. IC09–IC10. | R10–R11 |
| S14 | Kill worker after final receipt before import; recover with receipt, then without trusted receipt. | Verify/import only with pinned identity and confirmed stopped execution; missing proof fails closed. IC11, IC24. | R07, R13 |
| S15 | Lease expires while child is blocked; stale worker submits step/results. | Terminate/kill confirmed before replacement; stale fence rejected; unknown execution retains blocker. | R07–R08, R13 |
| S16 | Repeated temporary dependency error, permission denial, deadline expiration and process crash. | Bounded attempts; durable accounting; no multiplicative redelivery retries; retained safe failure. | R08, R12–R13 |
| S17 | Page history/steps while new runs/attempts appear; request as non-Admin. | Stable bounded pagination plus fresh current status; no detail leak; measured checks only. | R14 |
| S18 | Upgrade empty and existing 0004_preview_evidence database, attempt invalid ownership writes. | Constraints hold, existing history preserved; missing proof never fabricated; IC21–IC22. | R10, R16 |
| S19 | First run fails; later candidate passes while an older publication exists. | First remains unavailable; later candidate never moves active pointer in this slice. | R11–R12, R15 |
| S20 | Full-history fixture exceeds provisional budgets or object size limit. | Truthful bounded failure with evidence; no relaxed checks or hidden truncation. Live acceptance remains separate. | R08, R16 |

## Completion boundary

Refresh is verified only through durable handoff, not publication completion. Setup,
approval/recovery commands, scheduling and publisher readiness must be tracked as
separate dependencies. A fixture-seeded setup or synthetic approved candidate cannot
be reported as a complete evaluator flow. Implementation is authorized; complete-slice delivery remains pending.
