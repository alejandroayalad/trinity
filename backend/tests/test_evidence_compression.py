"""Check versioned gzip evidence, hostile streams and both storage readers.

Use synthetic bytes and an in-memory S3 double. No credentials, EIA requests,
remote uploads or retained publications are needed for these regressions.
"""

from dataclasses import replace
import gzip
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import ReadTimeoutError
from botocore.response import StreamingBody
from botocore.stub import Stubber

from refresh_fixture import stored_result
from test_preview_provenance import frozen_fixture
from test_s3 import FakeClock, MemoryS3
from test_sql_staging import Client
from trinity.adapters.s3 import S3Storage, StorageError, StoredArtifact, verified_chunks
from trinity.config import S3Settings
from trinity.connector.pipeline import verify_stored_candidate
from trinity.contracts.manifest import canonical_json, read_json, sha256
from trinity.errors import Problem
from trinity.publication.diagnostics import read_preview_diagnostics
from trinity.queries.service import QueryDeadline
from trinity.queries.staging import PublishedReader
from trinity.refresh.evidence import load_candidate


class CompressionTests(unittest.TestCase):
    def setUp(self):
        self.path = "evidence/details.json"
        self.data = canonical_json({"values": ["003", "0.000000", None] * 10000})
        self.artifact = StoredArtifact.from_bytes(self.path, self.data, compress=True)
        self.packed = self.artifact.encode(self.data)
        self.client, self.clock = MemoryS3(), FakeClock()
        self.settings = S3Settings("synthetic-bucket", "versions", "us-east-1")
        self.storage = S3Storage(self.settings, client=self.client, clock=self.clock, sleep=self.clock.sleep)
        self.version = str(uuid4())
        self.key = f"versions/{self.version}/{self.path}"

    def test_deterministic_roundtrip_preserves_values_and_both_hashes(self):
        self.assertEqual(self.artifact.encoding, "gzip-v1")
        self.assertLess(len(self.packed), len(self.data) // 10)
        self.assertEqual(self.artifact.encode(self.data), self.packed)
        self.assertEqual(gzip.decompress(self.packed), self.data)
        self.assertEqual((self.artifact.byte_size, self.artifact.sha256), (len(self.data), sha256(self.data)))
        self.assertEqual((self.artifact.stored_byte_size, self.artifact.stored_sha256),
                         (len(self.packed), sha256(self.packed)))
        with self.assertRaises(StorageError):
            self.artifact.encode(self.data + b" ")

    def test_bootstrap_parquet_and_unprofitable_small_files_stay_unencoded(self):
        for path, data in (("bundle.json", self.data), ("manifest.json", self.data),
                           ("reservation.json", self.data), ("data/national.parquet", self.data),
                           (self.path, b"{}")):
            with self.subTest(path=path):
                artifact = StoredArtifact.from_bytes(path, data, compress=True)
                self.assertEqual(artifact.encoding, "identity")
                self.assertEqual(artifact.encode(data), data)
                self.assertEqual(set(artifact.to_dict()), {"storage_path", "sha256", "byte_size"})

    def test_descriptors_are_strict_and_old_shape_is_preserved(self):
        raw = StoredArtifact.from_bytes(self.path, self.data)
        for version in (1, 2):
            self.assertEqual(StoredArtifact.from_dict(raw.to_dict(), version), raw)
        self.assertEqual(StoredArtifact.from_dict(self.artifact.to_dict(), 2), self.artifact)
        for version, value in ((1, self.artifact.to_dict()), (True, raw.to_dict()), (3, raw.to_dict()),
                               (2, self.artifact.to_dict() | {"encoding": "gzip-v2"}),
                               (2, self.artifact.to_dict() | {"stored_byte_size": True}),
                               (2, self.artifact.to_dict() | {"stored_sha256": "not-a-hash"}),
                               (2, self.artifact.to_dict() | {"extra": 1}),
                               (2, self.artifact.to_dict() | {"storage_path": "data/national.parquet"})):
            with self.subTest(version=version, value=value), self.assertRaises(StorageError):
                StoredArtifact.from_dict(value, version)

    def test_pinned_sdk_put_uses_compressed_length_and_conditional_write(self):
        client = boto3.client("s3", region_name="us-east-1", aws_access_key_id="testing",
                              aws_secret_access_key="testing", config=Config(retries={"total_max_attempts": 1}))
        self.addCleanup(client.close)
        with Stubber(client) as stub:
            stub.add_response("put_object", {}, {"Bucket": self.settings.bucket, "Key": self.key,
                "Body": self.packed, "ContentLength": len(self.packed), "IfNoneMatch": "*"})
            stub.add_response("get_object", {"Body": StreamingBody(io.BytesIO(self.packed), len(self.packed)),
                "ContentLength": len(self.packed)}, {"Bucket": self.settings.bucket, "Key": self.key})
            storage = S3Storage(self.settings, client=client)
            result = storage.operation(self.version).put_verified(self.path, self.data, artifact=self.artifact)
            self.assertEqual(result, self.artifact)
            stub.assert_no_pending_responses()

    def test_ambiguous_compressed_upload_reuses_exact_bytes_without_overwrite(self):
        def timeout(_request):
            raise ReadTimeoutError(endpoint_url="https://synthetic.invalid")
        self.client.after_put = timeout
        operation = self.storage.operation(self.version)
        operation.put_verified(self.path, self.data, artifact=self.artifact)
        self.assertEqual(len(self.client.puts), 1)
        self.assertEqual(self.client.objects[self.key], self.packed)
        self.assertTrue(all(body.closed for body in self.client.bodies))

    def test_stored_hash_rejects_a_different_encoding_of_identical_original(self):
        # A changed gzip timestamp leaves decoded bytes unchanged. The second
        # hash is essential: checking only the original JSON would miss this.
        changed = gzip.compress(self.data, compresslevel=1, mtime=1)
        self.assertEqual(gzip.decompress(changed), self.data)
        self.client.objects[self.key] = changed
        with self.assertRaisesRegex(StorageError, "object_identity"):
            self.storage.operation(self.version).verify(self.artifact)
        self.assertEqual(len(self.client.gets), 1)

    def test_corruption_truncation_trailing_data_and_concatenation_fail(self):
        damaged_crc = self.packed[:-8] + bytes([self.packed[-8] ^ 1]) + self.packed[-7:]
        for data in (damaged_crc, self.packed[:-1], self.packed + b"extra",
                     self.packed + gzip.compress(b"another member")):
            # Rebind the stored identity so rejection must come from gzip or
            # original-byte verification, not just the outer hash/length check.
            artifact = replace(self.artifact, stored_sha256=sha256(data), stored_byte_size=len(data))
            self.client.objects[self.key] = data
            with self.subTest(size=len(data)), self.assertRaisesRegex(StorageError, "object_identity"):
                self.storage.operation(self.version).verify(artifact)
        self.assertTrue(all(body.closed for body in self.client.bodies))

    def test_declared_expansion_and_reader_budget_bound_output(self):
        body = io.BytesIO(self.packed)
        response = {"Body": body, "ContentLength": len(self.packed)}
        # A plausible stored hash must not authorize an expansion beyond the
        # separately bound original length, even inside a single decoded chunk.
        small = replace(self.artifact, byte_size=16)
        with self.assertRaisesRegex(StorageError, "object_identity"):
            list(verified_chunks(response, small, checkpoint=lambda: None))
        self.client.objects[self.key] = self.packed
        reader = PublishedReader(self.client, self.settings)
        with self.assertRaises(Problem) as caught:
            reader.read_into(self.version, self.path, io.BytesIO(), deadline=QueryDeadline(30),
                max_bytes=len(self.data) - 1, digest=self.artifact.sha256,
                expected_size=self.artifact.byte_size, artifact=self.artifact)
        self.assertEqual(caught.exception.code, "query_resource_limit")
        self.assertTrue(all(body.closed for body in self.client.bodies))

    def test_checks_run_between_bounded_decompression_chunks(self):
        data = b"x" * (3 * 1024 * 1024)
        artifact = StoredArtifact.from_bytes(self.path, data, compress=True)
        packed = artifact.encode(data)
        stream = verified_chunks({"Body": io.BytesIO(packed), "ContentLength": len(packed)},
            artifact, checkpoint=self.storage.operation(self.version).checkpoint)
        self.assertEqual(len(next(stream)), 1024 * 1024)
        self.clock.now = 301
        with self.assertRaisesRegex(StorageError, "storage_deadline"):
            next(stream)

    def test_bad_original_hash_and_wire_length_fail_both_readers(self):
        self.client.objects[self.key] = self.packed
        for artifact in (replace(self.artifact, sha256="0" * 64),
                         replace(self.artifact, stored_byte_size=len(self.packed) + 1)):
            with self.subTest(artifact=artifact):
                with self.assertRaises(StorageError):
                    self.storage.operation(self.version).verify(artifact)
                with self.assertRaises(Problem):
                    PublishedReader(self.client, self.settings).read_into(self.version, self.path, io.BytesIO(),
                        deadline=QueryDeadline(30), max_bytes=len(self.data), digest=artifact.sha256,
                        expected_size=artifact.byte_size, artifact=artifact)
        self.assertTrue(all(body.closed for body in self.client.bodies))

    def test_chunked_streams_and_full_read_retry_reset_decoder_and_output(self):
        original = self.client.get_object
        self.client.objects[self.key] = self.packed
        class Interrupted(io.BytesIO):
            def read(self, size):
                if self.tell() >= 50:
                    raise ReadTimeoutError(endpoint_url="https://synthetic.invalid")
                return super().read(min(size, 50))
        class TinyChunks(io.BytesIO):
            def read(self, size):
                return super().read(min(size, 7))
        streams = []
        def get(**request):
            response = original(**request)
            response["Body"].close()
            response["Body"] = (Interrupted if len(self.client.gets) == 1 else TinyChunks)(self.packed)
            streams.append(response["Body"])
            return response
        self.client.get_object = get
        output = io.BytesIO(b"previous partial output")
        reader = PublishedReader(self.client, self.settings, sleep=self.clock.sleep)
        count = reader.read_into(self.version, self.path, output, deadline=QueryDeadline(30),
            max_bytes=len(self.data), digest=self.artifact.sha256,
            expected_size=len(self.data), artifact=self.artifact)
        self.assertEqual(count, len(self.data))
        self.assertEqual(output.getvalue(), self.data)
        self.assertEqual(self.clock.waits, [1])
        self.assertTrue(all(body.closed for body in streams))

    def test_expired_or_cancelled_storage_does_not_start_compression(self):
        for operation in (self.storage.operation(self.version, cancelled=lambda: True),
                          self.storage.operation(self.version, timeout_seconds=1)):
            self.clock.now = 2
            with patch("trinity.adapters.s3.gzip.compress") as encode:
                with self.assertRaises(StorageError):
                    operation.put_verified(self.path, self.data, artifact=self.artifact)
                encode.assert_not_called()
        self.assertEqual(self.client.puts, [])


class CompressionIntegrationTests(unittest.TestCase):
    def test_new_receipt_reloads_and_every_remote_original_is_unchanged(self):
        with TemporaryDirectory() as directory:
            report, receipt, objects, storage, digest = stored_result(Path(directory))
            self.assertEqual(receipt.bundle_format, 2)
            self.assertEqual(load_candidate(report.root, digest, storage).receipt, receipt)
            for artifact in receipt.artifacts:
                wire = objects[artifact.storage_path]
                decoded = gzip.decompress(wire) if artifact.encoding == "gzip-v1" else wire
                self.assertEqual((len(decoded), sha256(decoded)), (artifact.byte_size, artifact.sha256))
            self.assertTrue(any(item.encoding == "gzip-v1" for item in receipt.artifacts))
            self.assertEqual(storage.client.puts, [])  # Verification never rewrites a remote object.

    def test_legacy_v1_receipt_still_verifies_and_reloads(self):
        with TemporaryDirectory() as directory:
            report, receipt, objects, storage, _digest = stored_result(Path(directory))
            # Recreate the exact v1 layout in this disposable fixture. Existing
            # retained receipts do not have encoding fields or bundle_format=2.
            artifacts = []
            prefix = receipt.storage_evidence_path
            for item in receipt.artifacts:
                raw = gzip.decompress(objects[item.storage_path]) if item.encoding == "gzip-v1" else objects[item.storage_path]
                storage.client.objects[f"versions/{receipt.version_id}/{item.storage_path}"] = raw
                artifacts.append(StoredArtifact.from_bytes(item.storage_path, raw))
            bundle_path = report.root / "bundle.json"
            bundle = read_json(bundle_path.read_bytes())
            bundle.update(bundle_format=1, artifacts=[item.to_dict() for item in artifacts])
            bundle_bytes = canonical_json(bundle)
            bundle_path.write_bytes(bundle_bytes)
            storage.client.objects[f"versions/{receipt.version_id}/bundle.json"] = bundle_bytes
            receipt = replace(receipt, artifacts=tuple(artifacts), bundle_sha256=sha256(bundle_bytes), bundle_format=1)
            plan_path = report.root / prefix / "plan.json"
            plan = read_json(plan_path.read_bytes())
            plan["artifacts"] = [item.to_dict() for item in artifacts if item.storage_path != "reservation.json"]
            plan_path.write_bytes(canonical_json(plan))
            by_path = {item.storage_path: item for item in artifacts}
            by_path["bundle.json"] = StoredArtifact.from_bytes("bundle.json", bundle_bytes)
            journal_path = report.root / prefix / "journal.jsonl"
            events = [read_json(line) for line in journal_path.read_bytes().splitlines()]
            for event in events:
                if "artifact" in event:
                    event["artifact"] = by_path[event["artifact"]["storage_path"]].to_dict()
                if "bundle_sha256" in event:
                    event["bundle_sha256"] = receipt.bundle_sha256
            journal_path.write_bytes(b"".join(canonical_json(event) + b"\n" for event in events))
            for name in (f"{prefix}/result.json", "evidence/preparation/result.json", "evidence/preparation/receipt.json"):
                path = report.root / name
                result = read_json(path.read_bytes())
                result["bundle_sha256"] = receipt.bundle_sha256
                path.write_bytes(canonical_json(result))
            digest = sha256((report.root / "evidence/preparation/result.json").read_bytes())
            verify_stored_candidate(report, receipt, storage)
            self.assertEqual(load_candidate(report.root, digest, storage).receipt, receipt)
            self.assertEqual(storage.client.puts, [])

    def test_preview_reads_both_formats_and_rejects_format_downgrade(self):
        pinned, objects = frozen_fixture(padding=1024 * 1024)
        settings = SimpleNamespace(bucket="synthetic", prefix="versions")
        old = read_preview_diagnostics(pinned, "national", PublishedReader(Client(objects), settings), QueryDeadline(30))
        bundle = read_json(objects["bundle.json"])
        for index, value in enumerate(bundle["artifacts"]):
            path = value["storage_path"]
            if path not in objects:
                continue  # The synthetic manifest is not fetched by this evidence-only reader.
            artifact = StoredArtifact.from_bytes(path, objects[path], compress=True)
            bundle["artifacts"][index] = artifact.to_dict()
            objects[path] = artifact.encode(objects[path])
        bundle["bundle_format"] = 2
        objects["bundle.json"] = canonical_json(bundle)
        pinned = replace(pinned, evidence_bundle_sha256=sha256(objects["bundle.json"]))
        new = read_preview_diagnostics(pinned, "national", PublishedReader(Client(objects), settings), QueryDeadline(30))
        self.assertEqual(new, old)
        bundle["bundle_format"] = 1
        objects["bundle.json"] = canonical_json(bundle)
        pinned = replace(pinned, evidence_bundle_sha256=sha256(objects["bundle.json"]))
        with self.assertRaises(Problem):
            read_preview_diagnostics(pinned, "national", PublishedReader(Client(objects), settings), QueryDeadline(30))
