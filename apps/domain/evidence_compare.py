from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from numbers import Real
from typing import Any

from apps.domain.events import parse_utc_datetime, to_utc_iso

_AXIS_POSITIVE = "positive"
_AXIS_NEGATIVE = "negative"
_AXIS_UNCERTAIN = "uncertain"
_AXES = (_AXIS_POSITIVE, _AXIS_NEGATIVE, _AXIS_UNCERTAIN)

_EXPLICIT_AXIS_MAP = {
    "positive": _AXIS_POSITIVE,
    "pos": _AXIS_POSITIVE,
    "bullish": _AXIS_POSITIVE,
    "negative": _AXIS_NEGATIVE,
    "neg": _AXIS_NEGATIVE,
    "bearish": _AXIS_NEGATIVE,
    "uncertain": _AXIS_UNCERTAIN,
    "neutral": _AXIS_UNCERTAIN,
    "mixed": _AXIS_UNCERTAIN,
}

_POSITIVE_TERMS = (
    "beat",
    "upgrade",
    "guidance raised",
    "record",
    "surge",
    "strong demand",
    "호재",
    "실적 개선",
    "상향",
    "수주",
    "증가",
    "강세",
)
_NEGATIVE_TERMS = (
    "miss",
    "downgrade",
    "guidance cut",
    "investigation",
    "lawsuit",
    "recall",
    "plunge",
    "악재",
    "실적 부진",
    "하향",
    "감소",
    "약세",
    "리스크",
)
_IMBALANCE_RATIO = 4.0
_EMPTY_SUMMARY = "요약 정보 없음"


def build_evidence_compare_payload(
    *,
    event_id: str,
    evidences: list[dict[str, Any]],
    generated_at_utc: datetime | str | None = None,
) -> dict[str, Any]:
    normalized_event_id = str(event_id).strip()
    if not normalized_event_id:
        raise ValueError("event_id is required")

    grouped: dict[str, list[dict[str, Any]]] = {axis: [] for axis in _AXES}
    dropped_missing_metadata_count = 0

    for evidence in evidences:
        normalized = _normalize_evidence(evidence)
        if normalized is None:
            dropped_missing_metadata_count += 1
            continue

        axis, reason, matched_terms = _classify_axis(evidence=evidence, normalized=normalized)
        normalized["axis"] = axis
        normalized["classification_reason"] = reason
        if matched_terms:
            normalized["matched_terms"] = matched_terms
        grouped[axis].append(normalized)

    for axis in _AXES:
        grouped[axis] = _sort_by_published_at(grouped[axis])

    fallback_reason = _resolve_fallback_reason(grouped)
    if fallback_reason is not None:
        grouped = _fallback_to_uncertain(grouped)

    axis_counts = {axis: len(grouped[axis]) for axis in _AXES}
    compare_ready = fallback_reason is None
    generated_at = parse_utc_datetime(generated_at_utc or datetime.now(timezone.utc))

    return {
        "event_id": normalized_event_id,
        "status": "ready" if compare_ready else "compare_unavailable",
        "compare_ready": compare_ready,
        "fallback_reason": fallback_reason,
        "bias_warning": _build_bias_warning(compare_ready=compare_ready),
        "axes": grouped,
        "axis_counts": axis_counts,
        "comparable_axis_count": sum(1 for axis in _AXES if axis_counts[axis] > 0),
        "evidence_count": sum(axis_counts.values()),
        "dropped_missing_metadata_count": dropped_missing_metadata_count,
        "generated_at_utc": to_utc_iso(generated_at),
    }


