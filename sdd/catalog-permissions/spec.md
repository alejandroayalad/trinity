# Specification: Catalog and permissions

Date: 2026-10-04
Status: Implemented October 4, 2026 under alayala's explicit implementation request. Offline and real PostgreSQL/HTTP evidence are recorded separately in the [implementation session](../../ai/sessions/2026-10-04-catalog-permissions-implementation.md). Alayala's retained-account Docker operator check passed with no active publication; see [operator evidence](../../ai/sessions/2026-10-04-catalog-docker-operator-check.md). Frontend checks remain pending.
Branch: `feat/catalog-permissions`
Basis: [proposal](proposal.md), [API contract](../../docs/api-contract.md), [OpenAPI](../../docs/openapi.json), [security contract](../../docs/security-contract.md), [data contract v1](../../docs/schema.md), and A9/A15–A17/A19–A21 in [DECISIONS.md](../../DECISIONS.md).
Evidence: [specification session](../../ai/sessions/2026-10-04-catalog-permissions-specification.md).

## Human

### Result

An authenticated user can obtain descriptions of the published-data schemas their role permits. Viewer receives national metadata for dashboard support. Analyst and Admin receive metadata for national, facility and generator datasets.

Viewer uses the national dashboard, with cards, daily trends and national table values. Catalog and SQL navigation remain Analyst/Admin features. Keeping Viewer metadata API access does not add a Viewer Catalog button. The frontend is a later slice.

Input: a valid local session on `GET /api/v1/catalog`, with no parameters or request body. Flow: verify current identity and role → select permitted definitions → read publication and safe refresh state from one database snapshot → return metadata. Output includes columns, units, daily keys, available filter names, the national metric definition and freshness; it includes no outage rows.

Before any publication, the same definitions remain available with `data_ready=false` and `publication=null`. A candidate in storage does not count as published data. A database failure returns an error instead of pretending there is no publication.

### Failure example and review detail

An Analyst signs in, then their stored role changes to Viewer. Their next catalog request must contain only `national_outages`, using the same token. A hidden Catalog button alone would not enforce that boundary; the API must check the current role.

**Accepted freshness rule:** `last_refresh` means the run with the greatest `run_seq`, including an unfinished or failed run. This keeps the newest refresh attempt visible while the older valid publication remains usable. It does not mean “last successful publication.” D01 below links the accepted decision.

## LLM

### Requirements

The canonical contracts remain authoritative. The field inventories below make the catalog slice testable without changing their schemas. Requirement IDs are local to this slice.

