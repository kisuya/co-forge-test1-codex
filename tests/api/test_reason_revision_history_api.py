from __future__ import annotations

import os
import tempfile
import unittest

from apps.api.main import app
from apps.domain.events import price_event_store
from apps.domain.reason_reports import reason_report_store
from apps.domain.reasons import event_reason_store
from apps.infra.models import create_core_schema, drop_core_schema, execute_statement
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from apps.worker.detection import detect_price_event
from apps.worker.reason_reevaluation_queue import reason_reevaluation_queue
from apps.worker.reasons import rank_event_reasons
from fastapi.testclient import TestClient


class ReasonRevisionHistoryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="reason-revision-history-api-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/reason_revision_history.sqlite"
        os.environ["JWT_SECRET"] = "reason-revision-history-secret"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-reason-revision-history-setup")
        create_core_schema(self.runtime.engine)

        price_event_store.clear()
        event_reason_store.clear()
        reason_report_store.clear()
        reason_reevaluation_queue.clear()

        self.client = TestClient(app)
        self.owner = self.client.post(
            "/v1/auth/signup",
            json={"email": "revision-owner@example.com", "password": "revision-owner-password"},
        ).json()
        self.viewer = self.client.post(
            "/v1/auth/signup",
            json={"email": "revision-viewer@example.com", "password": "revision-viewer-password"},
        ).json()

        event = detect_price_event(
            symbol="NVDA",
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc="2026-02-16T12:10:00Z",
        )
        assert event is not None
        self.event = event
        self.event_id = event["id"]

        rank_event_reasons(
            event_id=self.event_id,
            detected_at_utc=event["detected_at_utc"],
            candidates=[
                {
                    "reason_type": "news",
                    "summary": "기사 헤드라인",
                    "source_url": "https://news.example/nvda",
                    "published_at": event["detected_at_utc"],
                }
            ],
        )
        self.reason_id = event_reason_store.list_by_event(self.event_id)[0].id

    def tearDown(self) -> None:
        reason_report_store.set_failure_mode(None)
        reason_reevaluation_queue.clear()
        reason_report_store.clear()
        event_reason_store.clear()
        price_event_store.clear()
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_revision_history_returns_transition_log_and_confidence_delta(self) -> None:
        report_id = self._submit_report(self.owner["access_token"])
        reason_report_store.mark_reviewed(report_id=report_id, note="triaged")
        reason_report_store.resolve_report(
            report_id=report_id,
            revision_reason="근거 재검증 후 점수 조정",
            confidence_before=0.71,
            confidence_after=0.46,
            note="resolved",
        )

        response = self.client.get(
            f"/v1/events/{self.event_id}/reason-revisions",
            headers=self._auth(self.owner["access_token"]),
        )
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["event_id"], self.event_id)
        self.assertTrue(body["meta"]["has_revision_history"])
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["meta"]["latest_status"], "resolved")

        revision = body["revision_history"][0]
        self.assertEqual(revision["report_id"], report_id)
        self.assertEqual(revision["reason_id"], self.reason_id)
        self.assertEqual(revision["confidence_before"], 0.71)
        self.assertEqual(revision["confidence_after"], 0.46)
        self.assertTrue(revision["revised_at_utc"])

        transitions = body["status_transitions"]
        self.assertEqual([item["to_status"] for item in transitions], ["received", "reviewed", "resolved"])
        self.assertEqual([item["from_status"] for item in transitions], [None, "received", "reviewed"])

    def test_no_history_returns_404(self) -> None:
        response = self.client.get(
            f"/v1/events/{self.event_id}/reason-revisions",
            headers=self._auth(self.owner["access_token"]),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "reason_revision_history_not_found")

    def test_partial_failure_returns_retryable_503(self) -> None:
        self._submit_report(self.owner["access_token"])
        reason_report_store.set_failure_mode("transient")

        response = self.client.get(
            f"/v1/events/{self.event_id}/reason-revisions",
            headers=self._auth(self.owner["access_token"]),
        )
        body = response.json()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(body["code"], "temporarily_unavailable")
        self.assertTrue(body["retryable"])

    def test_forbidden_user_cannot_read_revision_history(self) -> None:
        self._persist_event_owner(self.owner["user_id"])
        self._submit_report(self.owner["access_token"])

        response = self.client.get(
            f"/v1/events/{self.event_id}/reason-revisions",
            headers=self._auth(self.viewer["access_token"]),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "forbidden")

    def test_status_transition_must_follow_received_reviewed_resolved(self) -> None:
        report_id = self._submit_report(self.owner["access_token"])

        with self.assertRaises(ValueError):
            reason_report_store.resolve_report(
                report_id=report_id,
                revision_reason="순서 위반",
                confidence_before=0.51,
                confidence_after=0.33,
                note="invalid transition",
            )

    def _submit_report(self, token: str) -> str:
        response = self.client.post(
            f"/v1/events/{self.event_id}/reason-reports",
            json={
                "reason_id": self.reason_id,
                "report_type": "inaccurate_reason",
                "note": "원인 요약과 근거가 불일치합니다.",
            },
            headers=self._auth(token),
        )
        self.assertEqual(response.status_code, 201)
        return str(response.json()["report_id"])

    def _persist_event_owner(self, user_id: str) -> None:
        execute_statement(
            self.runtime.engine,
            """
            INSERT INTO price_events (
                id, user_id, symbol, market, change_pct, window_minutes, detected_at_utc, session_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.event["id"],
                user_id,
                self.event["symbol"],
                self.event["market"],
                self.event["change_pct"],
                self.event["window_minutes"],
                self.event["detected_at_utc"],
                self.event["session_label"],
            ),
        )

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}


if __name__ == "__main__":
    unittest.main()
