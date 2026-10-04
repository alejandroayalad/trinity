# Proposal: Filtered, paginated dataset previews

Date: 2026-10-04
Status: Proposal approved October 4, 2026 when alayala requested the [specification](spec.md). The specification and D01–D03 are approved; [design](design.md)/[tasks](tasks.md) are drafted under the subsequent continuation request. Implementation remains separately authorized.
Inspected branch/HEAD: `feat/catalog-permissions`, `7d2e001`; SQL pairing and other uncommitted work are active in the same checkout and remain outside this change.
Basis: A4, A9, A13–A21 in [DECISIONS.md](../../DECISIONS.md), the [API contract](../../docs/api-contract.md#preview-and-filter-choices), [OpenAPI](../../docs/openapi.json), and [security contract](../../docs/security-contract.md).
Evidence: [proposal session](../../ai/sessions/2026-10-04-dataset-preview-proposal.md).

## Human

### Goal and flow

Return actual published outage records through `GET /api/v1/datasets/{dataset_key}/preview`. Users select a date range and applicable entity IDs, then move through stable pages. This follows the completed catalog metadata slice; catalog success alone does not prove row access or query isolation.

| Persona | Permitted preview data |
|---|---|
| Viewer | `national_outages` only, for dashboard support. No Catalog or SQL navigation is added. |
| Analyst | `national_outages`, `facility_outages`, `generator_outages`. |
| Admin | The same three datasets as Analyst. Admin status does not expand analytical file access beyond the request. |

Input: the existing bearer session, a public dataset key, and only `start`, `end`, `facility`, `generator`, `limit`, `cursor` when applicable. No submitted SQL, storage path, role or historical-version selector is accepted.

1. Verify the current session and role, authorize the dataset, validate the filters and authenticate any cursor before analytical file access.
2. Resolve one active publication, resolve date defaults against it, and verify that a continuation belongs to that publication and the same request settings.
3. Use shared analytical rate/capacity admission and the trusted supervisor to stage only that dataset's published, checksum-verified Parquet files.
4. Execute typed filters and complete-key ordering in a separate DataFusion container with no network or credentials. Collect at most one page plus one lookahead row.
5. Return contract-ordered columns and row arrays, resolved dates, publication metadata and an authenticated next cursor when needed. Confirm execution ended before releasing capacity.

Example request for Analyst/Admin:

```http
GET /api/v1/datasets/generator_outages/preview?start=2026-09-01&end=2026-09-30&facility=46&generator=1&limit=10
```

Expected result: up to ten observed daily records for that exact facility/generator pair, ordered by `(period, facility, generator)`, with the source values preserved. A next cursor exists only if an eleventh matching row exists. This example does not assert that those records are currently published.

Failure example: Viewer requests `facility_outages`, with or without a copied cursor. Return the same safe `404 dataset_not_found` used for an unknown dataset, before downloads or execution. A hidden Catalog button alone cannot enforce this boundary.

### Scope

| Deliverable | Completion boundary |
|---|---|
| Protected preview endpoint | One endpoint for the three published datasets, using existing authentication, capabilities and dataset permissions. Reauthorize every page. |
| Typed filters | Inclusive dates and exact entity IDs; reject unsupported combinations before downloads. Preserve source case and leading zeros. |
| Stable pagination | Complete A9 daily-key ordering, at most `limit + 1` rows collected, authenticated cursors bound to filters and publication, and explicit restart after a publication change. |
| Published-file execution | Reuse the shared A19 staging, DataFusion isolation, admission, deadline and cleanup path. No in-process analytical fallback. |
| Response and evidence | Exact PreviewResponse serialization, safe diagnostics/errors and separate offline, real runtime, and human operator evidence. |

Outside this slice: facility/generator choice-list endpoints, national dashboard cards/aggregates, frontend tables or navigation, user-submitted SQL and its validator, export, arbitrary sorting/column selection, offset pagination, result caching, refresh/publication commands and cloud setup. Exact IDs can be supplied without implementing choice-list endpoints. Preview filters never modify a later SQL request.

### Existing behavior to preserve

| Area | Accepted rule |
|---|---|
| Dates | Default to the 30 calendar dates ending at the latest observation: end is the pinned publication's latest observation date and start is 29 days earlier. If only one bound is absent, use that bound's default. Require ordered bounds spanning at most 366 inclusive dates. Defaults describe a calendar range; missing records are not manufactured. |
| Entity filters | `facility` is supported for facility/generator datasets. `generator` requires `generator_outages` and an exact `facility`. IDs are source strings of 1–128 characters, not empty/whitespace-only. Unknown IDs return an empty matching result, not a registry lookup error. |
| Page size and ordering | Default `limit=100`; range 1–1,000. National sorts by `period`; facility by `(period, facility)`; generator by `(period, facility, generator)`. Source IDs use fixed binary ordering, never numeric conversion. |
| Rows | Include every A9 column in contract order. Preserve decimals as exact strings, dates as ISO date strings and missing optional values as null. Preserve signed/out-of-range published observations and source `percentOutage`; do not substitute the calculated national metric. |
| Empty versus unavailable | No matching observations returns 200 with empty rows and `reason=not_reported`; no active publication returns `409 data_unavailable`. A broken publication/file read is an error, not an empty dataset. |
| Publication changes | A request that has pinned a publication finishes against that version. A later page whose cursor names a publication no longer active returns `409 publication_changed`; restart pagination. A newer failed refresh does not invalidate an unchanged active publication. |

### Acceptance examples

| Scenario | Required result |
|---|---|
| Viewer requests national rows; Analyst/Admin request any of the three datasets | Exact allowed data and columns from one published version. No hidden-dataset diagnostics or identifiers leak. |
| Viewer requests facility/generator; anyone requests an unknown dataset | Same `404 dataset_not_found`; no analytical storage access. Invalid/revoked sessions are denied first. |
| Account becomes inactive or Analyst becomes Viewer between pages | Reauthorize the next page; an old cursor cannot retain the previous detail permission. |
| Invalid date, reversed or 367-day range, unsupported filter, invalid page size or nonempty GET body | Contract input error before downloads or container launch. Generator-only filter without facility is invalid. |
| Exact ID contains leading zeros, mixed case or SQL-looking text | Match it as literal text; never renumber, interpolate it into SQL or let it alter the operation. |
| Several entities share one date, with more than one page | Complete daily-key continuation returns every matching row once, in order, without skipping same-day entities. |
| Exactly `limit` matches versus `limit + 1` matches | Null cursor in the first case; an authenticated next cursor in the second. Lookahead never leaks an extra response row. |
| Cursor is altered, oversized, reused for another dataset/purpose, or filters/page size change | Safe input/cursor rejection before downloads; no arbitrary file/version selection or decoded private values in errors. |
| Publication changes during page execution or between requests | Current response remains internally pinned; next continuation returns `publication_changed` and requires restart. |
| No publication, candidate only, missing manifest binding or checksum mismatch | Unavailable/dependency error as applicable; never read candidate files or fetch EIA as a fallback. |
| Unknown entity/date without observations, null optional value, unusual signed value | Preserve the difference between no row, null and the actual source value; never invent zero outage. |
| Capacity/rate limit, storage outage, timeout, memory/output cap or client disconnect | Safe bounded outcome; no partial success. Execution must be confirmed stopped before capacity is released. Unknown termination retains its reservation. |
| Shared runner is unavailable or PostgreSQL admission fails | Fail closed. Do not execute in the API process or evade the shared capacity limit. |

### Recommendation and review gate

Keep preview as a separate SDD slice with one endpoint. Reuse the shared isolated execution foundation being developed for SQL; do not create a second executor or modify the SQL validator in this workstream. Preview uses a server-built typed operation rather than accepting user SQL. Its endpoint may be enabled only after that shared foundation passes runtime acceptance.

This proposal preserves existing A16/A19 product choices and introduces no production dependency. Approving it authorizes the detailed specification next. It does not authorize design, code, builds, migrations, publication, cloud actions or commits. The user's SQL pairing gates remain in force for work in the other terminal.

## LLM

### Inspected baseline and integration boundary

| Existing component | Observed responsibility and limit |
|---|---|
| `auth/permissions.py` | Provides `preview:national`, `preview:detail`, current-role capabilities and `require_dataset`. Public table names must map to the existing internal keys `national`, `facility`, `generator`; do not introduce another role matrix. |
| `catalog/registry.py` and `contracts/datasets.py` | Provide public columns/units, Arrow types, available filter names and complete daily keys. Reuse them; catalog definitions are not row-query execution. |
| `publication/repository.read_publication` | Reads one active publication consistently and distinguishes empty from inconsistent state. It does not resolve/stage a fully authorized immutable artifact set. |
| `main.create_app` | Registers health, authentication, settings and catalog. No preview router is registered in the inspected file. |
| `queries/runtime/sql_policy.py`, `queries/policy.py`, `queries/policy_worker.py`, `contracts/queries.py` | SQL work is present and changing in the other terminal. This proposal neither edits those files nor claims their completion or acceptance. Their existence does not establish a preview executor. |
| Catalog operator record | Three retained Docker personas passed metadata checks with no active publication. This cannot establish preview rows or safe analytical execution. |

Absence evidence at inspection: `rg --files backend/src/trinity/queries backend/migrations/versions backend/tests` listed SQL policy scaffolding/tests but no preview implementation/tests, query `client.py`, `runtime/engine.py` or runtime container entrypoint. `main.create_app` contained no preview registration. The two existing migration files contain authentication and app-entry state, but no analytical reservation/rate or artifact-manifest tables. SQL files may change concurrently; recheck this inventory before design/implementation. These are planning dependencies, not reported regressions.

Follow the selected A15 locations: shared query router/service/schemas, supervised client/runtime, and the bounded operation contract. Keep authentication/publication reads in short transactions; do not retain a catalog-style authenticated database snapshot throughout downloads and execution. Trusted code must pin both public publication metadata and the authorized immutable manifest/file identity needed by the runner. No client field can expand that set.

### Contract details for the specification

**Endpoint and transport.** Preserve OpenAPI's `PreviewResponse`: `publication`, `dataset_key`, `range`, `columns`, `rows`, `returned_rows`, `next_cursor`, `reason`, `diagnostics`. No total count, SQL `truncated` flag or invented timing field is added. `returned_rows` equals response row count. Every row matches its ordered columns and nullability. Preserve `X-Request-ID`, `Cache-Control: no-store` and existing Problem responses. Unsupported query parameters and nonempty GET bodies fail. Ensure path validation cannot turn the required unknown/hidden dataset 404 into an enum-validation leak.

**Cursor binding.** Authenticate purpose, dataset, resolved bounds and filters, page size, last complete daily key, and publication ID. Bound cursor input/output to 4,096 characters. The cursor conveys position, not authority. Bind normalized typed request meaning, not raw URL order. Authenticate before trusting decoded fields; compare against the freshly authorized active publication. Validate full key shape and types. Emit the last returned key, not the lookahead key. Continuation must not replace the current active publication with a historical cursor value. Preserve the accepted 422 `invalid_cursor` and 409 `publication_changed` distinctions.

**Typed preview execution.** The runtime receives only a bounded, server-built preview operation and an authorized local-file mapping. Build typed date/string predicates, complete-key continuation, fixed ascending sort and bounded collection. Do not concatenate user values into generated SQL, route preview through the user SQL API, or expose a filter-expression language. The lookahead cap limits collected result rows; it does not assert that the engine scans only `limit + 1` input rows. Query isolation, memory/time and output limits still apply.

**Authorization and diagnostics.** Require the applicable preview capability plus shared dataset permission before analytical reads. Viewer may read only national files and national-safe diagnostics. Do not reuse Admin candidate/error payloads. Diagnostics must belong to the same pinned published state; missing required provenance is not evidence of an empty diagnostic set. Schema/content mismatches fail safely rather than emitting partial rows. No raw paths, credential values, hidden counts, SQL or internal traces appear in public errors.

**Shared execution and limits.** Preserve A19's 30-second budget beginning before trusted downloads, 1 GiB per query container, 5 MiB encoded response, two active requests per user and four across the deployment. Apply the shared analytical per-user rate of 30 per minute; preview pages must not get a separate quota that bypasses SQL's shared budget. Keep preview's own page-size contract. Trusted staging verifies SHA-256 and mounts only requested authorized data read-only in a network-disabled query container with no credentials, application database or Docker control. Relevant temporary external failures get at most three total attempts with one- and three-second waits inside the original deadline; denials and validation failures are not retried. Stop confirmation and reservation ownership/crash recovery are mandatory.

### Details to resolve in later artifacts

| Detail | Required boundary |
|---|---|
| Preview rate debit and error precedence | Reuse shared analytical accounting. The accepted SQL counting boundary is documented for SQL; explicitly specify where malformed preview filters, invalid cursors, no publication and changed publication fall, without silently redefining the SQL rule. |
| Cursor representation and key management | Select bounded canonical encoding, authentication, deployment-stable secret configuration and restart/rotation behavior. If expiry changes user-visible behavior, review that choice in the specification. Never place signing material in the client or repository. |
| Duplicate query parameters and numeric/date coercion | Define deterministic strict handling and tests; do not inherit framework behavior accidentally or accept ambiguous filters. |
| Published artifact/diagnostic provenance | Identify the shared persisted manifest and diagnostic sources, necessary migration ownership and consistent snapshot before downloads. Existing catalog metadata is insufficient. |
| Shared runner readiness | Confirm which approved SQL work supplies staging, admission, runtime messages and container lifecycle. Extend the shared contract only through coordinated design; respect the user's current SQL pairing boundary. |

These are unresolved details, not newly accepted decisions. Link any selected product/security choice to DECISIONS.md at its review gate; avoid duplicating the canonical contract or silently changing OpenAPI.

### Planned verification and delivery stages

1. **Maintain data evidence — ongoing.** Preserve FINDINGS and source values. Synthetic fixtures establish behavior, not new EIA findings or live data completeness.
2. Specify request/permission rules, typed filters, full-key pagination, cursor semantics, serialization and failure cases. Draft design/tasks only after specification approval.
3. Implement and test bounded preview behavior when authorized, integrating with the shared runner rather than bypassing its unfinished controls. Do not enable a runnable analytical endpoint on stubs.
4. Establish real PostgreSQL/HTTP and container evidence for all roles, publication races, isolation, rate/capacity, deadlines, crash recovery and cleanup. Required evidence must pass before endpoint delivery.
5. Let alayala run the local operator check with private passwords against known published data, including a next page and a Viewer detail denial. A publication must be established through a separately authorized flow; never mark a candidate active merely to make this check pass.

Keep three evidence categories distinct:

| Evidence | Must establish | Does not establish |
|---|---|---|
| Offline tests | Filter/cursor/response contracts with synthetic inputs, exact decimals/nulls/IDs, pagination invariants and denied-before-I/O guards. | Real database, HTTP deployment, S3 access or container isolation. |
| Real database/HTTP/runtime tests | Current-role reads, publication pinning/races, shared admission, real DataFusion/Parquet behavior and actual container isolation/termination. Record each component's result; passing database tests alone cannot prove containers. | Retained-account operator success or live EIA/S3 completeness. |
| Local operator check | Alayala's three personas exercise the deployed preview endpoint and pagination over a known publication. | Exhaustive adversarial, crash-recovery or resource-limit coverage. |

No preview tests, runtime commands, migrations or cloud actions run while drafting this proposal. Existing catalog test results remain catalog evidence only.
