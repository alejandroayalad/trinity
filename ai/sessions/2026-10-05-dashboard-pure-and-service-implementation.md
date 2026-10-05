# National dashboard — pure calculation and offline service implementation

Date: 2026-10-05
Branch: `feat/national-dashboard`
Scope: [tasks](../../sdd/national-dashboard/tasks.md) Steps 2–3 only. A9/A15/A16/A19 apply; D01–D03 are the accepted specification rules.

## Objective and contributions

[ME] Alayala supplied Steps 2 and 3 and requested “continue with this steps.” [YOU] treated that request as authorization for both steps, with the Step 2 test gate before Step 3. The initial chat update interpreted authorization as Step 2 only; the next scope update corrected that interpretation before service work. Step 4, real runtime activation, retained data changes and Git delivery were not performed.

[YOU] Inspected repository status, README, CONTRIBUTING, product/data context, applicable decisions, the approved specification, design/tasks and existing preview, catalog, publication, transport and test code. Preserved pre-existing changes in DECISIONS, NOTES, the planning session, backend documentation, specification, design/tasks and the dashboard package stub. Explained input → flow → output and a duplicate-date failure before edits.

[YOU] Implemented strict primitive parsing, separate post-debit combination checks, publication-based date ranges, exact fraction rounding, gap points and shared dashboard/metric builders in `backend/src/trinity/dashboard/calculation.py`. Implemented closed response models, required fields, metric/reason rules, contiguous date checks, summary equality and publication/freshness consistency in `dashboard/schemas.py`.

[YOU] Implemented `NationalService`, exact D01 debit order, one read-only snapshot for publication/evidence/freshness, national `PreviewOperation` with page size equal to the selected date count, and `RefusingCodec`. Both routes reuse `queries.router.supervised_call`. `create_app` accepts `national_service` injection and reuses `enable_preview=False`. No cursor keys are needed by these routes.

[ME] Alayala explained that the dashboard exposes two decimal places and that the negative sign has no useful meaning once this value rounds to zero. [YOU] Confirmed that this explains why `-0.0001` percent is serialized as `0.00`. This records the rounded-zero explanation observed in the first reply.

[ME] Alayala then explained that `summary` represents the selected end date, not the latest available date. For a selected October 2, using October 1 would silently change the meaning and make missing October 2 data look valid. [YOU] Confirmed that this explains the `not_reported` summary. Both requested explanations have now been observed; the Step 2 human understanding checkbox is complete. This does not establish a broader code walkthrough or runtime verification.

## Necessary integration corrections

The original Step 3 file list omitted two integration points:

1. `SafeTransport.__call__` in `backend/src/trinity/errors.py` rejected every query string outside preview/refresh paths. Without registering the two new exact GET paths, `GET /api/v1/metrics/offline-share?period=2026-10-01` would return 422 before the service or session checks. The transport now passes these two paths to the strict authenticated service; body/query size limits and all other path rules stay in place. Offline HTTP tests check authentication precedence, duplicates, bodies, unexpected paths and the default execution gate.
2. `HealthTests.test_surface_contains_only_implemented_product_operations` in `backend/tests/test_health.py` asserted the old exact route set. The first full regression found only this failure. Added the two implemented endpoints to the assertion; the focused health check and full rerun passed.

These changes qualify the original “shared files outside the planned list are unchanged” gate. They are explicit scope corrections needed to integrate the authorized endpoints, not a claim that the original file list was complete. Design/tasks now name both files. No product decision changed.

## Verification and results

The worktree has no `.venv`; `uv` was not available on this shell. Commands ran from `backend/` with `PYTHONPATH=src` and the existing sibling `trinity/backend/.venv/bin/python` (CPython 3.14.8). This is a source verification run with an installed environment, not fresh locked-install evidence. No dependency or lockfile change was made. No formatter/linter/type-checker command is configured in `backend/pyproject.toml`; CONTRIBUTING review and the repository's unittest workflow were used.

