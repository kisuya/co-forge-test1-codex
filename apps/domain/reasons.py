from __future__ import annotations

from dataclasses import asdict, dataclass
from numbers import Real
from uuid import uuid4

_REQUIRED_BREAKDOWN_KEYS = ("source_reliability", "event_match", "time_proximity")
_CONFIDENCE_TOLERANCE = 1e-3
_FORBIDDEN_EXPLANATION_TERMS = ("매수", "매도", "추천", "buy", "sell", "financial advice")


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
    explanation: dict[str, object]

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
        explanation: dict[str, object],
    ) -> EventReason:
        validated_explanation = _validate_explanation(explanation=explanation, confidence_score=confidence_score)
        return EventReason(
            id=str(uuid4()),
            event_id=event_id,
            rank=rank,
            reason_type=reason_type,
            confidence_score=confidence_score,
            summary=summary,
            source_url=source_url,
            published_at=published_at,
            explanation=validated_explanation,
        )


def _validate_explanation(*, explanation: dict[str, object], confidence_score: float) -> dict[str, object]:
    if not isinstance(explanation, dict):
        raise ValueError("explanation must be an object")

    weights = _require_mapping_section(explanation=explanation, section_name="weights")
    signals = _require_mapping_section(explanation=explanation, section_name="signals")
    score_breakdown = _require_mapping_section(explanation=explanation, section_name="score_breakdown")
    explanation_text = explanation.get("explanation_text")
    if not isinstance(explanation_text, str) or not explanation_text.strip():
        raise ValueError("explanation.explanation_text must be a non-empty string")

    lowered_text = explanation_text.casefold()
    if any(term in lowered_text for term in _FORBIDDEN_EXPLANATION_TERMS):
        raise ValueError("explanation.explanation_text must not include investment recommendation terms")

    normalized_weights = _validate_breakdown_components(section=weights, field_name="weights")
    normalized_signals = _validate_breakdown_components(section=signals, field_name="signals")
    normalized_score_breakdown = _validate_breakdown_components(
        section=score_breakdown,
        field_name="score_breakdown",
    )
    total = _validate_non_negative_number(
        score_breakdown.get("total"),
        field_name="score_breakdown.total",
    )
    normalized_confidence_score = _validate_non_negative_number(confidence_score, field_name="confidence_score")

    if abs(sum(normalized_weights.values()) - 1.0) > _CONFIDENCE_TOLERANCE:
        raise ValueError("explanation.weights must sum to 1.0")
    if total > 1.0 + _CONFIDENCE_TOLERANCE:
        raise ValueError("explanation.score_breakdown.total must be <= 1.0")

    calculated_total = 0.0
    for component_name in _REQUIRED_BREAKDOWN_KEYS:
        expected_component = round(normalized_weights[component_name] * normalized_signals[component_name], 4)
        actual_component = normalized_score_breakdown[component_name]
        if abs(actual_component - expected_component) > _CONFIDENCE_TOLERANCE:
            raise ValueError(f"explanation.score_breakdown.{component_name} is inconsistent with weights/signals")
        calculated_total += actual_component

    if abs(total - calculated_total) > _CONFIDENCE_TOLERANCE:
        raise ValueError("explanation.score_breakdown.total must equal component sum")
    if abs(total - normalized_confidence_score) > _CONFIDENCE_TOLERANCE:
        raise ValueError("explanation.score_breakdown.total must match confidence_score")
    return explanation


def _require_mapping_section(*, explanation: dict[str, object], section_name: str) -> dict[str, object]:
    value = explanation.get(section_name)
    if not isinstance(value, dict):
        raise ValueError(f"explanation.{section_name} must be an object")
    return value


def _validate_breakdown_components(*, section: dict[str, object], field_name: str) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for component_name in _REQUIRED_BREAKDOWN_KEYS:
        if component_name not in section:
            raise ValueError(f"explanation.{field_name}.{component_name} is required")
        component_value = _validate_non_negative_number(
            section.get(component_name),
            field_name=f"{field_name}.{component_name}",
        )
        if component_value > 1.0 + _CONFIDENCE_TOLERANCE:
            raise ValueError(f"explanation.{field_name}.{component_name} must be <= 1.0")
        normalized[component_name] = component_value
    return normalized


def _validate_non_negative_number(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"explanation.{field_name} must be a number")
    normalized = float(value)
    if normalized < 0:
        raise ValueError(f"explanation.{field_name} must be non-negative")
    return normalized


event_reason_store = EventReasonStore()
