# National dashboard — real acceptance and operator handoff

Date: 2026-10-05
Branch: `feat/national-dashboard`
Scope: [Steps 4–5](../../sdd/national-dashboard/tasks.md), following [Steps 2–3](2026-10-05-dashboard-pure-and-service-implementation.md). A9/A15/A16/A19 and D01–D03 remain unchanged.

## Human handoff

The national dashboard and metric have dedicated tests through real DataFusion, PostgreSQL, loopback HTTP and the existing isolated query container. Final verification results are recorded below. This is local acceptance with synthetic stored bytes; it is not live S3 or retained-account proof.

**Retained operator check: not ready.** Read-only inspection found no active publication and zero publication events in the retained database. The installed retained API does not register either national endpoint and has no `enable_preview` parameter in `create_app`. The operator check stopped at these prerequisites. No data was seeded or published and no retained service was rebuilt, restarted or reconfigured.

The remaining work is to prepare the retained environment through separately authorized deployment/publication work, then have alayala perform the Viewer and Analyst checks. The new backend still defaults to `enable_preview=False`; installing the source alone does not enable execution. A valid publication and matched execution/storage configuration are also required.

## Authority and contributions

[ME] Alayala requested: “Continue with step 4 and 5 and give me the handoff please.” Both Step 2 explanations were already observed and recorded. This request authorized disposable acceptance and the Step 5 read-only readiness check. The task explicitly requires stopping the retained check if prerequisites are absent.

[YOU] Read the runner, existing real preview/query acceptance fixtures, CONTRIBUTING, current tasks/design/specification and the previous query-guarantee evidence. Before test edits, explained synthetic inputs → real database admission and container execution → validated national response, with checksum rejection before launch as the failure case. Preserved all existing worktree changes.

[YOU] Added `--dashboard` to `backend/tests/run_local_sql_checks.py` and included national acceptance in `--all`. Added:

- `backend/tests/test_dashboard_engine.py`: real Parquet/DataFusion over a 366-date leap-year range, interior/end gaps, exact decimals and 366 independent metric reads.
- `backend/tests/test_dashboard_postgres.py`: real session failures, input/debit ordering, missing publication, broken evidence, publication/freshness snapshot race and mixed four-service admission across processes.
- `backend/tests/test_dashboard_runtime.py`: real HTTP for all roles and presets, metric equality, pinned reader overlap, failed newer refresh, container restrictions and failure/cleanup checks.

Reused `PostgresFixture`, `candidate`, `publish_fixture`, `loopback`, `RuntimeSandbox`, the shared cleanup assertions and the release-observation helper. No second storage adapter, production query engine, admission layer or cleanup implementation was created. All 94 production Python source files match the SHA-256 baseline captured at the start of Step 4; no production fix was required by this acceptance work.

## Evidence boundaries by scenario

| Scenarios | Current evidence |
|---|---|
| S01, S06–S07, S10–S11, S20 | Real loopback HTTP through real national containers for Viewer, Analyst and Admin; default/custom ranges, absent dates, source percentage nulls, metric equality, closed response models and headers. Step 3 separately checks serialization recursively against canonical OpenAPI. |
| S03–S05, S08–S09 | Pure tests retain the full D01/D02 tables. Real PostgreSQL/HTTP checks prove shape versus semantic debit order. Real HTTP covers all presets, a 366-date custom range and dates wholly outside coverage. Real DataFusion covers leap day, interior/end gaps, zero capacity, positive-capacity zero outage, signed values and a near-half exact rounding boundary. |
| S02 | Real stored expired/revoked sessions and inactive accounts return 401 without debit; missing HTTP identity is rejected. Unknown roles are forbidden by the actual database constraint, which the test preserves. The service's defensive 403 for an unknown principal remains Step 3 controlled-adapter evidence. |
| S12 | Real empty active pointer with retained candidate rows gives 409 and no execution; missing bound evidence gives 503 before capacity. Shared preview regressions cover additional invalid pin/approval conditions. No foreign-key or security constraint was disabled to create a broken pointer. |
| S13–S14 | A barrier pauses a real repeatable-read transaction after the publication read while another connection publishes V2 and adds a failed run: the original evidence and freshness remain on V1. A separate real container overlap returns V1's 10.00 while V2 returns 20.00 and reports the newer failed refresh. |
| S15, S19 | Real national-only Parquet schema; inaccessible facility/generator/application tables, sibling unpublished sentinel, Docker socket, secrets/root-only files, writes and network; no inherited credential variables. Responses exclude the source detail canary and storage reads exclude detail datasets. Test fault commands probe the unchanged isolation configuration before calling the normal runtime handler. |
| S16 | Test workloads alter the bound runtime reply after real execution: duplicate/outside dates and unexpected lookahead all return `dependency_unavailable`, after cleanup. They are deliberately malformed runtime replies, not claims that producer validation accepts corrupt publications. |
| S17 | SQL, preview, dashboard and metric use real shared counters across spawned processes: 30 admitted attempts and 10 rate denials from 40 calls. Mixed capacity admits two for one user and four across users; subsequent calls are denied without queued work. These tests reserve real capacity without launching containers. |
| S18 | Actual checksum damage/missing objects fail before launch. Slow storage uses a shortened test deadline; the runtime timeout uses the unchanged 30 seconds. Real OOM/output limits, startup failure, socket disconnect, SIGKILL supervisor crash and uncertain removal preserve cleanup ownership. The release observer independently checks container absence and staging removal immediately before the actual database release. |
| S21 | Not run: retained readiness failed. Alayala has not performed the retained-account checks in this step. |

