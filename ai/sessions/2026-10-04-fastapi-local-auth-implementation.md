# FastAPI and local login — implementation and delivery

Date: 2026-10-04 (America/Merida)
Branch: `feat/fastapi-local-auth`
Base: `17864ee`, committed local main when the isolated worktree was created.

## Objective and authorization

[ME] Alayala requested: “complete the implementation commit an push this slice”. This authorizes the full SDD implementation and incremental commit/push delivery, superseding earlier per-step authorization stops. It does not claim an observed human walkthrough or authorize a PR, merge, live EIA/S3 operation or changes to unrelated findings work.

[YOU] AI implemented and tested the slice in the isolated `trinity-fastapi-local-auth` worktree. The original main worktree's findings/scripts changes were preserved. No subagents were used, following repository instructions. AI read CONTRIBUTING and kept public/slice docstrings and focused explanations. A20 controls local authentication; A21 records exact implementation choices and their delegated AI authorship. No password-library dependency or Python lockfile change was needed.

## Delivered flow

Input: local username/password from hidden seed/check prompts or the API. Login reserves shared attempt capacity, runs full-cost scrypt in a bounded spawned process, rechecks the locked current account and commits an opaque session digest before returning a token. Each protected request checks the current active user, role, expiry and revocation. `/me` shares a repeatable-read transaction with identity resolution and resolves only the active publication pointer. Admin settings reads authorize before repository access.

Implemented operations: `/health`, `/api/v1/auth/login`, `/api/v1/auth/logout`, `/api/v1/me` and read-only `/api/v1/settings`. The three persona seed command preserves existing credentials, roles, status, IDs and history. A separate operator HTTP command prints only safe check summaries. No setup/settings writes, analytical route, SQL executor, refresh worker, publication writer, browser flow or Clerk request is added.

Failure example: a real deferred PostgreSQL constraint rejects a session at commit. The API returns 503 auth_unavailable, returns no token and leaves no session. A database outage or missing app-state row never becomes a successful false/empty readiness response. Logout only succeeds after durable revocation. Transaction dependency teardown completes before a successful response is sent.

## Database and environment

The existing backend environment supplies CPython 3.14.8 and the pinned FastAPI/Psycopg/Alembic dependencies. `uv`, Docker and PostgreSQL were not initially on PATH. AI installed PostgreSQL 17.11 through Homebrew for isolated testing; Homebrew also installed/updated its formula dependencies and initialized its default cluster. That default cluster was not started or used. All test server work used private temporary Unix-socket clusters and removed only those clusters after stopping them. No existing database service was altered.

The authentication runner pins PostgreSQL 17.11, disables TCP listening, uses an owner-only temporary socket directory, rejects host authentication and creates `trinity_test_auth` solely for synthetic tests. The suite exercises real database constraints, locks and commits. `compose.yaml` pins `postgres:17.11-bookworm` for the local database only; Docker/Compose is not installed here, so that path was not executed. The supplied image/tag and initialization behavior were checked against the [official image documentation](https://hub.docker.com/_/postgres).

Alembic creates canonical auth/session state, internal login counters and the foreign-key dependency closure for app-entry reads. It bootstraps empty singletons and creates no credentials, runs or publication events. Dataset artifacts, validation results, outbox/commands and all refresh/publication write invariants remain later implementation. Row constraints here are not proof of the later publication transaction.

## Checks and measured results

The following commands used the existing interpreter at `../trinity/backend/.venv/bin/python` (invoked through its resolved path) with `PYTHONPATH=backend/src`, from this worktree root:

```bash
PYTHONPATH=backend/src ../trinity/backend/.venv/bin/python backend/tests/run_local_auth_checks.py
PYTHONPATH=backend/src ../trinity/backend/.venv/bin/python -m unittest discover -s backend/tests -q
```

- Focused acceptance: 43 tests passed in 35.153 seconds, including 25 real PostgreSQL tests and 18 offline auth checks. After the final settings-module and bounded-buffer review, all 43 passed again in 35.452 seconds.
- Full regression: 228 discovered, 203 passed, 25 opt-in PostgreSQL checks skipped in the ordinary offline command; 30.288 seconds. Those 25 were exercised by the separate acceptance command above. The final full regression rerun passed the same 203 checks with 25 opt-in skips in 27.936 seconds.
- Full scrypt benchmark at selected parameters: 0.54 seconds for one synthetic input. Tests use the full parameters, unique salts and Unicode input; no reduced-cost test setting was substituted.
- Real HTTP: started a loopback Uvicorn process with access logs and proxy-header trust disabled; the shared operator-check function verified login, identity, settings permissions, logout and subsequent denial for all three personas.
- Additional boundaries: concurrent seed runs, shared pools and separate throttle processes, five/30/60 attempt limits, rollover, forged-token denial before publication lookup, role changes/deactivation, expiry/revocation, deferred commit failure, rollback, consistent snapshots and secret-canary checks on responses/logs.

`compileall` completed for changed source/migrations/tests. Final static checks passed for 14 changed/new Markdown files, 248 local links, 67 anchors, 21 unique decision IDs, 13 requirement IDs and 24 scenario IDs. Python AST parsing and whitespace checks covered new/untracked files too. The repository has no configured formatter/linter/type checker. The existing Starlette/HTTPX deprecation warning remains; it was not resolved by changing selected dependencies. A fresh locked installation, Docker/Compose execution, frontend handling, evaluator-owned walkthrough and full product/remote runtime checks did not run.

## Corrections during implementation

The first offline auth run revealed that a missing-token test accessed the service attribute before parsing the header. Parsing now precedes service access. The first PostgreSQL runner rejected Homebrew's version suffix despite matching version 17.11; its version check now permits that suffix while retaining the exact numeric version. The first full suite exposed an older health test with no API settings; it now supplies API-only configuration and still proves no EIA credentials are needed.

Review also required function-scoped authentication dependencies so transaction teardown cannot follow a successful HTTP response. A regression injects teardown failure and receives 503. Settings remains in its A15 feature router/service. Oversized body chunks are rejected before extending the retained buffer. These corrections did not weaken credential, permission or persistence checks.

## Delivery and remaining evidence

Implementation/tests/database setup were committed as `2ce4c59` (`feat(auth): implement local login and role-aware app entry`). SDD/contracts/setup guidance and this evidence record form the second focused commit. The authorized push targets only `origin/feat/fastapi-local-auth`; the final handoff reports its result and local/remote head comparison. No history rewrite, PR or merge is included.

Done: local-login implementation and native PostgreSQL/HTTP/offline acceptance.
Pending at this record: the authorized documentation commit/push and final remote-head comparison. Separate operator evidence remains: retained persona passwords, evaluator walkthrough, fresh installation and Compose execution.
Blocker: none for this slice's code delivery; Docker/Compose execution is unavailable on this machine.

Next: [ME] follow `backend/README.md` at “Local API and three personas” to provision your own retained local accounts.
