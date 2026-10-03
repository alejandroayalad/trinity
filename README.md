# Trinity — Arkham Outage Explorer

Trinity is the selected product name for the Arkham Outage Explorer challenge. It will let users explore locally stored U.S. nuclear outage data.

**Status: data contract specified; implementation pending, October 3, 2026.** This repository imports the selected October 1–2 planning and evidence documents from Obsidian. The originals remain unchanged. Local CSV checks support the initial findings. There is no runnable application in this documentation set.

Current handoff: [backend selection](ai/sessions/2026-10-03-python-backend-selection.md#database-tools-follow-up), following the [vault reconciliation](ai/sessions/2026-10-03-vault-reconciliation-and-handoff.md). [PR #1](https://github.com/alejandroayalad/trinity/pull/1) merged data contract v1; [docs/schema.md](docs/schema.md) and [A9](DECISIONS.md#a9--data-contract-v1-finalized) remain canonical. Use the [application field guide](docs/application-model-guide.md) for the discussion explanations. [A10](DECISIONS.md#a10--python-for-the-backend-api-and-workers-closed) selects Python for the backend API and workers; [A11](DECISIONS.md#a11--fastapi-for-the-backend-http-api-closed) selects FastAPI; [A12](DECISIONS.md#a12--psycopg-3-and-alembic-for-postgresql-closed) selects Psycopg 3 and Alembic. Continue on `docs/backend-decisions-architecture`. Next: review compatible dependency versions; the API/security contract remains open. Maintain data evidence — ongoing; see [FINDINGS.md](FINDINGS.md).

## Intended behavior

| Role | Access |
|---|---|
| Viewer | National trends only. No facility or generator detail through any product path. |
| Analyst | All analytical datasets, filtered previews, and permitted read-only SQL. |
| Admin | Analyst access, manual refresh, shared settings, and publication approval when that mode is selected. |

Scheduled refreshes and manual Admin refreshes use the same validation process. Initial account setup runs once for the shared account. The schedule defaults to daily, with an Admin-selected time and timezone. Publication is automatic after validation or requires Admin approval. Admins can change these settings later. Failed required checks block publication in either mode.

## Selected architecture direction

| Component | Responsibility |
|---|---|
| Connector and preparation | Fetch the three EIA routes, validate records, and produce local Parquet datasets. |
| PostgreSQL | Store settings, refresh outcomes, approvals, and the published data version. |
| Apache DataFusion | Query the published Parquet datasets. Outage rows are not copied into PostgreSQL for user queries. |
| BullMQ and Redis | Run the full refresh pipeline in background workers with bounded concurrency; PostgreSQL outbox records preserve dispatch requests. |
| Clerk | Authenticate users; the backend enforces application permissions. |
| Backend and frontend | Enforce access and query rules; provide login, catalog, preview, SQL, and the selected Admin features. |

These are responsibilities, not a deployment diagram. [Data contract v1](docs/schema.md) specifies schemas, validation, immutable versions, and publication invariants. Python is selected for the backend API and workers, with FastAPI for the HTTP API and Psycopg 3/Alembic for PostgreSQL access/migrations. Frontend, component versions, and the concrete deployment remain open. See [DECISIONS.md](DECISIONS.md), A1–A12.

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
| [Application model field guide](docs/application-model-guide.md) | Why the application fields exist; reconciled explanations from the Obsidian discussion. |
| [A4 session](ai/sessions/2026-10-02-a4-state-and-outage-queries.md) and [document session](ai/sessions/2026-10-02-document-baseline.md) | Evidence of decisions, contributions, corrections, checks, and handoff. |

## Assumptions and limits

One shared application/account is in scope. There is no selected multi-organization or registration flow. Selecting DataFusion does not select Rust. The business guide's hypothetical examples are not EIA findings.

The final submission still needs source code, automated tests, `.env.example`, implemented migrations, and self-contained data reproduction. The entity-relationship diagrams are now specified in the data contract. The initial commits import existing documents by topic; they do not represent implementation work. Future commits must record verified work incrementally, without squashing or rewriting history.

The private repository is `alejandroayalad/trinity`. `EIA API KEY.md`, `First Aproximation.md`, and `IMPLEMENTATION BEFORE.md` are excluded. The challenge PDF, business guide, original analysis scripts, and bulk exports remain local. References to these items identify historical sources, not included artifacts. Historical session checks have not been rerun by this import.

Source: `Software Engineer - Technical Challenge.pdf`, pages 2–8, plus the accepted decisions in this folder.

## Delivery structure and slices

Keep the required documents at the root, the data contract in `docs/schema.md`, and supporting records in `ai/sessions/`. Create `connector/`, `backend/`, `frontend/`, `scripts/`, and `tests/` when their implementation or evidence is ready. These are proposed responsibility boundaries; no language or framework is selected by the folder names. Empty implementation folders and unverified run commands are not included.

1. **Maintain data evidence — ongoing.** Extend findings and preserve reproducible evidence throughout delivery.
2. Import selected documentation in focused commits with actual commit timestamps and original work dates in the records.
3. Implement against A9's data, validation, and publication contract. Close the SQL and authentication implementation contracts before building those paths.
4. Implement and verify working slices: extraction/model/metric, authenticated catalog and preview, restricted SQL, refresh/publication/settings, and the complete interface. Update relevant decisions, findings, and Engineering Notes with each slice.
5. Verify a clean checkout using the README, test all three personas, reproduce findings, and rehearse the live explanation before submission.