| ID | Required behavior |
|---|---|
| R01 | Add only `GET /api/v1/catalog` for this slice. Return HTTP 200 with `CatalogResponse` on success. Accept no query parameters or nonempty request body; preserve the existing bounded transport and safe errors. Client role, actor, dataset, version and storage-path selections are not supported inputs. |
| R02 | Resolve the current active account, valid session and trusted stored role on every request through the existing authentication contract. Require `catalog:read` before protected catalog-state reads. Missing/unknown roles grant no access. Do not cache role or session authority. |
| R03 | Apply the existing shared dataset policy. Viewer receives exactly one definition, `national_outages`; Analyst/Admin receive exactly all three canonical definitions. Return no duplicate definitions or hidden-dataset placeholders. Preserve public/internal key mapping as defined below. |
| R04 | Derive column names, order, nullability and daily keys from `contracts/datasets.py`, consistent with A9. Map Arrow types to the public `Column` types. Add human-readable labels, descriptions, units and supported filter names without maintaining a conflicting second analytical schema. |
| R05 | Return exactly one national `offline_share_percent` metric definition for all three roles. Preserve source `percentOutage` as a separate column. Return no calculated metric value, outage rows, sample records or entity-choice values. |
| R06 | Build a closed `CatalogResponse` with exactly the contract fields and bounded nested objects. No admin context, actor details, diagnostics, storage addresses or extra capability fields are included. Preserve exact wire casing and required null fields. |
| R07 | Resolve the active publication once per request from trusted PostgreSQL state. `data_ready` is true exactly when that snapshot contains a valid active publication. No active publication is a successful metadata response, independent of setup, refresh activity or candidate storage. Broken publication state is a dependency failure. |
| R08 | Identity, publication, readiness and refresh metadata describe one consistent database snapshot. A concurrent publication or refresh update must not mix IDs, dates or states from different snapshots within a response. A later request may observe the new state. |
| R09 | Return freshness only through the closed projection below. Publication-derived dates exactly match the returned publication or are null with no publication. Apply D01's accepted run-selection rule; never substitute last-successful-publication status for current refresh status. |
| R10 | Preserve Viewer privacy throughout the entire response and error path. Viewer receives no facility/generator schema, filter, label, count, raw diagnostic, candidate ID, actor ID or run error detail. The limited global refresh status/times and active publication/version identifiers explicitly allowed by OpenAPI remain permitted. |
| R11 | Return canonical safe problems, correlation headers and `Cache-Control: no-store` on success and failure. Reject invalid requests without echoing submitted values. Errors and captured logs contain no tokens, credentials, hidden schemas, storage paths, connection strings or internal traces. |
| R12 | Read static definitions and permitted application metadata only. Perform no EIA/S3/manifest/Parquet access, DataFusion execution, query-container launch or analytical-slot reservation. Make no application-state mutation, migration, account provisioning, refresh or publication action. |
| R13 | Reuse existing bounded database/authentication behavior and selected dependencies. Preserve health, login/logout, `/me`, settings and shared permission behavior. Do not require an EIA key, S3 credentials, Docker or Redis for catalog runtime. Static Python imports are not evidence of external I/O. |
| R14 | Preserve the accepted dashboard-only Viewer navigation boundary without implementing frontend work here. `catalog:read` and `preview:national` remain Viewer API capabilities; Catalog/SQL navigation and direct-screen access checks belong to later frontend acceptance. |
| R15 | Prove catalog behavior through the real production route and serialized response, not only permission helpers. Separate offline tests, real PostgreSQL/HTTP evidence, operator checks and later frontend/query-isolation evidence. Synthetic publication fixtures are test data, not permission to publish live data. |

### Endpoint and response

The OpenAPI operation is `/catalog` under the existing `/api/v1` base path. It defines no body, parameters, pagination, client-selected history or mutation. No catalog-detail endpoint is added.

| Response field | Required value |
|---|---|
| `datasets` | Exactly the role-permitted definitions from the matrix below. Each has only `key`, `label`, `description`, `daily_key`, `columns`, `available_filters`. |
| `metrics` | One `MetricDefinition` for the national calculated metric, whether or not data is published. |
| `data_ready` | Boolean derived from the active publication in this request's snapshot. |
| `publication` | Null, or exactly `publication_event_id`, `version_id`, `published_at`, `coverage_start`, `coverage_end`, `latest_observation_date`. IDs are UUID strings, observation dates are calendar dates, and timestamps are UTC strings ending in `Z`. |
| `freshness` | Exactly `latest_observation_date`, `published_at`, and `last_refresh`, including explicit nulls where required. |

Successful output is JSON. A request returns the complete role-permitted metadata or an error; it must not return HTTP 200 with missing definitions after a registry or state failure. OpenAPI size bounds apply, including up to three datasets, seven columns per dataset, three daily-key fields, four filter names, one metric, and 512 characters per dataset label/description or metric label. Do not add precision/scale fields to public `Column`; A9 still governs the stored decimal type.

### Dataset matrix and canonical metadata

