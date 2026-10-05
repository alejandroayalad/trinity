# Build Publication — implementation and acceptance

## Objective and authority

[ME] Alayala authorized all six approved Build Publication tasks without intermediate
approval stops, including code, migrations/tests in disposable local environments.
Live deployment, retained-data changes, commits, pushes and a PR are not authorized.
A24 and PUB-R01–R09/PUB-E01–E10 remain the scope. This record supersedes earlier
planning statements that implementation was not authorized; it preserves their history.

[YOU] inspected HEAD `b018784`, the existing uncommitted Publication planning documents,
Refresh Task 5, migrations through `0007_refresh_registration`, CONTRIBUTING and the
canonical contracts. No existing user changes were discarded. No dependency or
migration was required. Existing schema constraints are exercised on fresh disposable
PostgreSQL clusters and by the existing upgrade-from-Preview regression.

## Implemented flow

1. `refresh.evidence.load_candidate` preserves Refresh's public safe error while
   retaining typed internal storage/evidence causes. Actual adapter tests distinguish
   temporary exhaustion, missing objects, denied access and unknown errors.
   `publication.checks.recorded` reconstructs the same connector checks from frozen
   rows, requires all 16 required passes and 23 complete diagnostics, and compares
   exact registered artifacts/results with the worker's verified report. HTTP reads
   and commands share `publication.checks.actions`; unknown/permanent history denies retry.
2. `PublicationService.claim` commits one unique publish step per generation with
   a fresh run owner/fence and fixed 300-second step deadline/lease. Preparation and
   registration budgets, selected validation step and retained evidence stay unchanged.
   `PublicationWorker` holds the original same-host inode exclusively in the actual
   synchronous thread. Cancellation of its async waiter does not close that lock.
3. `PublicationService.finish` rechecks authority, evidence, approval and ordering
   under control → run → candidate → active-publication locks. It writes the stable
   UUIDv5 event, pointer, successful step/run, revisions and slot release together.
   Existing events return without moving the pointer, including after a newer event.
   Older work is superseded; narrower coverage fails. Unknown commits first look
   for the event; unresolved outcomes retain the blocker for explicit recovery.
4. `/approval`, `/publication-retry` and `/discard` use current Admin authority,
   strict empty bodies, UUID keys and exact candidate ETags. Authorized receipt
   replay precedes stale revision checks. Retry retains the approving actor and
   evidence, resolves the warning and rearms the existing outbox with a new generation.
   Discard preserves files/history and releases admission. Deferred actions stay disabled.
5. `publication-outbox` reuses bounded dispatch acknowledgment and retry accounting;
   `publication` uses a separate one-slot BullMQ queue. No delivered-job repair or
   automatic verifier restart occurs. `publication-recover` runs before dependency
   initialization, needs no EIA/S3/Redis access, checks worker host/root ownership,
   proves stop with the original exclusive lock, and performs one guarded reconciliation.
   Recovery does not authorize retry or release the slot. It emits the specified
   sanitized JSON and exit codes; repeats cannot create another warning/effect.

Failure example: a remote object disappears before an explicit retry. The new worker
checks the original hashes, records a permanent failure and preserves the old active
publication. Restoring the object later does not erase failure history or enable retry.

## Essential acceptance matrix

All PUB-E01–E10 essential gates passed in disposable local environments. The combined
Refresh/Publication run passed 92 tests without skips. After final contract corrections,
the complete Publication suite passed 30 tests without skips, including actual query
containers and stronger in-flight Preview assertions. Task 1's bounded foundation and
Tasks 2–6 are complete at this local boundary; data evidence remains ongoing.

| Gate | Production-path evidence | Current result |
|---|---|---|
| E01 | Real registration, automatic/approved worker, all three readers | Passed |
| E02 | Missing/failed/mixed proof, files, approval, ordering/coverage | Passed |
| E03 | Each final write rollback, deferred COMMIT rejection, duplicate/lost response | Passed |
| E04 | HTTP authority/replay/ETags, independent-process command races | Passed |
| E05 | Real Redis duplicates/loss and bounded dispatch/S3 attempts | Passed |
| E06 | Worker process deaths, original-lock proof, stale writes/live thread | Passed |
| E07 | Integrity failure, truthful actions, discard and new refresh admission | Passed |
| E08 | Real query containers, roles, pinned in-flight request, stale cursor | Passed |
| E09 | Actual CLI subprocesses, locks, targeting/repeats/races, rollback/exit codes | Passed |
| E10 | Temporary failure, distinct retrying Admin, exact reverify, permanent history | Passed |

## Measured commands

Working directory: `backend/`. `python` below denotes the existing CPython 3.14.8
interpreter at `../../trinity/backend/.venv/bin/python`; every invocation set
`PYTHONPATH=src`. No new environment was installed. Container-enabled invocations
also set `TRINITY_TEST_QUERY_IMAGE` to the immutable ID below and
`TRINITY_TEST_DOCKER_SOCKET` to this host's actual Docker Desktop Unix socket.

