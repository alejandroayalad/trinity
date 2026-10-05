"""Offline checks for PUT /settings and GET /settings/schedule-status.

The tests replace the database with controlled objects. They prove the order
of checks, the no-op rule, blocker choice and the HTTP shape. They do not
prove PostgreSQL locks or commit behavior; test_settings_postgres.py does.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from trinity.auth.permissions import Principal
from trinity.auth.schemas import Blocker
from trinity.errors import Problem
from trinity.main import create_app
from trinity.settings.schemas import SettingsResponse
from trinity.settings.service import (
    BLOCKER_MESSAGES, SettingsService, choose_blocker, parse_settings_command, schedule_status,
)

OPENAPI = json.loads((Path(__file__).resolve().parents[2] / "docs/openapi.json").read_text())
TOKEN = "a" * 43
HEADERS = {"Authorization": "Bearer " + TOKEN}
BODY = {"schedule_enabled": True, "daily_time": "06:15", "timezone": "America/New_York"}
RAW = json.dumps(BODY).encode()
SAVED = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


def settings_row(**changes):
    """Return a synthetic set-up settings row at revision 3."""
    row = {"setup_completed_at": SAVED, "schedule_enabled": True, "daily_time": "06:15",
           "schedule_timezone": "America/New_York", "revision": 3, "updated_at": SAVED,
           "updated_by": "user_example_admin"}
    row.update(changes)
    return row


UNSET = settings_row(setup_completed_at=None, schedule_enabled=False, daily_time=None,
                     schedule_timezone=None, revision=0, updated_by=None)


class FakeDatabase:
    """Yield one marker connection and record whether the transaction committed."""

    def __init__(self):
        self.connection = object()
        self.committed = False

    @contextmanager
    def transaction(self, deadline, *, readonly=False, error_code="auth_unavailable"):
        yield self.connection
        self.committed = True


class ParseTests(unittest.TestCase):
    def test_precondition_comes_before_body(self):
        # A missing If-Match wins over a broken body: the client first needs a revision.
        with self.assertRaises(Problem) as caught:
            parse_settings_command(b"not json", [], ())
        self.assertEqual((caught.exception.status, caught.exception.code), (428, "precondition_required"))

    def test_malformed_preconditions(self):
        for tags in (['*'], ['W/"settings-1"'], ['"settings-1", "settings-2"'], ['"settings-1"', '"settings-1"'],
                     ['"candidate-1"'], ['"settings-01"'], ['settings-1'], ['"settings-"']):
            with self.subTest(tags=tags), self.assertRaises(Problem) as caught:
                parse_settings_command(RAW, tags, ())
            self.assertEqual((caught.exception.status, caught.exception.code), (422, "invalid_request"))

    def test_body_errors(self):
        cases = [(b"{", 400, "invalid_json"), (b"[]", 422, "invalid_request"),
                 (json.dumps({**BODY, "publication_mode": "automatic"}).encode(), 422, "invalid_request"),
                 (json.dumps({**BODY, "schedule_enabled": "true"}).encode(), 422, "invalid_request")]
        for raw, status, code in cases:
            with self.subTest(raw=raw), self.assertRaises(Problem) as caught:
                parse_settings_command(raw, ['"settings-3"'], ())
            self.assertEqual((caught.exception.status, caught.exception.code), (status, code))

    def test_query_parameters_are_rejected(self):
        with self.assertRaises(Problem) as caught:
            parse_settings_command(RAW, ['"settings-3"'], [("x", "1")])
        self.assertEqual(caught.exception.status, 422)

    def test_valid_command(self):
        revision, values = parse_settings_command(RAW, ['"settings-12"'], ())
        self.assertEqual((revision, values.daily_time), (12, "06:15"))


class UpdateOrderTests(unittest.TestCase):
    """Replace each database step with a recorder to observe the order of checks."""

    def run_update(self, row, *, tags=('"settings-3"',), raw=RAW, deny=False):
        calls = []
        actor = Principal("user_example_admin", "admin", uuid4())

        def authorize(connection, token, capability, *, lock=False):
            calls.append(("authorize", lock))
            if deny:
                raise Problem(403, "forbidden")
            return actor

        def lock(connection):
            calls.append(("lock_settings",))
            return row

        def write(connection, values, actor_id, now):
            calls.append(("write_settings", actor_id, now))
            return {**row, "schedule_enabled": values.schedule_enabled, "daily_time": values.daily_time,
                    "schedule_timezone": values.timezone, "revision": row["revision"] + 1,
                    "updated_at": now, "updated_by": actor_id,
                    "setup_completed_at": row["setup_completed_at"] or now}

        database = FakeDatabase()
        with patch("trinity.refresh.service._authorize", authorize), \
                patch("trinity.settings.service.lock_settings", lock), \
                patch("trinity.settings.service.write_settings", write), \
                patch("trinity.settings.service.database_now", lambda connection: NOW):
            try:
                return SettingsService(database).update(TOKEN, raw, list(tags)), calls
            except Problem as error:
                return error, calls

    def test_denied_admin_reads_no_settings(self):
        result, calls = self.run_update(settings_row(), deny=True)
        self.assertEqual(result.status, 403)
        self.assertEqual(calls, [("authorize", False)])

    def test_bad_precondition_or_body_reads_no_settings(self):
        for tags, raw, status in (((), RAW, 428), (('*',), RAW, 422), (('"settings-3"',), b"{", 400)):
            with self.subTest(tags=tags, raw=raw):
                result, calls = self.run_update(settings_row(), tags=tags, raw=raw)
                self.assertEqual(result.status, status)
                self.assertEqual(calls, [("authorize", False)])

    def test_stale_revision_writes_nothing_even_for_identical_values(self):
        # The revision check comes before the no-op check. A stale client
        # must not receive 200, even when its values match the stored ones.
        result, calls = self.run_update(settings_row(revision=4))
        self.assertEqual((result.status, result.code), (412, "revision_mismatch"))
        self.assertEqual(calls, [("authorize", False), ("authorize", True), ("lock_settings",)])

    def test_no_op_save_returns_current_row_without_write(self):
        result, calls = self.run_update(settings_row())
        self.assertEqual((result.revision, result.updated_at, result.updated_by), ("3", SAVED, "user_example_admin"))
        self.assertNotIn("write_settings", [c[0] for c in calls])

    def test_single_field_change_creates_next_revision(self):
        result, calls = self.run_update(settings_row(schedule_enabled=False))
        self.assertEqual(calls[-1], ("write_settings", "user_example_admin", NOW))
        self.assertEqual((result.revision, result.schedule_enabled, result.updated_at), ("4", True, NOW))
        self.assertEqual(result.setup_completed_at, SAVED)

    def test_first_save_completes_setup(self):
        result, calls = self.run_update(UNSET, tags=('"settings-0"',))
        self.assertEqual((result.revision, result.setup_completed_at, result.updated_at), ("1", NOW, NOW))

    def test_dependency_failure_adds_retry_after(self):
        def broken(connection):
            raise Problem(503, "dependency_unavailable")
        with patch("trinity.refresh.service._authorize", lambda *a, **k: Principal("u", "admin", uuid4())), \
                patch("trinity.settings.service.lock_settings", broken):
            with self.assertRaises(Problem) as caught:
                SettingsService(FakeDatabase()).update(TOKEN, RAW, ['"settings-3"'])
        self.assertEqual((caught.exception.status, caught.exception.retry_after), (503, 1))


def lifecycle_context(code=None):
    """Return an object shaped like AdminContext with an optional blocker."""
    blocker = None if code is None else Blocker(code=code, message="Generic.", run_id=uuid4(),
                                               version_id=uuid4(), warning_id=uuid4())
    return SimpleNamespace(refresh_blocker=blocker)


class BlockerTests(unittest.TestCase):
    def test_priority_ids_and_messages(self):
        self.assertEqual(choose_blocker(UNSET, lifecycle_context("refresh_active")).code, "setup_required")
        disabled = choose_blocker(settings_row(schedule_enabled=False), lifecycle_context("failure_unresolved"))
        self.assertEqual((disabled.code, disabled.run_id, disabled.warning_id), ("schedule_disabled", None, None))
        for code in ("refresh_active", "review_required", "publication_in_progress", "failure_unresolved"):
            with self.subTest(code=code):
                context = lifecycle_context(code)
                blocker = choose_blocker(settings_row(), context)
                self.assertEqual(blocker.code, code)
                self.assertEqual(blocker.message, BLOCKER_MESSAGES[code])
                self.assertEqual((blocker.run_id, blocker.version_id, blocker.warning_id),
                                 (context.refresh_blocker.run_id, context.refresh_blocker.version_id,
                                  context.refresh_blocker.warning_id))
        self.assertIsNone(choose_blocker(settings_row(), lifecycle_context()))


class StatusTests(unittest.TestCase):
    def status(self, row, run=None):
        with patch("trinity.settings.service.read_settings", lambda connection: row), \
                patch("trinity.settings.service.database_now", lambda connection: NOW), \
                patch("trinity.refresh.repository.read_context", lambda connection: (run, None, None, None, None)):
            return schedule_status(Principal("u", "admin", None), object())

    def test_enabled_idle(self):
        result = self.status(settings_row())
        self.assertTrue(result.eligible_now)
        self.assertIsNone(result.blocker)
        self.assertEqual(result.next_check_local, "2026-10-06T06:15:00-04:00")
        self.assertEqual(result.evaluated_at, NOW)

    def test_disabled_and_unset_have_no_next_check(self):
        for row, code in ((settings_row(schedule_enabled=False), "schedule_disabled"), (UNSET, "setup_required")):
            with self.subTest(code=code):
                result = self.status(row)
                self.assertEqual((result.next_check_at, result.next_check_local, result.blocker.code),
                                 (None, None, code))
                self.assertFalse(result.eligible_now)

    def test_blocked_schedule_still_reports_next_check(self):
        run = {"id": uuid4(), "status": "running", "requested_at": SAVED, "finished_at": None}
        result = self.status(settings_row(), run)
        self.assertEqual(result.blocker.code, "refresh_active")
        self.assertEqual(result.blocker.run_id, run["id"])
        self.assertIsNotNone(result.next_check_at)

    def test_viewer_is_denied_before_reads(self):
        with patch("trinity.settings.service.read_settings", side_effect=AssertionError("protected read")):
            with self.assertRaises(Problem) as caught:
                schedule_status(Principal("u", "viewer", None), object())
        self.assertEqual(caught.exception.status, 403)


class Identity:
    """Supply a controlled principal to the real route dependencies."""

    def __init__(self, role="admin"):
        self.role = role
        self.database = None

    @contextmanager
    def authenticated(self, token):
        if token != TOKEN:
            raise Problem(401, "invalid_session")
        yield Principal("user_example_admin", self.role, None), object()


class FakeSettingsService:
    """Return a fixed committed response and record the raw route input."""

    def __init__(self):
        self.calls = []

    def update(self, token, raw, if_match, pairs):
        self.calls.append((token, raw, if_match, pairs))
        return SettingsResponse(setup_completed_at=SAVED, schedule_enabled=True, daily_time="06:15",
                                timezone="America/New_York", revision="4", updated_at=NOW,
                                updated_by="user_example_admin")


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.settings = FakeSettingsService()
        self.identity = Identity()
        self.context = TestClient(create_app(service=self.identity, settings_service=self.settings))
        self.client = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)

    def put(self, headers=None, **kwargs):
        merged = {**HEADERS, "Content-Type": "application/json", "If-Match": '"settings-3"', **(headers or {})}
        return self.client.put("/api/v1/settings", headers=merged, **kwargs)

    def test_put_returns_exact_response_and_etag(self):
        response = self.put(content=RAW)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["etag"], '"settings-4"')
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("x-request-id", response.headers)
        schema = OPENAPI["components"]["schemas"]["SettingsResponse"]
        self.assertEqual(set(response.json()), set(schema["properties"]))
        self.assertEqual(response.json()["updated_at"], "2026-10-05T12:00:00Z")
        self.assertEqual(self.settings.calls, [(TOKEN, RAW, ['"settings-3"'], [])])

    def test_transport_rejections_happen_before_the_service(self):
        self.assertEqual(self.put(headers={"Content-Type": "text/plain"}, content=RAW).status_code, 415)
        self.assertEqual(self.client.put("/api/v1/settings?x=1", headers={**HEADERS, "Content-Type": "application/json"},
                                         content=RAW).status_code, 422)
        self.assertEqual(self.put(content=b" " * 70000).status_code, 413)
        self.assertEqual(self.client.put("/api/v1/settings", headers={"Content-Type": "application/json"},
                                         content=RAW).status_code, 401)
        self.assertEqual(self.settings.calls, [])

    def test_status_route_shape_and_denials(self):
        with patch("trinity.settings.service.read_settings", lambda connection: settings_row()), \
                patch("trinity.settings.service.database_now", lambda connection: NOW), \
                patch("trinity.refresh.repository.read_context", lambda connection: (None,) * 5):
            response = self.client.get("/api/v1/settings/schedule-status", headers=HEADERS)
            self.assertEqual(response.status_code, 200)
            schema = OPENAPI["components"]["schemas"]["ScheduleStatus"]
            self.assertEqual(set(response.json()), set(schema["properties"]))
            self.assertEqual(response.json()["next_check_at"], "2026-10-06T10:15:00Z")
            self.assertEqual(response.json()["evaluated_at"], "2026-10-05T12:00:00Z")
            self.assertEqual(self.client.get("/api/v1/settings/schedule-status?x=1", headers=HEADERS).status_code, 422)
            for role in ("viewer", "analyst"):
                self.identity.role = role
                self.assertEqual(self.client.get("/api/v1/settings/schedule-status", headers=HEADERS).status_code, 403)


if __name__ == "__main__":
    unittest.main()
