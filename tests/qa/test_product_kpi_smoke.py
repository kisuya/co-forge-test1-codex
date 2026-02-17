from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from apps.api.main import app
from apps.domain.briefs import brief_inbox_store
from apps.domain.events import price_event_store
from apps.domain.product_kpi import (
    BRIEF_OPEN_RATE,
    CARD_CLICK_RATE,
    EVIDENCE_CLICK_RATE,
    INACCURATE_REASON_REPORT_RATE,
    ProductKpiCollector,
    build_product_kpi_snapshot,
)
from apps.domain.reason_reports import reason_report_store
from apps.domain.reasons import event_reason_store
from apps.infra.models import create_core_schema, drop_core_schema
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from apps.worker.detection import detect_price_event
from apps.worker.reason_reevaluation_queue import reason_reevaluation_queue
from apps.worker.reasons import rank_event_reasons
from fastapi.testclient import TestClient

_ARTIFACT_DIR = Path("artifacts/qa")
_ARTIFACT_PATH = _ARTIFACT_DIR / "product_kpi_smoke.json"
_DEFAULT_MIN_SAMPLES = 2


def _write_artifact(payload: dict[str, object]) -> None:
    _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _ARTIFACT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_previous_artifact() -> dict[str, object] | None:
    if not _ARTIFACT_PATH.exists():
        return None
    try:
        loaded = json.loads(_ARTIFACT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


class ProductKpiSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="qa-product-kpi-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/qa_product_kpi.sqlite"
        os.environ["JWT_SECRET"] = "qa-product-kpi-secret"
        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-qa-product-kpi")
        create_core_schema(self.runtime.engine)
        brief_inbox_store.clear()
        price_event_store.clear()
        event_reason_store.clear()
        reason_report_store.clear()
        reason_reevaluation_queue.clear()
        self.client = TestClient(app)
        user = self.client.post(
            "/v1/auth/signup",
            json={"email": "kpi-smoke@example.com", "password": "kpi-smoke-password"},
        ).json()
        self.user_id = user["user_id"]
        self.user_email = "kpi-smoke@example.com"
        self.headers = {"Authorization": f"Bearer {user['access_token']}"}
        self.event_ids = self._seed_events_and_reasons()
        self.reason_id = event_reason_store.list_by_event(self.event_ids[0])[0].id
        self.brief_ids = self._seed_briefs()

    def tearDown(self) -> None:
        reason_reevaluation_queue.clear()
        reason_report_store.clear()
        event_reason_store.clear()
        price_event_store.clear()
        brief_inbox_store.clear()
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_product_kpi_snapshot_smoke_and_artifact_output(self) -> None:
        previous_snapshot = build_product_kpi_snapshot(
            metric_samples={
                CARD_CLICK_RATE: {"numerator": 2, "denominator": 4},
                EVIDENCE_CLICK_RATE: {"numerator": 1, "denominator": 2},
                INACCURATE_REASON_REPORT_RATE: {"numerator": 1, "denominator": 2},
                BRIEF_OPEN_RATE: {"numerator": 1, "denominator": 4},
            },
            min_samples=_DEFAULT_MIN_SAMPLES,
            generated_at_utc="2026-02-16T00:00:00Z",
        )
        _write_artifact(previous_snapshot)
        collector = ProductKpiCollector()
        list_response = self.client.get("/v1/events?size=20")
        self.assertEqual(list_response.status_code, 200)
        item_count = len(list_response.json()["items"])
        self.assertGreaterEqual(item_count, 2)
        collector.record_card_impression(count=item_count)
        collector.record_card_impression(count=item_count)
        detail_responses = [
            self.client.get(f"/v1/events/{self.event_ids[0]}"),
            self.client.get(f"/v1/events/{self.event_ids[1]}"),
            self.client.get(f"/v1/events/{self.event_ids[0]}"),
        ]
        card_clicks = sum(1 for response in detail_responses if response.status_code == 200)
        collector.record_card_click(count=card_clicks)
        evidence_impressions = 0
        clicked_sources: set[str] = set()
        for response in detail_responses:
            self.assertEqual(response.status_code, 200)
            reasons = response.json()["event"]["reasons"]
            evidence_impressions += len(reasons)
            source_url = str(reasons[0]["source_url"] or "").strip()
            if source_url:
                clicked_sources.add(source_url)
        collector.record_evidence_impression(count=evidence_impressions)
        collector.record_evidence_click(count=len(clicked_sources))
        collector.record_reason_impression(count=evidence_impressions)
        report_response = self.client.post(
            f"/v1/events/{self.event_ids[0]}/reason-reports",
            json={
                "reason_id": self.reason_id,
                "report_type": "inaccurate_reason",
                "note": "QA smoke: source context mismatch",
            },
            headers=self.headers,
        )
        self.assertEqual(report_response.status_code, 201)
        collector.record_inaccurate_reason_report(count=1)
        brief_list_response = self.client.get("/v1/briefs", headers=self.headers)
        self.assertEqual(brief_list_response.status_code, 200)
        self.assertEqual(brief_list_response.json()["count"], 2)
        collector.record_brief_delivered(count=brief_list_response.json()["count"])
        read_response = self.client.patch(f"/v1/briefs/{self.brief_ids[0]}/read", headers=self.headers)
        self.assertEqual(read_response.status_code, 200)
        collector.record_brief_opened(count=1)
        min_samples = int(os.getenv("QA_PRODUCT_KPI_MIN_SAMPLES", str(_DEFAULT_MIN_SAMPLES)))
        snapshot = collector.build_snapshot(
            min_samples=min_samples,
            previous_snapshot=_load_previous_artifact(),
            generated_at_utc="2026-02-17T11:00:00Z",
        )
        _write_artifact(snapshot)
        self.assertTrue(_ARTIFACT_PATH.exists())
        self.assertFalse(snapshot["overall_low_confidence"])
        metrics = snapshot["metrics"]
        self.assertEqual(metrics[CARD_CLICK_RATE]["numerator"], 3)
        self.assertEqual(metrics[CARD_CLICK_RATE]["denominator"], 4)
        self.assertEqual(metrics[CARD_CLICK_RATE]["value"], 0.75)
        self.assertEqual(metrics[CARD_CLICK_RATE]["previous_value"], 0.5)
        self.assertEqual(metrics[CARD_CLICK_RATE]["delta"], 0.25)
        self.assertEqual(metrics[EVIDENCE_CLICK_RATE]["numerator"], 2)
        self.assertEqual(metrics[EVIDENCE_CLICK_RATE]["denominator"], 3)
        self.assertEqual(metrics[EVIDENCE_CLICK_RATE]["value"], 0.6667)
        self.assertEqual(metrics[EVIDENCE_CLICK_RATE]["previous_value"], 0.5)
        self.assertEqual(metrics[EVIDENCE_CLICK_RATE]["delta"], 0.1667)
        self.assertEqual(metrics[INACCURATE_REASON_REPORT_RATE]["numerator"], 1)
        self.assertEqual(metrics[INACCURATE_REASON_REPORT_RATE]["denominator"], 3)
        self.assertEqual(metrics[INACCURATE_REASON_REPORT_RATE]["value"], 0.3333)
        self.assertEqual(metrics[INACCURATE_REASON_REPORT_RATE]["previous_value"], 0.5)
        self.assertEqual(metrics[INACCURATE_REASON_REPORT_RATE]["delta"], -0.1667)
        self.assertEqual(metrics[BRIEF_OPEN_RATE]["numerator"], 1)
        self.assertEqual(metrics[BRIEF_OPEN_RATE]["denominator"], 2)
        self.assertEqual(metrics[BRIEF_OPEN_RATE]["value"], 0.5)
        self.assertEqual(metrics[BRIEF_OPEN_RATE]["previous_value"], 0.25)
        self.assertEqual(metrics[BRIEF_OPEN_RATE]["delta"], 0.25)
        artifact_text = _ARTIFACT_PATH.read_text(encoding="utf-8")
        self.assertNotIn(self.user_id, artifact_text)
        self.assertNotIn(self.user_email, artifact_text)

    def test_low_confidence_flags_for_missing_delayed_and_low_sample_metrics(self) -> None:
        snapshot = build_product_kpi_snapshot(
            metric_samples={
                CARD_CLICK_RATE: {"numerator": 1, "denominator": 2},
                INACCURATE_REASON_REPORT_RATE: {"numerator": 1, "denominator": 2},
                BRIEF_OPEN_RATE: {"numerator": 4, "denominator": 2},
            },
            min_samples=5,
            delayed_metrics={CARD_CLICK_RATE},
            generated_at_utc="2026-02-17T11:05:00Z",
        )
        metrics = snapshot["metrics"]
        self.assertTrue(snapshot["overall_low_confidence"])
        card_flags = set(metrics[CARD_CLICK_RATE]["flags"])
        self.assertIn("aggregation_delayed", card_flags)
        self.assertIn("sample_shortage", card_flags)
        self.assertTrue(metrics[CARD_CLICK_RATE]["low_confidence"])
        evidence_flags = set(metrics[EVIDENCE_CLICK_RATE]["flags"])
        self.assertIn("metric_missing", evidence_flags)
        self.assertTrue(metrics[EVIDENCE_CLICK_RATE]["low_confidence"])
        self.assertIsNone(metrics[EVIDENCE_CLICK_RATE]["value"])
        report_flags = set(metrics[INACCURATE_REASON_REPORT_RATE]["flags"])
        self.assertEqual(report_flags, {"sample_shortage"})
        self.assertTrue(metrics[INACCURATE_REASON_REPORT_RATE]["low_confidence"])
        brief_flags = set(metrics[BRIEF_OPEN_RATE]["flags"])
        self.assertIn("aggregation_delayed", brief_flags)
        self.assertIn("sample_shortage", brief_flags)
        self.assertEqual(metrics[BRIEF_OPEN_RATE]["value"], 1.0)
        self.assertTrue(metrics[BRIEF_OPEN_RATE]["low_confidence"])

    def _seed_events_and_reasons(self) -> list[str]:
        aapl = detect_price_event(
            symbol="AAPL",
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc="2026-02-16T12:00:00Z",
        )
        tsla = detect_price_event(
            symbol="TSLA",
            market="US",
            baseline_price=200.0,
            current_price=210.0,
            window_minutes=5,
            detected_at_utc="2026-02-16T12:10:00Z",
        )
        assert aapl is not None
        assert tsla is not None
        rank_event_reasons(
            event_id=aapl["id"],
            detected_at_utc=aapl["detected_at_utc"],
            candidates=[
                {
                    "reason_type": "news",
                    "summary": "Apple unveils updated guidance",
                    "source_url": "https://news.example/aapl-guidance",
                    "published_at": aapl["detected_at_utc"],
                }
            ],
        )
        rank_event_reasons(
            event_id=tsla["id"],
            detected_at_utc=tsla["detected_at_utc"],
            candidates=[
                {
                    "reason_type": "filing",
                    "summary": "Tesla filing published",
                    "source_url": "https://sec.example/tesla-filing",
                    "published_at": tsla["detected_at_utc"],
                }
            ],
        )
        return [aapl["id"], tsla["id"]]

    def _seed_briefs(self) -> list[str]:
        brief_specs = [
            {
                "brief_id": "brief-pre-kpi-1",
                "user_id": self.user_id,
                "brief_type": "pre_market",
                "title": "장 시작 전 체크",
                "summary": "AAPL 이벤트 점검",
                "generated_at_utc": "2026-02-17T00:10:00Z",
                "markets": ["US"],
                "items": [
                    {
                        "event_id": self.event_ids[0],
                        "symbol": "AAPL",
                        "market": "US",
                        "summary": "변동성 확대",
                        "event_detail_url": f"/events/{self.event_ids[0]}",
                        "source_url": "https://news.example/aapl-guidance",
                    }
                ],
                "status": "unread",
            },
            {
                "brief_id": "brief-post-kpi-1",
                "user_id": self.user_id,
                "brief_type": "post_close",
                "title": "장 마감 요약",
                "summary": "TSLA 이벤트 요약",
                "generated_at_utc": "2026-02-17T09:10:00Z",
                "markets": ["US"],
                "items": [
                    {
                        "event_id": self.event_ids[1],
                        "symbol": "TSLA",
                        "market": "US",
                        "summary": "근거 업데이트",
                        "event_detail_url": f"/events/{self.event_ids[1]}",
                        "source_url": "https://sec.example/tesla-filing",
                    }
                ],
                "status": "unread",
            },
        ]
        for brief in brief_specs:
            brief_inbox_store.upsert_brief(**brief)
        return [str(brief["brief_id"]) for brief in brief_specs]

if __name__ == "__main__":
    unittest.main()
