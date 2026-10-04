# Trinity Python backend

The backend exposes process liveness at `GET /health` and a shared EIA client with one-page methods, pagination and bounded retries for all three routes. It also records route/attempt evidence and provides one extraction command. Product routes, authentication, Parquet, PostgreSQL, S3, Redis/BullMQ, workers and query isolation remain pending.

## Setup

Use CPython **3.14.8** and **uv 0.12.23**, as selected in A17. The Python patch is recorded in `.python-version`; `pyproject.toml` enforces the uv version. From the repository root:

```bash
cd backend
uv sync --locked
```

This installs the package and pinned backend dependencies from `uv.lock`. A changed dependency definition without an updated lockfile must fail the locked installation. Installation and the health endpoint require no secrets or external services.

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

The implementation defaults to `max_pages=1000` (including the empty probe) and `timeout_seconds=300` for the entire route collection. Each page fetch permits at most three attempts, so network attempts are bounded by 3 × max_pages as well as the deadline. Result page counts count successful validated responses, not failed attempts. Both pagination bounds are configurable, not EIA guarantees or measured performance targets. Exhausting either limit raises `page_limit` or `pagination_deadline`; partial rows are never returned as success. These route-extraction bounds are separate from analytical query limits. The full-route methods now attach retrieval metadata on success and failure; see below. Numeric normalization, full-window/cross-route validation and Parquet remain pending. Successful pagination is not proof that a candidate is ready for publication.

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

## Start the API

```bash
uv run --locked uvicorn trinity.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/health for liveness or http://127.0.0.1:8000/docs for the scaffold's generated API documentation. Liveness does not establish data readiness or healthy external services. The root `docs/openapi.json` remains the planned product contract; it is not the running scaffold's schema.

## Check and build

```bash
uv run --locked python -m unittest discover -s tests -v
uv build
```

Verified on CPython 3.14.8 with uv 0.12.23: 59 health, configuration, mocked EIA client/pagination/retry, retrieval and command tests pass. Retry tests assert three-attempt exhaustion, exact backoff calls, permanent-error rejection, unchanged parameters, deadline handling and cancellation. Earlier dependency resolution, locked installation, package compatibility checks and backend-module imports passed. The initial scaffold also passed source/wheel builds. Starlette still emits the existing HTTPX test-client deprecation warning. The live gate and the fixed-window extraction command passed against the EIA API on October 3, 2026. Other external-service integrations have not been tested.

## Layout and next slice

`src/trinity/main.py` creates the FastAPI application. `src/trinity/__init__.py` has no infrastructure initialization. `tests/` contains standard-library unittest tests, so no additional test framework is required.

Follow A15's feature layout in [backend architecture](../docs/backend.md) as behavior is added. The next slice is numeric normalization, data validation and the typed Parquet pipeline. The lock now includes the selected API, environment configuration, HTTP, PostgreSQL, migration, PyArrow/DataFusion/SQLGlot, Redis/BullMQ and S3 libraries. HTTPX is a runtime dependency for the connector. Clerk is omitted because alayala selected local login; authentication implementation and contract reconciliation remain pending. The build uses uv_build 0.12.23. Installing these libraries does not implement their features or verify their external services.
