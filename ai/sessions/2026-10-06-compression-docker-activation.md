# Session - Compression Docker activation

Date: 2026-10-06. Mode: authorized local deployment and read-only verification.

## Objective and contributions

- [ME] Alayala requested Docker down/up so he could view the compression changes
  in the frontend. This explicitly authorized the build and service restart.
- [YOU] OpenCode checked active work, built the shared API/worker image, restarted
  the complete stack without deleting volumes, verified installed code and old
  publication reads, and opened the frontend in the browser.
- No refresh, EIA fetch, S3 write, credential rotation, migration, commit or push
  was initiated. Preserve the uncommitted implementation and existing user edits.
- Basis: [A27](../../DECISIONS.md#a27---compressed-refresh-evidence) and the
  [compression implementation](2026-10-06-refresh-evidence-compression.md).

## Commands and safety

Compose configuration validation succeeded without printing its secret values.
Before shutdown, PostgreSQL showed no running/requested refresh and zero
unreleased query reservations. Run #12 remained failed with `stage_timeout`.
Build first, so a failed build cannot strand the stopped stack. Then:

```bash
docker compose -f compose.yaml -f compose.sql.yaml --profile workers build api
docker compose -f compose.yaml -f compose.sql.yaml --profile workers down --timeout 30
docker compose -f compose.yaml -f compose.sql.yaml --profile workers up -d --no-build --wait --wait-timeout 120
```

No `--volumes`, volume cleanup or database reset was used. Existing PostgreSQL,
Redis, refresh-root and query-stage volumes were retained. The query image was
not rebuilt; it consumes unchanged Parquet. Vite was already running outside
Docker and was left running on `127.0.0.1:5173`.

## Verification and results

- Build completed using the locked dependency layers and newly installed source.
- API, refresh, recovery, publication, publication-outbox, outbox, scheduler and
  query-recovery containers all use
  `sha256:4af6f9bf5a804d09a6c29421b32b57602e959d9a6f6fc3bbc5307a4418d75a96`.
- API/PostgreSQL/Redis health checks passed; all long-lived workers were running.
- SHA-256 comparison confirmed that the installed S3 adapter, pipeline, refresh
  evidence loader, published diagnostic reader and query staging modules match
  the working tree. No working-tree module injection was used for that comparison.
- API `/health` returned `{"status":"ok"}`. Frontend root and app module returned
  HTTP 200. Frontend `/api/v1/me` proxy returned the expected unauthenticated 401,
  showing that routing reached the API; this is not an authenticated browser test.
- Post-restart SQL still showed failed run #12, zero unreleased query slots and
  publication `e2245cb7-e471-4004-bef5-4a01097e8afd`, published at 10:17:45.909615 UTC.
- Ran the evidence probe against installed code, without `--container` injection:
  `docker exec -i trinity-api-1 docker-entrypoint.sh /opt/venv/bin/python - --compare < scripts/profile_query_evidence.py`.
  Old-publication outputs matched; cold reads took 13.47/9.82 s, warm reads
  0.14/0.12 ms, and four concurrent cold callers shared three GETs totaling
  14,974,928 decoded bytes. These are uncompressed-publication compatibility
  samples, not new compressed-refresh timings or full dashboard measurements.
- `open "http://127.0.0.1:5173/"` succeeded. Human screen acceptance was not observed.

## Open boundary and next action

Compression applies to newly prepared versions. It does not rewrite the current
publication or repair run #12. The Admin must use normal failed-run recovery to
start another run. Per-file UI progress is still unchanged by A27.

Next action: [ME] In the frontend, open Refresh > Run #12 > Run again when ready
to measure the new compressed refresh. [YOU] Can inspect its retained timings and
evidence afterward; no new refresh has been claimed as successful here.
