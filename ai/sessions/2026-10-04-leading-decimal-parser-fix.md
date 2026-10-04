# Leading-decimal parser correction and live retry

Date: 2026-10-04. Base: `fde733b`; parser fix and tests remain uncommitted.

## Objective and contributions

[ME] Alayala ran the existing EIA live test (screenshot: two tests passed in 5.537 seconds), attempted October 1–3 preparation, and requested identification of the rejected value, contract comparison, a regression/fix and a new-version retry preserving the failed run. This request authorizes the live retry. [YOU] AI traced retained source responses, fixed the parser, ran tests and the authorized retry, and recorded results without logging credentials. No new connector or S3 layer was built.

## Confirmed parser defect

- Severity and scope: high; committed parser at `fde733b` blocks preparation of valid source data. Correction is uncommitted.
- Expected: A9 and `docs/schema.md` section 2 require exact decimal parsing. Optional percentages become null only when absent/null/blank; nonempty invalid numeric text fails. A finite decimal fraction such as `.5` represents exactly `0.5` and fits `DECIMAL(24,6)`.
- Observed: `normalize_row` in `backend/src/trinity/connector/normalize.py` rejected `percentOutage=".5"` from dataset `facility`, row key `(period="2026-10-02", facility="869")`. The row reports capacity `1881.2` MW, outage `9.412` MW and percentage units `percent`.
- Evidence: failed version `4342acf7-776a-41ad-bfdc-d1d471386fb7`, retained under `backend/artifacts/`, has `failure.json` reporting `invalid_decimal` for `percentOutage`. Its `evidence/retrieval.jsonl` SHA-256 is `f15959af29a9cd9d9053cf45c5850b0007105c528ccfa43942f416219a105d86`. Every retained response digest was checked before scanning rows. All 302 rows were inspected: this was the only normalization rejection.
- Failure scenario and flow: source response → `parquet._freeze_reserved` → `normalize_row` → `_optional_text` preserves `.5` → `_decimal` rejects it because `_DECIMAL_TEXT` requires an integer digit. National Parquet had already been written; facility parsing stopped freeze before validation or storage.
- Correction: allow a signed decimal fraction with digits after the point and no integer part. Preserve direct `Decimal` construction, source spelling, scale/overflow checks and negative-capacity rejection. Missing percentages still produce null/D02. Invalid text, nonfinite values, exponents and separators remain rejected. The old test incorrectly listed `.5` among invalid forms; that expectation was corrected.
- Validation still required: full successful EIA → validated candidate → S3 readback remains open because the requested window lacks October 3 source rows. No publication integration is claimed.

## Regression and runtime evidence

The new exact-row regression failed with `invalid_decimal` before the source fix. The additional lexical/scale test also failed as expected. After correction, 19 normalization tests and 26 real saved-Parquet tests passed. The saved-file regression confirms `0.500000` in Parquet and unchanged `.5` in retained source evidence. The full suite discovered 248 tests: 223 passed and 25 opt-in PostgreSQL checks skipped, in 29.245 seconds. No new dependency was needed for the parser. `git diff --check` passed; the source/test diff was reviewed.

All original retained rows now parse: national 2, facility 110, generator 190. Each route exhausted pagination with an empty terminal page and contained October 1–2 only. Source dates were not filled or changed.

The authorized retry used the existing command from `backend/` with the existing virtual environment:

```bash
.venv/bin/python -m trinity.connector.prepare --start 2026-10-01 --end 2026-10-03 --output-root ./artifacts
```

The local wrapper loaded only expected configuration keys from ignored `.env`, removed static AWS credential overrides, enforced the intended writer/destination, and kept secrets out of recorded output. It initially captured only standard output; failure JSON is emitted on standard error, so the final result was inspected from the parent-written failure file instead. No missing stdout was treated as success.

New version: `33fd735f-8003-42ab-959c-34238e40cd24`. Validation attempt: `97867d63-7e21-4104-b256-37f6a4aacb9c`. Manifest SHA-256: `9981ad728e859656c3aa2b6b77325092af85affd95e2daba0657953e525551a2`. The local `backend/artifacts/decimal-regression-evidence/tested-source.json` records the base commit and parser-patch hash; this run is not attributed to unchanged main.

Extraction and freeze succeeded. All three Parquet files exist, and inspection of the actual facility row confirms `percentOutage=0.500000`. Validation completed all 16 required results: 15 passed, only V04 failed. Its `V04-all.json` lists `2026-10-03` missing from national, facility and generator. Row counts remained 2/110/190, and every route ended with an empty probe. The reason the date is absent from EIA is unknown; no publication-delay explanation is claimed.

Command exit: 1. Parent `evidence/preparation/failure.json` records stage `validation`, status `incomplete`, `published=false`. The parent stage journal never enters storage, and there is no storage evidence directory or final success receipt. No candidate S3 upload or independent stored-candidate readback occurred. Diagnostics remain retained; failed required checks do not yield a frozen publishable warning set.

SHA-256 inventories before/after the retry confirm all seven files in the original failed run are unchanged. Both runs remain available. No Git commit/push, cloud policy change or publication occurred. A9 coverage and A16 publication gates are unchanged. Data evidence remains ongoing; see CAND-01/CAND-02 in `FINDINGS.md`.

Next: [ME] approve an explicitly scoped October 1–2 verification run, or retain October 1–3 and wait for the missing source date. A shorter run would not prove the original three-day window.

Subsequent action: alayala explicitly authorized the two-day run. It completed with all 16 required checks passing and independent S3 readback, still unpublished. Both failed runs remain intact. See the [separate verification session](2026-10-04-october-1-2-live-preparation.md); the three-day failure above remains valid evidence.
