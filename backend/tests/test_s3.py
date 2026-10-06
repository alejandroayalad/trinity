"""Test storage with real local Parquet and a conditional in-memory S3 double.

The double models request outcomes, not a deployed bucket policy. No test
loads real credentials or sends a network request. Explicit fake credentials
below let botocore Stubber verify the pinned SDK's request shape offline.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, ReadTimeoutError
from botocore.response import StreamingBody
from botocore.stub import Stubber

from test_parquet import START, END
from test_validate import reconciled, records_for
from trinity.adapters import s3
from trinity.adapters.s3 import S3Storage, StorageError, StoredArtifact
from trinity.config import ConfigurationError, S3Settings, load_s3_settings
from trinity.connector import parquet, pipeline
from trinity.connector.parquet import freeze_files
from trinity.connector.pipeline import store_candidate, verify_stored_candidate
from trinity.connector.validate import validate_candidate
from trinity.contracts.manifest import read_json, sha256


def sdk_error(code, status):
    """Put a synthetic secret in SDK text to detect unsafe exception copying."""
    return ClientError({"Error": {"Code": code, "Message": "synthetic-private-value"},
                        "ResponseMetadata": {"HTTPStatusCode": status}}, "ObjectOperation")


class FakeClock:
    """Advance retry time without sleeping; tests remain deterministic."""

    def __init__(self):
        self.now, self.waits = 0.0, []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


class MemoryS3:
    """Atomically reject overwrites and expose hooks for controlled failures."""

    def __init__(self):
        self.objects, self.puts, self.gets, self.bodies = {}, [], [], []
        self.before_put = self.after_put = self.before_get = None
        self.lock = threading.Lock()

    def put_object(self, **request):
        self.puts.append(request)
        if self.before_put:
            self.before_put(request)
        # A lock models S3's write-time condition. HEAD followed by PUT would
        # fail the concurrent reservation test because both writers could win.
        with self.lock:
            if request["IfNoneMatch"] != "*":
                raise AssertionError("unconditional write")
            if request["Key"] in self.objects:
                raise sdk_error("PreconditionFailed", 412)
            self.objects[request["Key"]] = request["Body"]
        if self.after_put:
            self.after_put(request)
        return {"ETag": '"deliberately-not-a-sha256"'}

    def get_object(self, **request):
        self.gets.append(request)
        if self.before_get:
            self.before_get(request)
        if request["Key"] not in self.objects:
            raise sdk_error("NoSuchKey", 404)
        body = io.BytesIO(self.objects[request["Key"]])
        self.bodies.append(body)
        return {"Body": body, "ContentLength": len(self.objects[request["Key"]]),
                "ETag": '"deliberately-not-a-sha256"'}


class StorageTests(unittest.TestCase):
    """Exercise the entire saved-validation to stored-bundle boundary."""

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.settings = S3Settings("trinity-test-bucket", "private/candidates", "us-east-1")
        self.clock, self.client = FakeClock(), MemoryS3()
        self.storage = S3Storage(self.settings, client=self.client,
                                 clock=self.clock, sleep=self.clock.sleep)

    def candidate(self, rows=None):
        frozen = freeze_files(output_root=self.root, start=START, end=END,
                              retrieval=records_for(reconciled() if rows is None else rows))
        return validate_candidate(frozen.root, frozen.manifest_sha256)

    def key(self, report, path):
        return f"{self.settings.prefix}/{report.manifest.version_id}/{path}"

    def failures(self, report):
        return [read_json(path.read_bytes()) for path in
                report.root.glob("evidence/storage-*/failure.json")]

    def test_complete_bundle_is_private_unpublished_and_all_bytes_verified(self):
        report = self.candidate()
        receipt = store_candidate(report, self.storage)
        self.assertFalse(receipt.published)
        self.assertEqual(receipt.warning_count, 0)
        self.assertFalse(receipt.approval_required)
        self.assertEqual(self.client.puts[0]["Key"], self.key(report, "reservation.json"))
        self.assertEqual(self.client.puts[-1]["Key"], self.key(report, "bundle.json"))
        self.assertEqual(len(self.client.objects), len(receipt.artifacts) + 1)
        for artifact in receipt.artifacts:
            data = self.client.objects[self.key(report, artifact.storage_path)]
            expected = ((artifact.stored_byte_size, artifact.stored_sha256)
                        if artifact.encoding == "gzip-v1" else (artifact.byte_size, artifact.sha256))
            self.assertEqual((len(data), sha256(data)), expected)
        self.assertEqual(receipt.bundle_format, 2)
        self.assertTrue(any(item.encoding == "gzip-v1" for item in receipt.artifacts))
        self.assertEqual(receipt.bundle_sha256,
                         sha256(self.client.objects[self.key(report, "bundle.json")]))
        self.assertTrue(all(body.closed for body in self.client.bodies))
        self.assertTrue(all(item["IfNoneMatch"] == "*" and "ACL" not in item
                            for item in self.client.puts))
        verify_stored_candidate(report, receipt, self.storage)
        self.assertEqual(self.failures(report), [])

    def test_warning_bearing_candidate_stores_without_approval_or_publication(self):
        rows = reconciled()
        rows["facility"][0]["facilityName"] = None
        report = self.candidate(rows)
        receipt = store_candidate(report, self.storage)
        self.assertEqual(receipt.warning_count, 1)
        self.assertTrue(receipt.approval_required)
        self.assertFalse(receipt.published)
        verify_stored_candidate(report, receipt, self.storage)

    def test_failed_validation_or_changed_file_never_starts_remote_write(self):
        for mode in ("failed", "changed", "missing", "extra"):
            with self.subTest(mode=mode):
                report = self.candidate()
                if mode == "failed":
                    report = replace(report, status="failed")
                elif mode == "changed":
                    (report.root / "data/national.parquet").write_bytes(b"changed")
                elif mode == "missing":
                    (report.root / "data/national.parquet").unlink()
                else:
                    (report.root / "data/extra.parquet").write_bytes(b"extra")
                with self.assertRaises(StorageError):
                    store_candidate(report, self.storage)
                self.assertEqual(self.client.puts, [])
                self.assertEqual(self.failures(report)[0]["status"], "incomplete")

    def test_change_during_upload_blocks_bundle_and_keeps_original_manifest(self):
        report = self.candidate()
        original = (report.root / "manifest.json").read_bytes()
        def mutate(request):
            if request["Key"].endswith("data/national.parquet"):
                (report.root / "data/national.parquet").write_bytes(b"mutated")
        self.client.after_put = mutate
        with self.assertRaises(StorageError):
            store_candidate(report, self.storage)
        self.assertNotIn(self.key(report, "bundle.json"), self.client.objects)
        self.assertEqual((report.root / "manifest.json").read_bytes(), original)
        self.assertEqual(len(self.failures(report)), 1)

    def test_reservation_collision_stops_before_any_data_and_preserves_bytes(self):
        report = self.candidate()
        key = self.key(report, "reservation.json")
        self.client.objects[key] = b"another-preparation"
        with self.assertRaisesRegex(StorageError, "prefix_collision"):
            store_candidate(report, self.storage)
        self.assertEqual(len(self.client.puts), 1)
        self.assertEqual(self.client.objects, {key: b"another-preparation"})

    def test_concurrent_writers_have_only_one_reservation_winner(self):
        report = self.candidate()
        barrier = threading.Barrier(2)
        self.client.before_put = lambda request: barrier.wait(timeout=5)
        def reserve(token):
            operation = self.storage.operation(report.manifest.version_id)
            try:
                operation.put_verified("reservation.json", token, reservation=True)
                return "won"
            except StorageError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, (b"first", b"second")))
        self.assertCountEqual(results, ["won", "prefix_collision"])
        self.assertEqual(len(self.client.objects), 1)

    def test_concurrent_complete_stores_cannot_mix_two_preparations(self):
        report = self.candidate()
        barrier = threading.Barrier(2)
        def wait_at_reservation(request):
            if request["Key"].endswith("reservation.json"):
                barrier.wait(timeout=5)
        self.client.before_put = wait_at_reservation
        def store(_index):
            try:
                return store_candidate(report, self.storage)
            except StorageError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(store, (1, 2)))
        self.assertEqual(results.count("prefix_collision"), 1)
        receipt = next(result for result in results if not isinstance(result, str))
        verify_stored_candidate(report, receipt, self.storage)
        # The loser can add local failure evidence. It cannot add data or its
        # reservation token to the winner's immutable bundle.
        self.assertEqual(len(self.client.objects), len(receipt.artifacts) + 1)
        self.assertEqual(len(self.failures(report)), 1)

    def test_existing_artifact_requires_exact_bytes_and_never_overwrites(self):
        for data in (b"same", b"other"):
            with self.subTest(data=data):
                report = self.candidate()
                key = self.key(report, "data/test.parquet")
                self.client.objects[key] = data
                operation = self.storage.operation(report.manifest.version_id)
                if data == b"same":
                    operation.put_verified("data/test.parquet", b"same")
                else:
                    with self.assertRaisesRegex(StorageError, "object_identity"):
                        operation.put_verified("data/test.parquet", b"same")
                self.assertEqual(self.client.objects[key], data)

    def test_ambiguous_saved_writes_resolve_by_readback_including_final_bundle(self):
        report = self.candidate()
        def timeout_after_save(request):
            raise ReadTimeoutError(endpoint_url="https://synthetic-private-value")
        self.client.after_put = timeout_after_save
        receipt = store_candidate(report, self.storage)
        self.assertEqual(len(self.client.puts), len(self.client.objects))
        verify_stored_candidate(report, receipt, self.storage)

    def test_temporary_missing_writes_have_three_attempts_and_one_three_waits(self):
        report = self.candidate()
        self.client.before_put = lambda request: (_ for _ in ()).throw(sdk_error("SlowDown", 503))
        with self.assertRaisesRegex(StorageError, "write_unresolved"):
            store_candidate(report, self.storage)
        self.assertEqual(len(self.client.puts), 3)
        self.assertEqual(self.clock.waits, [1, 3])
        self.assertEqual(self.client.objects, {})

    def test_temporary_write_recovers_then_reads_exact_bytes(self):
        report = self.candidate()
        def fail_twice(request):
            if len(self.client.puts) <= 2:
                raise sdk_error("ConditionalRequestConflict", 409)
        self.client.before_put = fail_twice
        receipt = store_candidate(report, self.storage)
        self.assertEqual(self.clock.waits, [1, 3])
        self.assertEqual(len(self.client.puts), len(receipt.artifacts) + 3)

    def test_permanent_error_does_not_retry_or_leak_and_retains_partial_progress(self):
        report = self.candidate()
        def deny(request):
            if len(self.client.puts) == 4:
                raise sdk_error("AccessDenied", 403)
        self.client.before_put = deny
        with self.assertRaises(StorageError) as caught:
            store_candidate(report, self.storage)
        self.assertEqual(len(self.client.puts), 4)
        self.assertEqual(self.clock.waits, [])
        self.assertNotIn("synthetic-private-value", str(caught.exception))
        self.assertNotIn(self.key(report, "bundle.json"), self.client.objects)
        journal = next(report.root.glob("evidence/storage-*/journal.jsonl")).read_bytes()
        self.assertEqual([read_json(line)["event"] for line in journal.splitlines()],
                         ["started", "reserved", "object_verified", "object_verified"])
        self.assertNotIn(b"synthetic-private-value", journal)
        self.assertEqual(self.failures(report)[0]["error_code"], "object_write_failed")

    def test_failed_readback_exhausts_reads_without_reupload(self):
        report = self.candidate()
        self.client.before_get = lambda request: (_ for _ in ()).throw(sdk_error("SlowDown", 503))
        with self.assertRaisesRegex(StorageError, "object_read_failed"):
            store_candidate(report, self.storage)
        self.assertEqual(len(self.client.puts), 1)
        self.assertEqual(len(self.client.gets), 3)
        self.assertEqual(self.clock.waits, [1, 3])

    def test_stream_interruption_retries_a_fresh_body_and_closes_each_body(self):
        report = self.candidate()
        original = self.client.get_object
        streams = []
        class InterruptedBody(io.BytesIO):
            def read(self, size):
                if self.tell() > 0:
                    raise ReadTimeoutError(endpoint_url="https://synthetic-private-value")
                return super().read(1)
        def interrupted(**request):
            response = original(**request)
            if len(self.client.gets) <= 2:
                response["Body"].close()
                response["Body"] = InterruptedBody(self.client.objects[request["Key"]])
                streams.append(response["Body"])
            return response
        self.client.get_object = interrupted
        receipt = store_candidate(report, self.storage)
        self.assertEqual(self.clock.waits, [1, 3])
        self.assertTrue(all(stream.closed for stream in streams))
        verify_stored_candidate(report, receipt, self.storage)

    def test_ambiguous_final_write_with_unreadable_bytes_is_not_success(self):
        report = self.candidate()
        def timeout(request):
            if request["Key"].endswith("bundle.json"):
                raise ReadTimeoutError(endpoint_url="https://synthetic-private-value")
        def deny_bundle(request):
            if request["Key"].endswith("bundle.json"):
                raise sdk_error("AccessDenied", 403)
        self.client.after_put, self.client.before_get = timeout, deny_bundle
        with self.assertRaises(StorageError):
            store_candidate(report, self.storage)
        self.assertIn(self.key(report, "bundle.json"), self.client.objects)
        self.assertEqual(list(report.root.glob("evidence/storage-*/result.json")), [])
        self.assertEqual(len(self.failures(report)), 1)

    def test_wrong_or_truncated_readback_fails_even_with_matching_etag(self):
        for body in (b"wrong", b""):
            with self.subTest(body=body):
                report = self.candidate()
                self.client.after_put = lambda request: self.client.objects.__setitem__(request["Key"], body)
                with self.assertRaisesRegex(StorageError, "object_identity"):
                    store_candidate(report, self.storage)
                self.assertNotIn(self.key(report, "bundle.json"), self.client.objects)
                self.assertTrue(all(stream.closed for stream in self.client.bodies))

    def test_final_verification_rechecks_previously_verified_objects(self):
        report = self.candidate()
        def corrupt_earlier(request):
            if request["Key"].endswith("bundle.json"):
                self.client.objects[self.key(report, "data/national.parquet")] = b"corrupt"
        self.client.after_put = corrupt_earlier
        with self.assertRaisesRegex(StorageError, "object_identity"):
            store_candidate(report, self.storage)
        self.assertEqual(list(report.root.glob("evidence/storage-*/result.json")), [])

    def test_object_limit_and_unsafe_paths_fail_before_remote_upload(self):
        report = self.candidate()
        with patch.object(pipeline, "MAX_OBJECT_BYTES", 16):
            with self.assertRaisesRegex(StorageError, "object_too_large"):
                store_candidate(report, self.storage)
        self.assertEqual(self.client.puts, [])
        operation = self.storage.operation(report.manifest.version_id)
        for path in ("../escape", "/absolute", "https://host/key", "data//x", "data\\x"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                operation.put_verified(path, b"x")
        with patch.object(s3, "MAX_OBJECT_BYTES", 3):
            with self.assertRaisesRegex(StorageError, "object_too_large"):
                operation.put_verified("data/x", b"four")
        self.assertEqual(self.client.puts, [])

    def test_deadline_in_retry_wait_and_after_request_blocks_success(self):
        report = self.candidate()
        self.client.before_put = lambda request: (_ for _ in ()).throw(sdk_error("SlowDown", 503))
        with self.assertRaisesRegex(StorageError, "storage_deadline"):
            store_candidate(report, self.storage, timeout_seconds=1)
        self.assertEqual(self.clock.waits, [])
        self.client.before_put = None
        self.client.after_put = lambda request: setattr(self.clock, "now", self.clock.now + 301)
        with self.assertRaisesRegex(StorageError, "storage_deadline"):
            store_candidate(self.candidate(), self.storage)

    def test_deadline_during_streaming_and_invalid_budgets_block_success(self):
        report = self.candidate()
        original = self.client.get_object
        clock = self.clock
        class SlowBody(io.BytesIO):
            def read(self, size):
                clock.now += 301
                return super().read(size)
        def delayed(**request):
            response = original(**request)
            response["Body"].close()
            response["Body"] = SlowBody(self.client.objects[request["Key"]])
            return response
        self.client.get_object = delayed
        with self.assertRaisesRegex(StorageError, "storage_deadline"):
            store_candidate(report, self.storage)
        for timeout in (0, -1, 301, True, float("nan"), float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(StorageError):
                self.storage.operation(report.manifest.version_id, timeout_seconds=timeout)

    def test_cancel_and_interrupt_keep_prior_evidence_without_bundle(self):
        report = self.candidate()
        with self.assertRaisesRegex(StorageError, "cancelled"):
            store_candidate(report, self.storage, cancelled=lambda: len(self.client.puts) >= 3)
        self.assertEqual(len(self.failures(report)), 1)
        self.assertNotIn(self.key(report, "bundle.json"), self.client.objects)
        report = self.candidate()
        def interrupt(request):
            raise KeyboardInterrupt
        self.client.after_put = interrupt
        with self.assertRaises(KeyboardInterrupt):
            store_candidate(report, self.storage)
        self.assertEqual(self.failures(report)[0]["error_code"], "cancelled")

    def test_local_persistence_failure_blocks_completion(self):
        original = parquet._write_bytes
        for suffix in ("plan.json", "bundle.json", "result.json"):
            with self.subTest(suffix=suffix):
                report = self.candidate()
                def fail(root, path, data):
                    if path.endswith(suffix):
                        raise OSError("synthetic-private-value")
                    return original(root, path, data)
                with patch.object(parquet, "_write_bytes", side_effect=fail):
                    with self.assertRaises(StorageError):
                        store_candidate(report, self.storage)
                journal = next(report.root.glob("evidence/storage-*/journal.jsonl")).read_bytes()
                self.assertNotIn(b'"event":"completed"', journal)
                self.assertEqual(len(self.failures(report)), 1)

    def test_journal_sync_failure_keeps_partial_upload_incomplete(self):
        report = self.candidate()
        original = pipeline.os.fsync
        def fail_during_upload(descriptor):
            if len(self.client.puts) >= 3:
                raise OSError("synthetic-private-value")
            return original(descriptor)
        with patch.object(pipeline.os, "fsync", side_effect=fail_during_upload):
            with self.assertRaises(StorageError):
                store_candidate(report, self.storage)
        self.assertNotIn(self.key(report, "bundle.json"), self.client.objects)
        self.assertEqual(list(report.root.glob("evidence/storage-*/result.json")), [])

    def test_local_bundle_and_receipt_readback_detect_silent_write_damage(self):
        original = parquet._write_bytes
        for suffix in ("bundle.json", "result.json"):
            with self.subTest(suffix=suffix):
                report = self.candidate()
                def damage(root, path, data):
                    original(root, path, b"{}" if path.endswith(suffix) else data)
                with patch.object(parquet, "_write_bytes", side_effect=damage):
                    with self.assertRaises(StorageError):
                        store_candidate(report, self.storage)
                journal = next(report.root.glob("evidence/storage-*/journal.jsonl")).read_bytes()
                self.assertNotIn(b'"event":"completed"', journal)

    def test_changed_local_upload_evidence_cannot_return_a_success_receipt(self):
        for name in ("plan.json", "reservation.json", "journal.jsonl"):
            with self.subTest(name=name):
                report = self.candidate()
                def damage_evidence(request):
                    if request["Key"].endswith("bundle.json"):
                        path = next(report.root.glob(f"evidence/storage-*/{name}"))
                        # Change a byte without truncating the open journal.
                        # This models silent corruption after prior fsync calls.
                        with path.open("r+b") as stream:
                            stream.write(b"!")
                self.client.after_put = damage_evidence
                with self.assertRaisesRegex(StorageError, "storage_evidence_readback"):
                    store_candidate(report, self.storage)
                self.assertEqual(len(self.failures(report)), 1)

    def test_snapshot_cannot_rebind_a_validated_file_to_new_bytes(self):
        report = self.candidate()
        original = pipeline._storage_snapshot
        def altered_identity(root):
            artifacts = original(root)
            return tuple(replace(item, sha256="0" * 64) if item.storage_path == "data/national.parquet"
                         else item for item in artifacts)
        with patch.object(pipeline, "_storage_snapshot", side_effect=altered_identity):
            with self.assertRaisesRegex(StorageError, "snapshot_validation_identity"):
                store_candidate(report, self.storage)
        self.assertEqual(self.client.puts, [])

    def test_later_consumer_rejects_remote_mutation_and_mixed_receipt(self):
        report = self.candidate()
        receipt = store_candidate(report, self.storage)
        with self.assertRaisesRegex(StorageError, "receipt_identity"):
            verify_stored_candidate(report, replace(receipt, published=True), self.storage)
        for path in ("manifest.json", "data/national.parquet", "bundle.json"):
            with self.subTest(path=path):
                key = self.key(report, path)
                original = self.client.objects.pop(key)
                with self.assertRaises(StorageError):
                    verify_stored_candidate(report, receipt, self.storage)
                self.client.objects[key] = original
        journal = report.root / receipt.storage_evidence_path / "journal.jsonl"
        # Removing completion must make a persisted result.json insufficient.
        journal.write_bytes(b"\n".join(journal.read_bytes().splitlines()[:-1]) + b"\n")
        with self.assertRaisesRegex(StorageError, "storage_incomplete"):
            verify_stored_candidate(report, receipt, self.storage)

    def test_later_consumer_rejects_changed_journal_details_or_local_bundle(self):
        report = self.candidate()
        receipt = store_candidate(report, self.storage)
        journal = report.root / receipt.storage_evidence_path / "journal.jsonl"
        original = journal.read_bytes()
        journal.write_bytes(original.replace(b'"byte_size":', b'"changed_size":', 1))
        with self.assertRaisesRegex(StorageError, "storage_incomplete"):
            verify_stored_candidate(report, receipt, self.storage)
        journal.write_bytes(original)
        bundle = report.root / "bundle.json"
        bundle.write_bytes(bundle.read_bytes() + b" ")
        with self.assertRaisesRegex(StorageError, "bundle_identity"):
            verify_stored_candidate(report, receipt, self.storage)

    def test_pinned_sdk_request_shape_with_stubber(self):
        # Stubber intercepts requests before HTTP. These are fake credentials,
        # so the SDK also has no reason to query a metadata credential service.
        client = boto3.client("s3", region_name="us-east-1", aws_access_key_id="testing",
                              aws_secret_access_key="testing", config=Config(retries={"total_max_attempts": 1}))
        self.addCleanup(client.close)
        storage = S3Storage(self.settings, client=client)
        report = self.candidate()
        key = self.key(report, "reservation.json")
        with Stubber(client) as stub:
            stub.add_response("put_object", {}, {"Bucket": self.settings.bucket, "Key": key,
                                                "Body": b"{}", "ContentLength": 2, "IfNoneMatch": "*"})
            stub.add_response("get_object", {"Body": StreamingBody(io.BytesIO(b"{}"), 2), "ContentLength": 2},
                              {"Bucket": self.settings.bucket, "Key": key})
            storage.operation(report.manifest.version_id).put_verified("reservation.json", b"{}", reservation=True)
            stub.assert_no_pending_responses()

    def test_client_creation_disables_sdk_retries_and_ambient_endpoints(self):
        with patch.object(s3.boto3, "client", return_value=self.client) as factory:
            S3Storage(self.settings)
        config = factory.call_args.kwargs["config"]
        self.assertEqual(config.retries, {"total_max_attempts": 1})
        self.assertEqual((config.connect_timeout, config.read_timeout), (5, 10))
        self.assertEqual(config.signature_version, "s3v4")
        self.assertTrue(config.ignore_configured_endpoint_urls)


class StorageConfigurationTests(unittest.TestCase):
    """Reject unsafe routing before resolving credentials or touching storage."""

    def test_explicit_environment_loading_and_safe_missing_errors(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigurationError):
                load_s3_settings()
        env = {"TRINITY_S3_BUCKET": "trinity-test-bucket", "TRINITY_S3_PREFIX": "private/candidates",
               "TRINITY_S3_REGION": "us-east-1"}
        with patch.dict(os.environ, env, clear=True):
            settings = load_s3_settings()
        self.assertEqual(settings.prefix, "private/candidates")
        self.assertNotIn("trinity-test-bucket", repr(settings))

    def test_invalid_settings_reject_paths_and_credential_bearing_endpoints(self):
        valid = dict(bucket="trinity-test-bucket", prefix="private/candidates", region="us-east-1")
        for field, values in {
            "bucket": ("", "x", "UPPER", "https://bucket", "a..b", "127.0.0.1", "a--x-s3"),
            "prefix": ("", "/root", "a/../b", "a//b", "s3://bucket", "a\\b", "a\nb"),
            "region": ("", "us east 1", "https://region"),
            "endpoint_url": ("http://host", "https://user:synthetic-private-value@host",
                             "https://host?key=synthetic-private-value", "https://host#secret",
                             "https://host/path", "https://host:bad", "https://host?"),
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ConfigurationError) as caught:
                        S3Settings(**{**valid, field: value})
                    self.assertNotIn("synthetic-private-value", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
