#!/usr/bin/env python3
"""Reproduce the selected findings from checksum-pinned historical inputs.

Read local CSV exports and sanitized API probes; make no network requests.
Write exact MW comparisons and measured findings to a new output directory.
Reject changed inputs or invalid rows. Exit 1 if historical claims do not match.
This report does not validate or publish an application candidate.
"""

import argparse
from collections import defaultdict
import csv
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
METRICS = ("capacity", "outage")
KEYS = {"us": ("period",), "facility": ("period", "facility"),
        "generator": ("period", "facility", "generator")}


def days_between(start, end):
    """Return every date in an inclusive calendar window."""
    start, end = date.fromisoformat(start), date.fromisoformat(end)
    if end < start:
        raise ValueError("Window end precedes start")
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def read_csv(path, grain):
    """Load unique daily rows without converting source decimals through floats."""
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        required = set(KEYS[grain]) | set(METRICS) | {"percentOutage"}
        if not required <= set(reader.fieldnames or []):
            raise ValueError(f"{grain}: missing CSV columns")
        rows, seen = [], set()
        for number, row in enumerate(reader, 2):
            if None in row or any(row[k] is None for k in required):
                raise ValueError(f"{grain}: malformed CSV row {number}")
            key = tuple(row[k] for k in KEYS[grain])
            if any(not value.strip() for value in key) or key in seen:
                raise ValueError(f"{grain}: empty or duplicate daily key at row {number}")
            seen.add(key)
            if date.fromisoformat(row["period"]).isoformat() != row["period"]:
                raise ValueError(f"{grain}: noncanonical date at row {number}")
            for field in (*METRICS, "percentOutage"):
                if field == "percentOutage" and not row[field].strip():
                    row[field] = None
                    continue
                value = Decimal(row[field])
                if not value.is_finite() or len(value.as_tuple().digits) > 24:
                    raise ValueError(f"{grain}: invalid number at row {number}")
                if value.as_tuple().exponent < -6 or abs(value) >= Decimal("1e18"):
                    raise ValueError(f"{grain}: number exceeds analysis precision at row {number}")
                if field == "capacity" and value < 0:
                    raise ValueError(f"{grain}: negative capacity at row {number}")
                row[field] = value
            rows.append(row)
    if not rows:
        raise ValueError(f"{grain}: empty export")
    return rows


