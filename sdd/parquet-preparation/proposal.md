# Proposal: typed Parquet candidate preparation

Date: 2026-10-03
Status: Approved by alayala. Steps 1–5 are implemented and offline-tested; session closure authorized October 4. Real S3 protection and live preparation remain unverified. See [tasks.md](tasks.md) and the [closure record](../../ai/sessions/2026-10-04-parquet-preparation-steps-2-5-close.md).
Approval record: “proposal reviewed and agreed continue with spec please”. That approval covered scope and direction; subsequent design and implementation authorization are recorded in tasks.md.
Branch: `feat/parquet-preparation`

Canonical requirements: [data contract v1](../../docs/schema.md), [decisions](../../DECISIONS.md) A5/A9/A13–A17/A19, and [backend structure](../../docs/backend.md).
Discovery and authorship: [session record](../../ai/sessions/2026-10-03-parquet-preparation-sdd-proposal.md).

## Human

### Why this change is needed

At proposal creation, the connector could retrieve the national, facility and generator routes for one fixed date window and save sanitized retrieval evidence. It did not yet produce the typed files that Trinity will query, prove that their totals agree, or store a complete immutable candidate in S3.

### Proposed outcome

One preparation command produces a new version containing all three Parquet datasets, a frozen file manifest, validation results and sanitized source evidence. A manifest is a list of the exact files and their identities. A checksum identifies saved bytes so a later change can be detected.

Input → existing EIA extraction → exact parsing → new Parquet files → frozen manifest → checks of the saved files → private application-owned S3 storage with verified checksums.

Success means a complete candidate has been checked and stored. Publication remains a separate application action under A16. Warnings stay attached for future Admin review. Failed or incomplete checks never become a successful candidate.

### Example and failure case

An identifier such as `"001a"` stays `"001a"`. A capacity of `"863.4"` is stored exactly as a decimal measurement. A missing optional source percentage stays null; it does not become zero.

If EIA supplies `"0.0000001"`, six fractional decimal places cannot preserve it. Preparation fails and retains the original value and failure evidence. It must not round the value or omit its row. The same failure rule applies if a saved Parquet file changes after the manifest was frozen.

### Scope

| Included in this slice | Boundary |
|---|---|
| Three Arrow schemas and strict parsing | Follow the existing contract; preserve identifiers, source values and null rules. |
| Candidate files and frozen manifest | New version directory for each preparation; never overwrite a frozen candidate. |
| Required checks and diagnostics | Validate saved bytes and retain one complete attempt bound to their manifest. |
| Immutable S3 artifacts and one command | Verify stored bytes; retain failure evidence and return nonzero on failure. |
| Focused tests and setup instructions | Document working commands and configuration when implemented and verified. |

Outside this slice: authentication, frontend, SQL execution, PostgreSQL migrations, refresh admission, scheduling, queue/recovery workers, Admin approval endpoints and the active publication update. These remain required product work. This command will supply reusable preparation behavior for the later refresh service; it will not create a second publication workflow.

### Recommended direction and review

Extend the existing connector using A15's module boundaries and the already selected PyArrow and boto3 dependencies. Keep this proposal as the first SDD artifact after discovery. Review it before drafting `spec.md`, then `design.md` and `tasks.md`; implementation and `verify-report.md` follow their respective stages.

Proposal approval accepts this scope and direction. It does not claim live EIA/S3 verification or resolve the design questions below. No cloud resource is created at this stage.

## LLM

### Current evidence baseline

Discovery began on clean local `main` at `fc7375a`. During this work the shared checkout gained `9fc0497`, which records the first live EIA run. The final branch includes that existing commit; this task did not create it. Its evidence is preserved.

- `retrieve_all` in `backend/src/trinity/connector/pipeline.py` uses one client, fixed bounds and one final `RetrievalResult` per route. A failed route does not stop the other routes; cancellation and evidence-sink failures propagate.
- `RetrievalResult` in `backend/src/trinity/connector/retrieval.py` exposes a complete collection only on success. Metadata includes sanitized response bytes, their SHA-256 values, request bounds and per-attempt evidence.
- `main` in `backend/src/trinity/connector/__main__.py` saves JSONL evidence with exclusive creation and flush/fsync after each completed route. Evidence remains in memory until route completion; hard termination can leave incomplete output.
- `_validate_page` in `backend/src/trinity/connector/client.py` checks row shape, string forms, dates/window and source units. It does not implement exact decimal storage or final Parquet validation.
- `backend/pyproject.toml` already pins PyArrow and boto3. `backend/tests/` uses standard-library unittest. The [new live-run brief](../../evidence/2026-10-03-first-live-eia-run.md) records 59 passing offline tests, two passing live checks and successful extraction for `2026-10-01` (1 national, 55 facility and 95 generator rows). These were not rerun for this proposal; the underlying JSONL remains outside Git. Full-window validation remains pending.

