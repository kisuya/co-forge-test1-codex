from __future__ import annotations

from datetime import datetime
from typing import Any

from apps.domain.events import parse_utc_datetime, to_utc_iso
from apps.domain.reasons import event_reason_store


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _recency_score(detected_at: datetime, published_at: datetime) -> float:
    delta_minutes = abs((detected_at - published_at).total_seconds()) / 60
    return _clamp(1 - (delta_minutes / 1440), 0.0, 1.0)


def rank_event_reasons(
    *,
    event_id: str,
    detected_at_utc: datetime | str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, object]]:
    detected_at = parse_utc_datetime(detected_at_utc)
    scored: list[tuple[float, dict[str, Any]]] = []

    for candidate in candidates:
        source_url = str(candidate.get("source_url", "")).strip()
        if not source_url:
            continue

        published_at_value = candidate.get("published_at", detected_at)
        published_at = parse_utc_datetime(published_at_value)

        source_reliability = float(candidate.get("source_reliability", 0.5))
        topic_match = float(candidate.get("topic_match_score", 0.5))
        confidence = (
            0.45 * _clamp(source_reliability, 0.0, 1.0)
            + 0.35 * _clamp(topic_match, 0.0, 1.0)
            + 0.20 * _recency_score(detected_at, published_at)
        )
        scored.append(
            (
                round(confidence, 4),
                {
                    "reason_type": str(candidate.get("reason_type", "unknown")),
                    "summary": str(candidate.get("summary", "")),
                    "source_url": source_url,
                    "published_at": to_utc_iso(published_at),
                },
            )
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    top_scored = scored[:3]

    built_reasons = []
    for index, (confidence, payload) in enumerate(top_scored, start=1):
        reason = event_reason_store.build_reason(
            event_id=event_id,
            rank=index,
            reason_type=payload["reason_type"],
            confidence_score=confidence,
            summary=payload["summary"],
            source_url=payload["source_url"],
            published_at=payload["published_at"],
        )
        built_reasons.append(reason)

    event_reason_store.replace_event_reasons(event_id, built_reasons)
    return [reason.to_dict() for reason in built_reasons]
