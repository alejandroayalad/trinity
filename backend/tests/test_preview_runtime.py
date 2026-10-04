"""Opt-in PostgreSQL, loopback HTTP and Docker acceptance with synthetic S3 bytes."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import multiprocessing
import os
from pathlib import Path
import signal
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from botocore.exceptions import ClientError
import httpx

from postgres_fixture import PostgresFixture, DSN
from preview_fixture import candidate, publish_fixture, loopback
from preview_runtime_fixture import IMAGE, SOCKET, RuntimeSandbox, cli
from test_preview_unit import codec
from trinity.adapters.postgres import Database
from trinity.config import ApiSettings
from trinity.errors import Problem
from trinity.main import create_app
from trinity.queries import repository
from trinity.queries.preview_schemas import PreviewResponse
from trinity.queries.service import PreviewService, QueryService, QueryDeadline


def crash_owner(args):
    """Kill only this spawned supervisor after Docker has started its owned container."""
    dsn,token,stage,volume,deployment,version,objects = args
    database=Database(ApiSettings(TRINITY_DATABASE_URL=dsn));database.open()
    sandbox=RuntimeSandbox(database,stage,volume=volume,deployment=deployment)
    sandbox.client.add(version,objects)
    sandbox.command='import time; time.sleep(60)'
    sandbox.after_start=lambda _:os.kill(os.getpid(),signal.SIGKILL)
    PreviewService(database,sandbox.execution,codec_factory=codec).execute(token,'national_outages',[])


@unittest.skipUnless(DSN and IMAGE,'Disposable PostgreSQL and matching query image required')
class PreviewRuntimeTests(PostgresFixture,unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.report,self.receipt,self.objects=candidate(self.root/'candidate')
        self.event,self.version=publish_fixture(DSN,self.report,self.receipt)
        self.sandbox=RuntimeSandbox(self.database,self.root/'stage');self.addCleanup(self.sandbox.close)
        self.sandbox.client.add(self.version,self.objects)
        self.previews=PreviewService(self.database,self.sandbox.execution,codec_factory=codec)
        self.queries=QueryService(self.database,self.sandbox.execution)
        self.app=create_app(service=self.service,preview_service=self.previews,query_service=self.queries)
        self.token=self.login('analyst')['Authorization'][7:]

    def execute(self,pairs=(),dataset='national_outages',*,token=None):
        return self.previews.execute(token or self.token,dataset,pairs)

    def test_operator_checker_over_real_http_and_containers(self):
        import io
        import pyarrow.parquet as pq
        from trinity.auth.check import check_persona
        from trinity.auth.preview_check import PreviewFixture
        from trinity.contracts.datasets import DATASETS
        from trinity.connector.validate import diagnostic_identity
        from trinity.publication.repository import read_pinned_publication
        from trinity.queries.preview_schemas import serialize_preview_rows
        with self.database.transaction(QueryDeadline(10),readonly=True) as c:
            publication=read_pinned_publication(c).publication
        expected={}
        for dataset,definition in DATASETS.items():
            # Read expected values from producer bytes, independently of preview execution.
            source=pq.read_table(io.BytesIO(self.objects[f'data/{dataset}.parquet'])).to_pylist()
            source=[row for row in source if dataset=='national' or row['facility']=='001a']
            source=sorted(source,key=lambda row:tuple(row[key] for key in definition.key_fields))[:2]
            expected[definition.table_name]=serialize_preview_rows(dataset,
                [[row[name] for name in definition.schema.names] for row in source])
        # Expected notes come from producer results, not from the endpoint being checked.
        summaries=diagnostic_identity(self.report.diagnostics)[2]
        diagnostics={dataset+'_outages':[
            {'code':note['code'],'scope':dataset,'severity':note['severity'],
             'message':note['message'],'affected_count':str(note['affected_count'])}
            for note in summaries if note['dataset_key']==dataset and note['code']!='D09'
            and note['affected_count']>0] for dataset in DATASETS}
        fixture=PreviewFixture(publication=publication,range={'start':'2026-10-01','end':'2026-10-03'},
                               facility='001a',generator='1',rows=expected,diagnostics=diagnostics)
        with loopback(self.app) as http:
            for role in ('viewer','analyst','admin'):
                check_persona(http,role,self.passwords[role],catalog=True,preview=fixture)
        self.assert_clean()

    def assert_clean(self, outcome='succeeded'):
        rows=self.sql('SELECT * FROM query_reservations ORDER BY created_at')
        self.assertTrue(rows)
        self.assertTrue(all(row['state']=='released' and row['cleanup_complete'] for row in rows))
        if outcome is not None:self.assertEqual(rows[-1]['outcome'],outcome)
        self.assertEqual(self.sandbox.remaining_containers(),[])
        self.assertEqual(list(self.sandbox.stage.iterdir()),[])

    def test_loopback_all_roles_exact_pages_filters_diagnostics_and_sql(self):
        with loopback(self.app) as http:
            for role in ('viewer','analyst','admin'):
                login=http.post('/api/v1/auth/login',json={'username':role,'password':self.passwords[role]})
                headers={'Authorization':'Bearer '+login.json()['access_token']}
                try:
                    for dataset in ('national','facility','generator'):
                        url=f'/api/v1/datasets/{dataset}_outages/preview'
                        before=len(self.sandbox.client.calls)
                        response=http.get(url,headers=headers,params={'limit':'1'})
                        if role=='viewer' and dataset!='national':
                            self.assertEqual(response.status_code,404)
                            self.assertEqual(len(self.sandbox.client.calls),before)
                            continue
                        self.assertEqual(response.status_code,200,response.text)
                        self.assertEqual(response.headers['cache-control'],'no-store')
                        self.assertIn('x-request-id',response.headers)
                        page=PreviewResponse.model_validate_json(response.content)
                        contract=json.loads((Path(__file__).resolve().parents[2]/'docs/openapi.json').read_text())
                        self.assertEqual(set(response.json()),set(contract['components']['schemas']['PreviewResponse']['properties']))
                        self.assertEqual(page.publication.publication_event_id,self.event)
                        self.assertEqual(page.returned_rows,1);self.assertIsNotNone(page.next_cursor)
                        self.assertTrue(all(note.scope==dataset and note.code!='D09' for note in page.diagnostics))
                        if dataset=='national':
                            self.assertNotIn('DETAIL_CANARY',response.text)
                            self.assertEqual([note.code for note in page.diagnostics],['D02'])
                        params={'limit':'1','cursor':page.next_cursor}
                        second=http.get(url,headers=headers,params=params)
                        self.assertEqual(second.status_code,200,second.text)
                        self.assertNotEqual(second.json()['rows'],page.rows)
                        debits=self.sql('SELECT cardinality(admitted_at) AS n FROM analytical_rate_limits WHERE user_id=%s',('test_'+role,))[0]['n']
                        replay=http.get(url,headers=headers,params=params)
                        self.assertEqual(replay.json(),second.json())
                        self.assertEqual(self.sql('SELECT cardinality(admitted_at) AS n FROM analytical_rate_limits WHERE user_id=%s',('test_'+role,))[0]['n'],debits+1)
                        if dataset=='generator':
                            filtered=http.get(url,headers=headers,params={'facility':'001a','generator':'1'})
                            self.assertEqual(filtered.status_code,200,filtered.text)
                            names=[column['name'] for column in filtered.json()['columns']]
                            self.assertEqual(filtered.json()['returned_rows'],3)
                            self.assertTrue(all(row[names.index('facility')]=='001a' for row in filtered.json()['rows']))
                            self.assertTrue(all(row[names.index('generator')]=='1' for row in filtered.json()['rows']))
                    sql=http.post('/api/v1/queries',headers=headers,json={'sql':'SELECT COUNT(*) FROM national_outages'})
                    self.assertEqual(sql.status_code,403 if role=='viewer' else 200,sql.text)
                    if role!='viewer':self.assertEqual(sql.json()['rows'],[['3']])
                finally:http.post('/api/v1/auth/logout',headers=headers,json={})
        self.assert_clean()

    def test_entire_keyset_walk_equals_full_fixture_and_defaults_are_equivalent(self):
        with loopback(self.app) as http:
            headers={'Authorization':'Bearer '+self.token}
            url='/api/v1/datasets/generator_outages/preview'
            params={'limit':'2'};rows=[]
            while True:
                response=http.get(url,headers=headers,params=params)
                self.assertEqual(response.status_code,200,response.text)
                page=response.json();rows.extend(page['rows'])
                if page['next_cursor'] is None:break
                params={'limit':'2','cursor':page['next_cursor'],'start':page['range']['start'],'end':page['range']['end']}
            self.assertEqual(len(rows),6)
            expected=[(day,facility,'1') for day in ('2026-10-01','2026-10-02','2026-10-03')
                      for facility in ('001a','002b')]
            self.assertEqual([tuple(row[:3]) for row in rows],expected)
            self.assertEqual(len({tuple(row[:3]) for row in rows}),6)
            self.assertEqual(rows,sorted(rows,key=lambda row:tuple(str(v).encode() for v in row[:3])))
            missing=http.get(url,headers=headers,params={'facility':'absent','generator':'01'})
            self.assertEqual(missing.status_code,200,missing.text)
            self.assertEqual((missing.json()['rows'],missing.json()['reason']),([], 'not_reported'))
            self.assertIsNone(missing.json()['next_cursor'])
        self.assert_clean()

    def test_publication_change_during_read_keeps_original_then_cursor_restarts(self):
        next_report,next_receipt,next_objects=candidate(self.root/'next')
        changed=False
        def switch(key):
            nonlocal changed
            idle=self.sql("SELECT count(*) AS n FROM pg_stat_activity WHERE datname=current_database() AND state='idle in transaction'")[0]['n']
            self.assertEqual(idle,0)
            if not changed:
                publish_fixture(DSN,next_report,next_receipt)
                self.sandbox.client.add(next_report.manifest.version_id,next_objects)
                changed=True
        self.sandbox.client.before_get=switch
        first=self.execute([('limit','1')])
        self.assertEqual(first.publication.publication_event_id,self.event)
        self.assertTrue(all(str(self.version) in path for path in self.sandbox.client.calls))
        before=len(self.sandbox.client.calls)
        with self.assertRaises(Problem) as caught:self.execute([('limit','1'),('cursor',first.next_cursor)])
        self.assertEqual(caught.exception.code,'publication_changed')
        self.assertEqual(len(self.sandbox.client.calls),before)
        self.assert_clean()

    def test_replay_revocation_and_invalid_cursor_are_checked_before_download(self):
        first=self.execute([('limit','1')]);before=len(self.sandbox.client.calls)
        for cursor in (first.next_cursor[:-1]+'!', 'forged'):
            with self.assertRaises(Problem):self.execute([('limit','1'),('cursor',cursor)])
            self.assertEqual(len(self.sandbox.client.calls),before)
        viewer=self.login('viewer')['Authorization'][7:]
        detail=self.execute([('limit','1')],dataset='facility_outages')
        before=len(self.sandbox.client.calls)
        with self.assertRaises(Problem) as caught:
            self.execute([('limit','1'),('cursor',detail.next_cursor)],dataset='facility_outages',token=viewer)
        self.assertEqual(caught.exception.code,'dataset_not_found')
        self.assertEqual(len(self.sandbox.client.calls),before)
        self.sql("UPDATE local_users SET is_active=false WHERE id='test_analyst'")
        with self.assertRaises(Problem) as caught:self.execute([('limit','1'),('cursor',first.next_cursor)])
        self.assertEqual(caught.exception.status,401)
        self.assertEqual(len(self.sandbox.client.calls),before)
        self.assert_clean()

    def test_storage_retry_counts_one_debit_and_corruption_never_starts(self):
        failures=0;waits=[]
        def temporary(key):
            nonlocal failures
            if failures<2:
                failures+=1
                raise ClientError({'Error':{'Code':'SlowDown'},'ResponseMetadata':{'HTTPStatusCode':503}},'GetObject')
        self.sandbox.client.before_get=temporary;self.sandbox.sleep=waits.append
        self.execute()
        self.assertEqual(waits,[1,3])
        self.assertEqual(self.sql('SELECT cardinality(admitted_at) AS n FROM analytical_rate_limits')[0]['n'],1)
        self.sandbox.client.before_get=None
        key=f'versions/{self.version}/data/national.parquet'
        original=self.sandbox.client.objects[key]
        # A same-size change reaches checksum verification. Added bytes hit the size bound first.
        for damaged,code in ((bytes([original[0]^1])+original[1:],'dependency_unavailable'),
                             (original+b'changed','query_resource_limit')):
            with self.subTest(code=code):
                self.sandbox.client.objects[key]=damaged
                before=len(self.sandbox.created);reads=self.sandbox.client.calls.count(key)
                with self.assertRaises(Problem) as caught:self.execute()
                self.assertEqual(caught.exception.code,code)
                self.assertEqual(self.sandbox.client.calls.count(key)-reads,1)
                self.assertEqual(len(self.sandbox.created),before)
                self.assert_clean(code)

    def test_staging_and_start_timeouts_cleanup_without_resetting_budget(self):
        prepared,execution=self.previews.prepare(self.token,'national_outages',[])
        self.sandbox.client.before_get=lambda _:time.sleep(.1)
        started=time.monotonic()
        with self.assertRaises(Problem) as caught:execution.execute(replace(prepared,deadline=QueryDeadline(.05)))
        self.assertEqual(caught.exception.code,'query_timeout');self.assertEqual(self.sandbox.created,[])
        self.assertLess(time.monotonic()-started,5);self.assert_clean('query_timeout')
        self.sandbox.client.before_get=None
        start_entered=threading.Event()
        def delay_start(_):
            start_entered.set();time.sleep(5.1)
        self.sandbox.before_start=delay_start
        prepared,execution=self.previews.prepare(self.token,'national_outages',[])
        # The startup hook consumes the same shortened test budget, after staging.
        with self.assertRaises(Problem) as caught:execution.execute(replace(prepared,deadline=QueryDeadline(5)))
        self.assertIn(caught.exception.code,('query_timeout','dependency_unavailable'))
        self.assertTrue(start_entered.is_set())
        self.assert_clean(None)

    def test_actual_thirty_second_timeout_confirms_stop_before_release(self):
        self.sandbox.command='import time; time.sleep(60)'
        started=time.monotonic()
        with self.assertRaises(Problem) as caught:self.execute()
        elapsed=time.monotonic()-started
        self.assertEqual(caught.exception.code,'query_timeout')
        self.assertGreaterEqual(elapsed,29);self.assertLess(elapsed,40)
        self.assert_clean('query_timeout')
        print(f'Preview 30-second timeout plus confirmed cleanup: {elapsed:.3f}s')

    def test_oom_and_oversized_output_produce_no_partial_success(self):
        for command in ('x=bytearray(2*1024*1024*1024)', "import sys; sys.stdout.write('x'*(7*1024*1024))"):
            self.sandbox.command=command
            with self.assertRaises(Problem) as caught:self.execute()
            self.assertEqual(caught.exception.code,'query_resource_limit')
            self.assert_clean('query_resource_limit')

    def test_ambiguous_create_is_resolved_by_owned_name_before_release(self):
        self.sandbox.after_create=lambda _:(_ for _ in ()).throw(Problem(503,'dependency_unavailable'))
        with self.assertRaises(Problem):self.execute()
        self.assert_clean('dependency_unavailable')

    def test_unknown_create_absence_never_frees_its_reservation(self):
        from preview_runtime_fixture import BridgeDocker
        with patch.object(BridgeDocker,'create',side_effect=Problem(503,'dependency_unavailable')):
            with self.assertRaises(Problem):self.execute()
        row=self.sql('SELECT * FROM query_reservations')[0]
        self.assertEqual(row['state'],'creating');self.assertFalse(row['cleanup_complete'])
        self.assertEqual(self.sandbox.remaining_containers(),[])
        self.sql("UPDATE query_reservations SET deadline=clock_timestamp()-interval '1 second'")
        recovery=self.sandbox.execution()
        try:
            with self.assertRaises(Problem):recovery.recover_one()
        finally:recovery.close()
        self.assertEqual(self.sql('SELECT state FROM query_reservations')[0]['state'],'creating')

    def test_unknown_removal_retains_capacity_until_real_recovery(self):
        self.sandbox.before_remove=lambda _:(_ for _ in ()).throw(Problem(503,'dependency_unavailable'))
        with self.assertRaises(Problem):self.execute()
        row=self.sql('SELECT * FROM query_reservations ORDER BY created_at')[0]
        self.assertNotEqual(row['state'],'released');self.assertFalse(row['cleanup_complete'])
        self.assertEqual(len(self.sandbox.remaining_containers()),1)
        self.sandbox.before_remove=None
        self.sql("UPDATE query_reservations SET deadline=clock_timestamp()-interval '1 second'")
        recovery=self.sandbox.execution()
        try:self.assertTrue(recovery.recover_one())
        finally:recovery.close()
        self.assert_clean('query_timeout')
        with self.database.transaction(QueryDeadline(10)) as c:
            self.assertFalse(repository.release_removed(c,row,'succeeded'))

    def test_supervisor_sigkill_recovery_and_stale_owner_fencing(self):
        args=(DSN,self.token,str(self.sandbox.stage),self.sandbox.volume,self.sandbox.deployment,
              str(self.version),self.objects)
        process=multiprocessing.get_context('spawn').Process(target=crash_owner,args=(args,))
        process.start();process.join(15)
        if process.is_alive():process.kill();process.join();self.fail('Supervisor did not reach crash point')
        self.assertEqual(process.exitcode,-signal.SIGKILL)
        old=self.sql('SELECT * FROM query_reservations ORDER BY created_at')[0]
        self.assertEqual(old['state'],'starting');self.assertTrue(old['start_intent'])
        self.assertEqual(len(self.sandbox.remaining_containers()),1)
        self.sql("UPDATE query_reservations SET deadline=clock_timestamp()-interval '1 second'")
        started=time.monotonic();recovery=self.sandbox.execution()
        try:
            self.assertTrue(recovery.recover_one())
            with self.assertRaises(Problem):recovery.cleanup(old,'query_timeout')
        finally:recovery.close()
        elapsed=time.monotonic()-started
        self.assertLess(elapsed,10);self.assert_clean('query_timeout')
        print(f'Preview SIGKILL recovery with confirmed cleanup: {elapsed:.3f}s')

    def test_real_http_disconnect_stops_its_container(self):
        self.sandbox.command='import time; time.sleep(60)'
        with loopback(self.app) as http:
            url=http.base_url
            connection=socket.create_connection((url.host,url.port),timeout=5)
            connection.sendall((f'GET /api/v1/datasets/national_outages/preview HTTP/1.1\r\n'
                f'Host: localhost\r\nAuthorization: Bearer {self.token}\r\n\r\n').encode())
            try:
                limit=time.monotonic()+10
                while time.monotonic()<limit:
                    rows=self.sql("SELECT state FROM query_reservations WHERE state='running'")
                    if rows:break
                    time.sleep(.02)
                self.assertTrue(rows)
            finally:connection.close()
            started=time.monotonic();limit=started+10
            while time.monotonic()<limit:
                if self.sql("SELECT count(*) AS n FROM query_reservations WHERE state='released'")[0]['n']==1:break
                time.sleep(.02)
            self.assert_clean('query_timeout')
            print(f'Preview disconnect to confirmed cleanup: {time.monotonic()-started:.3f}s')


    def test_preview_container_cannot_read_hidden_files_network_or_credentials(self):
        from trinity.queries.staging import stage_query
        from trinity.adapters.docker import read_frames
        self.sandbox.command="""import json,os,socket,pyarrow.parquet as pq
