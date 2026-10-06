# Session — QA-03 slow dashboard and preview reads

Date: 2026-10-05. Mode: investigation and proposed optimization.
Decision references: [A19](../../DECISIONS.md#a19--security-contract-and-local-execution-closed),
[query supervision](../../docs/security-contract.md#query-containers-and-supervision)
and [cache restrictions](../../docs/security-contract.md#exposure-and-deployment).

**October 6 continuation:** Alayala approved the initial bounds and additionally
required one verification for concurrent requests needing the same evidence.
The [implementation and measured comparison](2026-10-06-qa-03-cache-implementation.md)
supersede this record's pending gate. The proposed rules below retain their
October 5 history; [A19](../../DECISIONS.md#a19--security-contract-and-local-execution-closed)
and the [cache contract](../../docs/security-contract.md#verified-diagnostic-summary-cache)
are the current decision record.

## Objective and contributions

- [ME] Alayala requested backend profiling and optimization for single dashboard/preview reads taking 16–20 seconds. QA-03 is the slow-analytics finding in the recorded report; the earlier request-handling slice retains its QA-01 name.
- [YOU] OpenCode traced the backend, measured production evidence verification using the retained publication, and drafted a narrowly scoped cache recommendation. No optimization or deployment is claimed in this record.

## Confirmed bottleneck — backend read execution

- **Severity and scope:** P1 latency investigation; measured against the retained local stack, including its existing uncommitted 64 MiB evidence-limit change. This is not an end-to-end HTTP benchmark.
- **Expected:** A small dashboard response should not repeatedly spend seconds processing identical publication evidence without a deliberate reuse policy.
- **Observed:** `read_preview_diagnostics` took 3.14 and 10.39 seconds before analytical execution. Every call downloaded `bundle.json` (8,753 bytes), `validation.json` (14,871,806 bytes), and `diagnostics.json` (94,369 bytes): 14,974,928 bytes total.
- **Evidence/data flow:** `national_dashboard` → `supervised_call` → `NationalService._prepare` pins publication and reserves capacity → `QueryExecution.execute` → `read_preview_diagnostics` → `PublishedReader.read_into` verifies the three S3 objects → canonical JSON and complete-evaluation checks → Parquet staging → separate container execution → cleanup. The probe measures the evidence subroutine directly using that production reader/verifier. It does not call the endpoint or allocate analytical capacity.
- **Failure scenario:** Successive 30-day requests against one unchanged publication each reread nearly 15 MB before calculating at most 30 daily points. A slow evidence download alone accounted for 8.84 seconds in one sample. Small response size therefore does not predict request cost.
- **Recommended correction:** Reuse only successfully verified, dataset-scoped diagnostic summaries through the bounded cache proposed below. Keep complete verification on misses.
- **Validation still required:** Cache approval and implementation, permission/publication/failure/cancellation tests, end-to-end stage profiling including staging/container/cleanup, and cold/warm before-and-after timings. These measurements do not establish how much time Docker startup takes or explain every 16–20-second request.

## Measurements

One read-only database snapshot pinned the existing publication in 19.27 ms.
Each sample constructed a fresh execution adapter with the deployed configuration.
Factory setup includes S3 client construction and Docker configuration inspection,
not query container launch. Nothing changed the publication or source evidence.

| Sample | Profiler enabled | Factory setup | Evidence verification | Bundle read | Validation read | Diagnostics read |
|---|---|---:|---:|---:|---:|---:|
| 1 | No | 131.15 ms | 3,143.63 ms | 1,110.65 ms | 883.18 ms | 73.21 ms |
| 2 | No | 73.48 ms | 10,394.32 ms | 485.07 ms | 8,836.03 ms | 116.62 ms |
| 3 | Yes | 181.85 ms | 4,358.32 ms | 508.50 ms | 1,572.64 ms | 81.00 ms |

The third sample is for attribution, not latency comparison: cProfile adds
overhead. It recorded 6,235,996 calls, with 1.841 seconds cumulative in
`canonical_json`, including 1.608 seconds in `_json_value`. Downloads plus
repeated canonical encoding both contribute. No percentile or typical latency
claim can be made from these samples.

The retained script was then executed successfully against the same publication
to verify the reproduction command. Metadata pin took 21.64 ms:

| Sample | Profiler enabled | Factory setup | Evidence verification | Bundle read | Validation read | Diagnostics read |
|---|---|---:|---:|---:|---:|---:|
| 4 | No | 129.98 ms | 7,512.64 ms | 583.42 ms | 5,795.99 ms | 116.40 ms |
| 5 | No | 76.18 ms | 2,516.07 ms | 479.75 ms | 972.18 ms | 71.29 ms |
| 6 | Yes | 97.80 ms | 3,862.37 ms | 487.02 ms | 1,111.67 ms | 75.80 ms |

All six calls returned the same one national diagnostic note and the same
artifact byte counts. Across the four unprofiled samples, this stage alone took
2.52–10.39 seconds. The second profiler sample recorded 1.828 seconds cumulative
in `canonical_json`. These are repeated measurements of current code, not a
before/after optimization comparison.

The first operator attempt omitted `docker-entrypoint.sh`; its subprocess lacked
the entrypoint's database-password environment and returned `503 auth_unavailable`.
The corrected invocation below worked. This is a probe setup correction, not a
finding that the running API database connection failed.

## Reproduction

The initial probe ran from the approved OpenCode temporary directory. The
[retained script](../../scripts/profile_query_evidence.py) uses the same measurement
flow, restores its wrapper on exit, limits output labels and reports failures
with a nonzero exit code. From the repository root, using the existing API
container and its configured credentials:

```bash
docker exec -i trinity-api-1 docker-entrypoint.sh /opt/venv/bin/python - < scripts/profile_query_evidence.py
```

This performs three published-evidence reads (roughly 45 MB total for this
publication). It needs PostgreSQL, the configured S3 read profile and Docker
inspection access; it requires no persona password, bearer token or EIA key.
Do not print container environment variables or secret files. It creates no
query container, refresh run, session or retained file. Product API authorization
is not tested by this trusted operator probe.

## Proposed cache rules — awaiting alayala's decision

Recommendation: a small **verified diagnostic-summary cache**, owned by the
trusted API process. It targets the measured repeated work without changing
where analytical queries execute.

1. Cache only the complete successful projection (at most 32 notes per dataset), not raw evidence, query rows, identity, roles, errors or partial checks. Return copies so one caller cannot mutate another's result.
2. Key on the trusted storage namespace, requested dataset and the complete pinned publication/evidence identity: publication event/version, manifest/bundle hashes, validation attempt/checkset, contract, coverage and warning/approval binding. Never key only by date or dataset. A changed binding is a miss immediately.
3. Proposed initial bounds: 16 entries per process; a fixed 60-second lifetime after successful verification; hits do not extend it. Evict expired/old entries and clear everything on process restart.
4. Every request still authenticates and checks current permissions, pins the active publication, debits the analytical rate and reserves capacity before reaching the cache. Viewer requests can obtain only their national projection. Preserve `Cache-Control: no-store` on HTTP responses.
5. A miss or expiry runs the existing full hash/binding/completeness checks within the original deadline. Errors are never cached; do not serve expired data after a read failure. Concurrent fills must remain bounded and cancellable without releasing another request's slot.
6. Keep one network-disabled analytical container per query, authorized read-only Parquet staging and stop-before-release cleanup. The cache removes only repeated evidence work. The first request and requests after expiry may still be slow; measure them separately.

These are proposed rules, not an accepted amendment to A19. Do not silently
replace them with a dashboard-result cache, persistent worker or PostgreSQL copy
of analytical rows.

## Checkpoint and next action

- Checks run: the retained script completed three production-verifier calls and exited successfully; `git diff --check` passed. Inspected the added links and confirmed their targets. Product source and dependency files were not changed by this investigation, so no product regression suite or frontend build ran.
- Done: backend trace and live component profile; repeatable operator probe retained.
- Pending: cache decision, implementation/regression tests and end-to-end before/after measurements.
- Blocker: authorization to add the proposed cache rules under A19.

Next action: [ME] Approve or reject the bounded verified-summary cache (yes/no).
