# Trinity Python backend

The backend exposes process liveness at `GET /health` and a shared EIA client with one-page and paginated methods for all three routes. Product routes, authentication, retries/retrieval records, Parquet, PostgreSQL, S3, Redis/BullMQ, workers and query isolation remain pending.

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

All methods accept `start` and `end` as dates, a nonnegative `offset` (default 0), and `length` from 1 to 5,000 (default 5,000). Each method makes exactly one request with daily frequency, all three measurements and ascending sorting by the route's daily key. The client uses HTTPS, rejects redirects, and applies HTTPX I/O timeouts of 30 seconds (10 seconds for connection setup). These are not a total extraction deadline.

`EIAResponsePage.data` contains source rows with strings and unit metadata preserved. `response` retains sanitized source metadata; `total` is the parsed advertised count, `api_version` identifies the API release, and `warnings` preserves sanitized top-level warnings. Empty pages are valid. The facility advertised total is not used to infer completeness.

The one-page methods check the JSON envelope, daily frequency, row shape, identifiers, dates, requested window, units and page size. Paginated collection also checks duplicate keys, as described below. Decimal normalization, full coverage and cross-route reconciliation remain later stages. HTTP failures, API-body errors and malformed responses raise `EIAClientError` with safe `code` and optional `status_code`. Returned pages omit echoed request credentials. An HTTPX log filter masks the API key in request URLs without disabling logging; callers must still avoid logging raw credentials.

After exporting `EIA_API_KEY`, run this explicit live gate from `backend/`:

```bash
uv run --locked python tests/live_eia.py -v
```

It checks one page and then paginated extraction for each route on October 1, 2026. The paginated check uses a page size of 50, at most 25 responses and a 120-second deadline per route. It compares local page/row counts and supplied totals under the route-specific rules below. This live gate has not run here because the environment has no EIA key. It is excluded from default test discovery. The routine tests use HTTPX MockTransport and synthetic data.

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

The implementation defaults to `max_pages=1000` (including the empty probe) and `timeout_seconds=300` for the entire route collection. Both are configurable positive bounds, not EIA guarantees or measured performance targets. Exhausting either limit raises `page_limit` or `pagination_deadline`; partial rows are never returned as success. These route-extraction bounds are separate from analytical query limits. Retries, persistent retrieval records, numeric normalization, full-window/cross-route validation and Parquet remain pending. Successful pagination is not proof that a candidate is ready for publication.

### Start the API

```bash
uv run --locked uvicorn trinity.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/health for liveness or http://127.0.0.1:8000/docs for the scaffold's generated API documentation. Liveness does not establish data readiness or healthy external services. The root `docs/openapi.json` remains the planned product contract; it is not the running scaffold's schema.

## Check and build

```bash
uv run --locked python -m unittest discover -s tests -v
uv build
```

Verified on CPython 3.14.8 with uv 0.12.23: 32 health, configuration and mocked EIA client/pagination tests pass. Earlier dependency resolution, locked installation, package compatibility checks and backend-module imports passed. The initial scaffold also passed source/wheel builds. Starlette still emits the existing HTTPX test-client deprecation warning. External-service integration and live EIA credentials have not been tested.

## Layout and next slice

`src/trinity/main.py` creates the FastAPI application. `src/trinity/__init__.py` has no infrastructure initialization. `tests/` contains standard-library unittest tests, so no additional test framework is required.

Follow A15's feature layout in [backend architecture](../docs/backend.md) as behavior is added. The next slice is the connector and typed Parquet pipeline. The lock now includes the selected API, environment configuration, HTTP, PostgreSQL, migration, PyArrow/DataFusion/SQLGlot, Redis/BullMQ and S3 libraries. HTTPX is a runtime dependency for the connector. Clerk is omitted because alayala selected local login; authentication implementation and contract reconciliation remain pending. The build uses uv_build 0.12.23. Installing these libraries does not implement their features or verify their external services.
