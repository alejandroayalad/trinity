"""Opt-in catalog acceptance with real PostgreSQL and loopback HTTP."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx
import psycopg

from postgres_fixture import BACKEND, DSN, PostgresFixture
from trinity.auth.check import check_persona
from trinity.auth.permissions import Principal
from trinity.catalog import service as catalog_service
from trinity.config import ApiSettings
from trinity.errors import Problem
from trinity.main import create_app


@unittest.skipUnless(DSN, "Use tests/run_local_auth_checks.py for disposable PostgreSQL acceptance")
class PostgresCatalogTests(PostgresFixture, unittest.TestCase):
    def catalog(self, headers):
        return self.client.get("/api/v1/catalog", headers=headers)

    def test_real_sessions_all_personas_empty_and_published(self):
        headers = {role: self.login(role) for role in self.passwords}
        for published in (False, True):
            if published:
                event, version = self.publish()
            for role in self.passwords:
                body = self.catalog(headers[role])
                self.assertEqual(body.status_code, 200)
                data = body.json()
                expected = ["national_outages"] if role == "viewer" else [
                    "national_outages", "facility_outages", "generator_outages"]
                self.assertEqual([d["key"] for d in data["datasets"]], expected)
                self.assertEqual(data["data_ready"], published)
                if published:
                    self.assertEqual(data["publication"]["publication_event_id"], str(event))
                    self.assertEqual(data["publication"]["version_id"], str(version))
                    self.assertEqual(data["freshness"]["published_at"], data["publication"]["published_at"])
                else:
                    self.assertIsNone(data["publication"])
                    self.assertIsNone(data["freshness"]["last_refresh"])

    def test_role_session_expiry_revocation_and_deactivation_changes(self):
        headers = self.login("analyst")
        for role, count in (("viewer", 1), ("analyst", 3)):
            self.sql("UPDATE local_users SET role=%s WHERE username='analyst'", (role,))
            self.assertEqual(len(self.catalog(headers).json()["datasets"]), count)
        self.sql("UPDATE local_users SET is_active=false WHERE username='analyst'")
        self.assertEqual(self.catalog(headers).status_code, 401)
        self.sql("UPDATE local_users SET is_active=true WHERE username='analyst'")
        self.client.post("/api/v1/auth/logout", headers=headers, json={})
        self.assertEqual(self.catalog(headers).status_code, 401)
        viewer = self.login("viewer")
        self.sql("""UPDATE local_sessions SET created_at=now()-interval '2 hours',
            expires_at=now()-interval '1 hour' WHERE revoked_at IS NULL""")
        self.assertEqual(self.catalog(viewer).status_code, 401)

    def test_invalid_identity_never_reads_catalog_state(self):
        with patch("trinity.catalog.service.read_publication", side_effect=AssertionError("Protected read")) as read:
            response = self.catalog({"Authorization": "Bearer " + "x" * 43})
            self.assertEqual((response.status_code, response.json()["code"]), (401, "invalid_session"))
            headers = self.login("viewer")
            with patch("trinity.auth.repository.resolve_session", return_value=Principal("x", "unknown", None)):
                self.assertEqual(self.catalog(headers).status_code, 403)
            read.assert_not_called()

    def test_newest_sequence_wins_over_time_and_failure_does_not_hide_publication(self):
        event, version = self.publish()
        run, candidate, _ = self.lifecycle("failed")
        self.sql("""UPDATE refresh_runs SET requested_at='2024-01-01Z',
            error_summary='private-failure-canary' WHERE id=%s""", (run,))
        for role in self.passwords:
            response = self.catalog(self.login(role))
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertTrue(body["data_ready"])
            self.assertEqual(body["publication"]["publication_event_id"], str(event))
            self.assertEqual(body["publication"]["version_id"], str(version))
            latest = body["freshness"]["last_refresh"]
            self.assertEqual(latest["status"], "failed")
            self.assertEqual(latest["requested_at"], "2024-01-01T00:00:00Z")
            self.assertEqual(set(latest), {"status", "requested_at", "finished_at"})
            for hidden in (str(run), str(candidate), "private-failure-canary", "test_admin", "manifest_sha256"):
                self.assertNotIn(hidden, response.text)

    def test_candidate_only_metadata_is_not_published(self):
        _, candidate, _ = self.lifecycle("awaiting_approval", warnings=1)
        response = self.catalog(self.login("viewer"))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["data_ready"])
        self.assertIsNone(body["publication"])
        self.assertIsNone(body["freshness"]["published_at"])
        self.assertIsNone(body["freshness"]["latest_observation_date"])
        self.assertEqual(body["freshness"]["last_refresh"]["status"], "awaiting_approval")
        self.assertNotIn(str(candidate), response.text)

    def test_missing_inconsistent_and_unreadable_state_fail_closed(self):
        headers = self.login("viewer")
        _, version = self.publish()
        self.sql("UPDATE data_versions SET disposition='superseded' WHERE id=%s", (version,))
        self.assertEqual(self.catalog(headers).status_code, 503)
        self.sql("DELETE FROM active_publication")
        self.assertEqual(self.catalog(headers).status_code, 503)
        self.sql("INSERT INTO active_publication(id) VALUES (1)")
        for target in ("read_publication", "read_last_refresh"):
            with patch("trinity.catalog.service." + target,
                       side_effect=psycopg.OperationalError("private-state-canary")):
                response = self.catalog(headers)
            self.assertEqual((response.status_code, response.json()["code"]), (503, "dependency_unavailable"))
            self.assertNotIn("private-state-canary", response.text)

    def test_auth_storage_outage_has_no_static_fallback(self):
        settings = ApiSettings(TRINITY_DATABASE_URL="postgresql://nobody@/absent?host=/tmp/trinity-no-such-socket")
        with TestClient(create_app(settings=settings)) as client:
            self.assertEqual(client.get("/health").status_code, 200)
            response = client.get("/api/v1/catalog", headers={"Authorization": "Bearer " + "x" * 43})
        self.assertEqual((response.status_code, response.json()["code"]), (503, "auth_unavailable"))
        self.assertNotIn("datasets", response.json())

    def _during_catalog(self, headers, change):
        entered, release = threading.Event(), threading.Event()
        real = catalog_service.read_last_refresh

        def pause(connection):
            entered.set()
            if not release.wait(10):
                raise AssertionError("Snapshot test synchronization timed out")
            return real(connection)

        with patch("trinity.catalog.service.read_last_refresh", side_effect=pause):
            with ThreadPoolExecutor(max_workers=1) as executor:
                result = executor.submit(self.catalog, headers)
                try:
                    self.assertTrue(entered.wait(10))
                    change()
                finally:
                    release.set()
                response = result.result(timeout=10)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_publication_change_during_request_keeps_one_snapshot(self):
        event, version = self.publish()
        self.sql("UPDATE refresh_runs SET requested_at='2024-01-01Z'")
        headers = self.login("viewer")
        before = self._during_catalog(headers, self.publish)
        self.assertEqual(before["publication"]["publication_event_id"], str(event))
        self.assertEqual(before["publication"]["version_id"], str(version))
        self.assertEqual(before["freshness"]["last_refresh"]["requested_at"], "2024-01-01T00:00:00Z")
        after = self.catalog(headers).json()
        self.assertNotEqual(after["publication"]["publication_event_id"], str(event))
        self.assertNotEqual(after["freshness"]["last_refresh"]["requested_at"], "2024-01-01T00:00:00Z")
        for body in (before, after):
            self.assertEqual(body["freshness"]["published_at"], body["publication"]["published_at"])

    def test_refresh_update_during_request_keeps_one_snapshot(self):
        run, _, _ = self.lifecycle("running")
        headers = self.login("viewer")

        def fail_run():
            self.sql("""UPDATE refresh_runs SET status='failed', finished_at=now(),
                error_code='dependency_unavailable', error_summary='private-canary' WHERE id=%s""", (run,))

        before = self._during_catalog(headers, fail_run)
        self.assertEqual(before["freshness"]["last_refresh"]["status"], "running")
        self.assertIsNone(before["freshness"]["last_refresh"]["finished_at"])
        after = self.catalog(headers).json()
        self.assertEqual(after["freshness"]["last_refresh"]["status"], "failed")
        self.assertIsNotNone(after["freshness"]["last_refresh"]["finished_at"])

    def test_transaction_is_readonly_shared_and_teardown_failure_never_succeeds(self):
        headers = self.login("viewer")
        connections = []
        real_publication, real_refresh = catalog_service.read_publication, catalog_service.read_last_refresh

        def publication(connection):
            connections.append(connection)
            self.assertEqual(connection.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"], "on")
            self.assertEqual(connection.execute("SHOW transaction_isolation").fetchone()["transaction_isolation"], "repeatable read")
            return real_publication(connection)

        def refresh(connection):
            connections.append(connection)
            return real_refresh(connection)

        with patch("trinity.catalog.service.read_publication", side_effect=publication), patch(
                "trinity.catalog.service.read_last_refresh", side_effect=refresh):
            self.assertEqual(self.catalog(headers).status_code, 200)
        self.assertIs(connections[0], connections[1])
        self.assertEqual(len(connections), 2)
        real_context = self.service.authenticated

        @contextmanager
        def broken_cleanup(token):
            with real_context(token) as context:
                yield context
                raise Problem(503, "dependency_unavailable")

        with patch.object(self.service, "authenticated", side_effect=broken_cleanup):
            self.assertEqual(self.catalog(headers).status_code, 503)

    def test_real_loopback_http_all_personas_in_both_publication_states(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        environment = {**os.environ, "TRINITY_DATABASE_URL": DSN, "PYTHONPATH": str(BACKEND / "src")}
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "trinity.main:app", "--host", "127.0.0.1", "--port", str(port),
             "--no-access-log", "--no-proxy-headers", "--log-level", "critical"],
            env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=20, trust_env=False) as client:
                deadline = time.monotonic() + 15
                while True:
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if time.monotonic() > deadline:
                        self.fail("HTTP server did not become ready")
                    time.sleep(0.1)
                for published in (False, True):
                    if published:
                        self.publish()
                    for role in self.passwords:
                        landing = check_persona(client, role, self.passwords[role], catalog=True)
                        expected = ("national_dashboard" if role == "viewer" else "explorer") if published else (
                            "setup" if role == "admin" else "waiting")
                        self.assertEqual(landing, expected)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
