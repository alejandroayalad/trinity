# Design: FastAPI and local login

Date: 2026-10-04
Status: Implemented and locally verified October 4, 2026 under the request to complete, commit and push this slice. See [implementation evidence](../../ai/sessions/2026-10-04-fastapi-local-auth-implementation.md). Compose and evaluator-owned checks remain separate.
Branch: `feat/fastapi-local-auth`
Basis: [proposal](proposal.md), [specification](spec.md), [A15 structure](../../docs/backend.md) and [A20 security](../../docs/security-contract.md).

## Human

Keep the existing FastAPI app and add local login. PostgreSQL holds people, sessions and application readiness. A password hash verifies a password without storing its readable value. A session token is a random secret; its stored digest lets the server recognize it without saving the reusable secret.

Login checks credentials and saves a session. Each later request checks the stored session and the current role before reading protected state. `/me` uses one database snapshot so its readiness, publication and Admin controls agree. A failed database read returns an error rather than a waiting screen.

## LLM

### 1. Modules and request flow

Follow the existing A15 ownership; add files only as needed:

| Location under backend/ | Responsibility |
|---|---|
| `src/trinity/main.py`, `config.py`, `errors.py` | App lifecycle/router registration, explicit API settings, bounded transport and sanitized Problem mapping. `/me` remains a small route delegating to auth service; no feature logic in main. |
| `src/trinity/auth/{router,schemas,dependencies,service,repository,permissions,seed}.py` | Login/logout/me schemas, verified principal, capability/dataset policy, password/session workflow, persistence and seed command. |
| `src/trinity/adapters/postgres.py` | Bounded synchronous Psycopg pool and service-owned transactions. Repositories accept the supplied connection and never commit independently. |
| `src/trinity/settings/`, `publication/`, `refresh/` | Only the read services/repositories/schemas needed for settings and app-entry state; no mutation routers or workers in this slice. |
| `migrations/`, `alembic.ini`, `tests/` | Ordered schema revisions, disposable PostgreSQL integration checks, HTTP/policy/error regressions. |

Use synchronous route/dependency functions for synchronous Psycopg and password work so they do not run on the async event loop. Keep pool construction inside the API lifespan, open with bounded/nonblocking availability checks, and close on shutdown. No connection starts at import time. Preserve `create_app()` tests through explicit injected settings/services; production startup must validate API settings and must not select an unauthenticated fallback app.

Protected flow: bounded transport checks → bearer parsing → session/user lookup → capability check → protected repository lookup → response serialization. Identity lookup is required before authorization; that is distinct from a protected settings/publication read. FastAPI validation dependencies must not accidentally reveal protected resource existence before permission checks.

Login: apply shared throttle → bounded password work → recheck the locked current user/hash/active role in a transaction → insert digest/expiry → commit → return token. Hash verification occurs outside a long row lock; compare the locked hash with the verified hash and fail safely if it changed. Logout checks and conditionally revokes the current session in one transaction. A later request observes committed deactivation/revocation; already authorized in-flight work may finish under A20.

### 2. Implemented configuration and cryptographic defaults (A21)

Extend explicit environment loading with `ApiSettings`; retain `env_file=None`, hidden validation inputs and secret-safe exception messages. `TRINITY_DATABASE_URL` is secret-bearing and must never appear in repr/log output. Implemented defaults: pool min 0/max 4 per API process; pool acquisition, connection, statement and lock waits bounded at 5 seconds each. Bound the complete authentication operation at 15 seconds, including throttle/lookup/hash/commit; component timeouts use its remaining budget. Do not return success after a timeout or keep an untracked hash job accepting new work. Verify cancellation/cleanup before calling the deadline enforced.

