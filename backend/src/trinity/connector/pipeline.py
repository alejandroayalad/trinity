"""Extract all routes and store validated candidates through trusted adapters.

These are separate library entry points. The preparation command that joins
extraction, freezing, validation and storage belongs to the next slice.
"""

import asyncio
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date
import os
from pathlib import Path
from uuid import UUID, uuid4

import httpx

from trinity.config import ConfigurationError, EIASettings
from trinity.connector.client import EIAClient, EIAClientError, EIAInputError, EIARetrievalCancelled
from trinity.connector.retrieval import RetrievalResult
from trinity.adapters.s3 import MAX_OBJECT_BYTES, S3Storage, StorageError, StoredArtifact
from trinity.connector import parquet
from trinity.connector.validate import CHECKSET, ValidationReport, verify_validation
from trinity.contracts.manifest import canonical_json, read_json, sha256


DATASETS = ("national", "facility", "generator")


async def retrieve_all(
    *, start: date, end: date, page_size: int = 5000, max_pages: int = 1000,
    timeout_seconds: float = 300.0,
    on_result: Callable[[RetrievalResult], None] | None = None,
    settings: EIASettings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[RetrievalResult]:
    """One pool, sequential routes, one final result per route on normal failure.

    A failed route does not stop the other routes. Cancellation records the
    interrupted route and skipped routes, then propagates. A sink failure
    propagates immediately, since saved evidence cannot then be guaranteed.
    """
    results: list[RetrievalResult] = []

    def emit(result: RetrievalResult) -> None:
        results.append(result)
        if on_result is not None:
            on_result(result)

    try:
        client = EIAClient(settings, transport=transport)
    except ConfigurationError:
        for dataset in DATASETS:
            tracker = EIAClient.retrieval_tracker(dataset, start, end)
            emit(RetrievalResult(tracker.finish(
                "failed", error_code="configuration_error",
                error_message="Set EIA_API_KEY to a non-empty value in the process environment.",
            )))
        return results

    async with client:
        for index, dataset in enumerate(DATASETS):
            try:
                collection = await getattr(client, f"fetch_{dataset}")(
                    start=start, end=end, page_size=page_size,
                    max_pages=max_pages, timeout_seconds=timeout_seconds,
                )
            except (EIAClientError, EIAInputError) as error:
                assert error.metadata is not None
                result = RetrievalResult(error.metadata)
            except EIARetrievalCancelled as error:
                emit(RetrievalResult(error.metadata))
                for remaining in DATASETS[index + 1:]:
                    tracker = EIAClient.retrieval_tracker(remaining, start, end)
                    emit(RetrievalResult(tracker.finish(
                        "skipped", error_code="cancelled_before_start",
                        error_message="Not started because extraction was cancelled.",
                    )))
                raise
            else:
                assert collection.metadata is not None
                result = RetrievalResult(collection.metadata, collection)
            emit(result)
    return results


@dataclass(frozen=True)
class StoredCandidate:
    """Return a verified storage receipt, with no publication or approval grant.

    Retain bundle_sha256 outside the bundle it identifies. A later consumer
    must recheck the receipt and objects; a remote prefix alone proves nothing.
    """

    root: Path
    version_id: str
    attempt_id: str
    manifest_sha256: str
    bundle_sha256: str
    artifacts: tuple[StoredArtifact, ...]
    storage_evidence_path: str
    warning_digest: str
    warning_count: int
    approval_required: bool
    published: bool = False


def _storage_binding(report: ValidationReport) -> dict:
    """Bind storage evidence to the completed validation and frozen warnings."""
    return {
        "version_id": report.manifest.version_id, "attempt_id": report.attempt_id,
        "manifest_sha256": report.manifest.digest, "checkset_version": CHECKSET,
        "contract_version": report.manifest.contract_version,
        "requested_start": report.manifest.requested_start,
        "requested_end": report.manifest.requested_end,
        "warning_digest": report.warning_digest, "warning_count": report.warning_count,
        "approval_required": report.approval_required, "published": False,
    }


def _read_storage_file(root: int, path: str) -> bytes:
    """Read at most 64 MiB plus one byte through the safe local file helpers.

    Check size before allocating the body, then bound the read in case a file
    grows after that check. Reject links and special files just as freezing does.
    """
    import stat

    with parquet._parent(root, path) as (parent, name):
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise StorageError("unsafe_local_file")
            if info.st_size > MAX_OBJECT_BYTES:
                raise StorageError("object_too_large")
            data = stream.read(MAX_OBJECT_BYTES + 1)
        if len(data) > MAX_OBJECT_BYTES:
            raise StorageError("object_too_large")
        return data


def _storage_snapshot(root: int) -> tuple[StoredArtifact, ...]:
    """Measure completed candidate evidence before reserving remote storage.

    Execution journals for storage stay local: they change during the upload.
    Validation journals are complete snapshots and travel with their details.
    A prior local bundle blocks a new attempt; this slice has no resume command.
    """
    files = parquet._inventory(root)
    if "bundle.json" in files:
        raise StorageError("storage_already_attempted")
    return tuple(StoredArtifact.from_bytes(path, _read_storage_file(root, path))
                 for path in sorted(files) if not path.startswith("evidence/storage-"))


def _same_local_files(root: int, artifacts: tuple[StoredArtifact, ...]) -> None:
    """Detect mutation since the storage snapshot without replacing identities."""
    expected = {artifact.storage_path for artifact in artifacts}
    actual = {path for path in parquet._inventory(root)
              if not path.startswith("evidence/storage-") and path != "bundle.json"}
    if actual != expected:
        raise StorageError("local_inventory_changed")
    for artifact in artifacts:
        if StoredArtifact.from_bytes(artifact.storage_path, _read_storage_file(
                root, artifact.storage_path)) != artifact:
            raise StorageError("local_artifact_changed")


def _check_snapshot_binding(report: ValidationReport, artifacts: tuple[StoredArtifact, ...]) -> None:
    """Match snapshot hashes to the original validation, not just current disk.

    A file replacement between validation and snapshot measurement must not
    become a new accepted hash. Bind data, source and check evidence directly.
    The complete journal content is separately checked by verify_validation.
    """
    expected = {entry.storage_path: entry.sha256 for entry in report.manifest.entries}
    expected.update({
        "manifest.json": report.manifest.digest,
        "source-evidence.json": report.manifest.source_evidence_sha256,
        f"{report.evidence_path}/validation.json": report.validation_sha256,
        f"{report.evidence_path}/diagnostics.json": report.diagnostics_sha256,
    })
    expected.update({result.details_path: sha256(result.details_json)
                     for result in (*report.results, *report.diagnostics)})
    actual = {artifact.storage_path: artifact.sha256 for artifact in artifacts}
    if any(actual.get(path) != digest for path, digest in expected.items()):
        raise StorageError("snapshot_validation_identity")


def store_candidate(
    report: ValidationReport, storage: S3Storage, *, timeout_seconds: float = 300,
    cancelled: Callable[[], bool] | None = None,
) -> StoredCandidate:
    """Store one locally validated candidate and return a verified receipt.

    Input is a saved-file validation report plus a trusted storage adapter.
    Reserve a local evidence directory. Recheck the report and snapshot all
    candidate files. Reserve the remote version with a fresh random token.
    Upload each snapshot through conditional writes and SHA-256 readback.
    Recheck local inputs, freeze bundle.json, and upload that bundle last.
    Reverify the full remote bundle before durably saving the local receipt.

    The receipt identifies stored, unpublished bytes, including warning-bearing
    candidates. It grants no Admin approval and changes no application state.
    On failure, preserve partial-upload evidence and safe failure details where
    disk writes still work. Never delete remote objects or rewrite local files.
    A local bundle without a verified receipt is not storage completion.
    """
    operation = storage.operation(report.manifest.version_id, timeout_seconds=timeout_seconds,
                                  cancelled=cancelled)
    token = str(uuid4())
    evidence_path = f"evidence/storage-{token}"
    binding = _storage_binding(report)
    reserved_local = False
    try:
        with parquet._directory(report.root) as root:
            # Validate the directory identity before adding evidence to it.
            # Record subsequent failures even if the original data now fails.
            if (report.root.name != report.manifest.version_id
                    or sha256(parquet._read(root, "manifest.json")) != report.manifest.digest):
                raise StorageError("local_identity")
            with parquet._parent(root, evidence_path) as (parent, name):
                os.mkdir(name, mode=0o700, dir_fd=parent)
                reserved_local = True
                os.fsync(parent)
            with parquet._exclusive_file(root, f"{evidence_path}/journal.jsonl") as journal:
                saved_events = []

                def record(event: str, **details) -> None:
                    # Sync after each event, not only at context-manager exit.
                    # A kill during the next upload leaves prior progress intact.
                    data = canonical_json({"event": event, **binding, **details}) + b"\n"
                    journal.write(data)
                    journal.flush()
                    os.fsync(journal.fileno())
                    saved_events.append(data)

                record("started", preparation_token=token)
                with parquet._parent(root, f"{evidence_path}/journal.jsonl") as (parent, _name):
                    os.fsync(parent)
                operation.checkpoint()
                verify_validation(report)
                artifacts = _storage_snapshot(root)
                # Check between snapshot and upload. No changed file can receive
                # a new identity merely because the storage stage read it later.
                verify_validation(report)
                _check_snapshot_binding(report, artifacts)
                _same_local_files(root, artifacts)
                plan = canonical_json({**binding, "artifacts": [asdict(item) for item in artifacts]})
                parquet._write_bytes(root, f"{evidence_path}/plan.json", plan)
                reservation = canonical_json({**binding, "preparation_token": token})
                parquet._write_bytes(root, f"{evidence_path}/reservation.json", reservation)
                reservation_artifact = operation.put_verified("reservation.json", reservation, reservation=True)
                record("reserved", artifact=asdict(reservation_artifact))
                for artifact in artifacts:
                    operation.checkpoint()
                    data = _read_storage_file(root, artifact.storage_path)
                    if StoredArtifact.from_bytes(artifact.storage_path, data) != artifact:
                        raise StorageError("local_artifact_changed")
                    operation.put_verified(artifact.storage_path, data)
                    record("object_verified", artifact=asdict(artifact))

                verify_validation(report)
                _same_local_files(root, artifacts)
                operation.checkpoint()
                all_artifacts = tuple(sorted((*artifacts, reservation_artifact),
                                             key=lambda item: item.storage_path))
                bundle = canonical_json({"bundle_format": 1, **binding,
                                         "artifacts": [asdict(item) for item in all_artifacts]})
                # Check the bundle size before freezing it. All other objects
                # already have measured limits from the initial snapshot.
                bundle_artifact = StoredArtifact.from_bytes("bundle.json", bundle)
                parquet._write_bytes(root, "bundle.json", bundle)
                if _read_storage_file(root, "bundle.json") != bundle:
                    raise StorageError("local_bundle_readback")
                operation.put_verified("bundle.json", bundle)
                record("bundle_verified", artifact=asdict(bundle_artifact))
                # Re-read earlier objects too. An upload acknowledgment or an
                # intact bundle cannot hide a missing or changed member object.
                for artifact in all_artifacts:
                    operation.verify(artifact)
                operation.verify(bundle_artifact)
                verify_validation(report)
                _same_local_files(root, artifacts)
                operation.checkpoint()
                receipt = StoredCandidate(
                    report.root, report.manifest.version_id, report.attempt_id,
                    report.manifest.digest, bundle_artifact.sha256, all_artifacts,
                    evidence_path, report.warning_digest, report.warning_count,
                    report.approval_required,
                )
                result = canonical_json({**binding, "status": "stored_unpublished",
                                         "bundle_sha256": receipt.bundle_sha256,
                                         "artifact_count": len(all_artifacts)})
                parquet._write_bytes(root, f"{evidence_path}/result.json", result)
                if _read_storage_file(root, f"{evidence_path}/result.json") != result:
                    raise StorageError("receipt_readback")
                record("completed", bundle_sha256=receipt.bundle_sha256)
                # Confirm the persisted local receipt inputs as well as S3.
                # A successful write call alone cannot prove intact evidence.
                for path, expected in (
                    (f"{evidence_path}/plan.json", plan),
                    (f"{evidence_path}/reservation.json", reservation),
                    (f"{evidence_path}/journal.jsonl", b"".join(saved_events)),
                    ("bundle.json", bundle),
                ):
                    if _read_storage_file(root, path) != expected:
                        raise StorageError("storage_evidence_readback")
                operation.checkpoint()
                return receipt
    except BaseException as error:
        is_cancel = isinstance(error, (KeyboardInterrupt, asyncio.CancelledError))
        code = ("cancelled" if is_cancel else error.code
                if isinstance(error, StorageError) else "storage_incomplete")
        if reserved_local:
            try:
                with parquet._directory(report.root) as root:
                    parquet._write_bytes(root, f"{evidence_path}/failure.json", canonical_json({
                        **binding, "status": "incomplete", "stage": "storage", "error_code": code,
                    }))
            except Exception:
                pass  # An unavailable disk cannot retain another failure record.
        if is_cancel:
            raise
        raise StorageError(code) from None


def verify_stored_candidate(report: ValidationReport, receipt: StoredCandidate,
                            storage: S3Storage, *, timeout_seconds: float = 300) -> None:
    """Recheck a retained local receipt and every remote bundle object.

    A caller supplies the original validation and storage receipts. Reject
    missing completion, mixed identities, changed bytes or incomplete storage.
    This read-only remote check grants no publication or approval authority.
    """
    try:
        verify_validation(report)
        binding = _storage_binding(report)
        if (receipt.root != report.root or receipt.version_id != report.manifest.version_id
                or receipt.attempt_id != report.attempt_id
                or receipt.manifest_sha256 != report.manifest.digest
                or receipt.warning_digest != report.warning_digest
                or type(receipt.warning_count) is not int
                or receipt.warning_count != report.warning_count
                or receipt.approval_required is not report.approval_required
                or receipt.published is not False):
            raise StorageError("receipt_identity")
        with parquet._directory(report.root) as root:
            files = parquet._inventory(root)
            prefix = receipt.storage_evidence_path
            token = prefix.removeprefix("evidence/storage-")
            if prefix != f"evidence/storage-{str(UUID(token))}":
                raise StorageError("receipt_identity")
            if f"{prefix}/failure.json" in files:
                raise StorageError("storage_incomplete")
            bundle = _read_storage_file(root, "bundle.json")
            expected = canonical_json({"bundle_format": 1, **binding,
                                       "artifacts": [asdict(item) for item in receipt.artifacts]})
            if bundle != expected or sha256(bundle) != receipt.bundle_sha256:
                raise StorageError("bundle_identity")
            # The local plan must describe exactly the saved candidate snapshot.
            # The reservation is the only extra remote object in the bundle.
            plan = read_json(_read_storage_file(root, f"{prefix}/plan.json"))
            reservation = _read_storage_file(root, f"{prefix}/reservation.json")
            if reservation != canonical_json({**binding, "preparation_token": token}):
                raise StorageError("reservation_identity")
            artifacts = tuple(StoredArtifact(**item) for item in plan.pop("artifacts"))
            if canonical_json(plan) != canonical_json(binding):
                raise StorageError("plan_identity")
            all_artifacts = tuple(sorted((*artifacts, StoredArtifact.from_bytes(
                "reservation.json", reservation)), key=lambda item: item.storage_path))
            if all_artifacts != receipt.artifacts:
                raise StorageError("bundle_inventory")
            _check_snapshot_binding(report, artifacts)
            _same_local_files(root, artifacts)
            result = canonical_json({**binding, "status": "stored_unpublished",
                                     "bundle_sha256": receipt.bundle_sha256,
                                     "artifact_count": len(receipt.artifacts)})
            if _read_storage_file(root, f"{prefix}/result.json") != result:
                raise StorageError("receipt_identity")
            events = [read_json(line) for line in _read_storage_file(
                root, f"{prefix}/journal.jsonl").splitlines()]
            bundle_artifact = StoredArtifact.from_bytes("bundle.json", bundle)
            expected_events = [
                {"event": "started", **binding, "preparation_token": token},
                {"event": "reserved", **binding, "artifact": asdict(
                    StoredArtifact.from_bytes("reservation.json", reservation))},
                *({"event": "object_verified", **binding, "artifact": asdict(item)} for item in artifacts),
                {"event": "bundle_verified", **binding, "artifact": asdict(bundle_artifact)},
                {"event": "completed", **binding, "bundle_sha256": receipt.bundle_sha256},
            ]
            if canonical_json(events) != canonical_json(expected_events):
                raise StorageError("storage_incomplete")
            operation = storage.operation(receipt.version_id, timeout_seconds=timeout_seconds)
            for artifact in receipt.artifacts:
                operation.verify(artifact)
            operation.verify(bundle_artifact)
    except StorageError:
        raise
    except Exception:
        raise StorageError("stored_candidate_invalid") from None
