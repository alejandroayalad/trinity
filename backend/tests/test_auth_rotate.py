"""Check that password rotation changes only the chosen password hashes.

The offline tests need no database. The PostgreSQL tests run through
tests/run_local_auth_checks.py, which creates a disposable cluster. They
fill many application tables, copy every table before and after a rotation,
and require that only `local_users.password_hash` of the rotated personas
differs. Each refused request must leave the copy identical.
"""
import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import psycopg

from postgres_fixture import DSN, PostgresFixture
from trinity.auth import rotate
from trinity.auth.rotate import RotationError, rotate_passwords

NEW = {"viewer": "viewer-rotated-password-1", "analyst": "analyst-rotated-password-1",
       "admin": "admin-rotated-password-1"}


class RotateOfflineTests(unittest.TestCase):
    def test_names_are_validated_before_any_database_access(self):
        class NoDatabase:
            def transaction(self, *args, **kwargs):
                raise AssertionError("database used")
        for names in ((), ("viewer", "viewer"), ("root",)):
            with self.subTest(names=names), self.assertRaises(RotationError):
                rotate_passwords(NoDatabase(), names, lambda name: NEW[name])

    def test_command_requires_a_terminal(self):
        errors = io.StringIO()
        with patch("sys.stdin.isatty", return_value=False), redirect_stderr(errors):
            self.assertEqual(rotate.main(["viewer"]), 2)
        self.assertIn("requires a terminal", errors.getvalue())

    def test_two_different_entries_are_refused(self):
        with patch("trinity.auth.rotate.getpass", side_effect=["first-password-entry", "other-password-entry"]):
            with self.assertRaises(RotationError):
                rotate._prompt("viewer")


