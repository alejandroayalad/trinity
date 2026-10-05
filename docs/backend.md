# Backend architecture — Trinity

Status: structure and responsibility boundaries accepted by alayala on October 3, 2026, under [A15](../DECISIONS.md#a15--backend-structure-and-responsibility-boundaries-closed). Connector/preparation, the [A21 local-login slice](../ai/sessions/2026-10-04-fastapi-local-auth-implementation.md), [catalog metadata](../ai/sessions/2026-10-04-catalog-permissions-implementation.md) and the [SQL backend](../backend/SQL.md) are implemented; the remaining feature tree is still a roadmap. The tree below describes the files to implement; it is not a claim that they exist or run.

[DECISIONS.md](../DECISIONS.md) is the decision record. [Data contract v1](schema.md) remains authoritative for analytical fields, application models, validation, and publication invariants. This document maps those responsibilities to the accepted backend structure. [A16 API contract](api-contract.md) and [OpenAPI schemas](openapi.json) now define HTTP behavior. [A19 security contract](security-contract.md) selects current local session/role verification under A20, SQL functions, per-query containers, shared query admission and limits; implementation details and runtime verification remain pending.

## Package and entrypoints

Use one Python package at `backend/src/trinity/`, organized by feature. Keep infrastructure integrations in `adapters/` and shared data/message definitions in `contracts/`.

| Entrypoint | Responsibility |
|---|---|
| `main.py` | Create the FastAPI application, configure its lifecycle, and register feature routers. |
| `workers/main.py` | Start background-job consumers that delegate refresh/publication work to feature services. Scheduling, outbox dispatch, and recovery have explicit worker modules. Publication uses A24's one-host model; other process topology remains open. |
| `queries/runtime/main.py` | Execute permitted analytical work in a separate process, with query-only configuration and enforced limits. |

Sharing a package does not mean sharing process credentials or global mutable state. Runtime imports must not initialize API/worker configuration, PostgreSQL connections, or privileged integrations. Package initialization must have no such side effects.

## Accepted file structure

The feature tree is alayala's proposal, with the agreed `workers/recovery.py` addition and refined responsibility comments. Backend project metadata, Alembic migrations, and tests sit beside `src/`. Python package markers and individual test files will be added when implementation needs them; they are omitted from this responsibility map.

```text
backend/
├── pyproject.toml                      # Backend package and dependency definitions
├── migrations/                        # Alembic environment and reviewed revisions
├── tests/                             # Backend, runtime, connector, and worker checks
└── src/trinity/
    ├── main.py                        # Create FastAPI app and register routers
    ├── config.py                      # API/worker infrastructure configuration
    ├── errors.py                      # Safe public error responses
    │
    ├── auth/
    │   ├── router.py                  # Local login and logout endpoints
    │   ├── repository.py              # Local users and revocable sessions
    │   ├── schemas.py                 # Login request and session response models
    │   ├── seed.py                    # Repeatable local persona provisioning
    │   ├── dependencies.py            # Auth requirements for HTTP endpoints
    │   ├── service.py                 # Verified identity and trusted role
    │   └── permissions.py             # Admin / Analyst / Viewer access rules
    │
    ├── catalog/
    │   ├── router.py                  # Dataset, column, and metric endpoints
    │   ├── service.py                 # Role-filtered catalog and freshness
    │   ├── registry.py                # Dataset descriptions and allowed metrics
    │   └── schemas.py                 # Catalog request/response models
    │
    ├── queries/
    │   ├── router.py                  # SQL and preview endpoints
    │   ├── service.py                 # Derive permitted datasets; pin publication
    │   ├── schemas.py                 # Public query request/response models
    │   ├── client.py                  # Runtime communication and lifecycle supervision
    │   └── runtime/
    │       ├── main.py                # Isolated query-process entrypoint
    │       ├── config.py              # Query-only config; no API/worker secrets
    │       ├── sql_policy.py          # SQLGlot grammar and table authorization checks
    │       ├── engine.py              # DataFusion context and permitted file registration
    │       └── limits.py              # Runtime time, memory, row, and output limits
    │
    ├── refresh/
    │   ├── router.py                  # Request refresh; inspect run/progress
    │   ├── service.py                 # Run lifecycle, coordination, retry/recovery rules
    │   ├── repository.py              # Runs, steps, candidates, artifacts, validation results
    │   └── schemas.py                 # Refresh request/response models
    │
    ├── publication/
    │   ├── router.py                  # Candidate inspection and Admin approval
    │   ├── service.py                 # Single publication workflow
    │   ├── checks.py                  # Evidence, coverage, ordering, eligibility checks
    │   ├── repository.py              # Publications, approvals, active pointer
    │   └── schemas.py                 # Publication request/response models
    │
    ├── settings/
    │   ├── router.py                  # Setup and configuration endpoints
    │   ├── service.py                 # Schedule and publication-setting rules
    │   ├── repository.py              # Persist shared application settings
    │   └── schemas.py                 # Settings request/response models
    │
    ├── adapters/
    │   ├── postgres.py                # Psycopg connections and transaction primitives
    │   ├── s3.py                      # Object reads/writes and manifest access
    │   ├── bullmq.py                  # Queue integration
    │   └── outbox.py                  # Transactional outbox persistence/claim helpers
    │
    ├── workers/
    │   ├── main.py                    # Start background-job consumers
    │   ├── handlers.py                # Delegate jobs to feature services
    │   ├── outbox.py                  # Dispatch committed outbox requests to BullMQ
    │   ├── scheduler.py               # Turn due schedules into refresh requests
    │   └── recovery.py                # Trigger recovery of unfinished durable work
    │
    ├── connector/
    │   ├── pipeline.py                # One EIA-to-validated-candidate pipeline
    │   ├── client.py                  # EIA requests, pagination, concurrency
    │   ├── normalize.py               # Parse and normalize source values
    │   ├── validate.py                # Source checks and exact frozen-file validation
    │   └── parquet.py                 # Generate Parquet files and manifest
    │
    └── contracts/
        ├── datasets.py                # Analytical schemas and value rules
        ├── manifest.py                # Immutable candidate/version manifest
        ├── jobs.py                    # Background-job payload definitions
        └── queries.py                 # Internal query-process message contract
```

`frontend/`, root documentation, `docs/`, and `ai/sessions/` remain outside the backend package. The frontend framework is undecided. Do not create a second top-level connector implementation or duplicate backend tests merely to match the earlier tentative folder list.

## Dependency and ownership rules

Routers validate HTTP input and call authenticated feature services. Services own application rules and transaction boundaries. Repositories implement persistence using a supplied connection. Adapters wrap external systems; worker modules trigger and delegate work. Shared contracts define data/message shapes without importing feature services or initializing infrastructure.

`catalog/registry.py` supplies descriptions and metric metadata tied to `contracts/datasets.py`; it must not define a conflicting second analytical schema. Public `schemas.py` models describe HTTP inputs/outputs. Internal `contracts/queries.py` is a different trust boundary and must not be populated by blindly forwarding a public request body.

`errors.py` maps failures to safe public codes/messages. Raw SQL-engine errors, stack traces, credentials, storage locations, or unauthorized dataset details must not leak through HTTP or runtime messages. Diagnostic records follow the existing sanitized-evidence rules.

## Local authentication

Implementation scope and tested defaults are recorded in [A21](../DECISIONS.md#a21--local-auth-implementation-settings). `auth/passwords.py` owns bounded scrypt work and `auth/check.py` provides the secret-safe operator HTTP check. `/me` remains in the auth router and coordinates feature read repositories; settings reads use their own router/service.

A20 replaces the Clerk adapter with local login/logout behind `auth/service.py`. The service verifies seeded credentials, issues/revokes sessions and resolves current server-side roles through `auth/repository.py`. The seed entrypoint creates the three personas without silently overwriting existing accounts. Actor IDs come from the authenticated local user; request-supplied roles/actors are rejected. See the [security contract](security-contract.md#authentication-and-trusted-roles) and [API login contract](api-contract.md#local-login-and-logout). Clerk is future production work, not a challenge adapter.

## Query and preview flow

1. `auth/service.py` verifies the local bearer session, active account and current stored role without caching role/session results. `auth/permissions.py` authorizes the capability before protected reads. Missing/unknown roles deny access.
2. `queries/service.py` pins one active publication and derives permitted manifest entries. It invokes the single `queries/runtime/sql_policy.py` module for whole-input SQL and physical-table checks before file downloads. Do not duplicate SQL rules in the API.
3. The trusted supervisor behind `queries/client.py` reserves a shared PostgreSQL query slot, starts the analytical deadline, downloads only authorized objects through trusted `adapters/s3.py`, checks SHA-256 identities and stages a request-specific read-only Parquet mount.
4. Start a separate container running `queries/runtime/main.py` for the approved query/preview/dashboard operation. Supply the approved operation, pinned IDs, local-file mapping and server limits through `contracts/queries.py`; supply no network, credentials or Docker control. `engine.py` registers only those mounted authorized files.
5. Bound output, verify it belongs to the request/publication, confirm execution ended or stop it, remove temporary resources and release the query slot only when no execution remains. Use the same path for all analytical execution, with endpoint-specific pagination.

Catalog metadata uses the same permission policy without giving Viewer detail through registry/freshness/diagnostics. Exploration makes no EIA request. User SQL cannot reach PostgreSQL state or unpublished files. Selecting single-table scope still requires SQLGlot/DataFusion compatibility tests for arithmetic, CASE and the A19 functions.

**Failure example:** an Analyst submits a CTE over `job_outbox`. The single policy rejects unsupported syntax before any protected file download. A permitted national query receives only authorized publication files, never S3 or application-database access from the query container.

## Query process isolation and supervision

`queries/client.py`, or its trusted supervisor, owns container launch, restricted file staging, the total deadline, stop confirmation and cleanup. Only the trusted supervisor has Docker control. No query container receives its socket, credentials or network access. `runtime/limits.py` cooperates with container-enforced memory/output bounds; it cannot establish the sandbox alone.

Use one container per analytical query under A19. Runtime imports must not initialize privileged integrations. Exact image/hardening, trusted internal protocol, read-only mount enforcement and supervision/crash recovery remain to be implemented and verified locally using Docker Compose. S3 credentials stay in trusted components; query containers read local mounts only.

PostgreSQL transactions enforce the shared two-per-user/four-deployment analytical reservations. Hold capacity through file staging and execution; a timeout or lost lease does not free a possibly running container. Confirm termination before conditional release. Rate accounting is initially 30 analytical requests/user/minute across processes, excluding progress polling. The physical reservation schema and rate-window algorithm remain open implementation details. These records are separate from refresh admission.

Provisional limits: 1,000 SQL output rows, 5 MiB response, 30 seconds including trusted downloads/file reads and 1 GiB per query container. The supervisor applies the remaining deadline after staging, not a fresh timeout at container launch. Temporary external failures allow three total attempts with one- and three-second waits within that same deadline. No retries for invalid SQL, denied access or failed validation. Four containers may use 4 GiB plus other services; measure cold reads and representative analytical work locally.

## State ownership and atomic changes

| Owner | Canonical application models |
|---|---|
| `auth/repository.py` | `local_users`, `local_sessions`, `auth_login_limits`; credentials and sessions never enter analytical registration |
| `settings/repository.py` | `shared_settings` |
| `refresh/repository.py` | `refresh_runs`, `refresh_steps`, `data_versions`, `dataset_artifacts`, `validation_results`, `refresh_control`, `failure_warnings`, `api_commands` |
| `publication/repository.py` | `approvals`, `publication_events`, `active_publication` |
| `adapters/outbox.py` | `job_outbox` persistence, claiming, and delivery state |

Feature services own transactions through `adapters/postgres.py`. Repositories and outbox helpers accept the same connection and do not commit independently. A service can coordinate multiple repositories in one transaction without copying their SQL or state rules.

`refresh/service.py` commits run creation and outbox intent together. `publication/service.py` coordinates approval/publication intent and later the publication event, active pointer, and run-success update under A9. `publication/checks.py` evaluates the existing evidence and eligibility rules; it does not maintain a second set of connector data-quality rules. Settings/resource revisions, admission-slot ownership, command idempotency, publication generation and execution-fence checks remain required under A16. Recovery commands coordinate the same repositories in one transaction; they do not use separate HTTP-only state.

**Failure example:** the run insert succeeds but the outbox insert fails. The owning service rolls back the whole transaction and does not return acceptance. Redis dispatch happens after commit. Keep external EIA, S3, and Redis operations outside long database transactions; no distributed transaction is implied.

## Refresh, validation, and publication

An authorized manual request or due scheduled occurrence enters `refresh/service.py`. After the run/outbox transaction commits, `workers/outbox.py` dispatches through `adapters/bullmq.py`. `workers/handlers.py` routes the job kind to the responsible service; it does not implement another lifecycle.

The refresh service coordinates `connector/pipeline.py`: fixed-window extraction under A9, normalization, early source checks, Parquet generation, manifest freeze, and validation of those exact generated files. `contracts/datasets.py` and `contracts/manifest.py` supply shared definitions. Persist candidate/artifact/check results through `refresh/repository.py`, with the active execution fence.

`connector/validate.py` must cover both normalized values and the final candidate. It produces the one complete validation attempt required by A9, including artifact-integrity checks. `publication/checks.py` checks that the evidence belongs to the candidate and that coverage, ordering, approval, and other publication conditions hold. No approval can bypass failed or missing required validation.

**Failure example:** source rows pass but a Parquet object is truncated or missing. Final-file validation fails and the candidate stays unpublished. The prior publication remains available. A successful queue job alone is not proof that data passed validation or was published.

A16 derives automatic readiness versus required approval from the frozen warning set. Both use the outbox handoff to a publication worker. The HTTP approval endpoint records acceptance; it does not run the file/publication pipeline. The worker rechecks the frozen manifest's integrity and eligibility and performs A9's atomic publication transition. All three analytical datasets in a response remain on the one publication pinned for that request.

## Scheduling, dispatch, and recovery

| Module | Responsibility |
|---|---|
| `workers/scheduler.py` | Convert due occurrences into requests through feature services, respecting setup/settings and stable occurrence identity. |
| `workers/outbox.py` | Dispatch committed outbox work and record delivery through the persistence helpers; handle the enqueue/acknowledgment gap safely. |
| `workers/recovery.py` | Retain periodic Refresh recovery under A23. Publication uses the separate explicit operator mode in the existing worker entrypoint under A24; feature services own reconciliation. |

[A24](../DECISIONS.md#a24--build-publication-first-delivery) supersedes the earlier requested/running/publishing
automatic recovery scope only for Publication. Keep A23 Refresh recovery and bounded
pending/unacknowledged publication enqueue. Lost delivered publication jobs and
publisher crashes require the tested operator CLI, not an automatic replay. Admin
retry then rearms the same eligible candidate in a new publication generation;
operator reconciliation cannot grant this new attempt. Never revive terminal or
abandoned work. Services own transactions, eligibility, fences and recovery rules;
worker/queue adapters only delegate.

**Failure example:** Redis acknowledges a publication job, then loses it. The
operator proves no publisher owns the retained lock and reconciles database state.
A committed event remains unchanged; otherwise the run becomes safely publication-failed
and retains its slot. An Admin may retry the same eligible candidate and original
approval. No EIA extraction repeats. Earlier automatic redispatch for this scenario
is historical under A24.

## Proposed database execution model

Async FastAPI handlers and Psycopg `AsyncConnectionPool`, 1–5 connections per process with a 5-second acquisition deadline, remain earlier proposals, not accepted defaults. A17 selects versions; A19 selects PostgreSQL shared query-slot transactions without deciding pooling. Services own transactions; external downloads and retries must not hold long database transactions open.

## Contracts and verification still required

The accepted tree locates responsibilities; it does not complete these contracts. [A16](api-contract.md) supplies approved HTTP flow and detailed schemas; [A17](../DECISIONS.md#a17--dependency-versions-and-update-policy-closed) accepts dependency versions. A18/A19 select SQL features, authentication policy, container isolation, limits and retries. Exact implementation settings remain open. Implementation/compatibility checks remain pending:

| Open item | Required outcome before implementing that path |
|---|---|
| Dependency versions and execution model | Compatible pinned releases; PostgreSQL pooling/sync-async choices; bounded worker/query concurrency and verified worker recovery. |
| HTTP API implementation | Implement the 22 operations and field schemas in A16/OpenAPI, including dashboard, entity options, schedule status, rerun, warning resolution, retry and discard. |
| SQL and authentication | Exact dialect/AST/argument forms and compatibility fixtures for selected functions; token configuration and tests of local seeded login, revocation and current role/session checks. |
| Query process contract and deployment | Trusted message transport, one network-disabled query container, authorized read-only file mounts, private S3 download permissions, termination/cleanup and shared PostgreSQL admission verification. |
| Acceptance tests | Authorization before file reads, whole-input SQL rejection, exact decimals, snapshot consistency, transaction failures, final-file validation, timeout cleanup, resource exhaustion, and Redis/worker recovery. |

No application code, packages, processes, migrations, or runtime tests were created or run for this document. Add runnable commands only after implementation and verification.

Sources: [A4 and A6–A15](../DECISIONS.md), [data contract v1](schema.md), alayala's proposed tree, and the [review/correction history](../ai/sessions/2026-10-03-backend-stack-review-and-layout.md). The reviewed [Python subprocess documentation](https://docs.python.org/3/library/subprocess.html) explains environment inheritance and timeout behavior; [DataFusion runtime/SQL options](https://datafusion.apache.org/python/autoapi/datafusion/context/index.html) describe engine controls. These sources do not constitute runtime verification of Trinity.


## Refresh dispatch/preparation implementation mapping

The current [A23 slice](../DECISIONS.md#a23--durable-refresh-dispatch-and-one-fenced-preparation-execution)
uses `adapters/queue.py` for BullMQ, `refresh/dispatch.py` and `refresh/execution.py`
for service-owned transactions, and `workers/outbox.py`, `workers/refresh.py`,
`workers/recovery.py` with a `workers/__main__.py` command entrypoint. These concrete
names refine the earlier roadmap tree; they do not add a second queue stack.
Connector hooks reuse the existing preparation process and evidence formats.
Successful receipt routing and stopped-worker receipt recovery now call the
existing registration service. `refresh/candidates.py` exposes the Admin-only
persisted detail snapshot. Publication completion now uses the service described below.

## Publication first-delivery implementation boundary

[A24](../DECISIONS.md#a24--build-publication-first-delivery) accepts one supported worker host and one publication
consumer. Reuse A23's queue/outbox pattern, original same-host lifetime lock,
run fence/lease and publish step records. The 300-second step deadline is fixed for
one verifier invocation per publication generation; no heartbeat or publication
child supervisor is added. Async cancellation and lease expiration do not prove a
thread stopped. Keep the lock inside the actual synchronous execution.

Add publication services/command handling and job-kind routing to the current
feature structure. Do not call Refresh's terminal failure helper or preparation
claim/reclaim methods for publishing. Preserve receipt custody and preparation
budgets. Extend existing verification with typed safe causes so generic errors
cannot grant retry. No production dependency or new persistence table is selected.

The executable `publication-recover` mode must branch before the current entrypoint
loads Redis/S3 configuration. Require the trusted worker OS account, original host/root
and database access, but no EIA/S3/Redis access. It performs inspection or guarded
stop-proof reconciliation; it does not run HTTP Admin actions or verify remote files.
The [design](../sdd/publication/design.md#operator-interface--required-executable-delivery)
defines exact arguments, outcomes and exit codes. [Tasks](../sdd/publication/tasks.md)
require real CLI, retry, crash, concurrency and reader tests before completion.
The mode and publisher are implemented locally. Actual acceptance gates and
deployment limits are tracked in the [implementation record](../ai/sessions/2026-10-04-publication-implementation-acceptance.md).
