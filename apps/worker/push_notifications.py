from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class PushQueueMessage:
    user_id: str
    event_id: str
    token: str
    platform: str
    message: str
    queued_at_utc: str

    def to_dict(self) -> dict[str, str]:
        payload = asdict(self)
        return {key: str(value) for key, value in payload.items()}


class PushQueueAdapter:
    def enqueue(self, message: PushQueueMessage) -> PushQueueMessage:
        raise NotImplementedError


class InMemoryPushQueue(PushQueueAdapter):
    def __init__(self) -> None:
        self._messages: list[PushQueueMessage] = []
        self._failure: Exception | None = None

    def enqueue(self, message: PushQueueMessage) -> PushQueueMessage:
        if self._failure is not None:
            error = self._failure
            self._failure = None
            raise error
        self._messages.append(message)
        return message

    def list_messages(self) -> list[PushQueueMessage]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()
        self._failure = None

    def fail_next_enqueue(self, exc: Exception) -> None:
        self._failure = exc


push_notification_queue = InMemoryPushQueue()


def build_push_queue_message(
    *,
    user_id: str,
    event_id: str,
    token: str,
    platform: str,
    message: str,
    now_utc: datetime,
) -> PushQueueMessage:
    return PushQueueMessage(
        user_id=user_id,
        event_id=event_id,
        token=token,
        platform=platform,
        message=message,
        queued_at_utc=_to_utc_iso(now_utc),
    )


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
