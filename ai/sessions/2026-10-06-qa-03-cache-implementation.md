# Session — QA-03 verified evidence cache and shared cold reads

Date: 2026-10-06. Mode: implementation and verification.
Basis: [A19](../../DECISIONS.md#a19--security-contract-and-local-execution-closed),
[cache contract](../../docs/security-contract.md#verified-diagnostic-summary-cache),
[measured baseline](2026-10-05-qa-03-evidence-read-profile.md).

## Objective and contributions

- [ME] Alayala approved the proposed cache as a first fix. He described 60 seconds
  and 16 entries as starting values to revisit with measurements. He added the
  requirement that concurrent requests needing the same evidence download and
  verify it only once, with the other requests waiting for its result.
- [YOU] OpenCode implemented the cache, retained full verification on misses,
  added concurrency/admission/lifecycle tests, ran the offline backend suite and
  measured the working-tree implementation against retained published evidence.
- [YOU] Preserved the existing uncommitted source/deployment work, including the
  64 MiB evidence cap needed for this publication. No commit, API rebuild,
  service restart or publication mutation was performed in this continuation.

## Input, flow, output and failure

Services still resolve current identity and permissions, pin the active
publication, debit the rate counter and reserve capacity. `QueryExecution.execute`
then asks its process-owned `EvidenceCache` for that pinned evidence. The cache
key binds the deployment/storage/profile namespace and every publication and
evidence field. It does not include request dates or the caller's credentials.

The evidence bundle is publication-wide. One shared verification produces only
safe serialized note summaries; each request receives new models for its own
dataset. This avoids separate 15 MB fills for national and facility requests
while preserving Viewer-safe output. Nothing caches application authority,
analytical rows, raw evidence or D09.

An absent/expired identity is filled once by its first caller. Other callers
wait. The first caller executes synchronously, retaining its own reader and
reservation. Its fixed remaining analytical budget also bounds the shared work.
No new task or thread is launched by the production cache. Joining later cannot
extend that budget. Cache locks protect the index and completion state only;
network reads and verification run outside the lock.

Failure example: the evidence checksum fails while three callers wait. All
current callers receive failure; no entry survives. A later independent request
can verify again. An expired successful entry is never used as fallback.

Cancellation example: a waiting request disconnects and exits at its next
deadline check. It does not close the reader owned by another request. If the
owner disconnects but a waiter is still live, the owner completes the shared
verification within its original budget, then returns cancellation and cleans
its reservation. If all callers depart, verification stops at the next reader
or verifier deadline check. No slot is released just because HTTP disconnected.

## Implementation map

| File | Responsibility |
|---|---|
| `backend/src/trinity/publication/evidence_cache.py` | Fixed expiry, bounded LRU entries including pending fills, shared verification, independent waiter deadlines and safe failure broadcast. |
| `backend/src/trinity/publication/diagnostics.py` | Same complete hash/canonical/binding/checkset verification; immutable safe summaries and fresh dataset projections. The uncached wrapper remains available. |
| `backend/src/trinity/queries/config.py` | One cache per process, configured namespace, separate per-request readers, no cache use in recovery. |
| `backend/src/trinity/queries/client.py` | Cache access after existing service admission; original staging/container/cleanup flow. |
| `backend/tests/test_evidence_cache.py` | Fifteen focused cache, service-admission and factory checks. |
| `backend/tests/test_preview_lifecycle.py` | Two new checks: warm evidence still runs each query lifecycle; a cancelled fill owner retains its slot until shared work stops. |
| `scripts/profile_query_evidence.py` | Reproducible component comparison with uncached/cold/warm/concurrent modes. Optional host mode loads only the four working-tree modules into an isolated interpreter. |

## Checks and corrections

- Initial focused verification: **67 passed** across cache, provenance, preview
  lifecycle, dashboard service and preview service tests.
- Expanded cache/lifecycle verification: **26 passed**, including warm-cache
  Viewer isolation, revocation and capacity denial; real synthetic evidence
  validation; mutation isolation; fixed expiry; 16-entry LRU; pin/namespace
  changes; failure/recovery; independent cancellation; original-budget limits;
  pending-fill bounds; production factory wiring and release ordering.
- Broader command: `python -m unittest discover -s tests` from `backend/` in the
  temporary locked-dependency environment. **814 ran: 556 passed, 258 opt-in
  checks skipped.** No opt-in PostgreSQL/container integration is claimed.
- The first broad run had one environment-only failure: the import-isolation
  test clears `PYTHONPATH`, and the temporary environment did not have Trinity
  installed. Installed this working tree editable without changing dependencies
  or the lockfile, then reran the suite successfully. The assertion was not
  changed. A pre-existing Starlette/httpx deprecation warning remains.
- The reproducible comparison below exited successfully and checked equal
  national-note fingerprints and a single set of evidence reads for concurrent
  callers. The measured process used CPython 3.14.8 in the existing API container.
- Reviewed the diff for scope, unchanged verification steps and safe output;
  `git diff --check` passed. No frontend files changed, so frontend tests/build
  and Playwright were not rerun.

## Measured comparison — evidence stage only

Run from the repository root:

```bash
python3 scripts/profile_query_evidence.py --container trinity-api-1 --compare
```

The probe executes current working-tree modules in a separate interpreter. It
does not replace the running API's modules or install files into the container.
It uses the configured database/S3 environment through `docker-entrypoint.sh`,
pins one publication in a read-only snapshot and prints only safe measurements.
No persona password, EIA key or bearer token is needed or printed.

| Case | Evidence-stage duration | Evidence GETs | Evidence bytes |
|---|---:|---:|---:|
| Uncached verifier | 3,329.00 ms | 3 | 14,974,928 |
| Cold cache | 10,261.12 ms | 3 | 14,974,928 |
| Warm cache 1 | 0.11 ms | 0 | 0 |
| Warm cache 2 | 0.10 ms | 0 | 0 |
| Four concurrent cold callers | 5,361.60–5,363.04 ms per caller | **3 total** | **14,974,928 total** |

The concurrent group requested national, facility, generator and national notes.
It downloaded the bundle, validation and diagnostics objects once altogether,
not once per caller or dataset. Each result was checked for its requested scope.
National results matched the uncached result. The retained evidence produced one
national note, two facility notes and two generator notes.

Cold latency varies with storage: the cold-cache sample spent 8,693.40 ms reading
the validation object. It is not evidence of a cache regression versus the
3,329 ms sample. A cache miss retains the complete verifier and network work.
Metadata pin took 20.04 ms; per-request factory setup took 77.77–110.89 ms,
outside the evidence-stage timings above. No profiler overhead was enabled in
this comparison. These are component samples, not percentiles or HTTP budgets.

## Remaining validation and next action

- The running API is still on its previous image. The cache becomes active for
  HTTP requests only after an operator rebuild/restart.
- After activation, measure complete dashboard and preview requests, including
  permission/admission, staging, container launch/execution and cleanup. Record
  cold versus warm results separately. No whole-dashboard timing improvement
  is claimed from this component probe.
- Single-flight is per API process. Separate processes can each perform their
  own first fill; the selected 16-entry bound is also per process.
- Fixed expiry deliberately causes periodic cold reads. Use measured traffic
  and latency to revisit the initial bounds rather than silently changing them.

Next action: [ME] Rebuild the API with the existing local Compose configuration,
then verify a cold and repeated warm dashboard read. No query runtime protocol
or image change is required for this evidence-cache code.

## Git delivery — October 6 continuation

[ME] Alayala subsequently requested committing and pushing to the current branch,
`integrate/frontend-main`. [YOU] Prepared focused delivery with these code commits:

- `7c9cc68` — the existing 64 MiB evidence-limit correction and its two regression
  checks. This prerequisite permits cold reads of the retained 15 MB evidence.
- `b6439eb` — the bounded shared-verification cache, production wiring and tests.

Before the cache commit, exported the exact staged tree to an isolated temporary
directory. The cache, provenance, preview lifecycle, dashboard-service and
preview-service suites passed there: **70 tests, no skips**. The export contains
the intended prerequisite and cache changes, without unrelated unstaged API,
refresh or Compose changes. This closes the earlier working-tree-only boundary
for these focused checks; the larger 814-test result above remains a result for
the earlier working tree.

The documentation/profiling commit records A19, the measured baseline, cache
comparison, operator instructions and this delivery preparation. Deploying the
API and measuring full HTTP latency remain separate from Git delivery.
