"""Exercise local saved-file identities with synthetic, offline source evidence.

These tests cover the file-freeze stage. Duplicate rows deliberately survive
this stage; later validation must reject them. No EIA or S3 connection runs.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal, Inexact, Rounded, localcontext
import json
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from trinity.config import EIASettings
from trinity.connector.parquet import FreezeError, freeze_files, inspect_frozen_files
from trinity.connector.pipeline import retrieve_all
from trinity.connector.retrieval import RetrievalAttempt, RetrievalMetadata
from trinity.contracts.datasets import DATASETS
from trinity.contracts.manifest import (
    ManifestError, canonical_json, read_manifest, schema_fingerprint, sha256,
)


START = date(2026, 10, 1)
END = date(2026, 10, 3)
STAMP = datetime(2026, 10, 3, tzinfo=UTC)


def source_row(dataset: str, **changes) -> dict:
    """Make a fresh source row with lexical details that must survive storage."""
    row = {
        "period": START.isoformat(), "capacity": "863.4000000",
        "outage": "0.000001", "percentOutage": "0.0000000",
        "capacity-units": "megawatts", "outage-units": "megawatts",
        "percentOutage-units": "percent", "unknown": {"label": "café", "number": 1.25},
    }
    if dataset != "national":
        row.update(facility="001a", facilityName=" Synthetic plant ")
    if dataset == "generator":
        row["generator"] = "01B"
    row.update(changes)
    return row


def evidence(rows: dict[str, list[dict]] | None = None) -> list[RetrievalMetadata]:
    """Make retained responses, including the final empty exhaustion probe.

    Build this fixture without the EIA client's early checks. Tests can then
    supply invalid numeric text directly to the file-freeze parser boundary.
    """
    if rows is None:
        rows = {key: [source_row(key)] for key in DATASETS}
    records = []
    for dataset, data in rows.items():
        attempts = []
        for offset, page in ((0, data), (len(data), [])):
            body = json.dumps({"response": {"data": page, "frequency": "daily",
                                           "total": len(data)}})
            attempts.append(RetrievalAttempt(
                offset=offset, requested_length=5000, attempt_number=1,
                started_at=STAMP, completed_at=STAMP, http_status=200,
                api_status="no_error_reported", api_version="2.1.12",
                advertised_total=len(data), actual_row_count=len(page), error_code=None,
                sanitized_response=body, response_sha256=sha256(body.encode()),
            ))
        records.append(RetrievalMetadata(
            dataset=dataset, route=f"synthetic/{dataset}/data/",
            started_at=STAMP, completed_at=STAMP, pages_fetched=2,
            records_fetched=len(data), retries=0, final_status="success",
            error_message=None, error_code=None, requested_start=START,
            requested_end=END, frequency="daily", sort_fields=DATASETS[dataset].key_fields,
            attempts=tuple(attempts),
        ))
    return records


class FileFixture(unittest.TestCase):
    """Give each test an isolated, trusted output directory."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        # macOS /var is a system symlink. Supply its resolved trusted directory
        # so the tested API can reject symlink components without an exception.
        self.root = Path(self.temporary.name).resolve()

    def freeze(self, records=None, **kwargs):
        return freeze_files(output_root=self.root, start=START, end=END,
                            retrieval=evidence() if records is None else records, **kwargs)


