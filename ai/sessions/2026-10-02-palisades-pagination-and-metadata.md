# Session log — Palisades, pagination, and metadata

Date: October 2, 2026. Scope: data evidence and documentation.

## Objective and contributions

[ME] Alayala approved Palisades as AN-02 and requested investigation of further anomalies and how pagination/metadata work. [YOU] AI inspected the two-year CSVs, checked official sources, ran nine bounded API requests, saved responses without credentials, and drafted the findings and reproduction checks. A1–A4 in [DECISIONS.md](../../DECISIONS.md) remain unchanged. No application implementation or publication policy was selected.

## Findings and limits

Palisades has 389 consecutive daily rows at 100% outage from September 9, 2025 to October 2, 2026. Capacity and outage begin at 768.5 MW and end at 815.6 MW. Its generator rows match. It is the sole plant addition in the two-year window; no plants disappear or have internal gaps. All other 54 plants appear on every date.

EIA's January 26, 2026 article explicitly explains that Palisades entered the outage count when its status changed to restarting on September 9, 2025. The article explains the entry; it does not independently verify all later CSV records. [EIA source](https://www.eia.gov/TODAYINENERGY/detail.php?id=67047).

The live API confirms daily frequency and units, and reproduces the facility total mismatch. The interpretation that the total counts underlying generators is an inference from returned counts; EIA's implementation was not inspected. Unlike the earlier uncertainty, there is now direct evidence that a higher total can coexist with an exhausted facility response. Do not silently overwrite that total or declare every possible download complete.

## Candidate third anomaly: Callaway's extended full outage

Status: not selected. Alayala chose the facility API count mismatch as AN-03. The earlier investigation below is retained as supporting history.

Callaway (`facility = 6153`, generator `1`) has 99 consecutive daily records at 100% outage from March 29 to July 5, 2025. On March 28 it reports 0% outage. On March 29, capacity and outage both equal 1,236 MW; from April 1 through July 5 they both equal 1,190 MW. On July 6 outage falls to 1,130.5 MW, or 95%: power has begun to return, but the plant is not fully available. The facility and generator values match on the inspected boundary dates.

This is the longest full-plant 100% run in the inspected window after Palisades; the next is Columbia's 63-day run. NRC's May 8 report identifies Callaway as a refueling outage with a down date of March 29. That supports the outage category, not a complete explanation for its length. Ameren's 2025 filing says its last refueling completed in July 2025 (search result inspected; the SEC page did not load directly). No claim is made about the specific maintenance work responsible for all 99 days. [NRC report](https://www.nrc.gov/reading-rm/doc-collections/event-status/reactor-status/2025/20250508ps).

Proposed handling if selected: preserve valid repeated daily outage records, identify a continuous run by consecutive dates, and distinguish resuming some power from reaching full power. Any missing day breaks a confirmed continuous run. These are proposed product rules, not implemented functionality.

The wider scan found no missing/invalid numeric inputs, out-of-range percentages, or outage percentages inconsistent with MW beyond 0.0051 percentage points. Other candidates retained for later work: Sequoyah unit 2 has a 228-day run already in progress at the start of this extract; Turkey Point unit 4 capacity alternates by 22 MW at monthly boundaries in early 2026. Neither is counted as an accepted anomaly or given an unverified cause.

## Saved API evidence

Files live under `data/api_evidence_20261002/` in the data workspace. They record UTC retrieval time, route, parameters without the key, API version, response, and warnings. All nine requests succeeded under API version 2.1.14. Credentials and echoed request objects were excluded. These are selected responses, not a complete raw archive of the original paginated download.

| File | Verified content |
|---|---|
| `metadata_us.json`, `metadata_facility.json`, `metadata_generator.json` | Daily frequency, units, filters, advertised date range, and NRC source description. |
| `facility_one_day.json` | October 1, 2026: total 95, returned 55; identifiers and numeric values match the local CSV. |
| `facility_one_day_after_last.json` | Same date, offset 55, length 5: total 95, returned 0. |
| `generator_one_day.json` | Same date: total 95, returned 95. |
| `facility_browns_ferry.json`, `generator_browns_ferry.json` | Facility 46 on that date: both total 3; returns 1 plant row versus 3 generator rows. |
| `facility_two_years_after_last.json` | October 2, 2024–October 2, 2026, offset 39,863, length 1: total 69,103, returned 0. |

The API checks use explicit sorting by each route's candidate key fields. The existing downloader sorts by period only; these probes do not retroactively prove stable ordering for every earlier page. Matching local unique keys, daily coverage, and generator groups provide additional evidence, not proof of the API's internal consistency.

## Repeat the local checks

Run from the data workspace. No network access or credential is needed. This exact code was executed and all assertions passed before the document write.