def _normalize_evidence(evidence: Mapping[str, Any]) -> dict[str, Any] | None:
    source_url = str(evidence.get("source_url", "")).strip()
    published_at_raw = evidence.get("published_at")
    if not source_url or published_at_raw is None:
        return None

    try:
        published_at = parse_utc_datetime(published_at_raw)
    except Exception:  # noqa: BLE001 - malformed time should be dropped as unusable evidence.
        return None

    summary = str(evidence.get("summary") or evidence.get("title") or "").strip()
    normalized: dict[str, Any] = {
        "id": str(evidence.get("id", "")).strip() or None,
        "reason_type": str(evidence.get("reason_type", "unknown")).strip() or "unknown",
        "summary": summary or _EMPTY_SUMMARY,
        "source_url": source_url,
        "published_at": to_utc_iso(published_at),
    }

    confidence_score = _normalize_confidence(evidence.get("confidence_score"))
    if confidence_score is not None:
        normalized["confidence_score"] = confidence_score
    return normalized


def _normalize_confidence(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    score = float(value)
    if score < 0:
        return 0.0
    if score > 1:
        return 1.0
    return round(score, 4)


def _classify_axis(*, evidence: Mapping[str, Any], normalized: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    explicit_axis = _resolve_explicit_axis(evidence)
    if explicit_axis is not None:
        return explicit_axis, "explicit_axis", []

    text = " ".join(
        [
            str(evidence.get("title", "")),
            str(normalized.get("summary", "")),
            str(evidence.get("reason_type", "")),
        ]
    ).casefold()
    positive_terms = [term for term in _POSITIVE_TERMS if term in text]
    negative_terms = [term for term in _NEGATIVE_TERMS if term in text]

    if positive_terms and not negative_terms:
        return _AXIS_POSITIVE, "keyword_positive", positive_terms[:3]
    if negative_terms and not positive_terms:
        return _AXIS_NEGATIVE, "keyword_negative", negative_terms[:3]
    if positive_terms and negative_terms:
        return _AXIS_UNCERTAIN, "ambiguous_keywords", sorted(set(positive_terms + negative_terms))[:3]
    return _AXIS_UNCERTAIN, "no_polarity_signal", []


def _resolve_explicit_axis(evidence: Mapping[str, Any]) -> str | None:
    for key in ("axis", "sentiment", "stance", "polarity"):
        raw_value = str(evidence.get(key, "")).strip().casefold()
        axis = _EXPLICIT_AXIS_MAP.get(raw_value)
        if axis is not None:
            return axis
    return None


def _resolve_fallback_reason(grouped: Mapping[str, list[dict[str, Any]]]) -> str | None:
    positive_count = len(grouped[_AXIS_POSITIVE])
    negative_count = len(grouped[_AXIS_NEGATIVE])
    total_count = positive_count + negative_count + len(grouped[_AXIS_UNCERTAIN])

    if total_count < 2:
        return "insufficient_evidence"
    if positive_count == 0 and negative_count == 0:
        return "ambiguous_classification"
    if positive_count == 0 or negative_count == 0:
        return "axis_imbalance"

    larger = max(positive_count, negative_count)
    smaller = min(positive_count, negative_count)
    if total_count >= 4 and smaller > 0 and (larger / smaller) >= _IMBALANCE_RATIO:
        return "axis_imbalance"
    return None


def _fallback_to_uncertain(grouped: Mapping[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    merged = _sort_by_published_at(
        [
            *grouped[_AXIS_POSITIVE],
            *grouped[_AXIS_NEGATIVE],
            *grouped[_AXIS_UNCERTAIN],
        ]
    )
    return {
        _AXIS_POSITIVE: [],
        _AXIS_NEGATIVE: [],
        _AXIS_UNCERTAIN: merged,
    }


def _sort_by_published_at(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: (str(item["published_at"]), str(item["source_url"])), reverse=True)


def _build_bias_warning(*, compare_ready: bool) -> str:
    if compare_ready:
        return "긍정/부정 근거가 함께 존재합니다. 단일 결론보다 출처와 발행 시각을 함께 비교하세요."
    return "상충 근거가 충분하지 않아 불확실 축으로 표시합니다. 단정형 결론은 제공하지 않습니다."
