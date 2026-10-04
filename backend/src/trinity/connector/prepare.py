"""Prepare a fixed-window, stored and unpublished Parquet candidate.

The parent owns exclusive reservation, durable stage evidence and the final
command result. A spawned child runs the existing pipeline. The parent can
stop blocked native or network work without relying on cooperative checks.
Imports load no credentials and make no external requests.
"""

import argparse
import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime
import multiprocessing
import os
from pathlib import Path
import signal
import sys
import time
from uuid import UUID, uuid4

from trinity.adapters.s3 import S3Storage
from trinity.config import ConfigurationError, load_eia_settings, load_s3_settings
from trinity.connector import parquet
from trinity.connector.pipeline import PreparationError, _read_storage_file, prepare_candidate
from trinity.contracts.manifest import canonical_json, read_json, read_manifest, sha256


STAGES = ("extract:national", "extract:facility", "extract:generator", "freeze", "validation", "storage")
EVIDENCE = "evidence/preparation"


@dataclass(frozen=True)
class Limits:
    """Bound this preparation command, not future production-refresh workers.

    Tests inject smaller values to exercise actual process termination quickly.
    These limits are not public command options that can disable protection.
    """

    route: float = 300
    freeze: float = 120
    validation: float = 120
    storage: float = 300
    overall: float = 1440
    terminate_grace: float = 5

    def stage_seconds(self, stage: str) -> float:
        """Use the route limit for extraction and startup/transition waits."""
        return getattr(self, stage) if stage in ("freeze", "validation", "storage") else self.route


class _Arguments(argparse.ArgumentParser):
    def error(self, _message):
        # argparse normally echoes rejected arguments, which may contain a
        # credential pasted by mistake. Emit only a fixed input error instead.
        raise ConfigurationError("Invalid preparation arguments; use --help.")


def _date(text: str) -> date:
    """Require canonical YYYY-MM-DD; fromisoformat also accepts compact dates."""
    value = date.fromisoformat(text)
    if value.isoformat() != text:
        raise ValueError
    return value


def _reserve(output_root: Path, start: date, end: date) -> Path:
    """Reserve owner-only version/evidence directories without following links."""
    version = str(uuid4())
    with parquet._directory(output_root) as parent:
        os.mkdir(version, mode=0o700, dir_fd=parent)
        os.fsync(parent)
        root = os.open(version, parquet._DIRECTORY_FLAGS, dir_fd=parent)
        try:
            for path in ("data", "evidence", EVIDENCE):
                # Reopen each parent with O_NOFOLLOW. A replaced evidence
                # directory must not redirect a nested mkdir outside the version.
                with parquet._parent(root, path) as (directory, name):
                    os.mkdir(name, mode=0o700, dir_fd=directory)
                    os.fsync(directory)
            os.fsync(root)
            with parquet._parent(root, EVIDENCE) as (evidence, _name):
                os.fsync(evidence)
            parquet._write_bytes(root, f"{EVIDENCE}/input.json", canonical_json({
                "version_id": version, "requested_start": start, "requested_end": end,
                "window_kind": "explicit", "published": False,
            }))
        finally:
            os.close(root)
    return output_root.absolute() / version


def _send_stage(connection, event: str, stage: str, status: str | None) -> None:
    """Wait for the parent's durable acknowledgment before continuing work."""
    connection.send({"event": event, "stage": stage, "status": status})
    if connection.recv() != "saved":
        raise PreparationError(stage, "supervisor_protocol")


def _run_worker(request: dict, connection, *, transport=None, storage_factory=None) -> None:
    """Run the shared pipeline; allow only trusted in-process test injection."""
    root = request["root"]
    try:
        result = asyncio.run(prepare_candidate(
            root=root, start=request["start"], end=request["end"], settings=request["eia"],
            storage_factory=storage_factory or (lambda: S3Storage(request["s3"])),
            stage_event=lambda event, stage, status: _send_stage(connection, event, stage, status),
            transport=transport,
        ))
        # This is a child receipt, not command completion. Only the parent may
        # write result.json after it confirms child exit and checks these bytes.
        data = canonical_json(result)
        with parquet._directory(root) as descriptor:
            parquet._write_bytes(descriptor, f"{EVIDENCE}/receipt.json", data)
        connection.send({"event": "receipt", "sha256": sha256(data)})
    except (KeyboardInterrupt, asyncio.CancelledError):
        connection.send({"event": "failure", "code": "cancelled"})
        raise SystemExit(130)
    except PreparationError as error:
        code = "configuration_error" if error.code == "configuration_error" else "stage_failed"
        connection.send({"event": "failure", "code": code, "stage": error.stage})
        raise SystemExit(2 if code == "configuration_error" else 1)
    except BaseException:
        connection.send({"event": "failure", "code": "stage_failed"})
        raise SystemExit(1)
    finally:
        connection.close()


