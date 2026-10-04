"""Freeze local Parquet files and their evidence for later validation.

Use freeze_files with sanitized RetrievalMetadata from the existing connector.
Use inspect_frozen_files to detect changes against a retained manifest digest.
Neither function creates validation results, storage uploads or publication.
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
import io
import os
from pathlib import Path
import stat
from uuid import UUID, uuid4

import pyarrow as pa
import pyarrow.parquet as pq

from trinity.connector.normalize import NormalizationError, normalize_row
from trinity.connector.retrieval import RetrievalMetadata
from trinity.contracts.datasets import DATASETS
from trinity.contracts.manifest import (
    FileEntry, Manifest, ManifestError, canonical_json, read_json, read_manifest,
    safe_relative_path, schema_fingerprint, sha256,
)


# Register later-stage sidecars without creating them here. Their presence
# does not prove validation or readiness. All analytical files belong in data/.
SIDECARS = frozenset({
    "source-evidence.json", "manifest.json", "failure.json",
    "validation.json", "diagnostics.json", "bundle.json",
})
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


class FreezeError(RuntimeError):
    """Expose a safe code and any reserved version, never an external error."""

    def __init__(self, code: str, version_id: str | None = None) -> None:
        self.code = code
        self.version_id = version_id
        super().__init__(f"File freeze failed: {code}.")


@dataclass(frozen=True)
class FrozenFiles:
    """Return local file identities; this result grants no readiness status."""

    root: Path
    manifest: Manifest
    manifest_sha256: str


# @contextmanager lets callers use `with`. The code before yield opens a
# resource. The finally block closes it after the caller finishes or fails.
@contextmanager
def _directory(path: Path) -> Iterator[int]:
    """Open an existing directory without following any symlink component."""
    # A file descriptor is an open operating-system handle. Relative operations
    # below stay attached to that directory even if its path is later renamed.
    # Walk from / instead of resolving symlinks into apparently safe paths.
    absolute = path.absolute()
    descriptor = os.open(absolute.anchor, _DIRECTORY_FLAGS)
    try:
        for part in absolute.parts[1:]:
            if part in (".", ".."):
                raise ManifestError("unsafe_path")
            child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def _parent(root: int, relative: str) -> Iterator[tuple[int, str]]:
    """Check a relative path and open its parent without following symlinks."""
    parts = safe_relative_path(relative)
    descriptor = os.dup(root)
    try:
        for part in parts[:-1]:
            child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor, parts[-1]
    finally:
        os.close(descriptor)


def _read(root: int, relative: str) -> bytes:
    """Read one regular file through the checked directory handle."""
    with _parent(root, relative) as (parent, name):
        # O_NONBLOCK prevents a substituted pipe from blocking open().
        # fstat checks the actual opened object, not an earlier path lookup.
        descriptor = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent,
        )
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ManifestError("not_regular_file")
            return stream.read()


@contextmanager
def _exclusive_file(root: int, relative: str):
    """Create owner-only bytes once; sync the file and its directory on success."""
    with _parent(root, relative) as (parent, name):
        # O_EXCL makes creation atomic: two writers cannot both create a name.
        # Do not use an existence check followed by an overwriting open().
        descriptor = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=parent,
        )
        with os.fdopen(descriptor, "wb") as stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(parent)


def _write_bytes(root: int, relative: str, data: bytes) -> None:
    """Save a sidecar exclusively and finish its durable write before return."""
    with _exclusive_file(root, relative) as stream:
        stream.write(data)


def _measure(dataset: str, path: str, data: bytes) -> tuple[FileEntry, pa.Table]:
    """Measure a reopened file, including its saved schema and actual rows."""
    # Hash and parse the same bytes. Separate path reads could observe two
    # different files if a process replaced the file between operations.
    table = pq.ParquetFile(io.BytesIO(data)).read()
    expected = DATASETS[dataset].schema
    if not table.schema.equals(expected, check_metadata=False):
        raise ManifestError("saved_schema")
    if table.num_rows == 0:
        raise ManifestError("empty_dataset")
    for column in expected:
        if not column.nullable and table[column.name].null_count:
            raise ManifestError("required_null")
    periods = table["period"].to_pylist()
    entry = FileEntry(
        dataset_key=dataset, storage_path=path, sha256=sha256(data),
        schema_fingerprint=schema_fingerprint(dataset, table.schema),
        byte_size=len(data), row_count=table.num_rows,
        min_period=min(periods), max_period=max(periods),
    )
    return entry, table


def _source_rows(record: dict, start: date, end: date) -> list[dict]:
    """Derive rows from saved successful responses, keeping duplicates intact."""
    if (record["final_status"] != "success"
            or record["requested_start"] != start.isoformat()
            or record["requested_end"] != end.isoformat()):
        raise ManifestError("source_window_or_status")
    rows = []
    for attempt in record["attempts"]:
        body = attempt["sanitized_response"]
        if body is not None:
            if sha256(body.encode("utf-8")) != attempt["response_sha256"]:
                raise ManifestError("source_response_checksum")
        # Failed HTTP attempts remain evidence but must not become data rows.
        # Full exhaustion, frequency and count proof belongs to V01/V02 later.
        if (attempt["http_status"] != 200 or attempt["error_code"] is not None
                or attempt["api_status"] != "no_error_reported"):
            continue
        payload = read_json(body)
        data = payload["response"]["data"]
        if not isinstance(data, list):
            raise ManifestError("source_rows")
        rows.extend(data)
    return rows


def freeze_files(
    *, output_root: Path, start: date, end: date,
    retrieval: Sequence[RetrievalMetadata], version_id: str | None = None,
) -> FrozenFiles:
    """Save three datasets from original sanitized response evidence.

    The caller supplies existing connector metadata, valid fixed date bounds,
    and a trusted existing output directory. The connector must already have
    removed credentials. This function does not load keys or sanitize raw HTTP.

    Reserve a new UUID directory. Save the original response strings and route
    metadata before parsing rows from those saved bytes. Sort rows by daily
    key without deduplication. Write exact typed Parquet, reopen each file,
    and freeze a manifest with measured identities and the evidence checksum.

    Return FrozenFiles only after durable writes and an integrity recheck.
    Raise FreezeError on failure. Retain existing evidence and write a safe
    failure record when the disk permits. Do not repair or reuse a version.
    Partial files or a manifest alone never establish publication readiness.
    Coverage, reconciliation, diagnostics and validation attempts are Step 3.
    """
    version = str(uuid4()) if version_id is None else version_id
    try:
        if str(UUID(version)) != version:
            raise ValueError
        if type(start) is not date or type(end) is not date or start > end:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise FreezeError("invalid_input") from None

    root_path = Path(output_root).absolute() / version
    reserved = False
    try:
        with _directory(Path(output_root)) as parent:
            try:
                os.mkdir(version, mode=0o700, dir_fd=parent)
            except FileExistsError:
                raise FreezeError("version_collision", version) from None
            reserved = True
            os.fsync(parent)
            root = os.open(version, _DIRECTORY_FLAGS, dir_fd=parent)
            try:
                for name in ("data", "evidence"):
                    os.mkdir(name, mode=0o700, dir_fd=root)
                os.fsync(root)
                return _freeze_reserved(root, root_path, version, start, end, retrieval)
            finally:
                os.close(root)
    except FreezeError:
        raise
    except Exception:
        # Do not emit raw filesystem or Arrow errors. They can contain paths
        # or rejected values. No result means this stage did not complete.
        raise FreezeError("file_io", version if reserved else None) from None


def _freeze_reserved(
    root: int, root_path: Path, version: str, start: date, end: date,
    retrieval: Sequence[RetrievalMetadata],
) -> FrozenFiles:
    """Complete one newly reserved directory; retain failures without repair."""
    stage = "source_evidence"
    try:
        # sanitized_response is a string, not a reconstructed JSON object.
        # Its original numeric spelling and unknown fields remain untouched.
        records = [record.to_dict() for record in retrieval]
        evidence = canonical_json({"evidence_format": 1, "routes": records})
        _write_bytes(root, "source-evidence.json", evidence)
        saved_evidence = _read(root, "source-evidence.json")
        if saved_evidence != evidence:
            raise ManifestError("source_evidence_checksum")
        records = read_json(saved_evidence)["routes"]
        names = [record["dataset"] for record in records]
        if len(names) != len(DATASETS) or set(names) != set(DATASETS):
            raise ManifestError("source_dataset_set")

        stage = "parquet"
        entries = []
        for record in records:
            dataset = record["dataset"]
            definition = DATASETS[dataset]
            rows = [normalize_row(dataset, row).values
                    for row in _source_rows(record, start, end)]
            # list.sort() keeps every row, including identical daily keys.
            # V03 will reject duplicates later. Removing them here loses proof.
            rows.sort(key=lambda row: tuple(row[key] for key in definition.key_fields))
            table = pa.Table.from_pylist(rows, schema=definition.schema)
            path = f"data/{dataset}.parquet"
            # A failed write can leave partial bytes under this reserved name.
            # Only the later manifest declares final files. Never reuse this
            # version to overwrite a partial file or create a repaired result.
            with _exclusive_file(root, path) as stream:
                pq.write_table(
                    table, stream, version="2.6", compression="snappy",
                    store_schema=True, row_group_size=50_000,
                )
            entry, saved = _measure(dataset, path, _read(root, path))
            # Compare exact values after the saved-file conversion. Decimal
            # equality ignores insignificant zeros, but not changed digits.
            if saved.to_pylist() != rows:
                raise ManifestError("round_trip_values")
            entries.append(entry)

        stage = "manifest"
        manifest = Manifest(version, start, end, sha256(saved_evidence), tuple(entries))
        _check_files(root, manifest)
        _write_bytes(root, "manifest.json", manifest.to_bytes())
        read_manifest(_read(root, "manifest.json"), manifest.digest)
        return FrozenFiles(root_path, manifest, manifest.digest)
    except Exception as error:
        # Persist only known codes. Preserve lexical source values in the
        # evidence file, never in exception text or the failure summary.
        if isinstance(error, NormalizationError):
            code = error.code
        elif isinstance(error, ManifestError):
            code = str(error)
        else:
            code = "freeze_failed"
        failure = {"stage": stage, "code": code, "version_id": version,
                   "status": "failed"}
        if isinstance(error, NormalizationError):
            failure["field_name"] = error.field_name
        try:
            _write_bytes(root, "failure.json", canonical_json(failure))
        except Exception:
            # An unavailable disk cannot promise a new failure record.
            # The caller still receives failure and no successful result.
            pass
        raise FreezeError(code, version) from None


def _inventory(root: int, prefix: str = "") -> set[str]:
    """List only regular files/directories; reject links and special files."""
    files = set()
    for name in os.listdir(root):
        relative = prefix + name
        safe_relative_path(relative)
        mode = os.stat(name, dir_fd=root, follow_symlinks=False).st_mode
        if stat.S_ISDIR(mode):
            if relative not in ("data", "evidence") and not relative.startswith("evidence/"):
                raise ManifestError("unexpected_directory")
            child = os.open(name, _DIRECTORY_FLAGS, dir_fd=root)
            try:
                files.update(_inventory(child, relative + "/"))
            finally:
                os.close(child)
        elif stat.S_ISREG(mode):
            files.add(relative)
        else:
            raise ManifestError("unsafe_file")
    return files


def _check_files(root: int, manifest: Manifest) -> None:
    """Check identities of saved files; do not create V08 validation results."""
    expected = {entry.storage_path for entry in manifest.entries}
    files = _inventory(root)
    # Later stages can add only registered sidecars and JSON evidence files.
    # An extra Parquet file anywhere in the version cannot become invisible.
    for path in files - expected:
        if path in SIDECARS:
            continue
        if path.startswith("evidence/") and path.endswith((".json", ".jsonl")):
            continue
        raise ManifestError("unexpected_file")
    if "failure.json" in files:
        raise ManifestError("failed_freeze")
    if not expected <= files:
        raise ManifestError("missing_file")
    evidence = _read(root, "source-evidence.json")
    if sha256(evidence) != manifest.source_evidence_sha256:
        raise ManifestError("source_evidence_checksum")
    for entry in manifest.entries:
        actual, _table = _measure(entry.dataset_key, entry.storage_path,
                                  _read(root, entry.storage_path))
        if actual != entry:
            raise ManifestError("file_identity")


def inspect_frozen_files(root: Path, expected_sha256: str) -> Manifest:
    """Reopen a frozen version and reject changed files or evidence.

    Supply the original manifest digest. Return its verified file description,
    not a validation attempt or readiness decision. Raise FreezeError for any
    unsafe path, missing file, changed identity or incomplete failed freeze.
    """
    try:
        with _directory(Path(root)) as descriptor:
            manifest = read_manifest(_read(descriptor, "manifest.json"), expected_sha256)
            if Path(root).name != manifest.version_id:
                raise ManifestError("version_directory")
            _check_files(descriptor, manifest)
            return manifest
    except Exception:
        raise FreezeError("artifact_integrity") from None
