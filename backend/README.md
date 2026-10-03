# Trinity Python backend

This is the minimum project scaffold. It exposes process liveness at `GET /health`, returning `{"status":"ok"}`. Product routes, authentication, EIA extraction, Parquet, PostgreSQL, S3, Redis/BullMQ, workers and query isolation remain pending.

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

```bash
uv run --locked uvicorn trinity.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/health for liveness or http://127.0.0.1:8000/docs for the scaffold's generated API documentation. Liveness does not establish data readiness or healthy external services. The root `docs/openapi.json` remains the planned product contract; it is not the running scaffold's schema.

## Check and build

```bash
uv run --locked python -m unittest discover -s tests -v
uv build
```

Verified on CPython 3.14.8 with uv 0.12.23: dependency resolution, locked installation, six health/configuration tests, installed-package compatibility checks and backend-module imports. The initial scaffold also passed source/wheel builds. The tests cover environment loading, missing/blank keys, secret masking, fresh reads and health without credentials. Starlette still emits a deprecation warning for the approved HTTPX test client; all tests pass. No dependency was changed to hide that warning. External-service integration and live EIA credentials have not been tested.

## Layout and next slice

`src/trinity/main.py` creates the FastAPI application. `src/trinity/__init__.py` has no infrastructure initialization. `tests/` contains standard-library unittest tests, so no additional test framework is required.

Follow A15's feature layout in [backend architecture](../docs/backend.md) as behavior is added. The next slice is the connector and typed Parquet pipeline. The lock now includes the selected API, environment configuration, HTTP, PostgreSQL, migration, PyArrow/DataFusion/SQLGlot, Redis/BullMQ and S3 libraries. HTTPX is a runtime dependency for the connector. Clerk is omitted because alayala selected local login; authentication implementation and contract reconciliation remain pending. The build uses uv_build 0.12.23. Installing these libraries does not implement their features or verify their external services.
