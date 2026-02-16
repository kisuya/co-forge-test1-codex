from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from apps.domain.events import parse_utc_datetime, to_utc_iso
from apps.domain.reasons import event_reason_store
from apps.infra.observability import log_error

_FALLBACK_SUMMARY = "근거 수집 중"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _recency_score(detected_at: datetime, published_at: datetime) -> float:
    delta_minutes = abs((detected_at - published_at).total_seconds()) / 60
    return _clamp(1 - (delta_minutes / 1440), 0.0, 1.0)


def _build_explanation(*, source_reliability: float, topic_match: float, time_proximity: float) -> dict[str, object]:
    weights = {"source_reliability": 0.45, "topic_match": 0.35, "time_proximity": 0.20}
    signals = {
        "source_reliability": round(source_reliability, 4),
        "topic_match": round(topic_match, 4),
        "time_proximity": round(time_proximity, 4),
    }
    score_breakdown = {
        "source_reliability": round(weights["source_reliability"] * source_reliability, 4),
        "topic_match": round(weights["topic_match"] * topic_match, 4),
        "time_proximity": round(weights["time_proximity"] * time_proximity, 4),
    }
    score_breakdown["total"] = round(
        score_breakdown["source_reliability"]
        + score_breakdown["topic_match"]
        + score_breakdown["time_proximity"],
        4,
    )
    return {
        "weights": weights,
        "signals": signals,
        "score_breakdown": score_breakdown,
    }


def rank_event_reasons(
    *,
    event_id: str,
    detected_at_utc: datetime | str,
    candidates: list[dict[str, Any]],
    request_id: str | None = None,
) -> list[dict[str, object]]:
    detected_at = parse_utc_datetime(detected_at_utc)
    scored: list[tuple[float, dict[str, Any]]] = []

    for candidate in candidates:
        source_url = str(candidate.get("source_url", "")).strip()
        if not source_url:
            continue
        is_valid_url, invalid_reason = _validate_source_url(source_url)
        if not is_valid_url:
            log_error(
                feature="reason-004",
                event="invalid_source_url_candidate",
                request_id=request_id,
                logger_name="oh_my_stock.worker",
                event_id=event_id,
                source_url=source_url,
                reason=invalid_reason,
            )
            continue

        published_at_value = candidate.get("published_at", detected_at)
        published_at = parse_utc_datetime(published_at_value)

        source_reliability = float(candidate.get("source_reliability", 0.5))
        topic_match = float(candidate.get("topic_match_score", 0.5))
        time_proximity = _recency_score(detected_at, published_at)
        confidence = (
            0.45 * _clamp(source_reliability, 0.0, 1.0)
            + 0.35 * _clamp(topic_match, 0.0, 1.0)
            + 0.20 * time_proximity
        )
        explanation = _build_explanation(
            source_reliability=_clamp(source_reliability, 0.0, 1.0),
            topic_match=_clamp(topic_match, 0.0, 1.0),
            time_proximity=_clamp(time_proximity, 0.0, 1.0),
        )
        scored.append(
            (
                round(confidence, 4),
                {
                    "reason_type": str(candidate.get("reason_type", "unknown")),
                    "summary": str(candidate.get("summary", "")),
                    "source_url": source_url,
                    "published_at": to_utc_iso(published_at),
                    "explanation": explanation,
                },
            )
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    top_scored = scored[:3]
    if not top_scored:
        event_reason_store.replace_event_reasons(event_id, [])
        return [
            {
                "reason_type": "fallback",
                "confidence_score": 0.0,
                "summary": _FALLBACK_SUMMARY,
                "source_url": None,
                "published_at": to_utc_iso(detected_at),
                "rank": 1,
                "explanation": {
                    "weights": {},
                    "signals": {},
                    "score_breakdown": {"total": 0.0},
                },
            }
        ]

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
            explanation=payload["explanation"],
        )
        built_reasons.append(reason)

    event_reason_store.replace_event_reasons(event_id, built_reasons)
    return [reason.to_dict() for reason in built_reasons]


def _validate_source_url(source_url: str) -> tuple[bool, str]:
    parsed = urlsplit(source_url)
    if parsed.scheme.lower() not in {"http", "https"}:
        return False, "invalid_scheme"
    if not parsed.netloc:
        return False, "missing_host"
    return True, ""