def _worker(request: dict, connection) -> None:
    """Suppress library/SDK output; safe evidence comes through the parent."""
    # Redirect OS descriptors as well as Python streams. Native libraries can
    # bypass print(). No raw child traceback or secret-bearing SDK log escapes.
    with open(os.devnull, "w") as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
        sys.stdout = sys.stderr = sink

        def interrupted(_signum, _frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, interrupted)
        _run_worker(request, connection)


def _stop(process, grace: float) -> None:
    """Terminate, then kill if needed; confirm exit before returning failure."""
    if process.is_alive():
        process.terminate()
        process.join(grace)
    if process.is_alive():
        process.kill()
        process.join(grace)
    if process.is_alive():
        raise PreparationError("supervisor", "child_exit_unconfirmed")
    process.join()


def _verify_receipt(root: Path, digest: str, start: date, end: date) -> dict:
    """Match the child receipt to saved manifest, bundle and storage completion.

    The child has verified remote bytes. The parent checks its small retained
    receipt after exit, without starting another unbounded network operation.
    This check alone is not a new proof of remote immutability or publication.
    """
    with parquet._directory(root) as descriptor:
        data = _read_storage_file(descriptor, f"{EVIDENCE}/receipt.json")
        if sha256(data) != digest:
            raise ValueError
        result = read_json(data)
        if (canonical_json(result) != data or result["version_id"] != root.name
                or result["requested_start"] != start.isoformat()
                or result["requested_end"] != end.isoformat()
                or result["published"] is not False or result["window_kind"] != "explicit"
                or result["status"] != "stored_unpublished"
                or result["checkset_version"] != "trinity-data-v1"
                or type(result["warning_count"]) is not int or result["warning_count"] < 0
                or result["approval_required"] is not (result["warning_count"] > 0)):
            raise ValueError
        manifest = read_manifest(_read_storage_file(descriptor, "manifest.json"), result["manifest_sha256"])
        if manifest.version_id != root.name or manifest.requested_start != start or manifest.requested_end != end:
            raise ValueError
        bundle_bytes = _read_storage_file(descriptor, "bundle.json")
        if sha256(bundle_bytes) != result["bundle_sha256"]:
            raise ValueError
        bundle = read_json(bundle_bytes)
        prefix = result["storage_evidence_path"]
        if prefix != f"evidence/storage-{str(UUID(prefix.removeprefix('evidence/storage-')))}":
            raise ValueError
        files = parquet._inventory(descriptor)
        if f"{prefix}/failure.json" in files:
            raise ValueError
        saved = read_json(_read_storage_file(descriptor, f"{prefix}/result.json"))
        # Only these command-specific fields are absent from the storage result.
        if saved != {key: value for key, value in result.items()
                     if key not in ("window_kind", "storage_evidence_path")}:
            raise ValueError
        for key in ("version_id", "attempt_id", "manifest_sha256", "warning_digest", "warning_count",
                    "approval_required", "checkset_version", "contract_version", "requested_start",
                    "requested_end", "published"):
            if bundle[key] != result[key]:
                raise ValueError
        if len(bundle["artifacts"]) != result["artifact_count"]:
            raise ValueError
        journal = _read_storage_file(descriptor, f"{prefix}/journal.jsonl").splitlines()
        if read_json(journal[-1]).get("event") != "completed":
            raise ValueError
        return result


