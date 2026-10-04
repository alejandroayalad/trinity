"""Exercise saved-file validation with exact, synthetic three-day candidates.

Fixtures intentionally violate one rule at a time. Rebinding altered source
evidence creates a new synthetic test input before validation; production
code never rewrites a frozen identity. All files stay in temporary folders.
"""

import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal, Inexact, Rounded, localcontext
import json
from pathlib import Path
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from test_parquet import START, END, evidence, source_row
from trinity.config import EIASettings
from trinity.connector import validate
from trinity.connector.parquet import freeze_files
from trinity.connector.pipeline import retrieve_all
from trinity.connector.validate import (
    REQUIRED_CHECKS, ValidationError,
    diagnostic_identity, required_checks_pass, validate_candidate, verify_validation,
)
from trinity.contracts.datasets import DATASETS
from trinity.contracts.manifest import canonical_json, read_json, sha256


def reconciled() -> dict[str, list[dict]]:
    """Return full coverage with two facilities and generator ID reuse.

    Each facility has one generator, both named "1". This is valid because
    the generator key includes facility. National totals combine both rows.
    """
    rows = {dataset: [] for dataset in DATASETS}
    for day in ("2026-10-01", "2026-10-02", "2026-10-03"):
        rows["national"].append(source_row("national", period=day, capacity="200", outage="20", percentOutage="10"))
        for facility in ("001a", "002b"):
            for dataset in ("facility", "generator"):
                rows[dataset].append(source_row(dataset, period=day, facility=facility,
                                               generator="1", capacity="100", outage="10", percentOutage="10"))
    return rows


def records_for(rows: dict) -> list:
    """Use real route identities and sorted keys for normal source proof."""
    rows = {dataset: sorted(data, key=lambda row: tuple(row[key] for key in DATASETS[dataset].key_fields))
            for dataset, data in rows.items()}
    return [replace(record, route=validate._ROUTES[record.dataset],
                    attempts=tuple(replace(attempt, api_version=None) for attempt in record.attempts))
            for record in evidence(rows)]


