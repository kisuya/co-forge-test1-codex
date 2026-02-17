from __future__ import annotations

from datetime import datetime, timezone
from numbers import Real
from typing import Any

from apps.domain.events import parse_utc_datetime, to_utc_iso

_CONFIDENCE_TOLERANCE = 1e-6


def compute_notification_delta(
    *,
    event_id: str,
    previous_snapshot: dict[str, Any] | None,
    latest_reasons: list[dict[str, Any]],
    now_utc: datetime | str | None = None,
) -> dict[str, Any]:
    normalized_event_id = str(event_id).strip()
    if not normalized_event_id:
        raise ValueError("event_id is required")

    _validate_snapshot_event_id(event_id=normalized_event_id, previous_snapshot=previous_snapshot)

    latest_sources = _normalize_latest_sources(latest_reasons)
    previous_sources = _normalize_previous_sources(previous_snapshot)

    added_sources = sorted(latest_sources - previous_sources)
    removed_sources = sorted(previous_sources - latest_sources)

    confidence_after = _extract_latest_confidence(latest_reasons)
    previous_confidence = _extract_previous_confidence(previous_snapshot)

    fallback_reason: str | None = None
    if previous_snapshot is None or previous_confidence is None:
        fallback_reason = "missing_previous_snapshot"
        confidence_before = confidence_after
    else:
        confidence_before = previous_confidence

    confidence_delta = round(confidence_after - confidence_before, 4)
    has_confidence_change = abs(confidence_delta) > _CONFIDENCE_TOLERANCE
    has_source_changes = bool(added_sources or removed_sources)
    has_changes = has_source_changes or has_confidence_change

    if fallback_reason is None and not has_confidence_change:
        fallback_reason = "confidence_unchanged"

    compared_at = parse_utc_datetime(now_utc or datetime.now(timezone.utc))
    previous_snapshot_at = _extract_previous_snapshot_time(previous_snapshot)
    summary_line = _build_summary_line(
        fallback_reason=fallback_reason,
        added_sources=added_sources,
        removed_sources=removed_sources,
        confidence_delta=confidence_delta,
        has_changes=has_changes,
    )

    return {
        "event_id": normalized_event_id,
        "added_sources": added_sources,
        "removed_sources": removed_sources,
        "previous_source_count": len(previous_sources),
        "current_source_count": len(latest_sources),
        "confidence_before": confidence_before,
        "confidence_after": confidence_after,
        "confidence_delta": confidence_delta,
        "has_changes": has_changes,
        "fallback_reason": fallback_reason,
        "summary_line": summary_line,
        "previous_snapshot_at_utc": to_utc_iso(previous_snapshot_at) if previous_snapshot_at else None,
        "compared_at_utc": to_utc_iso(compared_at),
    }


def _validate_snapshot_event_id(*, event_id: str, previous_snapshot: dict[str, Any] | None) -> None:
    if previous_snapshot is None:
        return
    snapshot_event_id = str(previous_snapshot.get("event_id", "")).strip()
    if snapshot_event_id and snapshot_event_id != event_id:
        raise ValueError("previous_snapshot.event_id must match event_id")


def _normalize_latest_sources(latest_reasons: list[dict[str, Any]]) -> set[str]:
    normalized: set[str] = set()
    for reason in latest_reasons:
        source_url = str(reason.get("source_url", "")).strip()
        if source_url:
            normalized.add(source_url)
    return normalized


def _normalize_previous_sources(previous_snapshot: dict[str, Any] | None) -> set[str]:
    if previous_snapshot is None:
        return set()

    normalized: set[str] = set()
    source_urls = previous_snapshot.get("source_urls", [])
    if isinstance(source_urls, list):
        for item in source_urls:
            source_url = str(item).strip()
            if source_url:
                normalized.add(source_url)

    reasons = previous_snapshot.get("reasons", [])
    if isinstance(reasons, list):
        for reason in reasons:
            if not isinstance(reason, dict):
                continue
            source_url = str(reason.get("source_url", "")).strip()
            if source_url:
                normalized.add(source_url)

    return normalized


def _extract_previous_confidence(previous_snapshot: dict[str, Any] | None) -> float | None:
    if previous_snapshot is None:
        return None

    for key in ("confidence_score", "top_confidence_score", "confidence_after"):
        confidence = _normalize_confidence(previous_snapshot.get(key))
        if confidence is not None:
            return confidence
    return None


def _extract_latest_confidence(latest_reasons: list[dict[str, Any]]) -> float:
    highest = 0.0
    for reason in latest_reasons:
        confidence = _normalize_confidence(reason.get("confidence_score"))
        if confidence is None:
            continue
        highest = max(highest, confidence)
    return highest


def _normalize_confidence(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    normalized = float(value)
    if normalized < 0:
        return 0.0
    if normalized > 1:
        return 1.0
    return round(normalized, 4)


def _extract_previous_snapshot_time(previous_snapshot: dict[str, Any] | None) -> datetime | None:
    if previous_snapshot is None:
        return None
    for key in ("snapshot_at_utc", "sent_at_utc"):
        raw_value = previous_snapshot.get(key)
        if raw_value is None:
            continue
        return parse_utc_datetime(raw_value)
    return None


def _build_summary_line(
    *,
    fallback_reason: str | None,
    added_sources: list[str],
    removed_sources: list[str],
    confidence_delta: float,
    has_changes: bool,
) -> str:
    if fallback_reason == "missing_previous_snapshot":
        added_count = len(added_sources)
        if added_count:
            return f"초기 스냅샷이 없어 최신 근거 {added_count}건을 기준선으로 저장했습니다."
        return "초기 스냅샷이 없어 현재 confidence를 기준선으로 저장했습니다."

    if has_changes:
        parts: list[str] = []
        if added_sources:
            parts.append(f"근거 +{len(added_sources)}")
        if removed_sources:
            parts.append(f"근거 -{len(removed_sources)}")
        if abs(confidence_delta) > _CONFIDENCE_TOLERANCE:
            parts.append(f"confidence {confidence_delta:+.2f}")
        return ", ".join(parts)

    return "근거/신뢰도 변화가 없어 이벤트 이력만 갱신합니다."
