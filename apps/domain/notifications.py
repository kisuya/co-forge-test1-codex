from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from apps.domain.events import parse_utc_datetime, to_utc_iso

VALID_CHANNELS = {"in_app", "email", "push"}


@dataclass(frozen=True)
class Notification:
    id: str
    user_id: str
    event_id: str
    channel: str
    sent_at_utc: str
    status: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class NotificationStore:
    def __init__(self) -> None:
        self._notifications: list[Notification] = []
        self._last_sent_at: dict[tuple[str, str, str], datetime] = {}

    def clear(self) -> None:
        self._notifications.clear()
        self._last_sent_at.clear()

    def in_cooldown(
        self,
        *,
        user_id: str,
        event_id: str,
        channel: str,
        sent_at: datetime,
        cooldown_minutes: int = 30,
    ) -> bool:
        key = (user_id, event_id, channel)
        previous = self._last_sent_at.get(key)
        if previous is None:
            return False
        return sent_at - previous < timedelta(minutes=cooldown_minutes)

    def create_notification(
        self,
        *,
        user_id: str,
        event_id: str,
        channel: str,
        sent_at: datetime | str,
        message: str,
        status: str = "sent",
    ) -> Notification:
        if channel not in VALID_CHANNELS:
            raise ValueError("channel must be one of in_app, email, or push")

        sent_at_dt = parse_utc_datetime(sent_at)
        return Notification(
            id=str(uuid4()),
            user_id=user_id,
            event_id=event_id,
            channel=channel,
            sent_at_utc=to_utc_iso(sent_at_dt),
            status=status,
            message=message,
        )

    def save(self, notification: Notification) -> Notification:
        self._notifications.append(notification)
        self._last_sent_at[(notification.user_id, notification.event_id, notification.channel)] = (
            parse_utc_datetime(notification.sent_at_utc)
        )
        return notification

    def list_notifications(self) -> list[Notification]:
        return list(self._notifications)

    def list_by_event(self, event_id: str) -> list[Notification]:
        return [item for item in self._notifications if item.event_id == event_id]


notification_store = NotificationStore()
