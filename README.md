# Trinity — Arkham Outage Explorer

Trinity is the selected product name for the Arkham Outage Explorer challenge. It will let users explore U.S. nuclear outage data persisted in application-owned storage, without fetching live EIA data for each analytical request. A14 records alayala's interpretation of “locally.”

**Status: data contract specified; implementation pending, October 3, 2026.** This repository imports the selected October 1–2 planning and evidence documents from Obsidian. The originals remain unchanged. Local CSV checks support the initial findings. There is no runnable application in this documentation set.

Current handoff: [backend structure accepted](ai/sessions/2026-10-03-backend-structure-accepted.md), following the [stack review and correction](ai/sessions/2026-10-03-backend-stack-review-and-layout.md#author-correction-and-accepted-stack). [docs/schema.md](docs/schema.md) and A9 remain canonical for data/publication behavior; [docs/backend.md](docs/backend.md) records A15's accepted file structure and responsibility boundaries. Use the [application field guide](docs/application-model-guide.md) for the discussion explanations. A10–A14 select Python, FastAPI, Psycopg 3, Alembic, PyArrow, datafusion-python, SQLGlot, and application-owned S3 storage. Continue on `docs/backend-decisions-architecture`. Next: review the completed API field specification under approved A16 and settle remaining detailed security rules; A17 dependency versions and A18 staged SQL scope remain accepted. Maintain data evidence — ongoing; see [FINDINGS.md](FINDINGS.md).

Dependency versions are accepted under [A17](DECISIONS.md#a17--dependency-versions-and-update-policy-closed), including the exact release table and locked installation policy. Compatibility verification is pending. [A16](docs/api-security.md) records the approved API flow and expanded request/response contract; detailed authentication and SQL implementation rules remain separately marked. [OpenAPI](docs/openapi.json) defines all 20 HTTP operations. [A18](DECISIONS.md#a18--sql-scope-by-stage-closed) accepts the staged SQL scope; detailed grammar and the aggregate-function allowlist remain under review.

## Intended behavior

| Role | Access |
|---|---|
| Viewer | National trends only. No facility or generator detail through any product path. |
| Analyst | All analytical datasets, filtered previews, and permitted read-only SQL. |
| Admin | Analyst access, manual refresh, shared settings, and candidate review, warning recovery and approval when validated data has review warnings. |

Scheduled refreshes and manual Admin refreshes use the same validation process. Initial account setup runs once for the shared account. The schedule defaults to daily, with an Admin-selected time and timezone. After required validation, warning-free candidates publish automatically; candidates with review warnings need Admin approval. Publication policy is fixed. Admins can change the daily schedule. Required failures/incomplete checks block publication. One lifecycle is admitted at a time; pending review and unresolved failures block new work until the approved recovery action.

## Selected architecture direction

| Component | Responsibility |
|---|---|
| Connector and PyArrow | Fetch the three EIA routes, validate records, and prepare typed Parquet datasets. |
| Application-owned S3 | Hold immutable data versions and their manifest files under A9/A14. |
| PostgreSQL | Store settings, refresh outcomes, approvals, and the published data version. |
| datafusion-python | Query the permitted published Parquet files. Outage rows are not copied into PostgreSQL for user queries. |
| SQLGlot and backend policy | Inspect SQL structure and enforce the supported grammar and table permissions before analytical reads. |
| BullMQ and Redis | Run the full refresh pipeline in background workers with bounded concurrency; PostgreSQL outbox records preserve dispatch requests. |
| Clerk | Authenticate users; the backend enforces application permissions. |
| Backend and frontend | Enforce access and query rules; provide login, catalog, preview, SQL, and the selected Admin features. |

These are responsibilities, not a deployment diagram. [Data contract v1](docs/schema.md) specifies schemas, validation, immutable versions, and publication invariants. [Backend architecture](docs/backend.md) maps them to the accepted feature-based package and separate query runtime. Frontend, SQL/authentication details, and the concrete deployment remain open. A17 selects dependency versions; compatibility verification remains pending. See [DECISIONS.md](DECISIONS.md), A1–A18.

## Setup, running, and tests

Setup and run commands are not available yet. Do not treat this draft as a runnable submission. Add commands only after they work in the project environment.

| Required README content | Status |
|---|---|
| Prerequisites, configuration, and local startup | Pending implementation and verification. The EIA key must come from an environment variable. |
| Seeded users for Viewer, Analyst, and Admin | Required; not created. Clerk is selected in [A8](DECISIONS.md#a8--clerk-for-authentication-closed); integration remains pending. |
| Automated test command and results | No project tests or test results yet. |
| Connector failures: credentials, network, and bad data | A9 specifies failed-candidate handling and durable recovery obligations. Concrete retry/time limits and their runtime checks remain pending. Preserve the last valid publication. |
| Data reproduction commands and schema diagram | [Analytical and application ER diagrams](docs/schema.md) are specified. Historical source exports and scripts are still absent, so findings are not yet reproducible from a clean clone. |

## Documents required by Arkham

| File | Purpose |
|---|---|
| [README.md](README.md) | Setup, users, architecture, assumptions, limits, and document index. |
| [DECISIONS.md](DECISIONS.md) | Accepted choices, alternatives, reasons, and unresolved required topics. |
| [FINDINGS.md](FINDINGS.md) | Reconciliation, real anomalies, and reproducible evidence. |
| [NOTES.md](NOTES.md) | Engineering Notes: human/AI contributions, AI errors, and verification. Arkham also permits these notes inside README. |

## Documents selected by alayala

| File | Purpose |
|---|---|
| [PRODUCT.md](PRODUCT.md) | One-page product scope and selected additions. |
| [AGENTS.md](AGENTS.md) | Shared AI working instructions. |
| [CLAUDE.md](CLAUDE.md) | Entry point to the same shared instructions. |
| [docs/schema.md](docs/schema.md) | Finalized v1 data contract, validation checks, logical fields, and analytical/application ER diagrams. |
| [docs/backend.md](docs/backend.md) | Accepted backend file structure, process boundaries, transaction ownership, validation/recovery responsibilities, and pending contracts. |
| [docs/api-security.md](docs/api-security.md) | Approved A16 human flow, detailed requests/responses/errors and separately marked security proposals; A17 versions and A18 staged SQL scope remain independent. |
| [docs/openapi.json](docs/openapi.json) | Machine-readable HTTP schemas for all 20 approved API operations; not implemented endpoints. |
| [Application model field guide](docs/application-model-guide.md) | Why the application fields exist; reconciled explanations from the Obsidian discussion. |
| [A4 session](ai/sessions/2026-10-02-a4-state-and-outage-queries.md) and [document session](ai/sessions/2026-10-02-document-baseline.md) | Evidence of decisions, contributions, corrections, checks, and handoff. |

## Assumptions and limits

One shared application/account is in scope. There is no selected multi-organization or registration flow. Selecting DataFusion does not select Rust. The business guide's hypothetical examples are not EIA findings.

The final submission still needs source code, automated tests, `.env.example`, implemented migrations, and self-contained data reproduction. The entity-relationship diagrams are now specified in the data contract. The initial commits import existing documents by topic; they do not represent implementation work. Future commits must record verified work incrementally, without squashing or rewriting history.

The private repository is `alejandroayalad/trinity`. `EIA API KEY.md`, `First Aproximation.md`, and `IMPLEMENTATION BEFORE.md` are excluded. The challenge PDF, business guide, original analysis scripts, and bulk exports remain local. References to these items identify historical sources, not included artifacts. Historical session checks have not been rerun by this import.

Source: `Software Engineer - Technical Challenge.pdf`, pages 2–8, plus the accepted decisions in this folder.

## Delivery structure and slices

Keep required documents at the root, the data contract in `docs/schema.md`, backend architecture in `docs/backend.md`, and supporting records in `ai/sessions/`. A15 selects the feature tree in `backend/src/trinity/`, with backend migrations and tests beside `src/`. It includes the connector and separate API, worker, and query-runtime entrypoints. This supersedes the earlier tentative top-level connector grouping. `frontend/` remains separate; add supporting scripts only when needed. The selected tree is documented, not yet implemented. Empty implementation folders and unverified run commands are not included.

1. **Maintain data evidence — ongoing.** Extend findings and preserve reproducible evidence throughout delivery.
2. Import selected documentation in focused commits with actual commit timestamps and original work dates in the records.
3. Implement against A9's data, validation, and publication contract. Close the SQL and authentication implementation contracts before building those paths.
4. Implement and verify working slices: extraction/model/metric, authenticated catalog and preview, restricted SQL, refresh/publication/settings, and the complete interface. Update relevant decisions, findings, and Engineering Notes with each slice.
5. Verify a clean checkout using the README, test all three personas, reproduce findings, and rehearse the live explanation before submission.
