# Trinity Python backend

The backend exposes process liveness at `GET /health`, the existing evidence-only extraction command, and a separate preparation command. Preparation retrieves a fixed window, freezes exact Parquet, validates saved files and stores a verified unpublished bundle through a trusted S3 adapter. Offline command tests pass; [October 1–2 live preparation and independent S3 readback](../evidence/live-preparation/2026-10-04-october-1-2/README.md) also passed with the recorded uncommitted parser correction. The candidate remains unpublished; full-history and fresh locked setup are not established. Local login/logout, `/me`, catalog metadata, Admin settings reads, PostgreSQL migrations and three-persona provisioning are implemented. The SQL backend is implemented separately; see [SQL setup and verification limits](SQL.md). Preview/dashboard rows and refresh workers remain pending.

## Setup

Use CPython **3.14.8** and **uv 0.12.23**, as selected in A17. The Python patch is recorded in `.python-version`; `pyproject.toml` enforces the uv version. From the repository root:

```bash
cd backend
uv sync --locked
```

This installs the package and pinned backend dependencies from `uv.lock`. A changed dependency definition without an updated lockfile must fail the locked installation. Installation and imports require no secrets or external services. API startup requires `TRINITY_DATABASE_URL`; health does not require a working database or EIA/S3/Redis credentials.

## Local API and three personas

This slice exposes `GET /health`, `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/me`, `GET /api/v1/catalog`, `POST /api/v1/queries` and Admin-only `GET /api/v1/settings`. The static product contract still describes later routes; those routes are not implemented here.