Commands below use `SIBLING_PYTHON` to denote that existing interpreter, not a newly installed environment:

```sh
PYTHONPATH=src "$SIBLING_PYTHON" -m unittest discover -s tests -p 'test_dashboard_unit.py' -v
PYTHONPATH=src "$SIBLING_PYTHON" -m unittest discover -s tests -p 'test_preview_unit.py' -q
PYTHONPATH=src "$SIBLING_PYTHON" -m unittest discover -s tests -p 'test_dashboard_service.py' -q
PYTHONPATH=src "$SIBLING_PYTHON" -m unittest discover -s tests -p 'test_health.py' -q
env -u TRINITY_TEST_DATABASE_URL -u TRINITY_TEST_QUERY_IMAGE -u TRINITY_TEST_REDIS_PORT \
  PYTHONPATH=src "$SIBLING_PYTHON" -m unittest discover -s tests -v
```

| Check | Result |
|---|---|
| Dashboard pure | 16 passed; S03–S11 at the pure level |
| Existing preview unit | 28 passed |
| Dashboard service and in-process HTTP | 23 passed |
| Health route inventory | 2 passed |
| Full offline regression, including auth/catalog/SQL/preview | 590 discovered, 414 passed, 176 skipped, 0 failures/errors; final run 28.829 seconds |
| Diff whitespace | `git diff --check` passed |
| Documentation and new files | 163 local link destinations exist; Markdown fences are balanced; 10 untracked files passed the trailing-whitespace check. |
| Protected source baseline | SHA-256 comparison of 23 files passed: all 19 Python files under `queries/` (including runtime/staging), `contracts/queries.py`, `Dockerfile.query`, `pyproject.toml`, `uv.lock`. Git diff also showed no changes in the protected paths. |

The pure tests cover all D01 date-table rows, calendar leap rules, 366/367 bounds, malformed versus semantic inputs, every D02 row, ratios immediately below/at/above a rounding boundary, both signs with decimal precision reduced to three digits, maximum stored values, zero capacity versus zero outage, source preservation, null source percentage, interior/end gaps, out-of-coverage dates, per-date metric agreement, extra/missing fields, ordering and summary invariants.

Service tests cover all roles with national-only results, pre-debit authentication/shape rejection, committed semantic-failure debit, rate denial, second identity checks, 409 without execution, broken pin/evidence, same connection for all snapshot reads, failed/unfinished newer refresh, pinned metadata during a controlled pointer change, correct page sizes, closed transactions before execution, cancellation and capacity cleanup ownership, duplicate rows and refused signing, wrong response pin/range, default-disabled 503, enabled-switch delegation, safe headers, and nested serialization against the canonical OpenAPI schemas. These use controlled adapters; they do not establish actual PostgreSQL snapshot races, shared-counter persistence or Docker isolation.

A first test-file write used the repository-relative path while the command was already in `backend/`; that write failed and zero tests ran. Correcting the path produced the recorded pure test run. A first HTTP schema test incorrectly used whole-string matching for the canonical `Z$` suffix pattern. Corrected the test to use JSON Schema pattern search semantics; no production or OpenAPI change was needed. The existing Starlette/httpx deprecation warning was observed; dependency pins were preserved.

## Boundaries and next action

No SQL was executed against retained data. No EIA request, S3 operation, Docker build, container run, migration, live activation, commit, push, PR or remote mutation occurred. The integration tests skipped by the offline command remain unverified here. Runtime/image source is unchanged; no claim is made about a deployed image or process.

Maintain data evidence — ongoing. These synthetic cases are not EIA anomalies or coverage proof, so FINDINGS was not changed.

Done: pure and offline service gates passed, with the two documented integration additions.
Pending: separately authorized Step 4 real acceptance and later retained-account checks.
Blocker: no offline implementation blocker. Execution remains disabled by default; retained publication readiness is unverified.
Next: [ME] review Step 4 before authorizing real acceptance.
