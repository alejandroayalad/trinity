# Specification: typed Parquet candidate preparation

Date: 2026-10-03
Status: Approved by alayala, with full-window coverage confirmed. No acceptance scenario has been executed for this specification.
Branch: `feat/parquet-preparation`
Basis: [approved proposal](proposal.md), [data contract v1](../../docs/schema.md), and [A15 backend boundaries](../../docs/backend.md).

This document defines observable behavior for the approved preparation slice. `docs/schema.md` remains canonical. Requirement and scenario IDs below are local to this SDD; they are not new decision IDs. Design choices and runtime evidence remain separate.

## Human

### What must work

One command takes a fixed extraction window, retrieves the three EIA datasets, preserves their source evidence, writes exact typed Parquet files, freezes their manifest, validates those saved files and stores the complete candidate in private application-owned S3.

A successful candidate contains all three datasets and one complete validation attempt tied to the exact files. A stored candidate is not a published version. The command does not change what users can query.

### Expected behavior by situation

| Situation | Required result |
|---|---|
| All required checks pass, diagnostics finish and every artifact is verified in S3 | Command succeeds and identifies the stored candidate, manifest and validation attempt. |
| Required checks pass but review warnings exist | Command can succeed after storage verification; it reports the frozen warnings and required Admin review for later publication. |
| A required value is invalid, dates/groups are missing, or totals differ | Command fails; evidence remains. No rounding, row dropping or automatic repair. |
| A file changes, checks are incomplete, or S3 storage cannot be verified | Command fails; no complete stored candidate is claimed. |
| A candidate already exists | Its bytes remain unchanged. A new preparation uses a new version. |

### Concrete example

Facility `"001a"` and generator `"01B"` keep their exact identifiers. Capacity `"863.4000000"` fits because its extra trailing zero changes no value. Capacity `"863.4000001"` fails because fitting it into six fractional places would lose information. The original text remains in sanitized evidence.

### Review boundary

The proposal and specification are approved. Alayala's supplied October 1–3 example confirms that both detail datasets omitting October 2 MUST fail, retaining R07/S12 and canonical V04/V07. Each dataset must cover every requested day; individual entities need not appear every day. The [design draft](design.md) is ready for review. Authentication, SQL execution, application-state migrations, workers, approval endpoints and publication remain outside this slice.

## LLM

### 1. Terms and authority

| Term | Meaning in this specification |
|---|---|
| Candidate | One version's three analytical datasets and retained evidence, still unpublished. |
| Frozen manifest | Immutable description of the exact data files, contract version and file identities. |
| Validation attempt | One identified execution of the complete required check set and diagnostics against one frozen manifest. |
| Blocking failure | Required check failure/error, incomplete evaluation or stage failure that prevents successful preparation. |
| Review warning | A completed diagnostic observation under `warnings-v1`; it requires later Admin review but cannot waive a blocking failure. |