## Environment and reproduction

Used the existing sibling `trinity/backend/.venv/bin/python`, CPython 3.14.8, with `PYTHONPATH=backend/src:backend/tests` pointing at this checkout. `uv` is unavailable on the current shell and this worktree has no `.venv`. All 14 pinned direct dependencies matched `backend/pyproject.toml`, and import resolution was checked against this worktree. Fresh locked installation remains unverified; dependency definitions and `uv.lock` were not changed.

Used PostgreSQL 17.11 at the configured local Homebrew path and the configured Docker Desktop Unix socket. The existing local image was:

```text
sha256:ca94ae39c7694172dc6a683fac4a531605259bf04fec8be9b32dba9484d57433
```

A read-only, network-disabled container independently hashed all 10 package/runtime/contract files used by execution. Every hash matched this checkout. No image pull or build was needed. The database runner created/migrated/stopped only its temporary private Unix-socket cluster. Runtime fixtures own unique deployment labels and disposable volumes. Storage serves synthetic producer bytes through the existing native-to-Docker staging bridge; deployed mounts, live S3 permissions and production publication activation remain separate evidence.

From the repository root, after setting `SIBLING_PYTHON` to the existing interpreter and the two `TRINITY_TEST_*` execution settings to the verified local image/socket:

```sh
PYTHONPATH=backend/src:backend/tests "$SIBLING_PYTHON" -m unittest discover -s backend/tests -p 'test_dashboard_engine.py' -v
PYTHONPATH=backend/src:backend/tests "$SIBLING_PYTHON" backend/tests/run_local_sql_checks.py --dashboard --failfast
PYTHONPATH=backend/src:backend/tests "$SIBLING_PYTHON" backend/tests/run_local_sql_checks.py --all --failfast
env -u TRINITY_TEST_DATABASE_URL -u TRINITY_TEST_QUERY_IMAGE -u TRINITY_TEST_REDIS_PORT \
  PYTHONPATH=backend/src:backend/tests "$SIBLING_PYTHON" -m unittest discover -s backend/tests -v
```

The combined runtime and full offline commands run serially. The runner overwrites the test DSN with its disposable cluster. Never change that guard to use the retained database. Without an explicit image, container tests skip; a successful exit with skips is not full runtime acceptance.

## Measured results

| Check | Result |
|---|---|
| Final combined PostgreSQL/HTTP/container/engine regression | **101 passed, zero skipped**, 385.191 seconds; runner exited 0 after stopping its disposable cluster |
| National cases within the combined run | **19 passed**: 1 engine, 6 PostgreSQL, 12 runtime/HTTP |
| Shared cases within the combined run | **82 passed**: 11 SQL PostgreSQL, 10 preview PostgreSQL, 15 preview runtime, 10 query-guarantee, 25 auth and 11 catalog |
| Final full offline regression | **609 discovered: 415 passed, 194 opt-in skips**, 33.170 seconds; zero failures/errors |
| Production source comparison | All 94 Python files unchanged from the Step 4 baseline |
| Runtime image | All 10 execution package/contract/runtime file hashes matched current source; no build |
| Retained operator check | **Not ready; not performed** |

