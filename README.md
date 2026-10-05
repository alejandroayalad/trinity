# Trinity — Arkham Outage Explorer

**National dashboard handoff — October 5, 2026:** Steps 2–3 are implemented; Step 4 passed 101 combined tests with zero skips. Step 5 readiness and prerequisites are recorded in the [real acceptance and operator handoff](ai/sessions/2026-10-05-dashboard-runtime-and-operator-handoff.md). National reads reuse the shared preview runtime. Retained operator readiness is **not ready**: no active publication, and the installed retained API lacks the national routes and preview switch. Execution is still disabled by default in this branch. See the handoff for final automated results and the retained prerequisites.

Trinity is the selected product name for the Arkham Outage Explorer challenge. It will let users explore U.S. nuclear outage data persisted in application-owned storage, without fetching live EIA data for each analytical request. A14 records alayala's interpretation of “locally.”

**Refresh continuation:** `feat/refresh-publication` now extends merged SQL/Preview. Admin admission, durable BullMQ dispatch and fenced preparation are implemented with disposable-service checks. Linear migrations and verified candidate registration preserve Preview-compatible evidence fields. Task 5 now connects receipt routing/recovery and Admin candidate detail. [Current tasks](sdd/refresh-publication/tasks.md) track measured verification; Publication implementation and acceptance are tracked in the [implementation and acceptance](ai/sessions/2026-10-04-publication-implementation-acceptance.md) record.

**Previous delivery:** `feat/catalog-permissions`: catalog is complete; SQL is implemented with remaining verification tracked in its [current checklist](sdd/single-table-sql/tasks.md); preview integration and Step 4 automated acceptance passed. Step 5 operator tooling is implemented; the [handoff](ai/sessions/2026-10-04-dataset-preview-step-5-handoff.md) records checks and the closure boundary. Retained migration/publication linkage and the retained-account run remain incomplete; preview execution stays disabled. Step 4 results remain in the [acceptance record](ai/sessions/2026-10-04-dataset-preview-step-4-acceptance.md). See the [reconciliation and remaining boundaries](ai/sessions/2026-10-04-catalog-sql-preview-reconciliation.md) and [session index by theme](ai/sessions/README.md).

