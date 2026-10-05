# Failed-run recovery Step 4 — disposable acceptance

Date: 2026-10-05
Branch: `pending-endpoints-frontend`
Objective: deliver Step 3, then measure recovery transactions, competing writers,
worker stop evidence, HTTP replay and Redis delivery in disposable services.

## Authorization and delivery

[ME] Requested: “commit and push step 3 and proceed with step 4.”
[YOU] Reviewed and committed Step 3 incrementally: `bff8446`
(`feat(recovery): add atomic rerun and warning resolution`) and `da8be15`
(`docs(recovery): record design and step 3 verification`). Pushed the branch and
verified the remote head as `da8be15b88e9c7baf7bf11e9148a6f2b9969262a`.
The subsequent delivery authorization and commit are recorded below. No merge or retained deployment occurred.

## Changes and boundaries

[YOU] Added 22 runtime cases in `backend/tests/test_refresh_recovery_runtime.py`.
Shared the existing stopped-state fixture without inheriting its test methods and
registered the runtime module with `run_local_sql_checks.py --refresh`.
Updated one prior Publication test that still expected both newly implemented recovery actions to be disabled. It continues to require publication retry to be disabled for invalid evidence. Production code, migrations and dependencies did not change in Step 4.
A16/P01 and A19/A20 remain authoritative; synthetic failures are not EIA findings.

Measured behavior:

- Real PostgreSQL rolls back each recovery write and a deferred commit failure.
  A competing admission row lock also forces a real API timeout: safe `503`,
  `Retry-After: 1`, and no changes across recovery-owned tables.
  Old snapshots/history remain; rerun commits one new run, outbox and receipt.
- Rerun/delete, manual admission, same-key replay, candidate retry/discard,
  logout and role-change races preserve one accepted lifecycle outcome.
  Concurrent calls use separate transactions on separate pooled connections.
- A real preparation child that ignores SIGTERM is killed and joined before
  recovery. An obsolete heartbeat and duplicate delivery cannot revive it.
  Exhausted dispatch and unsupported policy are recoverable before child launch.
- A separate publisher process exits at the real claim boundary. The operator
  proves stopped custody, then recovery rejects its old commit and queue payload.
  The previous publication pointer, event and retained file bytes remain intact.
  Recovery also rejects a still-live publisher paused before its actual commit.
- Real loopback HTTP loses the accepted response after headers. The same request
  replays the committed receipt without a second run; old ETag/actions change.
  Revoked sessions and changed roles cannot replay a prior accepted intent.
- A real refused Redis connection leaves accepted rerun intent pending in SQL.
  Restored delivery through BullMQ/Redis claims that run once. Deleting a warning
  creates no dispatchable job. EIA records and object storage remain synthetic.

## Commands and results

Run from `backend/` with `PYTHONPATH=src`. This worktree has no local virtualenv;
the interpreter is the existing sibling `../trinity/backend/.venv/bin/python`
(relative to this worktree root), Python 3.14.8. Exact shell interpreter path used
is the sibling virtualenv resolved from that location. PostgreSQL is 17.11
(Homebrew), with disposable socket-only clusters. Redis is the already-present
`redis:8.10.2` image, with a unique temporary container and kernel-assigned port.
No image build or pull was needed.

Reproduce the focused check from this worktree root:

```sh
cd backend
PYTHONPATH=src ../../trinity/backend/.venv/bin/python tests/run_local_refresh_checks.py --pattern 'test_refresh_recovery*.py' --failfast
```

| Invocation with that interpreter | Result |
| --- | --- |
| `tests/run_local_sql_checks.py --pattern test_refresh_recovery_postgres.py --failfast` | 6 passed, 0 skipped, 0 failures/errors; 7.774 s |
| `tests/run_local_refresh_checks.py --pattern 'test_refresh_recovery*.py' --failfast` | 75 passed, 0 skipped, 0 failures/errors; 51.413 s (final run, including real lock timeout) |
| `tests/run_local_sql_checks.py --pattern test_auth_postgres.py --failfast` | 25 passed, 0 skipped, 0 failures/errors; 29.716 s |
| `tests/run_local_sql_checks.py --pattern test_publication_postgres.py --failfast` | 18 passed, 0 skipped, 0 failures/errors; 50.298 s |
| `tests/run_local_refresh_checks.py --failfast` | 121 discovered: 120 passed, 1 skipped, 0 failures/errors; 262.637 s |

