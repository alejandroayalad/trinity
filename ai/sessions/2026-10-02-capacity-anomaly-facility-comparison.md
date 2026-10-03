# Session log — Capacity anomaly and facility comparison

Date: October 2, 2026. Timezone: America/Merida.
Scope: data analysis and documentation; no application implementation.

## Objective and contributions

[ME] Alayala selected F5 as a good anomaly and requested a new anomalies section below the existing findings. [YOU] AI inspected the local CSV exports, compared facilities between September 30 and October 1, drafted AN-01, and wrote and executed the reproduction command embedded in [FINDINGS.md](../../FINDINGS.md).

## Decisions and corrections

A1–A4 in [DECISIONS.md](../../DECISIONS.md) remain unchanged. AN-01 is an evidence identifier, not a new architecture decision. Proposed product handling is not implemented behavior. The seasonal explanation remains a hypothesis. Matching national totals do not establish download completeness, and unchanged facility membership does not prove unchanged generator membership.

The existing reproduction paragraph was updated to distinguish the earlier formatting task from the later successful report runs. Fixed explanatory text in the report is not verified by executing it. No script authorship was inferred.

## Checks and results

The reproduction command reads `data/facility_20250101_20261002.csv` and `data/us_20250101_20261002.csv` from the data workspace, using Python Decimal arithmetic. It makes no API requests and does not change source files.

| Check | Observed result |
|---|---|
| Boundary dates and selected keys | Both dates present; no duplicate selected keys. |
| Facility membership | Same 55 identifiers; none added or removed. |
| Capacity changes | 47 increased, eight unchanged, none decreased. |
| Largest increase | Peach Bottom, facility 3166: 2,549.4 to 2,694.1 MW, +144.7 MW. |
| Reconciliation | Each facility sum equals the national capacity; summed changes equal +2,436.2 MW with zero difference. |

The exact embedded reproduction command ran successfully; all assertions passed. Document staging checks compare original text, relative links, code fences, and the changed-file diff. Saved-file equality is checked during publication of these reviewed drafts. Git diff is unavailable because the data workspace is not a Git repository. No application tests ran: this task changed evidence documentation only. No commit, push, API-key access, or new download occurred.

## Open questions and next action

One anomaly is now documented in its own section; two more still need selection and evidence. Source units, pagination completeness, the seasonal cause, and application validation policies remain open. The author has not yet given an explanation demonstrating understanding of the new reproduction command.

Next: review AN-01 in FINDINGS.md before selecting a second anomaly.

## Plain-language revision

Alayala requested a simpler, human-readable entry. AI shortened AN-01 and moved the supporting command and detailed table here. The observed values, uncertain cause, and proposed product behavior remain unchanged. This is an editorial change; the calculation was not changed or rerun.

## Reproducible check for AN-01

Run this command from the data workspace containing `data/`. It reads the existing national and facility exports without changing them or calling EIA. It checks the two dates, duplicate keys, plant membership, and matching totals. The exact command passed on October 2, 2026. Expected summary: 55 plants on each date, 47 increases, no decreases, eight unchanged, and a total increase of 2,436.2 MW.

| Facility | Name | 2026-09-30 capacity (MW) | 2026-10-01 capacity (MW) | Change (MW) |
|---|---|---:|---:|---:|
| `3166` | Peach Bottom | 2,549.4 | 2,694.1 | +144.7 |
| `6105` | Limerick | 2,241.8 | 2,374.3 | +132.5 |
| `6000` | Donald C Cook | 2,177.0 | 2,278.0 | +101.0 |
| `7722` | Watts Bar Nuclear Plant | 2,245.0 | 2,343.0 | +98.0 |
| `46` | Browns Ferry | 3,661.7 | 3,755.8 | +94.1 |

```bash
python3 - <<'PY'
import csv
from decimal import Decimal

before, after = "2026-09-30", "2026-10-01"

def selected_rows(path, identity):
    selected = {before: {}, after: {}}
    with open(path, newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            day = row["period"]
            if day not in selected:
                continue
            key = identity(row)
            assert key not in selected[day], ("Duplicate key", day, key)
            selected[day][key] = row
    assert all(selected.values()), "Missing boundary date"
    return selected

fac = selected_rows("data/facility_20250101_20261002.csv", lambda r: r["facility"])
us = selected_rows("data/us_20250101_20261002.csv", lambda r: "US")
added = set(fac[after]) - set(fac[before])
removed = set(fac[before]) - set(fac[after])
print("Facilities:", len(fac[before]), "->", len(fac[after]))
print("Added:", sorted(added), "Removed:", sorted(removed))
assert not added and not removed, "Membership changed; compare separately"
changes = []
for facility, old in fac[before].items():
    new = fac[after][facility]
    a, b = Decimal(old["capacity"]), Decimal(new["capacity"])
    changes.append((b - a, facility, new["facilityName"], a, b))
print("facility | name | capacity before MW | capacity after MW | change MW")
for delta, facility, name, a, b in sorted(changes, key=lambda x: (-x[0], x[1])):
    print(f"{facility} | {name} | {a} | {b} | {delta:+f}")
print("Increased / decreased / unchanged:",
      sum(x[0] > 0 for x in changes), sum(x[0] < 0 for x in changes),
      sum(x[0] == 0 for x in changes))
for day in (before, after):
    total = sum((Decimal(r["capacity"]) for r in fac[day].values()), Decimal(0))
    national = Decimal(us[day]["US"]["capacity"])
    assert total == national, (day, total, national)
    print(day, "facility sum = national capacity:", total, "MW")
facility_delta = sum((x[0] for x in changes), Decimal(0))
national_delta = Decimal(us[after]["US"]["capacity"]) - Decimal(us[before]["US"]["capacity"])
assert facility_delta == national_delta
print("Facility change = national change:", facility_delta, "MW")
PY
```

These results verify the saved rows. They do not establish the seasonal cause, original source units, complete API pagination, or unchanged generator membership.
