# Refresh Task 5 — receipt routing, recovery and candidate detail

Date: October 4, 2026. Branch: `feat/refresh-publication`.

## Objective and authorization

[ME] Alayala requested completion of Task 5 after the existing Refresh delivery,
with final changes left uncommitted and unpushed. The earlier authorized delivery
created five incremental commits through `4ce9a8f` and pushed that branch before
this Task 5 work began. This record does not authorize the publisher, live EIA/S3,
data activation, retained migrations, or future commits/pushes.

[YOU] inspected the latest code, existing work and canonical A9/A16/A22/A23/API
contracts, connected the worker/recovery handoff, implemented candidate detail,
and added process/database/HTTP/Redis acceptance. Existing concurrent Publication
proposal work in `NOTES.md` and its separate session was preserved. No new data
finding is inferred from synthetic evidence. Maintain data evidence — ongoing.

## Implemented flow

1. Successful `RefreshWorker.execute` passes the original receipt hash, reserved
   version, actual validation step and current fence to `CandidateRegistration`.
   Local and remote verification occur outside SQL. The final transaction saves
   artifacts/checks, freezes review evidence, and either queues one publication
   obligation or enters `awaiting_approval`. It never changes active publication.
2. `RecoveryService.once` first acquires the existing same-host lock exclusively,
   proving the supervisor and child released it. It rechecks expired ownership
   under SQL locks and takes a new owner/fence, including the same validation step.
   It imports the retained parent receipt without extraction or new validation.
   Unknown or still-held ownership keeps admission blocked.
3. Migration `0007_refresh_registration` preserves a fixed registration deadline
   and nondecreasing attempt counter. Verification gets at most thirty seconds
   within the original execution deadline and at most three invocations across
   crashes. Expired/failed verification records a failed run and operational
   warning. Corrupt/duplicate partial journals retain their files but cannot
   produce fabricated check rows or strand a stopped run through insert errors.
4. `GET /api/v1/candidates/{version_id}` checks the current Admin role, then reads
   one database snapshot. It exposes actual required checks and completed
   diagnostics, nullable review evidence, publication generation/attempt/outcome,
   failure warning, disposition, actions and `ETag: "candidate-<revision>"`.
   Private paths, raw details and storage settings stay private. Candidate
   revisions change when visible validation progress changes.

Failure example: a worker dies after saving its receipt. Recovery proves process
termination, then finds remote manifest bytes changed. The candidate becomes
rejected, the run becomes failed, the warning explains the failure and admission
remains blocked. No extraction repeats and the old active publication stays intact.

## Verification

Run from `backend/` with `PYTHONPATH=src` and the selected locked Python environment.
This checkout reused the existing sibling `.venv/bin/python`: CPython 3.14.8, pinned
BullMQ 3.3.0 and existing SDK packages. No dependency or lockfile changed. The prior
24-case isolated dispatch commit check belongs to delivery, not these final counts.

| Check | Final measured result |
|---|---|
| `python -m unittest discover -s tests -p test_refresh_evidence.py -q` | 5 passed in 0.954 seconds after deadline correction. |
| Focused candidate PostgreSQL scenarios | 18 passed, 1 Redis-only skip in 56.070 seconds; later tests are included in the final service run below. |
| Candidate revision progress regression | 1 passed in 3.992 seconds. |
| `python tests/run_local_refresh_checks.py --failfast` | 63 passed, no skips; 126.652 seconds. |
| `python -m unittest discover -s tests -q` | 511 collected: 372 passed, 139 opt-in skips; 50.665 seconds. |
| `python tests/run_local_sql_checks.py --all --failfast` | 72 collected: 55 passed, 17 query-image-dependent skips; 100.975 seconds. |

The broader SQL/auth/catalog/Preview regression loaded code before the final
candidate revision adjustment. That worker event change is covered by the focused
revision test and final complete Refresh rerun; no SQL/Preview implementation changed.

The new end-to-end scenarios preserve a nonempty older active publication in every
case. They cover automatic/warning routing, actual process death before/during/after
registration, duplicate delivery and retained Redis jobs, stale ownership before
and during verification, changed local/remote bytes, missing parent/remote evidence,
deadline expiry before/during verification, finite invocation budgets, real deferred
commit rejection, current-role denial, missing/partial checks and revision headers.
The remote-read test observes that no application transaction is open during SDK
reads. Existing dispatch/worker acceptance still covers queue loss, process locking,
termination escalation, immutable windows and bounded extraction/storage failures.

Intermediate failures were corrected, not counted as passes: the new fixture first
called another test class's `super()` method; a later deadline variable collided
with the coverage end date. Diff review also added candidate revision changes for
visible validation progress and rejection of duplicate partial journal rows. The
new Redis case initially used the wrong fixture environment name and skipped; the
corrected case uses `TRINITY_TEST_REDIS_PORT`. A one-off stdin-based invocation
could not spawn authentication children, so the standard file-based disposable
runner supplies the final service evidence. These intermediate runs are not final
acceptance counts.

Static parsing passed for 15 changed/new Python files. Whitespace checks and 397
local Markdown targets passed. This does not validate external URLs or heading
anchors. Existing Starlette/HTTPX deprecation and sanitized pool messages remain.

## Limits and handoff

All service runs use their own disposable PostgreSQL 17.11 Unix-socket cluster.
The Redis runner starts and removes its own Redis 8.10.2 loopback container. Real
preparation children use synthetic HTTP/storage; no live EIA/S3 call occurred.
Unknown remote ownership still requires external resolution; unavailable SQL retains
custody until the database can record recovery. Verification uses the existing SDK
socket bounds and cooperative deadline checks; it is not a new hard-killed remote
verification process. Commit guards reject readiness after budget exhaustion.

Publisher execution, approval/discard/retry commands, shared setup writes, scheduling,
retained database deployment, real S3 policies and full-history capacity remain
separate. No publisher or activation was implemented. The prior Preview compatibility
fixture uses an explicit test-only publication effect; it is not publisher proof.

Done: Task 5 implementation, 63 service checks, offline/regression checks and diff/link review.
Pending: separate publisher/deployment work and human code walkthrough.
Blocker: none within the authorized Task 5 boundary.

For the bounded walkthrough, trace `register_receipt` → `CandidateRegistration.register`
→ `persist_candidate`. The process lock proves stop; the SQL fence proves current
write authority; the saved receipt proves identity. Alayala's explanation has not
yet been observed. Next: [ME] review the Task 5 diff; do not activate publication.

## Subsequent delivery authorization

[ME] Alayala subsequently requested “commit and push please.” [YOU] isolated the
verified Task 5 implementation, tests and supporting documentation into one focused
commit on `feat/refresh-publication`. Concurrent Publication proposal/specification/
design files and their shared-document changes are excluded and preserved locally.
This delivery changes no runtime behavior beyond the implementation already tested
above; only authorization/status wording changed after those checks. No new live
work or retained migration is authorized.

Delivery checks: the staged tree passed whitespace review, parsing of 15 Python
files and 395 local Markdown targets, with no missing links. Runtime suites were
not repeated for this delivery because executable code was unchanged after the
measured Task 5 checks.
