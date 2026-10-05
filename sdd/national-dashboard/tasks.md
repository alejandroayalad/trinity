# Tasks: National dashboard and offline-share metric

Date: 2026-10-05
Status: Steps 2 and 3 authorized by alayala's request to continue the supplied steps. Implementation and offline checks are recorded below. Both Step 2 human explanations are recorded. Alayala subsequently authorized Steps 4–5 and requested a handoff; current results are recorded below.
Branch: `feat/national-dashboard`.
Basis: [approved specification](spec.md), [design](design.md), A9/A16/A19, and the [session record](../../ai/sessions/2026-10-05-dashboard-backend-priority.md#dashboard-design-and-tasks).

## Human

The slice adds a `dashboard/` feature folder with two GET routes that reuse the national preview read. There are four implementation steps after ongoing evidence work. Each step needs its own authorization and must pass its checks before the next one starts. Offline tests, real database/HTTP/container checks and alayala's retained-account check are separate kinds of evidence; one cannot replace another.

## LLM

### Step 1 — Maintain data evidence — ongoing

- [ ] [YOU] Keep FINDINGS and source values current whenever later dashboard work touches real data. Synthetic fixtures are not anomalies or completeness proof.
- [x] [ME] Approved the specification with D01–D03 and requested design/tasks. [YOU] Traced the preview, publication, catalog and runtime code, checked reuse offline and drafted this plan. This checkbox does not authorize implementation.
- [x] [ME] Selected a separate `dashboard/` feature folder and approved reuse of the preview execution switch. [YOU] Created `backend/src/trinity/dashboard/__init__.py` (docstring only) and updated the design, `docs/backend.md` and A15. At that planning point, no other dashboard code existed.

### Step 2 — Pure inputs, calculation and response models

Scope: R01, R03–R05, R12–R16, R21. No route, database or runtime change.

- [x] [ME] Authorized Step 2. [YOU] Before edits, explain input → flow → output and one failure case.
- [x] [YOU] Add `dashboard/calculation.py`: strict parsing for both endpoints, preset/custom range resolution, `offline_share` with fraction rounding, `build_points`, `build_dashboard`, `build_metric`.
- [x] [YOU] Add `dashboard/schemas.py`: closed OpenAPI-equal models with length, order, `summary == days[-1]` and metric/reason validators.
- [x] [YOU] Add `tests/test_dashboard_unit.py` covering S03–S11 at the pure level: D01 date table, leap years, 366/367, combinations, every D02 row, high-precision and signed values, zero capacity versus zero outage, null `percentOutage`, gaps including the end date, metric equals dashboard point for every date, extra or missing fields rejected.
- [x] [YOU] Follow CONTRIBUTING for comments and docstrings. Run the new tests and the existing preview unit tests. Record counts.
- [x] [ME] Explained why the `-0.0001` case returns `0.00` and why a missing end date gives a `not_reported` summary. [YOU] Recorded both observed explanations in the [implementation session](../../ai/sessions/2026-10-05-dashboard-pure-and-service-implementation.md).

Gate passed: 16 dashboard pure tests and 28 existing preview unit tests passed. [ME] explained both cases correctly: rounded zero loses its negative sign; the summary must represent the selected end date without substituting an earlier observation.

### Step 3 — Service, routes and offline orchestration

Scope: R02, R06–R11, R17–R18, R20–R22.

- [x] [ME] Authorized Step 3 in the same request, after the Step 2 test gate.
- [x] [YOU] Add `NationalService` in `dashboard/service.py` with the D01 order, one snapshot for publication, evidence and freshness, the national `PreviewOperation` with `page_size` equal to the number of dates, and `RefusingCodec`. Import shared pieces from `queries/`; copy none.
- [x] [YOU] Add both routes in `dashboard/router.py` with `queries.router.supervised_call`; register the router and add `national_service` injection in `main.py:create_app`. Use the existing preview execution switch (approved); keep it disabled by default.
- [x] [YOU] Add `tests/test_dashboard_service.py` with controlled adapters: exact debit points (S02–S04), 409 without execution (S12), freshness from the same snapshot, failed newer refresh (S14), refused cursor signing and duplicate rows (S16), disabled execution → 503, headers and exact OpenAPI serialization through `TestClient` (S20 offline part).
- [x] [YOU] Run auth, catalog, SQL and preview offline regressions. Confirm every file in `queries/`, `contracts/queries.py`, staging and the runtime image is unchanged.

Scope correction from implementation evidence: `SafeTransport` in `errors.py` rejected both new query paths before authentication. Register only the two exact GET paths so the service can apply D01. Update `tests/test_health.py` to include the two implemented routes in its exact route inventory. These are the only additional code/test files beyond the original Step 3 list. All `queries/` files, `contracts/queries.py`, staging and `Dockerfile.query` remain unchanged.

Gate: 23 offline service/HTTP tests passed. Full regression result is in the [implementation record](../../ai/sessions/2026-10-05-dashboard-pure-and-service-implementation.md). The original unchanged-files condition is qualified by the two necessary integration changes above.

### Step 4 — Real PostgreSQL, HTTP, engine and container acceptance

Scope: R06–R11, R17–R21 and all R scenarios.

- [x] [ME] Authorized Steps 4–5 and requested a handoff. [YOU] Reused the existing query image after all 10 runtime/contract file hashes matched; no build was needed.
- [x] [YOU] Add `--dashboard` to `tests/run_local_sql_checks.py` using disposable clusters only. Never point it at the retained database.
- [x] [YOU] Real engine fixture: a 366-date national range with gaps and exact decimals through `execute_preview`.
- [x] [YOU] Real HTTP and PostgreSQL: all roles (S01), session failures (S02), publication change during execution (S13), failed newer refresh (S14), broken state (S12), mixed SQL/preview/dashboard/metric rate and 2/4 slots across processes (S17).
- [x] [YOU] Real container: national-only mount and detail canaries (S15), network and write denial (S19), checksum, timeout, memory, disconnect and crash cleanup (S18).
- [x] [YOU] Run the combined regression. Record skips as pending, never as passes.

Gate passed: the combined run passed 101/101 tests with zero skips, including 19 national acceptance cases. See the [handoff](../../ai/sessions/2026-10-05-dashboard-runtime-and-operator-handoff.md) for exact scenario boundaries and timings. This does not prove retained publication readiness.

### Step 5 — Operator check and handoff

Scope: R23, S21.

- [x] [YOU] Checked retained readiness read-only: no active publication and zero publication events; the retained API has neither national routes nor the preview switch. Result: **not ready**. Stopped retained verification without seeding, publishing or deploying. See the [handoff](../../ai/sessions/2026-10-05-dashboard-runtime-and-operator-handoff.md).
- [ ] [ME] Sign in with retained Viewer and Analyst accounts. Check the default range, one historical custom range with range-end cards, and one metric date. [YOU] Record safe results only; no tokens or passwords.
- [x] [YOU] Updated SDD status, NOTES and the unique [runtime/operator handoff](../../ai/sessions/2026-10-05-dashboard-runtime-and-operator-handoff.md); checked links and the final diff.

Gate: prerequisite handoff complete. The retained operator check (S21) is blocked, not passed: no active publication; the running API lacks dashboard/metric/preview routes; its installed startup has no preview switch. No retained mutation was performed.

### Scenario coverage

| Scenarios | Steps |
|---|---|
| S01–S02 | Step 3 offline; Step 4 real; Step 5 retained accounts |
| S03–S11 | Step 2 pure; Step 3 HTTP; Step 4 real values |
| S12, S14, S16 | Step 3 offline; Step 4 real |
| S13, S15, S17–S19 | Step 4 real |
| S20 | Step 3 offline; Step 4 real HTTP and regressions |
| S21 | Step 5 |

### Verification commands

Run from `backend/` with the locked environment. This worktree has no `.venv`, and `uv` is unavailable on the current shell. The recorded checks used the existing sibling `trinity/backend/.venv/bin/python` with `PYTHONPATH=src`. A fresh locked install remains unverified; no dependency files changed.

| Purpose | Command |
|---|---|
| Pure checks | `.venv/bin/python -m unittest discover -s tests -p 'test_dashboard_unit.py' -v` |
| Orchestration | `.venv/bin/python -m unittest discover -s tests -p 'test_dashboard_service.py' -v` |
| Disposable PostgreSQL/HTTP | `.venv/bin/python tests/run_local_sql_checks.py --dashboard` |
| Offline regression | `env -u TRINITY_TEST_DATABASE_URL -u TRINITY_TEST_QUERY_IMAGE .venv/bin/python -m unittest discover -s tests -v` |

### Current checkpoint

Done: Steps 2–4 implementation and automated acceptance; Step 5 read-only readiness check and handoff. Both human explanations are recorded.
Pending: retained environment preparation and alayala's Viewer/Analyst operator check (S21).
Blocker: no active retained publication and an older retained API without the required routes/switch. This branch keeps execution disabled by default.
Next: [ME] review the handoff and decide the scope of retained deployment/publication preparation.
