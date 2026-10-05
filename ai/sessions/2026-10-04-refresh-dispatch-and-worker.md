# Refresh admission closure, durable dispatch and fenced preparation

Date: October 4, 2026. Branch: `feat/refresh-publication`.
Mode: authorized implementation of tasks 3–4, with task 2 status verification.

## Objective and contributions

[ME] Alayala requested checking where task 2 stopped and finishing durable dispatch
and the fenced preparation worker. Real disposable PostgreSQL/Redis and synthetic
source/storage with real child processes were required. No live EIA/S3, retained
migration, commit, push or PR was requested.

[YOU] Inspected the dirty worktree, current contracts and prior evidence handoff.
Task 2's HTTP, service, cursor and tracking code existed, but its acceptance evidence
did not: `backend/tests/` was inspected with `rg --files`; the runner named
`test_refresh_admission.py`, while that file was absent. Added that test module.
Preserved the pre-existing staged specification and uncommitted evidence writer.
No change was made to historical data findings or the user-selected anomalies.

## Implementation and flow

Admin request → transactionally retained run/slot/outbox/receipt → dispatcher lease
and attempt → BullMQ notification → one PostgreSQL execution claim → newest-national
discovery → fixed window/version → supervised preparation → retained receipt or
failed/partial evidence. Redis payloads carry identifiers only. Source and storage
configuration stay in the trusted worker.

`RefreshQueue` reuses installed/pinned BullMQ 3.3.0. No dependency/lockfile change.
Installed transitive versions match the selected metadata: `redis 7.4.1`, `msgpack 1.2.3`,
`semver 3.1.0`, and `croniter 2.0.7` on Python 3.14.8. Real Redis 8.10.2 runs in a uniquely allocated disposable loopback container; native
PostgreSQL 17.11 uses the existing isolated Unix-socket runner. The downloaded Redis
image digest is `sha256:6f81e8915c60b065a524e6967e0ad1c639ba6efa84d669f823683ea04d9150ee`.
The runner removes its own container and SQL cluster. Existing services are untouched.

`DispatchService` commits attempts before enqueue and checks lease token/generation
on acknowledgment. Three total dispatch attempts survive restarts and generation
repairs. Enqueue calls have a ten-second limit; pending retries wait one/three seconds;
crashed dispatcher leases expire after sixty seconds. A repaired generation bypasses
an old retained job. A claimed run cannot be failed as an unclaimed dispatch or
started again. Publication obligations are excluded.

`ExecutionService` persists a 1,530-second execution deadline once, sixty-second
discovery and the existing preparation stage budgets (300/120/120/300 seconds,
1,440-second whole preparation). Worker leases last thirty seconds with five-second
heartbeats. SQL triggers prevent changes to frozen bounds, started policy, execution
deadline and existing stage deadlines. These are bounded synthetic-tested defaults,
not measured full-history capacity. Registration remains a separate thirty-second
gate in task 5.

Supervisor/child lifetime locks prove local process termination without trusting a
reused PID. A lost lease stops the real child; terminate escalates to kill and join.
Unknown hosts, missing/replaced lock files and still-held locks retain admission.
No recovery path starts a second pipeline. External attempts are journaled and
counted in PostgreSQL before acknowledgment; validation start binds its generated
UUID to the durable step before checks begin. Completed journal lines and exact
saved details survive failure; partial import never supplies absent checks or readiness.

## Boundary and remaining work

Successful task 4 preparation retains the original receipt hash, confirmed child
exit and parent completion. The version remains unvalidated for application use,
and the run retains admission. Task 5 must connect this custody to the existing
candidate registration service and completed-receipt recovery. Recovery currently
returns `receipt_pending`; it does not restart extraction or treat a file as approval.
Setup writes, publisher, review/recovery HTTP commands, scheduling, deployment and
live full-history capacity remain separate. Maintain data evidence — ongoing.

## Verification

Commands run from `backend/` with `PYTHONPATH=src`, using the existing sibling
checkout's resolved Python 3.14 environment. No dependency installation, new lock
resolution or application build occurred. The repository-form `uv run --locked`
commands are documented in the backend README.