**Publication delivery:** [A24](DECISIONS.md#a24--build-publication-first-delivery) Tasks 1–6 are authorized and implemented locally. Atomic publication, Admin approval/retry/discard and executable operator recovery passed all essential local acceptance gates. See [implementation and acceptance](ai/sessions/2026-10-04-publication-implementation-acceptance.md); focused commits and push are now authorized; live activation and a PR remain outside this delivery. See the [full-system live acceptance plan](docs/live-system-acceptance-plan.md).

**Publication dependency:** Step 5, Refresh and publication, as [accepted under A16](DECISIONS.md#a16--approved-api-flow-and-detailed-contract). Implement the candidate-to-active-publication lifecycle before claiming real-data SQL/preview delivery.

**Status: Parquet preparation Steps 1–5 implemented and offline-tested; session closed October 4, 2026.** The backend has a FastAPI health endpoint, bounded three-route extraction, exact Parquet files, saved-file validation, a trusted S3 adapter and a supervised preparation command. All 185 offline tests passed at closure. The separate [October 1–2 live verification](evidence/live-preparation/2026-10-04-october-1-2/README.md) now passed all 16 required checks, stored an unpublished candidate and independently verified 50 S3 objects. It used the recorded uncommitted parser fix; the original three-day window and fresh locked setup remain unverified. The outage explorer is not yet implemented. See the [closure and S3 handoff](ai/sessions/2026-10-04-parquet-preparation-steps-2-5-close.md).

**Phase 3 — findings scripts:** [One offline report command](evidence/findings/README.md) reproduces the reconciliation, AN-01–AN-03, weighted-percentage example, and daily keys from bundled historical EIA inputs. The saved-data run passed all 16 claim checks and 82,650 exact MW comparisons. These results do not verify the separate live EIA → preparation → S3 gate. Keep the existing AWS setup; verify it with real execution evidence.

Current authentication handoff: [local login implementation](ai/sessions/2026-10-04-fastapi-local-auth-implementation.md). Login/logout, `/me`, Admin settings reads, migrations and persona provisioning are implemented and tested with native PostgreSQL 17.11 and real HTTP; see [local setup](backend/README.md#local-api-and-three-personas). Backend handoff: [backend structure accepted](ai/sessions/2026-10-03-backend-structure-accepted.md), following the [stack review and correction](ai/sessions/2026-10-03-backend-stack-review-and-layout.md#author-correction-and-accepted-stack). [docs/schema.md](docs/schema.md) and A9 remain canonical for data/publication behavior; [docs/backend.md](docs/backend.md) records A15's accepted file structure and responsibility boundaries. Use the [application field guide](docs/application-model-guide.md) for the discussion explanations. A10–A14 select Python, FastAPI, Psycopg 3, Alembic, PyArrow, datafusion-python, SQLGlot, and application-owned S3 storage. [Backend instructions](backend/README.md) describe the implemented commands. Current delivery: local-login slice reviewed; two-day EIA/S3 verification completed with an uncommitted parser correction and exact evidence. Next: review that correction and evidence. A16 API flow, A17 dependencies and A18 staged SQL scope remain accepted. Maintain data evidence — ongoing; see [FINDINGS.md](FINDINGS.md).

Dependency versions are accepted under [A17](DECISIONS.md#a17--dependency-versions-and-update-policy-closed), including the exact release table and locked installation policy. Compatibility verification is pending. [A16](docs/api-contract.md) records the approved API flow and expanded request/response contract; [A19 security contract](docs/security-contract.md) records accepted authentication, SQL, container isolation, admission and limits. [OpenAPI](docs/openapi.json) defines 22 HTTP operations (20 product operations plus local login/logout). [A18](DECISIONS.md#a18--sql-scope-by-stage-closed) accepts the staged SQL scope; A19 selects the function list and arithmetic/CASE; parser/engine implementation and measured checks are recorded in the [SQL checklist](sdd/single-table-sql/tasks.md).

**Catalog handoff — October 4, 2026:** `GET /api/v1/catalog` is implemented with national-only Viewer metadata, all three datasets for Analyst/Admin, and one consistent publication/freshness snapshot. The delivery regression passed 239 offline tests; 36 opt-in database tests were skipped there and passed separately in the 70-check auth/catalog runner. See the [current review](ai/sessions/2026-10-04-catalog-review-and-delivery.md). Real loopback HTTP covered all personas with synthetic state. Your retained-account Docker operator check passed for all three personas with no active publication; see [operator evidence](ai/sessions/2026-10-04-catalog-docker-operator-check.md), [operator instructions](backend/README.md#catalog-metadata-and-operator-check) and [implementation evidence](ai/sessions/2026-10-04-catalog-permissions-implementation.md). Preview rows and frontend remain later slices. The separately implemented SQL backend and its remaining runtime checks are documented in [SQL delivery](backend/SQL.md).

Catalog reading order: [SDD and delivery guide](sdd/catalog-permissions/README.md). Session history: [grouped by theme](ai/sessions/README.md).

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
| Seeded local authentication | Authenticate Viewer, Analyst and Admin accounts; the backend enforces the same application permissions. Clerk is future production work under A20. |
| Backend and frontend | Enforce access and query rules; provide login, catalog, preview, SQL, and the selected Admin features. |

These are responsibilities, not a deployment diagram. [Data contract v1](docs/schema.md) specifies schemas, validation, immutable versions, and publication invariants. [Backend architecture](docs/backend.md) maps them to the accepted feature-based package and separate query runtime. Docker Compose is selected for local execution; frontend and public hosting remain open. Exact security implementation and verification remain pending. A17 selects dependency versions; compatibility verification remains pending. See [DECISIONS.md](DECISIONS.md), including the later A22–A24 refinements.

## Setup, running, and tests

The selected local execution target is Docker Compose. `compose.yaml` supplies PostgreSQL 17.11 and the API; startup, migrations and a synthetic persona flow were verified locally on October 4, 2026 ([Docker session](ai/sessions/2026-10-04-docker-local-setup.md)). The supplied challenge requires local execution (page 7) and a repository link (page 8), not a public application URL. AWS/hosting remains undecided. See the [source review](ai/sessions/2026-10-03-security-contract-and-api-split.md#challenge-delivery-evidence).

The minimum backend setup is documented in [backend/README.md](backend/README.md). It exposes health, local login/logout, `/me` and read-only Admin settings; this is not a complete challenge submission. Follow the local API setup before starting it.

With CPython 3.14.8, uv 0.12.23 and the API database URL configured as described in the backend setup:

```bash
cd backend
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
uv run --locked uvicorn trinity.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
```

To run all three EIA routes for one fixed date window and save sanitized retrieval evidence, use the [extraction command](backend/README.md#retrieve-all-three-routes-and-save-evidence). It records failures as well as successes and returns a nonzero exit code when any route fails.

The separate [preparation command](backend/README.md#prepare-a-stored-candidate--step-5) connects extraction, exact files, validation and verified storage. Configure and verify private S3 protection before live use. Command success identifies an unpublished candidate; it does not change application publication state.

The health response is `{"status":"ok"}`. It reports process liveness, not data readiness. API startup requires the database URL; health requires no EIA key, login, working database, Redis or S3 connection. Trusted connector code can call `trinity.config.load_eia_settings()` to read `EIA_API_KEY` from the process environment; see [EIA configuration](backend/README.md#eia-configuration).

| Required README content | Status |
|---|---|
| Prerequisites, configuration, and local startup | Backend dependency resolution and locked installation verified; API + PostgreSQL Compose startup verified (see [backend setup](backend/README.md#run-with-docker-compose)); full application startup remains pending. `backend/.env.example` documents the environment-based EIA key loader. |
| Seeded users for Viewer, Analyst, and Admin | Implemented through repeatable hidden-input provisioning and tested with three synthetic personas. Supply your own local passwords; [A20](DECISIONS.md#a20--seeded-local-authentication-for-the-challenge-closed) selects local seeded accounts; Clerk configuration is not required. |
| Automated test command and results | The PR branch after main integration passed 220 offline checks; the prior local-auth acceptance passed 25 real PostgreSQL checks; see the [implementation evidence](ai/sessions/2026-10-04-fastapi-local-auth-implementation.md). Phase 3 separately passed 202 offline checks, including 17 findings tests; see the [findings record](ai/sessions/2026-10-04-findings-scripts-reproduction.md). The earlier Parquet closure passed 185 offline tests on CPython 3.14.8, including 18 preparation-command tests. These use synthetic HTTP/storage, real temporary Parquet and spawned processes. The earlier October 3 live extraction is separate [evidence](evidence/2026-10-03-first-live-eia-run.md); it does not verify the new preparation command or S3 protection. |
| Connector failures: credentials, network, and bad data | A9 specifies failed-candidate handling and durable recovery obligations. A19 selects three total attempts for temporary external failures with one- and three-second waits within the operation deadline; denied access, invalid SQL and failed validation are not retried. Refresh-stage deadlines and runtime checks remain pending. Preserve the last valid publication. |
| Data reproduction commands and schema diagram | [Analytical and application ER diagrams](docs/schema.md) are specified. [Findings reproduction](evidence/findings/README.md) includes the reviewed historical exports, sanitized API probes, checksums, command, and measured outputs. No key or network access is needed. |

### Local authentication setup contract

A20 selects local login as the challenge default. The implemented seed step creates accounts named `viewer`, `analyst`, and `admin`, one per persona. The evaluator supplies passwords locally during setup; store only salted password hashes. Keep actual passwords, session tokens and local secret files out of Git and logs. `.env.example` will contain placeholders only. Seeding must be repeatable without duplicating users, resetting existing passwords/roles or deleting history.

The [backend setup](backend/README.md#local-api-and-three-personas) provides migration, seed, start and safe persona-check commands. Real HTTP tests exercised all three personas in a disposable PostgreSQL database. Supply local passwords to provision your own retained accounts. Login returns an opaque session; permissions remain server-controlled. No Clerk account, key, provisioning or request is part of this flow. This removes the authentication provider dependency only; the existing EIA/storage setup requirements remain.

Clerk is deferred production work behind `auth/service.py`; the challenge does not implement two providers or switch providers after an authentication failure.

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
| [CONTRIBUTING.md](CONTRIBUTING.md) | Code readability, comment, and docstring rules for human and AI contributors. |
| [docs/schema.md](docs/schema.md) | Finalized v1 data contract, validation checks, logical fields, and analytical/application ER diagrams. |
| [Parquet preparation proposal](sdd/parquet-preparation/proposal.md), [specification](sdd/parquet-preparation/spec.md), [design](sdd/parquet-preparation/design.md) and [tasks](sdd/parquet-preparation/tasks.md) | Steps 1–5 implemented, with 185 passing offline tests and authorized session closure. Real S3 protection and live preparation remain separate gates. |
| [FastAPI/local login proposal](sdd/fastapi-local-auth/proposal.md), [specification](sdd/fastapi-local-auth/spec.md), [design](sdd/fastapi-local-auth/design.md) and [tasks](sdd/fastapi-local-auth/tasks.md) | Implemented A20 local-login slice; real PostgreSQL/HTTP evidence is in the linked tasks and session. Compose and evaluator walkthrough remain unverified. |
| [One-table SQL proposal](sdd/single-table-sql/proposal.md), [specification](sdd/single-table-sql/spec.md), [design](sdd/single-table-sql/design.md), [tasks](sdd/single-table-sql/tasks.md) and [pairing review](sdd/single-table-sql/pairing-gate.md) | SQL policy, DataFusion, admission/staging, isolated execution/recovery and HTTP delivery are committed. See [measured evidence and remaining acceptance boundaries](ai/sessions/2026-10-04-sql-delivery-commits.md). |
| [Catalog and permissions proposal](sdd/catalog-permissions/proposal.md), [specification](sdd/catalog-permissions/spec.md), [design](sdd/catalog-permissions/design.md) and [tasks](sdd/catalog-permissions/tasks.md) | Step 5, slice 1 implemented and automated-tested; see the [implementation evidence](ai/sessions/2026-10-04-catalog-permissions-implementation.md). Retained-account operator check passed; frontend navigation remains pending. |
| [Dataset preview proposal](sdd/dataset-preview/proposal.md), [specification](sdd/dataset-preview/spec.md), [design](sdd/dataset-preview/design.md) and [tasks](sdd/dataset-preview/tasks.md) | Specification approved; design/tasks drafted with staged offline, real runtime and operator evidence. Reuse confirmed frozen validation evidence; verify its publication/preview linkage and shared SQL execution before delivery. Steps 2–3 code is implemented; [Step 4 acceptance](ai/sessions/2026-10-04-dataset-preview-step-4-acceptance.md#final-checkpoint) records passing automated runtime/regression evidence. Step 5 adds the guarded [operator checker](ai/sessions/2026-10-04-dataset-preview-step-5-handoff.md); retained migration/publication linkage and operator acceptance remain pending. |
| [Publication proposal](sdd/publication/proposal.md), [specification](sdd/publication/spec.md), [design](sdd/publication/design.md) and [tasks](sdd/publication/tasks.md) | A24 scope approved; manual operator recovery and Admin retry are required delivery. Tasks 1–6 authorized and implemented; measured results are in the acceptance record. |
| [docs/backend.md](docs/backend.md) | Accepted backend file structure, process boundaries, transaction ownership, validation/recovery responsibilities, and pending contracts. |
| [Refresh/publication integration contract](sdd/refresh-publication/integration-contract.md) and [Build Refresh SDD](sdd/refresh-publication/proposal.md) | Preview-compatible migrations and verified candidate registration implemented; remaining Refresh admission, dispatcher, worker and publisher tracked in the SDD. |
| [docs/api-contract.md](docs/api-contract.md) | Approved A16 human flow, endpoint requests/responses/errors, pagination and recovery; security rules are maintained separately. |
| [docs/security-contract.md](docs/security-contract.md) | Accepted A19 roles, SQL policy, container/S3 boundaries, admission, limits, retry rules and required verification. |
| [docs/openapi.json](docs/openapi.json) | Machine-readable HTTP schemas for 22 specified API operations; six are implemented by the local-login, catalog and SQL slices. |
| [Application model field guide](docs/application-model-guide.md) | Why the application fields exist; reconciled explanations from the Obsidian discussion. |
| [A4 session](ai/sessions/2026-10-02-a4-state-and-outage-queries.md) and [document session](ai/sessions/2026-10-02-document-baseline.md) | Evidence of decisions, contributions, corrections, checks, and handoff. |

## Assumptions and limits

One shared application/account is in scope. There is no selected multi-organization or registration flow. Selecting DataFusion does not select Rust. The business guide's hypothetical examples are not EIA findings.

The backend includes locked dependencies, a health endpoint, bounded EIA extraction, retained evidence, exact Parquet preparation, saved-file validation, verified-storage code and 185 offline tests. The first live extraction passed for one fixed date ([evidence](evidence/2026-10-03-first-live-eia-run.md)). The preparation pipeline has a successful October 1–2 live EIA/S3 result with independent readback; see the recorded tested patch and limits above. The final submission still needs full-history preparation evidence, remaining product source code, full-product acceptance, later feature migrations, and self-contained data reproduction. The entity-relationship diagrams are specified in the data contract. The initial commits import documents; later commits record implementation incrementally without squashing or rewriting history.

The private repository is `alejandroayalad/trinity`. `EIA API KEY.md`, `First Aproximation.md`, and `IMPLEMENTATION BEFORE.md` are excluded. The challenge PDF, business guide, original analysis scripts, and bulk exports remain local. References to these items identify historical sources, not included artifacts. Historical session checks have not been rerun by this import.

Source: `Software Engineer - Technical Challenge.pdf`, pages 2–8, plus the accepted decisions in this folder.

## Delivery structure and slices

Keep required documents at the root, the data contract in `docs/schema.md`, backend architecture in `docs/backend.md`, and supporting records in `ai/sessions/`. A15 selects the feature tree in `backend/src/trinity/`, with backend migrations and tests beside `src/`. It includes the connector and separate API, worker, and query-runtime entrypoints. This supersedes the earlier tentative top-level connector grouping. `frontend/` remains separate; add supporting scripts only when needed. The health API, connector, analytical contracts and S3 adapter are implemented. Add other feature files as their behavior is implemented; the remaining selected tree is the roadmap.

1. **Maintain data evidence — ongoing.** Extend findings and preserve reproducible evidence throughout delivery.
2. Import selected documentation in focused commits with actual commit timestamps and original work dates in the records.
3. Implement against A9's data, validation, and publication contract. Implement A19 security boundaries and verify them locally before enabling untrusted queries.
4. Implement and verify working slices: extraction/model/metric, authenticated catalog and preview, restricted SQL, refresh/publication/settings, and the complete interface. Update relevant decisions, findings, and Engineering Notes with each slice.
5. Verify a clean checkout using the README, test all three personas, reproduce findings, and rehearse the live explanation before submission.