Absence check: inspected `backend/src/trinity/`, `backend/tests/` and the root directory with file listings. Expected `contracts/datasets.py`, `contracts/manifest.py`, `connector/normalize.py`, `connector/parquet.py`, `connector/validate.py`, `adapters/s3.py`, and a Parquet SDD folder were absent. Existing connector files cover extraction only. This is the implementation baseline, not a runtime defect finding.

### Required behavior

#### Schemas and parsing

Implement the three schemas from [schema section 2](../../docs/schema.md#2-analytical-datasets-and-keys): `national_outages`, `facility_outages`, and `generator_outages`, with dataset keys `national`, `facility`, and `generator`.

Use Arrow `Date32` for `period`, strings for identifiers/labels, and `DECIMAL(24,6)` for measurements. `period`, applicable identifiers, `capacity` and `outage` are required. `facilityName` and `percentOutage` are nullable; applicable optional columns remain present even when entirely null.

Parse decimal strings directly, never through binary floats. Preserve identifier case, whitespace in nonblank identifiers, and leading zeros. Reject numeric JSON identifiers/measurements, invalid calendar dates, missing required values, blank identifiers, nonfinite values, negative capacity, overflow and loss of a nonzero fractional digit. Insignificant trailing decimal zeros may be removed without changing the value. Preserve signed outage and unusual source percentages. Do not round, deduplicate, fill gaps or silently drop rows.

Missing/blank optional labels and percentages become null with diagnostics. Nonempty invalid optional numeric text fails. Preserve unknown source fields, lexical measurements and unit metadata in sanitized evidence without adding public columns automatically.

#### Candidate files and manifest

Write all three datasets under a newly reserved version directory. Preparation retries cannot mutate an existing frozen candidate. Preserve sanitized extraction evidence, including failures, separately from data files.

Freeze the contract version and deterministically ordered entries containing dataset key, normalized relative path, SHA-256 file checksum, schema fingerprint, row count and date bounds. Calculate the manifest digest from its defined canonical representation. Paths must stay within the version root; reject traversal, URLs, missing files and unexpected artifacts. No file or manifest entry can change after freeze.

The design must define canonical serialization, schema fingerprint inputs, ordering, file layout and the digest's exact input bytes. Avoid a self-referential manifest digest. Bind validation and diagnostics to the frozen manifest without rewriting it to append later results.

#### Validation of saved files

Reopen the exact Parquet files listed in the manifest. Combine their measured contents with preserved source evidence; an in-memory table check alone is insufficient.

| Check | Required outcome |
|---|---|
| V01 `source_complete` | All three routes reached documented exhaustion for the same window. Reject unstable/non-progressing extraction and national/generator total disagreements; retain the known facility total mismatch as evidence under A5. |
| V02 `schema_units` | Exact fields, types, nullability and decimal representation; source metadata confirms MW/MW/percent. |
| V03 `unique_keys` | Unique daily keys at each grain, including rejection of identical duplicate rows. |
| V04 `date_coverage` | One national row per requested date; facility/generator date sets equal the national set; no out-of-window rows. |
| V05 `facility_coverage` | Facility `(period, facility)` pairs exactly equal generator groups. |
| V06 `facility_reconciliation` | Exact generator sums equal facility capacity and outage for every facility/date. |
| V07 `national_reconciliation` | Facility sums and generator sums each exactly equal national capacity and outage for every date. |
| V08 `artifact_integrity` | Complete three-dataset manifest; readable files; valid paths; matching checksums, schema fingerprints, row counts and bounds. |

Use zero-MW tolerance and exact decimal arithmetic, including aggregates that exceed a single value's precision. Record expected/observed values and exact differences for reconciliation failures. Do not assume a fixed facility roster across dates or infer zero outage from a missing entity observation.

Use check set `trinity-data-v1`: V01/V02/V03/V08 each have three dataset-scoped rows; V04/V05/V06/V07 each have one `all` row. **One complete attempt has 16 required result rows.** Store the expected set, attempt ID, manifest digest, check-set version, counts and results. Missing, duplicate, skipped, interrupted, failed or error results cannot establish readiness; never merge passing rows from different attempts. Record failure/error results when a check cannot run.

#### Diagnostics and evidence

Apply the existing D01–D09 registry and `warnings-v1` severity rules from [schema section 5](../../docs/schema.md#5-validation-and-readiness). Required failures block; D01–D06 are review warnings; D07–D09 are informational. Preserve unusual source values. The known facility advertised-total mismatch remains Admin evidence without a user warning after required checks pass.

Freeze sorted diagnostic summaries, severity-registry version, warning count and warning digest tied to the successful validation attempt. Incomplete diagnostic evaluation or unknown severity/code cannot mean zero warnings. Bound summaries by code/scope and count affected observations; retain detailed sanitized evidence separately. Do not substitute diagnostics for required results or allow warnings to waive failures.

#### S3 storage and preparation command

Upload candidate Parquet files, frozen manifest, validation/diagnostic evidence and sanitized retrieval evidence under a unique private version prefix. Prevent overwrites at write time, including concurrent writers; a preliminary existence check alone is insufficient. Verify the stored bytes against recorded SHA-256 checksums. A failed or ambiguous upload/readback cannot report success. Keep partial uploads identifiable and ineligible; preserve local evidence when storage is unavailable.

Use the existing connector for extraction and A15's trusted S3 adapter boundary. Separate artifact storage from PostgreSQL publication. Never rewrite a version to repair an object, expose credentials, or make a bucket public. Define retry/collision semantics and storage policy requirements in design and test them before claiming immutability.

Provide one preparation command connecting extraction → parsing → Parquet → manifest freeze → validation/diagnostics → S3 storage. Preserve the existing extraction command. Return nonzero for stage failure/incompletion, retain sanitized failure evidence, and never continue to successful storage/readiness after invalid input. On success report version identity, manifest digest, validation outcome and warning summary; do not report publication. Exact syntax and configuration names remain for design, followed by verified backend instructions.

### Intended module ownership

| Area under `backend/src/trinity/` | Responsibility |
|---|---|
| `contracts/datasets.py`, `contracts/manifest.py` | Shared schemas, keys, manifest definition and identity rules. |
| `connector/normalize.py`, `connector/parquet.py` | Strict parsing, version files and frozen manifest generation. |
| `connector/validate.py` | Required checks, exact saved-file validation and diagnostics. |
| `adapters/s3.py` | Trusted immutable artifact writes and byte verification. |
| `connector/pipeline.py`, command entrypoint and `config.py` | Stage ordering, reusable outcomes, bounded execution and configuration. |

`backend/tests/`, `backend/README.md` and `backend/.env.example` receive focused tests and verified instructions during implementation. Reuse pinned packages; no additional production dependency is proposed. Future `refresh/repository.py` owns PostgreSQL records; this slice must preserve enough artifact identity and result structure for that integration without claiming database persistence.

### Verification scope for later stages

| Test group | Required cases |
|---|---|
| Parsing and Arrow round trips | Maximum representable positive/negative signed measurements, overflow, seventh nonzero fractional digit, insignificant trailing zeros, zero/negative capacity, nonfinite/invalid input, numeric JSON rejection, case/leading zeros, strict dates and nullable fields. |
| Coverage and reconciliation | Gaps, out-of-window rows, duplicate keys, missing counterpart groups, exact totals and nonzero differences at both aggregation levels; source completeness/unit failures. |
| Manifest and validation attempts | Deterministic identity, changed/truncated/missing files, path escape, wrong schemas/counts/bounds, extra/missing datasets, zero/missing result rows, mixed attempts and incomplete diagnostic execution. |
| Storage and command failures | S3 write/readback/checksum failures, partial uploads, concurrent writes/collisions, overwrite prevention, stage failure exit codes, cancellation and retained sanitized evidence. |
| Diagnostic semantics | Signed outage/out-of-range values preserved, optional null warnings, threshold boundary, zero denominator, membership/capacity info and A5 total mismatch without a warning hold. |

Use synthetic fixtures and the repository's unittest command first. Real Parquet files must be written and reopened in offline tests. Mocked S3 checks do not prove deployed permissions or byte integrity. Live EIA and real configured S3 verification remain separate gates; key-bearing commands belong to alayala.

### Open design details and risks

| Item | Required resolution |
|---|---|
| Command window | Define a bounded explicit-window preparation interface and its distinction from the later production refresh's supported start `2024-10-02` and `latest_national` discovery. Do not call a small test window a complete production refresh. |
| Manifest identity | Specify canonical bytes, schema metadata/fingerprints, file ordering/layout and source-evidence bindings. |
| Durable failures | Define when evidence is saved, crash/incomplete-attempt detection and finite stage budgets. The current route-completion sink does not guarantee preservation after a hard kill. |
| S3 configuration | Define trusted bucket/prefix/region or endpoint configuration, credential delivery, write protection, verified retry semantics and real-storage checks. No provider deployment or paid resource is selected here. |
| Preparation/publication handoff | Define a candidate result that preserves the canonical identities, complete checks and warning state for later PostgreSQL/worker integration. |

### Staged work

1. **Maintain data evidence — ongoing.** Preserve source evidence and record verified new candidates through the existing findings workflow.
2. Review this proposal, then define observable requirements in `spec.md`.
3. Resolve the design details in `design.md` and derive bounded implementation tasks in `tasks.md`.
4. Implement and run focused checks against the approved documents; document commands/configuration.
5. Record verification and remaining live gates in `verify-report.md` before delivery.

Current gate: [Step 1 human diff review](tasks.md). Alayala approved the specification, clarified design behavior and authorized schemas/exact parsing only. Step 1 is implemented and offline-tested; Steps 2–5 remain pending. No live extraction, S3 upload, commit or remote write is authorized by this approval.
