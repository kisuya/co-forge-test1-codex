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


class ReasonReportSubmissionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="reason-report-submission-api-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/reason_report_submission.sqlite"
        os.environ["JWT_SECRET"] = "reason-report-submission-secret"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-reason-report-submission-setup")
        create_core_schema(self.runtime.engine)

        price_event_store.clear()
        event_reason_store.clear()
        reason_report_store.clear()
        reason_reevaluation_queue.clear()

        self.client = TestClient(app)
        self.owner = self.client.post(
            "/v1/auth/signup",
            json={"email": "report-owner@example.com", "password": "report-owner-password"},
        ).json()
        self.viewer = self.client.post(
            "/v1/auth/signup",
            json={"email": "report-viewer@example.com", "password": "report-viewer-password"},
        ).json()

        event = detect_price_event(
            symbol="AAPL",
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc="2026-02-16T12:00:00Z",
        )
        assert event is not None
        self.event = event
        self.event_id = event["id"]

        rank_event_reasons(
            event_id=self.event_id,
            detected_at_utc=event["detected_at_utc"],
            candidates=[
                {
                    "reason_type": "filing",
                    "summary": "8-K filed",
                    "source_url": "https://sec.example/8k",
                    "published_at": event["detected_at_utc"],
                }
            ],
        )
        self.reason_id = event_reason_store.list_by_event(self.event_id)[0].id

    def tearDown(self) -> None:
        reason_reevaluation_queue.clear()
        reason_report_store.clear()
        event_reason_store.clear()
        price_event_store.clear()
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_submit_reason_report_returns_received_and_enqueues_task(self) -> None:
        response = self.client.post(
            f"/v1/events/{self.event_id}/reason-reports",
            json={
                "reason_id": self.reason_id,
                "report_type": "inaccurate_reason",
                "note": "근거 링크의 맥락이 이벤트와 맞지 않습니다.",
            },
            headers=self._auth(self.owner["access_token"]),
        )
        body = response.json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(body["status"], "received")
        self.assertTrue(body["report_id"])
        self.assertTrue(body["queued"])

        saved_report = reason_report_store.get_report(body["report_id"])
        assert saved_report is not None
        self.assertEqual(saved_report.status, "received")
        self.assertEqual(saved_report.reason_id, self.reason_id)

        queued = reason_reevaluation_queue.list_tasks()
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0].report_id, body["report_id"])
        self.assertEqual(queued[0].event_id, self.event_id)
        self.assertEqual(queued[0].reason_id, self.reason_id)
        self.assertEqual(queued[0].user_id, self.owner["user_id"])

    def test_duplicate_open_report_returns_400(self) -> None:
        first = self.client.post(
            f"/v1/events/{self.event_id}/reason-reports",
            json={
                "reason_id": self.reason_id,
                "report_type": "wrong_source",
                "note": "중복 제출 1회차",
            },
            headers=self._auth(self.owner["access_token"]),
        )
        second = self.client.post(
            f"/v1/events/{self.event_id}/reason-reports",
            json={
                "reason_id": self.reason_id,
                "report_type": "wrong_source",
                "note": "중복 제출 2회차",
            },
            headers=self._auth(self.owner["access_token"]),
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.json()["code"], "duplicate_reason_report")
        self.assertEqual(len(reason_reevaluation_queue.list_tasks()), 1)

    def test_missing_reason_id_returns_404(self) -> None:
        response = self.client.post(
            f"/v1/events/{self.event_id}/reason-reports",
            json={
                "reason_id": "missing-reason-id",
                "report_type": "inaccurate_reason",
                "note": "존재하지 않는 reason",
            },
            headers=self._auth(self.owner["access_token"]),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "reason_not_found")

    def test_forbidden_when_event_is_owned_by_another_user(self) -> None:
        self._persist_event_owner(self.owner["user_id"])

        response = self.client.post(
            f"/v1/events/{self.event_id}/reason-reports",
            json={
                "reason_id": self.reason_id,
                "report_type": "other",
                "note": "권한 없는 사용자가 제출",
            },
            headers=self._auth(self.viewer["access_token"]),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "forbidden")

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
