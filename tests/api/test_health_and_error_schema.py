from __future__ import annotations

import unittest

from apps.api.main import app
from fastapi.testclient import TestClient


class HealthAndErrorSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_endpoint_returns_ok(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertIn("x-request-id", response.headers)

    def test_not_found_uses_standard_error_schema(self) -> None:
        response = self.client.get("/v1/unknown", headers={"X-Request-ID": "req-test-404"})
        body = response.json()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(body["code"], "not_found")
        self.assertEqual(body["request_id"], "req-test-404")
        self.assertIn("message", body)
        self.assertIn("details", body)

    def test_method_not_allowed_uses_standard_error_schema(self) -> None:
        response = self.client.post("/health")
        body = response.json()

        self.assertEqual(response.status_code, 405)
        self.assertEqual(body["code"], "method_not_allowed")
        self.assertTrue(body["request_id"])
        self.assertIn("message", body)
        self.assertIn("details", body)


if __name__ == "__main__":
    unittest.main()
