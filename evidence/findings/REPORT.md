# Findings reproduction — measured results

Window: 2024-10-02 through 2026-10-02.
Historical claims reproduced: True.

| Check | Matches historical claim |
|---|---|
| at_least_30_days | True |
| daily_coverage_and_keys | True |
| exact_reconciliation | True |
| AN01_capacity_step | True |
| AN01_same_55_facilities | True |
| AN02_first_and_last | True |
| AN02_389_full_days | True |
| AN02_generator_agreement | True |
| AN02_only_facility_addition | True |
| AN02_entry_capacity | True |
| AN03_probes_match_csv | True |
| AN03_one_day_counts | True |
| AN03_browns_ferry | True |
| AN03_final_empty_probes | True |
| F1_weighted_example | True |
| F2_generator_1_reused | True |

Exact MW comparisons: 82650; nonmatching: 0.
Every date, entity, metric, compared value, and signed difference is in `reconciliation.csv`.
`report.json` contains measured anomaly values, source checksums, and request scopes.

## AN-01 — Capacity step

2026-09-30: 97620.5 MW; 2026-10-01: 100056.7 MW.
Difference: 2436.2 MW; summed facility difference: 2436.2 MW.
Facilities: 55 → 55; added: []; removed: [].
Increased: 47; decreased: 0; unchanged: 8.

## AN-02 — Palisades

First observed: 2025-09-09; last: 2026-10-02; records: 389.
First capacity/outage: 768.5/768.5 MW.
Last capacity/outage: 815.6/815.6 MW.
Longest exact full-outage run: 389 days, 2025-09-09 through 2026-10-02.
Missing dates: []; generator 1 agrees: True.

## AN-03 — Saved API probes

| Probe | Advertised total | Returned | Offset | Agrees with CSV scope |
|---|---:|---:|---:|---|
| facility_one_day | 95 | 55 | 0 | True |
| facility_one_day_after_last | 95 | 0 | 55 | True |
| generator_one_day | 95 | 95 | 0 | True |
| facility_browns_ferry | 3 | 1 | 0 | True |
| generator_browns_ferry | 3 | 3 | 0 | True |
| facility_two_years_after_last | 69103 | 0 | 39863 | True |

## Supporting checks

Millstone: 863.4 / 2108.4 × 100 = 40.95% (display); unit mean: 50.0%.
Generator 1 occurs at 47 facilities on 2026-09-15.

## Evidence limits

- Saved observations only; no current EIA query or proof of source completeness.
- API probes are selected responses, not every original download page.
- Seasonal cause and EIA internal counting method are not measured here.
- No S3 protection, live preparation, or application publication is verified.
