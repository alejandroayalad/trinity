"""Share disposable PostgreSQL state builders without inheriting test cases."""

from datetime import datetime, timezone
import os
from pathlib import Path
import secrets
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import psycopg
from psycopg.rows import dict_row

from trinity.adapters.postgres import Database
from trinity.auth.passwords import hash_password
from trinity.auth.service import AuthService
from trinity.config import ApiSettings
from trinity.main import create_app

DSN = os.environ.get("TRINITY_TEST_DATABASE_URL")
BACKEND = Path(__file__).resolve().parents[1]


class PostgresFixture:
    """Create fixture state only in the disposable test database."""
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
        self.sql("""TRUNCATE query_reservations,analytical_rate_limits,failure_warnings,refresh_control,active_publication,publication_events,
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