Authority: [schema sections 2–5](../../docs/schema.md#2-analytical-datasets-and-keys) define fields, parsing, extraction and validation; [section 6](../../docs/schema.md#6-postgresql-application-model) defines the 16 required result rows and identity bindings. [A14–A17](../../DECISIONS.md#a14--application-owned-storage-and-source-independence-closed) and [S3 security rules](../../docs/security-contract.md#published-data-and-s3-access) preserve storage, ownership and dependency boundaries. Existing EIA behavior remains reusable; extraction success alone is not validation proof.

### 2. Normative requirements

#### R01 — Fixed input window and complete source evidence

Preparation MUST use the same explicit, valid daily bounds for all three routes and every extraction retry. It MUST reject reversed/invalid/future bounds and MUST NOT shorten the window to accommodate a lagging route. Design will define the command interface and reference time for future-date checks. Bounded reproduction windows MUST NOT be presented as full production refreshes; A9's supported history start and later `latest_national` worker discovery remain unchanged.

V01 MUST establish documented page exhaustion, progress, stable totals and successful outcomes for all routes from retained evidence. National/generator advertised totals, where supplied, MUST agree with returned counts. The known stable facility total mismatch alone MUST NOT fail V01. An exhausted request/time budget, changing total, repeated page, failed/skipped route or missing completion proof MUST block success.

Preserve route, frequency, bounds, key sorting, offset, requested length, UTC request/response times, HTTP/API outcomes, API version, advertised total, actual count, sanitized response and its checksum. Preservation and redaction rules apply to failed attempts as well as successful ones. **Trace: A5; schema §4 and V01.**

#### R02 — Exact three-dataset schemas

The saved schemas MUST have precisely the applicable contract fields and nullability below. Fields remain present when entirely null. They MUST NOT gain unknown source columns, fabricated version columns or computed percentages.

| Field | National | Facility | Generator | Arrow type | Nullable |
|---|---|---|---|---|---|
| `period` | yes | yes | yes | `Date32` | no |
| `facility` | — | yes | yes | string | no |
| `generator` | — | — | yes | string | no |
| `facilityName` | — | yes | yes | string | yes |
| `capacity` | yes | yes | yes | `DECIMAL(24,6)` | no |
| `outage` | yes | yes | yes | `DECIMAL(24,6)` | no |
| `percentOutage` | yes | yes | yes | `DECIMAL(24,6)` | yes |

Dataset keys are `national`, `facility`, `generator`; analytical names are `national_outages`, `facility_outages`, `generator_outages`. V02 MUST verify saved schemas and evidence confirming daily frequency and source units MW/MW/percent. Required-field removal, changed units and incompatible types MUST fail. Exact column ordering and fingerprint serialization belong to design, consistently applied to all producers/validators. **Trace: schema §2 and V02.**

#### R03 — Strict dates, identifiers and nullable text

`period` MUST be a string in exact `YYYY-MM-DD` form representing a real calendar date, without timezone conversion. Applicable identifiers MUST be nonblank strings preserved exactly, including case, leading zeros and whitespace in a nonblank value. Numeric JSON identifiers MUST fail; labels MUST NOT become keys.

Missing/null/blank `facilityName` MUST become null with D01; nonblank labels MUST remain unchanged. A nonstring label MUST fail rather than be coerced. Missing/null/blank `percentOutage` MUST become null with D02. Required missing/null/blank fields MUST fail. **Trace: schema §2, V02, D01–D02.**

#### R04 — Exact decimal parsing and preservation

Measurements MUST be parsed directly from strings without a binary-float intermediate. JSON numbers/booleans, invalid nonempty text, nonfinite values, negative capacity, overflow and loss of a nonzero fractional digit MUST fail. Zero capacity is valid. Outage and source percentages may be signed and outside usual ranges; preserve them for diagnostics.

The largest representable magnitude is `999999999999999999.999999`. `0.000001` fits; `0.0000001` does not. Insignificant trailing fractional zeros MUST NOT cause rejection or rounding. Parsing MUST preserve them in the returned Decimal; Arrow/Parquet scale-six conversion MUST preserve the exact numeric value. Retain original lexical values in sanitized source evidence. Additional lexical forms such as exponent notation require an explicit design rule; this spec does not silently select one. **Trace: schema §2 and V02.**

#### R05 — New candidate and frozen artifact identity

Each preparation MUST reserve a unique version directory and write all three datasets there. It MUST NOT overwrite or repair an existing frozen candidate. Incomplete local output MUST remain distinguishable from a complete candidate; row failures MUST NOT produce a successful partial dataset.

Before validation, freeze contract version and deterministically sorted file entries containing dataset key, normalized relative path, SHA-256 checksum, schema fingerprint, row count and date bounds; retain byte size for the canonical artifact record. Compute the manifest SHA-256 from a defined canonical representation. Reordering equivalent entries MUST NOT change that digest. Changing any covered value MUST invalidate the old identity.

All data files MUST be covered exactly once; all three dataset keys MUST be represented, with positive per-file row counts and bounds within the requested window. Paths MUST resolve within the candidate root. Validation/diagnostic evidence written later MUST bind to this frozen manifest without modifying it. Design MUST distinguish declared evidence sidecars from unexpected data files. **Trace: schema §5–6 and V08.**

#### R06 — Validate the saved files

Validation MUST reopen every listed Parquet file and measure its actual contents. V08 MUST verify paths, dataset set, file readability, SHA-256, schema fingerprints, row counts and date bounds against the manifest. Missing, truncated, altered, unexpected or unreadable data files and unsafe paths MUST fail. Manifest tampering MUST fail its identity check. Source-row checks or writer-reported counts alone MUST NOT establish a pass.

The files sent to S3 MUST have the same identities that passed validation. A change after validation MUST be detected and block successful storage; it MUST NOT trigger silent manifest replacement. **Trace: schema §5 and V08; A15.**

#### R07 — Daily keys, date coverage and group equality

V03 MUST reject duplicate keys even when rows are identical: `period` for national, `(period, facility)` for facility, `(period, facility, generator)` for generator. Generator IDs may repeat across facilities.

V04 MUST require each dataset's distinct date set to equal the full inclusive requested window: `dates(national) = dates(facility) = dates(generator) = requested_dates`. National MUST contain exactly one row per requested date; facility and generator MUST each contain at least one row per requested date. Measure these sets from the saved files under R06. Matching facility and generator date sets is insufficient if both omit the same requested date, even when national covers that date. Any missing requested date or out-of-window row MUST fail. V05 MUST require exact equality between facility/date pairs and generator facility/date groups in both directions.

Membership may change between dates. Checks MUST NOT require every entity on every date, invent observations before an entity appears, deduplicate rows, or fill gaps with zero. Cross-route agreement does not prove an independent source inventory. **Trace: schema §2–5 and V03–V05.**

#### R08 — Exact reconciliation

V06 MUST compare each facility/date capacity and outage against sums of its generators. V07 MUST independently compare both facility and generator sums against the national row for each date. Comparisons MUST use exact decimal arithmetic with zero-MW tolerance, including aggregates beyond a single field's precision. A difference of `0.000001` MW MUST fail.

Failure evidence MUST identify date/group, measurement, both compared values and the signed difference with a documented direction. Percentages MUST NOT be summed/averaged to establish MW agreement. No tolerance adjustment or Admin approval can turn a required failure into a pass. **Trace: schema §5 and V06–V07.**

#### R09 — One complete validation attempt

The attempt MUST retain candidate/version identity, manifest digest, attempt ID, check set `trinity-data-v1`, expected checks and result rows. Each result MUST retain code/revision, dataset scope, required flag, severity, status, checked/failed counts, sanitized details and check time, consistent with the canonical result model.

| Required check codes | Scope per code | Rows |
|---|---|---:|
| V01, V02, V03, V08 | `national`, `facility`, `generator` | 12 |
| V04, V05, V06, V07 | `all` | 4 |

Exactly these **16 unique required results** MUST pass in the same completed attempt for the same manifest. A completed failing attempt MUST record failed/error outcomes, including checks that cannot run. An interrupted attempt may lack results but MUST remain incomplete and ineligible. Zero rows, missing/duplicate rows, wrong scopes, unsupported check sets or results mixed across attempts/manifests MUST NOT count as success.

A failure before a manifest can freeze MUST retain a preparation failure; it MUST NOT fabricate a manifest or successful validation attempt. Revalidating unchanged files uses a distinct attempt identity and cannot combine previous passing rows. Changed frozen files require a new candidate rather than replacement of their identity. **Trace: schema §5–6.**

#### R10 — Completed diagnostics with frozen severity

Run the canonical D01–D09 registry. D01–D06 are warnings: missing label, missing source percentage, negative outage, outage above capacity, source percentage outside 0–100, and absolute source/computed percentage difference greater than `0.0051` percentage points. D07–D09 are info: membership change, capacity change and the known facility advertised-total mismatch.

For D06, use unrounded same-row `100 × outage / capacity`; equality at the threshold MUST NOT warn. Absent source percentage or zero capacity makes D06 not applicable for that row, with the reason recorded and no invented comparison. Applicability evaluation still completes, including when no rows are eligible. D02 still applies to an absent source percentage; other applicable diagnostics still run. Preserve source values even when multiple diagnostics apply.

After all required checks pass and diagnostic evaluation completes, freeze the sorted diagnostic summaries, registry `warnings-v1`, warning count and warning digest tied to that successful validation attempt/manifest. Count warning summaries, not affected observations; retain affected counts and evidence separately. Info-only results MUST NOT require Admin review. An error, incomplete evaluation or unknown code/severity MUST block success rather than imply no warnings. **Trace: schema §3, §5–6; A5/A16.**

#### R11 — Sanitized, retained evidence and safe failure

Save source field values, unknown source fields and units for reproducibility. Remove keys, authorization headers, cookies and credential-bearing echoes before persistence, hashing, output or logging. Hash the actual sanitized saved bytes. Errors MUST use safe codes/messages, not raw secret-bearing exceptions.

Retain the failed stage, available identities, completed evidence and failure/incompletion outcome. Durably save available failed validation and diagnostic results/details as they are produced; retaining them MUST NOT establish readiness or freeze an incomplete warning set as successful. Controlled cancellation and stage failures MUST preserve previously saved evidence. Disk failure or hard termination MUST never leave a marker interpreted as successful completion; missing evidence prevents success. It is not a guarantee of writing new evidence to an unavailable disk. No cleanup may delete existing frozen candidates or prior publications. **Trace: schema §4–5; approved proposal.**

#### R12 — Immutable and verified S3 storage

Only a locally validated candidate with completed diagnostics may complete the storage stage. Store all data files, manifest, validation/diagnostic records and sanitized evidence under its unique private version prefix. Every stored artifact MUST have a retained checksum and verified bytes; data/manifest identities MUST match those validated locally.

Prevent object overwrites at write time, including concurrent writers. An existence check followed by an unconditional write is insufficient. Existing different bytes MUST never be replaced. Retry handling for ambiguous writes or identical existing objects belongs to design, but cannot rewrite them or claim success without verifying their identity. Writes and verification MUST have finite budgets consistent with A19's bounded external-retry rules; permanent errors and validation failures are not retryable repairs.

Any missing object, readback failure, checksum mismatch or unresolved upload outcome MUST block success. Preserve partial-upload evidence locally; incomplete prefixes MUST remain ineligible. Publication is a separate PostgreSQL transition, never a file rewrite or public bucket change. **Trace: A14/A19; schema §5; approved proposal.**

#### R13 — One preparation command and truthful outcomes

Provide one command that connects extraction → parsing → Parquet → frozen manifest → validation/diagnostics → verified S3 storage. Preserve the existing extraction command. Input/configuration checks MUST fail safely; no missing credential, invalid window or unsupported storage configuration may create a successful outcome.

Exit zero only when the entire stored candidate is complete and verified, including warning-bearing candidates. Return nonzero on failure, cancellation or incomplete work. Successful output MUST identify version, manifest digest, validation attempt/check set and frozen warning count/digest, and distinguish stored/unpublished from published. Failure output MUST identify the stage and retained evidence location where available, without secrets.

The command MUST NOT create application publication records, grant Admin approval, change the active version, or expose unpublished files to analytical queries. A later refresh service may consume its bound results through A15's owners. Exact CLI syntax, configuration names and exit-code taxonomy belong to design. **Trace: approved proposal; A15/A16.**

#### R14 — Focused verification and usable instructions

Implement focused tests for the scenarios below using the repository's unittest workflow, synthetic source fixtures and real temporary Parquet files. Verify write/reopen behavior, not only schema definitions or mocks. Keep offline storage tests separate from real configured S3 proof. Preserve existing extraction behavior with relevant regression checks.

Update backend instructions and placeholder configuration with exact implemented command syntax, working directory, prerequisites, fixed-window meaning, output layout, warning/failure semantics and required trusted storage settings. Keep credentials out of examples. Record actual command/results and live verification limits; do not claim unexecuted scenarios passed. Reuse the pinned dependencies; no new package is selected by this spec. **Trace: approved proposal; A17; repository verification rules.**

### 3. Acceptance scenarios

All scenarios below are **pending execution**. Unless a row says otherwise, Given a small valid synthetic fixture with the same fixed window, exact MW reconciliation and valid sanitized retrieval evidence. When applying the listed change, Then the stated outcome is required. Failures must retain evidence under R11. These examples are test inputs, not EIA anomaly findings.

#### Schemas and values

| ID | Given / When | Then | Requirement |
|---|---|---|---|
| S01 | Write/reopen all three datasets, including a fixture with optional columns entirely null. | Exact field sets, Date32, string IDs, decimal precision/scale and nullability survive; optional columns remain present. | R02, R06 |
| S02 | Use facility `"001a"`, generator `"01B"`, nonblank identifier `" 01 "` and a nonblank label with surrounding spaces. | Preserve each string exactly in saved data and keys. | R03 |
| S03 | Try missing/null/empty/whitespace-only required fields, numeric/boolean IDs, or a nonstring label. | Reject each input without coercion, skipped rows or a successful candidate. | R02–R04 |
| S04 | Compare `2024-02-29` with `2025-02-29`, `2026-2-01`, `20261001` and a timestamp string. | Accept the leap date; reject every invalid/noncanonical date form. | R03 |
| S05 | Parse `999999999999999999.999999`, its negative as outage, `0.000001`, `863.4000000`, and zero capacity, including with a low Decimal context precision. | Parsing retains insignificant trailing zeros; exact numeric values survive Arrow/Parquet round trip, with original spelling retained in evidence; signed outage is retained with its warning. | R04, R10 |
| S06 | Try `1000000000000000000`, `0.0000001`, `863.4000001`, NaN/infinity text, `abc`, numeric/boolean measurements and negative capacity. | Reject each; preserve source lexical evidence; no rounding. | R04, R11 |
| S07 | Omit or supply null/blank optional values; separately provide nonempty invalid percentage text. | Nulls produce D01/D02; invalid nonempty text blocks preparation. | R03–R04, R10 |
| S08 | Change MW units, remove required unit evidence or add an unknown source field. | Bad/missing required unit proof blocks; unknown field stays in sanitized evidence only. | R01–R02, R11 |

#### Completeness, keys and reconciliation

| ID | Given / When | Then | Requirement |
|---|---|---|---|
| S09 | Route evidence lacks exhaustion, is failed/skipped, changes totals, repeats pages or exhausts its budget; separately use disagreeing national/generator totals. | Each condition blocks success; a short page alone is not exhaustion proof. | R01 |
| S10 | Stable facility evidence advertises 95 while returning 55, with exhaustion and all required checks passing. | Record D09 info; no warning hold solely for this known mismatch. | R01, R10 |
| S11 | Insert an identical duplicate daily key at each grain; separately reuse generator `"1"` in two different facilities. | Reject duplicates at each grain; permit reuse across facilities. | R07 |
| S12 | Request October 1–3, 2026 and validate the saved files. Test full coverage; then separately omit October 2 from all routes, from national only, from either detail route, or from both detail routes while national retains it; also test an out-of-window row. | V04 passes only the full-coverage variant and fails every missing/extra-date variant. Matching detail date sets that both omit October 2 MUST fail; no shortened window or invented row. | R06–R07 |
| S13 | Remove a facility's generator group or add a generator group with no facility row. | V05 fails in each direction and identifies the missing counterpart. | R07 |
| S14 | Add an entity on day two with matched facility/generator groups and reconciled daily totals. | Required checks pass; membership change is info; day one receives no fabricated entity row. | R07, R10 |
| S15 | Change generator capacity/outage by `0.000001` while keeping the facility value unchanged. | V06 fails for the field/group and records exact compared values/difference. | R08 |
| S16 | Facility and generator sums agree with each other but differ from national by `0.000001`; also test the two comparisons independently. | V07 rejects either disagreement and records both comparison outcomes. | R08 |
| S17 | Sum many representable large values, including an aggregate beyond a single field's range. | Exact sums/differences are retained without rounding or wrapping; an unrepresentable matching national row cannot be fabricated. | R04, R08 |

#### Manifest and attempt identity

| ID | Given / When | Then | Requirement |
|---|---|---|---|
| S18 | Freeze equivalent entries in different input orders; then change a covered path/count/bound/schema/checksum/contract version. | Equivalent entries yield the same digest; covered changes invalidate the old digest. | R05 |
| S19 | Reopen an existing frozen version for preparation, including a concurrent reservation attempt. | Existing bytes remain unchanged; collision cannot overwrite the candidate. | R05 |
| S20 | After freeze, alter/truncate/remove a file, add an unexpected data file, or replace its schema/count/bounds. | V08 fails; in-memory source checks cannot rescue the candidate. | R06 |
| S21 | Use a path escape, absolute path, URL, duplicate file entry or missing/unknown dataset key. | Reject the manifest before unsafe access or storage. | R05–R06 |
| S22 | Supply 16 expected passing results for one manifest/attempt versus zero/missing/duplicate/wrong-scope results. | Only the exact complete set can satisfy required validation. | R09 |
| S23 | Mix passing results from attempts/manifests; interrupt validation; or inject an error preventing a dependent check. | Mixed/incomplete attempts cannot pass; a completed failing attempt records unexecutable checks as errors. | R09 |
| S24 | Fail parsing before manifest freeze. | Retain a preparation failure without fabricated validation success or manifest identity. | R04, R09, R11 |
| S25 | Change a file after successful local validation but before upload. | Block storage success; keep the original frozen identity and failure evidence. | R06, R12 |

#### Diagnostics and source preservation

| ID | Given / When | Then | Requirement |
|---|---|---|---|
| S26 | Use reconciled rows with negative outage, outage above capacity or source percentage outside 0–100. | Preserve values; emit applicable D03/D04/D05 warnings without changing required-check rules. | R04, R10 |
| S27 | With capacity `100` and outage `10`, compare source percentages `10.005100` and `10.005101`; test equivalent negative differences. | D06 is absent at exactly 0.0051 and present above it, using absolute difference. | R10 |
| S28 | Use zero capacity with a source percentage; separately use absent/null/blank source percentage with positive or zero capacity, including an all-ineligible dataset. | D06 is not applicable with recorded reasons and completed evaluation; no invented ratio/comparison. D02 still records missing source percentage; other diagnostics run. | R10 |
| S29 | Produce capacity/membership changes only; separately produce multiple affected rows in one warning summary. | Info-only results need no review; warning count counts summaries and affected count records rows. | R10 |
| S30 | Change diagnostic order versus change a frozen summary; inject unknown code/severity or interrupt evaluation. | Equivalent ordering keeps identity; changed summaries cannot reuse it; incomplete/unknown evaluation blocks success. | R10 |
| S31 | Synthetic source/error content includes secret-bearing echoes and unknown measurement fields. | Saved evidence/output contain no credential values; permitted source values remain and checksum matches sanitized bytes. | R11 |

#### Storage, command and verification boundaries

| ID | Given / When | Then | Requirement |
|---|---|---|---|
| S32 | Run a complete warning-free fixture through the preparation command and verified storage. | Exit zero; all three datasets and evidence are stored under one prefix with matching identities; output says unpublished. | R01–R14 |
| S33 | Run a complete valid candidate with D01–D06 warnings through verified storage. | Exit zero with frozen warnings and review requirement; no approval/publication side effect. | R10, R12–R13 |
| S34 | Storage write fails after some objects; verification read fails or returns different bytes; write outcome remains ambiguous. | Each variant returns nonzero, identifies incomplete storage and retains local evidence; no successful candidate claim. | R11–R13 |
| S35 | Concurrent writers target the same key, or an existing key contains different bytes. | No overwrite; conflict cannot create a mixed successful version. Retry handling never skips byte verification. | R12 |
| S36 | Fail evidence persistence, a required check or diagnostic evaluation; gracefully cancel between stages; separately terminate before completion is recorded. | Nonzero on handled failures/cancellation; available failed-check/diagnostic evidence already produced is durably retained where storage is writable; terminated/incomplete output is never readiness. | R09, R11, R13 |
| S37 | Omit credentials/configuration, use reversed/invalid/future bounds, or request a bounded reproduction window. | Invalid input fails safely; valid bounded runs are identified by their actual window, without a full-refresh claim. | R01, R13 |
| S38 | Follow documented setup and command examples using placeholders replaced locally; run focused and relevant existing tests. | Instructions reproduce implemented behavior; results distinguish offline tests, real storage checks and pending live work. | R14 |

### 4. Evidence required for acceptance

Record implementation revision, runtime/dependency versions, fixture/input identity, scenario IDs, command and actual result. For successful candidates retain the manifest digest, file checksums, schema fingerprints, measured counts/bounds, complete attempt and frozen diagnostic identities. For failures retain stage, safe error, relevant values and proof that existing bytes were not overwritten.

Use real local Parquet read/write tests for R02/R04–R09. Storage mocks establish controlled failure behavior only; verify the selected real S3 configuration's no-overwrite enforcement and stored-byte identities separately. Live EIA full-window preparation must be explicitly recorded before claiming full-window evidence. Existing one-day extraction evidence is not acceptance of this new pipeline. No credentials belong in test output or artifacts.

Maintain data evidence — ongoing: new source observations follow `FINDINGS.md` and the existing candidate workflow. Synthetic test cases do not become recorded source anomalies.

### 5. Design handoff and current gate

Keep `design.md` minimal: resolve the mechanisms below without repeating the specification. Plan implementation in small, independently testable steps, each with a bounded change and its relevant acceptance scenarios. Implement those steps only after the applicable review gates.

| Deferred design item | Constraints already fixed here |
|---|---|
| Command/window/configuration surface | Same frozen bounds throughout; bounded reproduction distinguished from production refresh; truthful exits and no publication side effects. |
| Canonical encodings and artifact layout | Deterministic manifest/schema/diagnostic identities, safe relative paths, declared sidecars and immutable files. |
| Parser/diagnostic details | Exact decimals and threshold comparisons; explicit additional lexical grammar and membership/capacity comparison basis; no invented first-day history. |
| Failure persistence and budgets | Retained sanitized evidence, detectable incompletion, finite stage/retry budgets and no false success after hard termination. |
| S3 protocol and handoff | Write-time overwrite prevention, verified stored bytes, safe collision/retry behavior and canonical results consumable by later refresh persistence. |

R01–R14 and S01–S38 remain the acceptance contract. Step 1 implements schemas/exact parsing only; later diagnostic, Parquet and readiness scenarios remain pending. [tasks.md](tasks.md) tracks actual checks and the required human diff review before Step 2. No cloud operations, commits or remote publication were performed for this slice.
