"""Check liveness separately from protected application availability."""
import unittest
from fastapi.testclient import TestClient
from trinity.main import create_app


class HealthTests(unittest.TestCase):
    def test_health_returns_process_liveness(self):
        with TestClient(create_app(service=object())) as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_surface_contains_only_implemented_product_operations(self):
        with TestClient(create_app(service=object())) as client:
            paths = client.get("/openapi.json").json()["paths"]
            response = client.get("/api/v1/me")
        self.assertEqual(set(paths), {"/health", "/api/v1/auth/login", "/api/v1/auth/logout",
                                     "/api/v1/me", "/api/v1/settings", "/api/v1/catalog"})
        self.assertEqual(response.status_code, 401)
