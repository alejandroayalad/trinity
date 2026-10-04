# SQL isolation and HTTP delivery commits

Date: 2026-10-04. Decision references: A9, A16, A19, A20.

## Authority and scope

[ME] Alayala requested commits for isolated execution, HTTP delivery and any remaining validator/DataFusion work. This extends the earlier autonomous T05–T20 authorization. No push, PR, retained database migration or live publication was requested.

[YOU] Reviewed and separated SQL changes from concurrent catalog and preview work. The existing validator/DataFusion implementation is `e851e28`; the remaining qualified-column alias correction is `1e3c072`. Kept the paired single-statement commits intact. Prepared isolated snapshots from the Git index so uncommitted catalog routes cannot hide missing dependencies.

## Isolation implementation and evidence

Validated SQL and one pinned publication enter the supervisor. PostgreSQL reserves shared capacity; verified files enter a generated request directory. A fixed-image, network-disabled container reads only that directory. The supervisor validates the complete result, confirms termination/removal and only then releases capacity. An ambiguous Docker create retains capacity; expiry alone does not release it.

Includes admission migration, publication pinning, GET-only staging, response models, service admission, Docker management/framing, runtime entrypoint, supervision and recovery. These are required dependencies of isolation. The auth test reset includes the new foreign-key tables without committing the separate catalog fixture refactor.

Checks on the isolated staged snapshot:

- SQL suite: 58 discovered, 53 passed, five real-container tests skipped before opting in (1.395 seconds).
- Built `backend/Dockerfile.query` from that snapshot with the locked environment.
- Opt-in Docker suite: all seven checks passed (5.252 seconds), including real execution, read-only mount/sibling/network/credential denial probes, kernel OOM, timeout removal, wrong-owner rejection and bounded frame handling. Probe tests use fixed test-only Python commands; the normal execution test uses the production runtime.
- Engine regression before commit: all ten checks passed (0.495 seconds), including canonical qualifiers with a table alias.

## Boundaries

Synthetic manifests and local Parquet bytes are used. No live EIA/S3 permission proof, retained-account query, frontend hiding or retained migration is claimed. Real recovery acceptance abandons a running reservation; it does not yet prove an actual API-process SIGKILL or every late-create/start race. This commit records implemented behavior and measured checks, not completion of every T16/T18 acceptance scenario.

Maintain data evidence — ongoing.

## HTTP delivery and final checks

The HTTP commit registers only the SQL route on top of the committed auth/settings routes. Catalog wiring remains in the working tree. It includes bounded request/error handling, cancellation signaling, real database/HTTP/container tests and their shared fixture, the existing API Docker build/entrypoint/base Compose prerequisites, the SQL overlay and operator instructions. Existing API Docker files are reused unchanged. Their inclusion is necessary for the SQL overlay to resolve its API image, database secret and service dependencies. No catalog or preview feature is included.

Checks against the exact staged SQL-only source snapshot (using the existing locked interpreter with PYTHONPATH pointed at the snapshot):

- `python -m unittest discover -s backend/tests -v`: 314 discovered, 273 passed, 41 opt-in tests skipped (33.333 seconds).
- `python backend/tests/run_local_sql_checks.py` with explicit query image/socket: all 11 checks passed (16.737 seconds). Includes independent-process rate/capacity accounting, identity recheck, Viewer denial, publication pinning, safe HTTP errors, real loopback HTTP/DataFusion results for Analyst/Admin and recovery of an expired running container. Synthetic GET responses and a test-only staging-volume bridge are used.
- Isolated snapshot `python backend/tests/run_local_auth_checks.py`: all 43 checks passed (28.987 seconds), proving the new migration does not break the committed auth suite.
- `docker compose -f compose.yaml -f compose.sql.yaml config --quiet`: passed with synthetic configuration values. No Compose services were started by this check.
- Staged whitespace and new documentation-link checks passed. The repository declares unittest and locked dependencies; no separate formatter/linter/type-check command is configured in pyproject.toml.

The rebuilt query image tested above was `sha256:ee3afd5e1ffb6d869c4657fd6b297168f9937ef851e7cc0c48ec754b45fabf39`. Tests used the local Docker Desktop Unix socket and negotiated Engine API 1.56. The API image and complete SQL Compose stack were not rebuilt/deployed during this commit task; their current verification boundary is explicit in backend/SQL.md.

The earlier mixed working-tree regression also passed 340 discovered tests (51 skipped) and 70 auth/catalog checks. Those counts are supporting preservation evidence, not the narrower committed snapshot's test count. No retained database, cloud resource or remote Git state was changed.

Done: focused local commits and measured synthetic SQL evidence.
Pending: remaining acceptance boundaries under "Boundaries" and the SQL operator instructions.
Blocker: none for committing; broader readiness is not asserted.
Next: [ME] review the HTTP delivery commit with `git show --stat HEAD`.
