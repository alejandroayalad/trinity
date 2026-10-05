"""Check liveness separately from protected application availability."""
import unittest
from fastapi.testclient import TestClient
from trinity.main import create_app


class HealthTests(unittest.TestCase):
    def test_health_returns_process_liveness(self):
        # The client calls the app in process. This proves the response contract,
        # not that a deployed server or an external data service is available.
        with TestClient(create_app(service=object())) as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_surface_contains_only_implemented_product_operations(self):
        # Keep the schema limited to implemented routes and require identity for /me.
        with TestClient(create_app(service=object())) as client:
            paths = client.get("/openapi.json").json()["paths"]
            response = client.get("/api/v1/me")
        self.assertEqual(set(paths), {"/health", "/api/v1/auth/login", "/api/v1/auth/logout",
                                     "/api/v1/me", "/api/v1/settings", "/api/v1/settings/schedule-status", "/api/v1/queries", "/api/v1/catalog",
                                     "/api/v1/dashboard/national", "/api/v1/metrics/offline-share",
                                     "/api/v1/datasets/{dataset_key}/preview",
                                     "/api/v1/datasets/{dataset_key}/facilities",
                                     "/api/v1/datasets/{dataset_key}/generators",
                                     "/api/v1/refresh-runs", "/api/v1/refresh-runs/{run_id}",
                                     "/api/v1/refresh-runs/{run_id}/rerun",
                                     "/api/v1/refresh-runs/{run_id}/warning",
                                     "/api/v1/candidates/{version_id}",
                                 "/api/v1/candidates/{version_id}/approval",
                                 "/api/v1/candidates/{version_id}/publication-retry",
                                 "/api/v1/candidates/{version_id}/discard"})
        self.assertEqual(response.status_code, 401)
