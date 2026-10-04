"""Prove query admission and identity ordering on disposable PostgreSQL."""

from datetime import timedelta
import multiprocessing
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from fastapi.testclient import TestClient
from postgres_fixture import PostgresFixture, DSN
from trinity.main import create_app
from trinity.errors import Problem
from trinity.publication.repository import read_pinned_publication
from trinity.queries import repository
from trinity.queries.service import QueryService, QueryDeadline
from trinity.queries.runtime.sql_policy import validate_query


def rate_attempt(dsn):
    with psycopg.connect(dsn,row_factory=dict_row) as connection:
        return repository.reserve_rate(connection,'test_analyst') is None


@unittest.skipUnless(DSN, 'Disposable PostgreSQL required')
class QueryPostgresTests(PostgresFixture, unittest.TestCase):
    def setUp(self):
        self.sql('''TRUNCATE query_reservations,analytical_rate_limits,failure_warnings,refresh_control,
            active_publication,publication_events,approvals,data_versions,refresh_steps,refresh_runs,
            shared_settings,local_sessions,local_users,auth_login_limits RESTART IDENTITY''')
        for role in self.passwords:
            self.sql('INSERT INTO local_users(id,username,password_hash,role) VALUES(%s,%s,%s,%s)',
                     ('test_'+role,role,self.hashes[role],role))
        for table in ('shared_settings','active_publication','refresh_control'):
            self.sql(f'INSERT INTO {table}(id) VALUES(1)')
        self.context = TestClient(create_app(service=self.service)); self.client = self.context.__enter__()
        self.factory = Mock(return_value=SimpleNamespace(deployment_id=uuid4(),daemon_id='synthetic',close=lambda:None))
        self.policy = Mock(side_effect=lambda sql,**kw:validate_query(sql))
        self.queries = QueryService(self.database,self.factory,policy=self.policy)

    def token(self, role): return self.login(role)['Authorization'][7:]

    def test_viewer_denial_precedes_policy_rate_and_configuration(self):
        with self.assertRaises(Problem) as caught: self.queries.prepare(self.token('viewer'),'SELECT 1')
        self.assertEqual(caught.exception.code,'forbidden')
        self.policy.assert_not_called();self.factory.assert_not_called()
        self.assertEqual(self.sql('SELECT count(*) AS n FROM analytical_rate_limits')[0]['n'],0)

    def test_invalid_sql_precedes_no_publication_and_debits_remain(self):
        token = self.token('analyst')
        for sql,code in [('SELECT * FROM local_users','sql_not_allowed'),('SELECT outage FROM national_outages','data_unavailable')]:
            with self.assertRaises(Problem) as caught: self.queries.prepare(token,sql)
            self.assertEqual(caught.exception.code,code)
        self.assertEqual(self.sql('SELECT cardinality(admitted_at) AS n FROM analytical_rate_limits')[0]['n'],2)
        self.factory.assert_not_called()

    def test_role_change_during_policy_is_denied_at_second_snapshot(self):
        self.publish(); token=self.token('analyst')
        def policy(sql,**kw):
            self.sql("UPDATE local_users SET role='viewer' WHERE id='test_analyst'")
            return validate_query(sql)
        self.queries.policy=policy
        with self.assertRaises(Problem) as caught:self.queries.prepare(token,'SELECT outage FROM national_outages')
        self.assertEqual(caught.exception.code,'forbidden');self.factory.assert_not_called()

    def test_real_processes_share_thirty_attempt_limit(self):
        with multiprocessing.get_context('spawn').Pool(4) as pool:
            results=pool.map(rate_attempt,[DSN]*40)
        self.assertEqual(sum(results),30)
        self.assertEqual(self.sql('SELECT cardinality(admitted_at) AS n FROM analytical_rate_limits')[0]['n'],30)

    def test_exact_rolling_boundary_and_clock_regression(self):
        self.sql("INSERT INTO analytical_rate_limits(user_id,last_time) VALUES('test_analyst',clock_timestamp()+interval '1 hour')")
        moment=self.sql('SELECT last_time FROM analytical_rate_limits')[0]['last_time']
        self.sql("UPDATE analytical_rate_limits SET admitted_at=%s",([moment-timedelta(seconds=60)]*30,))
        with self.database.transaction(QueryDeadline(30)) as c:self.assertIsNone(repository.reserve_rate(c,'test_analyst'))
        row=self.sql('SELECT * FROM analytical_rate_limits')[0]
        self.assertEqual(row['admitted_at'],[moment]);self.assertEqual(row['last_time'],moment)
        self.sql('UPDATE analytical_rate_limits SET admitted_at=%s',([moment]*30,))
        with self.database.transaction(QueryDeadline(30)) as c:self.assertEqual(repository.reserve_rate(c,'test_analyst'),60)
        self.assertEqual(self.sql('SELECT admitted_at FROM analytical_rate_limits')[0]['admitted_at'],[moment]*30)

    def test_capacity_limits_expiry_and_wrong_owner_never_release(self):
        self.publish();token=self.token('analyst')
        first,_=self.queries.prepare(token,'SELECT outage FROM national_outages')
        self.queries.prepare(token,'SELECT outage FROM national_outages')
        with self.assertRaises(Problem) as caught:self.queries.prepare(token,'SELECT outage FROM national_outages')
        self.assertEqual(caught.exception.code,'rate_limited')
        bad={**first.reservation,'owner_token':uuid4()}
        with self.database.transaction(QueryDeadline(30)) as c:self.assertFalse(repository.release_unlaunched(c,bad,'query_failed'))
        self.sql("UPDATE query_reservations SET deadline=clock_timestamp()-interval '1 second'")
        with self.assertRaises(Problem):self.queries.prepare(token,'SELECT outage FROM national_outages')
        admin=self.token('admin')
        self.queries.prepare(admin,'SELECT outage FROM national_outages');self.queries.prepare(admin,'SELECT outage FROM national_outages')
        self.assertEqual(self.sql("SELECT count(*) AS n FROM query_reservations WHERE state<>'released'")[0]['n'],4)

    def test_publication_pin_survives_pointer_change(self):
        old_event,old_version=self.publish()
        prepared,_=self.queries.prepare(self.token('analyst'),'SELECT outage FROM national_outages')
        new_event,new_version=self.publish()
        self.assertNotEqual(old_version,new_version)
        self.assertEqual(prepared.pinned.publication.publication_event_id,old_event)
        self.assertEqual(prepared.reservation['version_id'],old_version)

    def test_http_viewer_invalid_body_and_policy_denials_are_safe(self):
        with TestClient(create_app(service=self.service,query_service=self.queries)) as client:
            viewer=self.login('viewer');analyst=self.login('analyst')
            response=client.post('/api/v1/queries',headers=viewer,json={'sql':'SELECT outage FROM national_outages'})
            self.assertEqual(response.status_code,403);self.policy.assert_not_called();self.factory.assert_not_called()
            for body in ({'sql':' '},{'sql':123},{'sql':'SELECT 1','extra':True}):
                self.assertEqual(client.post('/api/v1/queries',headers=analyst,json=body).status_code,422)
            self.assertEqual(self.sql('SELECT count(*) AS n FROM analytical_rate_limits')[0]['n'],0)
            response=client.post('/api/v1/queries',headers=analyst,json={'sql':'SELECT * FROM private_marker'})
            self.assertEqual(response.status_code,422);self.assertEqual(response.json()['code'],'sql_not_allowed')
            self.assertNotIn('private_marker',response.text);self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertIn('x-request-id',response.headers)

    @unittest.skipUnless(os.environ.get('TRINITY_TEST_QUERY_IMAGE'),'Disposable query image required')
    def test_loopback_http_real_database_supervisor_and_query_container(self):
        from pathlib import Path
        import socket,subprocess,tempfile,threading,time
        import httpx,uvicorn
        from trinity.adapters.docker import Docker
        from trinity.queries.client import QueryExecution
        from trinity.queries.staging import PublishedReader
        from trinity.queries.schemas import QueryResponse
        from test_sql_staging import bundle,Client
        from test_sql_containers import DOCKER,SOCKET,IMAGE
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);stage=root/'stage';stage.mkdir()
            pin,objects=bundle(root/'source')
            _,version=self.publish()
            # Bind the synthetic immutable manifest to the actual DB publication.
            import json
            from trinity.contracts.manifest import canonical_json,sha256
            manifest=json.loads(objects['manifest.json']);manifest['version_id']=str(version)
            objects['manifest.json']=canonical_json(manifest)
            self.sql("UPDATE data_versions SET manifest_sha256=%s,coverage_start='2025-01-01',coverage_end='2025-01-03',latest_observation_date='2025-01-03' WHERE id=%s",
                     (sha256(objects['manifest.json']),version))
            volume='trinity-sql-http-'+uuid4().hex
            def cli(*args):return subprocess.check_output([DOCKER,*args],stderr=subprocess.DEVNULL,text=True).strip()
            cli('volume','create',volume)
            client=Client(objects);deployment=uuid4()
            class BridgeDocker(Docker):
                def create(inner,reservation):
                    # Test-only copy bridges native API paths to the daemon volume.
                    helper=cli('create','--entrypoint','/bin/true','--user','0','--mount',f'type=volume,src={volume},dst=/staging',IMAGE)
                    try:cli('cp',str(stage)+'/.',helper+':/staging')
                    finally:cli('rm',helper)
                    return super().create(reservation)
            factory=lambda:QueryExecution(self.database,BridgeDocker(SOCKET,IMAGE,volume),
                        PublishedReader(client,SimpleNamespace(bucket='test',prefix='versions')),stage,deployment)
            queries=QueryService(self.database,factory)
            app=create_app(service=self.service,query_service=queries)
            sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            server=uvicorn.Server(uvicorn.Config(app,log_level='critical',access_log=False))
            thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
            try:
                limit=time.monotonic()+5
                while not server.started and time.monotonic()<limit:time.sleep(.02)
                self.assertTrue(server.started)
                with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=35) as http:
                    for role in ('viewer','analyst','admin'):
                        token=http.post('/api/v1/auth/login',json={'username':role,'password':self.passwords[role]}).json()['access_token']
                        response=http.post('/api/v1/queries',headers={'Authorization':'Bearer '+token},
                            json={'sql':'SELECT COUNT(*), SUM(outage) FROM national_outages'})
                        if role=='viewer':
                            self.assertEqual(response.status_code,403);self.assertEqual(client.calls,[])
                        else:
                            self.assertEqual(response.status_code,200,response.text)
                            result=QueryResponse.model_validate_json(response.content)
                            self.assertEqual(result.rows,[['6','12.000000']])
                            self.assertEqual(result.publication.version_id,version)
                            self.assertEqual(response.headers['cache-control'],'no-store')
                self.assertEqual(self.sql("SELECT count(*) AS n FROM query_reservations WHERE state='released' AND cleanup_complete")[0]['n'],2)
                self.assertEqual(list(stage.iterdir()),[])
            finally:
                server.should_exit=True;thread.join(10);sock.close()
                # Test labels limit cleanup to this unique deployment on failure.
                ids=cli('ps','-aq','--filter',f'label=trinity.deployment={deployment}').split()
                for identifier in ids:cli('rm','-f',identifier)
                cli('volume','rm',volume)

    @unittest.skipUnless(os.environ.get('TRINITY_TEST_QUERY_IMAGE'),'Disposable query image required')
    def test_expired_running_container_recovery_fences_and_releases(self):
        import subprocess,tempfile
        from pathlib import Path
        from trinity.adapters.docker import Docker
        from trinity.queries.client import QueryExecution
        from test_sql_containers import DOCKER,SOCKET,IMAGE
        self.publish();prepared,_=self.queries.prepare(self.token('analyst'),'SELECT outage FROM national_outages')
        reservation=prepared.reservation
        volume='trinity-sql-recovery-'+uuid4().hex
        def cli(*args):return subprocess.check_output([DOCKER,*args],stderr=subprocess.DEVNULL,text=True).strip()
        cli('volume','create',volume)
        docker=Docker(SOCKET,IMAGE,volume)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory=root/str(reservation['request_id']);directory.mkdir()
            helper=cli('create','--entrypoint','/bin/true','--user','0','--mount',f'type=volume,src={volume},dst=/staging',IMAGE)
            try:cli('cp',str(root)+'/.',helper+':/staging')
            finally:cli('rm',helper)
            execution=QueryExecution(self.database,docker,None,root,reservation['deployment_id'])
            self.sql('UPDATE query_reservations SET daemon_id=%s WHERE request_id=%s',(docker.daemon_id,reservation['request_id']))
            original=docker.call
            def call(method,path,**kw):
                if path.startswith('/containers/create?'):kw['body']['Cmd']=['-c','import time; time.sleep(60)']
                return original(method,path,**kw)
            docker.call=call;identifier=None
            try:
                reservation=execution.change(reservation,('reserved',),'creating')
                identifier=docker.create(reservation)
                reservation=execution.change(reservation,('creating',),'created',container_id=identifier)
                reservation=execution.change(reservation,('created',),'starting');docker.start(identifier)
                reservation=execution.change(reservation,('starting',),'running')
                self.sql("UPDATE query_reservations SET deadline=clock_timestamp()-interval '1 second'")
                self.assertTrue(execution.recover_one())
                self.assertIsNone(docker.inspect(identifier));self.assertFalse(directory.exists())
                row=self.sql('SELECT * FROM query_reservations')[0]
                self.assertEqual(row['state'],'released');self.assertEqual(row['generation'],2)
                self.assertFalse(execution.recover_one())
                with self.database.transaction(QueryDeadline(10)) as connection:
                    self.assertFalse(repository.release_removed(connection,reservation,'succeeded'))
            finally:
                if identifier:docker.remove_stopped(identifier,reservation)
                docker.client.close();cli('volume','rm',volume)

    def test_multiple_processes_share_the_global_capacity_lock(self):
        self.publish()
        with multiprocessing.get_context('spawn').Pool(4) as pool:
            results=pool.map(capacity_attempt,[(DSN,user) for user in ('test_analyst','test_admin','test_viewer') for _ in range(4)])
        self.assertEqual(sum(results),4)
        counts=self.sql("SELECT user_id,count(*) AS n FROM query_reservations WHERE state<>'released' GROUP BY user_id")
        self.assertTrue(all(r['n']<=2 for r in counts))


def capacity_attempt(args):
    dsn,user=args
    with psycopg.connect(dsn,row_factory=dict_row) as connection:
        pinned=read_pinned_publication(connection)
        return repository.reserve_capacity(connection,user,pinned,uuid4(),'synthetic',30) is not None