checks=[]
for action in (lambda: open('/query/request.json','wb'), lambda: open('/query/sibling-secret','rb'),
               lambda: open('/var/run/docker.sock','rb'),lambda: open('/etc/shadow','rb'),
               lambda: socket.create_connection(('1.1.1.1',53),timeout=.2)):
 try: action();checks.append(False)
 except OSError: checks.append(True)
checks.append(not any(k.startswith(('AWS_','TRINITY_','PGPASSWORD')) for k in os.environ))
checks.append(os.getuid()==10001)
checks.append(set(pq.read_schema('/query/data/part-000000.parquet').names)=={'period','capacity','outage','percentOutage'})
print(json.dumps(checks))
"""
        prepared,execution=self.previews.prepare(self.token,'national_outages',[])
        reservation=prepared.reservation;attached=None
        try:
            reservation=execution.change(reservation,('reserved',),'staging')
            stage_query(self.sandbox.stage,reservation['request_id'],prepared.pinned,prepared.query,
                        execution.reader,prepared.deadline)
            reservation=execution.change(reservation,('staging',),'creating')
            identifier=execution.docker.create(reservation)
            reservation=execution.change(reservation,('creating',),'created',container_id=identifier)
            execution.docker.verify(execution.docker.inspect(identifier),reservation)
            attached,stream=execution.docker.attach(identifier,prepared.deadline)
            reservation=execution.change(reservation,('created',),'starting')
            execution.docker.start(identifier)
            reservation=execution.change(reservation,('starting',),'running')
            self.assertEqual(json.loads(read_frames(stream)),[True]*8)
        finally:
            if attached is not None:attached.close()
            try:execution.cleanup(reservation,'succeeded')
            finally:execution.close()
        self.assert_clean()
