# Proposal: Catalog and permissions

Date: 2026-10-04
Status: Implemented October 4, 2026 under alayala's explicit implementation request. Offline and real PostgreSQL/HTTP evidence are recorded separately in the [implementation session](../../ai/sessions/2026-10-04-catalog-permissions-implementation.md). Alayala's retained-account Docker operator check passed with no active publication; see [operator evidence](../../ai/sessions/2026-10-04-catalog-docker-operator-check.md). Frontend checks remain pending.
Inspected baseline: local `main`, `fde733b`, with unrelated working changes preserved.
Working branch: `feat/catalog-permissions`, created at alayala's subsequent request.
Basis: A9, A15–A17 and A19–A21 in [DECISIONS.md](../../DECISIONS.md).
Evidence: [proposal session](../../ai/sessions/2026-10-04-catalog-permissions-proposal.md).

## Human

### Goal

Let a signed-in user discover the outage datasets their role permits. A Viewer receives national metadata only. An Analyst or Admin receives national, facility and generator metadata. This is the first bounded slice of step 5, “Catalog, preview, SQL.” It completes dataset discovery, not the full Analyst experience.

**Accepted Viewer experience:** the Viewer uses the national dashboard, with summary cards, daily trends and national table values. Show no Catalog or SQL navigation to Viewer. Catalog and SQL navigation belong to Analyst/Admin. Before publication, retain the waiting screen. This navigation choice is recorded in [A16](../../DECISIONS.md#a16--approved-api-flow-and-detailed-contract); frontend implementation remains a later slice.

The Viewer keeps national-only metadata API access so the dashboard can obtain descriptions, units, metric definitions and freshness. `catalog:read` is an API permission, not a requirement to show a Catalog button. Backend checks continue to deny detailed data and SQL independently of navigation.

Metadata describes the data: column names and types, units, daily keys, available filters, the national metric formula, and freshness. The catalog returns no outage rows and performs no analytical calculation.

Input: `GET /api/v1/catalog` with the existing local bearer session, no parameters and no request body.

Flow: verify the current session and stored role → authorize catalog access → select permitted definitions from the existing dataset contract → read publication and safe refresh metadata from one PostgreSQL snapshot → return the catalog.

Output: the existing `CatalogResponse` shape, including permitted datasets, national metric metadata, `data_ready`, `publication`, and `freshness`.

Example: before the first publication, an Analyst catalog API response contains the definitions for `national_outages`, `facility_outages`, and `generator_outages`, with `data_ready=false` and `publication=null`. A Viewer catalog API response contains only `national_outages`; the Viewer interface remains on its waiting screen. Neither response claims that rows are available or requires a visible Catalog page for Viewer.

Failure case: an Analyst's stored role changes to Viewer between requests. Their next catalog request must contain only national metadata, even if the same session token is used. Sending `role=admin` cannot grant access; the endpoint has no role parameter.

### Scope

| Deliverable | Completion boundary |
|---|---|
| Authenticated catalog endpoint | Implement the specified `GET /catalog` operation under the existing `/api/v1` prefix, using current session verification and the shared permission policy. |
| Role-filtered definitions | Viewer receives exactly the national dataset; Analyst and Admin receive exactly all three. Columns, daily keys and types agree with A9 and the existing dataset definitions. |
| Descriptions, units and metric definition | Include allowed filter names and the national `offline_share_percent` definition. Keep source `percentOutage` distinct from the calculated metric. Do not calculate metric values here. |
| Readiness and freshness | Read the active publication once per request. Return permitted static definitions before publication. Expose only contract-listed refresh status/times, without candidate or actor details. |
| Acceptance evidence | Test real catalog HTTP responses for all three personas, invalid sessions, changed roles, safe failures, and consistent publication metadata. |

Outside this slice: preview rows, entity-choice values, dashboard/metric calculations, SQLGlot, DataFusion, query containers, analytical capacity admission, frontend, refresh commands, scheduling, candidate approval and publication writes. Catalog filter names do not mean preview endpoints exist.

Later frontend acceptance must prove that Viewer has no Catalog or SQL navigation and that direct navigation to those screens returns the user to the permitted landing screen. This backend slice verifies the retained national-only catalog API access; it does not claim the navigation has been implemented or tested.

Catalog uses static definitions and PostgreSQL metadata only. It needs no EIA request, S3 download, manifest download or query container. Existing live preparation work remains separate. A stored candidate alone must never make `data_ready` true.

### Acceptance examples

| Scenario | Required result |
|---|---|
| Viewer calls the catalog API, with or without a publication | Exactly `national_outages`; no facility/generator columns, filters, descriptions, counts or diagnostics. National metric metadata remains available for the dashboard, without a Viewer Catalog button. |
| Analyst or Admin, with or without a publication | Exactly `national_outages`, `facility_outages`, and `generator_outages`, with the correct columns, keys, units and allowed filters. |
| No publication; a refresh or unpublished candidate may exist | HTTP 200 with static definitions, `data_ready=false`, `publication=null`, and null publication-derived freshness dates. Existing refresh status/times may still be shown. |
| Active publication changes while a catalog request runs | Readiness, publication and freshness remain consistent with one database snapshot. The next request can observe the new publication. |
| Missing, invalid, expired or revoked session; inactive account or unknown role | Existing safe authentication/authorization failure; no protected catalog state read before authorization. |
| Analyst is downgraded to Viewer | The next request loses all detailed dataset metadata. Client-supplied role or actor fields cannot restore it. |
| Database unavailable or active publication state inconsistent | Safe dependency failure, never a successful empty catalog or false `data_ready=false`. |
| Latest refresh fails while an older publication remains active | Continue reporting the active publication as ready; show only safe refresh status/times, without raw errors or candidate details. |
| Any catalog request | No analytical file access or external source call. Successful and failed authenticated responses retain `Cache-Control: no-store` and safe error handling. |

### Recommendation and review gate

Reuse the implemented authentication, shared permissions, dataset definitions and publication reader. Add the catalog feature at the location already selected by A15. No new production dependency is proposed.

Alayala approved the specification, design/task drafting and then implementation. The [implementation session](../../ai/sessions/2026-10-04-catalog-permissions-implementation.md) records the delivered behavior and automated results; the local operator check remains a separate gate. The original 7:15–8:45 schedule covers the wider step 5 and is not a completion estimate for this proposal.

## LLM

### Verified implementation baseline

These observations describe the inspected pre-implementation baseline. Current implementation and tests are recorded in the linked implementation session:

| Existing component | What the inspected code establishes |
|---|---|
| `create_app` in `backend/src/trinity/main.py` | Registers health, auth and read-only settings routes; no catalog router is registered. |
| `authenticated` and `require_capability` in `backend/src/trinity/auth/dependencies.py` | Resolve a session through `AuthService.authenticated` and apply the shared capability guard before the feature service reads state. |
| `capabilities`, `require` and `require_dataset` in `backend/src/trinity/auth/permissions.py` | All three roles have `catalog:read`; Viewer permits only internal key `national`, while Analyst/Admin permit `national`, `facility`, and `generator`. Unknown roles fail closed. |
| `DATASETS` in `backend/src/trinity/contracts/datasets.py` | Supplies table names, ordered Arrow schemas, nullable fields and daily keys for all three datasets. It does not supply public labels, unit metadata or filter descriptions. |
| `read_publication` in `backend/src/trinity/publication/repository.py` | Reads the active pointer and publication/version/run state. An existing empty pointer returns null; missing or inconsistent state raises `503 dependency_unavailable`. |
| `Database.transaction` in `backend/src/trinity/adapters/postgres.py` | Read-only transactions use repeatable-read isolation. The existing authenticated context shares that connection with feature reads. |

Absence evidence: `rg --files backend/src/trinity backend/tests` listed no `backend/src/trinity/catalog/` package or catalog tests. `rg -n 'catalog' backend/src/trinity backend/tests` found only capability/schema references in auth files. Inspecting `create_app` confirmed no catalog route registration. The expected catalog endpoint is specified but not implemented in the inspected baseline. This is scope discovery, not a runtime defect finding.

`backend/tests/test_auth_unit.py` contains policy-matrix tests over internal dataset keys. `backend/tests/test_auth_postgres.py` contains auth, role-change and publication-snapshot scenarios for existing routes. Those tests do not establish catalog HTTP behavior. Prior recorded test counts are not new results for this proposal.

### Contract boundaries to carry into the specification

The [API contract](../../docs/api-contract.md) and [OpenAPI](../../docs/openapi.json) own response fields and errors. [Data contract v1](../../docs/schema.md) owns analytical types, keys, units and metric meaning. The [security contract](../../docs/security-contract.md) owns role filtering and safe metadata. The [backend structure](../../docs/backend.md) assigns catalog router, service, registry and schemas responsibilities.

**Public versus internal names:** OpenAPI `DatasetKey` uses `national_outages`, `facility_outages`, and `generator_outages`. Existing permission and connector registries use `national`, `facility`, and `generator`. The specification must explicitly connect the existing internal key to `DatasetDefinition.table_name`. Apply the shared dataset policy without introducing a second role matrix or changing public names to internal aliases.

**Navigation versus authorization:** preserve Viewer `catalog:read` and `preview:national` and the existing role matrix. The later frontend must not infer visible Catalog navigation from `catalog:read` alone. A16's accepted Viewer navigation refinement changes no endpoint, wire field or server permission. The specification is approved and design/tasks are drafted; the retained-account local operator check has since passed; frontend verification remains a later gate.

**One source of schema truth:** derive public column names, order, nullability, daily keys and type mapping from `contracts/datasets.py`. Catalog registry content adds labels, descriptions, units, allowed filters and metric metadata; it must not maintain a conflicting second analytical schema. Public `Column.type` uses the OpenAPI values such as `date` and `decimal`, not raw Arrow type strings. Do not add unapproved response fields.

**Safe freshness:** OpenAPI `Freshness` contains `latest_observation_date`, `published_at`, and nullable `last_refresh` with only `status`, `requested_at`, and `finished_at`. Use that bounded projection for every role. Do not reuse or serialize the Admin `read_context` payload, which reads candidate, approval and failure details. Publication-derived dates come from the same publication snapshot used for `data_ready`.

**Freshness detail resolved with specification approval:** `last_refresh` uses the run with greatest `run_seq`, including an unfinished or failed run, consistent with refresh-history ordering. A16 now records this accepted refinement. Keep it distinct from the active publication; earlier proposed wording remains in session history.

**Persistence and testing:** the existing app-entry migration already creates publication and refresh state. Reuse it for this read-only feature unless specification/design discovery proves an additional requirement. Acceptance may seed synthetic state in a disposable test database; this does not authorize writing or publishing production data. No migration or account provisioning runs during proposal drafting.

### Validation boundary and later work

Implementation acceptance must check complete serialized responses against OpenAPI, not just role-policy helpers. Cover both published and unpublished states, live role/session changes, freshness privacy, concurrent publication changes, and denial before protected reads. Use test guards that fail if catalog handling invokes EIA, S3, Parquet reads or analytical execution. Preserve existing auth, `/me`, settings and health behavior with relevant regression checks.

Use the repository's `unittest` workflow, then real local PostgreSQL/HTTP checks for the database and session boundaries. These checks are planned and have not run for this proposal. Passing this slice will establish catalog behavior only; later slices must prove preview/SQL authorization and analytical isolation independently.

Maintain data evidence — ongoing. This metadata-only proposal produces no new outage observation and changes no selected anomaly or publication rule.
