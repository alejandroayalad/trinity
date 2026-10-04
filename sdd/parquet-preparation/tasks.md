# Tasks: typed Parquet candidate preparation

Date: 2026-10-03
Basis: [specification](spec.md) and the five steps in [design](design.md).
Current authorization: the user requested committing and pushing Steps 2–3, then starting Step 4 on `feat/parquet-preparation`. Step 4 covers the trusted storage adapter and offline verification. Command integration and publication remain outside this change. No live EIA/S3 calls or session notes.

Maintain data evidence — ongoing. Preserve actual source evidence; synthetic tests are not new anomaly findings.

## Step 1 — Schemas and exact parsing

- [x] Define the three Arrow schemas, analytical names and daily keys in `contracts/datasets.py`.
- [x] Add pure `normalize_row` in `connector/normalize.py`: exact dates/identifiers/decimal text, units and nullable fields; preserve source evidence unchanged on success/failure.
- [x] Retain trailing zeros in returned Decimal values without context rounding; verify exact in-memory Arrow conversion and reject overflow/nonzero excess scale.
- [x] Run focused offline schema/parser checks and relevant existing regressions; record results below.
- [ ] Human reviews the Step 1 diff. Historical review checkbox; the current request explicitly authorizes Step 2 without asserting that this review was recorded.

Coverage: parsing portions of S02–S08 and source-preservation/error boundaries from S31. In-memory Arrow checks do not satisfy S01's saved-Parquet round trip, S05's later warning evaluation or S08's full V02 evidence evaluation. D01/D02 codes are row observations only; D03–D09 and complete diagnostics are Step 3.

## Step 2 — Freeze files

- [x] Write/reopen temporary Parquet for all three datasets without deduplication; complete S01 and remaining round-trip checks.
- [x] Implement canonical schema/manifest identities, new-version reservation and safe file paths; test S18–S21/S24.
- [x] Bind original sanitized evidence and preserve exact numeric values through saved-file conversion.
- [x] Human accepts and closes Step 2, and explicitly authorizes Step 3.

Gate passed: the user requested closing Step 2 and continuing with Step 3.

## Step 3 — Validate saved files

- [x] Implement V01–V08 and the exact 16-result attempt registry; test S09–S17/S22–S25's local boundary, including the shared missing-day rejection.
- [x] Implement D01–D09 and frozen diagnostic identity; test S26–S30. D06 is not applicable when source percentage is absent or capacity is zero, while evaluation still completes and D02 remains applicable.
- [x] Durably retain available failed/error validation and diagnostic evidence as produced; exercise persistence failure/cancellation from S36. Partial evidence never establishes readiness.
- [x] User authorizes committing and pushing Step 3, and proceeding to Step 4.

Gate passed by the user's request to commit, push and start Step 4. No publication side effects.

## Step 4 — Store immutable artifacts

- [ ] Implement conditional writes, collision handling, readback SHA-256 and final bundle verification through the trusted adapter.
- [ ] Test S25/S34–S35 with injected storage behavior, including ambiguous writes and incomplete prefixes.
- [ ] Verify actual configured storage protection separately before claiming real immutability.

Gate: successful exact-file validation; real writes require authorization and configured storage.

## Step 5 — Connect the preparation command

- [ ] Connect existing extraction to the approved stages, durable journals, bounded execution and truthful exits/output.
- [ ] Test S31–S38, failed-evidence retention and existing extraction regressions; warning-bearing storage success remains unpublished.
- [ ] Run the relevant full offline suite and document verified setup/commands; record live EIA/S3 checks separately.

Gate: prior stages verified. Active publication, application-state integration and unrelated product features remain outside this slice.

## Step 1 verification and review handoff

Publication boundary: these documents are committed separately. Step 1 source/tests remain local and uncommitted for human review; the results below describe that local working tree, not the documentation-only checkout.

Runtime: existing `backend/.venv`, CPython 3.14.8 and PyArrow 25.0.1. `uv` was unavailable on this shell's PATH; use the existing environment directly, with no dependency or lockfile changes.

From `backend/`:

```bash
.venv/bin/python -m unittest discover -s tests -p test_normalize.py -v
.venv/bin/python -m unittest discover -s tests -v
```

Focused result: **17 tests passed**. Full offline suite: **76 tests passed**, including the 59 existing regressions. The existing Starlette/HTTPX deprecation warning remains; no dependency change was made. No live calls, Parquet file writes, S3 operations or Step 2 implementation. See the [Step 1 evidence](../../ai/sessions/2026-10-03-parquet-schemas-exact-parsing-step-1.md).

Historical next action: [ME] review the new schemas, parser and focused tests before authorizing Step 2. The current request now authorizes Step 2.

## Step 2 verification and review handoff

Base: `5e17656` on `feat/parquet-preparation`. Implementation and this checklist remain uncommitted for review. Use the expanded `CONTRIBUTING.md` from `../trinity-main`; this branch has no copy. No dependency changes or session notes.

