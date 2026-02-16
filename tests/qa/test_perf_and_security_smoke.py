from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from apps.api.main import app
from apps.domain.b2b_auth import b2b_auth_service
from apps.infra.models import create_core_schema, drop_core_schema
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from fastapi.testclient import TestClient

_ARTIFACT_DIR = Path("artifacts/qa")
_DEFAULT_P95_THRESHOLD_MS = 500.0


def _p95(samples_ms: list[float]) -> float:
    if not samples_ms:
        return 0.0
    ordered = sorted(samples_ms)
    index = max(0, int(len(ordered) * 0.95) - 1)
    return round(ordered[index], 2)


def _write_artifact(filename: str, payload: dict[str, object]) -> None:
    _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (_ARTIFACT_DIR / filename).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


class PerfAndSecuritySmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="qa-smoke-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/qa_smoke.sqlite"
        os.environ["JWT_SECRET"] = "qa-smoke-secret"
        os.environ["B2B_API_KEYS_JSON"] = json.dumps(
            [
                {
                    "key": "qa-live-key",
                    "tenant_id": "qa-tenant",
                    "rate_limit_per_minute": 2,
                    "expires_at_utc": "2099-01-01T00:00:00Z",
                }
            ]
        )

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-qa-smoke")
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

    def test_core_api_p95_smoke(self) -> None:
        threshold_ms = float(os.getenv("QA_API_P95_THRESHOLD_MS", str(_DEFAULT_P95_THRESHOLD_MS)))
        iterations = int(os.getenv("QA_API_P95_ITERATIONS", "20"))
        endpoints = ["/health", "/v1/events?size=20", "/v1/watchlists/items?page=1&size=20"]

        summary: dict[str, dict[str, float | int]] = {}
        for endpoint in endpoints:
            samples_ms: list[float] = []
            for _ in range(iterations):
                started = time.perf_counter()
                response = self.client.get(endpoint)
                elapsed_ms = (time.perf_counter() - started) * 1000
                samples_ms.append(elapsed_ms)
                self.assertLess(response.status_code, 500)

            endpoint_p95 = _p95(samples_ms)
            summary[endpoint] = {
                "count": len(samples_ms),
                "p95_ms": endpoint_p95,
                "max_ms": round(max(samples_ms), 2),
            }
            self.assertLessEqual(
                endpoint_p95,
                threshold_ms,
                msg=f"{endpoint} p95 {endpoint_p95}ms exceeded threshold {threshold_ms}ms",
            )

        _write_artifact(
            "perf_smoke.json",
            {
                "threshold_ms": threshold_ms,
                "iterations": iterations,
                "summary": summary,
            },
        )

    def test_security_auth_and_rate_limit_regression(self) -> None:
        auth_missing = self.client.get("/v1/auth/me")
        self.assertEqual(auth_missing.status_code, 401)
        self.assertEqual(auth_missing.json()["code"], "invalid_token")

        b2b_missing = self.client.get("/v1/b2b/events/summary")
        self.assertEqual(b2b_missing.status_code, 401)
        self.assertEqual(b2b_missing.json()["code"], "invalid_api_key")

        headers = {"X-API-Key": "qa-live-key"}
        b2b_auth_service.reset_rate_limits()
        first = self.client.get("/v1/b2b/ping", headers=headers)
        second = self.client.get("/v1/b2b/ping", headers=headers)
        third = self.client.get("/v1/b2b/ping", headers=headers)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third.json()["code"], "rate_limit_exceeded")
        self.assertIn("retry-after", third.headers)

        _write_artifact(
            "security_smoke.json",
            {
                "auth_missing": auth_missing.status_code,
                "b2b_missing": b2b_missing.status_code,
                "rate_limit_statuses": [first.status_code, second.status_code, third.status_code],
                "retry_after": third.headers.get("retry-after"),
            },
        )


if __name__ == "__main__":
    unittest.main()
