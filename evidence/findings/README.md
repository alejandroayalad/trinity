# Reproduce the selected findings

This is historical EIA evidence, captured October 2, 2026. It is not a synthetic
test fixture or a new download. The bundled inputs cover October 2, 2024 through
October 2, 2026, inclusive. Maintain data evidence — ongoing.

## Run from the repository root

Use Python; this command needs only its standard library. No EIA key, AWS login,
`uv`, backend dependency installation, database, or network access is needed.
The project interpreter is CPython 3.14.8.

```bash
python3 scripts/generate_report.py --inputs evidence/findings/inputs --out backend/artifacts/findings
```

Choose a new output directory for each run. An existing directory is rejected so
that a failed run cannot be mistaken for an older successful report.

Expected exit code: `0`, with `Historical claims reproduced: True`. Read
`backend/artifacts/findings/REPORT.md` for measured values. `report.json` contains
the full facility changes, continuity results, request scopes, claim checks, and
input hashes. `reconciliation.csv` contains every comparison: date, facility where
applicable, metric, left and right source/value, signed `left - right` MW difference,
and match/mismatch/missing status. Missing values stay blank, not zero.

Exit `1` means the inputs were analyzed but at least one documented historical
claim did not match. Exit `2` means invalid/missing/changed inputs or an output
error. Neither means that an application candidate was published or rejected.

Compare a rerun with the retained measured output:

```bash
cmp backend/artifacts/findings/report.json evidence/findings/expected-report.json
cmp backend/artifacts/findings/REPORT.md evidence/findings/REPORT.md
```

The report is deterministic. The retained JSON includes the SHA-256 of the full
comparison CSV, so that file can be regenerated without keeping another large
derived copy in Git. Input hashes identify exact bytes; they are not an EIA
signature or proof that the source itself has no omissions.

## Inputs and scope

All required inputs are in [inputs/](inputs/). The command checks the size and
SHA-256 of every file against [manifest.json](inputs/manifest.json) before analysis.
Git attributes prevent line-ending conversion of the pinned inputs and retained
outputs. Original CSV CRLF line endings are preserved as part of their identity.
The three original CSV files retain their headers, row order, identifiers, decimal
text, and bytes. The JSON probes retain their existing sanitized bytes. No private
credential configuration, downloader, private note, or original manifest was imported.

| Check | Required bundled inputs | Date scope |
|---|---|---|
| Reconciliation and daily keys | `us_20241002_20261002.csv`, `facility_20241002_20261002.csv`, `generator_20241002_20261002.csv` | All 731 dates |
| AN-01 | National and facility CSVs above | September 30 → October 1, 2026 |
| AN-02 | All three CSVs above | Full window; Palisades first observed September 9, 2025 |
| AN-03 | Facility/generator CSVs; `facility_one_day.json`, `facility_one_day_after_last.json`, `generator_one_day.json`, `facility_browns_ferry.json`, `generator_browns_ferry.json`, `facility_two_years_after_last.json` | October 1, 2026; full-window end probe |
| F1 and F2 | Facility/generator CSVs | Millstone August 4, 2026; generator `1` September 15, 2026 |

`metadata_us.json`, `metadata_facility.json`, and `metadata_generator.json` are also
preserved and hashed as the supporting source-unit/route evidence for F3. The report
does not infer EIA's capacity definition from these metadata descriptions.

The original January 1, 2025–October 2, 2026 exports are not duplicated here.
During import, every parsed row in those three original files was compared with
the same subwindow of the bundled export, including source text. They agree:
640 national, 34,949 facility, and 60,549 generator rows. `original_findings_window`
in the result reports that subwindow separately. The full-window checks extend
the analysis to 731 days; they do not silently replace the historical 640-day scope.

## Results from the saved real data

See [the generated report](REPORT.md) and [full measured result](expected-report.json).

| Observation | Measured result |
|---|---|
| Daily coverage and unique keys | 731 national, 39,863 facility, 69,103 generator rows; all 731 dates present; no duplicate daily keys |
| Exact reconciliation | 79,726 generator-to-facility comparisons plus 2,924 facility/generator-to-national comparisons; all 82,650 differences are exactly 0 MW |
| AN-01 | 97,620.5 → 100,056.7 MW; +2,436.2 MW; same 55 facilities; 47 increased, 8 unchanged |
| AN-02 | September 9, 2025–October 2, 2026; 389 consecutive exact 100% records; capacity/outage 768.5 → 815.6 MW; generator `1` agrees |
| AN-03 | All-facility one-day total 95 vs 55 rows; Browns Ferry total 3 vs 1 row; empty probes at offsets 55 and 39,863; two-year advertised total 69,103 |

F1 also reproduces 40.95% from `863.4 / 2108.4 * 100`, compared with the simple
unit mean of 50%. F2 finds generator `1` at 47 facilities on September 15, 2026.

Observed values are calculated. The possible seasonal explanation for AN-01 and
the possible internal generator-count explanation for AN-03 are not calculated
facts. The source-backed Palisades restart explanation remains in
[FINDINGS.md](../../FINDINGS.md#an-02--palisades-enters-the-dataset-fully-offline),
separate from the measured 389-day duration. Product behavior remains governed by
[A5](../../DECISIONS.md#a5--validation-decides-whether-data-is-ready-closed) and
[A9](../../DECISIONS.md#a9--data-contract-v1-finalized); this command changes no policy.

## Review of the previous analysis

The implementation adapts the earlier `generate_report.py` methods: CSV reads,
Decimal sums, daily facility sets, calendar-consecutive runs, generator identity,
and weighted percentages. It also turns the existing
[AN-01 check](../../ai/sessions/2026-10-02-capacity-anomaly-facility-comparison.md)
and [Palisades/API checks](../../ai/sessions/2026-10-02-palisades-pagination-and-metadata.md)
into reusable functions. Alayala's original analysis remains his contribution.

The reviewed original script SHA-256 was
`0ca501c5ec55bee9f660f1c4d65908b96471a8a1645fca4011441998dae43f7c`.
The imported command excludes fixed claims about EIA's processing and seasonal
causes. It checks every facility against its generator group, uses zero MW
tolerance, and requires positive capacity, equal outage, and reported 100% for a
fully offline record. The former script's 99.9% threshold does not establish
AN-02's exact claim. No second connector or fetch command is introduced.

The historical probes contain timestamps, routes, key-free parameters, response
rows/totals, and API versions. They are selected diagnostic responses, not a full
archive of the original CSV download. The report ties probes to their dates,
filters, sorting, CSV values, and actual end offsets. Their results support saved
page exhaustion; they do not prove every historical page used stable sorting or
that EIA has no omissions shared by all grains.

## Synthetic verification and separate live gate

Run the focused tests from the repository root:

```bash
python3 -m unittest discover -s backend/tests -p test_findings_report.py -v
```

These tests use invented rows to check tiny MW differences, cancelling facility
differences, missing groups, duplicate keys, invalid numbers, date gaps, 99.9%
versus full outage, zero denominators, changed probe scope, nonempty end probes,
changed inputs, and preservation of previous outputs. They do not supply any
values in FINDINGS.md. The full backend suite uses the existing project environment.

Phase 2 is separate: existing S3 protection and a live preparation run still need
verification. A role ARN proves identity, not successful preparation or S3
protection. Keep the existing setup. The live gate requires actual EIA retrieval,
verified storage/readback, exit `0`, and verified `evidence/preparation/result.json`
with `published=false`. This offline report does not pass that gate.
