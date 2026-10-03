# Trinity Python backend

This is the minimum project scaffold. It exposes process liveness at `GET /health`, returning `{"status":"ok"}`. Product routes, authentication, EIA extraction, Parquet, PostgreSQL, S3, Redis/BullMQ, workers and query isolation remain pending.

## Setup

Use CPython **3.14.8** and **uv 0.12.23**, as selected in A17. The Python patch is recorded in `.python-version`; `pyproject.toml` enforces the uv version. From the repository root:

```bash
cd backend
uv sync --locked
```

This installs the package and development dependencies from `uv.lock`. A changed dependency definition without an updated lockfile must fail the locked installation. No secrets or external services are required. `.env.example` reserves a future EIA key; this scaffold does not read it.

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

Verified on CPython 3.14.8 with uv 0.12.23: locked installation, both smoke tests, and source/wheel builds. The tests check the health response and that product operations are not exposed. Starlette emits a deprecation warning for the approved HTTPX test client; both tests pass. No dependency was changed to hide that warning.

## Layout and next slice

`src/trinity/main.py` creates the FastAPI application. `src/trinity/__init__.py` has no infrastructure initialization. `tests/` contains standard-library unittest tests, so no additional test framework is required.

Follow A15's feature layout in [backend architecture](../docs/backend.md) as behavior is added. The next slice is the connector and typed Parquet pipeline. Redis and BullMQ remain selected for later background processing. Add the other A17 dependencies when their feature requires them, then regenerate and review the lockfile. This slice installs only FastAPI, Uvicorn, Pydantic and development HTTPX, plus their locked transitive dependencies. The build uses uv_build 0.12.23.
