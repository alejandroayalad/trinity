# Dependencies and EIA environment configuration

Date: October 3, 2026. Follow-up to the minimum Python project in PR #4.

## Objective and contributions

[ME] Alayala requested dependency resolution and reading the EIA key from the environment.
[YOU] AI added the selected backend dependencies, regenerated uv.lock, implemented explicit configuration loading, added regression tests and updated the setup documentation. The work is an incremental commit on the existing review branch. Human review remains pending.

## Implementation and decision references

A15 places trusted environment configuration in `backend/src/trinity/config.py`. `load_eia_settings()` constructs immutable settings from the current process environment. `EIA_API_KEY` is required only when that loader is called. Missing or blank values raise a safe `ConfigurationError`. SecretStr masks ordinary representations and JSON output; callers must not log the unwrapped value. No .env file is read automatically, no global settings instance is created and no credential is needed for imports or /health.

A17 package versions are preserved for the selected API, configuration, HTTP, PostgreSQL, migrations, analytical engine/parser, queue and S3 packages. HTTPX becomes a runtime dependency. Redis remains BullMQ's pinned transitive dependency. Clerk is omitted following alayala's later local-login choice; the older identity design still needs separate contract reconciliation. No authentication implementation or replacement authentication library is introduced here.

## Verification and limits

- `uv lock` and `uv sync --locked` succeeded with uv 0.12.23 and CPython 3.14.8.
- `python -m unittest discover -s tests -v`: six tests passed, including the four new configuration tests.
- `uv pip check`: all installed packages are compatible.
- Imports of the selected configuration, HTTP, PostgreSQL, migration, PyArrow, DataFusion, SQLGlot, Redis/BullMQ and S3 modules succeeded.
- Tests used synthetic credentials and isolated environments. No real EIA key was printed, stored or transmitted. No live EIA request was made.
- The existing Starlette/HTTPX test-client deprecation warning remains; approved pins were preserved.
- These checks do not prove external-service integration, data correctness, query security, dependency advisory status or cross-platform compatibility.

Done: dependency lock and explicit, tested environment loader.
Pending: human review and the connector implementation.
Blocker: none for this slice.

Next: implement bounded EIA extraction using the configuration loader and HTTPX.
