# Tasks: typed Parquet candidate preparation

Date: 2026-10-03
Basis: [specification](spec.md) and the five steps in [design](design.md).
Authorization: implement Step 1 only, then stop for human diff review. No storage, command integration, publication or unrelated refactoring belongs in Step 1.

Maintain data evidence — ongoing. Preserve actual source evidence; synthetic tests are not new anomaly findings.

## Step 1 — Schemas and exact parsing

- [x] Define the three Arrow schemas, analytical names and daily keys in `contracts/datasets.py`.
- [x] Add pure `normalize_row` in `connector/normalize.py`: exact dates/identifiers/decimal text, units and nullable fields; preserve source evidence unchanged on success/failure.
- [x] Retain trailing zeros in returned Decimal values without context rounding; verify exact in-memory Arrow conversion and reject overflow/nonzero excess scale.
- [x] Run focused offline schema/parser checks and relevant existing regressions; record results below.
- [ ] Human reviews the Step 1 diff. **Stop here. Step 2 is not authorized.**

Coverage: parsing portions of S02–S08 and source-preservation/error boundaries from S31. In-memory Arrow checks do not satisfy S01's saved-Parquet round trip, S05's later warning evaluation or S08's full V02 evidence evaluation. D01/D02 codes are row observations only; D03–D09 and complete diagnostics are Step 3.

## Step 2 — Freeze files

- [ ] Write/reopen temporary Parquet for all three datasets without deduplication; complete S01 and remaining round-trip checks.
- [ ] Implement canonical schema/manifest identities, new-version reservation and safe file paths; test S18–S21/S24.
- [ ] Bind original sanitized evidence and preserve exact numeric values through saved-file conversion.

Gate: Step 1 human diff review and explicit authorization before starting.

## Step 3 — Validate saved files

- [ ] Implement V01–V08 and the exact 16-result attempt registry; test S09–S17/S22–S25, including the shared missing-day rejection.
- [ ] Implement D01–D09 and frozen diagnostic identity; test S26–S30. D06 is not applicable when source percentage is absent or capacity is zero, while evaluation still completes and D02 remains applicable.
- [ ] Durably retain available failed/error validation and diagnostic evidence as produced; exercise persistence failure/cancellation from S36. Partial evidence never establishes readiness.

Gate: completed, reviewed file/manifest behavior. No publication side effects.

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

Next: [ME] review the new schemas, parser and focused tests before authorizing Step 2.
