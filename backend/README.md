# Trinity Python backend

The backend exposes process liveness at `GET /health`, the existing evidence-only extraction command, and a separate preparation command. Preparation retrieves a fixed window, freezes exact Parquet, validates saved files and stores a verified unpublished bundle through a trusted S3 adapter. Offline command tests pass; [October 1–2 live preparation and independent S3 readback](../evidence/live-preparation/2026-10-04-october-1-2/README.md) also passed with the recorded uncommitted parser correction. The candidate remains unpublished; full-history and fresh locked setup are not established. Local login/logout, `/me`, Admin settings reads, PostgreSQL migrations and three-persona provisioning are implemented. Redis/BullMQ, workers, analytical routes and query isolation remain pending.

## Setup

Use CPython **3.14.8** and **uv 0.12.23**, as selected in A17. The Python patch is recorded in `.python-version`; `pyproject.toml` enforces the uv version. From the repository root:

```bash
cd backend
uv sync --locked
```

This installs the package and pinned backend dependencies from `uv.lock`. A changed dependency definition without an updated lockfile must fail the locked installation. Installation and imports require no secrets or external services. API startup requires `TRINITY_DATABASE_URL`; health does not require a working database or EIA/S3/Redis credentials.

## Local API and three personas

This slice exposes `GET /health`, `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/me` and Admin-only `GET /api/v1/settings`. The static product contract still describes later routes; those routes are not implemented here.

Use PostgreSQL **17.11**. Root `compose.yaml` supplies the database only, pinned to `postgres:17.11-bookworm`, with a loopback port and persistent named volume. The [official image](https://hub.docker.com/_/postgres) supports this tag and password initialization. Docker/Compose execution has not been tested on the implementation machine; real native PostgreSQL 17.11 was used for acceptance. No existing database is migrated automatically.

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

### Run authentication acceptance

From `backend/`, with PostgreSQL 17.11 binaries installed:

```bash
uv run --locked python tests/run_local_auth_checks.py
```

On macOS the default binary directory is `/opt/homebrew/opt/postgresql@17/bin`; elsewhere export `TRINITY_PG_BIN` to the directory containing `postgres`, `initdb`, `pg_ctl` and `createdb`. The runner verifies version 17.11, creates a temporary cluster with no TCP listener and a private owner-only Unix socket, seeds synthetic users, runs real PostgreSQL/HTTP checks and stops/removes only its own temporary cluster. It never connects to the configured application database. Tests require a non-root OS user, as PostgreSQL initdb does.

The normal `unittest discover` run skips the opt-in database class when `TRINITY_TEST_DATABASE_URL` is absent. The runner enables those tests. Do not point this test variable at retained data: the opt-in tests reset the test schema. Test-only analytical guards establish policy behavior, not SQL/DataFusion/refresh endpoint security.

The implementation session records the exact runtime commands/results. Compose startup, a clean locked installation and an evaluator-owned walkthrough remain separate verification. Migration downgrade was tested only inside the disposable cluster; never use downgrade as recovery for retained application history.

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