def load_inputs(directory):
    """Verify every recorded input hash before reading the historical evidence."""
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["format_version"] != 1:
        raise ValueError("Unsupported input manifest")
    sources = {}
    for entry in manifest["files"]:
        name, role = entry["file"], entry["role"]
        if Path(name).name != name or role in sources:
            raise ValueError("Invalid input filename or duplicate role")
        path = directory / name
        content = path.read_bytes()
        if len(content) != entry["bytes"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ValueError(f"Input checksum mismatch: {name}")
        sources[role] = read_csv(path, role) if role in KEYS else json.loads(content)
    if not set(KEYS) <= sources.keys():
        raise ValueError("Input manifest must include all three exports")
    return manifest, sources


def coverage(rows, grain, start, end):
    """Report daily coverage and keys for the declared window."""
    expected, actual = set(days_between(start, end)), {r["period"] for r in rows}
    return {"rows": len(rows), "days": len(actual), "first": min(actual, default=None), "last": max(actual, default=None),
            "unique_keys": len({tuple(r[k] for k in KEYS[grain]) for r in rows}),
            "missing_dates": sorted(expected - actual), "outside_window": sorted(actual - expected)}


def grouped_totals(rows, keys):
    """Sum exact MW within each daily entity group."""
    groups = {}
    for row in rows:
        key = tuple(row[k] for k in keys)
        group = groups.setdefault(key, {m: Decimal(0) for m in METRICS})
        for metric in METRICS:
            group[metric] += row[metric]
    return groups


def reconcile(sources):
    """Compare each facility with its units, then each grain with national rows."""
    national = grouped_totals(sources["us"], ("period",))
    facilities = grouped_totals(sources["facility"], ("period", "facility"))
    units = grouped_totals(sources["generator"], ("period", "facility"))
    comparisons = []

    def compare(left, right, left_name, right_name):
        for key in sorted(left.keys() | right.keys()):
            for metric in METRICS:
                a, b = left.get(key, {}).get(metric), right.get(key, {}).get(metric)
                # A missing group is not a measured zero, even when its peer sums to zero.
                difference = None if a is None or b is None else a - b
                comparisons.append({"period": key[0], "facility": key[1] if len(key) > 1 else "",
                                    "metric": metric, "left_source": left_name, "right_source": right_name,
                                    "left_mw": a, "right_mw": b, "difference_mw": difference,
                                    "status": "missing" if difference is None else
                                              "match" if difference == 0 else "mismatch"})

    compare(units, facilities, "generator_sum", "facility")
    for grain in ("facility", "generator"):
        compare(grouped_totals(sources[grain], ("period",)), national, grain + "_sum", "national")
    return comparisons


def capacity_change(sources, before="2026-09-30", after="2026-10-01"):
    """Measure the selected capacity step and changes in facility membership."""
    national = {r["period"]: r for r in sources["us"]}
    a = {r["facility"]: r for r in sources["facility"] if r["period"] == before}
    b = {r["facility"]: r for r in sources["facility"] if r["period"] == after}
    if before not in national or after not in national or not a or not b:
        return {"available": False, "reason": "required_dates_not_reported"}
    changes = [{"facility": fid, "name": b.get(fid, a.get(fid))["facilityName"],
                "before_mw": a[fid]["capacity"] if fid in a else None,
                "after_mw": b[fid]["capacity"] if fid in b else None,
                "difference_mw": b[fid]["capacity"] - a[fid]["capacity"] if fid in a and fid in b else None}
               for fid in sorted(a.keys() | b.keys())]
    return {"available": True, "before": before, "after": after,
            "national_before_mw": national[before]["capacity"],
            "national_after_mw": national[after]["capacity"],
            "national_difference_mw": national[after]["capacity"] - national[before]["capacity"],
            "facility_total_difference_mw": sum((r["capacity"] for r in b.values()), Decimal(0)) -
                                            sum((r["capacity"] for r in a.values()), Decimal(0)),
            "facilities_before": len(a), "facilities_after": len(b),
            "added": sorted(b.keys() - a.keys()), "removed": sorted(a.keys() - b.keys()),
            "increased": sum(r["difference_mw"] is not None and r["difference_mw"] > 0 for r in changes),
            "decreased": sum(r["difference_mw"] is not None and r["difference_mw"] < 0 for r in changes),
            "unchanged": sum(r["difference_mw"] == 0 for r in changes), "facilities": changes}


def palisades(sources):
    """Measure first observation, exact full outage, continuity, and unit agreement."""
    rows = sorted((r for r in sources["facility"] if r["facility"] == "1715"), key=lambda r: r["period"])
    if not rows:
        return {"available": False, "reason": "facility_not_reported"}
    full = lambda r: r["capacity"] > 0 and r["capacity"] == r["outage"] and r["percentOutage"] == 100
    best, run, start, previous, best_start, best_end = 0, 0, None, None, None, None
    for row in rows:
        day = date.fromisoformat(row["period"])
        if full(row):
            if not run or previous is None or day - previous != timedelta(days=1):
                run, start = 0, row["period"]
            run += 1
            if run > best:
                best, best_start, best_end = run, start, row["period"]
        else:
            run = 0
        previous = day
    units = [r for r in sources["generator"] if r["facility"] == "1715"]
    unit_by_day = {r["period"]: r for r in units if r["generator"] == "1"}
    by_day = defaultdict(set)
    for row in sources["facility"]:
        by_day[row["period"]].add(row["facility"])
    days, changes = sorted(by_day), []
    for a, b in zip(days, days[1:]):
        for kind, ids in (("added", by_day[b] - by_day[a]), ("removed", by_day[a] - by_day[b])):
            changes.extend({"before": a, "after": b, "change": kind, "facility": fid} for fid in sorted(ids))
    first, last = rows[0], rows[-1]
    previous_date = (date.fromisoformat(first["period"]) - timedelta(days=1)).isoformat()
    fields = ("period", "capacity", "outage", "percentOutage")
    return {"available": True, "first": {k: first[k] for k in fields},
            "last": {k: last[k] for k in fields}, "records": len(rows),
            "missing_dates": sorted(set(days_between(first["period"], last["period"])) - {r["period"] for r in rows}),
            "full_offline_records": sum(full(r) for r in rows), "longest_full_offline_days": best,
            "longest_run_start": best_start, "longest_run_end": best_end,
            "generator_1_matches": len(units) == len(rows) == len(unit_by_day) and
                all(r["period"] in unit_by_day and all(r[k] == unit_by_day[r["period"]][k]
                    for k in (*METRICS, "percentOutage")) for r in rows),
            "facility_membership_changes": changes,
            "facilities_present_every_day": len(set.intersection(*(by_day[d] for d in days))),
            "entry_capacity_change": capacity_change(sources, previous_date, first["period"])}


def weighted_percentages(sources, period="2026-08-04", facility="566"):
    """Calculate the Millstone example from MW and compare it with the unit mean."""
    plants = [r for r in sources["facility"] if r["period"] == period and r["facility"] == facility]
    units = [r for r in sources["generator"] if r["period"] == period and r["facility"] == facility]
    if not plants or not units:
        return {"available": False, "reason": "example_not_reported"}
    capacity = sum((r["capacity"] for r in units), Decimal(0))
    outage = sum((r["outage"] for r in units), Decimal(0))
    ratio = 100 * outage / capacity if capacity else None
    percentages = [r["percentOutage"] for r in units]
    mean = sum(percentages, Decimal(0)) / len(units) if all(p is not None for p in percentages) else None
    return {"available": True, "period": period, "facility": facility,
            "capacity_mw": capacity, "outage_mw": outage,
            "weighted_percent": ratio,
            "display_percent": ratio.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if ratio is not None else None,
            "ratio_reason": "zero_capacity" if ratio is None else None,
            "simple_mean_percent": mean, "facility_source_percent": plants[0]["percentOutage"],
            "units": [{k: r[k] for k in ("generator", *METRICS, "percentOutage")} for r in units]}


def api_counts(sources, window):
    """Tie saved count and exhaustion probes to their request scope and CSV rows."""
    names = ("facility_one_day", "facility_one_day_after_last", "generator_one_day",
             "facility_browns_ferry", "generator_browns_ferry", "facility_two_years_after_last")
    results = {}
    for name in names:
        saved = sources[name]
        params = dict(saved["parameters"])
        grain = "generator" if name.startswith("generator") else "facility"
        expected_start = window["start"] if "two_years" in name else "2026-10-01"
        expected_end = window["end"] if "two_years" in name else "2026-10-01"
        expected_facets = {"facets[facility][]": "46"} if "browns_ferry" in name else {}
        actual_facets = {k: v for k, v in params.items() if k.startswith("facets[")}
        if (saved["metadata"] or saved["route"] != grain + "-nuclear-outages" or
                params.get("start") != expected_start or params.get("end") != expected_end or
                params.get("frequency") != "daily" or actual_facets != expected_facets or
                saved["response"].get("frequency") != "daily"):
            raise ValueError(f"Unexpected API probe scope: {name}")
        for index, key in enumerate(KEYS[grain]):
            if params.get(f"sort[{index}][column]") != key or params.get(f"sort[{index}][direction]") != "asc":
                raise ValueError(f"Unexpected API probe sort: {name}")
        response = saved["response"]
        data = response["data"]
        csv_rows = [r for r in sources[grain] if expected_start <= r["period"] <= expected_end and
                    (not expected_facets or r["facility"] == "46")]
        offset, length, total = int(params["offset"]), int(params["length"]), int(response["total"])
        if min(offset, total) < 0 or length <= 0:
            raise ValueError(f"Invalid API count: {name}")
        if "after_last" in name:
            tied = not data and offset == len(csv_rows)
        else:
            def comparable(row):
                return (tuple(row[k] for k in KEYS[grain]),
                        tuple(Decimal(row[k]) for k in (*METRICS, "percentOutage")))
            tied = offset == 0 and len(data) <= length and sorted(map(comparable, data)) == sorted(map(comparable, csv_rows))
        results[name] = {"route": saved["route"], "start": expected_start, "end": expected_end,
                         "facility": expected_facets.get("facets[facility][]"),
                         "offset": offset, "requested_length": length, "advertised_total": total,
                         "returned_rows": len(data), "csv_rows_in_scope": len(csv_rows),
                         "agrees_with_saved_csv": tied, "checked_at_utc": saved["checked_at_utc"],
                         "api_version": saved["api_version"]}
    first, tail = results["facility_one_day"], results["facility_one_day_after_last"]
    results["one_day_exhaustion_confirmed"] = (
        first["agrees_with_saved_csv"] and tail["agrees_with_saved_csv"] and
        first["returned_rows"] == tail["offset"] and first["advertised_total"] == tail["advertised_total"])
    return results


def build_report(manifest, sources):
    """Compute observations separately from explicit historical claim checks."""
    window = manifest["window"]
    scope = {g: coverage(sources[g], g, **window) for g in KEYS}
    comparisons = reconcile(sources)
    bad = [r for r in comparisons if r["status"] != "match"]
    step, offline = capacity_change(sources), palisades(sources)
    weighted, counts = weighted_percentages(sources), api_counts(sources, window)
    reused = {r["facility"] for r in sources["generator"] if r["period"] == "2026-09-15" and r["generator"] == "1"}
    checks = {
        "at_least_30_days": len(days_between(**window)) >= 30,
        "daily_coverage_and_keys": all(not s["missing_dates"] and not s["outside_window"] and
                                       s["rows"] == s["unique_keys"] for s in scope.values()),
        "exact_reconciliation": not bad,
        "AN01_capacity_step": step.get("national_difference_mw") == Decimal("2436.2") and
                              step.get("facility_total_difference_mw") == Decimal("2436.2"),
        "AN01_same_55_facilities": step.get("facilities_before") == step.get("facilities_after") == 55 and
                                   step.get("added") == step.get("removed") == [],
        "AN02_first_and_last": offline.get("first", {}).get("period") == "2025-09-09" and
                                offline.get("last", {}).get("period") == "2026-10-02" and
                                offline.get("first", {}).get("capacity") == Decimal("768.5") and
                                offline.get("last", {}).get("capacity") == Decimal("815.6"),
        "AN02_389_full_days": offline.get("records") == offline.get("full_offline_records") ==
                              offline.get("longest_full_offline_days") == 389 and offline.get("missing_dates") == [],
        "AN02_generator_agreement": offline.get("generator_1_matches", False),
        "AN02_only_facility_addition": offline.get("facility_membership_changes") == [
            {"before": "2025-09-08", "after": "2025-09-09", "change": "added", "facility": "1715"}] and
            offline.get("facilities_present_every_day") == 54,
        "AN02_entry_capacity": offline.get("entry_capacity_change", {}).get("national_difference_mw") == Decimal("768.5") and
                               offline.get("entry_capacity_change", {}).get("unchanged") == 54,
        "AN03_probes_match_csv": all(r["agrees_with_saved_csv"] for r in counts.values() if isinstance(r, dict)),
        "AN03_one_day_counts": counts["facility_one_day"]["advertised_total"] == 95 and
                               counts["facility_one_day"]["returned_rows"] == 55 and
                               counts["generator_one_day"]["advertised_total"] == counts["generator_one_day"]["returned_rows"] == 95,
        "AN03_browns_ferry": counts["facility_browns_ferry"]["advertised_total"] == 3 and
                             counts["facility_browns_ferry"]["returned_rows"] == 1 and
                             counts["generator_browns_ferry"]["advertised_total"] == counts["generator_browns_ferry"]["returned_rows"] == 3,
        "AN03_final_empty_probes": counts["one_day_exhaustion_confirmed"] and
                                   counts["facility_two_years_after_last"]["agrees_with_saved_csv"] and
                                   counts["facility_two_years_after_last"]["offset"] == 39863 and
                                   counts["facility_two_years_after_last"]["advertised_total"] == len(sources["generator"]) == 69103,
        "F1_weighted_example": weighted.get("display_percent") == Decimal("40.95") and weighted.get("simple_mean_percent") == 50,
        "F2_generator_1_reused": len(reused) == 47,
    }
    # Entry membership has its own detailed result; keep the main report compact.
    if offline.get("available"):
        offline["entry_capacity_change"].pop("facilities", None)
    report = {"input_manifest": manifest, "scope": scope,
              "reconciliation": {"comparisons": len(comparisons), "nonmatching": len(bad),
                                 "max_absolute_difference_mw": max((abs(r["difference_mw"]) for r in comparisons
                                                                    if r["difference_mw"] is not None), default=None),
                                 "details": "reconciliation.csv"},
              "AN01": step, "AN02": offline, "AN03": counts, "F1": weighted,
              "original_findings_window": {
                  g: coverage([r for r in sources[g] if "2025-01-01" <= r["period"] <= "2026-10-02"],
                              g, "2025-01-01", "2026-10-02") for g in KEYS},
              "F2": {"period": "2026-09-15", "generator": "1", "distinct_facilities": len(reused)},
              "historical_claim_checks": checks, "historical_claims_reproduced": all(checks.values()),
              "evidence_limits": ["Saved observations only; no current EIA query or proof of source completeness.",
                                  "API probes are selected responses, not every original download page.",
                                  "Seasonal cause and EIA internal counting method are not measured here.",
                                  "No S3 protection, live preparation, or application publication is verified."]}
    return report, comparisons


def write_report(output, report, comparisons):
    """Save the measured report and every comparison without overwriting prior runs."""
    output.mkdir(parents=True, exist_ok=False)
    with (output / "reconciliation.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=list(comparisons[0]))
        writer.writeheader()
        writer.writerows(comparisons)
    report["reconciliation"]["sha256"] = hashlib.sha256((output / "reconciliation.csv").read_bytes()).hexdigest()
    (output / "report.json").write_text(json.dumps(report, default=str, indent=2) + "\n")
    lines = ["# Findings reproduction — measured results", "",
             f"Window: {report['input_manifest']['window']['start']} through {report['input_manifest']['window']['end']}.",
             f"Historical claims reproduced: {report['historical_claims_reproduced']}.", "",
             "| Check | Matches historical claim |", "|---|---|"]
    lines += [f"| {name} | {passed} |" for name, passed in report["historical_claim_checks"].items()]
    lines += ["", f"Exact MW comparisons: {len(comparisons)}; nonmatching: {report['reconciliation']['nonmatching']}.",
              "Every date, entity, metric, compared value, and signed difference is in `reconciliation.csv`.",
              "`report.json` contains measured anomaly values, source checksums, and request scopes.", ""]
    step, offline, weighted = report["AN01"], report["AN02"], report["F1"]
    if step["available"]:
        lines += ["## AN-01 — Capacity step", "",
                  f"{step['before']}: {step['national_before_mw']} MW; {step['after']}: {step['national_after_mw']} MW.",
                  f"Difference: {step['national_difference_mw']} MW; summed facility difference: {step['facility_total_difference_mw']} MW.",
                  f"Facilities: {step['facilities_before']} → {step['facilities_after']}; added: {step['added']}; removed: {step['removed']}.",
                  f"Increased: {step['increased']}; decreased: {step['decreased']}; unchanged: {step['unchanged']}.", ""]
    if offline["available"]:
        lines += ["## AN-02 — Palisades", "",
                  f"First observed: {offline['first']['period']}; last: {offline['last']['period']}; records: {offline['records']}.",
                  f"First capacity/outage: {offline['first']['capacity']}/{offline['first']['outage']} MW.",
                  f"Last capacity/outage: {offline['last']['capacity']}/{offline['last']['outage']} MW.",
                  f"Longest exact full-outage run: {offline['longest_full_offline_days']} days, {offline['longest_run_start']} through {offline['longest_run_end']}.",
                  f"Missing dates: {offline['missing_dates']}; generator 1 agrees: {offline['generator_1_matches']}.", ""]
    lines += ["## AN-03 — Saved API probes", "",
              "| Probe | Advertised total | Returned | Offset | Agrees with CSV scope |",
              "|---|---:|---:|---:|---|"]
    lines += [f"| {name} | {r['advertised_total']} | {r['returned_rows']} | {r['offset']} | {r['agrees_with_saved_csv']} |"
              for name, r in report["AN03"].items() if isinstance(r, dict)]
    if weighted["available"]:
        lines += ["", "## Supporting checks", "",
                  f"Millstone: {weighted['outage_mw']} / {weighted['capacity_mw']} × 100 = {weighted['display_percent']}% (display); unit mean: {weighted['simple_mean_percent']}%.",
                  f"Generator 1 occurs at {report['F2']['distinct_facilities']} facilities on {report['F2']['period']}."]
    lines += ["", "## Evidence limits", ""] + ["- " + limit for limit in report["evidence_limits"]]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n")


def main(argv=None):
    """Run offline reproduction; return 0 for reproduced claims, 1 for differences, 2 for invalid input."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=ROOT / "evidence/findings/inputs")
    parser.add_argument("--out", type=Path, required=True, help="New directory for this run")
    args = parser.parse_args(argv)
    try:
        with localcontext() as context:
            context.prec = 60
            manifest, sources = load_inputs(args.inputs)
            report, comparisons = build_report(manifest, sources)
            write_report(args.out, report, comparisons)
    except (OSError, ValueError, KeyError, TypeError, InvalidOperation) as error:
        print(f"Findings report failed: {error}", file=sys.stderr)
        return 2
    passed = report["historical_claims_reproduced"]
    print(f"Historical claims reproduced: {passed}; comparisons: {len(comparisons)}; output: {args.out}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