| Internal policy/registry key | Public `Dataset.key` | Roles | Ordered daily key | Available filters |
|---|---|---|---|---|
| `national` | `national_outages` | Viewer, Analyst, Admin | `period` | `start`, `end` |
| `facility` | `facility_outages` | Analyst, Admin | `period`, `facility` | `start`, `end`, `facility` |
| `generator` | `generator_outages` | Analyst, Admin | `period`, `facility`, `generator` | `start`, `end`, `facility`, `generator` |

Use the existing `DatasetDefinition.table_name` to connect internal keys and public names. Neither short internal aliases nor PostgreSQL table names are extra public datasets. Client input cannot change this mapping. Present datasets in national → facility → generator order after permission filtering; this specification selects that stable presentation order without adding a new API field.

Ordered columns must match the canonical schema:

| Dataset | Column order |
|---|---|
| `national_outages` | `period`, `capacity`, `outage`, `percentOutage` |
| `facility_outages` | `period`, `facility`, `facilityName`, `capacity`, `outage`, `percentOutage` |
| `generator_outages` | `period`, `facility`, `generator`, `facilityName`, `capacity`, `outage`, `percentOutage` |

| Column | Public type | Nullable | Unit |
|---|---|---|---|
| `period` | `date` | false | null |
| `facility`, `generator` | `string` | false | null |
| `facilityName` | `string` | true | null |
| `capacity`, `outage` | `decimal` | false | `MW` |
| `percentOutage` | `decimal` | true | `percent` |

Each `Column` has exactly `name`, `type`, `nullable`, and `unit`. Include applicable optional columns even before publication or when source values would all be null. Describe identifiers as strings, preserving leading zeros; generator identity is scoped to its facility. Labels/descriptions must identify the dataset's grain in plain language and must not contain paths or hidden-dataset details. Exact display wording is not a separate business decision.

Available filters describe later preview inputs; they do not accept filters on the catalog endpoint, return entity lists, or prove preview implementation. Generator filtering later requires a facility, as already defined by the API contract.

### Metric definition

| Field | Value or meaning |
|---|---|
| `key` | `offline_share_percent` |
| `label` | A bounded human-readable national offline-share label. |
| `unit` | `percent` |
| `formula` | Text describing `100 × outage / capacity` for the national row on one date. This is display metadata, never executable user input. |
| `null_reasons` | `not_reported`, `zero_capacity` |
| `display_decimal_places` | 2 |

Keep A9's decimal calculation and half-up display rounding semantics. Catalog describes these semantics without executing them. Do not average source percentages or present missing observations as zero. No metric `value` or row is returned by this endpoint.

### Publication, freshness and failure states

An existing empty `active_publication` pointer is the no-publication state. A missing required pointer row or an active reference that cannot resolve to a valid publication/version/run is inconsistent state. The existing publication reader is the baseline; the catalog must not bypass its checks or infer readiness from stored files or the latest refresh run.

`freshness.latest_observation_date` and `freshness.published_at` equal the corresponding `publication` fields. With no publication, both are null. No independently computed “latest” source date may replace those values.

`last_refresh` is null only when the snapshot contains no refresh run. Otherwise it contains exactly `status`, `requested_at`, and nullable `finished_at`. Use canonical `RunStatus` values and recorded UTC timestamps. Do not infer finish times or expose `run_seq`, run IDs, requester IDs, errors, candidates, approvals or warnings. A run lookup failure is an error, not null.

