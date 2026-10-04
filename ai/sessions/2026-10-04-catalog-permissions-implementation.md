# Catalog and permissions — implementation and evidence

Date: 2026-10-04 (America/Merida)
Branch/base: `feat/catalog-permissions`, `fde733b`; no commit or remote change.
Status: Backend implementation and automated verification complete. Alayala's local operator check and behavior review remain pending.

## Objective and authorization

[ME] Alayala requested implementation and explicitly reserved his local operator check. He agreed that offline tests, real database/HTTP tests and the local operator check are separate evidence categories; passing one does not prove the others.

[YOU] AI implemented the approved [specification](../../sdd/catalog-permissions/spec.md) and [design](../../sdd/catalog-permissions/design.md) on the existing branch. Before edits, AI explained the session → permission → metadata snapshot → response flow and the failure case: a newer failed refresh leaves an older active publication ready, whereas a database failure produces an error. No retained understanding is inferred from the implementation request.

The implementation request supersedes earlier SDD drafting-only gates. It does not authorize Git delivery, live publication or marking the operator check complete. A9/A15–A17/A19–A21 and the accepted A16 navigation/freshness refinements remain in force.

## What changed

`catalog.router.catalog` exposes `GET /api/v1/catalog`. The existing session dependency checks identity and opens the read-only repeatable-read transaction. `catalog.service.get_catalog` calls the shared permission rule before state reads; it builds fresh permitted metadata, calls `read_publication` once and reads the safe latest-refresh projection using the same connection.

`auth.permissions.permitted_dataset_keys` now supplies the existing internal key rule to both catalog selection and `require_dataset`. It preserves capability counts and the existing hidden-dataset denial. `catalog.registry.describe_dataset` derives public names, ordered columns, types, nullability and daily keys from `contracts.datasets.DATASETS`; presentation data adds units, labels and available filter names. The calculated national metric remains separate from source `percentOutage`.

`refresh.repository.read_last_refresh` selects only `status`, `requested_at`, and `finished_at`, ordered by highest `run_seq`. It never calls Admin `read_context`. The catalog models reject extra fields, malformed timestamps, invalid coverage and conflicting readiness/freshness. Known invalid persisted state becomes `503 dependency_unavailable`; malformed static definitions remain safe internal failures. Existing transport provides no-store, request IDs and sanitized problems.

No migration, production dependency, lockfile change, analytical row read, EIA/S3 access, container, query slot, refresh command or publication action was added. Viewer still has metadata API access for the future national dashboard; no frontend, preview row endpoint or SQL executor is implemented here.

The existing hidden-input `auth.check` command gains optional `--catalog`. It verifies exact role-filtered catalog keys and snapshot consistency, logs out even after a failed catalog check, and checks denial after logout. The default auth-only behavior remains valid. It prints only safe summaries, not tokens or response bodies.

## Test organization and evidence

Moved the pre-existing database setup/lifecycle helper methods into `backend/tests/postgres_fixture.py`. An AST comparison proved every moved method and existing auth test body is unchanged. `PostgresAuthTests` and `PostgresCatalogTests` share fixture methods rather than inheriting one another's tests. The disposable runner now discovers both auth and catalog suites.

New permission-helper regressions live in `test_catalog_unit.py`; the existing auth unit suite remains unchanged. New real-database tests live in `test_catalog_postgres.py`. `test_health` retains its exact endpoint-surface assertion with the new catalog path added.

Runtime: existing CPython 3.14.8 environment, PostgreSQL 17.11 (Homebrew), private temporary Unix-socket cluster. `uv` was not found in the agent PATH or inspected usual executable locations. Commands below use the already-installed `.venv/bin/python`; all declared direct dependency versions matched `pyproject.toml`. This is not fresh locked-install evidence. No new package was installed. The existing Starlette/httpx deprecation warning appeared; dependency pins were not changed to suppress it.

### Offline evidence

Commands were run from `backend/`:

| Command | Observed result |
|---|---|
| `.venv/bin/python -m unittest discover -s tests -p 'test_catalog_unit.py' -v` | 16 passed in 4.690 seconds. Real catalog route with controlled identity/state; canonical metadata, role filtering, current-role policy, malformed input/state, safe errors/headers, no-I/O guards and operator-check behavior. |
| `.venv/bin/python -m unittest discover -s tests -p 'test_health.py' -v` | 2 passed in 0.054 seconds after updating the endpoint inventory. |
| `.venv/bin/python -m unittest discover -s tests -v` — final run | 272 discovered; 236 passed, 36 opt-in PostgreSQL tests skipped; 30.928 seconds. Those 36 were run separately, not counted as passing by this command. |