| Item | Implemented choice |
|---|---|
| Passwords | Standard-library `hashlib.scrypt`, N=131072, r=8, p=1, 16 random salt bytes, 64 output bytes, explicit 256 MiB maxmem. Versioned encoding stores algorithm, parameters, salt and digest. Parse only supported bounded parameters; use constant-time digest comparison. No Unicode normalization or truncation. Seed input: 15–1024 characters; login retains the canonical 1–1024 limit. |
| Sessions | `secrets.token_urlsafe(32)`; SHA-256 of the exact token stored as a unique digest. Absolute lifetime 8 hours, no sliding extension or refresh endpoint. Database time determines creation/expiry; expiry is exclusive. Limit header token length before hashing and accept exactly one Bearer credential. |
| Verification failures | Unknown/inactive user performs a dummy scrypt verification with the same work parameters. Unsupported/corrupt hashes produce a generic failure and sanitized internal diagnostic; unavailable crypto produces safe auth-unavailable, never plaintext/fast-hash fallback. |
| Transport | Bearer in Authorization only; no URL/cookie identity transport. No-store on login/logout/me and sensitive error responses. Bind local server to loopback; require HTTPS outside localhost. CORS disabled until frontend origins are explicitly selected; trust no forwarded client-IP header by default. |
| Runtime cost | At most two concurrent password verifications per API process; reject excess before scheduling hash work. Fix/document process count for local acceptance and measure memory/latency with full work factors. No Python dependency was added. |