class ValidationTests(unittest.TestCase):
    """Check complete attempts and retain inspectable evidence for failures."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def freeze(self, rows=None):
        return freeze_files(output_root=self.root, start=START, end=END,
                            retrieval=records_for(reconciled() if rows is None else rows))

    def run_candidate(self, rows=None):
        frozen = self.freeze(rows)
        return validate_candidate(frozen.root, frozen.manifest_sha256)

    def result(self, report, code, scope="all"):
        return next(item for item in (*report.results, *report.diagnostics)
                    if (item.check_code, item.dataset_key) == (code, scope))

    def details(self, report, code, scope="all"):
        return read_json(self.result(report, code, scope).details_json)

    def assert_failed(self, report) -> None:
        self.assertEqual(report.status, "failed")
        self.assertIsNone(report.warning_digest)
        self.assertIsNone(report.warning_count)
        self.assertIsNone(report.approval_required)
        self.assertEqual(len(report.results), 16)
        with self.assertRaises(ValidationError):
            verify_validation(report)

    def rebind_source(self, frozen, change):
        """Create a deliberately invalid but byte-bound synthetic source fixture."""
        path = frozen.root / "source-evidence.json"
        body = read_json(path.read_bytes())
        change(body["routes"])
        data = canonical_json(body)
        path.write_bytes(data)
        manifest = replace(frozen.manifest, source_evidence_sha256=sha256(data))
        (frozen.root / "manifest.json").write_bytes(manifest.to_bytes())
        return replace(frozen, manifest=manifest, manifest_sha256=manifest.digest)

    def test_complete_attempt_has_exact_registry_and_durable_bound_files(self) -> None:
        frozen = self.freeze()
        original = {entry.storage_path: (frozen.root / entry.storage_path).read_bytes()
                    for entry in frozen.manifest.entries}
        report = validate_candidate(frozen.root, frozen.manifest_sha256)
        self.assertEqual(report.status, "passed")
        self.assertEqual(len(report.results), 16)
        self.assertEqual(len(report.diagnostics), 23)
        self.assertEqual(set((r.check_code, r.dataset_key) for r in report.results), set(REQUIRED_CHECKS))
        self.assertEqual(report.warning_count, 0)
        self.assertFalse(report.approval_required)
        verify_validation(report)
        for path, expected in original.items():
            self.assertEqual((frozen.root / path).read_bytes(), expected)
        journal = [read_json(line) for line in (frozen.root / report.evidence_path / "journal.jsonl").read_bytes().splitlines()]
        self.assertEqual(journal[0]["event"], "started")
        self.assertEqual(len([event for event in journal if event["event"] == "result"]), 39)
        self.assertEqual(journal[-1]["event"], "completed")

    def test_s09_incomplete_or_unstable_source_proof_blocks(self) -> None:
        for change in ("no_probe", "failed", "skipped", "budget", "unstable", "repeated", "total", "offset", "route"):
            with self.subTest(change=change):
                frozen = self.freeze()

                def alter(records):
                    record = records[0]
                    if change == "no_probe":
                        record["attempts"].pop()
                        record["pages_fetched"] -= 1
                    elif change in ("failed", "skipped", "budget"):
                        record["final_status"] = "skipped" if change == "skipped" else "failed"
                        record["error_code"] = "page_limit" if change == "budget" else "failed"
                    elif change == "offset":
                        record["attempts"][1]["offset"] += 1
                    elif change == "route":
                        record["route"] = "wrong/data/"
                    elif change == "repeated":
                        record["attempts"].insert(1, deepcopy(record["attempts"][0]))
                    else:
                        attempts = record["attempts"][-1:] if change == "unstable" else record["attempts"]
                        for attempt in attempts:
                            body = read_json(attempt["sanitized_response"])
                            body["response"]["total"] = 99
                            attempt["sanitized_response"] = json.dumps(body)
                            attempt["response_sha256"] = sha256(attempt["sanitized_response"].encode())
                            attempt["advertised_total"] = 99

                frozen = self.rebind_source(frozen, alter)
                report = validate_candidate(frozen.root, frozen.manifest_sha256)
                self.assert_failed(report)
                self.assertNotEqual(self.result(report, "V01", "national").status, "pass")

    def test_s09_generator_total_disagreement_blocks(self) -> None:
        frozen = self.freeze()

        def alter(records):
            for attempt in records[2]["attempts"]:
                body = read_json(attempt["sanitized_response"])
                body["response"]["total"] = 99
                # Source response strings may contain unknown numeric fields.
                # Use ordinary JSON here; canonical JSON correctly rejects floats.
                attempt["sanitized_response"] = json.dumps(body)
                attempt["response_sha256"] = sha256(attempt["sanitized_response"].encode())
                attempt["advertised_total"] = 99

        frozen = self.rebind_source(frozen, alter)
        report = validate_candidate(frozen.root, frozen.manifest_sha256)
        self.assert_failed(report)
        self.assertEqual(self.result(report, "V01", "generator").status, "fail")

    def test_s10_facility_total_mismatch_is_info_only(self) -> None:
        # Use the scenario's exact 95-advertised / 55-returned counts.
        # Membership can change; every requested date remains represented.
        rows = {dataset: [] for dataset in DATASETS}
        for day, plants in (("2026-10-01", 18), ("2026-10-02", 18), ("2026-10-03", 19)):
            rows["national"].append(source_row("national", period=day, capacity=str(plants * 100),
                                               outage=str(plants * 10), percentOutage="10"))
            for index in range(plants):
                for dataset in ("facility", "generator"):
                    rows[dataset].append(source_row(dataset, period=day, facility=f"{index:03d}", generator="1",
                                                   capacity="100", outage="10", percentOutage="10"))
        frozen = self.freeze(rows)

        def alter(records):
            for attempt in records[1]["attempts"]:
                body = read_json(attempt["sanitized_response"])
                body["response"]["total"] = 95
                attempt["sanitized_response"] = json.dumps(body)
                attempt["response_sha256"] = sha256(attempt["sanitized_response"].encode())
                attempt["advertised_total"] = 95

        frozen = self.rebind_source(frozen, alter)
        report = validate_candidate(frozen.root, frozen.manifest_sha256)
        self.assertEqual(report.status, "passed")
        self.assertEqual(self.result(report, "D09", "facility").severity, "info")
        self.assertEqual(self.result(report, "D09", "facility").failed_count, 1)
        self.assertEqual(self.details(report, "D09", "facility")["affected"],
                         [{"advertised_total": 95, "row_count": 55}])
        self.assertEqual(report.warning_count, 0)
        self.assertFalse(report.approval_required)
        verify_validation(report)

    def test_s11_identical_duplicate_keys_fail_at_every_grain(self) -> None:
        for dataset in DATASETS:
            with self.subTest(dataset=dataset):
                rows = reconciled()
                rows[dataset].append(deepcopy(rows[dataset][0]))
                report = self.run_candidate(rows)
                self.assert_failed(report)
                self.assertEqual(self.result(report, "V03", dataset).status, "fail")

    def test_s12_every_shared_or_individual_missing_day_fails(self) -> None:
        for missing in (tuple(DATASETS), ("national",), ("facility",), ("generator",), ("facility", "generator")):
            with self.subTest(missing=missing):
                rows = reconciled()
                for dataset in missing:
                    rows[dataset] = [row for row in rows[dataset] if row["period"] != "2026-10-02"]
                report = self.run_candidate(rows)
                self.assert_failed(report)
                self.assertEqual(self.result(report, "V04").status, "fail")
                for dataset in missing:
                    self.assertEqual(self.details(report, "V04")[dataset]["missing_dates"], ["2026-10-02"])

    def test_s12_out_of_window_saved_row_cannot_pass(self) -> None:
        frozen = self.freeze()
        path = frozen.root / "data/national.parquet"
        table = pq.ParquetFile(path).read()
        rows = table.to_pylist()
        rows[0]["period"] = date(2026, 9, 30)
        pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), path)
        report = validate_candidate(frozen.root, frozen.manifest_sha256)
        self.assert_failed(report)
        self.assertEqual(self.result(report, "V08", "national").status, "fail")
        self.assertEqual(self.result(report, "V04").status, "error")
        # The coverage function also rejects extra dates if it receives them.
        tables = {key: [dict(row, period=date.fromisoformat(row["period"])) for row in data]
                  for key, data in reconciled().items()}
        tables["national"][0]["period"] = date(2026, 9, 30)
        self.assertEqual(validate._coverage(tables, frozen.manifest).failed, 1)

    def test_s13_missing_counterpart_groups_fail_in_both_directions(self) -> None:
        for dataset, detail in (("generator", "missing_generator_groups"), ("facility", "missing_facility_rows")):
            rows = reconciled()
            rows[dataset].pop(0)
            report = self.run_candidate(rows)
            self.assert_failed(report)
            self.assertTrue(self.details(report, "V05")[detail])
            comparisons = self.details(report, "V06")["comparisons"]
            missing = [item for item in comparisons if item["expected"] is None or item["observed"] is None]
            self.assertTrue(missing)
            self.assertTrue(all(item["difference"] is None for item in missing))

    def test_s14_membership_addition_passes_without_fabricating_prior_rows(self) -> None:
        rows = reconciled()
        for dataset in ("facility", "generator"):
            rows[dataset] = [row for row in rows[dataset]
                             if not (row["period"] == "2026-10-01" and row["facility"] == "002b")]
        rows["national"][0].update(capacity="100", outage="10")
        report = self.run_candidate(rows)
        self.assertEqual(report.status, "passed")
        self.assertFalse(report.approval_required)
        self.assertEqual(self.result(report, "D07", "facility").failed_count, 1)
        self.assertEqual(self.details(report, "D07", "facility")["affected"][0]["period"], "2026-10-02")
        self.assertEqual(self.result(report, "D08", "facility").failed_count, 0)

    def test_s15_s16_one_millionth_differences_fail_exactly(self) -> None:
        for dataset in ("generator", "facility", "both"):
            for field in ("capacity", "outage"):
                with self.subTest(dataset=dataset, field=field):
                    rows = reconciled()
                    for key in (("facility", "generator") if dataset == "both" else (dataset,)):
                        rows[key][0][field] = "100.000001" if field == "capacity" else "10.000001"
                    report = self.run_candidate(rows)
                    self.assert_failed(report)
                    self.assertEqual(self.result(report, "V06").status, "pass" if dataset == "both" else "fail")
                    comparisons = self.details(report, "V07")["comparisons"]
                    failed = [item for item in comparisons if not item["matches"]]
                    self.assertEqual(len(failed), 2 if dataset == "both" else 1)
                    self.assertTrue(all(item["difference"] == "0.000001" for item in failed))

    def test_s17_large_aggregates_ignore_decimal_context_precision(self) -> None:
        rows = reconciled()
        for dataset in ("facility", "generator"):
            for row in rows[dataset]:
                row.update(capacity="999999999999999999.999999", outage="0", percentOutage="0")
        for row in rows["national"]:
            row.update(capacity="999999999999999999.999999", outage="0", percentOutage="0")
        with localcontext() as context:
            context.prec = 3
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            report = self.run_candidate(rows)
        self.assert_failed(report)
        self.assertEqual(self.result(report, "V06").status, "pass")
        mismatches = [item for item in self.details(report, "V07")["comparisons"] if not item["matches"]]
        self.assertEqual(mismatches[0]["observed"], "1999999999999999999.999998")
        self.assertEqual(mismatches[0]["difference"], "999999999999999999.999999")

    def test_s22_s23_registry_rejects_partial_duplicate_mixed_or_wrong_results(self) -> None:
        report = self.run_candidate()
        def passes(results):
            return required_checks_pass(results, version_id=report.manifest.version_id,
                                        attempt_id=report.attempt_id, manifest_sha256=report.manifest.digest)
        self.assertTrue(passes(report.results))
        for results in ((), report.results[:-1], (*report.results, report.results[0]),
                        (report.results[0], *report.results[:-1])):
            self.assertFalse(passes(results))
        for changes in ({"dataset_key": "all"}, {"checkset_version": "future"},
                        {"attempt_id": "other"}, {"manifest_sha256": "0" * 64},
                        {"version_id": "other"}, {"required": False}, {"status": "error"},
                        {"severity": "warning"}, {"check_revision": 2}, {"check_revision": True},
                        {"checked_count": 0}, {"checked_at": "missing"}, {"dataset_key": []}):
            self.assertFalse(passes((replace(report.results[0], **changes), *report.results[1:])))

    def test_s23_revalidation_uses_new_attempt_and_preserves_old_evidence(self) -> None:
        frozen = self.freeze()
        first = validate_candidate(frozen.root, frozen.manifest_sha256)
        original = (first.root / first.evidence_path / "validation.json").read_bytes()
        second = validate_candidate(frozen.root, frozen.manifest_sha256)
        self.assertNotEqual(first.attempt_id, second.attempt_id)
        self.assertEqual(first.warning_digest, second.warning_digest)
        self.assertEqual((first.root / first.evidence_path / "validation.json").read_bytes(), original)
        verify_validation(first)
        verify_validation(second)
        with self.assertRaises(ValidationError):
            verify_validation(replace(first, diagnostics=second.diagnostics))

    def test_s20_s23_missing_file_records_error_dependencies_and_16_results(self) -> None:
        frozen = self.freeze()
        (frozen.root / "data/generator.parquet").unlink()
        report = validate_candidate(frozen.root, frozen.manifest_sha256)
        self.assert_failed(report)
        self.assertEqual(self.result(report, "V08", "generator").status, "fail")
        self.assertEqual(self.result(report, "V02", "generator").status, "error")
        self.assertEqual(self.result(report, "V06").status, "error")
        self.assertEqual(self.result(report, "V08", "national").status, "pass")

    def test_s25_handoff_guard_rejects_changes_without_replacing_identity(self) -> None:
        report = self.run_candidate()
        manifest = (report.root / "manifest.json").read_bytes()
        (report.root / "data/facility.parquet").write_bytes(b"changed")
        with self.assertRaises(ValidationError):
            verify_validation(report)
        self.assertEqual((report.root / "manifest.json").read_bytes(), manifest)
        self.assertEqual(len(list((report.root / report.evidence_path).glob("recheck-*.json"))), 1)

    def test_source_identifier_order_does_not_impose_python_lexical_order(self) -> None:
        rows = reconciled()
        for dataset in ("facility", "generator"):
            for row in rows[dataset]:
                row["facility"] = "46" if row["facility"] == "001a" else "104"
        records = [replace(record, route=validate._ROUTES[record.dataset],
                           attempts=tuple(replace(attempt, api_version=None) for attempt in record.attempts))
                   for record in evidence(rows)]
        frozen = freeze_files(output_root=self.root, start=START, end=END, retrieval=records)
        self.assertEqual(validate_candidate(frozen.root, frozen.manifest_sha256).status, "passed")

    def test_v02_rechecks_source_frequency_units_and_saved_values(self) -> None:
        for change in ("frequency", "units", "value"):
            frozen = self.freeze()

            def alter(records):
                attempt = records[0]["attempts"][0]
                body = read_json(attempt["sanitized_response"])
                if change == "frequency":
                    body["response"]["frequency"] = "monthly"
                else:
                    body["response"]["data"][0]["capacity-units" if change == "units" else "capacity"] = (
                        "kilowatts" if change == "units" else "201")
                attempt["sanitized_response"] = json.dumps(body)
                attempt["response_sha256"] = sha256(attempt["sanitized_response"].encode())

            frozen = self.rebind_source(frozen, alter)
            report = validate_candidate(frozen.root, frozen.manifest_sha256)
            self.assert_failed(report)
            self.assertNotEqual(self.result(report, "V02", "national").status, "pass")

    def test_s26_signed_and_out_of_range_values_survive_with_warnings(self) -> None:
        for outage, percentage, codes in (("-10", "-10", ("D03", "D05")),
                                          ("110", "110", ("D04", "D05"))):
            rows = reconciled()
            for dataset, data in rows.items():
                for row in data:
                    row.update(outage=str(int(outage) * (2 if dataset == "national" else 1)),
                               percentOutage=percentage)
            report = self.run_candidate(rows)
            self.assertEqual(report.status, "passed")
            self.assertTrue(report.approval_required)
            self.assertEqual(report.warning_count, 6)
            for dataset in DATASETS:
                for code in codes:
                    self.assertEqual(self.result(report, code, dataset).status, "fail")
            verify_validation(report)

    def test_s27_exact_d06_threshold_both_directions(self) -> None:
        for percentage, warns in (("10.005100", False), ("10.005101", True),
                                  ("9.994900", False), ("9.994899", True)):
            with self.subTest(percentage=percentage):
                rows = reconciled()
                for data in rows.values():
                    for row in data:
                        row["percentOutage"] = percentage
                with localcontext() as context:
                    context.prec = 2
                    context.traps[Inexact] = True
                    context.traps[Rounded] = True
                    report = self.run_candidate(rows)
                self.assertEqual(report.status, "passed")
                self.assertEqual(report.warning_count, 3 if warns else 0)
                for dataset in DATASETS:
                    self.assertEqual(self.result(report, "D06", dataset).status, "fail" if warns else "pass")

    def test_s28_missing_percentage_and_zero_capacity_complete_diagnostics(self) -> None:
        for missing in (None, "", " ", "absent", "present"):
            for zero in (False, True):
                with self.subTest(missing=missing, zero=zero):
                    rows = reconciled()
                    for data in rows.values():
                        for row in data:
                            if zero:
                                row.update(capacity="0", outage="0")
                            if missing == "absent":
                                row.pop("percentOutage")
                            elif missing != "present":
                                row["percentOutage"] = missing
                    report = self.run_candidate(rows)
                    self.assertEqual(report.status, "passed")
                    for dataset in DATASETS:
                        details = self.details(report, "D06", dataset)
                        count = len(rows[dataset]) if zero or missing != "present" else 0
                        self.assertEqual(len(details["not_applicable"]), count)
                        self.assertEqual(details["eligible_count"], len(rows[dataset]) - count)
                        for item in details["not_applicable"]:
                            self.assertEqual(set(item["reasons"]),
                                             ({"zero_capacity"} if zero else set()) |
                                             ({"missing_source_percentage"} if missing != "present" else set()))
                        self.assertEqual(self.result(report, "D02", dataset).status,
                                         "pass" if missing == "present" else "fail")

    def test_s29_warning_count_counts_summaries_not_rows(self) -> None:
        rows = reconciled()
        for data in rows.values():
            for row in data:
                row["percentOutage"] = None
        for dataset in ("facility", "generator"):
            for row in rows[dataset]:
                row["facilityName"] = None
        report = self.run_candidate(rows)
        self.assertEqual(report.status, "passed")
        self.assertEqual(report.warning_count, 5)
        self.assertEqual(self.result(report, "D02", "facility").failed_count, 6)
        self.assertEqual(self.result(report, "D01", "generator").failed_count, 6)

    def test_s29_capacity_changes_only_are_info_and_no_gap_is_carried_forward(self) -> None:
        rows = reconciled()
        for dataset, data in rows.items():
            for row in data:
                if row["period"] == "2026-10-02":
                    row.update(capacity="400" if dataset == "national" else "200", percentOutage="5")
        report = self.run_candidate(rows)
        self.assertEqual(report.status, "passed")
        self.assertFalse(report.approval_required)
        self.assertEqual(self.result(report, "D08", "national").failed_count, 2)
        self.assertEqual(self.result(report, "D08", "facility").failed_count, 4)
        # A gap is a required coverage failure, but must not create a capacity
        # comparison from October 1 directly to October 3.
        for data in rows.values():
            data[:] = [row for row in data if row["period"] != "2026-10-02"]
            data[-1]["capacity"] = "300"
        failed = self.run_candidate(rows)
        self.assert_failed(failed)
        self.assertEqual(self.result(failed, "D08", "national").checked_count, 0)

    def test_s30_diagnostic_order_is_stable_but_changed_summary_changes_digest(self) -> None:
        rows = reconciled()
        rows["facility"][0]["facilityName"] = None
        report = self.run_candidate(rows)
        digest, count, _summaries = diagnostic_identity(report.diagnostics)
        self.assertEqual(diagnostic_identity(tuple(reversed(report.diagnostics)))[:2], (digest, count))
        first = report.diagnostics[0]
        changed = (replace(first, details_json=canonical_json({"affected": ["changed"]})), *report.diagnostics[1:])
        self.assertNotEqual(diagnostic_identity(changed)[0], digest)
        for changes in ({"check_code": "D99"}, {"severity": "info"}, {"status": "error"},
                        {"attempt_id": "other"}, {"manifest_sha256": "0" * 64}):
            with self.assertRaises(ValidationError):
                diagnostic_identity((replace(first, **changes), *report.diagnostics[1:]))
        with self.assertRaises(ValidationError):
            diagnostic_identity(report.diagnostics[:-1])

    def test_s36_failed_diagnostic_retains_prior_results_without_frozen_digest(self) -> None:
        original = validate._diagnostic

        def fail_one(code, *args):
            if code == "D06":
                raise RuntimeError("synthetic secret-bearing external error")
            return original(code, *args)

        frozen = self.freeze()
        with patch.object(validate, "_diagnostic", side_effect=fail_one):
            report = validate_candidate(frozen.root, frozen.manifest_sha256)
        self.assert_failed(report)
        self.assertEqual(len(report.diagnostics), 23)
        self.assertEqual(self.result(report, "D06", "national").status, "error")
        data = (report.root / report.evidence_path / "diagnostics.json").read_bytes()
        self.assertFalse(read_json(data)["frozen"])
        self.assertNotIn(b"secret-bearing", data)

    def test_s36_cancel_between_checks_or_during_diagnostics_retains_journal(self) -> None:
        for after in (3, 20):
            frozen = self.freeze()
            polls = 0

            def cancelled():
                nonlocal polls
                polls += 1
                return polls > after

            with self.assertRaises(ValidationError) as caught:
                validate_candidate(frozen.root, frozen.manifest_sha256, cancelled=cancelled)
            self.assertEqual(caught.exception.code, "cancelled")
            folder = frozen.root / "evidence" / caught.exception.attempt_id
            events = [read_json(line) for line in (folder / "journal.jsonl").read_bytes().splitlines()]
            self.assertTrue(any(item["event"] == "result" for item in events))
            self.assertFalse(any(item["event"] == "completed" for item in events))
            self.assertEqual(read_json((folder / "incomplete.json").read_bytes())["status"], "incomplete")
            self.assertFalse((folder / "diagnostics.json").exists())

    def test_s36_keyboard_cancellation_preserves_failed_check_evidence(self) -> None:
        frozen = self.freeze()
        original = validate._required

        def stop_after_failure(code, scope, *args):
            if code == "V01" and scope == "facility":
                return validate._Outcome(1, 1, {"reason": "synthetic_failure"})
            if code == "V02":
                raise KeyboardInterrupt
            return original(code, scope, *args)

        with patch.object(validate, "_required", side_effect=stop_after_failure):
            with self.assertRaises(KeyboardInterrupt):
                validate_candidate(frozen.root, frozen.manifest_sha256)
        folder = next((frozen.root / "evidence").iterdir())
        events = [read_json(line) for line in (folder / "journal.jsonl").read_bytes().splitlines()]
        self.assertTrue(any(item.get("result", {}).get("status") == "fail" for item in events))
        self.assertTrue((folder / "incomplete.json").exists())

    def test_s36_evidence_write_failure_stops_before_success(self) -> None:
        frozen = self.freeze()
        original = validate.parquet._write_bytes

        def fail_write(root, path, data):
            if path.endswith("V02-national.json"):
                raise OSError("synthetic disk error")
            return original(root, path, data)

        with patch.object(validate.parquet, "_write_bytes", side_effect=fail_write):
            with self.assertRaises(ValidationError) as caught:
                validate_candidate(frozen.root, frozen.manifest_sha256)
        folder = frozen.root / "evidence" / caught.exception.attempt_id
        self.assertTrue((folder / "V01-generator.json").exists())
        self.assertFalse((folder / "validation.json").exists())
        self.assertTrue((folder / "incomplete.json").exists())

    def test_summary_or_detail_tampering_and_missing_completion_fail_handoff(self) -> None:
        for name in ("validation.json", "diagnostics.json", "V01-national.json", "journal.jsonl"):
            report = self.run_candidate()
            (report.root / report.evidence_path / name).write_bytes(b"{}")
            with self.assertRaises(ValidationError):
                verify_validation(report)

    def test_journal_cannot_lose_result_rows_while_retaining_completion(self) -> None:
        report = self.run_candidate()
        path = report.root / report.evidence_path / "journal.jsonl"
        lines = path.read_bytes().splitlines()
        path.write_bytes(b"\n".join((lines[0], *lines[2:])) + b"\n")
        with self.assertRaises(ValidationError):
            verify_validation(report)

    def test_s36_silent_summary_corruption_is_not_success(self) -> None:
        frozen = self.freeze()
        original = validate.parquet._write_bytes

        def corrupt(root, path, data):
            return original(root, path, b"{}" if path.endswith("diagnostics.json") else data)

        with patch.object(validate.parquet, "_write_bytes", side_effect=corrupt):
            with self.assertRaises(ValidationError) as caught:
                validate_candidate(frozen.root, frozen.manifest_sha256)
        folder = frozen.root / "evidence" / caught.exception.attempt_id
        self.assertTrue((folder / "incomplete.json").exists())
        self.assertNotIn(b'"event":"completed"', (folder / "journal.jsonl").read_bytes())

    def test_s36_journal_sync_failure_retains_prior_check_evidence(self) -> None:
        frozen = self.freeze()
        original = validate._Journal.append

        def stop(journal, event):
            if event["event"] == "result" and event["result"]["check_code"] == "V02":
                # Fail the actual fsync after the JSONL write. Earlier result
                # syncs already completed; no later check can report success.
                with patch.object(validate.os, "fsync", side_effect=OSError("synthetic sync failure")):
                    return original(journal, event)
            return original(journal, event)

        with patch.object(validate._Journal, "append", new=stop):
            with self.assertRaises(ValidationError) as caught:
                validate_candidate(frozen.root, frozen.manifest_sha256)
        folder = frozen.root / "evidence" / caught.exception.attempt_id
        self.assertTrue((folder / "V01-generator.json").exists())
        self.assertTrue((folder / "incomplete.json").exists())
        self.assertFalse((folder / "validation.json").exists())

    def test_s36_hard_termination_leaves_synced_journal_without_completion(self) -> None:
        frozen = self.freeze()
        # Kill only this synthetic test child after it syncs the first result.
        # SIGKILL prevents cleanup handlers from fabricating a final summary.
        code = '''
import os, signal, sys
from pathlib import Path
from trinity.connector import validate
original = validate._Journal.append
def stop(self, event):
    original(self, event)
    if event['event'] == 'result':
        os.kill(os.getpid(), signal.SIGKILL)
validate._Journal.append = stop
validate.validate_candidate(Path(sys.argv[1]), sys.argv[2])
'''
        completed = subprocess.run([sys.executable, "-c", code, str(frozen.root), frozen.manifest_sha256],
                                   capture_output=True, timeout=15)
        self.assertEqual(completed.returncode, -signal.SIGKILL)
        folder = next((frozen.root / "evidence").iterdir())
        events = [read_json(line) for line in (folder / "journal.jsonl").read_bytes().splitlines()]
        self.assertEqual([event["event"] for event in events], ["started", "result"])
        self.assertFalse((folder / "validation.json").exists())
        self.assertFalse((folder / "diagnostics.json").exists())

    def test_file_change_during_validation_fails_without_new_manifest(self) -> None:
        frozen = self.freeze()
        original = validate._diagnostic
        changed = False

        def change_file(*args):
            nonlocal changed
            if not changed:
                (frozen.root / "data/national.parquet").write_bytes(b"changed")
                changed = True
            return original(*args)

        with patch.object(validate, "_diagnostic", side_effect=change_file):
            report = validate_candidate(frozen.root, frozen.manifest_sha256)
        self.assert_failed(report)
        self.assertEqual(report.manifest.digest, frozen.manifest_sha256)

    def test_existing_connector_retries_feed_successful_validation_offline(self) -> None:
        rows = reconciled()
        called = set()

        def reply(request):
            dataset = next(key for key, route in validate._ROUTES.items()
                           if str(request.url.copy_with(query=None)) == route)
            if dataset not in called:
                called.add(dataset)
                return httpx.Response(503, json={"error": "synthetic temporary failure"})
            data = [] if int(request.url.params["offset"]) else rows[dataset]
            return httpx.Response(200, json={"response": {"frequency": "daily", "data": data,
                                                          "total": str(len(rows[dataset]))}})

        async def run():
            with patch("trinity.connector.client.sleep"):
                return await retrieve_all(start=START, end=END, transport=httpx.MockTransport(reply),
                                          settings=EIASettings(EIA_API_KEY="synthetic-key"))

        results = asyncio.run(run())
        frozen = freeze_files(output_root=self.root, start=START, end=END,
                              retrieval=[item.metadata for item in results])
        report = validate_candidate(frozen.root, frozen.manifest_sha256)
        self.assertEqual(report.status, "passed", [item.to_dict() for item in report.results if item.status != "pass"])
        verify_validation(report)


if __name__ == "__main__":
    unittest.main()
