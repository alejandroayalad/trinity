"""Offline regressions for permissions, credential bounds and safe HTTP errors."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import unittest
from unittest.mock import patch

from fastapi import Depends
from fastapi.testclient import TestClient
from trinity.adapters.postgres import Deadline
from trinity.auth.dependencies import require_capability
from trinity.auth.passwords import hash_password, verify_password, _verify
from trinity.auth.permissions import Principal, capabilities, require, require_dataset
from trinity.config import ApiSettings, ConfigurationError, load_api_settings
from trinity.errors import Problem, SafeTransport
from trinity.main import create_app


class PolicyTests(unittest.TestCase):
    def test_exact_canonical_capabilities(self):
        doc = json.loads((Path(__file__).resolve().parents[2] / "docs/openapi.json").read_text())
        self.assertEqual(set(capabilities("admin")), set(doc["components"]["schemas"]["Capability"]["enum"]))
        self.assertEqual([len(capabilities(r)) for r in ("viewer", "analyst", "admin")], [3, 5, 11])

    def test_policy_matrix_and_safe_dataset_denials(self):
        for role in ("viewer", "analyst", "admin"):
            actor = Principal("synthetic", role, None)
            for key in ("national", "facility", "generator", "unknown"):
                allowed = key == "national" or (role != "viewer" and key in ("facility", "generator"))
                if allowed:
                    require_dataset(actor, key)
                else:
                    with self.assertRaises(Problem) as caught:
                        require_dataset(actor, key)
                    self.assertEqual((caught.exception.status, caught.exception.code), (404, "dataset_not_found"))
        for role in (None, "owner", "ADMIN"):
            with self.assertRaises(Problem):
                capabilities(role)

    def test_unknown_capability_denies(self):
        with self.assertRaises(Problem):
            require(Principal("x", "admin", None), "imaginary:write")


class PasswordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = secrets.token_urlsafe(24) + "é"
        cls.encoded = hash_password(cls.password)

    def test_scrypt_roundtrip_distinct_salts_and_unicode(self):
        self.assertTrue(verify_password(self.password, self.encoded, Deadline()))
        self.assertFalse(verify_password(self.password + "x", self.encoded, Deadline()))
        self.assertNotEqual(hash_password(self.password), self.encoded)
        self.assertNotIn(self.password, self.encoded)

    def test_untrusted_hash_parameters_never_run(self):
        self.assertFalse(_verify("x", "scrypt-v1$999999999$8$1$invalid"))
        self.assertFalse(_verify("x", "scrypt-v1$131072$8$1$bad$bad"))

    def test_expired_hash_budget_reaps_child(self):
        import multiprocessing
        before = {p.pid for p in multiprocessing.active_children()}
        with self.assertRaises(Problem):
            verify_password(self.password, self.encoded, Deadline(0))
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)

    def test_hash_concurrency_rejects_before_spawn(self):
        with patch("trinity.auth.passwords._SLOTS") as slots:
            slots.acquire.return_value = False
            with self.assertRaises(Problem) as caught:
                verify_password("x", self.encoded, Deadline())
        self.assertEqual(caught.exception.status, 429)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.client_context = TestClient(create_app(service=object()))
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)

    def assert_problem(self, response, status, code):
        self.assertEqual(response.status_code, status)
        data = response.json()
        self.assertEqual(data["code"], code)
        self.assertEqual(set(data), {"type", "title", "status", "detail", "code", "request_id",
                                     "errors", "blocker", "current_revision"})
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-request-id"], data["request_id"])
        self.assertTrue(response.headers["content-type"].startswith("application/problem+json"))

    def test_invalid_identity_and_duplicate_headers(self):
        self.assert_problem(self.client.get("/api/v1/me"), 401, "authentication_required")
        for token in ("Basic x", "Bearer admin", "Bearer " + "x" * 4200):
            response = self.client.get("/api/v1/me", headers={"Authorization": token})
            self.assert_problem(response, 401, "invalid_session")
            self.assertEqual(response.headers["www-authenticate"], "Bearer")
        response = self.client.get("/api/v1/me", headers=[("Authorization", "Bearer " + "x" * 43)] * 2)
        self.assert_problem(response, 401, "invalid_session")

    def test_validation_never_reflects_values_or_unknown_names(self):
        canary = "private-secret-canary"
        for body in ({"username": "viewer", "password": canary, canary: "admin"},
                     {"username": [], "password": canary}, {"username": "viewer", "password": 42}):
            response = self.client.post("/api/v1/auth/login", json=body)
            self.assert_problem(response, 422, "invalid_request")
            self.assertNotIn(canary, response.text)
            for error in response.json()["errors"]:
                self.assertEqual(set(error), {"field", "code", "message"})

    def test_media_json_body_and_query_errors(self):
        self.assert_problem(self.client.post("/api/v1/auth/login", content="x"), 415, "unsupported_media_type")
        self.assert_problem(self.client.post("/api/v1/auth/login", content="{", headers={"content-type":"application/json"}), 400, "invalid_json")
        self.assert_problem(self.client.request("GET", "/api/v1/me", content="{}"), 422, "invalid_request")
        self.assert_problem(self.client.get("/api/v1/me?role=admin"), 422, "invalid_request")
        self.assert_problem(self.client.post("/api/v1/auth/login", content=b"x"*65537,
                                            headers={"content-type":"application/json"}), 413, "request_too_large")

    def test_unexpected_exceptions_are_contained(self):
        class Broken:
            def login(self, *args):
                raise RuntimeError("private-exception-canary")
        with TestClient(create_app(service=Broken())) as client:
            response = client.post("/api/v1/auth/login", json={"username":"viewer","password":"x"})
        self.assert_problem(response, 500, "internal_error")
        self.assertNotIn("private-exception-canary", response.text)

    def test_byte_limit_is_checked_on_chunks_without_content_length(self):
        invoked = []
        async def app(scope, receive, send):
            invoked.append(True)
        events = iter([{"type":"http.request","body":b"x"*33000,"more_body":True},
                       {"type":"http.request","body":b"x"*33000,"more_body":False}])
        output = []
        async def receive(): return next(events)
        async def send(message): output.append(message)
        asyncio.run(SafeTransport(app)({"type":"http","method":"POST","headers":[],"query_string":b""}, receive, send))
        self.assertFalse(invoked)
        self.assertEqual(output[0]["status"], 413)

    def test_analyst_guard_uses_production_dependencies_only_in_test_app(self):
        class Stub:
            role = "viewer"
            @contextmanager
            def authenticated(self, token):
                yield Principal("synthetic", self.role, None), None
        service = Stub()
        app = create_app(service=service)
        @app.get("/test-sql-guard")
        def guard(context=Depends(require_capability("sql:execute"))):
            return {"allowed":True}
        with TestClient(app) as client:
            for role, status in (("viewer",403),("analyst",200),("admin",200)):
                service.role=role
                self.assertEqual(client.get("/test-sql-guard",headers={"Authorization":"Bearer "+"x"*43}).status_code,status)
        self.assertNotIn("/test-sql-guard", create_app(service=object()).openapi()["paths"])


class ApiConfigTests(unittest.TestCase):
    def test_missing_and_secret_bearing_invalid_configuration(self):
        for values in ({}, {"TRINITY_DATABASE_URL":"private-canary"}):
            with patch.dict("os.environ", values, clear=True):
                with self.assertRaises(ConfigurationError) as caught:
                    load_api_settings()
            self.assertNotIn("private-canary", str(caught.exception))

    def test_import_and_app_creation_require_no_configuration(self):
        with patch.dict("os.environ", {}, clear=True):
            create_app()

    def test_real_startup_requires_api_configuration(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ConfigurationError):
                with TestClient(create_app()):
                    pass


class AvailabilityTests(unittest.TestCase):
    def test_unavailable_database_preserves_health_and_fails_auth_closed(self):
        from trinity.config import ApiSettings
        # A nonexistent Unix socket cannot accidentally reach an unrelated DB.
        settings=ApiSettings(TRINITY_DATABASE_URL='postgresql://nobody@/absent?host=/tmp/trinity-no-such-socket')
        with TestClient(create_app(settings=settings)) as client:
            self.assertEqual(client.get('/health').status_code,200)
            response=client.get('/api/v1/me',headers={'Authorization':'Bearer '+'x'*43})
        self.assertEqual((response.status_code,response.json()['code']),(503,'auth_unavailable'))
        self.assertNotIn('trinity-no-such-socket',response.text)


class CorruptIdentityTests(unittest.TestCase):
    def test_unknown_stored_role_is_denied_by_real_resolver(self):
        from types import SimpleNamespace
        from trinity.auth.repository import resolve_session
        for role in (None,'owner'):
            connection=SimpleNamespace(execute=lambda *args:SimpleNamespace(fetchone=lambda:{
                'session_id':None,'user_id':'synthetic','role':role}))
            with self.assertRaises(Problem) as caught:
                resolve_session(connection,'x'*43)
            self.assertEqual((caught.exception.status,caught.exception.code),(403,'forbidden'))
