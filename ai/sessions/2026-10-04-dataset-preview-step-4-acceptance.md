# Dataset preview Step 4 acceptance — October 4, 2026

## Authority and current state

[ME] Alayala said he had reviewed Step 3 and requested Step 4. This authorizes the automated acceptance stage, including temporary test databases and isolated test containers. The [task checklist](../../sdd/dataset-preview/tasks.md) assigns the matching image build to [ME]. Human review is recorded; no conceptual explanation is inferred.

[YOU] Continued on `feat/catalog-permissions`, HEAD `fa766e1`, preserving all reviewed, uncommitted Step 3 files. Current README, CONTRIBUTING, Step 3 record, preview tasks and the shared PostgreSQL/Docker implementation were inspected. Comments remain about behavior and specific rules. No production dependency or runtime implementation was changed in this portion of Step 4.

Local read-only prerequisite checks found PostgreSQL 17.11 and Docker 29.8.1. The only existing query tag was `trinity-query:sql-slice`; no Step 4 test-image configuration was supplied. Docker Desktop's user socket exists; `/var/run/docker.sock` does not. The older image cannot establish acceptance of the new protocol.

## Input, flow, output and failure

Input: synthetic retrieved rows, complete frozen validation evidence, disposable application state and current local personas. The existing producer freezes/validates/stores the fixture through an in-memory S3 adapter. A test-only transaction binds its exact version, manifest, attempt, bundle and required approval to the disposable active publication. The real PreviewService and actual HTTP route then enforce authority, debit and publication rules. Native database and container evidence remain separate.

Failure example: a malformed primitive filter yields 422 without debit; a semantic facility filter on national data consumes exactly one committed debit, then fails before staging. A concurrent publication change must leave one request on its original snapshot and require a cursor restart on the next request.

The fixture has three dates, two facilities and two generators per date. National missing percentage and facility missing label exercise scoped warnings; MW totals still reconcile. This is not EIA source evidence, the retained publication writer or source completeness proof. Maintain data evidence — ongoing; no findings changed.

## Changes

| File | Purpose |
|---|---|
| `backend/tests/run_local_sql_checks.py` | Adds `--preview` and `--all` while retaining the disposable Unix-socket cluster and cleanup boundaries. |
| `backend/tests/preview_fixture.py` | Reuses the real freeze/validation/bundle producer; atomically seeds its complete synthetic state only in a `trinity_test_` database; supplies real loopback HTTP. |
| `backend/tests/test_preview_postgres.py` | Tests migration constraints, exact approval pinning, HTTP denials, current role/session checks, mixed cross-process rate/capacity, rolling boundaries, independent-connection snapshots and unavailable dependencies. |
| `backend/tests/preview_runtime_fixture.py` | Prepares uniquely owned Docker resources and a test-only native-path/daemon-volume copy bridge. Synthetic object GETs preserve exact hashes and permit fault injection. |
| `backend/tests/test_preview_runtime.py` | Prepares real HTTP pagination/role/diagnostic/SQL scenarios plus isolation, timeouts, OOM/output, disconnect, ambiguous launch, SIGKILL recovery and stale-owner checks. Matching-image results are recorded below. |

## Measured checks

Commands from the repository root used the existing virtual environment, not a fresh dependency installation:

```sh
backend/.venv/bin/python backend/tests/run_local_sql_checks.py
backend/.venv/bin/python backend/tests/run_local_sql_checks.py --all
backend/.venv/bin/python backend/tests/run_local_sql_checks.py --preview
env -u TRINITY_TEST_DATABASE_URL -u TRINITY_TEST_QUERY_IMAGE backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_preview*.py' -q
```

