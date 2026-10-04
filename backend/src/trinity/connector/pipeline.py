"""Extract all routes and store validated candidates through trusted adapters.

prepare_candidate joins the library stages. The prepare command supplies its
exclusive version reservation, durable stage journal and process deadlines.
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
    on_route_start: Callable[[str], None] | None = None,
    settings: EIASettings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[RetrievalResult]:
    """Fetch all three routes for an inclusive date window with one shared client.

    The command or caller supplies the window and limits. Load credentials once,
    then collect national, facility, and generator records in that order.
    Return one result per route; failed routes contain evidence but no collection.
    Call on_result after each route so the caller can save its evidence.
    A route failure does not stop other routes. Missing credentials fail all three.
    Cancellation emits interrupted and skipped results, then propagates.
    A callback failure propagates immediately because evidence may not be saved.
    This function does not persist results, normalize numbers, or publish data.
    """
    results: list[RetrievalResult] = []

    def emit(result: RetrievalResult) -> None:
        """Retain a route result and pass it to the caller's optional evidence writer."""
        results.append(result)
        if on_result is not None:
            on_result(result)

    try:
        # One client owns the connection pool for this entire extraction.
        client = EIAClient(settings, transport=transport)
    except ConfigurationError:
        # A missing key prevents every route, so record all three without HTTP calls.
        for dataset in DATASETS:
            tracker = EIAClient.retrieval_tracker(dataset, start, end)
            emit(RetrievalResult(tracker.finish(
                "failed", error_code="configuration_error",
                error_message="Set EIA_API_KEY to a non-empty value in the process environment.",
            )))
        return results

    async with client:
        for index, dataset in enumerate(DATASETS):
            if on_route_start is not None:
                on_route_start(dataset)
            try:
                # Resolve the route method from the fixed internal dataset list.
                # Each collection has its own page budget, deadline, and evidence.
                collection = await getattr(client, f"fetch_{dataset}")(
                    start=start, end=end, page_size=page_size,
                    max_pages=max_pages, timeout_seconds=timeout_seconds,
                )
            except (EIAClientError, EIAInputError) as error:
                # Retain failure evidence and allow the next route to run.
                assert error.metadata is not None
                result = RetrievalResult(error.metadata)
            except EIARetrievalCancelled as error:
                # Cancellation stops the extraction. Record routes never started
                # before passing cancellation back to the command or task owner.
                emit(RetrievalResult(error.metadata))
                for remaining in DATASETS[index + 1:]:
                    tracker = EIAClient.retrieval_tracker(remaining, start, end)
                    emit(RetrievalResult(tracker.finish(
                        "skipped", error_code="cancelled_before_start",
                        error_message="Not started because extraction was cancelled.",
                    )))
                raise
            else:
                # Only a successful route supplies rows for later processing.
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
                 for path in sorted(files) if not _local_execution_file(path))


def _local_execution_file(path: str) -> bool:
    """Keep changing storage and supervisor journals out of frozen uploads."""
    return path.startswith(("evidence/storage-", "evidence/preparation/"))


def _same_local_files(root: int, artifacts: tuple[StoredArtifact, ...]) -> None:
    """Detect mutation since the storage snapshot without replacing identities."""
    expected = {artifact.storage_path for artifact in artifacts}
    actual = {path for path in parquet._inventory(root)
              if not _local_execution_file(path) and path != "bundle.json"}
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


class PreparationError(RuntimeError):
    """Identify the failed stage without copying source or SDK exception text."""

    def __init__(self, stage: str, code: str) -> None:
        self.stage, self.code = stage, code
        super().__init__(f"Preparation failed: {stage}/{code}.")


async def prepare_candidate(
    *, root: Path, start: date, end: date, settings: EIASettings,
    storage_factory: Callable[[], S3Storage],
    stage_event: Callable[[str, str, str | None], None],
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict:
    """Connect extraction, freezing, validation and storage for one new version.

    The command supervisor exclusively reserves root and its data/evidence
    directories. It supplies fixed dates and settings, then enforces hard
    deadlines around this function in a trusted child process. This library
    function alone provides no hard process timeout or command-success marker.

    Persist each completed route before proceeding. Freeze original sanitized
    responses into Parquet, validate those exact files and store the bundle.
    Return a small receipt for the supervisor to verify after child exit.
    Failed stages keep evidence and raise PreparationError. The supervisor
    records failure or interruption; neither path grants publication.
    """
    from trinity.connector.validate import validate_candidate

    stage = "extraction"
    try:
        with parquet._directory(root) as descriptor:
            # This is an internal handoff from the supervisor's exclusive
            # reservation, not a public option to resume or overwrite a version.
            if parquet._inventory(descriptor) - {
                "evidence/preparation/input.json", "evidence/preparation/journal.jsonl",
            }:
                raise PreparationError(stage, "version_not_empty")
            with parquet._exclusive_file(descriptor, "evidence/retrieval.jsonl") as stream:
                with parquet._parent(descriptor, "evidence/retrieval.jsonl") as (parent, _name):
                    os.fsync(parent)

                def route_start(dataset: str) -> None:
                    # nonlocal updates this invocation's outer stage value.
                    # A route failure then retains the correct stage identity.
                    nonlocal stage
                    stage = f"extract:{dataset}"
                    stage_event("started", stage, None)

                def save(result: RetrievalResult) -> None:
                    # The existing connector removes credentials before making
                    # this metadata. Preserve its original response strings.
                    stream.write(canonical_json(result.metadata.to_dict()) + b"\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                    stage_event("finished", f"extract:{result.metadata.dataset}",
                                result.metadata.final_status)

                results = await retrieve_all(
                    start=start, end=end, settings=settings, transport=transport,
                    page_size=5000, max_pages=1000, timeout_seconds=300,
                    on_result=save, on_route_start=route_start,
                )
            if len(results) != 3 or any(item.metadata.final_status != "success" for item in results):
                failed = next((item.metadata.dataset for item in results
                               if item.metadata.final_status != "success"), "national")
                raise PreparationError(f"extract:{failed}", "extraction_failed")

            stage = "freeze"
            stage_event("started", stage, None)
            frozen = parquet._freeze_reserved(descriptor, root, root.name, start, end,
                                               [item.metadata for item in results])
            stage_event("finished", stage, "success")

        stage = "validation"
        stage_event("started", stage, None)
        report = validate_candidate(root, frozen.manifest_sha256)
        stage_event("finished", stage, report.status)
        if report.status != "passed":
            raise PreparationError(stage, "validation_failed")

        stage = "storage"
        stage_event("started", stage, None)
        storage = storage_factory()
        try:
            receipt = store_candidate(report, storage)
        finally:
            # The injected test client may not own sockets. A real boto3 client
            # has close(); release its pool after this command's storage stage.
            close = getattr(storage.client, "close", None)
            if close is not None:
                close()
        stage_event("finished", stage, "success")
        return {
            **_storage_binding(report), "status": "stored_unpublished",
            "window_kind": "explicit", "bundle_sha256": receipt.bundle_sha256,
            "storage_evidence_path": receipt.storage_evidence_path,
            "artifact_count": len(receipt.artifacts),
        }
    except PreparationError:
        raise
    except (KeyboardInterrupt, asyncio.CancelledError):
        raise
    except StorageError as error:
        code = "configuration_error" if error.code == "storage_configuration" else "stage_failed"
        raise PreparationError(stage, code) from None
    except Exception:
        raise PreparationError(stage, "stage_failed") from None
