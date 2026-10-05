"""Build synthetic worker custody around the real preparation evidence formats."""
from pathlib import Path

from preview_fixture import candidate
from test_s3 import MemoryS3
from trinity.adapters.s3 import S3Storage
from trinity.config import S3Settings
from trinity.connector.pipeline import _storage_binding
from trinity.contracts.manifest import canonical_json, sha256


def stored_result(root, *, warnings=True):
    """Keep real saved files; simulate only parent receipt custody and remote I/O.

    This fixture does not claim a new live supervisor run. Supervisor exit and
    termination semantics are covered separately by test_prepare. The writer
    consumes exactly the same final/child bytes and storage bundle here.
    """
    if warnings:
        report, receipt, objects = candidate(root)
    else:
        from trinity.connector.parquet import freeze_files
        from trinity.connector.validate import validate_candidate
        from trinity.connector.pipeline import store_candidate
        from test_parquet import START, END
        from test_validate import records_for, reconciled
        frozen = freeze_files(output_root=Path(root).resolve(),start=START,end=END,
                              retrieval=records_for(reconciled()))
        report = validate_candidate(frozen.root,frozen.manifest_sha256)
        memory = MemoryS3()
        receipt = store_candidate(report,S3Storage(S3Settings('synthetic-bucket','versions','us-east-1'),client=memory))
        objects = {key.split('/',2)[2]:value for key,value in memory.objects.items()}
    result = canonical_json({**_storage_binding(report), 'status':'stored_unpublished',
        'window_kind':'explicit','bundle_sha256':receipt.bundle_sha256,
        'storage_evidence_path':receipt.storage_evidence_path,'artifact_count':len(receipt.artifacts)})
    folder = report.root/'evidence'/'preparation'
    folder.mkdir()
    (folder/'result.json').write_bytes(result)
    (folder/'receipt.json').write_bytes(result)
    client = MemoryS3()
    client.objects.update({f'versions/{report.manifest.version_id}/{path}':raw for path,raw in objects.items()})
    storage = S3Storage(S3Settings('synthetic-bucket','versions','us-east-1'),client=client)
    return report,receipt,objects,storage,sha256(result)
