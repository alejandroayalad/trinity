# Docker local setup — API and PostgreSQL

Date: 2026-10-04. Branch: `feat/docker-local`, based on `main` at `d46fe19`. Mode: implementation.

## Objective

Run the existing API and PostgreSQL with Docker Compose for local development. Keep credentials outside the image, keep database data, publish only on localhost, and document configuration and migration steps. Decision context: A19 (Docker Compose for local execution), A17 (exact versions), A21 (PostgreSQL 17.11, explicit migrations).

## Contributions

- [ME] alayala requested the Docker setup and its constraints, then asked for a Docker-only branch and pull request without unrelated feature work.
- [YOU] AI inspected the existing `compose.yaml` (database only), `backend/pyproject.toml`, `uv.lock`, `alembic.ini`, `migrations/env.py`, `trinity.config.ApiSettings` and the seed/check commands. It extended the existing Compose file instead of creating a second one, added `backend/Dockerfile`, `backend/.dockerignore` and `backend/docker-entrypoint.sh`, ran the checks below and updated `backend/README.md` and `README.md`.

## Choices made during implementation

- **One image, explicit migrations.** The API image also runs `alembic` and the seed command through `docker compose run --rm api …`. No migration runs on startup, which keeps the A21 rule "no existing database is migrated automatically".
- **Password as a Compose secret.** `TRINITY_POSTGRES_PASSWORD` stays in the shell. Compose mounts it at `/run/secrets/postgres_password`. PostgreSQL reads it through `POSTGRES_PASSWORD_FILE`. The API gets a password-free `TRINITY_DATABASE_URL`; the entrypoint exports libpq `PGPASSWORD` from the secret file. This also removes the need to URL-encode the password.
- **No `read_only` root filesystem.** First attempt used `read_only: true`. Compose refused: "cannot create secret … in read-only service api: `file` is the sole supported option". A file-based secret would need a password file on disk, so `read_only` was dropped. `cap_drop: ALL`, `no-new-privileges` and a non-root user (UID 10001) remain.
- **Base images.** `python:3.14.8-slim-bookworm` (matches `.python-version`), `ghcr.io/astral-sh/uv:0.12.23` (matches `required-version`), `postgres:17.11-bookworm` (unchanged). All tags were confirmed with `docker manifest inspect`.

These are implementation details inside A19/A21, not new entries in `DECISIONS.md`. A21's evidence line still says Docker/Compose startup is unverified; alayala should decide whether to update it.

## Checks and results

The setup was first built and tested in another working tree. This record reports the repeat run on this branch's own code. That run used a throwaway Compose project (`-p trinity-verify-main`) with a generated password and synthetic persona passwords. alayala's own `trinity` stack was using ports 8000/15432 at that time, so a temporary override file moved the throwaway project to `127.0.0.1:18000` and `127.0.0.1:25432`. The project, its volume, the override and the temporary password files were removed afterwards. alayala's running stack was not changed.

| Check | Result |
|---|---|
| Unset `TRINITY_POSTGRES_PASSWORD` | `docker compose up` exit 1: secret requires the variable. Passed (fails closed). |
| Empty password | PostgreSQL container exits 1 before init. Passed (fails closed). |
| Image build | `uv sync --locked --no-dev` succeeded on linux/arm64. Image 758 MB. Runs as `trinity` (10001). No `.env` file in the image. `trinity.main`, pyarrow 25.0.1, datafusion 54.0.0 and sqlglot import. |
| Startup | `docker compose up -d --build --wait`: postgres healthy, api healthy. |
| Before migration | `/health` 200; login 503. |
| Migration | `docker compose run --rm api alembic upgrade head` exit 0; `alembic current` → `0002_app_entry (head)`. |
| DB connectivity | After migration, unknown-user login 401 (database read succeeds). |
| Personas | Synthetic seed created viewer/analyst/admin; rerun created none. `trinity.auth.check.check_persona` passed for all three: landings `waiting`, `waiting`, `setup`. |
| Credential exposure | Generated password found 0 times in `docker inspect` (both containers), `docker compose config`, container logs and `docker history`. |
| Loopback only | Published ports bound to `127.0.0.1` only; request to the LAN IP refused. |
| Persistence | `docker compose down` then `up`: 3 users and `0002_app_entry` still present. Wrong password over TCP: `password authentication failed`. |
| Backend tests | With `TRINITY_TEST_DATABASE_URL` pointing at a `trinity_test_docker` database in the throwaway container: 248 tests OK. Without it: 248 OK, 25 skipped. The existing local virtual environment was used with `PYTHONPATH` set to this branch's `src`. |

## Corrections found during the run

- `read_only` conflicts with environment-sourced secrets (see above).
- `docker compose exec` skips the image entrypoint, so `PGPASSWORD` is absent there and database work fails. Database commands must use `docker compose run --rm api …`. Documented in `backend/README.md`.
- The test fixture refuses databases whose URL lacks `/trinity_test_`. A first test run against a `trinity` database failed by design; a `trinity_test_docker` database was then used.

## Not verified

- The interactive `seed` and `auth.check` commands with a real terminal. Their TTY guard rejected piped input by design; the same functions were called directly with synthetic passwords instead.
- alayala's own walkthrough with his own password and persona accounts.
- Linux x86_64 build, and Compose versions other than v5.5.1.
- EIA connector, S3 preparation, Redis/BullMQ and per-query containers in Compose (not implemented in Compose).

## Open questions

- Should A21's evidence line in `DECISIONS.md` record the Compose verification?

## Next action

[ME] Run steps 1–3 of "Run with Docker Compose" in `backend/README.md` with your own password.
