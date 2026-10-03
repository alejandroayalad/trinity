# Session — Python backend selection

Date: October 3, 2026. Scope: decisions and documentation. This is an AI-written summary, not a verbatim transcript or runtime evidence.

## Objective and contributions

[ME] Alayala started step 3, defining the backend and security, proposed a Python-oriented stack, and accepted Python for the API and workers. [YOU] AI inspected the current repository decisions and handoff, checked official library documentation, and recorded [A10](../../DECISIONS.md#a10--python-for-the-backend-api-and-workers-closed). The checkout had no reported changes before these edits.

## Decision references and corrections

A4 and A6–A8 already select PostgreSQL/DataFusion, BullMQ/Redis, the outbox, and Clerk. A9 and [docs/schema.md](../../docs/schema.md) already specify data and publication behavior. A10 selects the application language; it does not replace those decisions or accept every proposed library.

The current BullMQ Python development source includes `setGlobalConcurrency`. A method in that source is not proof that the eventual pinned release enforces concurrency or survives worker failures. The required verification should use two workers, a queue-wide limit of one, and worker restart/duplicate-delivery scenarios.

For security discussion, an Analyst querying `job_outbox` is a useful rejection case because Analysts may use SQL but may not access application-state tables. Viewer access must also be enforced across every product path. Neither Python nor an HTTP framework supplies this application policy automatically.

## Checks and results

Passed: diff review and `git diff --check`; a Python check resolved 61 relative links/anchors across the five changed documents and found ten unique decision headings. Byte comparisons against Git HEAD confirmed that the canonical schema, product rules, findings, and every earlier session were unchanged. The scope is the decision record, README, agent guidance, contribution note, and this new session. Git/Python emitted macOS cache-write warnings inside the sandbox but completed the checks successfully.

No application code, dependency installation, database migration, EIA request, runtime test, commit, push, or PR is included. Compatibility, concurrency, token checks, SQL isolation, decimal behavior, and resource limits remain unverified at runtime.

## Open questions and next action

FastAPI is recommended for request validation and generated OpenAPI documentation, but not selected. Python and library versions, the PostgreSQL driver/migration tool, frontend, token/role details, catalog/preview/query/refresh contracts, supported SQL, table-reference detection, and limits remain open.

Next: [ME] accept or reject FastAPI for the backend HTTP API.

## FastAPI follow-up

[ME] Alayala accepted FastAPI. [YOU] AI recorded [A11](../../DECISIONS.md#a11--fastapi-for-the-backend-http-api-closed), updated the current README and agent guidance, and retained the initial Python decision above as history. The existing uncommitted A10 changes were preserved. API request validation and documentation are framework facilities; authentication, authorization, SQL restrictions, and decimal serialization still need implementation and tests. Refresh execution remains in BullMQ workers.

The next proposed pair is Psycopg 3 for PostgreSQL access and Alembic for versioned schema migrations. A7/A9 require the refresh run and outbox record to commit together or both roll back. Psycopg exposes explicit transaction blocks. Alembic manages migration revisions and brings SQLAlchemy as a dependency; that does not itself select ORM models for application queries. These are recommendations, not accepted choices or installed packages. Sources: [Psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html), [Alembic](https://alembic.sqlalchemy.org/en/latest/), and [its dependencies](https://alembic.sqlalchemy.org/en/latest/front.html#dependencies).

Checks passed: diff review, `git diff --check`, 65 relative links/anchors, eleven unique decision headings, and whitespace checks in all five edited documents. No runtime checks, dependency installation, commits, or remote changes.

Next: [ME] accept or reject Psycopg 3 plus Alembic for PostgreSQL access and schema migrations.

## Backend decisions branch and commit slices

[ME] Alayala requested one continuing branch for backend decisions and architecture, with the current changes committed in two slices. [YOU] AI created `docs/backend-decisions-architecture` from `docs/vault-session-handoff-20261003` at `bc5969d`, preserving its existing handoff history. The two slices are Python selection (A10) and FastAPI selection (A11), each with its matching guidance and evidence notes. This continues the same session; the earlier no-commit statements describe the discussion before this authorization.

Keep subsequent backend decisions on this branch until the work is finished. This request does not accept Psycopg/Alembic, authorize implementation, or request a push or PR. The next decision remains the PostgreSQL driver and migration tool.

## Database tools follow-up

[ME] Alayala subsequently accepted Psycopg 3 and Alembic while the two-commit task was in progress. [YOU] AI recorded [A12](../../DECISIONS.md#a12--psycopg-3-and-alembic-for-postgresql-closed) and aligned current guidance. The Python slice was already committed as `2812313`; the second slice includes FastAPI and the newly accepted database tools. Earlier references to unaccepted tools describe the preceding discussion.

This selects the driver and migration tool, not dependency versions, an ORM, database schema implementation, or a deployment. No dependencies were installed, migrations executed, or runtime behavior verified. The branch remains the place for the unfinished backend/API/security decisions.

Checks passed before the second commit: 69 relative links/anchors, twelve unique decision headings, unchanged A9 and required-topic tracking, the exact five intended documentation files, and `git diff --check`. The first staged slice separately passed 61 links/anchors and ten unique decision headings.

Next: [YOU] review compatible dependency versions before proposing pins; complete the API/security contract afterward.
