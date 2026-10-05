"""Seed preparation inputs only; use real registration and publication code."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4
from psycopg.types.json import Jsonb
from postgres_fixture import PostgresFixture, DSN
from refresh_fixture import stored_result
from test_refresh_postgres import RefreshPostgresTests
from trinity.refresh.registration import CandidateRegistration
from trinity.workers.publication import PublicationWorker

class PublicationFixture(PostgresFixture):
    """Keep synthetic storage and real immutable registered database evidence."""
    reserve = RefreshPostgresTests.reserve
    register = RefreshPostgresTests.register

    def setUp(self):
        super().setUp()
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.writer=CandidateRegistration(self.database)
        self.admin=self.login('admin')
        self.new_candidate()

    def new_candidate(self, warnings=False):
        """Reserve and register without inserting any publication effect."""
        self.report,self.receipt,self.objects,self.storage,self.digest=stored_result(self.root,warnings=warnings)
        self.run,self.step=uuid4(),uuid4()
        self.version=UUID(self.report.manifest.version_id)
        self.reserve()
        lock=self.root/f'{self.run}.lock';lock.touch(mode=0o600)
        self.sql('UPDATE refresh_runs SET worker_execution_ref=%s WHERE id=%s',
            (Jsonb({'host':socket.gethostname(),'lock_inode':lock.stat().st_ino,
                    'version_id':str(self.version),'receipt_sha256':self.digest}),self.run))
        self.register()
        self.worker=PublicationWorker(self.database,self.root,lambda:self.storage)
        return self.version

    def payload(self):
        return self.sql("SELECT payload FROM job_outbox WHERE run_id=%s AND job_kind='publish_version'",(self.run,))[0]['payload']

    def command(self, action, *, headers=None, key=None, etag=None, body=None):
        revision=self.sql('SELECT revision FROM data_versions WHERE id=%s',(self.version,))[0]['revision']
        path = 'approval' if action=='approve' else action
        return self.client.post(f'/api/v1/candidates/{self.version}/{path}',json={} if body is None else body,
            headers={**(self.admin if headers is None else headers),'Idempotency-Key':key or str(uuid4()),
                     'If-Match':etag or f'"candidate-{revision}"'})

    def row(self):
        return self.sql('SELECT * FROM refresh_runs WHERE id=%s',(self.run,))[0]

    def operator(self,*args, overrides=None):
        """Invoke the executable with no EIA, S3, AWS or Redis environment."""
        env={k:v for k,v in os.environ.items() if not k.startswith(('TRINITY_','EIA_','AWS_'))}
        env.update(TRINITY_DATABASE_URL=DSN,TRINITY_REFRESH_ROOT=str(self.root))
        env.update(overrides or {})
        completed=subprocess.run([sys.executable,'-m','trinity.workers','publication-recover',
            '--run-id',str(self.run),*args],env=env,capture_output=True,text=True,timeout=20)
        return completed.returncode,json.loads(completed.stdout)

    def expire(self):
        self.sql("UPDATE refresh_runs SET lease_until=now()-interval '1 second' WHERE id=%s",(self.run,))
