# Data findings — Trinity

Status: ongoing data evidence, October 4, 2026. Phase 3 now reproduces the selected findings from bundled historical inputs. A4 remains accepted: PostgreSQL stores application state; Apache DataFusion queries outage data in Parquet.

Contract update: [A9](DECISIONS.md#a9--data-contract-v1-finalized) and [data contract v1](docs/schema.md) now specify keys, types, metric behavior, and validation rules. This is a new specification, not a rerun of the evidence below. Historical observations and source explanations remain unchanged.

## Authorship and evidence

Alayala fetched the data, analyzed it, and wrote the original findings in this document. AI organized the text, corrected wording, and added evidence references. AI also ran separate read-only checks of the local CSV exports. These checks support the findings; they do not transfer authorship of the original analysis to AI.

The evidence below distinguishes observed values from explanations and proposed product handling. Three selected anomalies are documented. Data review continues as new evidence appears; follow the [ongoing anomaly workflow](AGENTS.md#ongoing-anomaly-workflow). Remaining source-definition and verification work is tracked below. New candidates are not automatically confirmed findings.

**October 4 reproduction:** AI adapted the existing report methods and recorded checks into [one offline command](scripts/generate_report.py), imported the reviewed source exports and sanitized API probes, and ran the analysis. All 16 historical claim checks passed. The [reproduction guide](evidence/findings/README.md), [measured report](evidence/findings/REPORT.md), and [full result with input checksums](evidence/findings/expected-report.json) provide the inputs, scope, and results. Synthetic tests are separate from this real saved-data evidence. No live EIA/S3 preparation or publication is established by this run.

## Data inspected

Local workspace files cover January 1, 2025 through October 2, 2026. A grain is the level represented by one row: national, facility, or generator.

| Grain | File under the workspace `data/` folder | Rows | Distinct days |
|---|---|---:|---:|
| National | `us_20250101_20261002.csv` | 640 | 640 |
| Facility | `facility_20250101_20261002.csv` | 34,949 | 640 |
| Generator | `generator_20250101_20261002.csv` | 60,549 | 640 |

Historical supporting report: `data/REPORT_20250101_20261002.md` in the original data workspace. It is not required by the repository's reproduction command. Its explanations are not all independently verified. Agreement between exports does not prove that the API download is complete.

The later two-year export is in `data/last_2_years_20241002_20261002/`: 731 national rows, 39,863 facility rows, and 69,103 generator rows covering October 2, 2024–October 2, 2026. AN-02 and the new API checks use this export. All 731 dates are present, candidate keys are unique, and capacity/outage totals agree between national rows, facilities, and generators. The facility API total issue is documented below.

Those three two-year files are now preserved byte-for-byte under [evidence/findings/inputs/](evidence/findings/inputs/). Their January 1, 2025–October 2, 2026 subwindow matches every parsed row and source field in the three original exports above; AI checked this during import. This keeps the original scope reproducible without duplicating the shorter files.

## F1 — Calculate percentages from capacity and outage

**Alayala's finding:** A facility percentage is not the simple average of its generators' percentages. Each generator has its own capacity. Apply the same rule when calculating the national percentage.

**Observed example:** Millstone, `facility = 566`, on `2026-08-04`.

| Row | Capacity (MW) | Outage (MW) | Percent offline |
|---|---:|---:|---:|
| Generator `2` | 863.4 | 863.4 | 100% |
| Generator `3` | 1,245.0 | 0.0 | 0% |
| Facility | 2,108.4 | 863.4 | 40.95% |

The simple average is 50%. The capacity-weighted result is `863.4 / 2108.4 * 100`, which rounds to 40.95%. Capacity-weighted means that a larger generator contributes more to the total.

**Evidence:** AI matched these rows in the facility and generator exports. The values support summing megawatts before calculating the percentage. They do not establish EIA's internal processing method.

**Product implication:** Calculate the offline share as `sum(outage) / sum(capacity) * 100` for the same date and selected entities. Use the national row's same-day values for the national metric. Do not average percentages or reconstruct outage MW from a rounded percentage.

## F2 — Identify a generator within its facility

**Alayala's finding:** `generator` alone is not unique. Keep the source name `facility` in the schema. Use `facilityName` as descriptive text, not as the identifier.

| Purpose | Candidate key | Example |
|---|---|---|
| Identify a reactor over time | `(facility, generator)` | `(46, "1")`: Browns Ferry unit 1 |
| Identify one daily reactor row | `(period, facility, generator)` | `(2026-09-15, 46, "1")` |

Another reactor example from the original notes is `(371, "2")`: Columbia unit 2. Generator numbers need not begin at 1 at each facility.

**Evidence:** In the generator export, `generator = "1"` occurs at 47 distinct facilities on `2026-09-15`. AI found no duplicate `(period, facility, generator)` keys across the 60,549 generator rows. It also found no duplicate `(period, facility)` facility keys or `period` national keys in this window.

**Product implication:** A join or lookup using only `generator` can combine different facilities. Include `facility`; include `period` when matching daily observations. A9 now specifies these keys and source-string identifiers in [DECISIONS.md](DECISIONS.md).

## F3 — MW measures power, not energy over a day

**Alayala's finding:** Megawatts (MW) measure power. They do not measure energy produced or lost during the day. Megawatt-hours (MWh) measure energy over time.

**Product implication:** Label `capacity` and `outage` in MW. Do not label an outage value as daily energy loss. A daily record does not by itself provide the hourly information needed to calculate that loss.

**Source check:** The CSV exports omit the source unit columns. The live metadata and sample responses saved on October 2, 2026 confirm MW for capacity/outage and percent for `percentOutage`. See “API metadata and pagination checks” below for the source observation timing and remaining definition limits.

## F4 — The national totals match the lower-level totals

**Alayala's finding:** National totals match the sum of facilities and the sum of generators.

**Verification scope:** AI independently checked every date from `2025-01-01` through `2026-10-02` in the three exports. It parsed numeric values with Python `Decimal`, which preserves decimal arithmetic for these comparisons.

| Comparison | Field | Days checked | Mismatched days |
|---|---|---:|---:|
| National vs sum of facilities | `capacity` | 640 | 0 |
| National vs sum of facilities | `outage` | 640 | 0 |
| National vs sum of generators | `capacity` | 640 | 0 |
| National vs sum of generators | `outage` | 640 | 0 |

All 2,560 comparisons had an exact difference of 0 MW. Each export contains all 640 dates in this interval.

**October 4 extension:** The bundled 731-day export produced 79,726 generator-to-facility and 2,924 facility/generator-to-national capacity/outage comparisons. All **82,650 comparisons** had an exact difference of **0 MW**. The command writes every date, entity, metric, compared value, and signed difference to `reconciliation.csv`; its hash is in the [retained result](evidence/findings/expected-report.json). The original 640-day observation above remains unchanged.

**Limit:** This confirms agreement in the inspected exports. It does not prove full API history coverage, complete pagination, or the absence of reporting gaps at individual facilities. Do not invent a MW mismatch to satisfy the challenge.

## F5 — Capacity changes across dates

**Alayala's interpretation:** Capacity changes with the season.

**Observed example:** National capacity changes across the September–October boundary.

| Date | National capacity (MW) |
|---|---:|
| `2026-09-30` | 97,620.5 |
| `2026-10-01` | 100,056.7 |
| Difference | +2,436.2 |

**Evidence:** AI checked the national rows. Both dates contain the same set of 55 facility identifiers. The change is therefore not explained by a facility appearing or disappearing between these two dates.

**Interpretation limit:** This supports a changing denominator. It does not by itself prove which seasonal capacity definition EIA uses or the exact date of its switch. Keep the seasonal explanation provisional until a source specific to this dataset confirms it.

**Product implication:** Use the capacity recorded for the same date as the outage. Do not use one fixed capacity for every day.

## Anomalies

Three anomalies are documented below, with observed examples, supporting checks, and proposed product handling.

### AN-01 — Reported capacity increased overnight

**What happened?** From September 30 to October 1, 2026, total U.S. nuclear capacity rose from **97,620.5 MW to 100,056.7 MW**. That is an increase of **2,436.2 MW**.

**What did we check?** The same 55 plants appear on both days. Capacity increased at 47 plants and stayed the same at eight. Adding the changes from all plants gives exactly the national increase.

For example, **Peach Bottom** (`facility = 3166`) rose from **2,549.4 to 2,694.1 MW**: an increase of **144.7 MW**, the largest among the plants.

**Why is it unusual?** Many plants report higher capacity on the same day, even though no plant was added to the list. This does not mean the data is wrong.

**Why did it happen?** It may be a seasonal adjustment. We have confirmed the change, but have not confirmed its cause.

**How should Trinity handle it?** Use each day's reported capacity when calculating the percentage offline: `outage / capacity × 100`. Using one fixed capacity for every day would give the wrong percentage when capacity changes. This behavior is specified by A9, not implemented yet.

**How can someone check it?** We compared the saved national and plant CSVs for those two dates. The check passed. The [supporting check](ai/sessions/2026-10-02-capacity-anomaly-facility-comparison.md#reproducible-check-for-an-01) contains the command and the five largest changes.

This expands F5. Alayala selected it as an anomaly; AI checked the plant values and helped write this explanation.

### AN-02 — Palisades enters the dataset fully offline

**What happened?** Palisades (`facility = 1715`, generator `1`) first appears in our two-year export on **September 9, 2025**. Its capacity and outage were both **768.5 MW**, so it was **100% offline**. It stays at 100% offline for **389 consecutive daily records**, through October 2, 2026. On the last date, capacity and outage are both **815.6 MW**.

**Why did it happen?** EIA explains that Palisades changed from decommissioning to restarting on September 9, 2025. It was producing no power, so EIA began counting it as an outage. This explains its entry into the dataset; the 389-day duration comes from our saved rows. [EIA explanation, January 26, 2026](https://www.eia.gov/TODAYINENERGY/detail.php?id=67047).

**Why does it matter?** A plant can enter the dataset already offline. Its first appearance does not mean it suffered a new breakdown that day. Adding Palisades increased national capacity by **768.5 MW**; capacity at the existing plants did not change that day.

**How should Trinity handle it?** Include the reported capacity and outage from its first available date. Show earlier dates as “not reported,” not zero outage. Keep the restart explanation separate from the measured values. This behavior is specified by A9, not implemented yet.

**Did any plants disappear?** No. In our October 2, 2024–October 2, 2026 export, the other 54 plants appear every day. Palisades is the only plant added; no plant disappears or has a gap after its first appearance. This statement covers the saved two-year export, not all EIA history.

**How can someone check it?** The [supporting check](ai/sessions/2026-10-02-palisades-pagination-and-metadata.md#repeat-the-local-checks) compares daily plant lists and checks Palisades against its generator rows. It passed. Alayala approved this anomaly; AI performed the checks and drafted the entry.

### AN-03 — The facility API reports more rows than it returns

**What happened?** For **Browns Ferry** (`facility = 46`) on **October 1, 2026**, the facility API reports **3 matching rows**, but returns **1 plant row**. The generator API reports and returns **3 generator rows** for the same plant and date.

**What did we check?** For all plants on that date, the facility API reports **95 rows** but returns **55**. Asking for rows after those 55 returns nothing. The same problem occurs in the two-year download: **69,103 reported**, **39,863 returned**, and no rows after the last one. The [API checks below](#api-metadata-and-pagination-checks) contain the detailed results.

**Why is this an anomaly?** The advertised total does not match the number of plant rows available. Trusting that total alone could make Trinity report an incomplete download or keep requesting rows that do not exist.

**Why does it happen?** The reported total matches the generator count in our examples. EIA appears to count generators instead of plants. The mismatch is confirmed; the internal cause is still an inference.

**Rechecked October 3, 2026.** The connector's live extraction for October 1, 2026 again returned 55 facility rows against an advertised total of 95. See the [evidence brief](evidence/2026-10-03-first-live-eia-run.md).

**How should Trinity handle it?** Send the downloaded version to validation. If its counts and required checks pass, it is ready for publication without a user-facing warning about this known EIA count issue. If validation fails, the version stays unpublished. See [A5 in DECISIONS.md](DECISIONS.md#a5--validation-decides-whether-data-is-ready-closed) for the accepted rule and its relationship to Admin approval. The checks still need implementation.

**How can someone check it?** Run the [offline report command](evidence/findings/README.md#run-from-the-repository-root) against the original sanitized responses now bundled in `evidence/findings/inputs/`. It checks counts, request scope, CSV agreement, and the empty probes at offsets 55 and 39,863. These are selected probes, not all original download pages. The [historical supporting checks](ai/sessions/2026-10-02-palisades-pagination-and-metadata.md#repeat-the-local-checks) and live-rerun requests remain available. Alayala selected this as the third anomaly; AI reproduced the mismatch and wrote the explanation.

## API metadata and pagination checks

**Metadata describes the dataset.** A route without `/data/` returns its description, fields, units, filters, and available dates. Adding `/data/` requests actual rows. This is how EIA documents its API. [EIA API guide](https://www.eia.gov/opendata/documentation.php).

We queried all three route descriptions on October 2, 2026 and saved the responses in the data workspace under `data/api_evidence_20261002/`. Reviewed copies are now bundled in `evidence/findings/inputs/` with the original bytes and checksums.

| Item | Confirmed response |
|---|---|
| Date frequency and format | Daily; `YYYY-MM-DD` |
| Capacity and outage | `megawatts` |
| Percent outage | `percent` |
| Filters (called facets by EIA) | National: none. Facility: `facility`. Generator: `facility` and `generator`. |
| Available range advertised by all routes | January 1, 2007–October 2, 2026. This is not a claim that we downloaded that full range. |

The metadata names NRC's Power Reactor Status Report as its source. NRC says its status observations are collected between 4 a.m. and 8 a.m. Eastern time. These are daily status observations, not daily energy measurements. The precise seasonal capacity definition and EIA's treatment of missing source reports still need dataset-specific confirmation. [NRC daily report notes](https://www.nrc.gov/reading-rm/doc-collections/event-status/reactor-status/2025/20250508ps).

**Pagination means requesting rows in batches.** `length=5000` asks for up to 5,000 rows. `offset=0`, `5000`, and `10000` ask for successive batches. The downloader stops when a batch contains fewer than 5,000 rows. EIA documents `total` as the total matching row count, but the facility route behaves inconsistently in our checks. [EIA pagination documentation](https://www.eia.gov/opendata/documentation.php).

For **October 1, 2026**, live requests returned:

| Request | API total | Actual returned rows |
|---|---:|---:|
| All plants, offset 0, length 5000 | 95 | 55 |
| All plants, offset 55, length 5 | 95 | 0 |
| All generators, offset 0, length 5000 | 95 | 95 |
| Browns Ferry plant (`facility = 46`) | 3 | 1 |
| Browns Ferry generators (`facility = 46`) | 3 | 3 |

**What this means:** The facility total matches the generator count in these requests. That suggests EIA counts generators before combining them into plant rows; we have not inspected EIA's internal code. The mismatch is directly reproduced in EIA responses, not introduced by our CSV report.

For the two-year request, offset **39,863** returned **zero rows**, while `total` still said **69,103**. Our saved 39,863 plant/date rows also match the groups formed from the 69,103 generator rows. The live one-day plant rows match the saved CSV values. This supports reaching the end of the returned plant rows. It does not make the misleading total valid or prove the source itself has no omissions.

**Validation handling:** Follow [A5 in DECISIONS.md](DECISIONS.md#a5--validation-decides-whether-data-is-ready-closed). The known source total alone cannot determine completeness. Page exhaustion, unique keys, date coverage, and agreement with generator groups are evidence for the validation design. A9 now specifies the required checks and zero-MW reconciliation tolerance; implementation and runtime verification remain pending.

The [supporting session](ai/sessions/2026-10-02-palisades-pagination-and-metadata.md) lists the saved requests, reproduction steps, and remaining limits.

## Reproduction and remaining evidence

Run from the repository root, using the bundled inputs and a new output directory:

```bash
python3 scripts/generate_report.py --inputs evidence/findings/inputs --out backend/artifacts/findings
```

The command needs only Python's standard library and makes no network calls. It verifies input hashes, reports exact measured values, and returns `0` only when all recorded historical claim checks match. See the [guide](evidence/findings/README.md) for inputs, dates, output files, failure behavior, and the separate synthetic test command.

During the earlier formatting task, AI used separate inline checks. During the October 2 readiness review, AI reviewed and ran the old workspace `generate_report.py`; the report matched apart from its timestamp/output filename. Its fixed explanations were not calculated conclusions. The October 4 implementation reuses the useful methods and supporting session checks, removes those fixed causal claims, adds per-facility reconciliation, and checks exact full outage rather than the old 99.9% threshold.

The report methods and inputs are now preserved for reproduction. The precise seasonal capacity definition and EIA's revision methodology remain open. A9 selects full-window re-fetching for Trinity's revision handling and specifies validation checks; it does not establish EIA's internal methods. All three selected anomalies remain the capacity increase, Palisades entering fully offline, and the facility API count mismatch. Callaway was not selected. Real S3 protection and live preparation remain unverified. Data evidence remains ongoing as defined in AGENTS.md.

See [Engineering Notes](NOTES.md) for contributions and [the closed session](ai/sessions/2026-10-02-data-findings-and-handoff.md) for the handoff.
