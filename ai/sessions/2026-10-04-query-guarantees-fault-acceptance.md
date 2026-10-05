# Query guarantees: concurrent versions, isolation and uncertain execution

Date: 2026-10-04. Scope: A9/A19, SQL T15-V/T16-V and shared Preview execution.
Checkout: `trinity-main`, branch `main`; initial working tree clean.

## Authority and contributions

[ME] Alayala authorized implementation, local Docker/PostgreSQL verification and
checklist updates for all three query guarantees. The earlier review-only boundary
was explicitly removed. Git delivery was initially excluded. After reviewing the
result, alayala explicitly authorized commits, push and merge to `main`. Deployment
and non-Git remote-resource changes remain excluded.

[YOU] Reused the shared `QueryExecution`, query admission repository, staging,
Docker adapter, synthetic publication producer and disposable database runner.
Added ten acceptance cases in `backend/tests/test_query_guarantees.py`, a local
reply-loss proxy, one pre-create test barrier and inclusion in the existing
`--preview`, `--runtime-only` and `--all` runner modes. No production dependency,
SQL grammar, security control, lifecycle implementation or runtime image changed.

Before edits, traced input -> pinned publication/reservation -> private verified
staging -> restricted container -> confirmed removal -> conditional release.
The concrete failure under investigation was delayed or uncertain Docker work
outliving its capacity reservation. No premature release was found in the tested
paths. Tests are evidence for named scenarios, not exhaustive proof of all possible
interleavings or Docker/kernel behavior.

## Acceptance cases and execution evidence

All new cases use real PostgreSQL 17.11 and Docker with synthetic immutable
publication bytes. The existing `test_publication_runtime` was also rerun against
the production publication worker, with no fixture-created publication events.
`observe_release` inspects the real container and staging path
immediately before the real `release_removed` database write in in-process cases.
It does not fabricate inspection results or alter release behavior.

| Case | What the test establishes |
|---|---|
| V1/V2 overlap | Hold V1 after staging, publish V2 atomically through the fixture, finish and clean V2, then resume V1. New SQL returns `120.000000`; V1 still returns `60.000000`. V1 staged bytes remain identical after V2 cleanup. |
| SQL plus sandbox isolation | Hostile app-table, external-file, URL, metadata and multi-statement SQL fails over HTTP before downloads or launch. An allowed national SQL request enters a real restricted container; probes repeat policy checks, reject unregistered app/detail tables, deny a real unpublished sibling sentinel, Docker socket, secret path, root-only file, writes and network connections, and verify no inherited credential variables. It then executes the normal runtime request and returns exact results. |
| Late create | Recovery takes ownership while create is held. Absence retains capacity. Creation then completes but the stale owner cannot obtain a start grant; another recovery removes the stopped container before release. |
| Late start after removal | Hold start after durable intent. Recovery removes the container and releases. Resuming start against that immutable ID fails and cannot recreate execution. |
| Start before recovery | Hold the original owner after actual start. Recovery kills/removes the running container; the old owner's later state write fails. |
| Start between inspection and DELETE | Start a sleeper after recovery inspected it stopped but before DELETE. Docker refuses removal of the running container; capacity stays occupied. A later recovery kills/removes it before release. |
| Docker create/start reply loss | A loopback byte proxy forwards real daemon requests, consumes the actual reply and closes the client transport. Cleanup resolves the side effect using the recorded name/ID and removes before release. |
| Docker kill/delete reply loss | Lose real replies after stop/removal. The reservation remains `stopping`; subsequent recovery confirms absence/removal and releases. |
| PostgreSQL COMMIT reply loss | Forward to the disposable cluster's Unix socket; drop the real COMMIT reply after the `running` transition. Independent SQL sees committed `running`, while local cleanup has stale `starting`. No release occurs; recovery reconciles and removes execution first. |
| SIGKILL plus natural expiry | Kill a spawned supervisor immediately after actual Docker start. Start `python -m trinity.queries.recovery` as a separate process with normal configuration. Do not edit deadlines or directly invoke recovery in this case. Observe occupied `starting` until the original deadline, then removal/release and stale-owner rejection. |

The separate-process case checks final removal and release timestamps. Its parent
cannot instrument the child's release call; ordering there follows the same
production cleanup path whose individual release boundary is inspected in the
other cases. It uses the native test staging/copy bridge, not deployed Compose.

Published versions are retained under A9. Static inspection of
`backend/src/trinity/publication` and `backend/src/trinity/queries` found no
published-object deletion; the only recursive query deletion is request-scoped
`StagedQuery.cleanup`. The concurrent-reader test verifies that scope with actual
staged bytes. The new overlap test uses a synthetic atomic switch; the separately passing
production-worker runtime test verifies admitted SQL/Preview requests retain the
old publication after real worker activation and new requests use the new one.
Storage remains synthetic; live S3 policy is a separate gate.

## Reproduction and environment

The existing sibling Python environment was reused with `PYTHONPATH` explicitly
pointing at this checkout's `backend/src` and `backend/tests`. Python 3.14.8 and all
14 pinned direct dependencies matched `backend/pyproject.toml`. Import resolution
was checked against this checkout. This is not a fresh locked-install test.

Used the existing immutable query image
`sha256:ca94ae39c7694172dc6a683fac4a531605259bf04fec8be9b32dba9484d57433`.
A read-only, network-disabled image check compared SHA-256 for all nine runtime
and contract Python files against this checkout: all matched. Docker Engine 29.8.1,
API 1.56 and Docker Desktop's configured user Unix socket were used. No image pull/build or retained service
change was required.

