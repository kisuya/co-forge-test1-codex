from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import tempfile
import unittest

from apps.api.main import app
from apps.domain.b2b_auth import b2b_auth_service
from apps.domain.events import price_event_store
from apps.domain.reasons import event_reason_store
from apps.infra.models import create_core_schema, drop_core_schema
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from apps.worker.detection import detect_price_event
from fastapi.testclient import TestClient


class B2BEventSummaryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="b2b-summary-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/b2b-summary.sqlite"
        os.environ["B2B_API_KEYS_JSON"] = json.dumps(
            [
                {
                    "key": "summary-key",
                    "tenant_id": "tenant-summary",
                    "rate_limit_per_minute": 20,
                    "expires_at_utc": "2099-01-01T00:00:00Z",
                    "allowed_symbols": ["AAPL", "MSFT"],
                }
            ]
        )

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-b2b-summary-setup")
        create_core_schema(self.runtime.engine)
        b2b_auth_service.reset_rate_limits()

        price_event_store.clear()
        event_reason_store.clear()
        self.client = TestClient(app)
        self.now = datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc)

        self._create_event("AAPL", detected_at=self.now - timedelta(hours=1))
        self._create_event("TSLA", detected_at=self.now - timedelta(minutes=30))
        self._create_event("MSFT", detected_at=self.now - timedelta(hours=30))

    def tearDown(self) -> None:
        event_reason_store.clear()
        price_event_store.clear()
        b2b_auth_service.reset_rate_limits()
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_default_window_is_24h_and_scoped_to_tenant_symbols(self) -> None:
        response = self.client.get(
            "/v1/b2b/events/summary?now=2026-02-16T12:00:00Z",
            headers=self._headers(),
        )
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["items"][0]["symbol"], "AAPL")

    def test_unallowed_symbols_are_removed_and_audit_logged(self) -> None:
        with self.assertLogs("oh_my_stock.api", level="INFO") as captured:
            response = self.client.get(
                "/v1/b2b/events/summary?symbols=AAPL,TSLA&now=2026-02-16T12:00:00Z",
                headers=self._headers(),
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["items"][0]["symbol"], "AAPL")

        payloads = self._parse_payloads(captured.output)
        filtered = self._find_event(payloads, "b2b_summary_filtered_symbols")
        self.assertEqual(filtered["removed_symbols"], ["TSLA"])

    def test_limit_above_100_returns_400(self) -> None:
        response = self.client.get(
            "/v1/b2b/events/summary?limit=101",
            headers=self._headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_input")

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": "summary-key"}

    def _create_event(self, symbol: str, *, detected_at: datetime) -> None:
        detect_price_event(
            symbol=symbol,
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc=detected_at,
            session_label="regular",
        )

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
