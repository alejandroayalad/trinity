"""Opt-in real PostgreSQL and HTTP acceptance for the local-auth slice."""

from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import multiprocessing
from contextlib import contextmanager
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import httpx
import psycopg
from psycopg.rows import dict_row

from trinity.adapters.postgres import Database, Deadline
from trinity.auth import repository
from trinity.auth.check import check_persona
from trinity.auth.passwords import hash_password
from trinity.auth.permissions import Principal
from trinity.auth.seed import SeedError, seed_personas
from trinity.auth.service import AuthService
from trinity.config import ApiSettings
from trinity.errors import Problem
from trinity.main import create_app

DSN = os.environ.get("TRINITY_TEST_DATABASE_URL")
BACKEND = Path(__file__).resolve().parents[1]


def reserve_in_process(dsn):
    """Exercise shared counters from a separate API-like process."""
    database = Database(ApiSettings(TRINITY_DATABASE_URL=dsn))
    database.open()
    try:
        with database.transaction(Deadline()) as connection:
            return repository.reserve_login(connection, 'viewer', 'process-peer')
    finally:
        database.close()


@unittest.skipUnless(DSN, "Use tests/run_local_auth_checks.py for disposable PostgreSQL acceptance")
class PostgresAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DSN or "/trinity_test_" not in DSN:
            raise RuntimeError("Refusing a non-test database.")
        cls.settings = ApiSettings(TRINITY_DATABASE_URL=DSN)
        cls.migration = Config(str(BACKEND / "alembic.ini"))
        with patch.dict(os.environ, {"TRINITY_DATABASE_URL": DSN}):
            command.upgrade(cls.migration, "head")
        cls.passwords = {role: secrets.token_urlsafe(24) for role in ("viewer", "analyst", "admin")}
        cls.hashes = {role: hash_password(password) for role, password in cls.passwords.items()}
        cls.database = Database(cls.settings)
        cls.database.open()
        cls.service = AuthService(cls.database)

    @classmethod
    def tearDownClass(cls):
        cls.database.close()

    def sql(self, statement, values=()):
        with psycopg.connect(DSN, row_factory=dict_row) as connection:
            result = connection.execute(statement, values)
            return result.fetchall() if result.description else []

    def setUp(self):
        self.sql("""TRUNCATE failure_warnings,refresh_control,active_publication,publication_events,
            approvals,data_versions,refresh_steps,refresh_runs,shared_settings,local_sessions,
            local_users,auth_login_limits RESTART IDENTITY""")
        for role in self.passwords:
            self.sql("INSERT INTO local_users(id,username,password_hash,role) VALUES (%s,%s,%s,%s)",
                     ("test_" + role, role, self.hashes[role], role))
        self.sql("INSERT INTO shared_settings(id) VALUES (1)")
        self.sql("INSERT INTO active_publication(id) VALUES (1)")
        self.sql("INSERT INTO refresh_control(id) VALUES (1)")
        self.context = TestClient(create_app(service=self.service))
        self.client = self.context.__enter__()

    def tearDown(self):
        self.context.__exit__(None, None, None)

    def login(self, role):
        response = self.client.post("/api/v1/auth/login", json={"username":role,"password":self.passwords[role]})
        self.assertEqual(response.status_code, 200)
        return {"Authorization":"Bearer " + response.json()["access_token"]}

    def setup_done(self):
        self.sql("""UPDATE shared_settings SET setup_completed_at=now(),daily_time='08:00',
            schedule_timezone='America/Merida',updated_by='test_admin',schedule_enabled=true,revision=1""")

    def lifecycle(self, status, *, warnings=0, approved=False, code="dependency_unavailable"):
        self.setup_done()
        run, version, step = uuid4(), uuid4(), uuid4()
        terminal = status in ("succeeded", "failed", "discarded", "superseded")
        self.sql("""INSERT INTO refresh_runs(id,trigger_kind,requested_by,request_key,requested_at,
            finished_at,status,settings_revision,policy_snapshot,requested_start,requested_end,window_frozen_at,
            error_code,error_summary)
            VALUES (%s,'manual','test_admin',%s,now(),%s,%s,1,'{}','2026-10-01','2026-10-01',now(),%s,%s)""",
            (run,uuid4(),datetime.now(timezone.utc) if terminal else None,status,
             "dependency_unavailable" if status=="failed" else None,"Refresh failed" if status=="failed" else None))
        if status not in ("succeeded", "discarded", "superseded"):
            self.sql("UPDATE refresh_control SET holder_run_id=%s",(run,))
        self.sql("""INSERT INTO refresh_steps(id,run_id,step_seq,stage,work_key,attempt,status,
            execution_fence,finished_at,progress_unit) VALUES (%s,%s,1,'validate','all',1,'succeeded',0,now(),'checks')""",(step,run))
        self.sql("""INSERT INTO data_versions(id,run_id,status,disposition,approval_required,
            review_warning_count,review_warning_digest,diagnostics_frozen_at,created_at,manifest_frozen_at,
            manifest_sha256,validated_at,validation_step_id,coverage_start,coverage_end,latest_observation_date,
            contract_version,validation_checkset)
            VALUES (%s,%s,'validated','active',%s,%s,%s,now(),now(),now(),%s,now(),%s,
                '2026-10-01','2026-10-01','2026-10-01','trinity-data-v1','trinity-data-v1')""",
            (version,run,warnings>0,warnings,"a"*64,"b"*64,step))
        approval = None
        if approved:
            approval=uuid4()
            self.sql("""INSERT INTO approvals(id,version_id,approved_by,approved_at,manifest_sha256,
                validation_step_id,review_warning_digest) VALUES (%s,%s,'test_admin',now(),%s,%s,%s)""",
                (approval,version,"b"*64,step,"a"*64))
        if status in ("failed","publication_failed"):
            self.sql("""INSERT INTO failure_warnings(id,run_id,version_id,stage,code,message,created_at)
                VALUES (%s,%s,%s,'publish',%s,'Safe failure',now())""",(uuid4(),run,version,code))
        return run, version, approval

    def publish(self):
        run,version,_=self.lifecycle("succeeded")
        event=uuid4()
        self.sql("""INSERT INTO publication_events(id,version_id,published_at,publication_mode,idempotency_key)
            VALUES (%s,%s,now(),'automatic',%s)""",(event,version,uuid4()))
        self.sql("UPDATE active_publication SET publication_event_id=%s,revision=revision+1",(event,))
        return event,version

    def test_upgrade_rerun_and_constraints(self):
        before=self.sql("SELECT id,password_hash FROM local_users ORDER BY id")
        with patch.dict(os.environ,{"TRINITY_DATABASE_URL":DSN}):
            command.upgrade(self.migration,"head")
        self.assertEqual(before,self.sql("SELECT id,password_hash FROM local_users ORDER BY id"))
        cases=[("INSERT INTO local_users(id,username,password_hash,role) VALUES ('bad','other','x','owner')",()),
               ("INSERT INTO local_users(id,username,password_hash,role) VALUES ('other','viewer','x','viewer')",()),
               ("INSERT INTO local_sessions(id,user_id,token_digest,created_at,expires_at) VALUES (%s,'missing',%s,now(),now()+interval '1 hour')",(uuid4(),"a"*64)),
               ("INSERT INTO local_sessions(id,user_id,token_digest,created_at,expires_at) VALUES (%s,'test_viewer',%s,now(),now())",(uuid4(),"a"*64))]
        for sql,values in cases:
            with self.assertRaises(psycopg.IntegrityError):
                self.sql(sql,values)
        self.assertEqual(self.sql("SELECT count(*) AS n FROM local_sessions")[0]["n"],0)

    def test_seed_repeat_and_mismatch_preserve_history(self):
        before=self.sql("SELECT * FROM local_users ORDER BY id")
        def forbidden_prompt(name): raise AssertionError("Existing users must not need passwords")
        self.assertEqual(seed_personas(self.database,forbidden_prompt),[])
        self.assertEqual(before,self.sql("SELECT * FROM local_users ORDER BY id"))
        self.sql("UPDATE local_users SET is_active=false WHERE username='admin'")
        with self.assertRaises(SeedError):
            seed_personas(self.database,forbidden_prompt)
        self.assertFalse(self.sql("SELECT is_active FROM local_users WHERE username='admin'")[0]["is_active"])

    def test_seed_empty_concurrently_is_atomic(self):
        self.sql("DELETE FROM local_users")
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(lambda _:seed_personas(self.database,lambda role:self.passwords[role]),range(2)))
        self.assertEqual(sum(map(len,results)),3)
        self.assertEqual(self.sql("SELECT count(*) AS n FROM local_users")[0]["n"],3)
        for role in self.passwords:
            self.login(role)

    def test_all_personas_empty_me_and_settings_access(self):
        for role in self.passwords:
            headers=self.login(role)
            response=self.client.get("/api/v1/me",headers=headers)
            self.assertEqual(response.status_code,200)
            data=response.json()
            self.assertEqual(data["role"],role)
            self.assertEqual(data["landing_screen"],"setup" if role=="admin" else "waiting")
            self.assertFalse(data["data_ready"])
            self.assertIsNone(data["publication"])
            self.assertEqual(len(data["capabilities"]),{"viewer":3,"analyst":5,"admin":11}[role])
            if role!='admin': self.assertIsNone(data['admin_context'])
            settings=self.client.get("/api/v1/settings",headers=headers)
            self.assertEqual(settings.status_code,200 if role=="admin" else 403)
            if role=="admin": self.assertEqual(settings.headers['etag'],'"settings-0"')
        columns=set(self.sql("SELECT * FROM local_sessions LIMIT 1")[0])
        self.assertNotIn("access_token",columns)
        self.assertNotIn("password",columns)

    def test_generic_denials_and_no_session_for_bad_credentials(self):
        self.sql("UPDATE local_users SET is_active=false WHERE username='admin'")
        for username,password in [('unknown',self.passwords['admin']),('viewer','incorrect'),('admin',self.passwords['admin'])]:
            response=self.client.post('/api/v1/auth/login',json={'username':username,'password':password})
            self.assertEqual((response.status_code,response.json()['code']),(401,'invalid_credentials'))
        self.assertEqual(self.sql('SELECT count(*) AS n FROM local_sessions')[0]['n'],0)

    def test_role_changes_deactivation_and_unknown_role_fail_closed(self):
        headers=self.login('analyst')
        self.sql("UPDATE local_users SET role='viewer' WHERE username='analyst'")
        self.assertEqual(self.client.get('/api/v1/me',headers=headers).json()['role'],'viewer')
        self.sql("UPDATE local_users SET is_active=false WHERE username='analyst'")
        self.assertEqual(self.client.get('/api/v1/me',headers=headers).status_code,401)
        with patch('trinity.auth.repository.capabilities',side_effect=Problem(403,'forbidden')):
            self.sql("UPDATE local_users SET is_active=true WHERE username='analyst'")
            self.assertEqual(self.client.get('/api/v1/me',headers=headers).status_code,403)

    def test_logout_revokes_only_current_session_and_expiry_is_exclusive(self):
        first,second=self.login('viewer'),self.login('viewer')
        response=self.client.post('/api/v1/auth/logout',json={},headers=first)
        self.assertEqual(response.status_code,204)
        self.assertEqual(response.content,b'')
        self.assertEqual(self.client.get('/api/v1/me',headers=first).status_code,401)
        self.assertEqual(self.client.post('/api/v1/auth/logout',json={},headers=first).status_code,401)
        self.assertEqual(self.client.get('/api/v1/me',headers=second).status_code,200)
        self.sql("UPDATE local_sessions SET created_at=now()-interval '2 hours',expires_at=now()-interval '1 hour' WHERE revoked_at IS NULL")
        self.assertEqual(self.client.get('/api/v1/me',headers=second).status_code,401)

    def test_session_write_and_revocation_failures_do_not_succeed(self):
        with patch('trinity.auth.repository.create_session',side_effect=psycopg.OperationalError('private-db-canary')):
            response=self.client.post('/api/v1/auth/login',json={'username':'viewer','password':self.passwords['viewer']})
        self.assertEqual((response.status_code,response.json()['code']),(503,'auth_unavailable'))
        self.assertNotIn('private-db-canary',response.text)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM local_sessions')[0]['n'],0)
        headers=self.login('viewer')
        with patch('trinity.auth.repository.revoke_session',side_effect=psycopg.OperationalError('private-db-canary')):
            response=self.client.post('/api/v1/auth/logout',json={},headers=headers)
        self.assertEqual(response.status_code,503)
        self.assertEqual(self.client.get('/api/v1/me',headers=headers).status_code,200)

    def test_denied_settings_never_reads_the_repository(self):
        headers=self.login('viewer')
        with patch('trinity.settings.service.read_settings',side_effect=AssertionError('protected read')) as read:
            response=self.client.get('/api/v1/settings',headers=headers)
        self.assertEqual(response.status_code,403)
        read.assert_not_called()

    def test_setup_complete_and_published_landings(self):
        self.setup_done()
        admin=self.login('admin')
        self.assertEqual(self.client.get('/api/v1/me',headers=admin).json()['landing_screen'],'refresh_runs')
        event,version=self.publish()
        for role in self.passwords:
            data=self.client.get('/api/v1/me',headers=self.login(role)).json()
            self.assertTrue(data['data_ready'])
            self.assertEqual(data['publication']['version_id'],str(version))
            self.assertEqual(data['publication']['publication_event_id'],str(event))
            self.assertEqual(data['landing_screen'],'national_dashboard' if role=='viewer' else 'explorer')
        self.sql("UPDATE shared_settings SET setup_completed_at=NULL,schedule_enabled=false,daily_time=NULL,schedule_timezone=NULL,updated_by=NULL")
        self.assertEqual(self.client.get('/api/v1/me',headers=admin).json()['landing_screen'],'setup')

    def test_unpublished_candidate_never_sets_readiness(self):
        self.lifecycle('awaiting_approval',warnings=1)
        data=self.client.get('/api/v1/me',headers=self.login('viewer')).json()
        self.assertFalse(data['data_ready'])
        self.assertIsNone(data['publication'])

    def test_snapshot_stays_consistent_during_publication_change(self):
        self.publish()
        first=self.sql('SELECT publication_event_id FROM active_publication')[0]['publication_event_id']
        headers=self.login('viewer')
        with self.service.authenticated(headers['Authorization'][7:]) as (principal,connection):
            self.sql('UPDATE active_publication SET publication_event_id=NULL')
            result=self.service.me(principal,connection)
            self.assertEqual(result.publication.publication_event_id,first)
        self.assertFalse(self.client.get('/api/v1/me',headers=headers).json()['data_ready'])

    def test_missing_state_and_state_read_failure_are_not_empty(self):
        headers=self.login('viewer')
        with patch('trinity.auth.service.read_publication',side_effect=psycopg.OperationalError('private-db-canary')):
            response=self.client.get('/api/v1/me',headers=headers)
        self.assertEqual((response.status_code,response.json()['code']),(503,'dependency_unavailable'))
        self.sql('DELETE FROM active_publication')
        response=self.client.get('/api/v1/me',headers=headers)
        self.assertEqual((response.status_code,response.json()['code']),(503,'dependency_unavailable'))

    def test_admin_workflow_actions_and_unrecoverable_failure(self):
        run,version,_=self.lifecycle('awaiting_approval',warnings=1)
        headers=self.login('admin')
        data=self.client.get('/api/v1/me',headers=headers).json()['admin_context']
        actions={a['action']:a['enabled'] for a in data['actions']}
        self.assertTrue(actions['approve']); self.assertTrue(actions['discard']); self.assertFalse(actions['start_refresh'])
        self.sql("UPDATE refresh_runs SET status='publishing' WHERE id=%s",(run,))
        data=self.client.get('/api/v1/me',headers=headers).json()['admin_context']
        self.assertFalse(any(a['enabled'] for a in data['actions']))
        self.assertEqual(data['refresh_blocker']['code'],'publication_in_progress')

    def test_throttle_shared_across_pools_rollover_and_cleanup(self):
        other=Database(self.settings); other.open()
        def reserve(i):
            db=self.database if i%2 else other
            with db.transaction(Deadline()) as connection:
                return repository.reserve_login(connection,'viewer','same-peer')
        try:
            with ThreadPoolExecutor(max_workers=4) as executor:
                results=list(executor.map(reserve,range(12)))
            self.assertEqual(results.count(None),5)
            self.assertTrue(all(x is None or 1<=x<=60 for x in results))
            response=self.client.post('/api/v1/auth/login',json={'username':'viewer','password':'incorrect'},
                                      headers={'X-Forwarded-For':'different-peer'})
            self.assertEqual(response.status_code,429)
            self.assertIn('retry-after',response.headers)
            self.sql("UPDATE auth_login_limits SET window_start=now()-interval '61 seconds'")
            self.assertIsNone(reserve(0))
        finally:
            other.close()

    def test_real_http_three_personas(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        environment={**os.environ,'TRINITY_DATABASE_URL':DSN,'PYTHONPATH':str(BACKEND/'src')}
        process=subprocess.Popen([sys.executable,'-m','uvicorn','trinity.main:app','--host','127.0.0.1',
                                  '--port',str(port),'--no-access-log','--no-proxy-headers','--log-level','critical'],
                                 env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=20) as client:
                limit=time.monotonic()+15
                while True:
                    try:
                        if client.get('/health').status_code==200: break
                    except httpx.TransportError: pass
                    if time.monotonic()>limit: self.fail('HTTP server did not become ready')
                    time.sleep(0.1)
                for role in self.passwords:
                    landing=check_persona(client,role,self.passwords[role])
                    self.assertEqual(landing,'setup' if role=='admin' else 'waiting')
        finally:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)

    def test_throttle_is_shared_across_processes(self):
        with ProcessPoolExecutor(max_workers=3, mp_context=multiprocessing.get_context('spawn')) as executor:
            results=list(executor.map(reserve_in_process,[DSN]*9))
        self.assertEqual(results.count(None),5)
        self.assertEqual(len([value for value in results if value is not None]),4)

    def test_deferred_commit_failure_does_not_return_token(self):
        self.sql("""CREATE FUNCTION test_reject_session() RETURNS trigger LANGUAGE plpgsql AS
            'BEGIN RAISE EXCEPTION USING ERRCODE = ''23514'', MESSAGE = ''private-commit-canary''; END';
            CREATE CONSTRAINT TRIGGER test_session_commit AFTER INSERT ON local_sessions
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION test_reject_session()""")
        try:
            response=self.client.post('/api/v1/auth/login',json={'username':'viewer','password':self.passwords['viewer']})
            self.assertEqual((response.status_code,response.json()['code']),(503,'auth_unavailable'))
            self.assertNotIn('private-commit-canary',response.text)
            self.assertNotIn('access_token',response.json())
            self.assertEqual(self.sql('SELECT count(*) AS n FROM local_sessions')[0]['n'],0)
        finally:
            self.sql('DROP TRIGGER test_session_commit ON local_sessions; DROP FUNCTION test_reject_session()')

    def test_dependency_teardown_failure_is_not_a_successful_me(self):
        headers=self.login('viewer')
        real=self.service.authenticated
        @contextmanager
        def fail_after_read(token):
            with real(token) as context:
                yield context
                raise Problem(503,'dependency_unavailable')
        with patch.object(self.service,'authenticated',side_effect=fail_after_read):
            response=self.client.get('/api/v1/me',headers=headers)
        self.assertEqual((response.status_code,response.json()['code']),(503,'dependency_unavailable'))

    def test_duplicate_digest_and_transaction_rollback(self):
        headers=self.login('viewer')
        digest=hashlib.sha256(headers['Authorization'][7:].encode()).hexdigest()
        with self.assertRaises(psycopg.IntegrityError):
            self.sql("""INSERT INTO local_sessions(id,user_id,token_digest,created_at,expires_at)
                VALUES (%s,'test_viewer',%s,now(),now()+interval '1 hour')""",(uuid4(),digest))
        with self.assertRaises(Problem):
            with self.database.transaction(Deadline()) as connection:
                connection.execute("UPDATE local_users SET role='analyst' WHERE username='viewer'")
                connection.execute("UPDATE local_users SET role='unknown' WHERE username='admin'")
        self.assertEqual(self.sql("SELECT role FROM local_users WHERE username='viewer'")[0]['role'],'viewer')

    def test_schema_downgrade_upgrade_on_disposable_database(self):
        with patch.dict(os.environ,{'TRINITY_DATABASE_URL':DSN}):
            command.downgrade(self.migration,'base')
            self.assertIsNone(self.sql("SELECT to_regclass('public.local_users') AS relation")[0]['relation'])
            command.upgrade(self.migration,'head')
        self.assertEqual(self.sql('SELECT count(*) AS n FROM local_users')[0]['n'],0)
        self.assertIsNone(self.sql('SELECT publication_event_id FROM active_publication')[0]['publication_event_id'])

    def test_publication_retry_requires_matching_approval_and_recoverable_error(self):
        run,version,approval=self.lifecycle('publication_failed',warnings=1,approved=True)
        headers=self.login('admin')
        def actions():
            response=self.client.get('/api/v1/me',headers=headers)
            self.assertEqual(response.status_code,200)
            return {a['action']:a['enabled'] for a in response.json()['admin_context']['actions']}
        self.assertTrue(actions()['publication_retry'])
        self.sql("UPDATE approvals SET manifest_sha256=%s WHERE id=%s",('c'*64,approval))
        self.assertFalse(actions()['publication_retry'])
        self.sql("UPDATE approvals SET manifest_sha256=%s WHERE id=%s",('b'*64,approval))
        self.sql("UPDATE failure_warnings SET code='artifact_integrity'")
        self.assertFalse(actions()['publication_retry'])
        self.assertTrue(actions()['rerun'])
        self.assertTrue(actions()['discard'])

    def test_peer_and_global_throttle_bound_new_key_creation(self):
        for i in range(30):
            with self.database.transaction(Deadline()) as connection:
                self.assertIsNone(repository.reserve_login(connection,f'user-{i}','shared-peer'))
        with self.database.transaction(Deadline()) as connection:
            self.assertIsNotNone(repository.reserve_login(connection,'new-user','shared-peer'))
        self.sql('TRUNCATE auth_login_limits')
        for i in range(60):
            with self.database.transaction(Deadline()) as connection:
                self.assertIsNone(repository.reserve_login(connection,f'user-{i}',f'peer-{i}'))
        with self.database.transaction(Deadline()) as connection:
            self.assertIsNotNone(repository.reserve_login(connection,'new-user','new-peer'))
        self.assertEqual(self.sql('SELECT count(*) AS n FROM auth_login_limits')[0]['n'],121)

    def test_forged_token_never_reaches_publication_lookup(self):
        with patch('trinity.auth.service.read_publication',side_effect=AssertionError('protected read')) as read:
            response=self.client.get('/api/v1/me',headers={'Authorization':'Bearer '+'x'*43})
        self.assertEqual((response.status_code,response.json()['code']),(401,'invalid_session'))
        read.assert_not_called()

    def test_captured_error_logs_and_responses_exclude_secret_canaries(self):
        import io, logging
        stream=io.StringIO()
        handler=logging.StreamHandler(stream)
        logger=logging.getLogger()
        logger.addHandler(handler)
        old_level=logger.level
        logger.setLevel(logging.DEBUG)
        try:
            with patch('trinity.auth.repository.find_user',side_effect=psycopg.OperationalError('private-db-canary')):
                response=self.client.post('/api/v1/auth/login',json={'username':'viewer','password':'private-password-canary'})
            self.assertEqual(response.status_code,503)
            for canary in ('private-db-canary','private-password-canary'):
                self.assertNotIn(canary,response.text)
                self.assertNotIn(canary,stream.getvalue())
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