def supervise(request: dict, *, worker=_worker, limits: Limits = Limits()) -> tuple[int, dict]:
    """Run one spawned child with stage/overall deadlines and retained evidence.

    Each stage transition must follow the known sequence. The parent fsyncs
    it before acknowledging it. A late receipt, unexpected exit or missing
    stage never becomes success. Timeout and cancellation stop the child;
    only confirmed zero exit plus verified receipt permits final completion.
    """
    root = request["root"]
    # spawn starts a fresh interpreter instead of copying native-library state
    # with fork. The pipe joins trusted parent/child code, never a public client.
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=worker, args=(request, child))
    stage, index, active = "startup", 0, False
    started = stage_started = time.monotonic()
    receipt_digest = None
    all_success = True
    exit_code, error_code = 1, "preparation_incomplete"
    launched = False
    try:
        with parquet._directory(root) as descriptor:
            with parquet._exclusive_file(descriptor, f"{EVIDENCE}/journal.jsonl") as journal:
                saved_events = []

                def record(event: dict) -> None:
                    data = canonical_json(event) + b"\n"
                    journal.write(data)
                    journal.flush()
                    os.fsync(journal.fileno())
                    saved_events.append(data)

                record({"event": "started", "version_id": root.name})
                with parquet._parent(descriptor, f"{EVIDENCE}/journal.jsonl") as (directory, _name):
                    os.fsync(directory)
                process.start()
                launched = True
                child.close()
                while True:
                    now = time.monotonic()
                    if now - started >= limits.overall or now - stage_started >= limits.stage_seconds(stage):
                        raise PreparationError(stage, "deadline_exceeded")
                    if parent.poll(0.05):
                        try:
                            message = parent.recv()
                        except EOFError:
                            break
                        event = message.get("event")
                        if event == "started":
                            if active or index >= len(STAGES) or message.get("stage") != STAGES[index]:
                                raise PreparationError(stage, "stage_protocol")
                            stage, active = STAGES[index], True
                            stage_started = time.monotonic()
                        elif event == "finished":
                            if not active or message.get("stage") != stage:
                                raise PreparationError(stage, "stage_protocol")
                            if message.get("status") not in ("success", "passed", "failed", "cancelled", "skipped"):
                                raise PreparationError(stage, "stage_protocol")
                            active = False
                            index += 1
                            all_success = all_success and message["status"] in ("success", "passed")
                        elif event == "receipt":
                            if index != len(STAGES) or active or receipt_digest is not None or not all_success:
                                raise PreparationError(stage, "stage_protocol")
                            receipt_digest = message["sha256"]
                            continue
                        elif event == "failure":
                            code = message.get("code")
                            if code not in ("cancelled", "configuration_error"):
                                code = "stage_failed"
                            if message.get("stage") in STAGES:
                                stage = message["stage"]
                            raise PreparationError(stage, code)
                        else:
                            raise PreparationError(stage, "stage_protocol")
                        record(message)
                        parent.send("saved")
                    elif not process.is_alive():
                        break
                process.join(limits.terminate_grace)
                if process.is_alive() or process.exitcode != 0 or receipt_digest is None:
                    raise PreparationError(stage, "child_incomplete")
                now = time.monotonic()
                if now - started >= limits.overall or now - stage_started >= limits.stage_seconds(stage):
                    raise PreparationError(stage, "deadline_exceeded")
                result = _verify_receipt(root, receipt_digest, request["start"], request["end"])
                # The journal records verified child exit, not a promise that
                # an in-flight child will eventually finish successfully.
                record({"event": "child_verified", "receipt_sha256": receipt_digest})
            if _read_storage_file(descriptor, f"{EVIDENCE}/journal.jsonl") != b"".join(saved_events):
                raise PreparationError(stage, "journal_readback")
            now = time.monotonic()
            if now - started >= limits.overall or now - stage_started >= limits.stage_seconds(stage):
                raise PreparationError(stage, "deadline_exceeded")
            final = canonical_json(result)
            parquet._write_bytes(descriptor, f"{EVIDENCE}/result.json", final)
            if _read_storage_file(descriptor, f"{EVIDENCE}/result.json") != final:
                raise PreparationError(stage, "result_readback")
            return 0, result
    except (KeyboardInterrupt, asyncio.CancelledError):
        exit_code, error_code = 130, "cancelled"
    except PreparationError as error:
        error_code = error.code
        exit_code = {"cancelled": 130, "configuration_error": 2}.get(error.code, 1)
    except Exception:
        error_code = "preparation_incomplete"
    finally:
        if launched:
            try:
                _stop(process, limits.terminate_grace)
            except Exception:
                error_code, exit_code = "child_exit_unconfirmed", 1
        parent.close()
        child.close()
    failure = {"version_id": root.name, "status": "incomplete", "stage": stage,
               "error_code": error_code, "published": False,
               "evidence_path": f"{root.name}/{EVIDENCE}"}
    try:
        with parquet._directory(root) as descriptor:
            parquet._write_bytes(descriptor, f"{EVIDENCE}/failure.json", canonical_json(failure))
    except Exception:
        pass  # Failure stays nonzero even when disk persistence is unavailable.
    return exit_code, failure


def main(argv: list[str] | None = None, *, worker=_worker, limits: Limits = Limits()) -> int:
    """Return 0 stored/unpublished, 1 failed, 2 invalid input, or 130 cancelled.

    CLI users supply dates and an existing trusted output root. Load settings
    explicitly, reserve a new version, and supervise the trusted child. Print
    safe JSON only; the existing extraction command remains unchanged.
    """
    parser = _Arguments(description=__doc__)
    parser.add_argument("--start", required=True, type=_date)
    parser.add_argument("--end", required=True, type=_date)
    parser.add_argument("--output-root", required=True, type=Path)
    try:
        args = parser.parse_args(argv)
        if not args.start <= args.end <= datetime.now(UTC).date():
            raise ConfigurationError("Invalid fixed window.")
        eia, s3 = load_eia_settings(), load_s3_settings()
        root = _reserve(args.output_root, args.start, args.end)
    except (ConfigurationError, OSError, ValueError):
        print('{"status":"invalid_input","error_code":"configuration_or_arguments"}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    # Treat SIGTERM like controlled cancellation so the child is also stopped.
    # SIGKILL cannot be handled; an absent final result still means incomplete.
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        code, result = supervise({"root": root, "start": args.start, "end": args.end,
                                  "eia": eia, "s3": s3}, worker=worker, limits=limits)
    finally:
        signal.signal(signal.SIGTERM, previous)
    print(canonical_json(result).decode("ascii"), file=sys.stdout if code == 0 else sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
