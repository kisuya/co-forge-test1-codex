from __future__ import annotations

from dataclasses import dataclass

from apps.infra.models import create_core_schema, execute_statement, fetch_all
from apps.infra.postgres import get_database_runtime


@dataclass(frozen=True)
class NotificationRecord:
    id: str
    user_id: str
    event_id: str
    channel: str
    status: str
    message: str
    sent_at_utc: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "event_id": self.event_id,
            "channel": self.channel,
            "status": self.status,
            "message": self.message,
            "sent_at_utc": self.sent_at_utc,
        }


class NotificationDbService:
    def list_in_app_notifications(self, *, user_id: str) -> list[NotificationRecord]:
        normalized_user_id = _normalize_user_id(user_id)
        runtime = get_database_runtime()
        create_core_schema(runtime.engine)
        rows = fetch_all(
            runtime.engine,
            """
            SELECT id, user_id, event_id, channel, status, message, sent_at_utc
            FROM notifications
            WHERE user_id = ? AND channel = 'in_app'
            ORDER BY sent_at_utc DESC, id DESC
            """,
            (normalized_user_id,),
        )
        return [_row_to_notification(row) for row in rows]

    def count_unread_in_app_notifications(self, *, user_id: str) -> int:
        normalized_user_id = _normalize_user_id(user_id)
        runtime = get_database_runtime()
        create_core_schema(runtime.engine)
        rows = fetch_all(
            runtime.engine,
            """
            SELECT COUNT(*)
            FROM notifications
            WHERE user_id = ? AND channel = 'in_app' AND status != 'read'
            """,
            (normalized_user_id,),
        )
        return int(rows[0][0]) if rows else 0

    def mark_in_app_notification_read(self, *, notification_id: str, user_id: str) -> NotificationRecord | None:
        normalized_notification_id = (notification_id or "").strip()
        if not normalized_notification_id:
            return None
        normalized_user_id = _normalize_user_id(user_id)
        runtime = get_database_runtime()
        create_core_schema(runtime.engine)

        row = self._fetch_notification(
            notification_id=normalized_notification_id,
            user_id=normalized_user_id,
        )
        if row is None:
            return None
        if row.status != "read":
            execute_statement(
                runtime.engine,
                """
                UPDATE notifications
                SET status = 'read'
                WHERE id = ? AND user_id = ? AND channel = 'in_app'
                """,
                (normalized_notification_id, normalized_user_id),
            )
        return self._fetch_notification(
            notification_id=normalized_notification_id,
            user_id=normalized_user_id,
        )

    def _fetch_notification(self, *, notification_id: str, user_id: str) -> NotificationRecord | None:
        runtime = get_database_runtime()
        rows = fetch_all(
            runtime.engine,
            """
            SELECT id, user_id, event_id, channel, status, message, sent_at_utc
            FROM notifications
            WHERE id = ? AND user_id = ? AND channel = 'in_app'
            LIMIT 1
            """,
            (notification_id, user_id),
        )
        if not rows:
            return None
        return _row_to_notification(rows[0])


def _normalize_user_id(user_id: str) -> str:
    normalized = (user_id or "").strip()
    if not normalized:
        raise ValueError("user_id must not be empty")
    return normalized


def _row_to_notification(row: tuple[object, ...]) -> NotificationRecord:
    return NotificationRecord(
        id=str(row[0]),
        user_id=str(row[1]),
        event_id=str(row[2]),
        channel=str(row[3]),
        status=str(row[4]),
        message=str(row[5]),
        sent_at_utc=str(row[6]),
    )


notification_db_service = NotificationDbService()
