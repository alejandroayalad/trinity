# SQL backend delivery

`POST /api/v1/queries` accepts `{"sql":"SELECT period, outage FROM national_outages ORDER BY period LIMIT 10"}` with a bearer session. Analyst/Admin may run the closed single-table grammar. Viewer receives 403 before policy, analytical counters or downloads. Frontend SQL controls are a separate, unfinished slice.

SQLGlot validates the whole input before any published file read. One SELECT permits zero or one terminal semicolon and trailing comments. The service pins the publication and manifest, stages verified files, and uses a network-disabled DataFusion container. A response contains the pinned publication, ordered columns, exact numeric strings, rows and empty diagnostics. No active publication yields 409; denied SQL yields 422. Dependency failures never fall back to execution inside the API.

## Reproduce local evidence

From the repository root with the locked backend environment installed:

```sh
backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_sql*.py' -v
docker build -f backend/Dockerfile.query -t trinity-query:sql-slice backend
export TRINITY_TEST_QUERY_IMAGE="$(docker image inspect trinity-query:sql-slice --format '{{.Id}}')"
# Use the actual local Unix socket; Docker Desktop commonly uses ~/.docker/run/docker.sock.
export TRINITY_TEST_DOCKER_SOCKET=/var/run/docker.sock
backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_sql_containers.py' -v
backend/.venv/bin/python backend/tests/run_local_sql_checks.py
backend/.venv/bin/python backend/tests/run_local_sql_checks.py --pattern test_query_guarantees.py --failfast
```

The query-guarantee suite uses deterministic lifecycle barriers, lost real Docker/PostgreSQL replies, and a separately running recovery entry point after natural deadline expiry. It also checks V1/V2 overlap and SQL plus container isolation. Run CPU-heavy offline regression and runtime acceptance sequentially.

The database runner requires PostgreSQL 17.11 (`TRINITY_PG_BIN` selects its binary directory). It creates and stops its own Unix-socket cluster. Container tests create uniquely named disposable volumes/containers and remove them. These commands do not query EIA, read live S3 or migrate a retained database. On macOS, Docker's CLI directory may need adding to PATH so its credential helper can run during image build.

## Configure the local services

The opt-in `compose.sql.yaml` extends `compose.yaml`. The trusted API and recovery process receive the Docker socket; query containers receive neither this socket nor credentials. The query image must already exist under its immutable local `sha256:...` image ID. The API image also needs rebuilding after source changes.

Set these values in the operator's environment without storing secrets in Git:

| Variables | Meaning |
|---|---|
| `TRINITY_POSTGRES_PASSWORD` | Existing local database password, delivered as a Compose secret. |
| `TRINITY_QUERY_IMAGE` | Reviewed local query image ID returned by `docker image inspect`. |
| `TRINITY_QUERY_DEPLOYMENT_ID`, `TRINITY_QUERY_STAGE_VOLUME` | Stable deployment UUID and dedicated named staging volume. Preserve them across restarts so recovery can find its reservations. |
| `TRINITY_DOCKER_SOCKET_HOST`, `TRINITY_DOCKER_GID` | Local daemon Unix socket and its actual group ID, accessible to the non-root API/recovery user. |
| `TRINITY_QUERY_AWS_DIRECTORY`, `TRINITY_QUERY_READ_PROFILE` | Existing AWS configuration/credentials directory mounted read-only, and an explicit published-object read profile. Its IAM restrictions require separate live verification. |
| `TRINITY_S3_BUCKET`, `TRINITY_S3_PREFIX`, `TRINITY_S3_REGION` | Existing application-owned published storage. No resource creation is performed. |

First validate configuration without starting services or printing resolved configuration:

```sh
docker compose -f compose.yaml -f compose.sql.yaml config --quiet
```

After operator review of the database target and migration `0003_query_admission`, the deployment commands are:

```sh
docker compose -f compose.yaml -f compose.sql.yaml build api
docker compose -f compose.yaml -f compose.sql.yaml up -d postgres
docker compose -f compose.yaml -f compose.sql.yaml run --rm --no-deps api alembic upgrade head
docker compose -f compose.yaml -f compose.sql.yaml up -d api query_recovery
```

The staging initializer accepts a new empty root or the expected UID/GID 10001 and mode 0700. Unexpected ownership fails for operator review. It does not recursively change an existing directory. Recovery runs without S3 credentials and retains capacity if it cannot prove container termination/removal. Do not clear reservations or remove a staging volume to bypass occupied capacity.

## Verification limits

The recorded end-to-end test uses real PostgreSQL, loopback HTTP and Docker with synthetic published manifests and a test-only copy into the daemon volume. It does not prove deployed Compose volume wiring, actual cloud permissions or retained-account SQL. The complete SQL Compose stack has configuration evidence only. The [query-guarantee acceptance](../ai/sessions/2026-10-04-query-guarantees-fault-acceptance.md) now records actual supervisor SIGKILL, natural-expiry recovery through a separate entry point, selected late create/start races and real Docker/PostgreSQL reply loss. T15-V/T16-V are locally verified for those cases; full deployed wiring and broader HTTP acceptance remain separate. The final combined runtime run passed 82/82 with zero skips; the record preserves earlier intermittent setup-login failures with unknown cause. Earlier [commit evidence](../ai/sessions/2026-10-04-sql-delivery-commits.md) remains historical.
