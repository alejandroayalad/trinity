# Design: National dashboard and offline-share metric

Date: 2026-10-05
Status: Steps 2–3 authorized and implemented October 5, 2026; see the [implementation record](../../ai/sessions/2026-10-05-dashboard-pure-and-service-implementation.md). Alayala accepted the `dashboard/` feature folder and reuse of the preview execution switch. Steps 4–5 were subsequently authorized; see the [real acceptance and operator handoff](../../ai/sessions/2026-10-05-dashboard-runtime-and-operator-handoff.md). Retained deployment and activation were not performed.
Branch: `feat/national-dashboard`; inspected HEAD `60499b7`.
Basis: [approved specification](spec.md) (R01–R23, D01–D03), [preview design](../dataset-preview/design.md), A9/A15/A16/A19–A21 in [DECISIONS.md](../../DECISIONS.md), [backend structure](../../docs/backend.md), [API contract](../../docs/api-contract.md#catalog-and-national-dashboard) and [schema](../../docs/schema.md).
Evidence: [planning and specification session](../../ai/sessions/2026-10-05-dashboard-backend-priority.md#dashboard-design-and-tasks).

## Human

### What will change

Add a new `dashboard/` feature folder with two GET routes. Both use the national preview read that already exists: same strict checks, rate debit, publication pin, frozen national diagnostics, capacity slot, staging, isolated container and cleanup. The new code is small. It checks the dashboard inputs, turns the national rows into one point per date, calculates the metric with exact fractions, and builds the two OpenAPI responses.

Input → flow → output: `GET /dashboard/national?preset=90d` → check session and `national:read` → check parameter shape → debit one analytical attempt → check combinations → in one database snapshot, pin the publication, its evidence and the latest refresh → resolve 90 dates from the latest observation → run one national preview operation for those dates, with page size equal to the number of dates → after confirmed cleanup, fill missing dates, calculate each metric and set `summary` to the last point → `DashboardResponse`.

Example: the range has 30 dates and the national file has 29 rows (October 1 is missing). The runtime returns 29 rows and `has_more=false`. The API returns 30 points; October 1 has null values and `not_reported`.

Failure: the published national file has the same date twice. The existing preview row check sees keys that are not strictly ascending and returns `503 dependency_unavailable`. The client receives no partial dashboard.

### Delivery boundary

No change to the runtime image, `contracts/queries.py`, `queries/client.py`, staging, migrations or dependencies. The metric uses Python's standard `fractions` module.

Accepted by alayala on October 5, 2026:

- **Feature folder:** all dashboard code goes in `backend/src/trinity/dashboard/`, not in `queries/` or `catalog/` (recorded under A15). The initial folder contained only `__init__.py`; Steps 2–3 subsequently implemented the planned modules.
- **Execution switch:** the routes use the existing preview execution switch (`create_app(enable_preview=…)`). They return `503 dependency_unavailable` until preview execution is enabled, because they depend on the same runtime and frozen-evidence gate. No separate dashboard switch is added.

## LLM

### Inspected baseline

Paths are relative to `backend/src/trinity/`.

| Component | Observed behavior and use |
|---|---|
| `queries/service.py:PreviewService.prepare` | Identity → primitive parse → `repository.reserve_rate` → semantic checks → reauthorize and `read_pinned_publication` + `read_preview_publication` in one read-only snapshot → `PreviewOperation` → separate 30-second deadline → `reserve_capacity`. The dashboard copies this order (D01); it does not call the preview route or parse preview parameters. |
| `contracts/queries.py:PreviewOperation` | Accepts `national`, a range of 1–366 dates and `page_size` 1–1000. Checked on this branch: a 366-date national operation with `page_size=366` is valid, 367 dates are rejected, and a one-date `page_size=1` operation is valid. No new operation kind is needed. |
| `queries/client.py:QueryExecution.execute` | For a `PreviewOperation`, reads national diagnostics with `read_preview_diagnostics`, stages only that dataset, runs the container, validates the batch with `build_preview_batch_response`, checks the 5 MiB limit and confirms cleanup before returning a `PreviewResponse`. |
| `queries/preview_schemas.py:build_preview_batch_response` | Checked with synthetic batches: normal rows pass; duplicate dates, negative capacity and `has_more=true` with a codec that refuses to sign all return `503 dependency_unavailable`; zero rows return `reason=not_reported`. Decimal cells are exact six-place strings. |
| `catalog/service.py:get_catalog`, `refresh/repository.py:read_last_refresh`, `catalog/schemas.py` | Freshness rule and models (`Freshness`, `LastRefresh`, `utc_timestamp`). Reuse the models and the repository read; leave `get_catalog` unchanged. |
| `queries/config.py:preview_execution_factory`, `main.py:create_app` | Execution stays disabled unless `enable_preview=True`. Tests inject services through `app.state`. |

The checks above ran with this branch's source on `PYTHONPATH` and the locked environment of the sibling `trinity` worktree (Python 3.14.8), because this worktree has no `.venv`. They are design evidence, not acceptance tests.

### Component responsibilities

| File | Planned responsibility |
|---|---|
| `dashboard/__init__.py` — created | Package docstring only. |
| `dashboard/calculation.py` — new | Pure code, no database or storage. `parse_dashboard_input` and `parse_metric_input` (D01 primitive shape), `resolve_range` (preset or custom, combinations, 366 limit), `offline_share` (exact D02 rounding), `build_points` (one point per date, null reasons), `build_dashboard` and `build_metric` (from a validated `PreviewResponse`, publication and freshness). |
| `dashboard/schemas.py` — new | Closed models `NationalDay`, `DateRange`, `DashboardResponse`, `MetricValue`, `MetricResponse`, matching OpenAPI exactly. Validators enforce `len(days) == dates in range`, ascending dates, `summary == days[-1]`, metric/reason pairing and the two-place pattern. Reuse `Publication`, `Freshness` and `PreviewDiagnostic`. |
| `dashboard/service.py` — new | `NationalService` with `dashboard(token, pairs, body, cancelled)` and `metric(...)`. One shared `_prepare` implements the D01 order and returns a `PreparedPreview` with a `RefusingCodec`, plus the pinned freshness. |
| `dashboard/router.py` — new | `APIRouter(prefix='/api/v1')` with `GET /dashboard/national` and `GET /metrics/offline-share`, `response_model`, raw `request.query_params.multi_items()`, the request body and the existing `queries.router.supervised_call`. |
| `main.py` | Register the dashboard router. Add `national_service=None` to `create_app` and store it in `app.state`, like `preview_service`. |
| `errors.py` — necessary integration addition | `SafeTransport` lets the two exact GET paths reach identity-first parameter/body validation. Keep transport limits and all other path rules. |
| `tests/test_health.py` — necessary regression update | Add the two implemented endpoints to the exact route inventory. |

Dependency direction: `dashboard/` imports shared analytical pieces from `queries/` (`repository.reserve_rate`, `repository.reserve_capacity`, `service.QueryDeadline`, `service.PreparedPreview`, `config.preview_execution_factory`, `router.supervised_call`), `contracts/queries.py:PreviewOperation`, `publication/repository.py`, `refresh/repository.py:read_last_refresh` and the catalog freshness models. `queries/` never imports `dashboard/`. No query, staging or supervision logic is copied.

Placement note: `docs/backend.md` listed “metric endpoints” under `catalog/router.py`. The catalog serves metric definitions; computing the metric needs the analytical slot and container. Alayala selected a separate `dashboard/` feature; the backend tree and A15 now show it.

### Request flow and transaction boundaries

| Phase | Work | Boundary |
|---|---|---|
| A — identity | `resolve_session`, `require(principal, 'national:read')`. | Short read-only transaction, 15-second preflight deadline like preview. |
| B — shape | Inspect all pairs. Dashboard accepts only `preset`, `start`, `end`; metric accepts only `period` (required). Duplicates, unknown names, blanks, nonempty body, bad dates or bad `preset` → 422. | Pure; no debit. |
| C — rate | `repository.reserve_rate`. Denied → 429 with `Retry-After`. | Separate short write transaction; committed. |
| D — combinations | Preset with dates; one custom date; `start > end`; more than 366 dates → 422. | Pure; debit kept. |
| E — snapshot | Reauthorize the same user/session; `read_pinned_publication`; `None` → 409 `data_unavailable`; `read_preview_publication`; `read_last_refresh`; build `Freshness`. | One read-only snapshot (D03). |
| F — operation | Resolve preset from `latest_observation_date`. Build `PreviewOperation('national', …, start, end, page_size=dates)`. | Pure. |
| G — admission and execution | `preview_execution_factory(enabled=…)`, new 30-second deadline, `reserve_capacity`, then `execution.execute(prepared)`. | Existing supervisor; no open transaction during I/O. |
| H — response | `build_dashboard` or `build_metric` from the returned `PreviewResponse`, then model validation. | Pure; runs after cleanup. Any failure here is 503 `dependency_unavailable`; the slot is already released correctly. |

`RefusingCodec.encode` raises. With `page_size` equal to the number of dates and unique dates, `has_more` can be true only for a broken artifact, so signing must never happen. The dashboard needs no cursor keys, and a missing cursor-key configuration cannot break a Viewer dashboard.

### Metric calculation (D02)

`offline_share(capacity: str, outage: str) -> (value, reason)` takes the exact decimal strings from the preview row.

1. Capacity `0` → `(None, 'zero_capacity')`. (Negative capacity is already rejected by the preview row check.)
2. `x = Fraction(Decimal(outage)) * 10000 / Fraction(Decimal(capacity))` is the exact ratio in hundredths of a percent.
3. `n = floor(|x|)`; if `|x| − n ≥ 1/2`, add 1. This is half away from zero.
4. `n == 0` → `"0.00"`. Otherwise sign + `n // 100` + `"."` + two digits of `n % 100`.

Fractions make every rounding decision exact, so there is no double rounding. A randomized comparison with `Decimal` at default precision found no difference in 200,000 cases plus targeted near-half cases. That shows agreement, not proof; the fraction method is exact by construction. Expected D02 table outputs were reproduced: `12.50`, `40.95`, `12.35`, `-12.35`, `0.00`.

### Point building

`build_points(start, end, rows)` maps each preview row by date. For each date from `start` to `end`:

| Row | `capacity`, `outage`, `percentOutage` | `offline_share_percent`, `reason` |
|---|---|---|
| absent | `null`, `null`, `null` | `null`, `not_reported` |
| capacity `0` | source strings; `percentOutage` may be null | `null`, `zero_capacity` |
| capacity > 0 | source strings | calculated, `null` |

Rows are already validated as unique, ascending and inside the requested range. `build_points` still rejects a row outside the range or a repeated date (defense in depth). Source strings are passed through unchanged, so the dashboard uses the preview serializer (R14). The metric endpoint uses the same `build_points` for its one date, so R16 holds by construction.

### Errors and limits

All error mapping, the 30-second deadline, 1 GiB memory, 5 MiB output, retries, disconnect handling and cleanup come from the existing preview path. A dashboard response for 366 dates is far below 5 MiB; the existing size check still applies to the runtime batch. No dashboard-specific retry or timeout exists.

### Verification approach

| Layer | Plan |
|---|---|
| Offline pure | `tests/test_dashboard_unit.py`: parsing, D01 date table, leap years, combinations, every D02 row, signs, high-precision values, zero capacity, null `percentOutage`, gaps, summary equality, metric/dashboard agreement over a range, model rejection of wrong lengths or extra fields. |
| Offline orchestration | `tests/test_dashboard_service.py`, modeled on `test_preview_service.py`: exact D01 order and debit points with controlled adapters, one snapshot for publication and freshness, no execution on 409, refusing codec, disabled execution → 503, route headers and OpenAPI shape through `TestClient`. |
| Real engine | Extend the existing temporary-Parquet engine fixture: 366-date national range, missing dates, exact decimals through `execute_preview`. |
| Real PostgreSQL/HTTP/container | Add a `--dashboard` option to `tests/run_local_sql_checks.py`: all roles, publication races, failed newer refresh, mixed SQL/preview/dashboard rate and slot limits, national-only mount, lifecycle faults. |
| Operator | Alayala's retained-account check (S21) against a legitimate publication. |

## Review gate

Done: design that reuses the national preview path in a new `dashboard/` feature, with exact rounding and the shared execution switch.
Pending: retained-account acceptance (S21); both Step 2 explanations and Step 4 local acceptance are recorded. See [tasks](tasks.md) and the runtime/operator handoff.
Blocker: the retained database has no active publication; the older retained API lacks national/preview routes and the preview switch.
