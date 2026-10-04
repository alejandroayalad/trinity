# Design: typed Parquet candidate preparation

Date: 2026-10-03
Status: Steps 1–5 implemented and offline-tested; alayala authorized delivery and session closure on October 4. Actual checks and remaining live gates are recorded in [tasks.md](tasks.md). The mechanisms below retain the staged design.
Basis: [proposal](proposal.md), [specification](spec.md), [canonical contract](../../docs/schema.md) and [A15 module boundaries](../../docs/backend.md).

## Human

Use the existing extraction flow, then five small implementation steps: exact parsing, frozen files, saved-file validation, immutable storage, and command integration. Each step has its own offline tests before the next step starts. These mechanisms are implemented within this slice; they do not add or change accepted product decisions.

Input: one explicit date window and trusted storage configuration. Output: an identified, verified S3 candidate with its validation and warning evidence, still unpublished. A changed file, incomplete check or unverified upload fails preparation and retains available evidence.

**Confirmed coverage:** Each dataset must contain data for every requested day. For October 1–3, national dates `{1,2,3}` and facility/generator dates `{1,3}` fail V04. Individual facilities or generators need not appear every day. This retains A9/V04/V07 and the approved R07/S12.

## LLM

### 1. Command and module boundaries

Implemented interface; working directory `backend/`. Real EIA/S3 use remains a separate authorization and verification gate:

```bash
uv run --locked python -m trinity.connector.prepare \
  --start 2026-10-01 --end 2026-10-03 --output-root ./artifacts
```

`connector/prepare.py` is a thin command/supervisor. `connector/pipeline.py` adds reusable `prepare_candidate` orchestration around existing `retrieve_all`; the existing extraction command stays valid. Reuse `contracts/datasets.py`, `contracts/manifest.py`, `connector/normalize.py`, `connector/parquet.py`, `connector/validate.py` and `adapters/s3.py` from A15. No new production dependency or parallel pipeline.

Validate strict ISO dates and `start <= end <= current UTC date` once before extraction. Both bounds are inclusive and frozen. This command labels every run an explicit-window preparation; it does not implement production `latest_national` discovery. Load configuration only at invocation: existing `EIA_API_KEY`, proposed `TRINITY_S3_BUCKET`, `TRINITY_S3_PREFIX`, `TRINITY_S3_REGION` and optional trusted `TRINITY_S3_ENDPOINT_URL`. Credentials come from the configured SDK provider, never command arguments or recorded settings. Reject endpoint user-info/query/fragment and invalid relative prefixes. Do not select or provision a storage provider here.

Reserve `<output-root>/<version_uuid>/` with exclusive directory creation, owner-only access and no reused version. Keep data in `data/{national,facility,generator}.parquet`, immutable JSON sidecars in the version root, and append-only execution evidence in `evidence/`. Reject symlinks, absolute/URL paths, backslashes, empty/dot/traversal segments and undeclared data files. Register the fixed sidecar names so they are not mistaken for analytical data. Temporary partial files never count as final files.

### 2. Exact parsing and file identity

Build explicit Arrow fields in R02 order; use `date32`, strings and `decimal128(24,6)` with specified nullability. Decimal text uses ASCII `[+-]?[0-9]+(\.[0-9]+)?`; reject surrounding whitespace, exponents, separators and nonfinite forms. Optional all-blank percentages become null. Check representability from the text without Decimal context arithmetic; return `Decimal(original_text)` so insignificant trailing zeros remain exactly preserved. Arrow's scale-six representation must retain the exact numeric value; the caller's unchanged sanitized evidence retains original spelling. Later aggregation uses integer millionths without rounding.

Write one file per dataset, rows ordered by its daily key without deduplication. Use Parquet 2.6, Snappy, stored Arrow schema and row groups of at most 50,000 rows; tests verify their behavior against the pinned PyArrow. Reopen files for measurement. Writer settings do not promise identical Parquet bytes across dependency versions; SHA-256 identifies the actual saved bytes. [Arrow writer options](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.write_table.html) document these controls.

