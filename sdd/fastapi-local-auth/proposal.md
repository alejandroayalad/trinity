# Proposal: FastAPI and local login

Date: 2026-10-04
Status: Implemented and locally verified October 4, 2026 under the request to complete, commit and push this slice. See [implementation evidence](../../ai/sessions/2026-10-04-fastapi-local-auth-implementation.md). Compose and evaluator-owned checks remain separate.
Branch: `feat/fastapi-local-auth`
Basis: A10–A12, A15–A17, A19 and A20 in [DECISIONS.md](../../DECISIONS.md).
Related: [specification](spec.md), [design](design.md), [tasks](tasks.md), [session](../../ai/sessions/2026-10-04-fastapi-local-auth-sdd.md).

## Human

### Outcome

Replace the task's historical “Clerk verification” wording with **local credential and session verification**. A20 already selects local login. Create the FastAPI application foundation, PostgreSQL migrations needed by this slice, three seeded accounts, login/logout, server-side permissions, `/me`, and safe errors.

Input: a locally supplied username and password. Flow: verify the stored password hash → create a revocable session → resolve the current account and role on each protected request → allow only that role's capabilities. Output: `/me` reports identity, permissions and the correct landing screen, even before any dataset is published.

Example: `viewer` signs in before the first publication and receives `landing_screen=waiting`, `data_ready=false`, and `publication=null`. An Admin receives `setup` until shared setup is complete. A database outage returns a safe error; it does not pretend the application has no data.

Failure case: a Viewer sends an Admin role in a request or tries to read settings directly. The backend rejects the forged field or denies the action before reading protected settings. Hiding a button is not access control.

### Scope

| Deliverable | Boundary |
|---|---|
| Configuration and database foundation | Explicit API settings, bounded connections, Alembic revisions and empty application state; preserve independent connector configuration and `/health`. |
| Local identities | Repeatable `viewer`, `analyst`, `admin` seeding; password hashes, opaque bearer sessions, expiry, revocation and throttling. |
| App entry and access | Login/logout, `/me`, shared capability/dataset policy and read-only `GET /settings` as a real Admin-only acceptance route. |
| Safe failures | Contract-shaped errors, redaction, input limits and denial before protected access. |
| Evidence | Direct HTTP tests, real local PostgreSQL migration/session tests and an evaluator-owned three-persona check. |

Read-only settings is a small supporting part of this slice: it provides a real Admin allow/deny check without implementing setup writes or refresh commands. Analyst-only analytical execution remains a later slice; its permission dependency is tested here through a test-only route using the production policy.

Outside scope: frontend and browser token persistence, registration/password recovery, Clerk integration, setup/settings writes, catalog/preview/SQL execution, refresh workers, scheduling, publication writes, cloud configuration and live EIA/S3 work. No placeholder product endpoints claim those features work.

### Completion and review

The planned 6:30–7:15 slot is a scheduling label, not evidence that secure login, migrations and runtime verification fit in 45 minutes. Implement in the bounded steps in [tasks](tasks.md); unfinished checks remain open.

Recommendation: reuse the selected FastAPI/Psycopg/Alembic stack and Python cryptographic primitives, subject to the compatibility checks in the design. All four documents were drafted together as requested. The subsequent instruction authorized complete implementation and delivery; A21 records the implementation defaults and their AI authorship.

## LLM

### Verified baseline

The new worktree starts at local `main` commit `17864ee`. `create_app` in `backend/src/trinity/main.py` registers only `GET /health`; it opens no external connections. `config.py` contains explicit EIA and S3 settings, with no import-time credential requirement. `backend/pyproject.toml` already pins FastAPI, Pydantic Settings, Psycopg/pool, Alembic and SQLAlchemy. Tests use `unittest`; no formatter, linter or type checker is configured there.

Absence evidence: `git ls-tree -r --name-only HEAD backend sdd` and filesystem checks inspected the backend and SDD directories. Expected `backend/migrations/`, `backend/src/trinity/auth/` and `backend/src/trinity/errors.py` are absent. Only the Parquet SDD existed. Authentication behavior is specified in the canonical documents but has no implementation in this baseline.

The original `trinity` worktree contains unrelated uncommitted findings/scripts work. This branch was created in a separate worktree from committed HEAD; none of those changes were moved, overwritten or included.

### Contract ownership and evidence

[API contract](../../docs/api-contract.md) and [OpenAPI](../../docs/openapi.json) own wire fields and errors; [security contract](../../docs/security-contract.md) owns A19/A20 authorization; [schema](../../docs/schema.md) owns application state; [backend structure](../../docs/backend.md) owns module boundaries. No second schema or new authentication provider is selected here.

The four documents began as AI-authored planning evidence. The later implementation request authorized completion; A21 and the implementation session record the resulting defaults and measured evidence. Static checks do not prove migration correctness, working accounts, role isolation, deployed endpoints, or data readiness. Maintain data evidence — ongoing; synthetic identity fixtures do not create anomaly findings.
