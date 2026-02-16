from __future__ import annotations

import json
import os
import tempfile
import unittest

from apps.api.main import app
from apps.worker.detection import detect_price_event
from apps.infra.models import create_core_schema, drop_core_schema
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from fastapi.testclient import TestClient


class RequestIdLoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="request-id-logging-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/request_id.sqlite"
        os.environ["JWT_SECRET"] = "logging-secret"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-logging-setup")
        create_core_schema(self.runtime.engine)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_api_success_logs_are_structured_and_mask_sensitive_fields(self) -> None:
        with self.assertLogs("oh_my_stock.api", level="INFO") as captured:
            response = self.client.post(
                "/v1/auth/signup",
                json={"email": "masking@example.com", "password": "masking-password"},
                headers={"X-Request-ID": "req-api-success"},
            )

        self.assertEqual(response.status_code, 201)
        payloads = self._parse_payloads(captured.output)

        requested = self._find_event(payloads, "auth_signup_requested")
        succeeded = self._find_event(payloads, "auth_signup_succeeded")
        for payload in (requested, succeeded):
            self.assertIn("ts", payload)
            self.assertIn("level", payload)
            self.assertIn("request_id", payload)
            self.assertIn("feature", payload)
            self.assertEqual(payload["request_id"], "req-api-success")

        self.assertEqual(requested["email"], "m***@example.com")
        self.assertEqual(requested["password"], "***")
        self.assertEqual(succeeded["access_token"], "***")
        self.assertEqual(succeeded["feature"], "auth-001")

    def test_api_failure_logs_include_request_id(self) -> None:
        self.client.post(
            "/v1/auth/signup",
            json={"email": "login-log@example.com", "password": "valid-password"},
        )

        with self.assertLogs("oh_my_stock.api", level="ERROR") as captured:
            response = self.client.post(
                "/v1/auth/login",
                json={"email": "login-log@example.com", "password": "wrong-password"},
                headers={"X-Request-ID": "req-api-failure"},
            )

        self.assertEqual(response.status_code, 401)
        payloads = self._parse_payloads(captured.output)
        failed = self._find_event(payloads, "auth_login_failed")

        self.assertEqual(failed["level"], "error")
        self.assertEqual(failed["request_id"], "req-api-failure")
        self.assertEqual(failed["feature"], "auth-001")
        self.assertEqual(failed["email"], "l***@example.com")

    def test_worker_logs_are_structured_and_include_request_id(self) -> None:
        with self.assertLogs("oh_my_stock.worker", level="INFO") as captured_success:
            event = detect_price_event(
                symbol="AAPL",
                market="US",
                baseline_price=100.0,
                current_price=104.0,
                window_minutes=5,
                detected_at_utc="2026-02-17T00:00:00Z",
                request_id="req-worker-success",
            )
        self.assertIsNotNone(event)
        success_payloads = self._parse_payloads(captured_success.output)
        succeeded = self._find_event(success_payloads, "worker_detection_succeeded")
        self.assertEqual(succeeded["request_id"], "req-worker-success")
        self.assertEqual(succeeded["feature"], "ops-003")
        self.assertEqual(succeeded["level"], "info")

        with self.assertLogs("oh_my_stock.worker", level="ERROR") as captured_failure:
            with self.assertRaises(ValueError):
                detect_price_event(
                    symbol="AAPL",
                    market="JP",
                    baseline_price=100.0,
                    current_price=104.0,
                    window_minutes=5,
                    detected_at_utc="2026-02-17T00:01:00Z",
                    request_id="req-worker-failure",
                )

        failure_payloads = self._parse_payloads(captured_failure.output)
        failed = self._find_event(failure_payloads, "worker_detection_failed")
        self.assertEqual(failed["request_id"], "req-worker-failure")
        self.assertEqual(failed["feature"], "ops-003")
        self.assertEqual(failed["level"], "error")

    def _parse_payloads(self, output: list[str]) -> list[dict[str, object]]:
        payloads: list[dict[str, object]] = []
        for line in output:
            json_start = line.find("{")
            if json_start < 0:
                raise AssertionError(f"log line missing json payload: {line!r}")
            payloads.append(json.loads(line[json_start:]))
        return payloads

    def _find_event(self, payloads: list[dict[str, object]], event: str) -> dict[str, object]:
        for payload in payloads:
            if payload.get("event") == event:
                return payload
        raise AssertionError(f"event '{event}' not found in logs: {payloads!r}")


if __name__ == "__main__":
    unittest.main()