Define one internal canonical JSON encoder: UTF-8, `ensure_ascii=True`, sorted object keys, separators `(',', ':')`, no newline, no NaN/floats; dates are ISO strings, decimal values are exact fixed-six strings, and counters are integers. Preserve Unicode strings without normalization. Readers reject duplicate JSON keys and unsupported format versions.

| Identity | Canonical input |
|---|---|
| Schema fingerprint | `schema_format=1`, dataset key and ordered `{name,type,nullable}` fields; types use `date32`, `string`, `decimal(24,6)`. Ignore incidental writer metadata but verify actual saved fields and nullability. |
| Manifest SHA-256 | Entire `manifest.json`: `manifest_format=1`, `contract_version=1`, version UUID, requested bounds, source-evidence SHA-256 and entries ordered by dataset key/path. Each entry contains path, dataset key, file SHA-256, schema fingerprint, byte size, row count and measured min/max dates. |
| Diagnostic digest | Registry `warnings-v1` and complete summaries ordered by code/scope, with severity, affected count and detailed-evidence SHA-256. Use fixed message templates; put variable observations in bound evidence. |

Store the manifest digest outside its own hashed body. Freeze source evidence before freezing the manifest; later validation never rewrites either. Freeze each final sidecar through an exclusive write, flush/fsync and close; sync its directory before recording the completed stage. A crash can leave partial bytes, which fail parsing/identity checks. There is no repair-in-place or resume command in this slice; a new invocation reserves a new version.

### 3. Validation, diagnostics and handoff

`validate.py` reopens exactly the manifest files, verifies checksums/schema/counts/bounds and derives key/date/group sets from their contents. Preserve source evidence for V01/V02. Materialize the expected 16-result registry once; one attempt UUID and manifest digest bind every result. Record failed/error outcomes for checks that cannot execute. Never infer a pass from an empty result list or combine attempts. V04 generates the inclusive requested date set and compares each saved dataset's distinct dates against it, recording missing and extra dates per dataset. National must also have exactly one row per date. Shared omissions fail S12; no per-entity daily roster is imposed.

V05 compares facility/date pairs in both directions. V06/V07 use arbitrary-size integer sums in millionths; emit exact expected, observed and `observed - expected` values. A missing group is missing evidence, not zero. D06 applies only when source percentage is present and capacity is positive: test `abs(P*C - 100*O*1000000) > 5100*C`, with P, C and O in millionths. Otherwise record not-applicable counts/reasons (`missing_source_percentage`, `zero_capacity`) in evaluation evidence, without inventing a ratio. This completes D06 evaluation even if no row is eligible; D02 still applies to absent source percentages, and other diagnostics still run.

D07 compares facility and generator membership sets between consecutive requested days. D08 compares capacity for the same natural entity on consecutive days when both observations exist, including national. The first requested day has no invented predecessor; a gap has no carried-forward capacity. Aggregate D01–D09 by code/dataset scope, with affected counts and separate detailed evidence. Unknown codes or incomplete evaluation block success. Freeze summaries only after all required results pass and diagnostics finish; warning count counts warning summaries, not rows.

Durably append available required-check and diagnostic results/details to an attempt-specific journal as produced, with flush/fsync, including failed/error outcomes. On failure or interruption retain that evidence and an explicit failed/incomplete summary where writable. Produce `validation.json` and `diagnostics.json` without promoting partial/failed evidence to frozen successful diagnostics or readiness. A disk failure cannot guarantee a new write; it still blocks success. The reusable successful result binds version/bounds, contract/check set, manifest, attempt, all 16 results, diagnostics/digest/count, `approval_required` and artifacts. Future refresh persistence owns application records; this slice grants no approval/publication.

### 4. Storage and failure handling

First reserve `<prefix>/<version_uuid>/reservation.json` using a random preparation token. Then use explicit `put_object(IfNoneMatch="*")` for every object; no unconditional upload helper or initial HEAD-then-PUT. A prefix reservation conflict stops before data uploads. AWS documents conditional creation and conflicts in [conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html).

