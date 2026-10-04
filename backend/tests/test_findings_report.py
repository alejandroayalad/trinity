"""Synthetic checks for the offline findings command; these are not EIA evidence."""

from copy import deepcopy
import csv
from decimal import Decimal
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/generate_report.py"
SPEC = importlib.util.spec_from_file_location("findings_report", SCRIPT)
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


def row(period="2026-10-01", facility="46", generator="1", capacity="100", outage="0", percent="0"):
    return {"period": period, "facility": facility, "generator": generator,
            "facilityName": "Synthetic plant", "capacity": Decimal(capacity),
            "outage": Decimal(outage), "percentOutage": Decimal(percent) if percent is not None else None}


def simple_sources():
    return {"us": [row()], "facility": [row()], "generator": [row()]}


def probe_sources():
    sources = simple_sources()
    specs = {
        "facility_one_day": ("facility", 0, False),
        "facility_one_day_after_last": ("facility", 1, False),
        "generator_one_day": ("generator", 0, False),
        "facility_browns_ferry": ("facility", 0, True),
        "generator_browns_ferry": ("generator", 0, True),
        "facility_two_years_after_last": ("facility", 1, False),
    }
    for name, (grain, offset, filtered) in specs.items():
        params = [["frequency", "daily"], ["start", "2026-10-01"], ["end", "2026-10-01"],
                  ["offset", offset], ["length", 5000]]
        for i, key in enumerate(report.KEYS[grain]):
            params += [[f"sort[{i}][column]", key], [f"sort[{i}][direction]", "asc"]]
        if filtered:
            params.append(["facets[facility][]", "46"])
        sources[name] = {"metadata": False, "route": grain + "-nuclear-outages", "parameters": params,
                         "response": {"total": "3", "frequency": "daily", "data": [] if offset else [row()]},
                         "checked_at_utc": "synthetic", "api_version": "synthetic"}
    return sources


