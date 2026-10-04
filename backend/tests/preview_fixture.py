"""Build complete synthetic publication evidence only for disposable acceptance."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import socket
import threading
import time
from uuid import UUID, uuid4

import httpx
import psycopg
import uvicorn

from trinity.auth.schemas import Publication
from trinity.config import S3Settings
from trinity.adapters.s3 import S3Storage
from trinity.connector.parquet import freeze_files
from trinity.connector.pipeline import store_candidate
from trinity.connector.validate import validate_candidate
from trinity.publication.repository import PreviewPublication
from test_parquet import START, END
from test_validate import reconciled, records_for
from test_s3 import MemoryS3


def candidate(root):
    """Use the real producer; only retrieval records and object storage are synthetic."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    rows = reconciled()
    # Missing source percentages and a private facility label exercise diagnostic
    # scoping without changing exact MW reconciliation or daily coverage.
    rows['national'][0]['percentOutage'] = None
    rows['facility'][0]['facilityName'] = None
    rows['generator'][0]['facilityName'] = 'DETAIL_CANARY'
    frozen = freeze_files(output_root=Path(root).resolve(), start=START, end=END,
                          retrieval=records_for(rows))
    report = validate_candidate(frozen.root, frozen.manifest_sha256)
    storage = MemoryS3()
    receipt = store_candidate(report, S3Storage(S3Settings('synthetic-bucket','versions','us-east-1'),client=storage))
    objects = {key.split('/',2)[2]:value for key,value in storage.objects.items()}
    return report, receipt, objects


def publish_fixture(dsn, report, receipt):
    """Atomically seed a verified synthetic version; refuse non-test database names."""
    if '/trinity_test_' not in dsn:
        raise RuntimeError('Disposable database required')
    run, step, approval, event = (uuid4() for _ in range(4))
    version = UUID(report.manifest.version_id)
    with psycopg.connect(dsn) as connection:
        if not connection.execute('SELECT current_database()').fetchone()[0].startswith('trinity_test_'):
            raise RuntimeError('Disposable database required')
        connection.execute("""INSERT INTO refresh_runs(id,trigger_kind,requested_by,request_key,requested_at,
            finished_at,status,settings_revision,policy_snapshot,requested_start,requested_end,window_frozen_at)
            VALUES(%s,'manual','test_admin',%s,now(),now(),'succeeded',1,'{}',%s,%s,now())""",
                           (run,uuid4(),START,END))
        connection.execute("""INSERT INTO refresh_steps(id,run_id,step_seq,stage,work_key,attempt,status,
            execution_fence,finished_at,progress_unit) VALUES(%s,%s,1,'validate','all',1,'succeeded',0,now(),'checks')""",(step,run))
        connection.execute("""INSERT INTO data_versions(id,run_id,status,disposition,approval_required,
            review_warning_count,review_warning_digest,diagnostics_frozen_at,created_at,manifest_frozen_at,
            manifest_sha256,validated_at,validation_step_id,coverage_start,coverage_end,latest_observation_date,
            contract_version,validation_checkset,evidence_bundle_sha256,validation_attempt_id)
            VALUES(%s,%s,'validated','active',%s,%s,%s,now(),now(),now(),%s,now(),%s,%s,%s,%s,
                'trinity-data-v1','trinity-data-v1',%s,%s)""",
                           (version,run,report.approval_required,report.warning_count,report.warning_digest,
                            report.manifest.digest,step,START,END,END,receipt.bundle_sha256,UUID(report.attempt_id)))
        if report.approval_required:
            connection.execute("""INSERT INTO approvals(id,version_id,approved_by,approved_at,
                manifest_sha256,validation_step_id,review_warning_digest) VALUES(%s,%s,'test_admin',now(),%s,%s,%s)""",
                               (approval,version,report.manifest.digest,step,report.warning_digest))
        connection.execute("""INSERT INTO publication_events(id,version_id,published_at,publication_mode,
            approval_id,actor_id,idempotency_key) VALUES(%s,%s,now(),%s,%s,%s,%s)""",
                           (event,version,'approval' if report.approval_required else 'automatic',
                            approval if report.approval_required else None,
                            'test_admin' if report.approval_required else None,uuid4()))
        connection.execute('UPDATE active_publication SET publication_event_id=%s,revision=revision+1',(event,))
    return event, version


@contextmanager
def loopback(app):
    """Serve real HTTP on a kernel-assigned loopback port, with access logs disabled."""
    sock = socket.socket()
    sock.bind(('127.0.0.1',0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app,log_level='critical',access_log=False))
    thread = threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True)
    thread.start()
    try:
        limit = time.monotonic()+5
        while not server.started and thread.is_alive() and time.monotonic()<limit:
            time.sleep(.01)
        if not server.started:
            raise RuntimeError('Test server failed to start')
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=40) as client:
            yield client
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()
        if thread.is_alive():
            raise RuntimeError('Test server did not stop')
