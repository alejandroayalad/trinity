# Proposal: Plant and generator filter choices

Date: 2026-10-05
Status: Planning only; separate commit/push authorized, implementation not authorized.
Basis: A9/A13/A15/A16/A19/A20 in [DECISIONS.md](../../DECISIONS.md), [API contract](../../docs/api-contract.md#preview-and-filter-choices), [OpenAPI](../../docs/openapi.json), [preview specification](../dataset-preview/spec.md) and [security contract](../../docs/security-contract.md).
Order: after [Schedule settings](../schedule-settings/proposal.md), before failed-run recovery.

## Human

### Outcome and flow

Analyst/Admin choose a Plant by label while the API receives its exact facility ID. Generator choices depend on a selected facility. Choices come from observations in the selected published date range, not an independent registry or a live EIA request.

| New endpoint, under `/api/v1` | Input | Result |
|---|---|---|
| `GET /datasets/{dataset_key}/facilities` | Session; facility or generator dataset; optional `start`, `end`, `search`, `limit`, `cursor` | `FacilityOptions` containing IDs and nullable names, publication/range and pagination metadata. |
| `GET /datasets/{dataset_key}/generators` | Session; generator dataset; required exact `facility`; optional `start`, `end`, `limit`, `cursor` | `GeneratorOptions` containing facility/generator ID pairs, publication/range and pagination metadata. No generator search parameter is introduced. |

Input → flow → output: authenticate and authorize the detailed dataset → validate input/cursor → pin one publication and resolve dates → reserve shared analytical capacity → stage only authorized verified files → compute distinct choices in isolated DataFusion → return one bounded page with an authenticated continuation.

Example: the label shows `Example Plant (0046)` and the submitted filter is `facility=0046`. Do not convert it to `46`. Selecting generator `1` sends both `facility=0046` and `generator=1` to preview. This is synthetic UI data, not a verified plant identity.

Failure case: a user loads page one, then a new publication becomes active. The continuation returns `409 publication_changed`; the UI clears old choice pages and restarts. A cursor cannot select the old version or preserve permissions after a role change.

### Accepted rules and recommendation

Facilities are available for `facility_outages` and `generator_outages`; generators only for `generator_outages`, with a required facility. Viewer cannot use either route. Unknown/unauthorized datasets use the same safe `404 dataset_not_found` before file access. National data has no Plant filter. Specify the exact unsupported-route errors against OpenAPI without leaking hidden datasets.

Use preview's bounded date defaults: the last 30 dates ending at the pinned latest observation; resolve individually omitted bounds and require an ordered range of at most 366 inclusive dates. Return only entities observed within that range. A missing entity does not establish zero outage, decommissioning or a complete entity registry.

Page size defaults to 50 and caps at 100. Sort by exact source IDs with stable binary ordering; preserve case and leading zeros. Facility labels use the latest non-null name within the requested range, or null. Facility search is a literal case-insensitive substring of ID or name, at most 100 characters; `%` and `_` are ordinary text, not wildcards.

Recommendation: use the existing preview execution infrastructure with dedicated typed choice operations and separate cursor purposes. Distinct IDs, labels and ordering must be computed over all matching observations before page slicing. A preview page's first 100 rows cannot establish a complete choice page.

Changing dataset, date range, search or parent facility starts a new choice request. Changing facility clears any generator selection that no longer belongs to it. These filters affect the table preview only; they never rewrite submitted SQL. Align the frontend details in its separate specification.

## LLM

### Reuse and details to specify

`queries.preview.authorize_preview`, `strict_date` and `source_id` provide existing permission/lexical patterns. `PreviewService.prepare` provides publication pinning and shared rate/capacity admission. `queries.staging`, `queries.client` and `queries.runtime.preview.execute_preview` demonstrate verified-file isolation and typed predicates. Reuse these boundaries; do not derive choices by calling the public SQL endpoint or fetching only one preview page.

`queries.cursors.CursorCodec` currently encodes preview-specific fields and purpose. Reuse its authenticated-envelope approach, not preview tokens unchanged. Choice cursors must bind purpose, dataset, publication, effective bounds, page size, last ID and search/parent facility where applicable. Reauthorize each page and reject tampering/mismatches with `422 invalid_cursor`. Resolve exact encoding, normalization and validation/debit order in the specification.

The generator dataset can contain multiple names for a facility on the same latest date. Specify a deterministic tie-break for that case. Also specify whether name search applies to the displayed latest label or any observed label, and the exact case-insensitive comparison behavior. A16 does not settle these details; do not silently inherit engine defaults. Preserve original source names regardless of display choice.

Read enough to determine whether another distinct option exists, return at most `limit`, and include a cursor only for a further option. A19's SQL output limit must not truncate the rows examined to compute distinct entities or labels. Apply shared analytical rate/capacity, deadline, memory and response limits. No new dependency, entity table or storage layer is proposed.

### Current evidence

Inspect `backend/src/trinity/queries/` and search `rg -n '@router\.|facilities|generators' backend/src/trinity/queries backend/src/trinity/catalog`. The registered analytical handlers are SQL and dataset preview; no facility/generator-choice route exists. Preview filtering already accepts exact IDs. `main.py:create_app` still defaults preview execution off, so implemented reuse is not retained deployment proof.

### Bounded sequence and validation

1. **Maintain data evidence — ongoing.** Preserve source identifiers/names and investigate newly observed inconsistencies through FINDINGS; sample labels are not findings.
2. Specify inputs, labels/search, tie-breaking, empty responses and cursor semantics from the approved wire contract.
3. Design typed runtime operations and cursor-purpose separation within the shared supervisor; no SQL grammar expansion.
4. After separate authorization, implement routes and focused tests, then run real PostgreSQL/HTTP/Parquet/container checks.
5. Verify the UI restarts on publication/filter changes and retained Analyst/Admin access works; Viewer direct calls must fail before detailed reads.

| Checks to specify | Concrete coverage |
|---|---|
| Identity and role | Exact IDs with leading zeros; same generator ID under different facilities; Viewer, revoked session and changed role; no protected I/O on denial. |
| Names/search | Latest non-null name, all-null names, same-day conflicting names, literal wildcard characters, case handling, maximum/invalid search and unsupported generator search. |
| Paging and dates | Repeated daily rows produce distinct options; 50/100 limits and lookahead; empty range; full-range label selection; date defaults; tampered/cross-purpose cursor; publication switch. |
| Execution | Authorized files only, shared SQL/preview limits, no partial results on resource failure, cleanup before capacity release and exact OpenAPI response shape. |

Done: source-grounded proposal. Pending: specification and explicit label/search decisions. Blocker: none for planning. No implementation or runtime test is claimed.
