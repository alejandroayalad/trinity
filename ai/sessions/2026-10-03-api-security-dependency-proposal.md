# Session API security and dependency proposal

Date: October 3, 2026. Scope: documentation proposal on `docs/backend-decisions-architecture`.

## Objective and contributions

[ME] Alayala requested a definition of API/security contracts and dependency versions using best practice. [YOU] AI inspected the clean repository, README, PRODUCT, A9–A15, canonical schema, backend architecture, and latest architecture session. Earlier memory was used only to locate canonical material; current repository decisions supersede its older open-stack notes.

[YOU] AI drafted [docs/api-security.md](../../docs/api-security.md) and proposed [A16–A17](../../DECISIONS.md#proposed-decisions). No decision is marked accepted. The draft preserves A9 and existing roles and adds explicit recommended HTTP shapes, current Clerk authorization, SQL grammar, process limits, and candidate version pins. README/backend links and Engineering Notes identify its proposed status.

## Evidence and limits

Official Clerk, DataFusion, SQLGlot, RFC 9457, Python, PostgreSQL, Redis, BullMQ, uv, and package release sources are linked beside the relevant claims. Public PyPI JSON was read for FastAPI, Uvicorn, Pydantic, pydantic-settings, Psycopg, psycopg-pool, Alembic, SQLAlchemy, PyArrow, DataFusion, SQLGlot, BullMQ, Clerk SDK, HTTPX, boto3, and uv. The first sandboxed read failed with DNS resolution blocked; an approved network retry succeeded. No package was installed.

Declared constraints checked: DataFusion 54.0.0 requires PyArrow >=22 for Python >=3.14; proposed PyArrow is 25.0.1. Clerk 7.0.0 requires Pydantic >=2.11.2 and HTTPX >=0.28.1; proposed versions meet those declarations. BullMQ 3.3.0 fixes its Redis client at 7.4.1; that client is distinct from proposed Redis server 8.10.2. The complete transitive dependency graph has not been resolved or audited.

No application defect or runtime behavior was demonstrated. Query sandbox deployment, per-request S3 access delivery, image digests, worker/EIA recovery budgets, frontend, and runtime tests remain open. A9, PRODUCT, FINDINGS, and historical sessions are preserved. Maintain data evidence — ongoing.

## Checks and results

Passed: relative-link and anchor checks across all six changed/new documents (92 local links, 21 anchors); balanced fences and whitespace; 17 unique decision IDs; byte comparison against HEAD for 19 preserved files, including A9 schema, PRODUCT, FINDINGS, AGENTS, and all earlier sessions. Reviewed the tracked diff and both new documents. `git diff --check` passed. No dependency resolver, advisory audit, application build, or runtime tests ran; implementation does not yet exist.

## Next action

[ME] Review and accept or revise A16–A17, especially single-table SQL and the latency/availability tradeoff of current Clerk lookups. Acceptance does not authorize implementation, Git publication, cloud resources, or costs.