class FindingsReportTests(unittest.TestCase):
    def test_exact_decimal_reconciliation_and_tiny_mismatch(self):
        sources = simple_sources()
        sources["generator"] = [row(capacity="0.1", outage="0.000001"), row(generator="2", capacity="0.2")]
        sources["us"] = sources["facility"] = [row(capacity="0.3", outage="0.000001")]
        self.assertTrue(all(c["status"] == "match" for c in report.reconcile(sources)))
        sources["generator"][0]["outage"] = Decimal(0)
        bad = [c for c in report.reconcile(sources) if c["status"] == "mismatch"]
        self.assertEqual(len(bad), 2)
        self.assertTrue(all(c["difference_mw"] == Decimal("-0.000001") for c in bad))
        self.assertEqual(bad[0]["facility"], "46")

    def test_facility_mismatch_is_visible_when_national_totals_match(self):
        sources = simple_sources()
        sources["facility"] = [row(capacity="40"), row(facility="99", capacity="60")]
        sources["generator"] = [row(capacity="60"), row(facility="99", capacity="40")]
        bad = [c for c in report.reconcile(sources) if c["status"] != "match"]
        self.assertEqual({(c["facility"], c["difference_mw"]) for c in bad},
                         {("46", Decimal(20)), ("99", Decimal(-20))})

    def test_missing_zero_group_is_not_a_match(self):
        sources = simple_sources()
        sources["us"] = sources["facility"] = [row(capacity="0")]
        sources["generator"] = []
        missing = [c for c in report.reconcile(sources) if c["status"] == "missing"]
        self.assertEqual(len(missing), 4)
        self.assertTrue(all(c["difference_mw"] is None and c["left_mw"] is None for c in missing))

    def test_capacity_change_keeps_added_and_removed_observations_missing(self):
        sources = simple_sources()
        sources["us"] = [row(period="2026-09-30"), row(capacity="120")]
        sources["facility"] = [row(period="2026-09-30", facility="001"), row(facility="002", capacity="120")]
        result = report.capacity_change(sources)
        self.assertEqual(result["added"], ["002"])
        self.assertEqual(result["removed"], ["001"])
        self.assertEqual(result["national_difference_mw"], Decimal(20))
        self.assertTrue(all(r["difference_mw"] is None for r in result["facilities"]))

    def test_missing_anomaly_dates_are_unavailable(self):
        sources = simple_sources()
        self.assertFalse(report.capacity_change(sources)["available"])
        self.assertFalse(report.palisades(sources)["available"])
        self.assertFalse(report.weighted_percentages(sources)["available"])

    def test_palisades_gap_and_nearly_full_day_break_runs(self):
        sources = simple_sources()
        sources["facility"] = [row(period=f"2026-10-{d:02}", facility="1715", outage="100", percent="100")
                               for d in (1, 2, 4, 5, 6)]
        sources["generator"] = deepcopy(sources["facility"])
        result = report.palisades(sources)
        self.assertEqual(result["missing_dates"], ["2026-10-03"])
        self.assertEqual(result["longest_full_offline_days"], 3)
        self.assertTrue(result["generator_1_matches"])
        sources["facility"][3]["outage"] = Decimal("99.9")
        sources["facility"][3]["percentOutage"] = Decimal("99.9")
        result = report.palisades(sources)
        self.assertEqual(result["longest_full_offline_days"], 2)
        self.assertEqual(result["full_offline_records"], 4)
        self.assertFalse(result["generator_1_matches"])

    def test_zero_capacity_is_not_full_outage(self):
        sources = simple_sources()
        sources["facility"] = sources["generator"] = [row(facility="1715", capacity="0", percent="100")]
        self.assertEqual(report.palisades(sources)["full_offline_records"], 0)
        self.assertEqual(report.palisades(sources)["longest_full_offline_days"], 0)

    def test_weighted_percentage_uses_mw_and_half_up(self):
        sources = simple_sources()
        sources["generator"] = [row(capacity="1", outage="1", percent="100"), row(generator="A", capacity="3")]
        result = report.weighted_percentages(sources, "2026-10-01", "46")
        self.assertEqual(result["simple_mean_percent"], Decimal(50))
        self.assertEqual(result["display_percent"], Decimal("25.00"))
        sources["generator"] = [row(capacity="20000", outage="2469", percent=None)]
        result = report.weighted_percentages(sources, "2026-10-01", "46")
        self.assertEqual(result["display_percent"], Decimal("12.35"))
        self.assertIsNone(result["simple_mean_percent"])

    def test_weighted_zero_capacity_is_unknown(self):
        sources = simple_sources()
        sources["generator"] = [row(capacity="0")]
        result = report.weighted_percentages(sources, "2026-10-01", "46")
        self.assertIsNone(result["display_percent"])
        self.assertEqual(result["ratio_reason"], "zero_capacity")

    def test_api_tail_must_be_empty_at_actual_csv_end(self):
        sources = probe_sources()
        window = {"start": "2026-10-01", "end": "2026-10-01"}
        self.assertTrue(report.api_counts(sources, window)["one_day_exhaustion_confirmed"])
        sources["facility_one_day_after_last"]["response"]["data"] = [row()]
        self.assertFalse(report.api_counts(sources, window)["one_day_exhaustion_confirmed"])
        sources = probe_sources()
        sources["facility_one_day_after_last"]["parameters"][3][1] = 3
        self.assertFalse(report.api_counts(sources, window)["one_day_exhaustion_confirmed"])

    def test_api_total_change_or_row_difference_cannot_confirm_exhaustion(self):
        window = {"start": "2026-10-01", "end": "2026-10-01"}
        for change in ("total", "row"):
            with self.subTest(change=change):
                sources = probe_sources()
                if change == "total":
                    sources["facility_one_day_after_last"]["response"]["total"] = "4"
                else:
                    sources["facility_one_day"]["response"]["data"][0]["outage"] = Decimal(1)
                self.assertFalse(report.api_counts(sources, window)["one_day_exhaustion_confirmed"])

    def test_api_probe_scope_cannot_be_substituted(self):
        window = {"start": "2026-10-01", "end": "2026-10-01"}
        for field, value in (("start", "2026-09-30"), ("facets[facility][]", "999"),
                             ("sort[1][column]", "generator")):
            sources = probe_sources()
            sources["facility_one_day_after_last"]["parameters"].append([field, value])
            with self.subTest(field=field), self.assertRaises(ValueError):
                report.api_counts(sources, window)

    def test_csv_rejects_duplicates_missing_and_nonfinite_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.csv"
            for values in (("2026-10-01,1,0,0\n" * 2), "2026-10-01,NaN,0,0\n",
                           "2026-10-01,,0,0\n", "2026-10-01,1,Infinity,0\n",
                           "2026-10-01,1,0.0000001,0\n"):
                path.write_text("period,capacity,outage,percentOutage\n" + values)
                with self.subTest(values=values), self.assertRaises((ValueError, report.InvalidOperation)):
                    report.read_csv(path, "us")

    def test_daily_keys_preserve_string_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.csv"
            with path.open("w", newline="") as target:
                writer = csv.DictWriter(target, fieldnames=list(row()))
                writer.writeheader()
                writer.writerows([row(facility="001", generator="A"), row(facility="1", generator="A")])
            rows = report.read_csv(path, "generator")
            self.assertEqual({r["facility"] for r in rows}, {"001", "1"})

    def test_coverage_reports_absent_and_outside_dates(self):
        result = report.coverage([row(period="2026-10-01"), row(period="2026-10-04")],
                                 "us", "2026-10-01", "2026-10-03")
        self.assertEqual(result["missing_dates"], ["2026-10-02", "2026-10-03"])
        self.assertEqual(result["outside_window"], ["2026-10-04"])

    def test_checksum_failure_exits_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            content = b"original"
            (directory / "data.csv").write_bytes(b"modified")
            manifest = {"format_version": 1, "files": [{"role": "us", "file": "data.csv", "bytes": len(content),
                                                        "sha256": hashlib.sha256(content).hexdigest()}]}
            (directory / "manifest.json").write_text(json.dumps(manifest))
            output = directory / "output"
            with redirect_stderr(io.StringIO()):
                self.assertEqual(report.main(["--inputs", str(directory), "--out", str(output)]), 2)
            self.assertFalse(output.exists())

    def test_existing_report_directory_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "REPORT.md").write_text("previous evidence")
            with self.assertRaises(FileExistsError):
                report.write_report(directory, {}, [])
            self.assertEqual((directory / "REPORT.md").read_text(), "previous evidence")


if __name__ == "__main__":
    unittest.main()
