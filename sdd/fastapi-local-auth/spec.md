# Specification: FastAPI and local login

Date: 2026-10-04
Status: Implemented and locally verified October 4, 2026 under the request to complete, commit and push this slice. See [implementation evidence](../../ai/sessions/2026-10-04-fastapi-local-auth-implementation.md). Compose and evaluator-owned checks remain separate.
Branch: `feat/fastapi-local-auth`
Basis: [proposal](proposal.md), [API contract](../../docs/api-contract.md), [OpenAPI](../../docs/openapi.json), [security contract](../../docs/security-contract.md) and [schema](../../docs/schema.md).

## Human

Three people can sign in locally: Viewer, Analyst and Admin. The server decides their access from stored account state. No caller can grant themselves a role. Logout, expiry and account deactivation remove access on subsequent requests.

An empty installation is valid: Viewers and Analysts wait for data; an Admin starts at setup. Losing the database is a service failure, not an empty installation. These rules must work through direct API calls.

## LLM

### Requirements

| ID | Required behavior |
|---|---|
| R01 | Preserve unauthenticated `/health` as process liveness. API settings are explicit, secret-safe and independent of EIA/S3/Redis. Imports open no connections, perform no migrations and create no accounts. Missing/invalid API configuration fails API startup safely; valid configuration with temporarily unavailable PostgreSQL still permits liveness and fails protected operations closed. |
| R02 | Use reviewed Alembic revisions and parameterized Psycopg queries for application state. Enforce canonical keys, role/expiry constraints and retained actor references. Bootstrap empty singleton state without a publication. Migration reruns do not destroy records; application startup never upgrades the database. |
| R03 | Provision exactly the three required named personas on an empty database. Operator-supplied passwords stay local. Reruns create only missing users and preserve existing IDs, hashes, roles, status and history. Report an existing persona-role/status mismatch safely; never silently repair it. Concurrent seed runs cannot duplicate accounts. |
| R04 | `POST /api/v1/auth/login` accepts only the canonical username/password fields. Valid active credentials with a known role return `200 LoginResponse` only after session persistence commits. Store salted password hashes and token digests; return the raw token only in the login response. Unknown user, wrong password and inactive user share `401 invalid_credentials`. |
| R05 | Every protected request resolves current session expiry/revocation, active user and current server-side role. Missing credentials return `401 authentication_required`; malformed/unknown/expired/revoked/inactive sessions return `401 invalid_session`; a missing/unknown stored role returns `403 forbidden`. Authentication storage failure returns `503 auth_unavailable`, with no protected effect. |
| R06 | `POST /api/v1/auth/logout` requires a valid session and `{}`; persist revocation before bodyless 204. Later use and repeated logout return 401. Other sessions and already accepted background work are unaffected. A failed revocation write never returns success. |
| R07 | Enforce one capability and dataset policy across dependencies/services. Viewer has the three canonical national/catalog capabilities; Analyst adds detailed preview and SQL; Admin adds six settings/refresh/review capabilities. Client roles/actor IDs grant no authority. Authorize before protected lookup; unauthorized/unknown datasets share safe `404 dataset_not_found` after applicable capability checks. |
| R08 | `/me` returns exactly `MeResponse`, including canonical capability strings, one consistent publication snapshot and Admin context only for Admin. No publication means false/null readiness; candidate files, validation success and S3 objects cannot set readiness. Broken state/dependencies return safe errors, never fabricated empty state. |
| R09 | Landing behavior follows the table below. Setup-incomplete Admin takes precedence even if a publication exists. Shared setup state is account-wide. Admin action flags reflect canonical workflow eligibility; they grant no authority and do not implement command endpoints. |
| R10 | Implement read-only Admin `GET /api/v1/settings` with canonical `SettingsResponse` and revision ETag. Viewer/Analyst receive 403 before settings access. This slice does not implement setup or settings mutation. |
| R11 | Use `application/problem+json` and the full canonical `Problem` shape. Preserve 401/403/404/409/413/415/422/429/500/503 meanings, `WWW-Authenticate` on 401, `Retry-After` on 429 and no-store on auth and identity responses. Never expose submitted values, hashes, digests, tokens, connection strings, stack traces or protected storage metadata. |
| R12 | Enforce the 64 KiB streamed body limit, content type, strict fields and supported query parameters. Reject nonempty GET bodies and invalid logout bodies. Bound credential verification, PostgreSQL waits and login attempts across API processes; unauthenticated traffic cannot create unlimited hash work. |
| R13 | Prove migrations, seed idempotence, login/session transitions, role changes, safe errors and empty-state `/me` with real local PostgreSQL plus direct HTTP tests. Separate policy/harness evidence from production route evidence and later full-product acceptance. |

### Landing behavior

