# Tasks: FastAPI and local login

Date: 2026-10-04
Status: Implementation completed under alayala's explicit request to complete, commit and push this slice. Local acceptance passed; delivery state is in the [implementation session](../../ai/sessions/2026-10-04-fastapi-local-auth-implementation.md).
Branch: `feat/fastapi-local-auth`
Basis: [proposal](proposal.md), [specification](spec.md), [design](design.md), A21.

## Human

Local login now works for Viewer, Analyst and Admin. The server checks current sessions/roles, denies invalid identities, and returns waiting/setup state before publication. Read-only settings is Admin-only. The user authorized the complete implementation and Git delivery; that supersedes the earlier per-step authorization gates without claiming a human walkthrough happened.

## LLM

### Step 1 — Maintain data evidence — ongoing

- [x] [YOU] Preserved existing findings, connector/preparation code and unrelated work in the original main worktree. Synthetic auth fixtures do not create anomaly findings or prove the separate real S3/live gate.
- [x] [ME] Authorized complete implementation, commit and push. [YOU] Recorded exact implementation defaults and AI authorship in A21.
- [ ] [YOU] Continue maintaining real data evidence as future slices consume source records. This ongoing activity remains open.

### Step 2 — Configuration and PostgreSQL foundation

- [x] [YOU] Verified CPython 3.14.8, existing locked dependencies and full-cost scrypt. Selected native PostgreSQL 17.11 and pinned the database-only Compose tag.
- [x] [YOU] Implemented explicit API settings, lazy bounded Psycopg lifecycle, transaction budgets and Alembic revisions without automatic migration/seed.
- [x] [YOU] Verified upgrades/reruns, disposable downgrade/rebuild, empty singleton state, role/session constraints and transaction rollback on real PostgreSQL.
- [x] [YOU] Preserved independent EIA/S3 configuration and health liveness. Updated the old health test to supply API configuration while still omitting EIA credentials.
- [ ] [ME] Execute the supplied Compose configuration on a Docker-capable machine. Native PostgreSQL evidence does not establish container startup.

### Step 3 — Personas, credential verification and sessions

- [x] [YOU] Implemented hidden-input seed flow, concurrent-safe atomic provisioning, existing-account preservation and mismatch reporting.
- [x] [YOU] Implemented salted scrypt, bounded spawned verification, opaque token/digest persistence and shared PostgreSQL login counters.
- [x] [YOU] Verified login/logout, expiry, account deactivation/current-role changes, forged-token denial and rollback on session/revocation failures.
- [x] [YOU] Proved a real deferred PostgreSQL commit failure returns no token or committed session. Tested multi-process throttle reservations and per-peer/global limits.
- [ ] [ME] Provision retained local persona accounts using your own passwords. The acceptance runner created and removed only synthetic disposable accounts.

### Step 4 — Permissions, app entry and safe HTTP behavior

- [x] [YOU] Implemented the canonical capability/dataset policy and real Admin-only settings reads. Denied calls do not reach protected repositories.
- [x] [YOU] Verified all landing-table outcomes, unpublished-candidate exclusion, consistent publication snapshots and distinct dependency failure handling.
- [x] [YOU] Implemented Admin blocker/actions, strict bodies/queries, streamed 64 KiB limits, safe Problem fields and no-store/request-ID headers.
- [x] [YOU] Tested critical review/publishing/publication-failure actions and approval binding; checked error responses/logs for secret canaries. Test-only SQL guards are absent from the production app.
- [ ] [ME] Explain why a database outage returns 503 instead of `data_ready=false`. No observed human explanation is claimed.

### Step 5 — Direct API acceptance and handoff

- [x] [YOU] Added an isolated PostgreSQL runner and a hidden-input operator HTTP check. Verified three personas against a real loopback Uvicorn server.
- [x] [YOU] Ran focused authentication and full backend regression tests. Results and exact runtime boundaries are in the session; opt-in skips were exercised separately.
- [x] [YOU] Updated setup/run/seed/test instructions, canonical implementation references, SDD state and AI contributions; reviewed source and documentation diffs.
- [ ] [ME] Repeat the persona check with retained accounts and perform a fresh locked installation/Compose walkthrough. Agent acceptance is not evaluator-owned evidence.
- [x] [ME] Authorized incremental commits and branch push. No PR/merge was requested; actual commit/push results belong in the session and final handoff.

### Acceptance coverage

| Scenarios | Evidence |
|---|---|
| S01–S04 | API configuration/liveness/import tests; actual Alembic upgrade/rerun/downgrade and PostgreSQL constraint tests. |
| S05–S09 | Concurrent empty seeding, unchanged existing users, mismatch denial, real login/denials and strict transport/credential tests. |
| S10–S16 | Forged/malformed/expired/revoked sessions, current roles, corrupt-role resolver fixture, real commit/revocation failures, settings allow/deny and test-only analytical guards. |
| S17–S20 | All landing-table states, candidate/pointer distinction, repeatable-read race, missing state/failed reads, review/publishing/retry approval and permanent-error handling. Full future lifecycle-command implementation remains separate. |
| S21–S24 | Multi-process/shared-pool counters, peer/global limits and rollover, canary-safe errors/logs, real HTTP persona flow, full-cost Unicode/salt/hash/deadline checks. S23's human repetition remains open. |

From `backend/`, the normal command is `uv run --locked python -m unittest discover -s tests -v`. It skips PostgreSQL acceptance unless explicitly enabled. Run `uv run --locked python tests/run_local_auth_checks.py` for isolated real PostgreSQL/HTTP acceptance. The implementation machine used the existing pinned Python environment because `uv` was not on PATH; exact executed commands are recorded in the session.

No formatter/linter/type checker is configured in `pyproject.toml`. Do not infer SQL execution, DataFusion isolation, refresh/publication writes, fresh-clone startup or deployed runtime acceptance from these results.
