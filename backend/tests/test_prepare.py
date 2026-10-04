"""Exercise the real preparation supervisor with offline child processes.

Top-level worker functions are importable by Python's spawn mechanism. They
inject synthetic HTTP/storage inside the child; no production test-mode CLI
or environment switch can bypass the real adapters.
"""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import io
import os
from pathlib import Path
import signal
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch

import httpx

from test_s3 import MemoryS3, sdk_error
from test_validate import reconciled
from trinity.adapters.s3 import S3Storage
from trinity.connector import parquet, pipeline, prepare, validate
from trinity.contracts.manifest import read_json, sha256


SECRET = "synthetic-command-secret"


def fixture_worker(request, connection):
    """Run the production pipeline and supervisor protocol with fake services."""
    mode = request["s3"].prefix
    rows = reconciled()
    if mode == "warnings":
        rows["facility"][0]["facilityName"] = None
    elif mode == "parse-failure":
        rows["facility"][0]["outage"] = "0.0000001"
    elif mode == "validation-failure":
        rows["facility"][0]["outage"] = "10.000001"
    client = MemoryS3()
    if mode == "storage-failure":
        def denied(_request):
            raise sdk_error("AccessDenied", 403)
        client.before_put = denied
    elif mode == "read-failure":
        def denied(_request):
            raise sdk_error("AccessDenied", 403)
        client.before_get = denied
    elif mode == "collision":
        key = f"{mode}/{request['root'].name}/reservation.json"
        client.objects[key] = b"existing-different-bytes"
    elif mode == "ambiguous":
        from botocore.exceptions import ReadTimeoutError
        def ambiguous(_request):
            raise ReadTimeoutError(endpoint_url="https://synthetic-command-secret")
        client.after_put = ambiguous
    elif mode == "missing-credentials":
        from botocore.exceptions import NoCredentialsError
        def missing(_request):
            raise NoCredentialsError
        client.before_put = missing
    elif mode == "unresolved":
        def unavailable(_request):
            raise sdk_error("SlowDown", 503)
        client.before_put = unavailable
    elif mode == "corrupt":
        def corrupt(request):
            client.objects[request["Key"]] = b"corrupt"
        client.after_put = corrupt

    def handler(http_request):
        dataset = ("national" if "/us-" in http_request.url.path else
                   "facility" if "/facility-" in http_request.url.path else "generator")
        if mode == "extraction-failure" and dataset == "facility":
            return httpx.Response(401, json={"error": SECRET, "request": {"api_key": SECRET}})
        records = rows[dataset] if http_request.url.params["offset"] == "0" else []
        # Preserve unknown source fields, but remove keys and credential echoes
        # before any route journal or source-evidence file is saved.
        records = [{**row, "unknown_source_field": "retained"} for row in records]
        return httpx.Response(200, json={
            "apiVersion": "2.1.0", "request": {"api_key": SECRET},
            "authorization": SECRET, "cookie": SECRET, "echo": SECRET,
            "response": {"frequency": "daily", "total": str(len(rows[dataset])), "data": records},
        })
    if mode == "diagnostic-failure":
        def failed(*args):
            raise RuntimeError(SECRET)
        validate._diagnostic = failed
    if mode == "cancel":
        def cancelled(_request):
            raise KeyboardInterrupt
        client.before_put = cancelled
    if mode == "persistence-failure":
        original_retrieve = pipeline.retrieve_all
        async def fail_sink(**kwargs):
            original_save = kwargs["on_result"]
            def save(result):
                original_save(result)
                raise OSError(SECRET)
            kwargs["on_result"] = save
            return await original_retrieve(**kwargs)
        pipeline.retrieve_all = fail_sink
    if mode == "cancel-between-stages":
        original_event = prepare._send_stage
        def cancel_between(connection, event, stage, status):
            original_event(connection, event, stage, status)
            if event == "finished" and stage == "freeze":
                raise KeyboardInterrupt
        prepare._send_stage = cancel_between
    prepare._run_worker(request, connection, transport=httpx.MockTransport(handler),
                        storage_factory=lambda: S3Storage(request["s3"], client=client, sleep=lambda _seconds: None))


def blocked_worker(request, connection):
    """Reach a known stage, then ignore terminate to require a real hard kill."""
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    stage = request["s3"].prefix
    for name in prepare.STAGES:
        prepare._send_stage(connection, "started", name, None)
        if name == stage:
            # An actual blocked process tests the supervisor, not a mocked clock.
            time.sleep(60)
        prepare._send_stage(connection, "finished", name, "success")