**D01 — accepted with specification approval, October 4, 2026:** choose the run with the greatest `run_seq` visible in the snapshot, regardless of status. The sequence is the existing ordering used by refresh history; timestamps and completion status do not override it. No runs means null. [A16's catalog freshness refinement](../../DECISIONS.md#a16--approved-api-flow-and-detailed-contract) is the canonical decision record. Earlier proposed status remains in the specification session history.

| Snapshot state | Readiness and freshness result |
|---|---|
| Empty active pointer; no refresh runs | `data_ready=false`, `publication=null`; all three freshness values null. |
| Empty active pointer; latest run running, awaiting approval or failed | Same false/null readiness and null publication dates; expose only that run's allowed status/times under D01. |
| Valid active publication; newer run unfinished or failed | `data_ready=true`; retain active publication and its dates; `last_refresh` describes the newer run under D01. |
| Stored/validated candidate without an active publication | Remain false/null; candidate metadata does not appear. |
| Missing/broken active pointer, unreadable state or invalid required persisted metadata | Safe dependency failure; no partial successful catalog. |

No `409 data_unavailable` is returned merely because catalog data is not published. That behavior belongs to analytical reads; catalog definitions remain useful before publication. Separate calls to `/me` and `/catalog` may see different publications after a real change; consistency is required within each request, not across separate requests.

### Errors and bounded work

| Trigger | Required outcome |
|---|---|
| Well-formed request with no authorization | `401 authentication_required`; no protected catalog-state read. |
| Malformed, unknown, expired or revoked session; inactive account | `401 invalid_session`; no protected catalog-state read. |
| Missing/unknown stored role or absent required capability | `403 forbidden`; no protected catalog-state read. |
| Nonempty query string or GET body within transport bounds | `422 invalid_request`; no catalog work. This includes `role`, `actor`, `dataset`, `version`, `cursor` and path-like inputs. |
| Body exceeds 65,536 bytes | Existing `413 request_too_large`; streamed input remains bounded. |
| Authentication storage/pool unavailable | Existing `503 auth_unavailable`; no successful fallback response. |
| Authorized publication/freshness read fails or required state is inconsistent | `503 dependency_unavailable`; no fake empty state or partial success. Preserve safe existing infrastructure error behavior where failure occurs before authentication completes. |
| Unexpected internal failure, including malformed static metadata | Safe `500 internal_error`; no raw exception or successful incomplete response. |

Transport rejection may precede authentication, as in the existing application. Combined-invalid-input tests must not require a different precedence. All failures use canonical `Problem` fields, `application/problem+json`, `X-Request-ID` and `Cache-Control: no-store`. A 401 includes `WWW-Authenticate: Bearer`. Catalog failures expose no Admin blocker details or hidden identifiers in error fields. Preserve existing body timeout and database bounds; do not add retries or unbounded work to mask a failure.

Analytical output caps, query admission and container limits remain later execution requirements, not catalog machinery. Catalog does not reserve analytical slots or perform analytical reads. This does not waive existing general API transport/authentication protections or select a new rate-limit policy.

### Acceptance scenarios

All scenarios below are required evidence for implementation unless explicitly marked as later frontend work. They are specifications, not recorded test results. Ranges in the requirement column include each requirement in the range.

| ID | Scenario | Expected result | Requirements |
|---|---|---|---|
| S01 | Each persona calls the real catalog route before publication | 200; exact role dataset set, one national metric and false/null readiness. | R01–R07 |
| S02 | Each persona calls with a valid active publication | 200; canonical public keys, valid publication and matching freshness dates. | R03–R09 |
| S03 | Compare all returned definitions to A9 and `DATASETS` | Exact column order/type/nullability/units, daily keys and allowed filter names; internal keys do not replace public names. | R03–R06 |
| S04 | Inspect Viewer JSON with detailed candidate/error fixtures present | No detailed schema/filter/label/count/diagnostic or candidate/actor/error leakage anywhere in the response. | R06, R10 |
| S05 | Missing authorization, malformed token, unknown token | Expected 401 code and challenge; spies prove catalog state is not read. | R02, R11 |
| S06 | Expire/revoke the session or deactivate the account between requests | Next request denied; no stale cached authority. | R02, R11 |
| S07 | Change Analyst to Viewer, then Viewer to Analyst, using retained session | Each next request matches the current role; prior metadata response is not reused. | R02, R03, R10 |
| S08 | Resolver encounters missing/unknown role | 403 before catalog-state reads; no permissive fallback. Use a focused resolver fixture if database constraints prevent storing that state. | R02, R03 |
| S09 | Supply role/actor/dataset/version/path parameters or a nonempty GET body | Safe 422; no echoed inputs, expanded access or protected catalog work. Oversized bodies remain 413. | R01, R11 |
| S10 | Empty pointer with no runs, then with running/review/failed run fixtures | Correct false/null readiness; null publication dates; safe refresh status/times only. | R07, R09 |
| S11 | Higher run sequence has older timestamps or is unfinished/failed | Under D01, select highest sequence; do not select by latest timestamp, finish time or success. | R09 |
| S12 | Older publication remains active while newest run fails | Published data remains ready; publication dates unchanged; latest refresh reports failure safely. | R07–R10 |
| S13 | Validated/stored candidate exists but no active publication | No readiness, candidate leakage, manifest lookup or file download. | R07, R10, R12 |
| S14 | Delete required pointer row or inject a broken active reference/state | 503 dependency failure; never 200 with fabricated no-publication state. | R07, R11 |
| S15 | Auth database unavailable; separately fail an authorized metadata read | Correct safe 503 path, bounded completion, no static-catalog fallback that bypasses auth/state. | R02, R09, R11, R13 |
| S16 | Concurrent connection publishes between reads in one catalog request | One coherent old or new snapshot, never mixed publication IDs/dates/readiness; next request sees committed state. | R07, R08 |
| S17 | Concurrent connection changes latest refresh state between reads | Freshness remains in the request snapshot; no mixed run fields or substituted publication dates. | R08, R09 |
| S18 | Validate complete successful and failed HTTP bodies/headers | Closed OpenAPI objects, required nulls, UUID/date/UTC formats, field bounds, no-store and request IDs; 401 challenge. | R05, R06, R11 |
| S19 | Inject secret/path/hidden-dataset canaries into exceptions and forbidden metadata | Serialized output and captured logs contain no canaries; safe error rather than partial metadata. | R06, R10, R11 |
| S20 | Guard all external/analytical operations to fail on invocation | Catalog works using static definitions and PostgreSQL only; no EIA/S3/Parquet, query slot, container, refresh or publication action. | R12, R13 |
| S21 | Missing static definition, invalid registry metadata or unsupported type mapping | Safe complete failure, not fewer successful definitions or a raw schema exception. | R03–R06, R11 |
| S22 | Regression checks for existing API and permission behavior | Health, login/logout, `/me`, settings and capability counts retain current behavior; no credentials/configuration added for this slice. | R13, R14 |
| S23 | Follow documented setup with three local personas and call catalog over real HTTP/PostgreSQL | Correct role results and evidence for real session/database path; fixture publication remains test-only. | R15 |
| S24 | Later frontend: sign in as Viewer and attempt Catalog/SQL navigation directly | Waiting screen before publication; otherwise national dashboard only. No Catalog/SQL controls or screens; permitted national API support remains available. Not a completion claim for this backend slice. | R14 |

### Verification and review gate

Use the repository's `unittest` workflow for focused catalog/permission/serialization cases, followed by relevant auth regression checks. Use disposable local PostgreSQL and direct HTTP tests for session changes, state failures and publication/refresh races. Offline service doubles cannot prove transaction consistency; policy helpers alone cannot prove HTTP filtering. Operator-owned persona checks remain distinct from AI-run automated evidence.

Implementation and automated tests now exist. The [implementation session](../../ai/sessions/2026-10-04-catalog-permissions-implementation.md) records 16 focused offline catalog tests, 236 passing full-regression offline tests, and the separate 70-check disposable runner (36 database-backed plus 34 offline). No application-state migration or live publication was required. These results do not establish the retained-account operator check or S24 frontend navigation.

The specification and D01 governed implementation. Review the measured evidence, including the completed retained-account operator check. Maintain data evidence — ongoing; this slice creates no new source-data finding.
