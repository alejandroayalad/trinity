"""Create S3 objects once and verify actual readback bytes.

The connector owns candidate validation and bundle assembly. This adapter
owns conditional requests, finite retries and streamed SHA-256 verification.
It never lists buckets, deletes objects, changes policies or publishes data.
"""

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import math
import time
from uuid import UUID

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
    """Identify an immutable object relative to one reserved version prefix."""

    storage_path: str
    sha256: str
    byte_size: int

    @classmethod
    def from_bytes(cls, path: str, data: bytes) -> "StoredArtifact":
        """Measure exact bytes and reject unsafe names or the 64 MiB limit."""
        safe_relative_path(path)
        if len(data) > MAX_OBJECT_BYTES:
            raise StorageError("object_too_large")
        return cls(path, sha256(data), len(data))


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
                digest, count = hashlib.sha256(), 0
                while True:
                    self.checkpoint()
                    chunk = body.read(_CHUNK_BYTES)
                    self.checkpoint()
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > artifact.byte_size or count > MAX_OBJECT_BYTES:
                        raise StorageError("object_identity")
                    digest.update(chunk)
                if count != artifact.byte_size or digest.hexdigest() != artifact.sha256:
                    raise StorageError("object_identity")
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

    def put_verified(self, path: str, data: bytes, *, reservation: bool = False) -> StoredArtifact:
        """Create once, then read back; reject conflicts and unresolved outcomes.

        A reservation contains a fresh random token. Its first conflict stops
        before any data upload. Only a prior ambiguous request can resolve a
        reservation by identical readback. Within the reserved prefix, an
        identical existing artifact is safe only after full byte verification.
        Every retry retains IfNoneMatch='*'; no path overwrites an object.
        """
        artifact = StoredArtifact.from_bytes(path, data)
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
