from __future__ import annotations

import os
import tempfile
import unittest

from apps.api.main import app
from apps.infra.models import create_core_schema, drop_core_schema, execute_statement
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from fastapi.testclient import TestClient


class InAppNotificationsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="in-app-notifications-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/notifications.sqlite"
        os.environ["JWT_SECRET"] = "notifications-secret"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-notify-setup")
        create_core_schema(self.runtime.engine)
        self.client = TestClient(app)

        self.user_a = self.client.post(
            "/v1/auth/signup",
            json={"email": "notify-a@example.com", "password": "notify-password-a"},
        ).json()
        self.user_b = self.client.post(
            "/v1/auth/signup",
            json={"email": "notify-b@example.com", "password": "notify-password-b"},
        ).json()

        self.a_event_1 = "evt-a-1"
        self.a_event_2 = "evt-a-2"
        self.b_event_1 = "evt-b-1"
        self.a_notification_1 = "ntf-a-1"
        self.a_notification_2 = "ntf-a-2"
        self.b_notification_1 = "ntf-b-1"

        self._insert_event(self.user_a["user_id"], self.a_event_1, symbol="AAPL")
        self._insert_event(self.user_a["user_id"], self.a_event_2, symbol="MSFT")
        self._insert_event(self.user_b["user_id"], self.b_event_1, symbol="TSLA")
        self._insert_notification(
            self.a_notification_1,
            self.user_a["user_id"],
            self.a_event_1,
            status="sent",
            sent_at="2026-02-16T12:00:00Z",
        )
        self._insert_notification(
            self.a_notification_2,
            self.user_a["user_id"],
            self.a_event_2,
            status="sent",
            sent_at="2026-02-16T12:05:00Z",
        )
        self._insert_notification(
            self.b_notification_1,
            self.user_b["user_id"],
            self.b_event_1,
            status="sent",
            sent_at="2026-02-16T12:10:00Z",
        )

    def tearDown(self) -> None:
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_list_notifications_returns_user_scoped_items_and_unread_count(self) -> None:
        response = self.client.get(
            "/v1/notifications",
            headers=self._auth(self.user_a["access_token"]),
        )
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(body["items"]), 2)
        self.assertEqual(body["unread_count"], 2)
        self.assertTrue(all(item["user_id"] == self.user_a["user_id"] for item in body["items"]))

    def test_patch_read_marks_notification_and_updates_unread_count(self) -> None:
        response = self.client.patch(
            f"/v1/notifications/{self.a_notification_1}/read",
            headers=self._auth(self.user_a["access_token"]),
        )
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["notification"]["id"], self.a_notification_1)
        self.assertEqual(body["notification"]["status"], "read")
        self.assertEqual(body["unread_count"], 1)

    def test_cross_user_notification_access_returns_404(self) -> None:
        response = self.client.patch(
            f"/v1/notifications/{self.a_notification_1}/read",
            headers=self._auth(self.user_b["access_token"]),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "notification_not_found")

    def _insert_event(self, user_id: str, event_id: str, *, symbol: str) -> None:
        execute_statement(
            self.runtime.engine,
            """
            INSERT INTO price_events (id, user_id, symbol, market, change_pct, window_minutes, detected_at_utc, session_label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, user_id, symbol, "US", 3.5, 5, "2026-02-16T12:00:00Z", "regular"),
        )

    def _insert_notification(
        self,
        notification_id: str,
        user_id: str,
        event_id: str,
        *,
        status: str,
        sent_at: str,
    ) -> None:
        execute_statement(
            self.runtime.engine,
            """
            INSERT INTO notifications (id, user_id, event_id, channel, status, message, sent_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (notification_id, user_id, event_id, "in_app", status, "Event update", sent_at),
        )

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}


if __name__ == "__main__":
    unittest.main()
