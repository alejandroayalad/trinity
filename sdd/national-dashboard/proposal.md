# Proposal: Dashboard backend first

Date: 2026-10-05
Status: Draft for review. Planning requested; this document does not authorize implementation or runtime activation.
Inspected branch/HEAD: `frontend`, `444795f`. Concurrent frontend specification, decisions and design-reference work is preserved.
Basis: A9/A15/A16/A19/A20 in [DECISIONS.md](../../DECISIONS.md), [API contract](../../docs/api-contract.md#catalog-and-national-dashboard), [OpenAPI](../../docs/openapi.json), [data contract](../../docs/schema.md), [backend architecture](../../docs/backend.md) and [security contract](../../docs/security-contract.md). Design attribution follows [A25 on the inspected frontend commit](https://github.com/alejandroayalad/trinity/blob/444795f0156983255b7756e175ab4cf5cdca8438/DECISIONS.md#a25--figma-design-and-brand-handoff); this reference does not import frontend work into the main-based endpoint branch.
Evidence: [planning session](../../ai/sessions/2026-10-05-dashboard-backend-priority.md).

## Human

### Outcome and priority

Deliver the backend needed by the designed national dashboard first. Follow with schedule settings and initial setup, Plant filter choices, and failed-run recovery. This priority replaces the earlier backend order in `sdd/frontend/proposal.md` on the separate `frontend` branch; existing slice IDs remain useful references. The concurrent frontend specification is preserved and is not required to read this proposal.

Two new national endpoints are needed. A16 already defines both; all paths below have the `/api/v1` prefix.

| Endpoint | Input | Output and screen use |
|---|---|---|
| `GET /dashboard/national` | Session; `preset=30d`, `90d`, or `1y`, or both `start` and `end` | `DashboardResponse`: publication, range, summary, daily points, national diagnostics and freshness. Cards, chart and daily values share this response. |
| `GET /metrics/offline-share` | Session; `period=YYYY-MM-DD` | `MetricResponse`: publication, date, calculated metric and national diagnostics. Must agree with the dashboard for the same date and publication. |

Viewer, Analyst and Admin can use both. Facility contributions remain Analyst/Admin only and reuse `GET /datasets/facility_outages/preview`. Do not add a separate endpoint for each visual component.

Input → processing → output: authenticate → pin a published version and safe freshness metadata → authorize national files and reserve shared analytical capacity → read checksum-verified Parquet through the isolated DataFusion runtime → calculate exact decimal percentages and fill calendar display gaps → return a consistent response after confirmed execution cleanup. Exploration makes no live EIA request.

Example: a synthetic national row with capacity `1000` MW and outage `125` MW produces `12.50` in both endpoints. An absent next-day row produces a null display point with `not_reported`, never `0.00`. Without a publication, return `409 data_unavailable`; the page shows its waiting state.

### Screen-to-data mapping

| Element | Data and behavior |
|---|---|
| Cards and offline meter | `summary.capacity`, `summary.outage`, `summary.offline_share_percent`, all for `summary.period`. Source `percentOutage` stays separate. Remaining MW is capacity minus outage, using decimal arithmetic. |
| Chart and daily table | `days` has one point per requested calendar date. `1y` means 365 dates; custom ranges allow at most 366 inclusive dates. Missing points break the chart line. |
| Pinned observation and previous-day comparison | Read the selected date from `days`. Compare the previous calendar date, not the previous reported row. If the previous date is outside the loaded range, use the metric endpoint; do not extend an already maximum-sized range. |
| Facility ranking | Preview one selected date. Follow all pages before claiming a complete ranking or total: preview sorts by daily key, not by outage. Sort exact outage values after collection. Show reported facilities only; missing observations are absent rows. |
| Selected facility detail and sparkline | Use the returned source ID with facility preview over a bounded date range. No Plant choice-list endpoint is needed for an already returned facility. Absent dates become display gaps. Sparkline duration remains a frontend choice. |
| Publication and freshness | Use the response publication/freshness and national diagnostics. A failed newer refresh must not hide the valid publication. Never expose Admin errors or facility diagnostics to Viewer. |

### One screen detail to resolve in the specification

The handoff keeps “Latest observation” cards independent of the chart range. A16 requires `summary` to equal the requested range's end date. The concurrent frontend draft R24 uses range-end summary for the cards. These differ when the user selects a historical custom range.

Recommendation: preserve the handoff's latest cards using the default dashboard response, and obtain a separate range response only when needed. This uses the existing endpoint and does not change `summary`. Align frontend R24 after review; this proposal does not overwrite the concurrent draft. The alternative is to make cards follow the selected range and label them “Range end observation.”

All combined national, metric and facility panels must have matching `publication_event_id` and `version_id`. On mismatch or preview `publication_changed`, reload the affected group instead of mixing versions. Specify bounded reload behavior before implementation; clients cannot choose arbitrary historical publications.

The retained Figma screenshot describes a 30-day facility sparkline; frontend draft D03 proposes eight days from the HTML reference. Either fits preview. Resolve the UI duration in frontend planning; it does not require another backend endpoint.

### Delivery sequence

1. **Maintain data evidence — ongoing.** Preserve selected anomalies and source values. Mock values are not findings. New observations follow the existing evidence workflow.
2. **Dashboard backend.** Review this scope, then write the exact specification, followed by design/tasks and separately authorized code. Deliver both national routes with one metric calculation and the checks below.
3. **Schedule settings and initial setup.** `PUT /settings` and `GET /settings/schedule-status`: Admin access, revisions, timezone rules and scheduled execution integration. Saving settings alone does not prove a refresh will run.
4. **Plant filter.** Facility/generator choice endpoints: exact IDs, date bounds, role checks and publication-bound pagination. Reuse preview infrastructure.
5. **Failed-run recovery.** Rerun and warning resolution: revisions, atomic admission, preserved history and existing candidate retry/discard behavior.

Frontend implementation, dependency installation and live activation remain separate work. Dashboard planning does not remove setup/publication prerequisites for a retained-user demonstration.

## LLM

### Reuse and bounded scope

Paths here are relative to `backend/src/trinity/`.

| Existing source | Reuse or extension |
|---|---|
| `catalog/service.py:get_catalog` | Safe publication/latest-refresh metadata patterns. Pin dashboard freshness and data identity in one consistent metadata snapshot. |
| `queries/service.py:PreviewService.prepare` | Identity checks, authorized publication pinning, shared rate/capacity admission and short metadata transactions. Do not call the public preview route internally or submit generated SQL through the user SQL endpoint. |
| `queries/client.py`, `queries/staging.py`, `queries/config.py` | Trusted staging, checksums, isolated execution, deadlines, safe errors and confirmed cleanup. No duplicate storage layer or in-process analytical fallback. |
| `contracts/queries.py`, `queries/runtime/preview.py:execute_preview` | Closed typed operations and national-only mounted files. Design the smallest explicit operation extension for dashboard and metric reads. |
| `catalog/schemas.py`, `auth/schemas.py`, `contracts/datasets.py` | Existing publication, freshness, diagnostic and source-column definitions. Keep the selected feature structure; exact file placement belongs in design. |

No production dependency or migration is proposed. Verify any need during design. Keep source `percentOutage` separate from calculated share. Calculate `100 × outage / capacity` with decimal arithmetic and half-up rounding to two displayed places. Preserve signed/out-of-range values. Zero capacity gives a null metric with `zero_capacity`, while source MW remains available. Never average percentages or pool dates. Display gap points are not stored analytical observations.

Apply A19 authorization and shared analytical limits. Specify strict query parsing and rate-debit ordering explicitly, using preview's accepted patterns where applicable. Dashboard custom dates require both bounds, unlike preview. Require `summary == days[-1]`, including a missing end date. National endpoints expose national diagnostics only.

### Verification plan

| Layer | Evidence required |
|---|---|
| Offline contracts/calculation | Default/preset/custom dates, leap years, 366-day bound, malformed/duplicate/unknown fields, missing dates, zero capacity versus zero outage, signed/out-of-range values, exact rounding, summary equality and metric/dashboard agreement. |
| Database and HTTP | All personas, expired sessions, no publication, safe diagnostics/freshness, failed refresh with old publication retained, publication changes and shared admission with SQL/preview. |
| Real isolated runtime | Exact national Parquet values; only authorized mounts; no network/secrets; deadline/output/memory failures; stop confirmation and capacity recovery. Reuse existing regressions and add dashboard-specific cases. |
| Frontend integration later | Latest versus historical cards, matching publications, previous calendar-day gaps, complete facility pagination before ranking, Viewer detail denial and out-of-range meter presentation without changing values. |
| Retained-user acceptance | Alayala exercises both routes against a legitimately published version and configured runtime. Disposable fixtures do not prove this gate. |

### Current evidence and limits

`rg -n '@router\.' backend/src/trinity` lists auth, read-only settings, catalog, SQL/preview, refresh runs and candidate actions. No dashboard or metric handler appears. `main.py:create_app` registers those routers and defaults preview execution to disabled. `queries/config.py:preview_execution_factory` returns `503 dependency_unavailable` when disabled.

Facility preview is implemented; retained deployment readiness was not checked. No database, running service, EIA or S3 request was made. Configured runtime and a valid publication are acceptance dependencies, not permission to fabricate state or weaken the gate.

Done: screen/data mapping and dashboard-first backend proposal.
Pending: scope review and dashboard specification.
Blocker: none for planning; retained runtime/publication readiness is unverified.