- Initial SQL database baseline: 11 discovered, 9 passed, 2 image-dependent skips, 14.826 seconds. Migration 0004 applied successfully in the disposable cluster.
- Combined database run: 70 discovered, **54 passed**, 16 image-dependent skips, 121.158 seconds. This covers SQL, the original nine preview DB cases, auth and catalog.
- Final SQL/preview database run after the added real missing-runner-configuration check: 35 discovered, **19 passed**, 16 image-dependent skips, 47.146 seconds. All ten preview database cases passed. The 16 skips are 14 preview container cases plus two existing SQL container cases; none counts as a pass.
- Offline preview run: 87 discovered, 64 passed and 23 database/container skips, 3.151 seconds. One further database-only configuration case was added afterward; it does not alter the 64 offline cases.
- Five Step 4 test/runner files passed AST and whitespace checks. Scoped test/runner diff review and `git diff --check` passed. All 315 local links/anchors and code fences passed across the eight changed/new Markdown files (including the preserved Step 3 documents).

Initial fixture corrections: the producer requires its output root to exist; the fixture now creates its own temporary root. The logout test initially omitted the required empty JSON body and therefore had not revoked the session; the corrected request asserts 204 before testing revocation. These were test setup errors, not relaxed production guards. The existing Starlette/httpx deprecation warning remains; no dependency was changed.

Real database coverage uses separate processes for mixed service limits and independent connections for the publication race. HTTP denial coverage uses a bound loopback server, not only TestClient. Successful preview HTTP pages, resource isolation and actual cleanup timing require the pending image run. No real S3 request or retained database operation ran.

## Initial image gate (subsequently satisfied)

