"""Close Admin admission with real HTTP transactions and process races."""
import multiprocessing
import unittest
from uuid import uuid4
from postgres_fixture import DSN, PostgresFixture
from trinity.adapters.postgres import Database
from trinity.config import ApiSettings
from trinity.errors import Problem
from trinity.refresh.service import RefreshService


def compete(dsn, token, key, ready, start, result):
    """Use an independent connection pool in each spawned contender."""
    database = Database(ApiSettings(TRINITY_DATABASE_URL=dsn))
    database.open()
    ready.put(True)
    start.wait(10)
    try:
        receipt = RefreshService(database).start(token,b'{}',[key])
        result.put(('accepted',str(receipt.run_id),receipt.replayed))
    except Problem as error:
        result.put((error.code,))
    finally:
        database.close()


@unittest.skipUnless(DSN,'Use the disposable refresh runner')
class AdmissionTests(PostgresFixture, unittest.TestCase):
    def request(self, headers=None, key=None, body=b'{}'):
        return self.client.post('/api/v1/refresh-runs',content=body,
            headers={**(headers or {}),'Idempotency-Key':key or str(uuid4()),'Content-Type':'application/json'})

    def test_permissions_setup_strict_input_and_tracking(self):
        self.assertEqual(self.request().status_code,401)
        for role in ('viewer','analyst'):
            self.assertEqual(self.request(self.login(role)).status_code,403)
        admin = self.login('admin')
        self.assertEqual(self.request(admin).status_code,409)
        self.setup_done()
        for body in (b'{"actor":"admin"}',b'{"start":"2024-01-01"}',b'[]',b'{'):
            self.assertEqual(self.request(admin,body=body).status_code,400 if body==b'{' else 422)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM refresh_runs')[0]['n'],0)
        response = self.request(admin)
        self.assertEqual(response.status_code,202,response.text)
        detail = self.client.get(response.json()['status_url'],headers=admin)
        self.assertEqual(detail.status_code,200,detail.text)
        self.assertEqual(detail.json()['status'],'requested')
        self.assertEqual(self.request(admin).status_code,409)

    def test_replay_returns_original_receipt_after_state_change(self):
        self.setup_done(); admin=self.login('admin'); key=str(uuid4())
        first=self.request(admin,key)
        self.assertEqual(first.status_code,202,first.text)
        self.sql("UPDATE refresh_runs SET status='running',started_at=now()")
        replay=self.request(admin,key)
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json(),{**first.json(),'replayed':True})
        self.assertEqual(self.sql('SELECT count(*) AS n FROM job_outbox')[0]['n'],1)

    def test_receipt_failure_and_deferred_commit_failure_roll_back(self):
        self.setup_done(); admin=self.login('admin')
        # Exercise both an insert failure and an error raised only at COMMIT.
        for deferred in (False,True):
            self.sql("CREATE FUNCTION reject_receipt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic'; END $$")
            trigger = ('CREATE CONSTRAINT TRIGGER reject_receipt AFTER INSERT ON api_commands DEFERRABLE INITIALLY DEFERRED'
                       if deferred else 'CREATE TRIGGER reject_receipt BEFORE INSERT ON api_commands')
            self.sql(trigger+' FOR EACH ROW EXECUTE FUNCTION reject_receipt()')
            try:
                response=self.request(admin)
                self.assertEqual(response.status_code,503,response.text)
                for table in ('refresh_runs','job_outbox','api_commands'):
                    self.assertEqual(self.sql(f'SELECT count(*) AS n FROM {table}')[0]['n'],0)
                self.assertIsNone(self.sql('SELECT holder_run_id FROM refresh_control')[0]['holder_run_id'])
            finally:
                self.sql('DROP TRIGGER reject_receipt ON api_commands')
                self.sql('DROP FUNCTION reject_receipt()')

    def race(self, same_key):
        self.setup_done(); token=self.login('admin')['Authorization'][7:]
        context=multiprocessing.get_context('spawn')
        ready,result,start=context.Queue(),context.Queue(),context.Event()
        keys=[str(uuid4()),str(uuid4())]
        if same_key:keys[1]=keys[0]
        processes=[context.Process(target=compete,args=(DSN,token,key,ready,start,result)) for key in keys]
        try:
            for process in processes:process.start()
            for _ in processes:ready.get(timeout=15)
            start.set()
            outcomes=[result.get(timeout=15) for _ in processes]
            for process in processes:
                process.join(10);self.assertEqual(process.exitcode,0)
            self.assertEqual(self.sql('SELECT count(*) AS n FROM refresh_runs')[0]['n'],1)
            self.assertEqual(self.sql('SELECT count(*) AS n FROM job_outbox')[0]['n'],1)
            if same_key:
                self.assertEqual({item[0] for item in outcomes},{'accepted'})
                self.assertEqual({item[2] for item in outcomes},{True,False})
                self.assertEqual(len({item[1] for item in outcomes}),1)
            else:
                self.assertEqual({item[0] for item in outcomes},{'accepted','refresh_blocked'})
        finally:
            for process in processes:
                if process.is_alive():process.kill();process.join()
            ready.close();result.close()

    def test_same_key_process_race(self):
        self.race(True)

    def test_distinct_key_process_race(self):
        self.race(False)

    def test_each_admission_write_rolls_back_the_whole_command(self):
        self.setup_done();admin=self.login('admin')
        for table,event in (('refresh_runs','INSERT'),('refresh_control','UPDATE'),('job_outbox','INSERT')):
            self.sql("CREATE FUNCTION reject_admission() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic'; END $$")
            self.sql(f'CREATE TRIGGER reject_admission BEFORE {event} ON {table} FOR EACH ROW EXECUTE FUNCTION reject_admission()')
            try:
                self.assertEqual(self.request(admin).status_code,503)
                for target in ('refresh_runs','job_outbox','api_commands'):
                    self.assertEqual(self.sql(f'SELECT count(*) AS n FROM {target}')[0]['n'],0)
                self.assertIsNone(self.sql('SELECT holder_run_id FROM refresh_control')[0]['holder_run_id'])
            finally:
                self.sql(f'DROP TRIGGER reject_admission ON {table}')
                self.sql('DROP FUNCTION reject_admission()')

    def test_current_role_and_session_checked_before_replay(self):
        self.setup_done();admin=self.login('admin');key=str(uuid4())
        self.assertEqual(self.request(admin,key).status_code,202)
        self.sql("UPDATE local_users SET role='viewer' WHERE id='test_admin'")
        self.assertEqual(self.request(admin,key).status_code,403)
        self.sql("UPDATE local_users SET role='admin' WHERE id='test_admin'")
        self.sql("UPDATE local_sessions SET revoked_at=now()")
        self.assertEqual(self.request(admin,key).status_code,401)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM api_commands')[0]['n'],1)

    def test_tracking_cursor_is_bound_and_private_fields_stay_hidden(self):
        from trinity.refresh.cursors import RefreshCursorCodec
        from trinity.queries.cursors import load_cursor_keys
        from trinity.refresh.service import RefreshService
        import json
        from test_preview_unit import environment
        keys=load_cursor_keys(environment())
        self.client.app.state.refresh_service=RefreshService(self.database,codec_factory=lambda:RefreshCursorCodec(keys))
        self.setup_done();admin=self.login('admin')
        for _ in range(3):
            response=self.request(admin);self.assertEqual(response.status_code,202,response.text)
            # Synthetic terminal runs permit history paging without invoking the
            # later product recovery/publisher. No production endpoint does this.
            self.sql("UPDATE refresh_runs SET status='discarded',finished_at=now() WHERE status='requested'")
            self.sql('UPDATE refresh_control SET holder_run_id=NULL')
        first=self.client.get('/api/v1/refresh-runs?limit=1',headers=admin)
        self.assertEqual(first.status_code,200,first.text)
        token=first.json()['next_cursor'];self.assertIsNotNone(token)
        second=self.client.get('/api/v1/refresh-runs',params={'cursor':token},headers=admin)
        self.assertEqual(second.status_code,200,second.text)
        self.assertNotEqual(first.json()['items'][0]['run_id'],second.json()['items'][0]['run_id'])
        self.assertEqual(self.client.get('/api/v1/refresh-runs',params={'cursor':token+'x'},headers=admin).status_code,422)
        self.assertEqual(self.client.get('/api/v1/refresh-runs',params={'cursor':token,'limit':2},headers=admin).status_code,422)
        for private in ('policy_snapshot','worker_execution_ref','lease_token','payload'):
            self.assertNotIn(private,first.text)

    def test_same_key_different_current_admin_is_a_conflict(self):
        self.setup_done();key=str(uuid4())
        self.assertEqual(self.request(self.login('admin'),key).status_code,202)
        self.sql("UPDATE local_users SET role='admin' WHERE id='test_analyst'")
        response=self.request(self.login('analyst'),key)
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json()['code'],'idempotency_conflict')

    def test_each_unresolved_holder_blocks_new_intent(self):
        self.setup_done();admin=self.login('admin')
        response=self.request(admin);self.assertEqual(response.status_code,202,response.text)
        run=response.json()['run_id']
        for status in ('running','awaiting_approval','publishing','publication_failed','failed'):
            self.sql("UPDATE refresh_runs SET status=%s,finished_at=CASE WHEN %s='failed' THEN now() ELSE NULL END,error_code='refresh_failed',error_summary='Safe failure' WHERE id=%s",(status,status,run))
            if status=='publication_failed':
                self.sql("INSERT INTO failure_warnings(id,run_id,stage,code,message,created_at) VALUES(%s,%s,'prepare','refresh_failed','Safe failure',now())",(uuid4(),run))
            self.assertEqual(self.request(admin).status_code,409)
            self.assertEqual(self.sql('SELECT count(*) AS n FROM refresh_runs')[0]['n'],1)
            self.assertEqual(self.sql('SELECT count(*) AS n FROM api_commands')[0]['n'],1)

    def test_loopback_http_commit_failure_acceptance_and_replay(self):
        """Exercise real HTTP sockets in addition to the in-process adapter cases."""
        import socket
        import threading
        import time
        import httpx
        import uvicorn
        self.setup_done();admin=self.login('admin');key=str(uuid4())
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(16)
        port=listener.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(self.client.app,lifespan='off',access_log=False,log_level='critical'))
        thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True)
        thread.start()
        try:
            for _ in range(250):
                if server.started:break
                time.sleep(.02)
            self.assertTrue(server.started)
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=5) as client:
                headers={**admin,'Idempotency-Key':key}
                self.sql("CREATE FUNCTION socket_reject() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic'; END $$")
                self.sql('CREATE CONSTRAINT TRIGGER socket_reject AFTER INSERT ON api_commands DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION socket_reject()')
                try:
                    response=client.post('/api/v1/refresh-runs',json={},headers=headers)
                    self.assertEqual(response.status_code,503,response.text)
                    self.assertEqual(self.sql('SELECT count(*) AS n FROM refresh_runs')[0]['n'],0)
                finally:
                    self.sql('DROP TRIGGER socket_reject ON api_commands')
                    self.sql('DROP FUNCTION socket_reject()')
                response=client.post('/api/v1/refresh-runs',json={},headers=headers)
                self.assertEqual(response.status_code,202,response.text)
                self.assertEqual(client.get(response.json()['status_url'],headers=admin).status_code,200)
                replay=client.post('/api/v1/refresh-runs',json={},headers=headers)
                self.assertEqual(replay.status_code,200,replay.text)
                self.assertEqual(replay.json()['run_id'],response.json()['run_id'])
        finally:
            server.should_exit=True
            thread.join(5)
            listener.close()
            self.assertFalse(thread.is_alive())