class FreezeFilesTests(FileFixture):
    """Check real temporary Parquet writes, evidence and no-overwrite behavior."""

    def test_live_leading_decimal_percentage_survives_saved_parquet(self) -> None:
        rows = {key: [source_row(key)] for key in DATASETS}
        rows["facility"] = [source_row(
            "facility", period="2026-10-02", facility="869", capacity="1881.2",
            outage="9.412", percentOutage=".5",
        )]
        result = self.freeze(evidence(rows))
        saved = pq.read_table(result.root / "data/facility.parquet").to_pylist()
        self.assertEqual(saved[0]["percentOutage"], Decimal("0.500000"))
        source = json.loads((result.root / "source-evidence.json").read_text())
        facility = next(item for item in source["routes"] if item["dataset"] == "facility")
        original = json.loads(facility["attempts"][0]["sanitized_response"])
        self.assertEqual(original["response"]["data"][0]["percentOutage"], ".5")

    def test_s01_all_schemas_survive_all_null_optional_columns(self) -> None:
        rows = {key: [source_row(key, facilityName=None, percentOutage=None)]
                for key in DATASETS}
        result = self.freeze(evidence(rows))
        for key, definition in DATASETS.items():
            with self.subTest(dataset=key):
                saved = pq.ParquetFile(result.root / f"data/{key}.parquet").read()
                self.assertTrue(saved.schema.equals(definition.schema, check_metadata=True))
                self.assertEqual(saved["percentOutage"].null_count, 1)
                if key != "national":
                    self.assertEqual(saved["facilityName"].null_count, 1)
                self.assertEqual(saved.schema.field("period").type, pa.date32())
                self.assertEqual(saved.schema.field("capacity").type, pa.decimal128(24, 6))
        self.assertEqual(inspect_frozen_files(result.root, result.manifest_sha256), result.manifest)

    def test_s02_s05_exact_numbers_ids_and_original_spelling(self) -> None:
        values = ["999999999999999999.999999", "0.000001", "863.4000000", "0"]
        rows = {key: [source_row(key, capacity=value,
                                outage="-999999999999999999.999999",
                                facility=" 01 ") for value in values] for key in DATASETS}
        records = evidence(rows)
        original = deepcopy(records)
        # A low ambient precision must not round conversion or comparison.
        # Enable traps so accidental Decimal arithmetic fails visibly.
        with localcontext() as context:
            context.prec = 3
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            result = self.freeze(records)
        for key in DATASETS:
            saved = pq.ParquetFile(result.root / f"data/{key}.parquet").read().to_pylist()
            self.assertEqual([row["capacity"] for row in saved], list(map(Decimal, values)))
            self.assertTrue(all(row["outage"] == Decimal("-999999999999999999.999999")
                                for row in saved))
            if key != "national":
                self.assertEqual(saved[0]["facility"], " 01 ")
                self.assertEqual(saved[0]["facilityName"], " Synthetic plant ")
            if key == "generator":
                self.assertEqual(saved[0]["generator"], "01B")
            self.assertNotIn("unknown", saved[0])
        saved_evidence = (result.root / "source-evidence.json").read_bytes()
        self.assertEqual(sha256(saved_evidence), result.manifest.source_evidence_sha256)
        self.assertEqual(json.loads(saved_evidence)["routes"], [r.to_dict() for r in original])
        self.assertEqual(records, original)

    def test_sort_preserves_identical_and_conflicting_duplicate_keys(self) -> None:
        rows = {}
        for key in DATASETS:
            early = source_row(key)
            late = source_row(key, period=END.isoformat())
            rows[key] = [late, early, deepcopy(early), source_row(key, outage="2")]
        result = self.freeze(evidence(rows))
        for key in DATASETS:
            saved = pq.ParquetFile(result.root / f"data/{key}.parquet").read().to_pylist()
            self.assertEqual(len(saved), 4)
            self.assertEqual([row["period"] for row in saved], [START, START, START, END])
            self.assertEqual(saved[0], saved[1])
            self.assertEqual(saved[2]["outage"], Decimal("2"))

    def test_s24_parse_failure_keeps_source_without_manifest(self) -> None:
        # National may already be saved when facility parsing fails. Those
        # files must not acquire a manifest or a fabricated validation result.
        for value in ("863.4000001", "1000000000000000000", "NaN", 1.25, True):
            with self.subTest(value=value):
                rows = {key: [source_row(key)] for key in DATASETS}
                rows["facility"][0]["capacity"] = value
                records = evidence(rows)
                before = deepcopy(records)
                version = str(uuid4())
                with self.assertRaises(FreezeError):
                    self.freeze(records, version_id=version)
                folder = self.root / version
                failure = json.loads((folder / "failure.json").read_bytes())
                self.assertEqual(failure["stage"], "parquet")
                self.assertEqual(failure["status"], "failed")
                self.assertNotIn("manifest_sha256", failure)
                self.assertFalse((folder / "manifest.json").exists())
                self.assertFalse((folder / "validation.json").exists())
                self.assertEqual(json.loads((folder / "source-evidence.json").read_bytes())["routes"],
                                 [record.to_dict() for record in before])
                self.assertEqual(records, before)

    def test_s19_existing_version_is_never_repaired(self) -> None:
        result = self.freeze()
        before = {str(p.relative_to(result.root)): p.read_bytes()
                  for p in result.root.rglob("*") if p.is_file()}
        with self.assertRaises(FreezeError) as caught:
            self.freeze(version_id=result.manifest.version_id)
        self.assertEqual(caught.exception.code, "version_collision")
        after = {str(p.relative_to(result.root)): p.read_bytes()
                 for p in result.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_s19_incomplete_version_cannot_be_reused(self) -> None:
        version = str(uuid4())
        folder = self.root / version
        folder.mkdir()
        (folder / "partial").write_bytes(b"retained evidence")
        with self.assertRaises(FreezeError) as caught:
            self.freeze(version_id=version)
        self.assertEqual(caught.exception.code, "version_collision")
        self.assertEqual(list(folder.iterdir()), [folder / "partial"])
        self.assertEqual((folder / "partial").read_bytes(), b"retained evidence")

    def test_s19_concurrent_reservations_have_one_winner(self) -> None:
        version = str(uuid4())

        def attempt():
            try:
                return self.freeze(version_id=version)
            except FreezeError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: attempt(), range(2)))
        self.assertEqual(results.count("version_collision"), 1)
        winner = next(result for result in results if result != "version_collision")
        inspect_frozen_files(winner.root, winner.manifest_sha256)
        self.assertEqual(stat.S_IMODE(winner.root.stat().st_mode), 0o700)
        for path in winner.root.rglob("*"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700 if path.is_dir() else 0o600)

    def test_s20_changed_missing_truncated_or_extra_files_fail(self) -> None:
        for change in ("alter", "truncate", "remove", "extra", "root_extra", "evidence_extra"):
            with self.subTest(change=change):
                result = self.freeze()
                path = result.root / "data/national.parquet"
                original_manifest = (result.root / "manifest.json").read_bytes()
                if change == "alter":
                    path.write_bytes(path.read_bytes() + b"changed")
                elif change == "truncate":
                    path.write_bytes(path.read_bytes()[:32])
                elif change == "remove":
                    path.unlink()
                else:
                    name = {"extra": "data/extra.parquet", "root_extra": "extra.parquet",
                            "evidence_extra": "evidence/extra.parquet"}[change]
                    (result.root / name).write_bytes(b"unexpected")
                with self.assertRaises(FreezeError):
                    inspect_frozen_files(result.root, result.manifest_sha256)
                self.assertEqual((result.root / "manifest.json").read_bytes(), original_manifest)

    def test_s20_replaced_schema_count_or_bounds_fail(self) -> None:
        for change in ("schema", "count", "bounds", "value"):
            with self.subTest(change=change):
                result = self.freeze()
                path = result.root / "data/national.parquet"
                table = pq.ParquetFile(path).read()
                if change == "schema":
                    table = table.drop(["percentOutage"])
                elif change == "count":
                    table = pa.concat_tables([table, table])
                else:
                    rows = table.to_pylist()
                    rows[0]["period" if change == "bounds" else "capacity"] = (
                        END if change == "bounds" else Decimal("2"))
                    table = pa.Table.from_pylist(rows, schema=table.schema)
                pq.write_table(table, path)
                with self.assertRaises(FreezeError):
                    inspect_frozen_files(result.root, result.manifest_sha256)

    def test_s20_false_manifest_measurements_fail_even_with_new_digest(self) -> None:
        # A valid-looking manifest cannot substitute writer claims for saved
        # measurements, even when a caller gives its newly calculated digest.
        changes = {"row_count": 2, "min_period": END, "schema_fingerprint": "0" * 64,
                   "sha256": "0" * 64, "byte_size": 1}
        for field, value in changes.items():
            with self.subTest(field=field):
                result = self.freeze()
                entries = list(result.manifest.entries)
                update = {field: value}
                if field == "min_period":
                    update["max_period"] = END
                entries[0] = replace(entries[0], **update)
                altered = replace(result.manifest, entries=tuple(entries))
                (result.root / "manifest.json").write_bytes(altered.to_bytes())
                with self.assertRaises(FreezeError):
                    inspect_frozen_files(result.root, altered.digest)

    def test_s21_symlink_files_directories_and_output_root_are_rejected(self) -> None:
        target = self.root / "outside"
        target.mkdir()
        sentinel = target / "sentinel"
        sentinel.write_bytes(b"unchanged")
        for location in ("data/national.parquet", "data", "manifest.json", "evidence/link"):
            with self.subTest(location=location):
                result = self.freeze()
                path = result.root / location
                if path.is_dir():
                    path.rename(result.root / "saved-data")
                elif path.exists():
                    path.unlink()
                path.symlink_to(target if location == "data" else sentinel)
                with self.assertRaises(FreezeError):
                    inspect_frozen_files(result.root, result.manifest_sha256)
        link = self.root / "output-link"
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaises(FreezeError):
            freeze_files(output_root=link, start=START, end=END, retrieval=evidence())
        self.assertEqual(list(target.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b"unchanged")

    def test_evidence_changes_and_response_checksum_mismatch_fail(self) -> None:
        result = self.freeze()
        (result.root / "source-evidence.json").write_bytes(b"{}")
        with self.assertRaises(FreezeError):
            inspect_frozen_files(result.root, result.manifest_sha256)
        records = evidence()
        attempts = list(records[0].attempts)
        attempts[0] = replace(attempts[0], response_sha256="0" * 64)
        records[0] = replace(records[0], attempts=tuple(attempts))
        version = str(uuid4())
        with self.assertRaises(FreezeError):
            self.freeze(records, version_id=version)
        self.assertTrue((self.root / version / "source-evidence.json").exists())
        self.assertFalse((self.root / version / "manifest.json").exists())

    def test_source_routes_must_match_the_supplied_window_and_dataset_set(self) -> None:
        records = evidence()
        cases = (records[:-1], [*records, records[0]],
                 [replace(records[0], requested_end=START), *records[1:]],
                 [replace(records[0], final_status="failed"), *records[1:]])
        for changed in cases:
            version = str(uuid4())
            with self.assertRaises(FreezeError):
                self.freeze(changed, version_id=version)
            self.assertTrue((self.root / version / "source-evidence.json").exists())
            self.assertFalse((self.root / version / "manifest.json").exists())

    def test_empty_dataset_and_out_of_window_bounds_do_not_freeze(self) -> None:
        for national in ([], [source_row("national", period="2026-09-30")]):
            records = evidence({"national": national,
                                "facility": [source_row("facility")],
                                "generator": [source_row("generator")]})
            version = str(uuid4())
            with self.assertRaises(FreezeError):
                self.freeze(records, version_id=version)
            self.assertFalse((self.root / version / "manifest.json").exists())

    def test_registered_sidecars_and_journals_are_not_data(self) -> None:
        result = self.freeze()
        (result.root / "validation.json").write_text("{}")
        (result.root / "evidence/attempt.jsonl").write_text("{}\n")
        inspect_frozen_files(result.root, result.manifest_sha256)

    def test_partial_write_retains_failure_but_no_manifest(self) -> None:
        def interrupted_write(_table, stream, **_options):
            stream.write(b"partial")
            raise OSError("synthetic external error must not escape")

        version = str(uuid4())
        with patch("trinity.connector.parquet.pq.write_table", side_effect=interrupted_write):
            with self.assertRaises(FreezeError) as caught:
                self.freeze(version_id=version)
        self.assertNotIn("external error", str(caught.exception))
        self.assertTrue((self.root / version / "failure.json").exists())
        self.assertFalse((self.root / version / "manifest.json").exists())

    def test_failed_evidence_sync_cannot_return_success(self) -> None:
        from trinity.connector import parquet

        original_sync = parquet.os.fsync
        version = str(uuid4())

        def fail_file_sync(descriptor):
            # Directory sync works. The first evidence-file sync fails, as
            # does the attempted failure-record sync. Neither grants success.
            if stat.S_ISREG(parquet.os.fstat(descriptor).st_mode):
                raise OSError("synthetic disk failure")
            original_sync(descriptor)

        with patch("trinity.connector.parquet.os.fsync", side_effect=fail_file_sync):
            with self.assertRaises(FreezeError):
                self.freeze(version_id=version)
        self.assertFalse((self.root / version / "manifest.json").exists())

    def test_row_group_limit_and_writer_settings_on_real_file(self) -> None:
        # Cross the proposed 50,000-row boundary by one row. Repeated keys
        # are intentional: this test checks storage, not duplicate validation.
        rows = {key: [source_row(key)] for key in DATASETS}
        rows["national"] *= 50_001
        result = self.freeze(evidence(rows))
        file = pq.ParquetFile(result.root / "data/national.parquet")
        self.assertEqual(file.metadata.format_version, "2.6")
        self.assertEqual(file.metadata.num_row_groups, 2)
        self.assertEqual([file.metadata.row_group(i).num_rows for i in range(2)], [50_000, 1])
        self.assertEqual(file.metadata.row_group(0).column(0).compression, "SNAPPY")
        self.assertIn(b"ARROW:schema", file.metadata.metadata)

    def test_existing_connector_evidence_freezes_without_live_calls(self) -> None:
        # Exercise the actual extraction result shape. This synthetic secret
        # and credential echo prove we retain the connector's sanitized bytes.
        secret = "synthetic-test-key"

        def reply(request):
            dataset = ("national" if "us-nuclear" in request.url.path else
                       "facility" if "facility-nuclear" in request.url.path else "generator")
            rows = [] if int(request.url.params["offset"]) else [source_row(dataset)]
            return httpx.Response(200, json={"apiVersion": "2.1.12",
                "api_key": secret, "echo": secret,
                "response": {"frequency": "daily", "total": "1", "data": rows}})

        results = asyncio.run(retrieve_all(
            start=START, end=END, settings=EIASettings(EIA_API_KEY=secret),
            transport=httpx.MockTransport(reply),
        ))
        frozen = self.freeze([result.metadata for result in results])
        saved = (frozen.root / "source-evidence.json").read_text()
        self.assertNotIn(secret, saved)
        self.assertIn("[REDACTED]", saved)
        self.assertEqual(json.loads(saved)["routes"], [r.metadata.to_dict() for r in results])


class ManifestIdentityTests(FileFixture):
    """Exercise deterministic manifest encodings and strict reader boundaries."""

    def test_s18_entry_order_and_all_covered_values(self) -> None:
        manifest = self.freeze().manifest
        reordered = replace(manifest, entries=tuple(reversed(manifest.entries)))
        self.assertEqual(manifest.digest, reordered.digest)
        entry = manifest.entries[0]
        changes = {"storage_path": "data/another.parquet", "row_count": 2,
                   "max_period": END, "schema_fingerprint": "0" * 64,
                   "sha256": "0" * 64, "byte_size": entry.byte_size + 1}
        for name, value in changes.items():
            with self.subTest(field=name):
                changed = replace(manifest, entries=(replace(entry, **{name: value}),
                                                       *manifest.entries[1:]))
                self.assertNotEqual(manifest.digest, changed.digest)
                with self.assertRaises(ManifestError):
                    read_manifest(changed.to_bytes(), manifest.digest)
        # Unsupported contract versions cannot be used, even with a matching
        # recalculated checksum. They also invalidate the previous identity.
        body = json.loads(manifest.to_bytes())
        for field, value in (("contract_version", 2), ("manifest_format", 2),
                             ("source_evidence_sha256", "0" * 64),
                             ("version_id", str(uuid4())), ("requested_end", "2026-10-04")):
            changed = canonical_json({**body, field: value})
            self.assertNotEqual(sha256(changed), manifest.digest)
            with self.assertRaises(ManifestError):
                read_manifest(changed, manifest.digest)
            if field in ("contract_version", "manifest_format"):
                with self.assertRaises(ManifestError):
                    read_manifest(changed, sha256(changed))

    def test_s21_unsafe_paths_duplicate_entries_and_dataset_sets(self) -> None:
        manifest = self.freeze().manifest
        entry = manifest.entries[0]
        for path in ("../escape", "/tmp/file", "s3://bucket/file", "https://host/file",
                     "data//file.parquet", "data/./file.parquet", "data/../file.parquet",
                     "data\\file.parquet", "", "data/file.parquet/", "data/\x00.parquet"):
            with self.subTest(path=path):
                with self.assertRaises(ManifestError):
                    replace(manifest, entries=(replace(entry, storage_path=path),
                                              *manifest.entries[1:]))
        for entries in (manifest.entries[:-1], (*manifest.entries, entry),
                        (replace(entry, dataset_key="unknown"), *manifest.entries[1:])):
            with self.assertRaises(ManifestError):
                replace(manifest, entries=entries)

    def test_s21_reader_rejects_unsafe_manifest_before_parquet_access(self) -> None:
        result = self.freeze()
        body = json.loads(result.manifest.to_bytes())
        body["entries"][0]["storage_path"] = "../outside.parquet"
        changed = canonical_json(body)
        (result.root / "manifest.json").write_bytes(changed)
        with patch("trinity.connector.parquet.pq.ParquetFile") as read:
            with self.assertRaises(FreezeError):
                inspect_frozen_files(result.root, sha256(changed))
            read.assert_not_called()

    def test_schema_identity_covers_order_type_and_nullability_not_metadata(self) -> None:
        schema = DATASETS["national"].schema
        original = schema_fingerprint("national", schema)
        self.assertEqual(original, schema_fingerprint("national", schema.with_metadata({b"writer": b"test"})))
        for changed in (pa.schema(list(schema)[::-1]), schema.set(0, pa.field("period", pa.date32())),
                        schema.set(0, pa.field("period", pa.string(), nullable=False))):
            self.assertNotEqual(original, schema_fingerprint("national", changed))

    def test_canonical_json_rejects_floats_and_lossy_decimals(self) -> None:
        with localcontext() as context:
            context.prec = 2
            self.assertEqual(canonical_json({"z": Decimal("863.4000000"), "a": START}),
                             b'{"a":"2026-10-01","z":"863.400000"}')
        for value in (1.25, float("nan"), float("inf"), Decimal("1.0000001"), Decimal("NaN")):
            with self.assertRaises(ManifestError):
                canonical_json({"value": value})

    def test_reader_rejects_duplicate_keys_noncanonical_bytes_and_missing_fields(self) -> None:
        manifest = self.freeze().manifest
        body = manifest.to_bytes()
        duplicate = b'{"contract_version":1,' + body[1:]
        missing = json.loads(body)
        del missing["source_evidence_sha256"]
        for changed in (duplicate, body + b"\n", canonical_json(missing), b"{}", b"null"):
            with self.assertRaises(ManifestError):
                read_manifest(changed, sha256(changed))


if __name__ == "__main__":
    unittest.main()