| Identity/state | landing_screen | data_ready / publication | admin_context |
|---|---|---|---|
| Viewer or Analyst, no publication | waiting | false / null | null |
| Admin, setup incomplete | setup | Actual pointer state | Present |
| Admin, setup complete, no publication | refresh_runs | false / null | Present |
| Viewer, publication exists | national_dashboard | true / exact publication | null |
| Analyst, publication exists | explorer | true / exact publication | null |
| Admin, setup complete, publication exists | explorer | true / exact publication | Present |

### Acceptance scenarios

Automated coverage is recorded in [tasks](tasks.md) and the implementation session. S23 has agent-run real HTTP proof; the evaluator-owned repetition remains pending. Published/refresh states below use isolated synthetic database fixtures, never a production publication shortcut.

| ID | Given / When | Expected result | Requirements |
|---|---|---|---|
| S01 | Import backend/runtime modules without environment secrets; call health with configured API and unavailable DB | No import-time I/O; health 200; protected requests fail closed | R01 |
| S02 | Invalid/missing API settings; start configured API | Safe configuration failure; no DSN or credential in output | R01, R11 |
| S03 | Empty disposable PostgreSQL; upgrade twice | One migration head, required constraints and singleton rows; no publication/users invented by migration | R02 |
| S04 | Insert duplicate username/digest, invalid role, orphan session or nonpositive expiry | PostgreSQL rejects each write; failed transaction leaves no partial effects | R02 |
| S05 | Seed empty DB, repeat with different supplied passwords, then run two seed processes | Three unique personas; existing IDs/hashes/roles/status/history unchanged | R03 |
| S06 | Existing persona is disabled or has a mismatched role; run seed | Safe mismatch report, nonzero result, no reset or partial seed batch | R03 |
| S07 | Each persona supplies valid credentials; call login then me | 200, committed digest only, exact identity/capabilities and no secret fields in me | R04, R07, R08 |
| S08 | Unknown username, bad password or disabled account logs in | Same generic 401 shape; no session; comparable verification path | R04, R11 |
| S09 | Send role/actor fields, invalid JSON/media type, oversized streamed body or unknown query parameters | Canonical safe validation/size error; no reflected values or session | R04, R11, R12 |
| S10 | Missing/malformed/forged/expired/revoked token; call protected route | Correct 401 code and Bearer header; protected repository never called | R05 |
| S11 | Change role or deactivate account after login; next request | Current role used, or access denied; no role/session authority cache | R05, R07 |
| S12 | Inject unknown/missing role through a corrupt repository fixture | 403 and no protected read; do not weaken the DB role constraint to test this | R05 |
| S13 | Two sessions exist; logout one, reuse it, repeat logout | First 204 without body; revoked token gets 401; other session works | R06 |
| S14 | Authentication query/session commit/revocation fails | 503 auth_unavailable; no successful session/logout claim or protected effect | R04–R06 |
| S15 | Viewer/Analyst/Admin call real settings endpoint | 403/403/200 respectively; denied cases never read protected settings | R07, R10 |
| S16 | Exercise shared capability/dataset dependencies through test-only HTTP routes | Viewer cannot SQL/detail; Analyst/Admin can pass those guards; Viewer detail/unknown keys share 404; forged actors never trusted | R07 |
| S17 | Each persona calls me against empty DB, then setup-complete/no-publication fixture | Exact waiting/setup/refresh_runs outcomes; no EIA/S3/Redis calls | R08, R09 |
| S18 | Complete publication fixture or unpublished candidate exists | Only active event yields readiness; all six landing-table rows match | R08, R09 |
| S19 | Publication changes concurrently with me; app-state read fails or required singleton is missing | Internally consistent snapshot or safe failure; never mixed IDs/dates or false empty state | R08 |
| S20 | Admin has active/review/failed/publishing/terminal workflow fixtures | Canonical blocker/actions; no recovery command execution or authority from flags | R09 |
| S21 | Multiple API processes exceed login attempt budget; spoof forwarded headers | Shared limit, 429 with Retry-After before hash work; untrusted proxy headers ignored | R12 |
| S22 | Inject validation, database and unexpected exceptions with secret canaries | Safe Problem fields/headers and redacted captured logs; no raw input or infrastructure details | R11 |
| S23 | Evaluator follows documented local migration/seed/login checks | Three personas work via real HTTP/PostgreSQL; commands require no Clerk/EIA/S3 credentials for this slice | R13 |
| S24 | Boundary timestamps, Unicode passwords, distinct salts/tokens, hash verifier unavailable | Exact expiry, no password truncation, nonreused secrets; unsupported crypto fails closed | R04, R05, R12 |

### Proof boundary

Passing `/me` does not establish detailed-dataset or SQL security. S16 proves the shared guard using test-only routes; it does not prove future query execution. Every future catalog/preview/SQL/refresh route must gain direct allow/deny tests before full role isolation is claimed. No unpublished data or application table may become a user SQL source.