@unittest.skipUnless(DSN, "Use tests/run_local_auth_checks.py")
class RotatePostgresTests(PostgresFixture, unittest.TestCase):
    def snapshot(self):
        """Copy every row of every application table as sorted JSON text.

        The table list comes from the catalog, so a table added by a later
        migration is compared too. Only password_hash is kept apart, so a
        test can require that exactly the rotated hashes changed.
        """
        tables = [row["table_name"] for row in self.sql("""SELECT table_name FROM information_schema.tables
            WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name""")]
        copy = {}
        for table in tables:
            rows = self.sql(f"SELECT row_to_json(t)::jsonb AS r FROM {table} t")
            values = [row["r"] for row in rows]
            if table == "local_users":
                hashes = {value["username"]: value.pop("password_hash") for value in values}
            copy[table] = sorted(json.dumps(value, sort_keys=True) for value in values)
        return copy, hashes

    def populate(self):
        """Create sessions, login limits, setup, runs, publication and a receipt."""
        headers = {role: self.login(role) for role in self.passwords}
        self.client.post("/api/v1/auth/logout", json={}, headers=self.login("viewer"))
        self.client.post("/api/v1/auth/login", json={"username": "analyst", "password": "wrong-password-x"})
        self.publish()
        started = self.client.post("/api/v1/refresh-runs", json={},
                                   headers={**headers["admin"], "Idempotency-Key": "00000000-0000-4000-8000-000000000001"})
        self.assertEqual(started.status_code, 202, started.text)
        for table in ("local_sessions", "auth_login_limits", "refresh_runs", "job_outbox", "api_commands",
                      "publication_events", "data_versions"):
            self.assertGreater(self.sql(f"SELECT count(*) AS n FROM {table}")[0]["n"], 0, table)
        return headers

    def assert_unchanged(self, before):
        self.assertEqual(self.snapshot(), before)

    def test_rotation_changes_only_the_chosen_hashes(self):
        headers = self.populate()
        (tables, hashes) = self.snapshot()
        self.assertEqual(rotate_passwords(self.database, ("admin", "viewer"), lambda name: NEW[name]),
                         ["viewer", "admin"])
        after_tables, after_hashes = self.snapshot()
        self.assertEqual(after_tables, tables)
        self.assertNotEqual(after_hashes["viewer"], hashes["viewer"])
        self.assertNotEqual(after_hashes["admin"], hashes["admin"])
        self.assertEqual(after_hashes["analyst"], hashes["analyst"])
        # An existing session keeps working: sessions are not revoked.
        self.assertEqual(self.client.get("/api/v1/me", headers=headers["admin"]).status_code, 200)
        # The new password logs in; the old one does not; analyst is unchanged.
        login = lambda user, password: self.client.post(
            "/api/v1/auth/login", json={"username": user, "password": password}).status_code
        self.assertEqual(login("admin", NEW["admin"]), 200)
        self.assertEqual(login("viewer", self.passwords["viewer"]), 401)
        self.assertEqual(login("analyst", self.passwords["analyst"]), 200)

    def test_refused_requests_write_nothing(self):
        self.populate()

        def short(name):
            return "a" * 14

        def mismatch(name):
            raise RotationError("The two password entries differ; nothing was changed.")

        def replace_role_while_typing(name):
            # Another connection changes the role after the read-only check.
            with psycopg.connect(DSN) as other:
                other.execute("UPDATE local_users SET role='viewer' WHERE username='admin'")
            return NEW[name]

        for label, change, source in (
                ("short password", None, short),
                ("entries differ", None, mismatch),
                ("wrong role", "UPDATE local_users SET role='viewer' WHERE username='admin'", lambda n: NEW[n]),
                ("inactive", "UPDATE local_users SET is_active=false WHERE username='admin'", lambda n: NEW[n]),
                ("missing", "UPDATE local_users SET username='admin_old' WHERE username='admin'", lambda n: NEW[n]),
                ("changed while typing", None, replace_role_while_typing)):
            with self.subTest(label):
                if change:
                    self.sql(change)
                before = self.snapshot()
                with self.assertRaises(RotationError):
                    rotate_passwords(self.database, ("viewer", "admin"), source)
                restore = "UPDATE local_users SET role='admin', is_active=true, username='admin' WHERE id='test_admin'"
                if source is replace_role_while_typing:
                    # The other connection changed the role, not the rotation.
                    # Undo that change first; then nothing else may differ.
                    self.sql(restore)
                    self.assert_unchanged(before)
                else:
                    self.assert_unchanged(before)
                    self.sql(restore)

    def test_commit_failure_writes_nothing(self):
        # A deferred constraint trigger fails only at COMMIT, after the UPDATE
        # statements succeeded. The whole batch must roll back.
        from trinity.errors import Problem
        self.populate()
        before = self.snapshot()
        self.sql("CREATE FUNCTION reject_rotation() RETURNS trigger LANGUAGE plpgsql "
                 "AS $$ BEGIN RAISE EXCEPTION 'synthetic'; END $$")
        self.sql("CREATE CONSTRAINT TRIGGER reject_rotation AFTER UPDATE ON local_users "
                 "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION reject_rotation()")
        try:
            with self.assertRaises(Problem):
                rotate_passwords(self.database, ("viewer", "admin"), lambda name: NEW[name])
        finally:
            self.sql("DROP TRIGGER reject_rotation ON local_users")
            self.sql("DROP FUNCTION reject_rotation()")
        self.assert_unchanged(before)

    def test_command_prints_only_names(self):
        output, errors = io.StringIO(), io.StringIO()
        entries = [NEW["analyst"], NEW["analyst"]]
        with patch.dict(os.environ, {"TRINITY_DATABASE_URL": DSN}), \
                patch("sys.stdin.isatty", return_value=True), \
                patch("trinity.auth.rotate.getpass", side_effect=entries), \
                redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(rotate.main(["analyst"]), 0)
        self.assertEqual((output.getvalue(), errors.getvalue()), ("Rotated: analyst\n", ""))
        stored = self.sql("SELECT password_hash FROM local_users WHERE username='analyst'")[0]["password_hash"]
        self.assertNotIn(NEW["analyst"], output.getvalue() + stored)
        self.assertNotIn(stored, output.getvalue())


if __name__ == "__main__":
    unittest.main()