Use PostgreSQL **17.11**. Root `compose.yaml` supplies PostgreSQL, pinned to `postgres:17.11-bookworm`, and the API built from `backend/Dockerfile`. Both use loopback ports; the database uses a persistent named volume. The [official image](https://hub.docker.com/_/postgres) supports this tag and password initialization from a file. No existing database is migrated automatically. You can run the API in Docker (next section) or natively (steps 1–4 below). Both paths use the same Compose database.

### Run with Docker Compose

Requires Docker Compose with support for environment-sourced secrets. Verified with Docker 29.8.1 and Compose v5.5.1 on macOS arm64.

| Setting | Where it comes from |
|---|---|
| `TRINITY_POSTGRES_PASSWORD` | Your shell only. Compose passes it as the secret `/run/secrets/postgres_password` to both containers. It is not in the image, the database URL, `docker inspect` or `docker compose config`. |
| `TRINITY_DATABASE_URL` | Set in `compose.yaml` without a password: `postgresql://trinity@postgres:5432/trinity`. `backend/docker-entrypoint.sh` reads the secret into libpq `PGPASSWORD`. |
| Ports | API `127.0.0.1:8000`, PostgreSQL `127.0.0.1:15432`. Nothing is published on other interfaces. |
| Data | Named volume `trinity_postgres_data`. It survives `docker compose down` and image rebuilds. `docker compose down -v` deletes it. |

The image uses CPython 3.14.8 and uv 0.12.23, installs only from `uv.lock` (`uv sync --locked --no-dev`) and runs as a non-root user. `backend/.dockerignore` keeps `.env` files, `.venv`, `artifacts/` and tests out of the build context.

1. From the repository root, supply the password and start both services. The API waits until PostgreSQL is healthy:

   ```zsh
   read -rs 'TRINITY_POSTGRES_PASSWORD?Local PostgreSQL password: '
   export TRINITY_POSTGRES_PASSWORD
   docker compose up -d --build --wait
   ```

   An unset password stops `up` with an error. An empty password stops PostgreSQL before it creates the database. PostgreSQL uses the password only when it first creates the volume; a later different value does not change it and logins fail.

2. Apply migrations and create the three personas. Use `docker compose run`, not `docker compose exec`: `exec` skips the entrypoint, so the database password is not available. `run` gives the seed command the terminal it needs for hidden password input.

   ```zsh
   docker compose run --rm api alembic upgrade head
   docker compose run --rm api python -m trinity.auth.seed
   ```

   Before migration, `/health` returns `200` but login returns `503 auth_unavailable`.

3. Check the API. `/health` reports process liveness only. The persona check does not use the database password, so `exec` is correct here:

   ```zsh
   curl -s http://127.0.0.1:8000/health
   docker compose exec api python -m trinity.auth.check --catalog
   ```

4. Stop the services and keep the data with `docker compose down`. Rebuild after code changes with `docker compose up -d --build --wait`. New migrations need step 2 again.

All host clients reach the containerized API through one Docker gateway address. The per-peer login limit (30 per 60 seconds) therefore applies to all local clients together. The EIA connector, S3 preparation, Redis/BullMQ workers and query containers are not part of this Compose setup yet.

### Run the API natively

1. From the repository root, supply a local database password and start PostgreSQL. In **zsh**, the hidden prompt keeps the value out of shell history:

   ```zsh
   read -rs 'TRINITY_POSTGRES_PASSWORD?Local PostgreSQL password: '
   export TRINITY_POSTGRES_PASSWORD
   docker compose up -d --wait postgres
   ```

2. Export `TRINITY_DATABASE_URL` locally. For Compose use the shape `postgresql://trinity:<URL-encoded-password>@127.0.0.1:15432/trinity`. Enter the complete real URL through a hidden prompt; `.env.example` contains only a placeholder. No `.env` file is loaded automatically.

   ```zsh
   read -rs 'TRINITY_DATABASE_URL?Local PostgreSQL URL: '
   export TRINITY_DATABASE_URL
   cd backend
   uv run --locked alembic upgrade head
   uv run --locked python -m trinity.auth.seed
   ```

   The seed command prompts only for missing `viewer`, `analyst` and `admin` passwords, 15–1024 characters. It stores salted hashes. Reruns preserve IDs, passwords, roles, account status and history. An existing persona with a different role or inactive status produces a safe failure; there is no automatic reset. Seed and migration commands must finish before product requests can succeed.

3. Start one API process from `backend/`:

   ```bash
   uv run --locked uvicorn trinity.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
   ```

   Each API process permits two simultaneous password verifications and four database connections. The local acceptance target is one API process. Use HTTPS outside localhost; this slice configures no public ingress, proxy trust or browser token storage. Disabling access logs avoids recording attacker-supplied URL values.

4. In a second terminal with the locked environment, run the safe HTTP check:

   ```bash
   cd backend
   uv run --locked python -m trinity.auth.check
   ```

   It prompts for the three passwords, checks login → `/me` → settings permission → logout → denial, and prints only role/check/landing summaries. It never prints tokens or passwords. Do not paste login responses into logs or commit local secret files.

An empty installation returns `waiting` for Viewer/Analyst and `setup` for Admin. Once shared setup exists, Admin gets `refresh_runs` until publication. Setup writes and refresh execution are later slices. A stored candidate does not become published merely because it exists. Unavailable authentication storage returns `503 auth_unavailable`; app-state read failure returns `503 dependency_unavailable`, not an empty-data response.

Sessions expire after eight hours and do not slide. Logout revokes only the current session. Every protected call re-reads the active user, session and current role. Shared PostgreSQL login limits are 5 attempts/username, 30/direct peer and 60 globally in each 60-second window; `429` includes `Retry-After`. Password work runs in bounded child processes and uses full-cost scrypt. Credentials, token digests, raw database errors and storage paths are absent from public responses.

### Run authentication and catalog acceptance

From `backend/`, with PostgreSQL 17.11 binaries installed:

```bash
uv run --locked python tests/run_local_auth_checks.py
```

On macOS the default binary directory is `/opt/homebrew/opt/postgresql@17/bin`; elsewhere export `TRINITY_PG_BIN` to the directory containing `postgres`, `initdb`, `pg_ctl` and `createdb`. The runner verifies version 17.11, creates a temporary cluster with no TCP listener and a private owner-only Unix socket, seeds synthetic users, runs real PostgreSQL/HTTP checks and stops/removes only its own temporary cluster. It never connects to the configured application database. Tests require a non-root OS user, as PostgreSQL initdb does.

The normal `unittest discover` run skips the opt-in database class when `TRINITY_TEST_DATABASE_URL` is absent. The runner enables auth and catalog tests, including real loopback HTTP checks. Do not point this test variable at retained data: the opt-in tests reset the test schema. Test-only analytical guards establish policy behavior, not SQL/DataFusion/refresh endpoint security.

The implementation session records the exact runtime commands/results. Compose startup, the locked image install and a synthetic three-persona flow were verified on October 4, 2026 ([Docker session](../ai/sessions/2026-10-04-docker-local-setup.md)); an evaluator-owned walkthrough remains separate verification. Migration downgrade was tested only inside the disposable cluster; never use downgrade as recovery for retained application history.

### Catalog metadata and operator check

`GET /api/v1/catalog` accepts the existing bearer session, no parameters and no body. Viewer receives only `national_outages`; Analyst/Admin receive all three analytical definitions. The response contains columns, units, keys, filter names, the national metric definition and safe freshness. It reads no analytical files or live source data.

Before publication it returns metadata with `data_ready=false` and `publication=null`. Once a publication exists, its dates remain distinct from `last_refresh`, which reports the greatest-sequence attempt even if it failed. Database failure returns an error rather than false empty state. Viewer keeps this metadata API access for dashboard support; Catalog and SQL navigation remain hidden in the future Viewer interface. This slice implements no frontend, preview rows or SQL execution.

The three evidence categories remain separate:

| Evidence | Current result |
|---|---|
| Offline tests | 239 delivery regression checks passed, including 16 catalog checks; 36 opt-in database tests were skipped in that command and exercised separately below. |
| Automated PostgreSQL/HTTP | The disposable runner passed 70 checks: 36 database-backed checks and 34 offline checks. Catalog's real HTTP test exercised all personas before and after synthetic publication. |
| Your local operator check | Passed October 4 with retained Docker accounts and privately entered passwords for all three personas, with no active publication. See [operator evidence](../ai/sessions/2026-10-04-catalog-docker-operator-check.md). |

For the operator check, keep your existing PostgreSQL setup and accounts. Start or restart the API from the updated checkout with `TRINITY_DATABASE_URL` set in that terminal. Using the existing virtual environment, from the repository root:

```bash
backend/.venv/bin/python -m uvicorn trinity.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
```

In a second terminal at the repository root:

```bash
backend/.venv/bin/python -m trinity.auth.check --catalog
```

The check prompts privately for each persona password and checks login, identity, settings permissions, permitted catalog metadata, logout and post-logout denial. It prints only a safe pass/fail summary for each persona. Empty publication state is a valid check outcome. It never publishes data or changes roles. Keep the default command without `--catalog` for the original auth-only check. The operator check does not replace the automated race, corrupted-state or outage tests.

With uv available, the equivalent checker from `backend/` is `uv run --locked python -m trinity.auth.check --catalog`. This implementation used the existing CPython 3.14.8 virtual environment because uv was absent from the agent's PATH; every installed direct dependency matched its declared pin. That is not a fresh locked-install result. No new migration or dependency was added. See the [catalog implementation evidence](../ai/sessions/2026-10-04-catalog-permissions-implementation.md).

## EIA configuration

Set `EIA_API_KEY` in the process environment before calling `load_eia_settings()` from `trinity.config`. In Bash, enter it without writing the value into shell history:

```bash
read -rsp 'EIA API key: ' EIA_API_KEY
export EIA_API_KEY
```

The loader reads the current environment on each call. It rejects a missing, empty or whitespace-only value with `ConfigurationError`. It returns a `SecretStr`, which masks the value in normal representations and JSON output. Only trusted connector code should call `.get_secret_value()` when preparing an EIA request; never log that value or a URL containing it.

`.env.example` documents the variable. No `.env` file is loaded automatically. Loading configuration makes no EIA request and does not verify whether the key is valid. Imports and `/health` do not require an EIA key.

## Run

### Fetch one EIA page

Use one `EIAClient` instance for all routes. Its constructor reads the environment; it owns one HTTPX AsyncClient and closes it on leaving the async context.

```python
from datetime import date
from trinity.connector.client import EIAClient

async def fetch_pages():
    day = date(2026, 10, 1)
    async with EIAClient() as client:
        national = await client.fetch_national_page(start=day, end=day, length=1)
        facility = await client.fetch_facility_page(start=day, end=day, length=1)
        generator = await client.fetch_generator_page(start=day, end=day, length=1)
    return national, facility, generator
```

The one-page methods accept `start` and `end` as dates, a nonnegative `offset` (default 0), and `length` from 1 to 5,000 (default 5,000). Each returns one validated response page, with at most three identical request attempts for temporary failures. Requests use daily frequency, all three measurements and ascending sorting by the route's daily key. The client uses HTTPS and rejects redirects. HTTPX I/O timeouts remain 30 seconds (10 seconds for connection setup); a separate 30-second total page deadline now covers all attempts, waits and response processing.

### Retry policy

Retry HTTP 429, 500, 502, 503 and 504 with at most **three total attempts**. Wait **one second** before attempt two and **three seconds** before attempt three. Do not wait after the final failure or a success. Connection/read/write timeouts, interrupted reads/writes and remote protocol errors use the same bounded policy.

HTTP statuses outside that allowlist, including 400/401, fail immediately. Arbitrary connection errors (which may indicate TLS/configuration problems), pool timeouts, local protocol errors, invalid JSON, HTTP-200 API error bodies and failed response validation are not retried.

Retries preserve route, date bounds, offset, page size and all other request parameters. A retry never resets either the page deadline or the enclosing route deadline. Expiry during a request or backoff stops further attempts. Caller cancellation propagates without retry. Page expiry reports `request_deadline`; route expiry reports `pagination_deadline`.

`EIAResponsePage.data` contains source rows with strings and unit metadata preserved. `response` retains sanitized source metadata; `total` is the parsed advertised count, `api_version` identifies the API release, and `warnings` preserves sanitized top-level warnings. Empty pages are valid. The facility advertised total is not used to infer completeness.

The one-page methods check the JSON envelope, daily frequency, row shape, identifiers, dates, requested window, units and page size. Paginated collection also checks duplicate keys, as described below. Decimal normalization, full coverage and cross-route reconciliation remain later stages. HTTP failures, API-body errors and malformed responses raise `EIAClientError` with safe `code` and optional `status_code`. Returned pages omit echoed request credentials. An HTTPX log filter masks the API key in request URLs without disabling logging; callers must still avoid logging raw credentials.

After exporting `EIA_API_KEY`, run this explicit live gate from `backend/`:

```bash
uv run --locked python tests/live_eia.py -v
```

It checks one page and then paginated extraction for each route on October 1, 2026. The paginated check uses a page size of 50, at most 25 page fetches and a 120-second deadline per route. Each page fetch can make up to three attempts. It compares local page/row counts and supplied totals under the route-specific rules below. This live gate passed on October 3, 2026 ([evidence](../evidence/2026-10-03-first-live-eia-run.md)). It is excluded from default test discovery. The routine tests use HTTPX MockTransport and synthetic data.

### Fetch all pages for a route

`fetch_national()`, `fetch_facility()` and `fetch_generator()` return an `EIACollection`. Use the same date arguments as the one-page methods:

```python
async with EIAClient() as client:
    result = await client.fetch_generator(
        start=date(2026, 10, 1), end=date(2026, 10, 1), page_size=50
    )
    records = result.data
    counts = (result.page_count, result.data_page_count, result.record_count)
```

Each collection starts at offset zero and advances by the actual number of returned rows. A short page or reaching the advertised total does not end collection. An empty page confirms exhaustion. Duplicate keys, repeated/overlapping pages and changing supplied totals fail the collection. National/generator totals must equal the final record count when supplied. Facility totals are preserved and compared, but a mismatch does not fail or stop collection under A5/A9.

| Result field | Meaning |
|---|---|
| `data` / `record_count` | Combined source rows and their count. |
| `pages` / `page_count` | Sanitized page responses and count, including the final empty probe. |
| `data_page_count` | Number of nonempty pages. |
| `advertised_total` | Stable total across pages where supplied; null if absent everywhere. |
| `total_matches` | Whether the final record count matches that total; null if no total exists. |
| `minimum_data_pages` | Ceiling of total/page size for national/generator; null for facility or missing totals. |

EIA supplies a record total, not a separate page count. `minimum_data_pages` is a derived lower bound: short nonterminal pages can increase the actual count. No expected count is invented when metadata is missing.

The implementation defaults to `max_pages=1000` (including the empty probe) and `timeout_seconds=300` for the entire route collection. Each page fetch permits at most three attempts, so network attempts are bounded by 3 × max_pages as well as the deadline. Result page counts count successful validated responses, not failed attempts. Both pagination bounds are configurable, not EIA guarantees or measured performance targets. Exhausting either limit raises `page_limit` or `pagination_deadline`; partial rows are never returned as success. These route-extraction bounds are separate from analytical query limits. The full-route methods now attach retrieval metadata on success and failure; see below. The preparation command below adds exact normalization, saved-file coverage/reconciliation checks and Parquet. Successful pagination is not proof that a candidate is ready for publication.

## Retrieve all three routes and save evidence

Set `EIA_API_KEY` in the process environment as described above. From `backend/`, run:

```bash
uv run --locked python -m trinity.connector --start 2026-10-01 --end 2026-10-01 --output /tmp/trinity-retrieval-2026-10-01.jsonl
```

Use a new output filename for each run. The parent directory must exist. The command reserves the file before making any request and refuses to overwrite an existing file. The output is JSONL: one JSON object per route, written and synced after that route finishes. Standard output contains the same route summaries without the large attempt list.

`retrieve_all()` in `connector/pipeline.py` uses one shared `EIAClient`, runs national → facility → generator sequentially, and keeps the same explicit date window. It continues after an individual route fails. It returns three `RetrievalResult` objects; only successful results contain an `EIACollection`. The command retains source response evidence in the JSONL file; it does not publish data or write Parquet. This fixed-window extraction command is not yet the full refresh pipeline or latest-national-date discovery.

Options: `--page-size` (default 5,000), `--max-pages` (default 1,000, including the empty probe), and `--timeout-seconds` (default 300 per route). These are per-route bounds. The three sequential routes can therefore take up to roughly three route deadlines plus output time.

| Exit code | Meaning |
|---|---|
| `0` | All three routes finished extraction successfully. This does not mean full data validation passed. |
| `1` | At least one route failed. Missing credentials produce three failed records without HTTP requests. |
| `2` | Invalid command syntax or output could not be created/written. |
| `130` | Cancelled. The interrupted route is recorded as `cancelled`; remaining routes are `skipped`. |

### Retrieval metadata

`fetch_national()`, `fetch_facility()` and `fetch_generator()` return `collection.metadata` on success. `EIAClientError`, `EIAInputError` (a `ValueError`) and `EIARetrievalCancelled` (an `asyncio.CancelledError`) carry `.metadata` on failure. Cancellation still propagates. The one-page methods retain their original return/error interface; full retrieval evidence belongs to the full-route methods and orchestration command.

`RetrievalMetadata` includes dataset/route, UTC `started_at`/`completed_at`, date bounds, frequency/sort fields, `pages_fetched`, `records_fetched`, `retries`, `final_status`, `error_code`, `error_message` and attempt evidence. Counters are local to each call, including concurrent calls on a shared client.

- `pages_fetched` counts responses that pass page validation, including the terminal empty probe. Failed HTTP attempts do not add pages.
- `records_fetched` counts rows from those pages. On success it equals `collection.record_count`. On failure it is evidence of fetched rows, not a usable partial collection; a page later rejected for duplicate keys or total disagreement is included.
- `retries` counts actual second/third HTTP attempts, summed across pages. An interrupted backoff does not count a retry that never started.
- Final states are `success`, `failed`, `cancelled` and `skipped`. Times for skipped/configuration-failed routes describe record finalization, with no HTTP attempts.

Each `RetrievalAttempt` records offset, requested length, attempt number within the page, UTC times, HTTP/API status, API version, advertised total, actual response row count and a safe error code. Shared route/frequency/window/sort details live on the parent record. `api_status=no_error_reported` only means no API error field appeared; it is not a validation pass. An in-flight request cancelled by a deadline has attempt code `interrupted` and the enclosing route has the specific deadline failure.

JSON response bodies are sanitized before serialization and hashing. `sanitized_response` stores the exact string whose UTF-8 bytes produce `response_sha256` (SHA-256). No request URL with a key, request headers, cookies or raw exception text is saved. Non-JSON bodies and absent responses have null body/checksum fields; arbitrary raw error text is deliberately omitted. Attempt row counts may exist even when page validation fails.

Evidence remains in memory until a route finishes, then the command flushes and syncs its line. Disk failure or a hard process kill can leave an incomplete output file; this command is not a durable worker/recovery system. A graceful cancellation records interrupted/skipped routes when output remains writable. Invalid command syntax stops before retrieval begins.

## Schemas and exact row parsing — Step 1

Historical delivery boundary: the 17/76-test results below describe the Step 1 working tree. Step 1 is in base commit `5e17656`; Steps 2–5 are implemented. See the current delivery record in tasks.md.

`trinity.contracts.datasets.DATASETS` defines the three Arrow schemas, table names and daily keys. `trinity.connector.normalize.normalize_row(dataset, row)` accepts an already sanitized source row and returns typed `values` and D01/D02 observation codes. It performs no I/O or readiness decision. Preserve the original sanitized row/retrieval evidence: parsing does not alter it, including on failure, and unknown fields stay there rather than becoming analytical columns.

The parser preserves identifiers and labels, validates dates/units, and parses decimal strings exactly. `863.4000000` retains its trailing zeros in the returned Decimal; Arrow scale-six conversion preserves the numeric value. `863.4000001`, overflow, numeric JSON measurements and invalid text fail with a safe `NormalizationError` containing field/code only. Missing optional labels/percentages become null. Complete diagnostic evaluation belongs to Step 3's `validate_candidate` function below.

From `backend/`, run focused offline checks with `.venv/bin/python -m unittest discover -s tests -p test_normalize.py -v`. Step 1 passed 17 focused tests and 76 total offline tests using the existing CPython 3.14.8/PyArrow 25.0.1 environment. `uv` was unavailable on that shell's PATH; the existing environment was used directly without dependency changes. These checks include in-memory Arrow conversion, not Parquet file round trips. See [tasks and the human-review gate](../sdd/parquet-preparation/tasks.md).

## Local frozen-file validation — Steps 2 and 3

`trinity.connector.parquet.freeze_files` takes already sanitized retrieval metadata, fixed dates and an existing trusted output directory. It reserves a new version and saves original response evidence, three exact Parquet datasets and a bound manifest. It preserves duplicate rows for validation to reject. It makes no network request.

`trinity.connector.validate.validate_candidate(root, expected_sha256)` takes that version directory and its retained manifest digest. It reopens saved files and produces all 16 required V01–V08 results, plus 23 dataset-scoped D01–D09 evaluations. Required failures or diagnostic errors block success. A successful report freezes the warning digest and count; `approval_required=True` means later Admin review is required. It does not grant approval or publish data.

Each call reserves `evidence/<attempt UUID>/` with `journal.jsonl`, one detail file per check/scope, and final `validation.json` and `diagnostics.json` summaries. Each journal result is flushed and synced before the next check. Revalidation uses another attempt directory; previous results remain unchanged. Cooperative cancellation or persistence failure raises `ValidationError`; keyboard/async cancellation propagates. Both retain an incomplete summary where writable. A hard kill can leave only the journal. Neither partial evidence nor a summary file alone establishes success.

`verify_validation(report)` rechecks a passing report, its completion journal, details and current file identities. Storage calls this guard before using the report. Changed files fail and retain a safe recheck record where writable. The preparation command below connects these stages.

Run the focused offline checks from `backend/` with the existing environment:

```bash
.venv/bin/python -m unittest discover -s tests -p test_validate.py -v
.venv/bin/python -m unittest discover -s tests -v
```

These tests use synthetic evidence and temporary Parquet files, including a killed test child for incomplete-attempt behavior. They do not use EIA credentials or S3. See [the task checklist](../sdd/parquet-preparation/tasks.md) for actual results and current review gates.

### Immutable storage library — Step 4

`trinity.connector.pipeline.store_candidate(report, storage)` accepts a passing `ValidationReport` and `trinity.adapters.s3.S3Storage`. It rechecks exact local files, reserves `<prefix>/<version UUID>/reservation.json` with a fresh token, and writes each object with `IfNoneMatch="*"`. The adapter hashes actual streamed GET bytes after each write. A first reservation conflict stops before data uploads. An ambiguous write succeeds only if readback proves identical bytes. Existing different bytes are never replaced.

The complete inventory includes all three Parquet datasets, manifest, original sanitized source evidence and saved validation/detail evidence. Storage execution journals stay local. `bundle.json` lists every remote member's path, size and SHA-256 plus the version, manifest, validation and warning identities. It uploads last. The stage rechecks all remote members before returning `StoredCandidate`, with `published=False`. Warnings retain `approval_required=True`; storage grants no approval.

Local `evidence/storage-<token>/` holds the upload plan, reservation body, synced progress journal and verified result or safe failure record. A partial prefix, bundle or `result.json` alone is insufficient. `verify_stored_candidate(report, receipt, storage)` checks the retained identities, complete local journal and all remote bytes. No resume, delete or repair operation is implemented; use a new preparation version after failure.

`load_s3_settings()` reads `TRINITY_S3_BUCKET`, `TRINITY_S3_PREFIX` and `TRINITY_S3_REGION` explicitly. Optional `TRINITY_S3_ENDPOINT_URL` must use HTTPS without user-info, a non-root path, query or fragment. Omit it for AWS. The adapter ignores ambient SDK endpoint overrides and uses the SDK credential provider chain; credentials are never command arguments or recorded settings. Imports do not resolve credentials. `.env.example` contains placeholders only and is not loaded automatically.

Each object is limited to 64 MiB, checked before upload. Storage uses a maximum 300-second budget, three attempts for temporary failures and one/three-second waits. SDK retries are disabled; connect/read timeouts are five/ten seconds. Deadline and cancellation checks run between operations and streamed chunks. A blocked SDK call can run until its socket timeout when the library runs alone. The preparation command adds hard process supervision. Failed validation, denied access and byte mismatches are not retried.

Run offline storage checks from `backend/`:

```bash
.venv/bin/python -m unittest discover -s tests -p test_s3.py -v
```

Tests use an injected conditional storage double and the pinned SDK's `Stubber`, with real temporary Parquet files. They prove local behavior and request shape, not deployed immutability. Before real-storage acceptance, separately verify a private prefix, policy-enforced conditional writes, no candidate-writer delete/version-delete or policy-changing rights, and no lifecycle deletion of retained candidates. An alternative endpoint must prove equivalent behavior. No bucket or policy is created here. See [AWS conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html) and [policy enforcement](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html). No live EIA/S3 check was run for this slice.

## Prepare a stored candidate — Step 5

Working directory: `backend/`. Use the locked environment from Setup, the EIA key loader described above, and an existing private S3 bucket with separately verified protection. Set `TRINITY_S3_BUCKET`, `TRINITY_S3_PREFIX` and `TRINITY_S3_REGION` in the process environment. Supply SDK credentials through your trusted local provider. Omit `TRINITY_S3_ENDPOINT_URL` for AWS; an alternative endpoint must meet the storage requirements above. `.env.example` is a reference, not an automatically loaded configuration file.

After configuring and authorizing live access, the implemented command is:

```bash
mkdir -p artifacts
uv run --locked python -m trinity.connector.prepare \
  --start 2026-10-01 --end 2026-10-03 --output-root ./artifacts
```

With the already installed environment, `.venv/bin/python` can replace `uv run --locked python`. To inspect syntax without credentials or external calls:

```bash
.venv/bin/python -m trinity.connector.prepare --help
```

Both dates are inclusive and must use `YYYY-MM-DD`, with `start <= end <= current UTC date`. The command labels the result `window_kind="explicit"`. A three-day reproduction does not claim full-history coverage or discover `latest_national`. Each invocation exclusively reserves a new version UUID under an existing output root; it never resumes, repairs or overwrites a previous version. The example `backend/artifacts/` directory is ignored by Git.

Input → extraction → exact files/manifest → validation/diagnostics → verified storage → parent-confirmed receipt. `connector/pipeline.py::prepare_candidate` reuses existing functions. `connector/prepare.py` runs it in a spawned trusted child. The parent syncs each stage event before allowing the child to proceed. Budgets are 300 seconds and 1,000 pages per extraction route, 120 seconds for freeze, 120 for validation, 300 for storage, and 1,440 seconds overall. On timeout or controlled cancellation, the parent terminates the child, escalates to kill after five seconds if needed, and confirms exit. These are command limits, not production-refresh service limits. [Python process controls](https://docs.python.org/3.14/library/multiprocessing.html#multiprocessing.Process.terminate) describe the underlying operations.

Under `artifacts/<version UUID>/`, `data/` holds the three Parquet files. The root holds `source-evidence.json`, `manifest.json` and, after storage, `bundle.json`. `evidence/retrieval.jsonl` durably retains each completed route before normalization. `evidence/<validation attempt>/` holds check details and summaries; `evidence/storage-<token>/` holds upload progress. `evidence/preparation/` holds safe inputs, the parent stage journal, the child receipt and the final result or failure. Changing supervisor/storage journals remain local; completed route and validation evidence is included in the stored bundle.

| Exit | Meaning |
|---|---|
| `0` | Child exited successfully; saved receipt and bundle agree. JSON output identifies version, manifest, validation attempt/check set, bundle, actual dates, warning count/digest and `published=false`. Warnings keep `approval_required=true`. |
| `1` | Stage failure, failed validation, timeout, unresolved storage, lost child or failed evidence persistence. Safe JSON identifies the stage and retained evidence location where available. |
| `2` | Invalid arguments, dates or configuration, including missing credentials. SDK credential failure can be discovered during storage; prior evidence remains. |
| `130` | Controlled cancellation, including Ctrl-C or SIGTERM. Available evidence remains; the child is stopped before return. |

Only the parent writes `evidence/preparation/result.json`, after confirmed child exit and receipt verification. A child receipt, partial prefix, bundle or missing final result is not command success. If validation fails, no upload starts. If storage fails, partial remote objects remain untouched and unpublished. Hard termination can lose the in-flight route; already synced route/check evidence remains where the filesystem permits. No command grants approval, writes application publication records or changes the active version.

Offline verification, with no EIA/S3 calls:

```bash
.venv/bin/python -m unittest discover -s tests -p test_prepare.py -v
.venv/bin/python -m unittest discover -s tests -q
```

Command tests use synthetic HTTP and injected storage inside real child processes, real temporary Parquet files and real termination signals. See [tasks.md](../sdd/parquet-preparation/tasks.md) for current counts and limits. The October 1–3 live command above reached validation after a parser correction but correctly failed because October 3 rows were absent. A separately authorized October 1–2 run passed all required checks and independent S3 readback; see the [exact evidence](../evidence/live-preparation/2026-10-04-october-1-2/README.md). The original three-day window remains unverified. The existing `python -m trinity.connector` extraction command remains available and unchanged.

## Start the API

```bash
uv run --locked uvicorn trinity.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
```

Open http://127.0.0.1:8000/health for liveness or http://127.0.0.1:8000/docs for the implemented API documentation. Liveness does not establish data readiness or healthy external services. The root `docs/openapi.json` remains the planned product contract; it includes operations beyond the running API.

## Check and build

```bash
uv run --locked python -m unittest discover -s tests -v
uv build
```

At October 4 closure, the existing CPython 3.14.8 environment passed 185 offline tests, including 18 focused preparation-command tests. The suite includes the earlier 59 health, configuration, mocked EIA client/pagination/retry, retrieval and command tests. Retry tests assert three-attempt exhaustion, exact backoff calls, permanent-error rejection, unchanged parameters, deadline handling and cancellation. Earlier dependency resolution, locked installation, package compatibility checks and backend-module imports passed. The initial scaffold also passed source/wheel builds. Starlette still emits the existing HTTPX test-client deprecation warning. The live gate and the fixed-window extraction command passed against the EIA API on October 3, 2026. Other external-service integrations have not been tested.

## Layout and next slice

`src/trinity/main.py` creates the FastAPI application. `src/trinity/__init__.py` has no infrastructure initialization. `tests/` contains standard-library unittest tests, so no additional test framework is required.

Follow A15's feature layout in [backend architecture](../docs/backend.md) as behavior is added. Steps 1–5 are implemented. Alayala authorized Step 5 delivery and session closure; real storage protection and live preparation remain separate verification gates. See the [session close and S3 handoff](../ai/sessions/2026-10-04-parquet-preparation-steps-2-5-close.md). The lock includes the selected API, environment configuration, HTTP, PostgreSQL, migration, PyArrow/DataFusion/SQLGlot, Redis/BullMQ and S3 libraries. HTTPX is a runtime dependency for the connector. Clerk is omitted because alayala selected local login; authentication implementation and contract reconciliation remain pending. The build uses uv_build 0.12.23. Installing these libraries does not implement their features or verify their external services.

Current catalog delivery: [review and test evidence](../ai/sessions/2026-10-04-catalog-review-and-delivery.md), [SDD reading order](../sdd/catalog-permissions/README.md). Earlier test counts above retain their original session context.


## Preview groundwork — Step 2

`queries/preview.py` validates decoded query pairs and separates primitive parsing
from semantic checks after the shared rate debit. `queries/cursors.py`
authenticates bounded, publication-bound cursors. `queries/preview_schemas.py`
validates canonical columns, exact decimal strings, explicit diagnostic input,
complete-key pages and the 5 MiB response limit. No preview endpoint is enabled.

Run the focused offline checks from `backend/`:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_preview_unit.py' -v
```

Tests use synthetic publications and public test key bytes. No active publication
or configured secret is needed. Step 3 integration is described below; retained
configuration and real runtime verification remain pending.
The stored candidate stays unpublished. See [Step 2 evidence](../ai/sessions/2026-10-04-dataset-preview-step-2.md)
and the [remaining stages](../sdd/dataset-preview/tasks.md).


## Preview integration — Step 3

`GET /api/v1/datasets/{dataset_key}/preview` now routes through `PreviewService`.
It checks identity and primitive input before committing one shared analytical
rate debit. Semantic/cursor checks, fresh permission, publication/evidence pinning
and shared capacity follow. The common supervisor stages verified files and runs
one typed preview operation in the isolated query runtime. No API-process query
fallback exists. Diagnostic counts describe the frozen dataset, not the page.

**Delivery stays disabled:** the default `create_app()` uses `enable_preview=False`.
The internal constructor flag is for explicit acceptance configuration; it is not
an operator environment switch or evidence of readiness. Only tests inject doubles.
Step 4 records automated matching-image, database accounting, isolation and cleanup
evidence below. Retained publication linkage is still required before delivery is enabled. No preview key is generated or configured by startup.

The shared internal protocol now requires `protocol_version=1`, an explicit
`operation_kind` (`sql` or `preview`) and an exact `operation_digest`. SQL retains
its independent policy validation and public response. The API and query image
must be deployed together; an older image fails closed. The user built the matching
Step 4 acceptance image; this does not deploy it to the retained application.

`0004_preview_evidence` has run **only in disposable test databases**. It adds nullable paired
`data_versions.evidence_bundle_sha256` and `validation_attempt_id` references to the
existing immutable bundle. It performs no backfill or publication. Applying it to
the retained database requires separate approval. The publication writer must
verify/freeze these references with the existing validation step, manifest,
checkset and warning identity before activation; that writer remains a separate
slice. Existing unbound versions fail the preview provenance read.

The trusted reader checks the bundle hash, both summary hashes, all 16 required
results and 23 completed diagnostics, including their detail identities. It emits
only canonical notes for the requested dataset, never raw details or D09. These
metadata reads do not download another dataset's Parquet.

From `backend/`, run the offline preview checks:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_preview_*.py' -v
```

Without runtime opt-ins, these run temporary-Parquet/DataFusion and in-process
TestClient checks; PostgreSQL/loopback HTTP/container cases skip. Use the explicit
Step 4 commands below for that separate evidence. See [Step 3 evidence](../ai/sessions/2026-10-04-dataset-preview-step-3.md).


## Preview acceptance — Step 4

Automated acceptance passed: 432 distinct tests across offline, disposable
PostgreSQL/HTTP and matching-image Docker suites. All 76 offline opt-in skips
were covered by the explicit suites. Retained publication linkage and the
operator check are still pending; preview execution remains disabled.

The disposable SQL runner accepts `--preview` for SQL/preview acceptance and
`--all` to include auth/catalog database regressions. `--runtime-only` selects the
15 preview container cases (including the Step 5 checker); `--failfast` stops at the first failure. It initializes a fresh local
PostgreSQL 17.11 cluster, migrates that temporary database through 0004, seeds
complete synthetic producer evidence, and stops only its own cluster. It does
not migrate or publish anything in the retained database.

The user supplied the matching image with this build from the repository root:

```sh
PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH" docker build -f backend/Dockerfile.query -t trinity-query:preview-step4 backend
```

After that build, acceptance uses its immutable local image ID and the verified
local Docker socket via `TRINITY_TEST_QUERY_IMAGE` and
`TRINITY_TEST_DOCKER_SOCKET`. On the verified macOS Docker Desktop setup, run
from the repository root:

```sh
export TRINITY_TEST_QUERY_IMAGE="$(/Applications/Docker.app/Contents/Resources/bin/docker image inspect trinity-query:preview-step4 --format '{{.Id}}')"
export TRINITY_TEST_DOCKER_SOCKET="$HOME/.docker/run/docker.sock"
backend/.venv/bin/python backend/tests/run_local_sql_checks.py --all
backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_sql_containers.py' -v
```

Without the explicit image, database-only checks can run but container cases
skip; exit zero then is not full Step 4 acceptance. Test storage serves exact
synthetic bundle/Parquet bytes. A test-only bridge copies request files into a
unique disposable daemon volume; this does not prove deployed Compose wiring or
real S3 permissions. The acceptance record distinguishes real-container results from these remaining
deployment and retained-publication boundaries.
See [Step 4 evidence](../ai/sessions/2026-10-04-dataset-preview-step-4-acceptance.md).


## Preview operator check — Step 5

The optional `--preview-fixture` mode checks all three personas against an
independently verified publication fixture. Default auth and `--catalog` behavior
are unchanged. The fixture pins publication metadata, range, facility/generator,
two expected rows per dataset and scoped frozen diagnostic summaries. Page size
is fixed to 1, so the check must follow a real cursor and compare the second row.
Missing publication, unavailable runtime, empty pages or no continuation return
exit 2 (`not ready/incomplete`), never a pass. Other failures return 1.

**Retained verification is blocked:** read-only inspection found zero retained
publications and migration `0002_app_entry`; preview remains disabled. Do not run
a test seed, publish the candidate or invent fixture metadata to satisfy this check.
The [operator handoff](../ai/sessions/2026-10-04-dataset-preview-step-5-handoff.md)
records the concrete October 1–2 Palisades candidate, hash-checked expected rows,
fixture fields and the missing retained publication/configuration prerequisites.

Only after those prerequisites are verified, run from the repository root:

```sh
backend/.venv/bin/python -m trinity.auth.check --catalog --preview-fixture /absolute/private/preview-fixture.json
```

Keep the fixture outside Git. The terminal prompts privately for each password.
Tokens/cursors stay in memory; the checker attempts logout on failure and checks
revocation after successful checks. Output contains safe summaries only. This
command neither configures nor enables preview and makes no publication changes.

## Refresh evidence registration — initial implementation

`refresh.evidence.load_candidate` reconstructs and rechecks a retained parent receipt,
validation report and stored bundle. `refresh.registration.CandidateRegistration`
then atomically stores artifacts/results and Preview's existing `evidence_bundle_sha256`
and `validation_attempt_id`, with the selected validation step. Zero warnings creates
publication intent; review warnings wait for approval. This is an internal trusted
worker boundary, not a public upload endpoint. The task 4 worker retains completion for the task 5 routing gate.

Migrations `0005_refresh_evidence` and `0006_refresh_dispatch` extend
`0004_preview_evidence`; existing Preview evidence remains unchanged. Do not run
migrations against a retained database as part of the disposable test command.
From `backend/`, the focused checks are:

```bash
uv run --locked python -m unittest discover -s tests -p test_refresh_evidence.py -v
uv run --locked python tests/run_local_sql_checks.py --refresh
```

The second command creates and removes only its own PostgreSQL 17.11 cluster and
uses synthetic storage. It checks upgrade from Preview, writer rollback/identity,
and actual Preview-service provenance with a test-only publication effect. It does
not prove a running publisher or execute query containers. Admin admission/read
routes, dispatch, supervised refresh execution and failure import are implemented;
see the additional Redis/process acceptance below.
See [current implementation status](../sdd/refresh-publication/tasks.md).


## Refresh dispatch and preparation — tasks 2–4

`POST /api/v1/refresh-runs` accepts an empty object with a UUID `Idempotency-Key`
from a current Admin after shared setup. It commits a run, admission reservation,
outbox intent and receipt together. The returned tracking URL works before enqueue.
Exact replay returns the original receipt. History and step cursors use explicitly
configured `TRINITY_REFRESH_CURSOR_KEYS_JSON` and `TRINITY_REFRESH_CURSOR_ACTIVE_KEY_ID`,
with the same 32-byte base64url key format as Preview but separate keys/purpose.

From `backend/`, run real disposable-service acceptance:

```bash
uv run --locked python tests/run_local_refresh_checks.py --failfast
```

The runner requires Docker and the existing PostgreSQL 17.11 binaries. It starts
only a disposable Redis 8.10.2 container on a random loopback port and a private
PostgreSQL Unix-socket cluster, then removes both. Preload `redis:8.10.2` if needed.
`TRINITY_DOCKER_BIN` and `TRINITY_PG_BIN` can select the installed executables.
No EIA key or cloud access is used. The Redis-only cases intentionally skip when
using `run_local_sql_checks.py --refresh` without the Redis runner.

Background entrypoints are `python -m trinity.workers outbox`, `refresh`, and
`recovery`. They use `TRINITY_DATABASE_URL` and trusted `TRINITY_REDIS_URL`.
Refresh/recovery also require an existing private durable `TRINITY_REFRESH_ROOT`;
refresh alone loads the existing EIA and S3 settings. Keep this root on the same
host/filesystem for recovery and preserve its lock/evidence files. Never place
credentials in command arguments or queue payloads.

Do not enable a live refresh walkthrough yet: task 5 must wire successful receipt
custody into candidate registration and completed-receipt recovery. Task 4 leaves
successful preparation unvalidated in application state with admission retained.
Failure import is implemented: measured results stay available, readiness stays
false, and an unresolved warning blocks a new run. Publisher, setup writes and
Admin resolution commands remain separate. See the [implementation record](../ai/sessions/2026-10-04-refresh-dispatch-and-worker.md).
