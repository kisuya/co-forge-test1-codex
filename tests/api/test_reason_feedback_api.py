from __future__ import annotations

import os
import tempfile
import unittest

from apps.api.main import app
from apps.domain.events import price_event_store
from apps.domain.feedback import reason_feedback_store
from apps.domain.reasons import event_reason_store
from apps.infra.models import create_core_schema, drop_core_schema
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from apps.worker.detection import detect_price_event
from apps.worker.reasons import rank_event_reasons
from fastapi.testclient import TestClient


class ReasonFeedbackApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="reason-feedback-api-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/feedback.sqlite"
        os.environ["JWT_SECRET"] = "feedback-secret"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-feedback-setup")
        create_core_schema(self.runtime.engine)

        price_event_store.clear()
        event_reason_store.clear()
        reason_feedback_store.clear()
        self.client = TestClient(app)
        self.user = self.client.post(
            "/v1/auth/signup",
            json={"email": "feedback@example.com", "password": "feedback-password"},
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
        reason_feedback_store.clear()
        event_reason_store.clear()
        price_event_store.clear()
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_duplicate_submission_overwrites_previous_feedback(self) -> None:
        first = self.client.post(
            f"/v1/events/{self.event_id}/feedback",
            json={"reason_id": self.reason_id, "feedback": "helpful"},
            headers=self._auth(self.user["access_token"]),
        )
        second = self.client.post(
            f"/v1/events/{self.event_id}/feedback",
            json={"reason_id": self.reason_id, "feedback": "not_helpful"},
            headers=self._auth(self.user["access_token"]),
        )

        self.assertEqual(first.status_code, 201)
        self.assertFalse(first.json()["overwritten"])
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["overwritten"])
        self.assertEqual(second.json()["feedback"]["feedback"], "not_helpful")
        self.assertEqual(len(reason_feedback_store.list_by_event(self.event_id)), 1)

    def test_invalid_reason_id_returns_400(self) -> None:
        response = self.client.post(
            f"/v1/events/{self.event_id}/feedback",
            json={"reason_id": "invalid-reason-id", "feedback": "helpful"},
            headers=self._auth(self.user["access_token"]),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_input")

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}


if __name__ == "__main__":
    unittest.main()