| Command | Measured result |
|---|---|
| `python tests/run_local_refresh_checks.py --failfast` | 40 passed, no skips, 65.879 seconds; real disposable Redis/PostgreSQL, real crash/child-process cases. |
| `python -m unittest discover -s tests -q` | 488 collected, 371 passed, 117 opt-in checks skipped; 48.527 seconds. |
| `python tests/run_local_sql_checks.py --all --failfast` | 72 collected, 55 passed, 17 query-image-dependent checks skipped; 97.144 seconds. |

The broader SQL/auth/catalog/Preview database regression ran before the final
worker-only failure/policy guards; the 40-case refresh suite ran after them.
A separate real loopback HTTP check passed: one test in 3.422 seconds. Uvicorn
served the production app over a real socket. A deferred database commit failure
returned 503 with no run, then the same key accepted once (202), replayed (200)
and exposed working tracking. This supplements the in-process HTTP adapter suite.
Run it with the focused command below, replacing `*object_limit*` with
`*loopback_http*`. Production code did not change after the full regression runs.

The final S20 assertion refinement passed separately: one test in 5.252 seconds.
It confirms more than 700 national rows were processed, all 39 validation results
were retained, and failure occurred at storage. This distinguishes an object-limit
failure from an earlier malformed-fixture failure. The production guard stays at
64 MiB; the full-calendar test uses a trusted 1 KiB limit.

Reproduce that focused check from `backend/`:

```bash
PYTHONPATH=src:tests python -c 'import sys, unittest; import run_local_sql_checks; unittest.defaultTestLoader.testNamePatterns=["*object_limit*"]; sys.argv=["run_local_sql_checks.py","--refresh","--failfast"]; raise SystemExit(run_local_sql_checks.main())'
```

Acceptance uses the production HTTP adapter with real database transactions,
independent processes for admission races and dispatcher crashes, actual BullMQ
producer/consumer APIs and retained Redis jobs, and spawned preparation children.
Synthetic full-history rows exercise the object ceiling using a smaller trusted
test limit; production's 64 MiB limit is unchanged. Actual full-history EIA/S3
throughput is not established. Source/storage mocks never replace the database,
queue, supervisor or validation pipeline in these worker checks.

The earlier new fixtures had incorrect assumptions about malformed-JSON status,
the active-publication column name and cursor key encoding; those were corrected.
An intermediate run overlapped edits to child-process hooks and was superseded by
stable-source reruns. Final review added safe failed-state handling for corrupted
partial journals and unavailable lock-file storage, candidate disposition/policy
guards and database bounds protection. No failed check is counted as passed.

Static parsing passed for 37 changed/new Python files. Changed/new-file whitespace
and 425 local Markdown link targets passed. Link checking
does not validate external URLs or heading anchors. The worker CLI `--help` smoke
check passed without loading EIA credentials or starting workers. Existing
Starlette/HTTPX deprecation and safe pool-connection messages remain.

Done: task 2 acceptance closure and task 3–4 implementation with disposable evidence.
Pending: task 5 successful-receipt routing and completed-receipt recovery.
Blocker: none for this bounded implementation; live enablement remains gated.

## Sources checked

[Official BullMQ job IDs](https://docs.bullmq.io/guide/jobs/job-ids) forbid colons and
explain retained-job deduplication. [Python introduction](https://docs.bullmq.io/python/introduction)
and installed 3.3.0 source supplied the Queue/Worker API. [Redis compatibility](https://docs.bullmq.io/guide/redis-tm-compatibility/)
states the supported Redis baseline; the actual combination was tested separately.
[EIA technical documentation](https://www.eia.gov/opendata/documentation.php) documents
descending period sorting and bounded `length`. Synthetic discovery verifies those
parameters and rejects malformed/empty data. No live endpoint response is claimed.

For a short code walkthrough, follow `DispatchService.recover` into
`ExecutionService.claim`: a new dispatch generation repairs notification delivery;
only a still-requested, never-started run can claim execution. Alayala's explanation
of that distinction has not yet been observed.

Next: [YOU] complete task 5 candidate routing and safe completed-receipt recovery.

## Incremental delivery authorization

Alayala subsequently requested a commit for each task slice and a branch push.
The existing work is split into persistence, registration foundation, admission,
dispatch, and supervised preparation commits. An isolated export of the dispatch
commit passed all 24 cumulative disposable-service tests in 29.651 seconds.
The later Task 5 integration request explicitly excludes commits and push for
that new work; it starts after this delivery. No history rewrite is authorized.