`connector/parquet.py::freeze_files` accepts the existing connector's sanitized `RetrievalMetadata` records, fixed date bounds and an existing trusted output directory. It reserves an owner-only UUID directory exclusively, saves `source-evidence.json`, and parses rows from its original response strings. It writes `data/{national,facility,generator}.parquet` without removing duplicates, reopens the bytes, checks exact values, and freezes `manifest.json`. A parsing failure retains source evidence and a safe `failure.json` without a manifest. Failed versions cannot be reused.

`contracts/manifest.py` defines canonical JSON, ordered schema fingerprints, immutable manifest entries and strict manifest reading. `inspect_frozen_files` reopens files against the retained digest and rejects changed evidence, schemas, counts, bounds, checksums, missing/unexpected data, unsafe paths and symlinks. This is the file-integrity primitive for S20; it does **not** emit V08 results or establish readiness. The 16-result attempt registry, source completeness, date coverage, reconciliation and diagnostics remain Step 3. Signed outage values survive; warning evaluation remains pending.

Runtime: existing `backend/.venv`, CPython 3.14.8 and PyArrow 25.0.1. From `backend/`:

```bash
.venv/bin/python -m unittest discover -s tests -p test_parquet.py -v
.venv/bin/python -m unittest discover -s tests -v
```

Results: **25 focused tests passed; 101 full offline tests passed**, including all 76 prior tests. Synthetic temporary files cover S01, S18–S21 file behavior, S24, numeric limits under low Decimal precision, original response preservation, concurrent reservations, partial writes and evidence-sync failure. Writer checks confirm Parquet 2.6, Snappy, stored Arrow schema and row groups no larger than 50,000. One initial integration-test fixture used the wrong settings keyword; the corrected fixture uses the existing `EIA_API_KEY` alias. The existing Starlette/HTTPX deprecation warning remains.

Diff reviewed; whitespace checks passed for the checklist and all new files. No formatter, linter or type-checker command is configured in `backend/pyproject.toml`. No live EIA/S3 calls, application-state changes, commits or pushes. Local create-once writes and tamper detection do not prove S3 protection. Command integration, stage deadlines and full readiness validation remain pending in their assigned steps.

Closed by the user's request to continue with Step 3. This closes the review gate without committing the files.

## Step 3 verification and review handoff

Step 2 is accepted and closed. Its three new source/test files are preserved. Step 3 adds `connector/validate.py`, `tests/test_validate.py` and focused backend instructions. All changes remain uncommitted on `feat/parquet-preparation` above `5e17656`. No dependency changes or session notes.

`validate_candidate` reads a retained manifest digest and the exact saved files. It produces the 16-result `trinity-data-v1` registry and 23 dataset-scoped D01–D09 evaluations. Every result binds the version, attempt, manifest, check revision, scope, counts, time and detail identity. V04 compares each dataset to the full requested date set. V06/V07 use integer millionths and record `observed - expected`; absent groups remain absent. D06 uses exact cross multiplication, including equality at the threshold and completed not-applicable evaluations. Source validation uses the connector's full route URLs and recorded key-sort fields without assuming Python's string comparison matches source ID ordering.

Each validation attempt exclusively reserves `evidence/<attempt UUID>/`. It saves check detail JSON and an append-only `journal.jsonl`, flushing and syncing each result before the next check. Attempt-specific `validation.json` and `diagnostics.json` preserve repeated validation without overwriting earlier summaries. Completed failed attempts retain all 16 required outcomes, including errors for unavailable inputs. Interrupted attempts retain prior evidence and an incomplete marker where writable. Warning summaries/digest/count and `approval_required` freeze only after all required checks pass and diagnostics complete.

`verify_validation` checks the passing report against the same attempt's complete journal, summaries, detail files and current candidate files. It rejects mixed diagnostics, incomplete evidence and changed bytes. A failed file recheck retains safe evidence where writable and never replaces the original manifest. This is S25's local handoff guard; actual S3/upload behavior remains Step 4.

From `backend/`, using the existing CPython 3.14.8 / PyArrow 25.0.1 environment:

```bash
.venv/bin/python -m unittest discover -s tests -p test_validate.py -v
.venv/bin/python -m unittest discover -s tests -q
```

Results: **34 focused tests passed; 135 full offline tests passed**, including the 101 prior tests. Coverage includes S09–S17, S20/S22–S23, S25's local guard, S26–S30, and S36's validation-stage persistence/cancellation boundary. Fixtures include 95 advertised versus 55 returned facility rows, shared missing dates, one-millionth mismatches, aggregates beyond DECIMAL(24,6), exact D06 thresholds in both directions, all-ineligible D06 rows, separate attempt identities, summary/journal tampering, write/sync failure and a test child killed after a synced result. The hard-kill test proves incomplete evidence does not establish completion; command supervision/deadlines remain Step 5.

Diff reviewed; whitespace checks passed for tracked changes and both new Step 3 files. The existing Starlette/HTTPX deprecation warning remains. Source/wheel builds and real EIA/S3 checks were not run; no packaging or dependency files changed, and live calls remain excluded. No PostgreSQL/publication changes, commits or pushes. Step 4 remains unstarted.

Delivery update: the user authorized two focused implementation commits and a push, followed by Step 4. The historical uncommitted/no-push statements above describe the original review handoffs. Before delivery, all 135 offline tests passed again.