[ME] Build `trinity-query:preview-step4` using the exact command in [backend acceptance instructions](../../backend/README.md#preview-acceptance--step-4). [YOU] Then resolve its immutable image ID, use the verified local socket, run the container/combined acceptance checks, inspect cleanup and record measured timings and any defects.

Until that run, the prepared container assertions are **not evidence**. Step 4 remains incomplete; default preview execution stays disabled. The retained evidence index/publication writer and Step 5 operator run remain separate. Nothing was committed, pushed, deployed or published.

Done: Step 3 review recorded; Step 4 fixtures and database acceptance work; disposable-only migration.
Pending: matching-image container acceptance and final combined regression.
Blocker: user-built image under the task's [ME] boundary.
Next: [ME] build `trinity-query:preview-step4`.


## Matching image supplied

[ME] Built `trinity-query:preview-step4` successfully and supplied the terminal screenshot. [YOU] Independently resolved local image ID `sha256:ca94ae39c7694172dc6a683fac4a531605259bf04fec8be9b32dba9484d57433` and started the combined acceptance runner with that exact ID and Docker Desktop's verified user Unix socket. The image-build gate is satisfied; test results, not the screenshot, determine runtime acceptance. No retained service was rebuilt or started by this run.


## Runtime harness corrections

The first matching-image combined run executed 71 tests in 355.376 seconds: 66 passed, four failed and one errored. These results were investigated before acceptance:

- **Scope:** uncommitted test harness and shared Docker adapter. **Expected:** intentional timeout, OOM, isolation and disconnect workloads reach a real restricted container; normal requests retain the fixed runtime command. **Observed:** four fault scenarios failed at `Docker.verify` before the workload ran. **Evidence/flow:** `BridgeDocker.call` replaced `Cmd` with an explicit probe, while `Docker.verify` correctly required `-m trinity.queries.runtime`. **Failure scenario:** a 60-second sleeper was rejected as `dependency_unavailable` before it could exercise the 30-second deadline. **Correction:** extract the unchanged isolation checks into `_verify_isolation`; production `verify` still requires the fixed command. Only the test subclass accepts its exact configured probe command and applies the same checks to real Docker inspection. No inspection fields are fabricated. A real-container regression also confirms the production verifier rejects a changed command. **Validation:** the seven standalone SQL container/frame checks passed in 9.020 seconds; full runtime reruns are recorded below.
- **Scope:** uncommitted corruption assertion. **Expected:** a checksum mismatch returns `dependency_unavailable`; exceeding the staged-file bound returns `query_resource_limit`. **Observed:** the test appended bytes and incorrectly expected the checksum error. **Evidence/flow:** `PublishedReader.read_into` compares `ContentLength` against the manifest-backed size bound before hashing. **Failure scenario:** appending seven bytes correctly hits the resource guard first. **Correction:** test a same-size byte change for checksum rejection and appended bytes for the resource limit; assert one GET, no retry and no container launch in both cases. Production staging behavior is unchanged. **Validation:** final matching-image acceptance below includes both cases.

The host-side verifier extraction changes no query-runtime code, so the supplied image remains the matching runtime. Native test staging uses the documented test-only copy bridge; this does not establish deployed Compose volume wiring.


## Corrected focused runtime result

With the same immutable image and local socket, `--runtime-only --failfast` passed all **14 preview runtime cases**, with **zero skips**, in **140.024 seconds**. The six SQL staging regressions also passed in 0.144 seconds. The seven standalone SQL container/frame tests passed in 9.020 seconds. The broader offline run discovered 432 tests: 356 passed and 76 opt-in database/container cases skipped, in 72.130 seconds; those skips require the explicit suites, not an assumption of success.

Measured focused cleanup timings:

| Scenario | Observation |
|---|---|
| Real 30-second analytical deadline | Timeout plus confirmed container removal, staged-file cleanup and reservation release: 30.296 seconds. |
| Actual loopback HTTP disconnect | Socket closure to confirmed cleanup/release: 2.140 seconds. |
| Supervisor process SIGKILL after Docker start | Recovery claim, stale-owner rejection and confirmed cleanup: 0.208 seconds. |
| Unknown create or removal | Capacity remains reserved while termination cannot be established; the removal case releases only after real recovery succeeds. |

The actual HTTP scenarios cover all three roles, continuation/replay, exact entity filtering, full daily-key traversal, scoped diagnostics, closed OpenAPI response fields and existing SQL behavior. Independent connections prove snapshot stability across a publication change and rejection of an old cursor on the next request. Mixed SQL/preview processes share the real PostgreSQL rate/capacity limits. Synthetic storage faults prove bounded retries and one debit; checksum/size failures do not launch a container.

The final combined run additionally checks explicit expected generator keys, generator-filter values and one new debit for cursor replay. Its result is recorded in the final checkpoint below.


## Final checkpoint

**Step 4 automated acceptance passed.** The final `--all` run passed **71/71 tests, zero skips, in 238.743 seconds**. This includes 11 SQL PostgreSQL cases, 10 preview PostgreSQL cases, 14 preview runtime cases, 25 auth PostgreSQL cases and 11 catalog PostgreSQL cases. Every assertion added during final review ran in this combined result.

Across the final offline, combined and standalone container suites, **432 distinct tests passed**. Test-name reconciliation confirms all 76 offline opt-in skips were executed successfully by the explicit suites. The seven standalone container/frame cases include two offline frame cases, so they must not be counted twice. This is aggregate coverage across separate runs, not a claim of a single 432-test runtime command.

The final combined run measured 30.128 seconds for timeout plus confirmed cleanup, 2.082 seconds for disconnect cleanup, and 0.158 seconds for SIGKILL recovery. The timeout's small cleanup interval is measured, not a zero-overhead termination guarantee. Docker inspection after completion found no `trinity.query` containers and no `trinity-preview-test-` or `trinity-sql-test-` volumes. The runner exited successfully after stopping its own temporary PostgreSQL cluster. No retained evidence file appears in the diff.

Review/checks: the focused Step 4 diff was inspected; all 29 changed/new Python files parsed; `git diff --check` passed; eight changed/new Markdown files passed local link/anchor and code-fence checks. `backend/pyproject.toml` defines no separate formatter, linter or type-checker command. The existing Starlette/httpx deprecation warning does not indicate a failed check; dependencies remain unchanged.

Done: Step 4 real disposable PostgreSQL, loopback HTTP, matching-image Docker acceptance and combined regressions; user image-build contribution recorded.
Pending: retained publication writer/index linkage, retained-database migration, deployed configuration and Step 5 retained-account operator evidence.
Blocker for delivery: no verified retained active publication supplies the required frozen provenance. Preview execution stays disabled. Synthetic test publication cannot satisfy that boundary.
Next: [ME] review this checkpoint. No Step 5 work, retained migration, publication, commit or push was performed.
