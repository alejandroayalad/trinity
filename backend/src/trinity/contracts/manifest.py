"""Define canonical identities for local, unpublished candidate files.

Canonical JSON has one byte representation for the same value. Hash these
bytes with SHA-256. Keep each digest outside the body that it identifies.
This module checks manifest structure. It does not read analytical files.
"""

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
import hashlib
import json
import re
from uuid import UUID

import pyarrow as pa

from trinity.contracts.datasets import DATASETS


class ManifestError(ValueError):
    """Report an identity error without including paths or source values."""


def sha256(data: bytes) -> str:
    """Return the lowercase SHA-256 identity of the supplied bytes."""
    return hashlib.sha256(data).hexdigest()


def _json_value(value):
    """Convert supported values without float conversion or decimal rounding."""
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is date:
        return value.isoformat()
    if isinstance(value, Decimal):
        # Formatting uses six places. Compare with the input before accepting
        # it: 1.0000000 fits, but 1.0000001 must not become 1.000000.
        if not value.is_finite():
            raise ManifestError("invalid_decimal")
        text = format(value, ".6f")
        if Decimal(text) != value:
            raise ManifestError("decimal_scale")
        return text
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(type(key) is str for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    # In particular, reject floats, including NaN and infinity. Their use in
    # an identity could conceal a prior loss of decimal precision.
    raise ManifestError("unsupported_json_value")


def canonical_json(value) -> bytes:
    """Encode supported values as sorted, compact ASCII JSON with no newline."""
    return json.dumps(
        _json_value(value), ensure_ascii=True, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    """Reject duplicate JSON keys instead of silently keeping the last value."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError("duplicate_json_key")
        result[key] = value
    return result


def _invalid_constant(_text: str):
    """Reject JSON extensions such as NaN instead of accepting nonfinite data."""
    raise ManifestError("invalid_json_number")


def read_json(data: bytes | str):
    """Read strict JSON; preserve numbers in original source-response JSON.

    Source responses can contain numeric unknown fields. The canonical encoder
    rejects floats in identities, but this reader must retain source evidence.
    """
    try:
        return json.loads(
            data, object_pairs_hook=_unique_object, parse_constant=_invalid_constant,
        )
    except (ValueError, UnicodeError, TypeError):
        raise ManifestError("invalid_json") from None


def safe_relative_path(path: str) -> tuple[str, ...]:
    """Return path segments only for normalized relative file paths.

    Do not normalize unsafe input into a valid path. Reject URLs, Windows
    paths, empty segments, traversal and control characters before file access.
    """
    if (type(path) is not str or not path or "\\" in path or ":" in path
            or any(ord(char) < 32 or ord(char) == 127 for char in path)):
        raise ManifestError("unsafe_path")
    parts = tuple(path.split("/"))
    if any(part in ("", ".", "..") for part in parts):
        raise ManifestError("unsafe_path")
    return parts


def _digest(value: str) -> None:
    """Require the 64 lowercase hexadecimal digits of a SHA-256 digest."""
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ManifestError("invalid_digest")


def schema_fingerprint(dataset: str, schema: pa.Schema) -> str:
    """Hash ordered fields, types and nullability; ignore writer metadata."""
    if dataset not in DATASETS:
        raise ManifestError("unknown_dataset")
    types = {pa.date32(): "date32", pa.string(): "string",
             pa.decimal128(24, 6): "decimal(24,6)"}
    fields = []
    for column in schema:
        if column.type not in types:
            raise ManifestError("unsupported_schema_type")
        fields.append({"name": column.name, "type": types[column.type],
                       "nullable": column.nullable})
    return sha256(canonical_json({"schema_format": 1, "dataset_key": dataset,
                                  "fields": fields}))


@dataclass(frozen=True)
class FileEntry:
    """Hold the identity and measurements of one saved analytical file."""

    dataset_key: str
    storage_path: str
    sha256: str
    schema_fingerprint: str
    byte_size: int
    row_count: int
    min_period: date
    max_period: date


@dataclass(frozen=True)
class Manifest:
    """Describe all three datasets and bind their original saved evidence.

    Construction rejects unsafe paths, missing datasets and invalid bounds.
    Frozen fields and a tuple of frozen entries prevent identity changes in
    memory. They do not prevent another process from changing files on disk.
    """

    version_id: str
    requested_start: date
    requested_end: date
    source_evidence_sha256: str
    entries: tuple[FileEntry, ...]
    manifest_format: int = 1
    contract_version: int = 1

    def __post_init__(self) -> None:
        try:
            if str(UUID(self.version_id)) != self.version_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ManifestError("invalid_version_id") from None
        if (type(self.manifest_format) is not int or self.manifest_format != 1
                or type(self.contract_version) is not int or self.contract_version != 1):
            raise ManifestError("unsupported_format")
        if (type(self.requested_start) is not date or type(self.requested_end) is not date
                or self.requested_start > self.requested_end):
            raise ManifestError("invalid_window")
        _digest(self.source_evidence_sha256)
        entries = tuple(self.entries)
        paths = set()
        for entry in entries:
            if not isinstance(entry, FileEntry) or entry.dataset_key not in DATASETS:
                raise ManifestError("unknown_dataset")
            parts = safe_relative_path(entry.storage_path)
            if (len(parts) != 2 or parts[0] != "data" or not parts[1].endswith(".parquet")
                    or entry.storage_path in paths):
                raise ManifestError("invalid_data_path")
            paths.add(entry.storage_path)
            _digest(entry.sha256)
            _digest(entry.schema_fingerprint)
            # bool is a subclass of int in Python. Require the exact int type
            # so True cannot stand in for a measured row count or byte size.
            if (type(entry.row_count) is not int or entry.row_count <= 0
                    or type(entry.byte_size) is not int or entry.byte_size <= 0):
                raise ManifestError("invalid_file_count")
            if (type(entry.min_period) is not date or type(entry.max_period) is not date
                    or not self.requested_start <= entry.min_period
                    <= entry.max_period <= self.requested_end):
                raise ManifestError("invalid_file_bounds")
        if {entry.dataset_key for entry in entries} != set(DATASETS):
            raise ManifestError("incomplete_dataset_set")
        # A frozen dataclass permits this constructor-only assignment.
        # Normalize entry order, so caller order does not change the digest.
        object.__setattr__(self, "entries", tuple(sorted(
            entries, key=lambda entry: (entry.dataset_key, entry.storage_path),
        )))

    def to_bytes(self) -> bytes:
        """Return the canonical manifest body, without its own digest."""
        return canonical_json(asdict(self))

    @property
    def digest(self) -> str:
        """Identify the entire canonical manifest body."""
        return sha256(self.to_bytes())


def read_manifest(data: bytes, expected_sha256: str) -> Manifest:
    """Reject changed, noncanonical, duplicate-key or unsupported manifests.

    The caller supplies the previously retained digest. Reading a digest
    computed from the current file would not detect a replaced manifest.
    """
    _digest(expected_sha256)
    if sha256(data) != expected_sha256:
        raise ManifestError("manifest_checksum")
    try:
        body = read_json(data)
        body["requested_start"] = date.fromisoformat(body["requested_start"])
        body["requested_end"] = date.fromisoformat(body["requested_end"])
        entries = []
        for item in body["entries"]:
            item["min_period"] = date.fromisoformat(item["min_period"])
            item["max_period"] = date.fromisoformat(item["max_period"])
            entries.append(FileEntry(**item))
        body["entries"] = tuple(entries)
        manifest = Manifest(**body)
        if manifest.to_bytes() != data:
            raise ManifestError("noncanonical_manifest")
        return manifest
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ManifestError("invalid_manifest") from None