For an ambiguous write within this same preparation, read back the object and compare its full SHA-256 and byte size. Identical bytes resolve that operation; different or unverifiable bytes fail. Retry only temporary external errors, at most three attempts with 1/3-second waits within the deadline; disable additional SDK retries. Repeated conditional writes must never replace an object. Hash streamed GET bytes after each upload, including metadata/evidence files; never treat ETag or uploader success alone as SHA-256 proof. Cap each object at 64 MiB for this bounded first implementation and fail before upload if exceeded; multipart/streaming expansion needs a later measured change.

After verifying data, manifest, validation, diagnostics and retained source/detail evidence, freeze `bundle.json` listing their relative paths, sizes and SHA-256 values plus version/manifest/attempt identities. Upload and read back this bundle last. Its digest is held in the local result, outside its own body. An absent or unverified bundle cannot establish success. A future consumer must verify the bundle and referenced objects; listing a prefix is never readiness proof. An ambiguous final write still returns failure unless readback resolves it.

Require a private prefix, enforced conditional writes and no delete/version-delete or policy-changing rights for candidate writers; disable lifecycle deletion on retained candidate prefixes. Conditional writes alone do not protect a key after deletion. Review and verify the configured policy before real-storage acceptance; this design creates no bucket or policy. AWS supports [bucket-policy enforcement of conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html); a configured alternative endpoint must prove equivalent behavior.

Retain the current route-completion JSONL sink with flush/fsync before normalization. Add durable stage-start/stage-end events and safe failure records. A hard kill may lose the in-flight route; mark the preparation incomplete rather than claim full evidence. Local evidence survives storage failure. Keep the execution journal local; immutable uploaded evidence snapshots contain only completed records. Output/error paths never include credentials or raw SDK exceptions.

Implemented command budgets: 300 seconds per extraction route, 1,000 pages per route including exhaustion probes; 120 seconds for parsing/file writing, 120 for validation/diagnostics and 300 for storage including readback. All stages share an overall 1,440-second ceiling. These are preparation-command defaults, not production-refresh service limits. The supervisor stops the trusted child process on a stage/overall timeout (terminate, then kill after five seconds), waits for exit and records incompletion. It never marks a timed-out run successful. Test hard termination and delayed I/O explicitly; cooperative checks alone cannot interrupt blocked native work.

Return `0` only for the complete verified stored candidate, including completed warning-bearing candidates; `1` for stage failure/incompletion, `2` for input/configuration errors and `130` for cancellation. Only the supervisor writes the final local result after confirmed successful child completion and verification of its receipt. Failure to persist that result is failure. Output includes version/manifest/attempt, check set, warnings and `published=false`. Partial remote objects remain private and identifiable; no automated deletion or publication is added.

### 5. Small implementation steps

Maintain data evidence — ongoing. Record actual new source observations through the existing findings workflow; synthetic fixtures are not anomalies. [tasks.md](tasks.md) derives from these five steps and records current authorization:

| Step | Change and independently runnable check |
|---|---|
| 1. Parse | Schemas and exact conversion only; synthetic fixtures for S02–S08, no network. S01 round-trip acceptance waits for step 2. |
| 2. Freeze files | Real temporary Parquet round trips, safe paths and deterministic identities; S01/S18–S21/S24. |
| 3. Validate | Saved-file checks, attempt registry and diagnostics; S09–S17/S22–S30, including S12's shared missing-day rejection. |
| 4. Store | Immutable storage adapter with injected client; S25/S34–S35 plus checksum/bundle/collision tests. Real policy verification is a separate gate. |
| 5. Connect command | Reuse extraction, durable evidence, deadlines and truthful output; S31–S38 plus existing extraction regression tests. |

Each step first runs its focused unittest module, then relevant existing tests. The completed slice runs `uv run --locked python -m unittest discover -s tests -v`. Step 1's actual commands/results are in [tasks.md](tasks.md); its in-memory Arrow checks do not prove saved-Parquet behavior. S3 policy checks and new live extraction remain pending.

Current gate: alayala configures S3; real storage protection and live preparation require separate verification. Historical Step 1 checks alone did not prove the later validation or storage behavior; see [tasks.md](tasks.md) for each step's evidence.