First full regression: 272 discovered, one failure and 36 skips in 26.365 seconds. `HealthTests.test_surface_contains_only_implemented_product_operations` expected the old route list; the actual list added only `/api/v1/catalog`. Corrected that exact expected set, ran the focused health tests, then reran the full suite. No catalog or auth behavior was relaxed to pass the check.

### Automated PostgreSQL and HTTP evidence

`.venv/bin/python tests/run_local_auth_checks.py` passed **70 checks in 55.136 seconds**, with no skips: **36 database-backed checks** (25 auth, 11 catalog) and **34 offline checks** (18 auth, 16 catalog). The runner created, migrated and removed only its disposable test cluster. The existing auth suite also tests downgrade/rebuild inside that cluster; no retained application database was migrated or reset.

Catalog-specific proof includes:

- All three real sessions receive the exact role-permitted datasets before and after a synthetic publication. Expiry, logout, deactivation and stored role changes affect subsequent requests.
- Greatest `run_seq` wins even when its `requested_at` is older or the attempt failed. A newer failure does not change active-publication readiness; unpublished candidate state does not create readiness or expose candidate details.
- Two synchronized connections prove publication and refresh updates cannot mix fields within a request. The next request observes the committed new state. Events coordinate the race rather than sleeps.
- Real transaction checks confirm one shared connection, read-only mode and repeatable-read isolation. Missing/inconsistent state and read/cleanup failures return safe errors, without successful partial output.
- `test_real_loopback_http_all_personas_in_both_publication_states` launches Uvicorn on a temporary loopback port and invokes the optional catalog checker for all three synthetic personas in both states. The existing auth-only real HTTP test also still passes.

The other database tests use FastAPI TestClient with real PostgreSQL. Only the explicitly named loopback tests establish a real network HTTP exchange. Both are automated evidence with disposable identities, not alayala's operator check or live publication proof.

### Local operator evidence — pending at initial handoff

[ME] Alayala owns this check with retained accounts and his configured local database/API. AI ran `python -m trinity.auth.check --help` to verify the flag is available; that command is not an operator acceptance result. A read-only probe found no reachable API on `127.0.0.1:8000` during handoff. AI did not start or reconfigure a retained service.

Follow the [operator instructions](../../backend/README.md#catalog-metadata-and-operator-check). Start the updated API with the existing `TRINITY_DATABASE_URL` in its terminal, then run `backend/.venv/bin/python -m trinity.auth.check --catalog` from a second terminal at the repository root. Password input is hidden. A false/null publication state is a valid result; this check never creates a publication.

Pending: observed safe pass/fail results for Viewer, Analyst and Admin using retained accounts, and alayala's explanation of the failed-newest-refresh/active-publication distinction. S24 frontend navigation stays in a later slice. Native PostgreSQL acceptance does not prove Docker/Compose, fresh installation, query isolation or live EIA/S3 readiness.

## Review and preservation

Code review covered the permission/data flow, closed response models, exception boundaries, unchanged auth test behavior and exact source diff. Final checks passed: `git diff --check`, 196 local Markdown targets/anchors across ten relevant documents, balanced fences and Python syntax parsing for new files. SHA-256 checks confirmed connector files, FINDINGS, dependency/lock files and OpenAPI remain unchanged from this task's start. Existing uncommitted SDD/product/API-navigation work was retained. This task did not alter source-data findings or analytical/connector contracts. Maintain data evidence — ongoing.

No commit, push, PR, retained-account provisioning, cloud mutation or live data publication occurred. Test credentials were generated only for disposable fixtures and not recorded.

Done: catalog code, offline regression, real database/HTTP verification and operator-check instructions.
Pending: alayala's retained-account operator check and human review; frontend/query slices remain separate.
Blocker: no automated failure remains; start the retained local API before the operator check.

Next: [ME] start the updated local API using the existing configuration.

## Subsequent retained-account operator result

The [Docker operator check](2026-10-04-catalog-docker-operator-check.md) subsequently passed for all three personas after explicitly approved migrations and private password entry. Earlier pending statements above describe the initial implementation handoff. This later run had no active publication; it does not replace the automated publication-state checks.
