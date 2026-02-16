from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from apps.domain.events import parse_utc_datetime, price_event_store
from apps.domain.reasons import event_reason_store

_VALID_FEEDBACK = {"helpful", "not_helpful"}


@dataclass(frozen=True)
class ReasonFeedback:
    user_id: str
    event_id: str
    reason_id: str
    feedback: str
    updated_at_utc: str

    def to_dict(self) -> dict[str, str]:
        return {
            "user_id": self.user_id,
            "event_id": self.event_id,
            "reason_id": self.reason_id,
            "feedback": self.feedback,
            "updated_at_utc": self.updated_at_utc,
        }


class ReasonFeedbackStore:
    def __init__(self) -> None:
        self._feedback_by_key: dict[tuple[str, str, str], ReasonFeedback] = {}

    def clear(self) -> None:
        self._feedback_by_key.clear()

    def submit(
        self,
        *,
        user_id: str,
        event_id: str,
        reason_id: str,
        feedback: str,
    ) -> tuple[ReasonFeedback, bool]:
        normalized_user_id = _normalize_non_empty(user_id, field_name="user_id")
        normalized_event_id = _normalize_non_empty(event_id, field_name="event_id")
        normalized_reason_id = _normalize_non_empty(reason_id, field_name="reason_id")
        normalized_feedback = _normalize_feedback(feedback)
        _validate_reason_belongs_to_event(event_id=normalized_event_id, reason_id=normalized_reason_id)

        key = (normalized_user_id, normalized_event_id, normalized_reason_id)
        overwritten = key in self._feedback_by_key
        item = ReasonFeedback(
            user_id=normalized_user_id,
            event_id=normalized_event_id,
            reason_id=normalized_reason_id,
            feedback=normalized_feedback,
            updated_at_utc=_utc_now_iso(),
        )
        self._feedback_by_key[key] = item
        return item, overwritten

    def list_by_event(self, event_id: str) -> list[ReasonFeedback]:
        normalized_event_id = _normalize_non_empty(event_id, field_name="event_id")
        items = [item for item in self._feedback_by_key.values() if item.event_id == normalized_event_id]
        return sorted(items, key=lambda item: item.updated_at_utc, reverse=True)

    def aggregate(
        self,
        *,
        from_utc: datetime | None = None,
        to_utc: datetime | None = None,
        symbol: str | None = None,
        market: str | None = None,
        min_samples: int = 3,
    ) -> list[dict[str, object]]:
        if min_samples < 1:
            raise ValueError("min_samples must be >= 1")
        normalized_symbol = (symbol or "").strip().upper() or None
        normalized_market = (market or "").strip().upper() or None

        buckets: dict[tuple[str, str], dict[str, int]] = {}
        for feedback in self._feedback_by_key.values():
            feedback_time = parse_utc_datetime(feedback.updated_at_utc)
            if from_utc and feedback_time < from_utc:
                continue
            if to_utc and feedback_time > to_utc:
                continue

            event = price_event_store.get_event(feedback.event_id)
            if event is None:
                continue
            if normalized_symbol and event.symbol != normalized_symbol:
                continue
            if normalized_market and event.market != normalized_market:
                continue

            key = (event.market, event.symbol)
            bucket = buckets.setdefault(key, {"helpful": 0, "total": 0})
            bucket["total"] += 1
            if feedback.feedback == "helpful":
                bucket["helpful"] += 1

        items: list[dict[str, object]] = []
        for (item_market, item_symbol), counts in buckets.items():
            total = counts["total"]
            helpful = counts["helpful"]
            items.append(
                {
                    "market": item_market,
                    "symbol": item_symbol,
                    "helpful_ratio": round(helpful / total, 4) if total else 0.0,
                    "sample_count": total,
                    "low_confidence": total < min_samples,
                }
            )
        return sorted(items, key=lambda item: (str(item["market"]), str(item["symbol"])))


def _normalize_non_empty(value: str, *, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _normalize_feedback(feedback: str) -> str:
    normalized = (feedback or "").strip().lower()
    if normalized not in _VALID_FEEDBACK:
        raise ValueError("feedback must be helpful or not_helpful")
    return normalized


def _validate_reason_belongs_to_event(*, event_id: str, reason_id: str) -> None:
    reasons = event_reason_store.list_by_event(event_id)
    valid_reason_ids = {reason.id for reason in reasons}
    if reason_id not in valid_reason_ids:
        raise ValueError("invalid reason_id for event")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


reason_feedback_store = ReasonFeedbackStore()