```bash
python3 - <<'PY'
import csv, json
from pathlib import Path
from decimal import Decimal
from datetime import date, timedelta
from collections import defaultdict

base = Path("data/last_2_years_20241002_20261002")
def load(grain):
    with (base / f"{grain}_20241002_20261002.csv").open(newline="") as source:
        return list(csv.DictReader(source))
fac, gen, national = load("facility"), load("generator"), load("us")
expected = {(date(2024, 10, 2) + timedelta(days=i)).isoformat() for i in range(731)}
byday = defaultdict(set)
for row in fac:
    byday[row["period"]].add(row["facility"])
assert set(byday) == expected
changes = []
days = sorted(byday)
for a, b in zip(days, days[1:]):
    for kind, ids in (("appears", byday[b] - byday[a]),
                      ("disappears", byday[a] - byday[b])):
        changes.extend((b, kind, plant) for plant in sorted(ids))
assert changes == [("2025-09-09", "appears", "1715")]
p = sorted((r for r in fac if r["facility"] == "1715"), key=lambda r:r["period"])
expected_p = {(date(2025, 9, 9) + timedelta(days=i)).isoformat() for i in range(389)}
assert len(p) == len({r["period"] for r in p}) == 389
assert {r["period"] for r in p} == expected_p
assert all(Decimal(r["percentOutage"]) == 100 and
           Decimal(r["outage"]) == Decimal(r["capacity"]) for r in p)
gp = {r["period"]:r for r in gen if r["facility"] == "1715" and r["generator"] == "1"}
assert set(gp) == expected_p
assert all(Decimal(r[k]) == Decimal(gp[r["period"]][k])
           for r in p for k in ("capacity", "outage", "percentOutage"))
print("Membership changes:", changes)
print("Palisades:", len(p), "consecutive daily records at 100% offline")
print("Palisades first/last:", p[0], p[-1])
# Callaway is a candidate, not an accepted third anomaly.
c = {r["period"]:r for r in fac if r["facility"] == "6153"}
run = [(date(2025, 3, 29) + timedelta(days=i)).isoformat() for i in range(99)]
assert all(Decimal(c[d]["percentOutage"]) == 100 for d in run)
assert Decimal(c["2025-03-28"]["percentOutage"]) == 0
assert Decimal(c["2025-07-06"]["percentOutage"]) == 95
print("Callaway: 99 daily records at 100%, then 95% on 2025-07-06")
evidence = Path("data/api_evidence_20261002")
def response(name):
    return json.loads((evidence / (name + ".json")).read_text())["response"]
for grain in ("us", "facility", "generator"):
    meta = response("metadata_" + grain)
    assert meta["defaultFrequency"] == "daily"
    assert {k:v["units"] for k,v in meta["data"].items()} == {
        "capacity":"megawatts", "outage":"megawatts", "percentOutage":"percent"}
    print(grain, "facets:", [f["id"] for f in meta["facets"]])
for name, total, count in (("facility_one_day",95,55),
                           ("facility_one_day_after_last",95,0),
                           ("generator_one_day",95,95),
                           ("facility_browns_ferry",3,1),
                           ("generator_browns_ferry",3,3),
                           ("facility_two_years_after_last",69103,0)):
    r = response(name)
    assert int(r["total"]) == total and len(r["data"]) == count
    print(name, "API total:", total, "returned:", count)
print("All local evidence assertions passed.")
PY
```

## Repeat the API requests

The original diagnostic used the existing downloader's local key configuration. For a portable rerun, the following equivalent requests use an already configured `EIA_API_KEY` environment variable. The user runs key-bearing commands under the local working agreement. This replay snippet was syntax-checked, not executed; the nine equivalent requests recorded in the JSON evidence were executed. It prints selected non-secret results and writes no files. Fresh results can differ if EIA revises the source.

```bash
python3 - <<'PY'
import json, os, urllib.parse, urllib.request
from pathlib import Path

key = os.environ["EIA_API_KEY"]
for path in sorted(Path("data/api_evidence_20261002").glob("*.json")):
    saved = json.loads(path.read_text())
    suffix = "/" if saved["metadata"] else "/data/"
    params = saved["parameters"] + [["api_key", key]]
    url = "https://api.eia.gov/v2/nuclear-outages/" + saved["route"] + suffix
    try:
        with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params), timeout=40) as reply:
            response = json.load(reply)["response"]
        if saved["metadata"]:
            print(path.name, response.get("frequency"), response.get("data"))
        else:
            print(path.name, "total", response.get("total"), "rows", len(response.get("data", [])))
    except Exception as error:
        print(path.name, "request failed:", type(error).__name__, getattr(error, "code", ""))
        raise SystemExit(1)
PY
```

## Verification and handoff

The local evidence assertions, saved-response checks, Markdown code fences, and relative links were checked. A Python bytecode compilation attempt hit a sandbox cache restriction; an in-memory syntax check passed instead. Document diffs are reviewed before writing and saved bytes are verified against the reviewed drafts. No application tests apply to this documentation task. No commit, push, or source CSV modification occurred.

Pending: confirm the exact seasonal capacity methodology, decide how production validation handles the observed total mismatch, and correct unsupported explanations in the older generated report. The third anomaly is now selected and documented as AN-03. Metadata verification does not itself select keys or SQL types. Do not mark the entire data phase closed.

Next: review AN-03 in FINDINGS.md. The anomaly-selection task is complete; the full data-evidence phase remains open.

## AN-03 selection correction

[ME] Alayala rejected Callaway as the third selection and identified the reproduced facility API count mismatch as the anomaly. [YOU] AI added AN-03 to FINDINGS.md, corrected the current count to three, and updated this handoff. Five assertions against the saved API responses passed again; no new API requests or application changes were made. The confirmed mismatch stays separate from the inferred internal cause. The existing reproduction code and source evidence were preserved.