OWASP prefers Argon2id and gives scrypt as its alternative; the implemented scrypt work factors follow its guidance. This choice reuses Python instead of adding a password dependency, with verified availability and one measured local baseline: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [Python hashlib](https://docs.python.org/3/library/hashlib.html#hashlib.scrypt). Python supplies cryptographic token generation and constant-time comparison: [Python secrets](https://docs.python.org/3/library/secrets.html). These references support the design. Runtime evidence is recorded separately in the implementation session. If scrypt cannot meet the verified local budget, stop and review a pinned password library; never lower security parameters silently.

Browser storage remains outside this backend slice. The future frontend must select token handling explicitly; this design does not approve persistent browser storage.

### 3. Migrations and seed transaction

Create ordered Alembic revisions, with no real credentials in revision files or `alembic.ini`:

| Revision purpose | Tables/state and reason |
|---|---|
| Authentication | Canonical `local_users`, `local_sessions`, plus internal `auth_login_limits`. Users have stable text IDs; sessions use UUIDs, unique digests, an indexed user reference and expiry/revocation fields. No cascading actor-history deletion. |
| App-entry read dependency closure | Full canonical columns/constraints for `shared_settings`, `refresh_runs`, `refresh_steps`, `data_versions`, `approvals`, `publication_events`, `active_publication`, `refresh_control`, `failure_warnings`. These provide setup, publication, current run, warning and action eligibility. Add cyclic foreign keys after the tables exist, inside the revision transaction. |
| Bootstrap | Insert `shared_settings(id=1)` with setup incomplete/schedule disabled, `active_publication(id=1)` with null event, and `refresh_control(id=1)` with no holder. Initialize revisions to zero and database UTC timestamps. No runs, candidates, events or personas are fabricated. |

This is the foreign-key closure needed for app-entry reads, not full refresh persistence. Defer `dataset_artifacts`, `validation_results`, `job_outbox` and `api_commands` to the feature that writes them. `data_versions.validation_step_id` and `approvals.validation_step_id` reference `refresh_steps`; the complete validation evidence and publication transaction remain future service obligations. Document row-local versus cross-row constraints; the existence of these tables does not authorize publication or prove A9/A16 write invariants.

No partial lookalike publication table and no hardcoded `data_ready=false`. Verify required singleton rows and joins; a missing row/dangling or inconsistent pointer is failure. Downgrade/destructive cleanup is tested only in a disposable database and never executed as an automatic application recovery action. Document backup/forward repair for retained real state.

Implemented seed entrypoint: `python -m trinity.auth.seed`, with hidden terminal prompts for missing persona passwords. No password command-line arguments, printed credentials or fixed example passwords. Acquire a transaction-scoped seed advisory lock, re-read all three names, validate existing personas and insert missing ones atomically. Existing credentials/roles/status/IDs never change. A mismatch rolls back the batch. Passwords for already present users are not required. Automated tests inject credentials in memory through the same service; README instructions must be verified before presented as working commands.

### 4. Shared login throttle

Use PostgreSQL atomic counters so restarting/adding an API process cannot reset the allowance. Implemented fixed windows: five attempts per username per 60 seconds, 30 per direct peer IP per 60 seconds and 60 globally per 60 seconds. Count successes and failures before password work. These are login-only limits; A19's analytical counter is separate.

`auth_login_limits` has `(scope, key_digest)` primary key, `window_start timestamptz` and nonnegative `attempts bigint`. Scope is username/peer/global. Digest bounded canonical key material; do not retain raw usernames/IPs in throttle keys or logs. Usernames are exact case-sensitive account names; no hidden normalization. Ignore client-selected forwarding headers. A global gate is locked first, then peer and username in a stable order; rollover and increments commit atomically using database time. Return 429 and remaining-window Retry-After before expensive work if any limit is exhausted. Storage failure returns 503 auth_unavailable.

The global allowance bounds new key creation. Delete expired counter rows in bounded maintenance batches without removing an active window. Counters contain no tokens or passwords. Fixed-window boundary bursts remain possible; the hash concurrency bound limits per-process memory. Tests must cover parallel reservations, rollover, rollback, restart and fake proxy headers.

### 5. Permissions and consistent app entry

Use an explicit role-to-capabilities mapping with exactly the strings in OpenAPI. Dataset visibility maps Viewer to `national` and Analyst/Admin to `national`, `facility`, `generator`. Policy helpers deny unknown roles and keys by default. Derive all human actor IDs from the verified principal. Do not let request models accept actor/role overrides.

`GET /me` reads identity plus app state within one read-only repeatable-read transaction. Its authentication dependency and entry service share that supplied connection/transaction; do not authenticate in a separate snapshot and then assemble app state. Resolve the singleton active pointer and join its event/version once; map only the six public Publication fields. Admin also reads shared settings, refresh control, current run, failure warning and candidate/approval metadata needed for canonical actions. Non-Admins never load or serialize Admin context. If setup is incomplete, Admin lands on setup; otherwise apply the spec landing table.

Build action flags from [canonical lifecycle rules](../../docs/api-contract.md#lifecycle-and-action-eligibility): setup blocks start, occupied lifecycle yields the appropriate active/review/publishing/failure blocker, and recovery applies only to the corresponding eligible run/candidate. Include relevant actions even when disabled, using existing BlockCode values. Use retained validation/warning/approval identities for eligibility, never a fresh S3 listing. Flags describe business eligibility; this slice exposes no command endpoints. Later commands must recheck actual eligibility in their mutation transaction, including file identity before publication.

`GET /settings` first requires `settings:read`, then serializes the canonical settings row and ETag. It does not offer setup writes. Permission test routes exist only inside tests and import production dependencies; they must never be registered by `create_app()`.

### 6. Errors and validation

A shared error mapper produces exactly the canonical Problem fields and bounded safe messages. Generate a server request ID; do not reflect arbitrary incoming headers. Map authentication persistence errors to auth_unavailable, later app-state dependency failures to dependency_unavailable and unexpected failures to internal_error. Always roll back failed transactions and release connections.

Enforce the byte limit while reading ASGI body chunks, including missing/false Content-Length; reject unsupported media types before decoding JSON. Strict models reject extra keys. Map validation failures to field names plus safe reasons only, excluding Pydantic input/exception context. Validate no-query/no-body rules explicitly. Capture neither request bodies nor Authorization headers in access/application logs, and do not log raw database exceptions/DSNs. Tests use unique secret canaries and check both response and captured logs.

No-data `/me` succeeds with the canonical waiting/setup payload. Future authorized analytical routes return `409 data_unavailable` after permission and applicable SQL policy checks; this slice must not add dummy analytical endpoints to demonstrate that response.

### 7. Verification and unresolved boundaries

Run fast pure policy/serialization checks first, HTTP checks next, and opt-in real disposable PostgreSQL migration/concurrency tests before acceptance. Real PostgreSQL is required; SQLite/mocks cannot prove constraints, locks, commit failure or cross-process limits. Test full scrypt parameters at least once and measure cost; smaller test factors alone do not establish runtime readiness.

A21 selects PostgreSQL 17.11 and `postgres:17.11-bookworm`. Native PostgreSQL tests passed; Docker/Compose was unavailable for execution. Frontend storage, full query/refresh integration and deployed runtime verification remain later work. A21 records these defaults under the explicit implementation request; A20 did not originally select them. Password verification uses a spawned child, with a one-second termination grace before kill/reap when the operation deadline expires. Request dependencies close their transactions before sending a successful response.
