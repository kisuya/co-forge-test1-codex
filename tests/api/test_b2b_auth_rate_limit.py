from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest

from apps.api.main import app
from apps.domain.b2b_auth import b2b_auth_service
from apps.infra.models import create_core_schema, drop_core_schema
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from fastapi.testclient import TestClient


class B2BAuthRateLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="b2b-auth-rate-limit-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/b2b.sqlite"
        os.environ["B2B_API_KEYS_JSON"] = json.dumps(
            [
                {
                    "key": "live-b2b-key",
                    "tenant_id": "tenant-a",
                    "rate_limit_per_minute": 2,
                    "expires_at_utc": "2099-01-01T00:00:00Z",
                },
                {
                    "key": "expired-b2b-key",
                    "tenant_id": "tenant-a",
                    "rate_limit_per_minute": 2,
                    "expires_at_utc": "2020-01-01T00:00:00Z",
                },
            ]
        )

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-b2b-setup")
        create_core_schema(self.runtime.engine)
        b2b_auth_service.reset_rate_limits()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        b2b_auth_service.reset_rate_limits()
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_missing_or_expired_key_returns_401(self) -> None:
        missing = self.client.get("/v1/b2b/ping")
        expired = self.client.get(
            "/v1/b2b/ping",
            headers={"X-API-Key": "expired-b2b-key"},
        )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(missing.json()["code"], "invalid_api_key")
        self.assertEqual(expired.status_code, 401)
        self.assertEqual(expired.json()["code"], "invalid_api_key")

    def test_valid_key_is_authenticated(self) -> None:
        response = self.client.get(
            "/v1/b2b/ping",
            headers={"X-API-Key": "live-b2b-key"},
        )
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["tenant_id"], "tenant-a")

    def test_rate_limit_returns_429_with_retry_after_header(self) -> None:
        first = self.client.get("/v1/b2b/ping", headers={"X-API-Key": "live-b2b-key"})
        second = self.client.get("/v1/b2b/ping", headers={"X-API-Key": "live-b2b-key"})
        third = self.client.get("/v1/b2b/ping", headers={"X-API-Key": "live-b2b-key"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third.json()["code"], "rate_limit_exceeded")
        self.assertIn("retry-after", third.headers)
        self.assertGreaterEqual(int(third.headers["retry-after"]), 1)

    def test_logs_key_identifier_without_raw_key(self) -> None:
        expected_key_id = hashlib.sha256("live-b2b-key".encode("utf-8")).hexdigest()[:12]

        with self.assertLogs("oh_my_stock.api", level="INFO") as captured:
            response = self.client.get(
                "/v1/b2b/ping",
                headers={"X-API-Key": "live-b2b-key", "X-Request-ID": "req-b2b-log"},
            )

        self.assertEqual(response.status_code, 200)
        serialized = "\n".join(captured.output)
        self.assertNotIn("live-b2b-key", serialized)

        payloads = self._parse_payloads(captured.output)
        event = self._find_event(payloads, "b2b_authenticated")
        self.assertEqual(event["key_id"], expected_key_id)
        self.assertEqual(event["request_id"], "req-b2b-log")

    def _parse_payloads(self, output: list[str]) -> list[dict[str, object]]:
        payloads: list[dict[str, object]] = []
        for line in output:
            json_start = line.find("{")
            payloads.append(json.loads(line[json_start:]))
        return payloads

    def _find_event(self, payloads: list[dict[str, object]], event: str) -> dict[str, object]:
        for payload in payloads:
            if payload.get("event") == event:
                return payload
        raise AssertionError(f"event '{event}' not found in logs: {payloads!r}")


if __name__ == "__main__":
    unittest.main()
