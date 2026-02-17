from __future__ import annotations

from collections.abc import Mapping

from fastapi import HTTPException, Request

from apps.api.auth_guard import require_authenticated_user
from apps.domain.portfolio_holdings_db import portfolio_holdings_db_service
from apps.domain.portfolio_impact import estimate_portfolio_event_impact
from apps.domain.reasons import event_reason_store

_REASON_STATUS_COLLECTING = "collecting_evidence"
_REASON_STATUS_VERIFIED = "verified"
_COMPONENT_KEYS = ("source_reliability", "event_match", "time_proximity")
_DEFAULT_EXPLANATION_TEXT = "근거 수집 중입니다. 검증 가능한 출처가 확보되면 confidence 설명이 갱신됩니다."
_COLLECTING_REVISION_HINT = "근거 수집/검증이 진행 중이며 카드 내용이 업데이트될 수 있습니다."
_PARTIAL_REVISION_HINT = "일부 confidence 설명 데이터가 누락되어 기본값으로 표시하고 있습니다."


def serialize_event(
    event: object,
    *,
    request: Request | None = None,
    include_reason_state: bool = False,
) -> dict[str, object]:
    event_payload = event.to_dict()
    reasons = [reason.to_dict() for reason in event_reason_store.list_by_event(event_payload["id"])]
    event_payload["reasons"] = reasons
    if include_reason_state:
        reason_state = _build_reason_state_fields(reasons)
        event_payload["reason_status"] = reason_state["reason_status"]
        event_payload["confidence_breakdown"] = reason_state["confidence_breakdown"]
        event_payload["explanation_text"] = reason_state["explanation_text"]
        event_payload["revision_hint"] = reason_state["revision_hint"]
    event_payload["portfolio_impact"] = build_portfolio_impact(event_payload, request=request)
    return event_payload


def _build_reason_state_fields(reasons: list[dict[str, object]]) -> dict[str, object]:
    if not reasons:
        return {
            "reason_status": _REASON_STATUS_COLLECTING,
            "confidence_breakdown": _default_confidence_breakdown(),
            "explanation_text": _DEFAULT_EXPLANATION_TEXT,
            "revision_hint": _COLLECTING_REVISION_HINT,
        }

    reason_status = _infer_reason_status(reasons)
    confidence_breakdown, has_partial_breakdown = _extract_confidence_breakdown(reasons[0])
    explanation_text, has_partial_text = _extract_explanation_text(reasons[0])

    if reason_status == _REASON_STATUS_COLLECTING:
        revision_hint: str | None = _COLLECTING_REVISION_HINT
    elif has_partial_breakdown or has_partial_text:
        revision_hint = _PARTIAL_REVISION_HINT
    else:
        revision_hint = None

    return {
        "reason_status": reason_status,
        "confidence_breakdown": confidence_breakdown,
        "explanation_text": explanation_text,
        "revision_hint": revision_hint,
    }


def _infer_reason_status(reasons: list[dict[str, object]]) -> str:
    for reason in reasons:
        status = reason.get("reason_status")
        if status in {_REASON_STATUS_COLLECTING, _REASON_STATUS_VERIFIED}:
            return str(status)

    has_evidence = any(str(reason.get("source_url") or "").strip() for reason in reasons)
    return _REASON_STATUS_VERIFIED if has_evidence else _REASON_STATUS_COLLECTING


def _extract_confidence_breakdown(reason: dict[str, object]) -> tuple[dict[str, object], bool]:
    explanation = reason.get("explanation")
    if not isinstance(explanation, Mapping):
        return _default_confidence_breakdown(), True

    weights, weights_partial = _normalize_components(explanation.get("weights"))
    signals, signals_partial = _normalize_components(explanation.get("signals"))
    score_breakdown, score_partial = _normalize_score_breakdown(explanation.get("score_breakdown"))
    return (
        {
            "weights": weights,
            "signals": signals,
            "score_breakdown": score_breakdown,
        },
        weights_partial or signals_partial or score_partial,
    )


def _extract_explanation_text(reason: dict[str, object]) -> tuple[str, bool]:
    explanation = reason.get("explanation")
    if not isinstance(explanation, Mapping):
        return _DEFAULT_EXPLANATION_TEXT, True

    explanation_text = explanation.get("explanation_text")
    if isinstance(explanation_text, str) and explanation_text.strip():
        return explanation_text.strip(), False
    return _DEFAULT_EXPLANATION_TEXT, True


def _normalize_components(section: object) -> tuple[dict[str, float], bool]:
    if not isinstance(section, Mapping):
        return {key: 0.0 for key in _COMPONENT_KEYS}, True

    normalized: dict[str, float] = {}
    is_partial = False
    for key in _COMPONENT_KEYS:
        value = section.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            normalized[key] = 0.0
            is_partial = True
            continue
        normalized[key] = float(value)
    return normalized, is_partial


def _normalize_score_breakdown(section: object) -> tuple[dict[str, float], bool]:
    if not isinstance(section, Mapping):
        return {
            "source_reliability": 0.0,
            "event_match": 0.0,
            "time_proximity": 0.0,
            "total": 0.0,
        }, True

    normalized: dict[str, float] = {}
    is_partial = False
    for key in (*_COMPONENT_KEYS, "total"):
        value = section.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            normalized[key] = 0.0
            is_partial = True
            continue
        normalized[key] = float(value)
    return normalized, is_partial


def _default_confidence_breakdown() -> dict[str, object]:
    return {
        "weights": {"source_reliability": 0.0, "event_match": 0.0, "time_proximity": 0.0},
        "signals": {"source_reliability": 0.0, "event_match": 0.0, "time_proximity": 0.0},
        "score_breakdown": {"source_reliability": 0.0, "event_match": 0.0, "time_proximity": 0.0, "total": 0.0},
    }


def build_portfolio_impact(
    event_payload: dict[str, object],
    *,
    request: Request | None,
) -> dict[str, object] | None:
    if request is None:
        return None
    if not request.headers.get("authorization", "").strip():
        return None

    try:
        user = require_authenticated_user(request)
    except HTTPException:
        return None

    holding = portfolio_holdings_db_service.get_by_symbol(
        user_id=user.user_id,
        symbol=str(event_payload["symbol"]),
    )
    if holding is None:
        return None

    try:
        impact = estimate_portfolio_event_impact(
            market=str(event_payload["market"]),
            qty=holding.qty,
            avg_price=holding.avg_price,
            change_pct=float(event_payload["change_pct"]),
        )
    except ValueError:
        return None
    impact["symbol"] = holding.symbol
    return impact
