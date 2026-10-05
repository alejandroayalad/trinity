"""Opt-in real PostgreSQL and HTTP checks for schedule settings.

Run through tests/run_local_auth_checks.py. It creates a disposable cluster
and sets TRINITY_TEST_DATABASE_URL. Never point this variable at retained
data: every test truncates the application tables.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import time
import unittest
from unittest.mock import patch

import psycopg

from postgres_fixture import DSN, PostgresFixture
from trinity.errors import Problem
from trinity.settings import service as settings_service
from trinity.settings.service import SettingsService

BODY = {"schedule_enabled": True, "daily_time": "06:15", "timezone": "America/New_York"}


@unittest.skipUnless(DSN, "Use tests/run_local_auth_checks.py")
class SettingsPostgresTests(PostgresFixture, unittest.TestCase):
    def put(self, headers, tag, body=BODY):
        return self.client.put("/api/v1/settings", content=json.dumps(body),
                               headers={**headers, "Content-Type": "application/json", "If-Match": tag})

    def settings_row(self):
        return self.sql("SELECT * FROM shared_settings WHERE id=1")[0]

    def counts(self):
        """Count rows that a refresh admission would create."""
        return {table: self.sql(f"SELECT count(*) AS n FROM {table}")[0]["n"]
                for table in ("refresh_runs", "job_outbox", "api_commands")}

    def test_first_setup_then_edit_keeps_setup_time(self):
        admin = self.login("admin")
        first = self.put(admin, '"settings-0"')
        self.assertEqual(first.status_code, 200, first.json())
        self.assertEqual(first.headers["etag"], '"settings-1"')
        data = first.json()
        self.assertEqual((data["revision"], data["updated_by"]), ("1", "test_admin"))
        self.assertEqual(data["setup_completed_at"], data["updated_at"])
        self.assertEqual(self.client.get("/api/v1/me", headers=admin).json()["landing_screen"], "refresh_runs")
        second = self.put(admin, '"settings-1"', {**BODY, "daily_time": "07:00"})
        self.assertEqual((second.status_code, second.json()["revision"]), (200, "2"))
        self.assertEqual(second.json()["setup_completed_at"], data["setup_completed_at"])
        self.assertNotEqual(second.json()["updated_at"], data["updated_at"])

    def test_no_op_and_stale_no_op(self):
        admin = self.login("admin")
        saved = self.put(admin, '"settings-0"').json()
        before = self.settings_row()
        same = self.put(admin, '"settings-1"')
        self.assertEqual((same.status_code, same.headers["etag"]), (200, '"settings-1"'))
        self.assertEqual(same.json(), saved)
        self.assertEqual(self.settings_row(), before)
        # Identical values with an old revision still fail: the revision check comes first.
        stale = self.put(admin, '"settings-0"')
        self.assertEqual((stale.status_code, stale.json()["code"]), (412, "revision_mismatch"))
        self.assertEqual(self.settings_row(), before)

    def test_precondition_and_body_failures_write_nothing(self):
        admin = self.login("admin")
        before = self.settings_row()
        cases = [({"If-Match": None}, BODY, 428), ({}, {**BODY, "publication_mode": "automatic"}, 422),
                 ({}, {**BODY, "timezone": "america/new_york"}, 422), ({"If-Match": '"settings-7"'}, BODY, 412),
                 ({"If-Match": "*"}, BODY, 422)]
        for override, body, status in cases:
            with self.subTest(override=override, body=body):
                headers = {**admin, "Content-Type": "application/json", "If-Match": '"settings-0"', **override}
                headers = {k: v for k, v in headers.items() if v is not None}
                response = self.client.put("/api/v1/settings", content=json.dumps(body), headers=headers)
                self.assertEqual(response.status_code, status)
        self.assertEqual(self.settings_row(), before)

    def test_viewer_and_analyst_are_denied_before_settings_reads(self):
        for role in ("viewer", "analyst"):
            headers = self.login(role)
            with patch("trinity.settings.service.lock_settings", side_effect=AssertionError("protected read")), \
                    patch("trinity.settings.service.read_settings", side_effect=AssertionError("protected read")):
                self.assertEqual(self.put(headers, '"settings-0"').status_code, 403)
                self.assertEqual(self.client.get("/api/v1/settings/schedule-status", headers=headers).status_code, 403)

    def test_concurrent_saves_one_wins(self):
        admin = self.login("admin")
        token = admin["Authorization"].split()[1]
        self.put(admin, '"settings-0"')
        # Hold the settings row from another connection so both saves pass
        # their checks and then wait on the same lock.
        blocker = psycopg.connect(DSN)
        blocker.execute("SELECT id FROM shared_settings WHERE id=1 FOR UPDATE")
        bodies = [{**BODY, "daily_time": "07:00"}, {**BODY, "daily_time": "08:00"}]

        def save(body):
            try:
                return SettingsService(self.database).update(token, json.dumps(body).encode(), ['"settings-1"'])
            except Problem as error:
                return error

        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(save, body) for body in bodies]
            time.sleep(0.5)
            blocker.rollback()
            blocker.close()
            results = [future.result(10) for future in futures]
        winners = [r for r in results if not isinstance(r, Problem)]
        losers = [r for r in results if isinstance(r, Problem)]
        self.assertEqual(len(winners), 1)
        self.assertEqual([(r.status, r.code) for r in losers], [(412, "revision_mismatch")])
        row = self.settings_row()
        self.assertEqual((row["revision"], row["daily_time"]), (2, winners[0].daily_time))

    def test_failure_before_commit_leaves_no_change(self):
        admin = self.login("admin")
        token = admin["Authorization"].split()[1]
        before = self.settings_row()
        real_write = settings_service.write_settings

        def write_then_fail(*args):
            # Run the real UPDATE, then fail inside the same transaction.
            real_write(*args)
            raise psycopg.OperationalError("synthetic failure")

        with patch("trinity.settings.service.write_settings", write_then_fail):
            with self.assertRaises(Problem) as caught:
                SettingsService(self.database).update(token, json.dumps(BODY).encode(), ['"settings-0"'])
        self.assertEqual(caught.exception.status, 503)
        self.assertEqual(self.settings_row(), before)

    def test_save_during_lifecycle_creates_no_work(self):
        for status in ("running", "awaiting_approval", "failed"):
            with self.subTest(status=status):
                # Start each state from the fixture's clean tables.
                self.tearDown()
                self.setUp()
                admin = self.login("admin")
                self.lifecycle(status)
                before, revision = self.counts(), self.settings_row()["revision"]
                run = self.sql("SELECT id, settings_revision FROM refresh_runs")[0]
                response = self.put(admin, f'"settings-{revision}"', {**BODY, "daily_time": "05:00"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.counts(), before)
                self.assertEqual(self.sql("SELECT settings_revision FROM refresh_runs WHERE id=%s", (run["id"],))[0],
                                 {"settings_revision": run["settings_revision"]})

    def test_status_reads_one_snapshot_and_writes_nothing(self):
        admin = self.login("admin")
        unset = self.client.get("/api/v1/settings/schedule-status", headers=admin).json()
        self.assertEqual((unset["blocker"]["code"], unset["next_check_at"], unset["eligible_now"]),
                         ("setup_required", None, False))
        run, version, _ = self.lifecycle("failed")
        before = (self.counts(), self.settings_row(), self.sql("SELECT revision FROM refresh_control")[0])
        response = self.client.get("/api/v1/settings/schedule-status", headers=admin)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual((data["blocker"]["code"], data["blocker"]["run_id"], data["blocker"]["version_id"]),
                         ("failure_unresolved", str(run), str(version)))
        self.assertIsNotNone(data["blocker"]["warning_id"])
        self.assertFalse(data["eligible_now"])
        self.assertGreater(data["next_check_at"], data["evaluated_at"])
        self.assertTrue(data["next_check_local"].endswith("-06:00"))
        self.assertEqual(before, (self.counts(), self.settings_row(), self.sql("SELECT revision FROM refresh_control")[0]))

    def test_corrupt_stored_timezone_is_unavailable(self):
        self.setup_done()
        self.sql("UPDATE shared_settings SET schedule_timezone='america/merida'")
        admin = self.login("admin")
        for path in ("/api/v1/settings", "/api/v1/settings/schedule-status"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, headers=admin).status_code, 503)



if __name__ == "__main__":
    unittest.main()
