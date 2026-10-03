# Trinity — Arkham Outage Explorer

Trinity is the selected product name for the Arkham Outage Explorer challenge. It will let users explore U.S. nuclear outage data persisted in application-owned storage, without fetching live EIA data for each analytical request. A14 records alayala's interpretation of “locally.”

**Status: minimum Python scaffold implemented; product features pending, October 3, 2026.** This repository imports the selected October 1–2 planning and evidence documents from Obsidian. The originals remain unchanged. Local CSV checks support the initial findings. The backend now has a FastAPI health endpoint and smoke tests. The outage explorer is not yet implemented.

Current handoff: [backend structure accepted](ai/sessions/2026-10-03-backend-structure-accepted.md), following the [stack review and correction](ai/sessions/2026-10-03-backend-stack-review-and-layout.md#author-correction-and-accepted-stack). [docs/schema.md](docs/schema.md) and A9 remain canonical for data/publication behavior; [docs/backend.md](docs/backend.md) records A15's accepted file structure and responsibility boundaries. Use the [application field guide](docs/application-model-guide.md) for the discussion explanations. A10–A14 select Python, FastAPI, Psycopg 3, Alembic, PyArrow, datafusion-python, SQLGlot, and application-owned S3 storage. The [minimum Python scaffold](backend/README.md) starts the implementation. Next: implement the connector and typed Parquet pipeline; A16 API flow, A17 dependencies and A18 staged SQL scope remain accepted. Maintain data evidence — ongoing; see [FINDINGS.md](FINDINGS.md).

Dependency versions are accepted under [A17](DECISIONS.md#a17--dependency-versions-and-update-policy-closed), including the exact release table and locked installation policy. Compatibility verification is pending. [A16](docs/api-contract.md) records the approved API flow and expanded request/response contract; [A19 security contract](docs/security-contract.md) records accepted authentication, SQL, container isolation, admission and limits. [OpenAPI](docs/openapi.json) defines all 20 HTTP operations. [A18](DECISIONS.md#a18--sql-scope-by-stage-closed) accepts the staged SQL scope; A19 selects the function list and arithmetic/CASE; parser/engine verification remains pending.

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

These are responsibilities, not a deployment diagram. [Data contract v1](docs/schema.md) specifies schemas, validation, immutable versions, and publication invariants. [Backend architecture](docs/backend.md) maps them to the accepted feature-based package and separate query runtime. Docker Compose is selected for local execution; frontend and public hosting remain open. Exact security implementation and verification remain pending. A17 selects dependency versions; compatibility verification remains pending. See [DECISIONS.md](DECISIONS.md), A1–A19.

## Setup, running, and tests

The selected local execution target is Docker Compose; no Compose configuration exists yet. The supplied challenge requires local execution (page 7) and a repository link (page 8), not a public application URL. AWS/hosting remains undecided. See the [source review](ai/sessions/2026-10-03-security-contract-and-api-split.md#challenge-delivery-evidence).

The minimum backend setup is documented in [backend/README.md](backend/README.md). It exposes only `GET /health`; this is not a complete challenge submission.

With CPython 3.14.8 and uv 0.12.23 installed:

```bash
cd backend
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
uv run --locked uvicorn trinity.main:app --host 127.0.0.1 --port 8000
```

The health response is `{"status":"ok"}`. It reports process liveness, not data readiness. The health endpoint requires no EIA key, login, database, Redis or S3 connection. Trusted connector code can call `trinity.config.load_eia_settings()` to read `EIA_API_KEY` from the process environment; see [EIA configuration](backend/README.md#eia-configuration).

| Required README content | Status |
|---|---|
| Prerequisites, configuration, and local startup | Backend dependency resolution and locked installation verified; full application/Compose startup remains pending. `backend/.env.example` documents the environment-based EIA key loader. |
| Seeded users for Viewer, Analyst, and Admin | Required; not created. Clerk is selected in [A8](DECISIONS.md#a8--clerk-for-authentication-closed); integration remains pending. |
| Automated test command and results | Six health/configuration tests passed on CPython 3.14.8; product acceptance tests remain pending. |
| Connector failures: credentials, network, and bad data | A9 specifies failed-candidate handling and durable recovery obligations. A19 selects three total attempts for temporary external failures with one- and three-second waits within the operation deadline; denied access, invalid SQL and failed validation are not retried. Refresh-stage deadlines and runtime checks remain pending. Preserve the last valid publication. |
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
| [docs/api-contract.md](docs/api-contract.md) | Approved A16 human flow, endpoint requests/responses/errors, pagination and recovery; security rules are maintained separately. |
| [docs/security-contract.md](docs/security-contract.md) | Accepted A19 roles, SQL policy, container/S3 boundaries, admission, limits, retry rules and required verification. |
| [docs/openapi.json](docs/openapi.json) | Machine-readable HTTP schemas for all 20 approved API operations; not implemented endpoints. |
| [Application model field guide](docs/application-model-guide.md) | Why the application fields exist; reconciled explanations from the Obsidian discussion. |
| [A4 session](ai/sessions/2026-10-02-a4-state-and-outage-queries.md) and [document session](ai/sessions/2026-10-02-document-baseline.md) | Evidence of decisions, contributions, corrections, checks, and handoff. |

## Assumptions and limits

One shared application/account is in scope. There is no selected multi-organization or registration flow. Selecting DataFusion does not select Rust. The business guide's hypothetical examples are not EIA findings.

The scaffold includes package metadata, a dependency lockfile, a health endpoint, an environment-based EIA key loader, six tests and `backend/.env.example`. The final submission still needs product source code, acceptance tests, implemented migrations, and self-contained data reproduction. The entity-relationship diagrams are now specified in the data contract. The initial commits import existing documents by topic; they do not represent implementation work. Future commits must record verified work incrementally, without squashing or rewriting history.

The private repository is `alejandroayalad/trinity`. `EIA API KEY.md`, `First Aproximation.md`, and `IMPLEMENTATION BEFORE.md` are excluded. The challenge PDF, business guide, original analysis scripts, and bulk exports remain local. References to these items identify historical sources, not included artifacts. Historical session checks have not been rerun by this import.

Source: `Software Engineer - Technical Challenge.pdf`, pages 2–8, plus the accepted decisions in this folder.

## Delivery structure and slices

Keep required documents at the root, the data contract in `docs/schema.md`, backend architecture in `docs/backend.md`, and supporting records in `ai/sessions/`. A15 selects the feature tree in `backend/src/trinity/`, with backend migrations and tests beside `src/`. It includes the connector and separate API, worker, and query-runtime entrypoints. This supersedes the earlier tentative top-level connector grouping. `frontend/` remains separate; add supporting scripts only when needed. Only the package root and API entrypoint are implemented so far. Add feature files as their behavior is implemented; the remaining selected tree is the roadmap.

1. **Maintain data evidence — ongoing.** Extend findings and preserve reproducible evidence throughout delivery.
2. Import selected documentation in focused commits with actual commit timestamps and original work dates in the records.
3. Implement against A9's data, validation, and publication contract. Implement A19 security boundaries and verify them locally before enabling untrusted queries.
4. Implement and verify working slices: extraction/model/metric, authenticated catalog and preview, restricted SQL, refresh/publication/settings, and the complete interface. Update relevant decisions, findings, and Engineering Notes with each slice.
5. Verify a clean checkout using the README, test all three personas, reproduce findings, and rehearse the live explanation before submission.
