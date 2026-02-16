from __future__ import annotations

from dataclasses import asdict, dataclass
from uuid import uuid4


@dataclass(frozen=True)
class EventReason:
    id: str
    event_id: str
    rank: int
    reason_type: str
    confidence_score: float
    summary: str
    source_url: str
    published_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class EventReasonStore:
    def __init__(self) -> None:
        self._reasons_by_event: dict[str, list[EventReason]] = {}

    def clear(self) -> None:
        self._reasons_by_event.clear()

    def replace_event_reasons(self, event_id: str, reasons: list[EventReason]) -> None:
        self._reasons_by_event[event_id] = reasons

    def list_by_event(self, event_id: str) -> list[EventReason]:
        return list(self._reasons_by_event.get(event_id, []))

    def build_reason(
        self,
        *,
        event_id: str,
        rank: int,
        reason_type: str,
        confidence_score: float,
        summary: str,
        source_url: str,
        published_at: str,
    ) -> EventReason:
        return EventReason(
            id=str(uuid4()),
            event_id=event_id,
            rank=rank,
            reason_type=reason_type,
            confidence_score=confidence_score,
            summary=summary,
            source_url=source_url,
            published_at=published_at,
        )


event_reason_store = EventReasonStore()