The focused suite includes 29 parsing/eligibility cases, 18 offline service/projection cases,
6 real SQL cases and 22 runtime cases in the final focused run. Suites overlap; do not sum their counts as
unique tests. The pre-existing Starlette/httpx deprecation warning appeared;
no dependency was changed to suppress it.

Test-authoring corrections: the first focused launch found an invalid fixture
`super()` call, corrected with independent fixture setup. The next reached the
HTTP check and exposed an incorrect test path `/api/v1/auth/me`; corrected to
canonical `/api/v1/me`. The final focused run above passed. Neither issue needed
a production change. The first broader run stopped after 105 tests (104 passed,
1 failed, no skips; 171.030 s): the old integrity-failure test expected both new
recovery actions disabled. The accepted specification enables those actions for
a safely stopped failure. That test now requires them enabled while retaining
its rejection of same-candidate publication retry. All 18 Publication database
cases passed after this correction. One edit command used a wrong working-directory-relative
path and did not change a file; the corrected command targeted this worktree.

## Review and cleanup

[YOU] Reviewed the final test/document diff; `git diff --check` passed.
The recovery records and session index had 114 checked relative links and no
missing targets. Runners completed their own PostgreSQL/Redis cleanup. Final
Docker inspection showed only the retained `trinity-api-1` and
`trinity-postgres-1`, both healthy, matching the pre-test services.

The broader run skipped
`PublicationRuntimeTests.test_published_readers_roles_inflight_pinning_and_cursor_switch`:
its query-container image setting was not provided. That older published-reader
integration check is not claimed as passed. No image build was performed.
All 22 new runtime cases and all 6 recovery PostgreSQL cases ran without skips.

## Remaining integration boundary

The full settings mutation and scheduler clock-loop race cannot run on this
branch. Inspected `backend/src/trinity/settings/` and
`backend/src/trinity/workers/`; searched backend source for `scheduler` and
settings mutation routes. `settings/router.py` exposes only `GET /settings`,
and workers contain refresh, recovery, publication and outbox entry points,
with no scheduler implementation. The expected settings mutation/scheduler
artifacts are absent from this checkout. No other worktree was copied or merged.

The runtime tests exercise the shared scheduled `_insert_run` admission primitive
under `lock_control`, and a real settings-row update against the rerun's shared
lock. These prove that database boundary only. They do not prove the missing
scheduler's timing, mutation endpoint, lock order or integration. Keep that
portion of Step 4 open until the settings/scheduler work is integrated.
Step 5 retained operator acceptance also remains open; no genuine retained run
was fabricated, abandoned or rerun. No live EIA/S3 access occurred.

Next action: integrate the approved settings/scheduler slice, then run its actual
mutation/admission paths concurrently with recovery in disposable acceptance.

## Slice delivery

[ME] Requested: “okay wrap it up and deliver this slice.”
[YOU] Reviewed the final diff and the existing successful run logs. No executable
code changed after those runs; tests were not repeated for Git/document delivery.
Committed the runtime acceptance work as `2812ab9`
(`test(recovery): verify concurrent recovery and durable delivery`) and pushed
`pending-endpoints-frontend`. `git ls-remote` matched local commit
`2812ab96a50104a663cfd943c25bf074dec7bf97` after the push.
The following documentation commit carries this handoff and updated task status;
its final remote verification is reported in the delivery response.

The implementation and available automated acceptance are delivered. The actual
settings mutation/scheduler integration, skipped query-image check, retained
operator acceptance and unobserved human explanation remain explicit open items.
No merge, build, retained recovery command or live EIA/S3 operation was performed.