| Command | Actual result |
|---|---|
| `python tests/run_local_refresh_checks.py --publication --failfast` with query-container settings | 28 passed, no skips, 180.962 s; before the additional legacy-failure guard. |
| `python tests/run_local_sql_checks.py --pattern test_publication_postgres.py --failfast` | 18 passed, no skips, 95.090 s; includes the final deadline and legacy-failure guard tests. |
| `python tests/run_local_refresh_checks.py --failfast` with query-container settings | 92 passed, no skips, 410.989 s; before the final publication work-key/dispatch corrections. |
| `python tests/run_local_refresh_checks.py --publication --failfast` with query-container settings, final contract run | 30 passed, no skips, 215.290 s; includes all final production corrections and in-flight Preview verification. |
| `python -m unittest discover -s tests -q` | 540 collected: 375 passed, 165 opt-in skips, 87.490 s; before the additional dispatch regression and final Publication-only changes. |
| `python tests/run_local_sql_checks.py --all --failfast` | 72 collected: 55 passed, 17 query-image-dependent skips, 135.745 s. |

The 17 skipped existing runtime regressions are separate from Publication's actual
container gate, which ran and passed. Broad regression counts are not added to
focused counts because their cases overlap. Syntax parsing passed for 27 changed/new
Python files; OpenAPI JSON parsed and 528 local document targets resolved. Heading
anchors and external URLs were not validated. `git diff --check` passed. No formatter
or linter command is configured in `backend/pyproject.toml`; none is claimed.


## Corrections during verification

- The first container invocation supplied a tag and the absent default socket.
  The adapter correctly refused it. The rerun uses the actual immutable image ID
  and Docker Desktop Unix socket; production checks were not relaxed.
- Contract review corrected the drafted route `/approve` to canonical `/approval`.
  The command action name remains `approve`, as specified.
- The first offline regression still expected the old API surface. Its route-set
  assertion now includes exactly the three implemented canonical commands.
- A Refresh crash regression compared unordered SQL result lists. Recovery can
  change row storage order. Both reads now use `ORDER BY step_seq`; identity and
  immutable deadline/attempt assertions remain unchanged.
- The session-expiry test initially violated the existing created-before-expiry
  database constraint. The fixture now moves both synthetic timestamps; the
  production constraint is unchanged.
- Review extended dispatch exhaustion lock ownership through COMMIT and moved S3
  initialization after the publication claim. Invalid configuration now records
  a stopped, nonretryable failure rather than appearing as an interrupted worker.
- Final review preserved a known permanent failure when the clock crosses the
  deadline while reporting it. A regression proves it cannot become retryable.
  Operator repeat handling now requires the current finished publish-failure marker;
  empty legacy owner/lease fields alone return `blocked`, not `already_failed`.
- One combined run was invalidated because a long-running process loaded an older
  checks module before the recovery helper changed. Its late import failed; it is
  not counted as acceptance. Code was frozen and a fresh combined run was started.
- Final contract audit set publish-step `work_key=publication` and made dispatch
  prove preparation released the original lock before consuming an enqueue attempt.
  A separate process holds the shared preparation lock across repeated dispatch calls;
  attempts stay zero until release. The final suite passed these corrections.
- The container test now explicitly retains an admitted Preview across publication,
  checks its original rows/diagnostics and old-version storage keys, and requires a
  nonempty old cursor before testing `publication_changed`.
- Existing auth action tests used metadata-only legacy fixtures. They now assert
  that missing registered proof cannot enable approval/retry, and unimplemented
  Run again remains disabled. Real registered action success is covered here.

## Environment and limits

Checks use CPython 3.14.8 from the existing sibling environment with `PYTHONPATH=src`.
All 15 installed direct dependencies matched the declared exact pins. `uv` is absent
from the shell; this is not a fresh `uv sync --locked` result. No dependency pins changed.
PostgreSQL 17.11 runs in private disposable Unix-socket clusters. Redis 8.10.2 uses
uniquely owned disposable containers. Query execution uses the existing immutable
image `sha256:ca94ae39c7694172dc6a683fac4a531605259bf04fec8be9b32dba9484d57433` and the
actual local Docker socket. Synthetic storage supplies real producer Parquet/evidence
bytes through the existing adapter; it is not live S3 custody or policy evidence.

Maintain data evidence — ongoing. Synthetic fixtures add no EIA findings and change
none of AN-01–AN-03 or CAND-02. Live EIA/S3, full-history capacity, storage overwrite/
delete protection, retained-root custody, retained migrations, live activation and
retained-account acceptance remain separately authorized deployment work. Automatic
publication crash recovery, multi-host failover and hard process deadlines remain
explicitly deferred by A24. No full A16 recovery or frontend completion is claimed.

## Checkpoint

Done: Tasks 1–6 local delivery, all E01–E10 gates, relevant regressions and final checks.
Pending: separately authorized deployment prerequisites and retained-account proof.
Blocker: none for this approved local slice; live deployment is not authorized.

For a later human walkthrough, trace `PublicationWorker.execute` → `PublicationService`
→ `publication-recover` → Admin `publication-retry`. The lock proves stop, the fence
proves current authority, and the receipt/hash proves identity. Alayala's explanation
has not been observed. No extra implementation approval is needed to finish this slice.

## Subsequent Git delivery authorization

[ME] Alayala subsequently requested focused commits and push of this implementation,
followed by planning full live-system acceptance. This supersedes the earlier Git
restriction for this delivery only. [YOU] grouped evidence/queue support, publication
and recovery behavior, acceptance tests, and contracts/documentation separately.
No history rewrite, merge, PR or live test is included. The prior measured tests
remain the evidence; they were not rerun merely to package unchanged code.
The [live-system plan](../../docs/live-system-acceptance-plan.md) identifies missing
setup/schedule writes, the fixed historical refresh window and isolated runtime gates.
