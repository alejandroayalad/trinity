# Session - Refresh evidence compression

Date: 2026-10-06. Mode: debugging, then authorized implementation.

**Later activation:** alayala authorized the full Docker restart after this
implementation handoff. See [deployment verification](2026-10-06-compression-docker-activation.md).
The no-deployment statements below describe the earlier implementation boundary.

## Objective and contributions

- [ME] Alayala identified refresh storage as the current performance bottleneck after run #12 exceeded the 300-second stage deadline.
- [YOU] OpenCode inspected retained run state and evidence, measured compression,
  implemented [A27](../../DECISIONS.md#a27---compressed-refresh-evidence), and ran
  offline, disposable-service and read-only retained compatibility checks.
- [ME] Supplied the failed run #12 evidence and asked for the failure to be investigated before changing timeout or retry behavior.

- [ME] Chose evidence compression as the first optimization to isolate and measure before adding concurrency, incremental extraction, or larger deadlines.
- [YOU] Exact bundle/encoding fields are AI-authored implementation details.
  No separate human explanation or verification of those details is claimed.
- [YOU] Kept scope to compression and its readers/tests. Incremental progress,
  per-request timing, concurrency and deadline changes remain separate. No
  dependencies, migrations, frontend changes, build, retained restart, EIA fetch,
  S3 write, refresh, commit or push were performed.

## Evidence behind the change

Run `bae632cb-fc7d-43ef-8ac8-1f6f47bd1bd6` (#12) prepared candidate
`27b43e73-d280-433f-8c26-294baa4cef91`. Its window was 2024-10-02 through
2026-10-06, with national/facility/generator counts 735/40,083/69,483. All 16
required checks passed. All 39 checks completed; six informational diagnostics
failed, with zero review warnings. These counts describe this run, not a new
dataset-completeness or anomaly finding.

Storage started at 14:33:45.259846 UTC and was abandoned at 14:38:47.323645 UTC.
The supervisor hit its 300-second stage deadline and confirmed child stop. The
storage journal retained 47/48 verified planned files plus the reservation.
The last recorded attempt was `s3_get` of `source-evidence.json` (29,107,006 bytes),
with no retries. The UI showed zero because progress is currently reported only
after complete storage success. No completed bundle/receipt was retained.

Run #10 stored almost the same 103.20 MB in 30.88 seconds. A later read-only probe
verified the failed candidate's source evidence in 3.911 seconds (7.098 MiB/s).
AWS reads worked then; historical per-request upload/read times were not retained.
The exact earlier slowdown remains unknown. A larger timeout was not presented
as a speed improvement.

## Input, flow, output and failure

Original validated local evidence enters `StoredArtifact.from_bytes`. For
eligible JSON/JSONL, gzip level 1 with a zero timestamp is selected only if it
saves bytes. New bundle format 2 freezes both original and encoded hashes/sizes.
`StorageOperation.put_verified` rechecks the original, reproduces the measured
encoding, sends a conditional write and verifies both representations on readback.
The final complete-object verification remains in place.

`bundle.json`, `manifest.json`, `reservation.json` and Parquet stay unencoded.
Local evidence and its validation identity are unchanged. Registration/publication
and the published evidence reader share `verified_chunks`; only the pinned
descriptor selects encoding. The existing cache keys include bundle identity.

Failure example: a gzip object has a correct stored hash but expands beyond its
declared original length. The bounded decoder rejects it before readiness or
query output. Stored and decoded hashes, gzip completeness, response length,
body cleanup, existing deadlines, retries and conditional-write semantics remain
mandatory. A different gzip representation of identical JSON also fails the
stored hash. Format 1 receipts are still read without rewriting them.

Canonical descriptor and rollout rules:
[compressed evidence storage](../../docs/schema.md#compressed-evidence-storage).

## Checks and results

The shell has no `uv` and this checkout has no virtualenv. Used the existing
sibling `trinity/backend/.venv/bin/python` (CPython 3.14.8) with `PYTHONPATH=src:tests`
from `backend/`. This is not a new locked-install check. No backend formatter,
linter or type-check command is configured. Existing Starlette/httpx deprecation
and sanitized pool notices remain.
All 14 direct dependency versions matched `pyproject.toml`; the S3 adapter import
was confirmed to resolve to this working tree rather than the sibling checkout.

| Check | Result |
|---|---|
| `python -m unittest test_evidence_compression test_s3 test_prepare test_refresh_evidence test_preview_provenance test_sql_staging test_evidence_cache -q` | 99 passed, zero skips, 18.738 s. Includes 15 new compression/compatibility tests. |
| `python -m unittest discover -s tests -q`, with opt-in service settings removed | 829 collected: 571 passed, 258 skipped, 51.511 s. |
| `python tests/run_local_refresh_checks.py --failfast` | 141 collected: 140 passed, one query-image case skipped, 262.368 s. Disposable PostgreSQL 17.11 and Redis 8.10.2; synthetic EIA/S3, actual spawned workers and recovery. |
| `python tests/run_local_sql_checks.py --pattern test_publication_runtime.py --failfast` with image digest and actual Docker socket | One passed, zero skips, 36.423 s. Real publication-to-query-container flow, all roles, SQL/preview, in-flight pinning and publication switch. |
| `python3 scripts/profile_query_evidence.py --container trinity-api-1 --compare` | Old live publication verified with new reader in an isolated interpreter; outputs equal, warm cache has zero reads, concurrent cold callers share three GETs. No service code installed. |

Runtime harness correction: the first invocation supplied `trinity-query:local`,
but `Docker.__init__` requires an immutable `sha256:` image ID. After correcting
that, the default socket was unavailable. Selected the existing image's digest
`sha256:7618028421be473c7e37ba2558d899e5c98ad1113a44fb3e0a56d9bb2173e0be`
and Docker context's socket (`$HOME/.docker/run/docker.sock`), then the test passed.
No application guard or assertion was weakened. Test resources were cleaned by
the existing runners; no retained database or service was changed.

The retained probe's cold reads were 8.28/9.58 s; warm reads 0.15/0.37 ms. It read
the old uncompressed publication, so these are compatibility/cache samples, not
compressed-refresh speed measurements. The probe now loads the storage/staging
modules too and labels byte counts as decoded bytes.

## Implemented codec measurement

Loaded the working-tree S3 adapter through stdin into a separate interpreter in
the existing refresh container. Read only the candidate's saved storage plan and
its 48 files. For each, ran `StoredArtifact.from_bytes(..., compress=True)`,
`encode`, and `verified_chunks`, then compared the recovered bytes to the input.
No network request or file write occurred.

| Measurement | Result |
|---|---:|
| Planned original bytes | 103,338,932 |
| Encoded bytes, keeping bootstrap files and Parquet raw | 4,304,973 |
| Encoded members | 13 of 48 |
| Byte reduction | 95.83% |
| Local read/measure/encode/verify/equality duration | 1.118 s |
| Original-byte equality | All 48 files |

The manifest/bundle descriptor overhead and network request latency still exist.
The measurement is not a full refresh, a throughput percentile or a guarantee
that a 300-second deadline will never be reached. Frozen source and validation
evidence remain intact; no anomaly was removed to reduce storage.

## Open boundaries and next action

- Source diff and document links reviewed; `git diff --check` passed. No code is deployed.
- Coordinate reader-first/coordinated activation before a new format 2 run.
  Existing binaries cannot read format 2. Do not restart an active worker or
  recompress an existing immutable candidate. Keep normal failed-run recovery.
- Measure a complete new EIA/S3 refresh after operator activation. This change
  does not repair or rerun failed run #12 automatically.

Next action: [ME] Authorize the coordinated deployment when ready to measure a
new refresh. [YOU] Can perform read-only verification afterward.
