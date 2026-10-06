"""Create S3 objects once and verify actual readback bytes.

The connector owns candidate validation and bundle assembly. This adapter
owns conditional requests, finite retries and streamed SHA-256 verification.
It never lists buckets, deletes objects, changes policies or publishes data.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass
import gzip
import hashlib
import math
import re
import time
from uuid import UUID
import zlib

import boto3
from botocore.config import Config
from botocore.exceptions import (
    ClientError, ConnectionClosedError, ConnectTimeoutError, EndpointConnectionError,
    IncompleteReadError, NoCredentialsError, PartialCredentialsError, ReadTimeoutError, ResponseStreamingError,
)

from trinity.config import S3Settings
from trinity.contracts.manifest import safe_relative_path, sha256


MAX_OBJECT_BYTES = 64 * 1024 * 1024
_CHUNK_BYTES = 1024 * 1024
_TEMPORARY = (ConnectionClosedError, ConnectTimeoutError, EndpointConnectionError,
              IncompleteReadError, ReadTimeoutError, ResponseStreamingError)


class StorageError(RuntimeError):
    """Expose a fixed safe code, never SDK exception text or infrastructure URLs."""

    def __init__(self, code: str, *, cause: str | None = None) -> None:
        self.code = code
        # Keep the existing outward code stable. Publication uses the internal
        # cause to distinguish safe retry from permanent or unknown failures.
        self.cause = cause or code
        super().__init__(f"Candidate storage failed: {code}.")


@dataclass(frozen=True)
class StoredArtifact:
    """Bind original file bytes and, for gzip-v1, their exact stored encoding.

    Original hashes still bind validation details and local files. Compressed
    hashes bind the S3 bytes separately, so a different encoding is not silently
    accepted just because it expands to the same JSON. Bundle format 1 has only
    the first three fields; format 2 can also carry the three encoding fields.
    """

    storage_path: str
    sha256: str
    byte_size: int
    encoding: str = "identity"
    stored_sha256: str | None = None
    stored_byte_size: int | None = None

    def __post_init__(self):
        safe_relative_path(self.storage_path)
        pairs = [(self.byte_size, self.sha256)]
        if self.encoding == "gzip-v1":
            if not self.compressible(self.storage_path):
                raise StorageError("object_identity")
            pairs.append((self.stored_byte_size, self.stored_sha256))
        elif (self.encoding != "identity" or self.stored_sha256 is not None
              or self.stored_byte_size is not None):
            raise StorageError("object_identity")
        for size, digest in pairs:
            if (type(size) is not int or size < 0 or type(digest) is not str
                    or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
                raise StorageError("object_identity")
            if size > MAX_OBJECT_BYTES:
                raise StorageError("object_too_large")

    @staticmethod
    def compressible(path: str) -> bool:
        """Keep bootstrap objects and already-compressed Parquet unchanged."""
        return path == "source-evidence.json" or (
            path.startswith("evidence/") and path.endswith((".json", ".jsonl")))

    def to_dict(self) -> dict:
        """Preserve the exact old descriptor shape for unencoded objects."""
        result = asdict(self)
        if self.encoding == "identity":
            for field in ("encoding", "stored_sha256", "stored_byte_size"):
                del result[field]
        return result

    @classmethod
    def from_dict(cls, value: dict, bundle_format: int) -> "StoredArtifact":
        """Reject unknown formats, surplus fields and compressed v1 members."""
        fields = {"storage_path", "sha256", "byte_size"}
        if type(bundle_format) is not int or bundle_format not in (1, 2):
            raise StorageError("object_identity")
        if set(value) != fields and not (
                bundle_format == 2 and value.get("encoding") == "gzip-v1"
                and set(value) == fields | {"encoding", "stored_sha256", "stored_byte_size"}):
            raise StorageError("object_identity")
        return cls(**value)

    @classmethod
    def from_bytes(cls, path: str, data: bytes, *, compress: bool = False) -> "StoredArtifact":
        """Measure original bytes and use gzip only when it saves storage.

        Level 1 keeps compression cheap. A zero timestamp makes repeated
        encoding deterministic, including after an ambiguous upload response.
        """
        safe_relative_path(path)
        if len(data) > MAX_OBJECT_BYTES:
            raise StorageError("object_too_large")
        if compress and cls.compressible(path):
            packed = gzip.compress(data, compresslevel=1, mtime=0)
            if len(packed) < len(data):
                return cls(path, sha256(data), len(data), "gzip-v1", sha256(packed), len(packed))
        return cls(path, sha256(data), len(data))

    def encode(self, data: bytes) -> bytes:
        """Encode only the measured original, never assign changed bytes a new hash."""
        if len(data) != self.byte_size or sha256(data) != self.sha256:
            raise StorageError("object_identity")
        if self.encoding == "identity":
            return data
        packed = gzip.compress(data, compresslevel=1, mtime=0)
        if len(packed) != self.stored_byte_size or sha256(packed) != self.stored_sha256:
            raise StorageError("object_identity")
        return packed


def verified_chunks(response, artifact: StoredArtifact, *, checkpoint, max_bytes=MAX_OBJECT_BYTES):
    """Yield bounded original bytes, checking both identities before completion.

    The trusted bundle selects the encoding, not S3 metadata or magic-byte
    guessing. Limit each decoded chunk and the complete output, even when a
    tiny malicious gzip stream would expand beyond its declared size. Require
    exactly one complete gzip member, with no trailing data. Callers own body
    closure and must not use partial output after any exception.
    """
    size = artifact.stored_byte_size if artifact.encoding == "gzip-v1" else artifact.byte_size
    digest = artifact.stored_sha256 if artifact.encoding == "gzip-v1" else artifact.sha256
    if artifact.byte_size > max_bytes or size > MAX_OBJECT_BYTES:
        raise StorageError("object_too_large")
    if type(response.get("ContentLength")) is not int or response["ContentLength"] != size:
        raise StorageError("object_identity")
    # Adding 16 selects gzip framing, including its trailer/CRC validation.
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if artifact.encoding == "gzip-v1" else None
    wire_hash, original_hash = hashlib.sha256(), hashlib.sha256()
    wire_count = original_count = 0
    while True:
        checkpoint()
        chunk = response["Body"].read(min(_CHUNK_BYTES, size - wire_count + 1))
        checkpoint()
        if not chunk:
            break
        wire_count += len(chunk)
        if wire_count > size:
            raise StorageError("object_identity")
        wire_hash.update(chunk)
        while True:
            checkpoint()
            # Permit one excess byte only to detect a false declared length.
            # Never use an unbounded decompress() or flush() on remote input.
            limit = min(_CHUNK_BYTES, artifact.byte_size - original_count + 1)
            try:
                decoded = decoder.decompress(chunk, limit) if decoder else chunk
            except zlib.error:
                raise StorageError("object_identity") from None
            checkpoint()
            original_count += len(decoded)
            if original_count > artifact.byte_size:
                raise StorageError("object_identity")
            original_hash.update(decoded)
            if decoder and decoder.unused_data:
                raise StorageError("object_identity")
            if decoded:
                yield decoded
            if decoder is None:
                break
            # A small encoded block can produce several bounded output chunks.
            # Drain that block before reading more bytes from the network.
            chunk = decoder.unconsumed_tail
            if not chunk and len(decoded) < limit:
                break
    checkpoint()
    if (wire_count != size or wire_hash.hexdigest() != digest
            or original_count != artifact.byte_size or original_hash.hexdigest() != artifact.sha256
            or decoder is not None and not decoder.eof):
        raise StorageError("object_identity")


def _error_kind(error: Exception) -> str:
    """Classify transport/status failures without copying external messages."""
    if isinstance(error, (NoCredentialsError, PartialCredentialsError)):
        return "configuration"
    if isinstance(error, _TEMPORARY):
        return "temporary"
    if isinstance(error, ClientError):
        status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = error.response.get("Error", {}).get("Code")
        if status == 412 or code == "PreconditionFailed":
            return "exists"
        if status == 403 or code in ("AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"):
            return "denied"
        if code == "NoSuchKey":
            return "missing"
        if status in (409, 429, 500, 502, 503, 504) or code in (
            "RequestTimeout", "SlowDown", "InternalError", "ServiceUnavailable",
            "ConditionalRequestConflict",
        ):
            return "temporary"
    # NoSuchBucket, denied access, credentials and unsupported requests fail
    # immediately. Retrying cannot repair configuration or validation failures.
    return "permanent"


class S3Storage:
    """Use one trusted S3 client and a finite budget per storage operation.

    Supply an injected SDK-shaped client for offline tests. Otherwise create
    the pinned boto3 client explicitly, using its credential provider chain.
    Imports alone never initialize credentials or perform network requests.
    The caller must separately verify private, no-delete storage policies.
    """

    def __init__(self, settings: S3Settings, *, client=None,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.settings = settings
        self.clock, self.sleep = clock, sleep
        # Refresh supplies a durable custody callback. CLI callers leave it
        # unset. A callback failure must stop before any remote side effect.
        self.before_attempt = None
        try:
            self.client = client if client is not None else boto3.client(
                "s3", region_name=settings.region, endpoint_url=settings.endpoint_url,
                config=Config(
                    signature_version="s3v4", connect_timeout=5, read_timeout=10,
                    retries={"total_max_attempts": 1},
                    ignore_configured_endpoint_urls=True,
                ),
            )
        except Exception:
            raise StorageError("storage_configuration") from None

    def operation(self, version_id: str, *, timeout_seconds: float = 300,
                  cancelled: Callable[[], bool] | None = None) -> "StorageOperation":
        """Create a version-bound request budget; do not reserve remotely yet.

        The 300-second ceiling includes writes, readback and retry waits.
        Checks run before/after requests and between streamed chunks. Socket
        timeouts bound SDK waits. Hard process supervision belongs to Step 5.
        """
        try:
            if str(UUID(version_id)) != version_id:
                raise ValueError
            if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
                    or not 0 < timeout_seconds <= 300):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise StorageError("invalid_storage_input") from None
        return StorageOperation(self, version_id, self.clock() + timeout_seconds, cancelled)


class StorageOperation:
    """Bind every request to the same trusted version and deadline."""

    def __init__(self, storage: S3Storage, version: str, deadline: float,
                 cancelled: Callable[[], bool] | None) -> None:
        self.storage, self.version = storage, version
        self.deadline, self.cancelled = deadline, cancelled

    def checkpoint(self) -> None:
        """Fail on cancellation or elapsed time before another side effect."""
        if self.cancelled is not None and self.cancelled():
            raise StorageError("cancelled")
        if self.storage.clock() >= self.deadline:
            raise StorageError("storage_deadline")

    def _key(self, path: str) -> str:
        safe_relative_path(path)
        key = f"{self.storage.settings.prefix}/{self.version}/{path}"
        if len(key.encode("utf-8")) > 1024:
            raise StorageError("object_key_too_long")
        return key

    def _wait(self, attempt: int) -> None:
        """Use A19's one/three-second waits, only inside the remaining budget."""
        self.checkpoint()
        wait = (1, 3)[attempt - 1]
        if self.storage.clock() + wait >= self.deadline:
            raise StorageError("storage_deadline")
        self.storage.sleep(wait)
        self.checkpoint()

    def verify(self, artifact: StoredArtifact, *, allow_missing: bool = False) -> bool:
        """Hash a streamed GET, comparing byte size and SHA-256, never ETag.

        Return False only for NoSuchKey when resolving an ambiguous write.
        Other missing objects, bad bytes and exhausted read retries raise.
        Close each response body even if reading or verification fails.
        """
        key = self._key(artifact.storage_path)
        if not 0 <= artifact.byte_size <= MAX_OBJECT_BYTES:
            raise StorageError("object_too_large")
        for attempt in range(1, 4):
            self.checkpoint()
            body = None
            if self.storage.before_attempt is not None:
                self.storage.before_attempt({"kind": "s3_get", "path": artifact.storage_path, "attempt": attempt})
            try:
                response = self.storage.client.get_object(Bucket=self.storage.settings.bucket, Key=key)
                body = response["Body"]
                self.checkpoint()
                for _chunk in verified_chunks(response, artifact, checkpoint=self.checkpoint):
                    pass
                return True
            except StorageError:
                raise
            except Exception as error:
                kind = _error_kind(error)
                if kind == "configuration":
                    raise StorageError("storage_configuration") from None
                if kind == "missing" and allow_missing:
                    return False
                if kind != "temporary" or attempt == 3:
                    raise StorageError("object_read_failed", cause={
                        "temporary": "storage_temporary", "missing": "evidence_missing",
                        "denied": "storage_denied", "configuration": "storage_configuration",
                    }.get(kind, "unknown_failure")) from None
            finally:
                if body is not None:
                    try:
                        body.close()
                    except Exception:
                        raise StorageError("object_read_failed") from None
            self._wait(attempt)
        raise StorageError("object_read_failed")

    def put_verified(self, path: str, data: bytes, *, reservation: bool = False,
                     artifact: StoredArtifact | None = None) -> StoredArtifact:
        """Create once, then read back; reject conflicts and unresolved outcomes.

        A reservation contains a fresh random token. Its first conflict stops
        before any data upload. Only a prior ambiguous request can resolve a
        reservation by identical readback. Within the reserved prefix, an
        identical existing artifact is safe only after full byte verification.
        Every retry retains IfNoneMatch='*'; no path overwrites an object.
        """
        self.checkpoint()
        artifact = artifact or StoredArtifact.from_bytes(path, data)
        if artifact.storage_path != path:
            raise StorageError("object_identity")
        data = artifact.encode(data)
        self.checkpoint()
        key = self._key(path)
        ambiguous = False
        for attempt in range(1, 4):
            self.checkpoint()
            if self.storage.before_attempt is not None:
                self.storage.before_attempt({"kind": "s3_put", "path": path, "attempt": attempt})
            try:
                self.storage.client.put_object(
                    Bucket=self.storage.settings.bucket, Key=key, Body=data,
                    ContentLength=len(data), IfNoneMatch="*",
                )
                self.checkpoint()
            except StorageError:
                raise
            except Exception as error:
                kind = _error_kind(error)
                if kind == "configuration":
                    raise StorageError("storage_configuration") from None
                if kind == "exists":
                    if reservation and not ambiguous:
                        raise StorageError("prefix_collision") from None
                    self.verify(artifact)
                    return artifact
                if kind != "temporary":
                    raise StorageError("object_write_failed") from None
                ambiguous = True
                # A timeout can arrive after the server has saved the bytes.
                # Read first. Missing bytes permit another conditional write;
                # different or unreadable bytes must never be repaired.
                if self.verify(artifact, allow_missing=True):
                    return artifact
                if attempt == 3:
                    raise StorageError("write_unresolved") from None
                self._wait(attempt)
            else:
                self.verify(artifact)
                return artifact
        raise StorageError("write_unresolved")