With the repository environment installed, from its root:

```sh
export PYTHONPATH="$PWD/backend/src:$PWD/backend/tests"
# Set TRINITY_TEST_QUERY_IMAGE to the verified immutable local image ID.
# Set TRINITY_TEST_DOCKER_SOCKET to the verified local Unix socket.
backend/.venv/bin/python backend/tests/run_local_sql_checks.py --pattern test_query_guarantees.py --failfast
backend/.venv/bin/python -m unittest discover -s backend/tests -v
backend/.venv/bin/python -m unittest discover -s backend/tests -p test_sql_containers.py -v
backend/.venv/bin/python backend/tests/run_local_sql_checks.py --all --failfast
backend/.venv/bin/python backend/tests/run_local_sql_checks.py --pattern test_publication_runtime.py
```

Run the CPU-heavy offline suite and runtime suite sequentially. The runner creates,
migrates and stops its own temporary PostgreSQL cluster. Fault proxies bind only
loopback and forward only to disposable/local service sockets; they do not log
payloads. Test containers and volumes have unique fixture ownership.

## Results and corrections

- Initial harness failure: copying another unittest class's `setUp` retained its
  lexical `super()` and failed before any scenario. Replaced it with setup on the
  new class, reusing the same underlying fixtures.
- First eight focused cases passed in 61.786 seconds. A subsequent nine-case run,
  adding lost kill/delete replies, passed in 90.713 seconds. The tenth case adds
  the tighter start-between-inspection-and-delete interleaving.
- Offline regression: 551 discovered, 375 passed, 176 opt-in skips in 88.952 seconds.
  Skips are not passes; unrelated Refresh/Publication opt-in suites are not part
  of this query-only change.
- Standalone Docker/frame suite: all seven passed, zero skips, in 18.038 seconds.
- First combined attempt stopped after 14 tests: existing preview login returned
  503 rather than 200. It overlapped CPU-heavy offline work. Resource contention
  is a hypothesis, not an established cause; no limit or assertion was relaxed.
- Serial combined attempt: stopped after 34 tests in 406.142 seconds on another
  setup login returning 503. The first 33 passed. The failure was before the
  supervisor-crash scenario, not an observed query stop/release failure. Running
  suites concurrently is therefore not a sufficient explanation.
- Final ten-case focused acceptance: 10/10 passed, zero skips, in 81.618 seconds.
  Natural-expiry recovery completed 30.305 seconds after supervisor death.
- Authentication/catalog: 36/36 passed, zero skips, in 82.859 seconds separately.
- Remaining existing Preview crash/unknown-state cases: 3/3 passed, zero skips,
  in 10.297 seconds; SIGKILL cleanup after recovery claim measured 0.190 seconds.
- Production publication/reader runtime: 1/1 passed, zero skips, in 42.386 seconds.
- Final diagnostic combined run: **82/82 passed, zero skips, in 362.301 seconds**.
  This includes 11 SQL PostgreSQL, 10 Preview PostgreSQL, 15 Preview runtime,
  10 new query-guarantee, 25 authentication and 11 catalog cases. No authentication
  diagnostic failure occurred. Measured timeout plus cleanup: 30.139 seconds;
  natural-expiry recovery after supervisor death: 29.697 seconds. The earlier
  login failures did not recur, but their cause remains unconfirmed. This run
  does not establish that the intermittent authentication issue was fixed.
- Final static review: all five changed Python files parsed; 226 local Markdown
  link targets resolved; `git diff --check` passed. The project config declares
  no separate formatter, linter or type-checker command. No production files changed.
- Final Docker inspection found zero `trinity.query` containers and zero
  `trinity-preview-test-`, `trinity-sql-test-` or `trinity-sql-recovery-` volumes.
  The final database runner exited 0 after stopping its own temporary cluster.

The final focused and auth/catalog commands ran through a temporary local wrapper
that calls the unchanged password verifier and reports only function line, safe
problem code, elapsed time and child/result booleans if it fails. It changes no
limits, retries, authentication result or query behavior. The wrapper is outside
the repository. No diagnostic authentication failure occurred in those runs.
The test fixture now includes only the safe public problem code in a failed-login
assertion; it never prints a successful session response. The normal reproduction
commands above require no tracing wrapper.

The existing Starlette/httpx deprecation warning remains. Do not add an unpinned
replacement dependency for this verification task.

## Remaining boundaries

No live EIA/S3 access, retained account, deployed Compose service, cloud permission,
public hosting or fresh installation is claimed. SQL T18-V/T20-V and frontend
T20-UI keep their separate scope. Unknown create with no observable container
continues to hold capacity conservatively; this work does not invent evidence
that would authorize releasing it. Infrastructure failure can delay stop proof;
capacity remains occupied during that uncertainty. Published evidence is retained.

Done: all three guarantees passed named local acceptance; T15-V/T16-V and the
shared Preview checklist are reconciled; the full 82-case combined runtime and
separate publication-worker test passed. Code/doc diff and local links checked.
Pending: deployed/live gates and diagnosis if the intermittent setup-login 503
recurs. Earlier failures remain recorded rather than described as repaired.
Blocker: none for the scoped local acceptance; no deployed readiness is claimed.
Next: [YOU] deliver the reviewed work through focused commits and a non-squashed
merge to `main`, as subsequently authorized by alayala.
