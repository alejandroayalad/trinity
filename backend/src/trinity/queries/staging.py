"""Read and seal exactly the selected files from a pinned published manifest."""

from dataclasses import dataclass
import io
import json
import os
from pathlib import Path
import shutil
import time
from uuid import UUID

import pyarrow.parquet as pq

from trinity.contracts.choices import ChoiceOperation
from trinity.adapters.s3 import MAX_OBJECT_BYTES, StorageError, StoredArtifact, _error_kind, verified_chunks
from trinity.contracts.datasets import DATASETS
from trinity.contracts.manifest import read_manifest, safe_relative_path
from trinity.errors import Problem
from trinity.contracts.queries import request_message, canonical_message, PreviewOperation

MANIFEST_BYTES = 4 * 1024 * 1024
MAX_FILES = 1024
MAX_STAGE_BYTES = 512 * 1024 * 1024


class PublishedReader:
    """Expose GET only through a trusted client and configured object root."""
    def __init__(self, client, settings, *, clock=time.monotonic, sleep=time.sleep):
        self.client, self.settings, self.clock, self.sleep = client, settings, clock, sleep

    def read_into(self, version, path, output, *, deadline, max_bytes, digest, expected_size=None,
                  artifact=None):
        """Read original bytes using only a trusted bundle's encoding descriptor.

        Legacy objects and the bootstrap bundle/manifest stay unencoded. For a
        compressed member, verify the stored bytes and bound decompression to
        its original declared size. Never infer an encoding from S3 metadata.
        Retry temporary failures only, restarting the same bounded output.
        """
        if str(UUID(str(version))) != str(version):
            raise Problem(503, 'dependency_unavailable')
        safe_relative_path(path)
        key = f'{self.settings.prefix}/{version}/{path}'
        if len(key.encode()) > 1024:
            raise Problem(503, 'dependency_unavailable')
        for attempt in range(3):
            deadline.remaining()
            output.seek(0); output.truncate()
            body = None
            try:
                response = self.client.get_object(Bucket=self.settings.bucket, Key=key)
                body = response['Body']
                if type(response.get('ContentLength')) is not int or response['ContentLength'] > max_bytes:
                    raise Problem(503, 'query_resource_limit')
                member = artifact or StoredArtifact(path, digest,
                    response['ContentLength'] if expected_size is None else expected_size)
                if (member.storage_path != path or member.sha256 != digest
                        or expected_size is not None and member.byte_size != expected_size):
                    raise Problem(503, 'dependency_unavailable')
                count = 0
                for chunk in verified_chunks(response, member, checkpoint=deadline.remaining, max_bytes=max_bytes):
                    output.write(chunk)
                    count += len(chunk)
                output.flush(); output.seek(0)
                return count
            except Problem:
                raise
            except StorageError as error:
                code = 'query_resource_limit' if error.code == 'object_too_large' else 'dependency_unavailable'
                raise Problem(503, code) from None
            except Exception as error:
                if _error_kind(error) != 'temporary' or attempt == 2:
                    raise Problem(503, 'dependency_unavailable') from None
            finally:
                if body is not None:
                    try: body.close()
                    except Exception: raise Problem(503, 'dependency_unavailable') from None
            wait = (1, 3)[attempt]
            if deadline.remaining() <= wait:
                raise Problem(504, 'query_timeout')
            self.sleep(wait)
        raise Problem(503, 'dependency_unavailable')


@dataclass(frozen=True)
class StagedQuery:
    """Identify only this generated request directory, never source S3 paths."""
    directory: Path
    request_id: str

    def cleanup(self):
        """Remove only the generated request tree; never follow a symlink root."""
        if self.directory.name != self.request_id or self.directory.is_symlink():
            raise Problem(503, 'dependency_unavailable')
        if self.directory.exists(): shutil.rmtree(self.directory)


def stage_query(root: Path, request_id, pinned, query, reader: PublishedReader, deadline) -> StagedQuery:
    """Verify the manifest and every selected file before sealing the request."""
    request_id = str(UUID(str(request_id)))
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise Problem(503, 'dependency_unavailable')
    staged = StagedQuery(root / request_id, request_id)
    created = False
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        data = io.BytesIO()
        publication = pinned.publication
        if isinstance(query, (PreviewOperation, ChoiceOperation)) and (query.version_id != str(publication.version_id)
                or query.publication_event_id != str(publication.publication_event_id)):
            raise Problem(503, 'dependency_unavailable')
        reader.read_into(publication.version_id, 'manifest.json', data, deadline=deadline,
                         max_bytes=MANIFEST_BYTES, digest=pinned.manifest_sha256)
        manifest = read_manifest(data.getvalue(), pinned.manifest_sha256)
        if (manifest.version_id != str(publication.version_id) or manifest.contract_version != 1
                or pinned.contract_version != 'trinity-data-v1'
                or manifest.requested_start != publication.coverage_start
                or manifest.requested_end != publication.coverage_end):
            raise Problem(503, 'dependency_unavailable')
        selected = [entry for entry in manifest.entries if entry.dataset_key == query.dataset]
        if (not selected or len(selected) > MAX_FILES or sum(e.byte_size for e in selected) > MAX_STAGE_BYTES
                or any(e.byte_size > MAX_OBJECT_BYTES for e in selected)):
            raise Problem(503, 'query_resource_limit')
        os.mkdir(request_id, 0o755, dir_fd=root_fd); created = True
        request_fd = os.open(request_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            os.mkdir('data', 0o755, dir_fd=request_fd)
            data_fd = os.open('data', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=request_fd)
            try:
                for index, entry in enumerate(selected):
                    deadline.remaining()
                    temporary, final = f'part-{index:06d}.partial', f'part-{index:06d}.parquet'
                    descriptor = os.open(temporary, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                         0o600, dir_fd=data_fd)
                    with os.fdopen(descriptor, 'w+b') as stream:
                        reader.read_into(publication.version_id, entry.storage_path, stream, deadline=deadline,
                                         max_bytes=entry.byte_size, digest=entry.sha256, expected_size=entry.byte_size)
                        parquet = pq.ParquetFile(stream)
                        from trinity.contracts.manifest import schema_fingerprint
                        schema = DATASETS[query.dataset].schema
                        if (not parquet.schema_arrow.equals(schema, check_metadata=False)
                                or schema_fingerprint(query.dataset, parquet.schema_arrow) != entry.schema_fingerprint
                                or parquet.metadata.num_rows != entry.row_count):
                            raise Problem(503, 'dependency_unavailable')
                        os.fsync(stream.fileno()); os.fchmod(stream.fileno(), 0o444)
                    os.rename(temporary, final, src_dir_fd=data_fd, dst_dir_fd=data_fd)
            finally:
                os.close(data_fd)
            descriptor = os.open('request.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o444, dir_fd=request_fd)
            with os.fdopen(descriptor, 'wb') as stream:
                message = request_message(request_id, publication.version_id, query)
                stream.write(canonical_message(message))
                stream.flush(); os.fsync(stream.fileno())
        finally:
            os.close(request_fd)
        deadline.remaining()
        return staged
    except Problem:
        if created: staged.cleanup()
        raise
    except Exception:
        if created: staged.cleanup()
        raise Problem(503, 'dependency_unavailable') from None
    finally:
        os.close(root_fd)
