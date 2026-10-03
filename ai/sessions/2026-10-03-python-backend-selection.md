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
