"""Smoke checks for HTTP startup and the scaffold's exposed surface."""

import unittest

from fastapi.testclient import TestClient

from trinity.main import create_app


class HealthTests(unittest.TestCase):
    def test_health_returns_process_liveness(self) -> None:
        with TestClient(create_app()) as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_scaffold_exposes_no_product_operations(self) -> None:
        with TestClient(create_app()) as client:
            schema = client.get("/openapi.json").json()
            response = client.get("/api/v1/me")
        self.assertEqual(set(schema["paths"]), {"/health"})
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
