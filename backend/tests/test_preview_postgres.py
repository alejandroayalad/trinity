"""Prove preview authority, publication and mixed admission on disposable PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import multiprocessing
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from postgres_fixture import PostgresFixture, DSN
from preview_fixture import candidate, publish_fixture, loopback
from test_preview_unit import codec
from trinity.adapters.postgres import Database
from trinity.config import ApiSettings
from trinity.errors import Problem
from trinity.main import create_app
from trinity.publication.repository import read_pinned_publication, read_preview_publication
from trinity.queries import repository
from trinity.queries.preview import ResolvedPreview
from trinity.queries.service import PreviewService, QueryService, QueryDeadline


def prepare_in_process(args):
    """Use real services and DB transactions; preparation intentionally starts no runner."""
    dsn,token,kind,valid,deployment = args
    database = Database(ApiSettings(TRINITY_DATABASE_URL=dsn));database.open()
    factory = lambda:SimpleNamespace(deployment_id=deployment,daemon_id='acceptance',close=lambda:None)
    try:
        if kind == 'preview':
            service = PreviewService(database,factory,codec_factory=codec)
            service.prepare(token,'national_outages',[] if valid else [('facility','01')])
        else:
            service = QueryService(database,factory)
            service.prepare(token,'SELECT outage FROM national_outages' if valid else 'SELECT * FROM local_users')
        return 'prepared'
    except Problem as error:
        return error.code
    finally:
        database.close()


@unittest.skipUnless(DSN,'Disposable PostgreSQL required')
class PreviewPostgresTests(PostgresFixture,unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.report,self.receipt,self.objects = candidate(self.root/'candidate')
        self.event,self.version = publish_fixture(DSN,self.report,self.receipt)
        self.factory = Mock(return_value=SimpleNamespace(deployment_id=uuid4(),daemon_id='acceptance',close=lambda:None))
        self.previews = PreviewService(self.database,self.factory,codec_factory=codec)

    def token(self,role='analyst'):
        return self.login(role)['Authorization'][7:]

    def count(self, user='test_analyst'):
        rows = self.sql('SELECT cardinality(admitted_at) AS n FROM analytical_rate_limits WHERE user_id=%s',(user,))
        return rows[0]['n'] if rows else 0

    def prepare(self, token, pairs=(), dataset='national_outages'):
        return self.previews.prepare(token,dataset,pairs)[0]

    def test_migration_pair_constraint_and_real_pin_approval_binding(self):
        with self.database.transaction(QueryDeadline(10),readonly=True) as c:
            pinned = read_preview_publication(c,read_pinned_publication(c))
        self.assertEqual(pinned.evidence_bundle_sha256,self.receipt.bundle_sha256)
        self.assertEqual(pinned.validation_attempt_id,self.report.attempt_id)
        for statement in ("UPDATE data_versions SET evidence_bundle_sha256=NULL",
                          "UPDATE data_versions SET validation_attempt_id=NULL",
                          "UPDATE data_versions SET evidence_bundle_sha256='bad'"):
            with self.assertRaises(psycopg.errors.CheckViolation):self.sql(statement)
        self.sql('UPDATE approvals SET review_warning_digest=%s',('a'*64,))
        with self.assertRaises(Problem) as caught:self.prepare(self.token())
        self.assertEqual(caught.exception.code,'dependency_unavailable');self.factory.assert_not_called()

    def test_loopback_identity_shape_and_post_debit_failures(self):
        with loopback(create_app(service=self.service,preview_service=self.previews)) as http:
            viewer=self.login('viewer');analyst=self.login('analyst')
            url='/api/v1/datasets/national_outages/preview'
            self.assertEqual(http.get(url).status_code,401)
            denied=http.get('/api/v1/datasets/facility_outages/preview?limit=bad',headers=viewer)
            self.assertEqual(denied.status_code,404)
            for query in ('limit=1&limit=2','unknown=x','limit=0','start=2026-02-30','facility='):
                response=http.get(url+'?'+query,headers=analyst)
                self.assertEqual(response.status_code,422)
            self.assertEqual(http.request('GET',url,headers=analyst,content=b'{}').status_code,422)
            self.assertEqual(self.count(),0)
            for query in ('facility=01','cursor=forged','start=2026-10-03&end=2026-10-01'):
                response=http.get(url+'?'+query,headers=analyst)
                self.assertEqual(response.status_code,422)
                self.assertEqual(response.headers['cache-control'],'no-store')
                self.assertEqual(response.headers['content-type'],'application/problem+json')
                self.assertIn('x-request-id',response.headers)
            self.assertEqual(self.count(),3)
            self.factory.assert_not_called()

    def test_each_request_rechecks_role_and_session_before_pin(self):
        token=self.token()
        def changed():
            self.sql("UPDATE local_users SET role='viewer' WHERE id='test_analyst'")
            return codec()
        self.previews.codec_factory=changed
        with self.assertRaises(Problem) as caught:self.prepare(token,dataset='facility_outages')
        self.assertEqual(caught.exception.code,'dataset_not_found')
        self.assertEqual(self.count(),1);self.factory.assert_not_called()
        self.previews.codec_factory=codec
        self.sql("UPDATE local_users SET role='analyst' WHERE id='test_analyst'")
        response=self.client.post('/api/v1/auth/logout',headers={'Authorization':'Bearer '+token},json={})
        self.assertEqual(response.status_code,204)
        with self.assertRaises(Problem) as caught:self.prepare(token)
        self.assertEqual(caught.exception.status,401);self.assertEqual(self.count(),1)

    def test_mixed_services_share_rate_across_processes(self):
        token=self.token();deployment=uuid4()
        args=[(DSN,token,'preview' if i%2 else 'sql',False,deployment) for i in range(40)]
        with multiprocessing.get_context('spawn').Pool(4) as pool:results=pool.map(prepare_in_process,args)
        self.assertEqual(results.count('rate_limited'),10)
        self.assertEqual(sum(result in ('invalid_request','sql_not_allowed') for result in results),30)
        self.assertEqual(self.count(),30)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM query_reservations')[0]['n'],0)

    def test_mixed_capacity_across_processes_and_fenced_release(self):
        tokens={role:self.token(role) for role in ('analyst','admin','viewer')}
        args=[(DSN,tokens[role],'preview' if role=='viewer' or i%2 else 'sql',True,uuid4())
              for role in tokens for i in range(4)]
        with multiprocessing.get_context('spawn').Pool(4) as pool:results=pool.map(prepare_in_process,args)
        self.assertEqual(results.count('prepared'),4)
        self.assertEqual(results.count('rate_limited'),8)
        counts=self.sql("SELECT user_id,count(*) AS n FROM query_reservations WHERE state<>'released' GROUP BY user_id")
        self.assertTrue(all(row['n']<=2 for row in counts))
        row=self.sql('SELECT * FROM query_reservations LIMIT 1')[0]
        with self.database.transaction(QueryDeadline(10)) as c:
            self.assertFalse(repository.release_unlaunched(c,row|{'owner_token':uuid4()},'query_failed'))
        self.assertEqual(self.sql("SELECT count(*) AS n FROM query_reservations WHERE state<>'released'")[0]['n'],4)

    def test_exact_rolling_boundary_then_preview_and_sql_each_debit_once(self):
        token=self.token()
        self.sql("INSERT INTO analytical_rate_limits(user_id,last_time) VALUES('test_analyst',clock_timestamp()+interval '1 hour')")
        moment=self.sql('SELECT last_time FROM analytical_rate_limits')[0]['last_time']
        self.sql('UPDATE analytical_rate_limits SET admitted_at=%s',([moment-timedelta(seconds=60)]*30,))
        with self.assertRaises(Problem):self.prepare(token,[('facility','01')])
        self.assertEqual(self.count(),1)
        queries=QueryService(self.database,self.factory)
        with self.assertRaises(Problem):queries.prepare(token,'SELECT * FROM local_users')
        self.assertEqual(self.count(),2)
        self.sql('UPDATE analytical_rate_limits SET admitted_at=%s',([moment]*30,))
        with self.assertRaises(Problem) as caught:self.prepare(token)
        self.assertEqual(caught.exception.retry_after,60);self.assertEqual(self.count(),30)

    def test_snapshot_survives_independent_pointer_change(self):
        token=self.token();pinned=threading.Event();changed=threading.Event()
        original=read_pinned_publication
        def pause(connection):
            result=original(connection);pinned.set()
            if not changed.wait(5):raise RuntimeError('Race synchronization failed')
            return result
        with patch('trinity.queries.service.read_pinned_publication',side_effect=pause):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future=executor.submit(self.prepare,token)
                self.assertTrue(pinned.wait(5))
                self.sql('UPDATE active_publication SET publication_event_id=NULL')
                changed.set();prepared=future.result(timeout=10)
        self.assertEqual(prepared.pinned.publication.publication_event_id,self.event)
        self.assertEqual(prepared.pinned.evidence_bundle_sha256,self.receipt.bundle_sha256)
        request=ResolvedPreview('national',self.report.manifest.requested_start,self.report.manifest.requested_end)
        cursor=codec().encode(request,self.event,('2026-10-01',))
        with self.assertRaises(Problem) as caught:self.prepare(token,[('cursor',cursor)])
        self.assertEqual(caught.exception.code,'publication_changed')

    def test_missing_provenance_signing_or_admission_fail_closed(self):
        token=self.token()
        self.sql('UPDATE data_versions SET evidence_bundle_sha256=NULL,validation_attempt_id=NULL')
        with self.assertRaises(Problem) as caught:self.prepare(token)
        self.assertEqual(caught.exception.code,'dependency_unavailable');self.factory.assert_not_called()
        self.sql('UPDATE data_versions SET evidence_bundle_sha256=%s,validation_attempt_id=%s',
                 (self.receipt.bundle_sha256,self.report.attempt_id))
        unconfigured=PreviewService(self.database,self.factory)
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(Problem):unconfigured.prepare(token,'national_outages',[])
        self.assertEqual(self.count(),2);self.factory.assert_not_called()
        self.previews.codec_factory=codec
        self.sql('DELETE FROM query_admission')
        try:
            with self.assertRaises(Problem) as caught:self.prepare(token)
            self.assertEqual(caught.exception.code,'dependency_unavailable')
            self.assertEqual(self.sql('SELECT count(*) AS n FROM query_reservations')[0]['n'],0)
        finally:self.sql('INSERT INTO query_admission(id) VALUES(1)')

    def test_missing_runner_configuration_retains_debit_without_capacity(self):
        from trinity.queries.config import preview_execution_factory
        service=PreviewService(self.database,lambda:preview_execution_factory(self.database,enabled=True),
                               codec_factory=codec)
        token=self.token()
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(Problem) as caught:service.prepare(token,'national_outages',[])
        self.assertEqual(caught.exception.code,'dependency_unavailable');self.assertEqual(self.count(),1)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM query_reservations')[0]['n'],0)

    def test_database_outage_reaches_no_configuration_or_storage(self):
        database=Database(ApiSettings(TRINITY_DATABASE_URL='postgresql://nobody@/trinity_test_absent?host=/tmp/trinity-absent-step4'))
        database.open()
        try:
            service=PreviewService(database,self.factory,codec_factory=codec)
            with self.assertRaises(Problem) as caught:service.prepare('x'*43,'national_outages',[])
            self.assertEqual(caught.exception.code,'auth_unavailable');self.factory.assert_not_called()
        finally:database.close()