def killed_worker(request, connection):
    """Die after a durable stage start; no receipt or final result can exist."""
    prepare._send_stage(connection, "started", prepare.STAGES[0], None)
    os.kill(os.getpid(), signal.SIGKILL)


def empty_worker(request, connection):
    """Exit zero without work; zero process status alone must not mean success."""
    connection.close()


def late_exit_worker(request, connection):
    """Send a valid receipt, but delay process exit beyond the stage budget."""
    fixture_worker(request, connection)
    time.sleep(1.2)


def bad_receipt_worker(request, connection):
    """Claim completion before running stages; exercise protocol rejection."""
    connection.send({"event": "receipt", "sha256": "0" * 64})
    connection.close()


class PreparationCommandTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        env = {"EIA_API_KEY": SECRET, "TRINITY_S3_BUCKET": "trinity-test-bucket",
               "TRINITY_S3_PREFIX": "success", "TRINITY_S3_REGION": "us-east-1"}
        self.environment = patch.dict(os.environ, env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def run_command(self, mode="success", *, worker=fixture_worker, limits=prepare.Limits(), args=None):
        os.environ["TRINITY_S3_PREFIX"] = mode
        output, errors = io.StringIO(), io.StringIO()
        arguments = args if args is not None else ["--start", "2026-10-01", "--end", "2026-10-03",
                                                  "--output-root", str(self.root)]
        with redirect_stdout(output), redirect_stderr(errors):
            code = prepare.main(arguments, worker=worker, limits=limits)
        self.assertNotIn(SECRET, output.getvalue() + errors.getvalue())
        return code, output.getvalue(), errors.getvalue()

    def version(self):
        return next(path for path in self.root.iterdir() if path.is_dir())

    def test_complete_command_verifies_saved_candidate_and_prints_unpublished(self):
        code, output, errors = self.run_command()
        self.assertEqual((code, errors), (0, ""), errors)
        result = read_json(output)
        self.assertEqual(result["status"], "stored_unpublished")
        self.assertFalse(result["published"])
        self.assertEqual(result["window_kind"], "explicit")
        self.assertEqual(result["warning_count"], 0)
        self.assertFalse(result["approval_required"])
        self.assertEqual((result["requested_start"], result["requested_end"]),
                         ("2026-10-01", "2026-10-03"))
        root = self.version()
        self.assertEqual(read_json((root / prepare.EVIDENCE / "result.json").read_bytes()), result)
        self.assertEqual(sha256((root / "bundle.json").read_bytes()), result["bundle_sha256"])
        evidence = (root / "source-evidence.json").read_bytes()
        self.assertIn(b"unknown_source_field", evidence)
        for path in root.rglob("*.json*"):
            self.assertNotIn(SECRET.encode(), path.read_bytes())
        events = [read_json(line) for line in (root / prepare.EVIDENCE / "journal.jsonl").read_bytes().splitlines()]
        self.assertEqual([item["stage"] for item in events if item["event"] == "started" and "stage" in item],
                         list(prepare.STAGES))
        self.assertEqual(events[-1]["event"], "child_verified")
        remote_paths = [item["storage_path"] for item in read_json((root / "bundle.json").read_bytes())["artifacts"]]
        self.assertIn("evidence/retrieval.jsonl", remote_paths)
        self.assertFalse(any(path.startswith(prepare.EVIDENCE + "/") for path in remote_paths))

    def test_warnings_and_resolved_ambiguous_writes_exit_zero(self):
        for mode in ("warnings", "ambiguous"):
            with self.subTest(mode=mode):
                code, output, errors = self.run_command(mode)
                self.assertEqual((code, errors), (0, ""))
                result = read_json(output)
                self.assertFalse(result["published"])
                self.assertEqual(result["warning_count"], 1 if mode == "warnings" else 0)
                self.assertIs(result["approval_required"], mode == "warnings")

    def test_stage_failures_exit_nonzero_and_preserve_available_evidence(self):
        for mode, stage in (("extraction-failure", "extract:facility"), ("parse-failure", "freeze"),
                            ("validation-failure", "validation"), ("diagnostic-failure", "validation"),
                            ("storage-failure", "storage"), ("read-failure", "storage"), ("collision", "storage"),
                            ("unresolved", "storage"), ("corrupt", "storage")):
            with self.subTest(mode=mode):
                code, output, errors = self.run_command(mode)
                self.assertEqual((code, output), (1, ""))
                failure = read_json(errors)
                self.assertEqual(failure["stage"], stage)
                root = self.root / failure["version_id"]
                self.assertFalse((root / prepare.EVIDENCE / "result.json").exists())
                routes = (root / "evidence/retrieval.jsonl").read_bytes().splitlines()
                self.assertEqual(len(routes), 3)
                if stage == "validation":
                    summaries = list(root.glob("evidence/*/validation.json"))
                    self.assertEqual(len(read_json(summaries[0].read_bytes())["results"]), 16)
                if stage == "freeze":
                    self.assertTrue((root / "source-evidence.json").exists())
                    self.assertFalse((root / "manifest.json").exists())

    def test_cancel_returns_130_and_retains_evidence(self):
        code, output, errors = self.run_command("cancel")
        self.assertEqual((code, output), (130, ""))
        self.assertEqual(read_json(errors)["error_code"], "cancelled")
        self.assertFalse((self.version() / prepare.EVIDENCE / "result.json").exists())

    def test_cancel_between_stages_preserves_manifest_without_validation_success(self):
        code, output, errors = self.run_command("cancel-between-stages")
        self.assertEqual((code, output), (130, ""))
        self.assertEqual(read_json(errors)["stage"], "freeze")
        self.assertTrue((self.version() / "manifest.json").exists())
        self.assertEqual(list(self.version().glob("evidence/*/validation.json")), [])

    def test_missing_sdk_credentials_are_safe_configuration_failure(self):
        code, output, errors = self.run_command("missing-credentials")
        self.assertEqual((code, output), (2, ""))
        self.assertEqual(read_json(errors)["error_code"], "configuration_error")

    def test_sink_failure_retains_the_completed_route_and_no_manifest(self):
        code, output, errors = self.run_command("persistence-failure")
        self.assertEqual((code, output), (1, ""))
        routes = (self.version() / "evidence/retrieval.jsonl").read_bytes().splitlines()
        self.assertEqual(len(routes), 1)
        self.assertEqual(read_json(routes[0])["dataset"], "national")
        self.assertFalse((self.version() / "manifest.json").exists())

    def test_input_and_configuration_reject_before_reservation(self):
        base = ["--output-root", str(self.root)]
        for start, end in (("20261001", "2026-10-03"), ("2026-1-01", "2026-10-03"),
                           ("2026-10-03", "2026-10-01"), ("2025-02-29", "2026-10-01"),
                           ("9999-01-01", "9999-01-02"), (SECRET, "2026-10-03")):
            with self.subTest(start=start):
                code, output, _errors = self.run_command(args=[*base, "--start", start, "--end", end])
                self.assertEqual((code, output), (2, ""))
                self.assertEqual(list(self.root.iterdir()), [])
        for key in ("EIA_API_KEY", "TRINITY_S3_BUCKET", "TRINITY_S3_REGION"):
            with self.subTest(key=key), patch.dict(os.environ, {key: ""}):
                self.assertEqual(self.run_command()[0], 2)
        self.assertEqual(self.run_command(args=["--api-key", SECRET])[0], 2)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_existing_version_and_symlink_output_cannot_be_overwritten(self):
        code, output, _errors = self.run_command()
        self.assertEqual(code, 0)
        result = read_json(output)
        with patch.object(prepare, "uuid4", return_value=result["version_id"]):
            self.assertEqual(self.run_command()[0], 2)
        alias = self.root / "alias"
        alias.symlink_to(self.version(), target_is_directory=True)
        args = ["--start", "2026-10-01", "--end", "2026-10-03", "--output-root", str(alias)]
        self.assertEqual(self.run_command(args=args)[0], 2)

    def test_reservation_rejects_a_replaced_intermediate_directory(self):
        with TemporaryDirectory() as temporary:
            outside = Path(temporary).resolve()
            original = prepare.os.mkdir
            def replace_evidence(name, mode=0o777, *, dir_fd=None):
                original(name, mode=mode, dir_fd=dir_fd)
                if name == "evidence" and dir_fd is not None:
                    os.rename("evidence", "old-evidence", src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
                    os.symlink(str(outside), "evidence", dir_fd=dir_fd)
            with patch.object(prepare.os, "mkdir", side_effect=replace_evidence):
                self.assertEqual(self.run_command()[0], 2)
            self.assertEqual(list(outside.iterdir()), [])

    def test_zero_exit_without_receipt_and_premature_receipt_are_incomplete(self):
        for worker in (empty_worker, bad_receipt_worker, killed_worker):
            with self.subTest(worker=worker.__name__):
                code, output, errors = self.run_command(worker=worker)
                self.assertEqual((code, output), (1, ""))
                root = self.root / read_json(errors)["version_id"]
                self.assertFalse((root / prepare.EVIDENCE / "result.json").exists())

    def test_valid_receipt_with_late_process_exit_is_not_command_success(self):
        code, output, errors = self.run_command(worker=late_exit_worker,
                                               limits=replace(prepare.Limits(), storage=1))
        self.assertEqual((code, output), (1, ""))
        self.assertEqual(read_json(errors)["error_code"], "deadline_exceeded")
        self.assertTrue((self.version() / prepare.EVIDENCE / "receipt.json").exists())
        self.assertFalse((self.version() / prepare.EVIDENCE / "result.json").exists())

    def test_blocked_validation_and_storage_are_killed_and_reaped(self):
        for stage in ("validation", "storage"):
            limits = replace(prepare.Limits(), validation=0.2 if stage == "validation" else 120,
                             storage=0.2 if stage == "storage" else 300, terminate_grace=0.1)
            before = time.monotonic()
            code, output, errors = self.run_command(stage, worker=blocked_worker, limits=limits)
            self.assertEqual((code, output), (1, ""))
            self.assertEqual(read_json(errors)["error_code"], "deadline_exceeded")
            self.assertLess(time.monotonic() - before, 10)
            self.assertEqual(prepare.multiprocessing.active_children(), [])

    def test_overall_deadline_stops_child_even_before_first_stage(self):
        code, output, errors = self.run_command("validation", worker=blocked_worker,
                                               limits=replace(prepare.Limits(), overall=0.1, terminate_grace=0.1))
        self.assertEqual((code, output), (1, ""))
        self.assertEqual(read_json(errors)["error_code"], "deadline_exceeded")
        self.assertEqual(prepare.multiprocessing.active_children(), [])

    def test_parent_sigterm_stops_and_reaps_the_child(self):
        # Send a real signal to the command's parent. The blocked test child
        # ignores terminate, so cleanup must escalate and leave no live child.
        timer = threading.Timer(0.7, lambda: os.kill(os.getpid(), signal.SIGTERM))
        timer.start()
        try:
            code, output, errors = self.run_command("validation", worker=blocked_worker,
                                                   limits=replace(prepare.Limits(), terminate_grace=0.1))
        finally:
            timer.cancel()
            timer.join()
        self.assertEqual((code, output), (130, ""))
        self.assertEqual(read_json(errors)["error_code"], "cancelled")
        self.assertEqual(prepare.multiprocessing.active_children(), [])

    def test_parent_journal_sync_failure_stops_before_acknowledging_more_work(self):
        original = prepare.os.fsync
        def fail_after_launch(descriptor):
            # Fail the first actual stage-event sync, independent of how many
            # directory syncs reservation needs. The child is waiting for ACK.
            for journal in self.root.glob(f"*/{prepare.EVIDENCE}/journal.jsonl"):
                if b'"stage":"extract:national"' in journal.read_bytes():
                    raise OSError(SECRET)
            return original(descriptor)
        with patch.object(prepare.os, "fsync", side_effect=fail_after_launch):
            code, output, errors = self.run_command()
        self.assertEqual((code, output), (1, ""))
        self.assertEqual(prepare.multiprocessing.active_children(), [])
        self.assertFalse((self.version() / prepare.EVIDENCE / "result.json").exists())

    def test_final_result_persistence_failure_cannot_exit_zero(self):
        original = parquet._write_bytes
        def fail(root, path, data):
            if path == f"{prepare.EVIDENCE}/result.json":
                raise OSError(SECRET)
            return original(root, path, data)
        # spawn imports clean modules in the child. This patch affects only
        # the parent's final completion write after successful remote storage.
        with patch.object(parquet, "_write_bytes", side_effect=fail):
            code, output, errors = self.run_command()
        self.assertEqual((code, output), (1, ""))
        self.assertTrue((self.version() / prepare.EVIDENCE / "receipt.json").exists())
        self.assertEqual(read_json(errors)["status"], "incomplete")

    def test_parent_receipt_verification_failure_cannot_exit_zero(self):
        with patch.object(prepare, "_verify_receipt", side_effect=ValueError(SECRET)):
            code, output, errors = self.run_command()
        self.assertEqual((code, output), (1, ""))
        self.assertEqual(read_json(errors)["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