The offline skips remain skips; several corresponding database/container cases passed in the separate combined run. The counts overlap across suites and must not be added as a unique-test total. Unrelated Refresh/Publication opt-in acceptance is not claimed by this dashboard run.

Final combined measurements: national 30-second timeout plus cleanup **30.113 seconds**; HTTP disconnect to confirmed cleanup **2.089 seconds**; natural-expiry recovery after supervisor death **29.963 seconds**. The shared separate-process recovery case also passed, at **31.345 seconds** after owner death. No timeout, authentication or cleanup assertion was weakened.

Final Docker inspection found no containers with the `trinity.query` label and no `trinity-preview-test-`, `trinity-sql-test-` or `trinity-sql-recovery-` volumes. The original retained API and PostgreSQL containers remained healthy with their existing uptime. All test-owned resources were cleaned up. Final static review passed: `git diff --check`, AST parsing of six dashboard test/runner files, 294 local Markdown link destinations, balanced fences and whitespace checks for 14 untracked files. Protected query/staging/runtime source, dependency files and the runtime image definition have no Git diff.

The first focused Step 4 suite passed 18/18 tests with zero skips in 123.319 seconds. It measured national timeout plus cleanup at 30.119 seconds, real HTTP disconnect cleanup at 2.084 seconds and natural-expiry recovery after supervisor death at 29.791 seconds. The final combined run also includes the subsequently added real-HTTP preset/fully absent range case and explicit real-engine zero-outage assertion.

The initial isolated PostgreSQL run stopped on a test fixture constraint error: setting `expires_at=created_at` violates the required positive session lifetime. Corrected the fixture to use a creation time two hours ago and expiry one hour ago. The focused rerun passed without changing authentication, relaxing a database constraint or adding retries. Existing Starlette/httpx deprecation warnings remain; dependency pins are preserved.

## Retained readiness evidence

Inspected the already running `trinity-postgres-1` with `psql` in an explicit `BEGIN READ ONLY` transaction. The statement returned only readiness/count values:

```sql
SELECT json_build_object(
  'active_publication', EXISTS (
    SELECT 1 FROM active_publication WHERE publication_event_id IS NOT NULL
  ),
  'publication_events', (SELECT count(*) FROM publication_events)
);
```

Observed: `active_publication=false`, `publication_events=0`. No published version exists to validate for the operator check. Candidate presence cannot substitute for publication.

Inspected the installed `trinity-api-1` code without printing configuration or secrets: `app.openapi()['paths']` lacks both national routes, and `inspect.signature(create_app)` has no `enable_preview` parameter. Observed readiness summary: `national_routes_registered=false`, `preview_switch_available=false`. Initial introspection assumed the current route/signature shape and failed; the final check accounts for the installed older version. No claim is made that rebuilding alone supplies the missing publication or execution configuration. A separate read-only HTTP request to the running API at `http://127.0.0.1:8000/openapi.json` returned 200 and confirmed that both national routes and the preview route are absent. This confirms the missing route surface in the running service, not only its installed source.

No retained login, migration, seed, publication, configuration write, image rebuild or service restart occurred. No live EIA or S3 call, commit, push, PR or remote mutation occurred. Synthetic fixtures are not new EIA anomalies; maintain data evidence — ongoing, and leave FINDINGS unchanged.

## Remaining operator gate

After the retained prerequisites are supplied through separately authorized work, [ME] must sign in as Viewer and Analyst and check the default range, a historical range with cards for its end date, and one matching metric date. [YOU] records only safe observed results. Until then, S21 is pending and Step 5 is a prerequisite handoff, not operator acceptance.

Next: [ME] review this handoff and decide the scope of retained deployment/publication preparation.

## Subsequent Git delivery authorization

[ME] Alayala requested committing and pushing the completed dashboard work, then merging it into `pending-endpoints-frontend`. This supersedes the earlier no-Git boundary for delivery only; retained deployment/publication and the operator check remain outside this Git action.

[YOU] Fetched origin and verified both local branches matched their remotes. The target worktree was clean and its head was an ancestor of the dashboard branch. Split the implementation into `e611bd0` (pure calculation/models), `1c29537` (service/routes) and `08974b5` (real acceptance), followed by the design/evidence documentation commit. The requested merge preserves these commits without squashing or rewriting history. Git history and remote refs provide the final delivery identity; the acceptance results above apply to the unchanged source tree.
