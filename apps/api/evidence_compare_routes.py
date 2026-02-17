from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from apps.api.auth_guard import require_authenticated_user
from apps.domain.evidence_compare import build_evidence_compare_payload
from apps.domain.events import parse_utc_datetime, price_event_store, to_utc_iso
from apps.domain.reasons import event_reason_store

_AXES = ("positive", "negative", "uncertain")


def register_evidence_compare_routes(app: FastAPI) -> None:
    @app.get("/v1/events/{event_id}/evidence-compare")
    def get_evidence_compare(event_id: str, request: Request) -> dict[str, Any]:
        event = price_event_store.get_event(event_id)
        if event is None:
            raise HTTPException(
                status_code=404,
                code="event_not_found",
                message="Event not found",
                details={"event_id": event_id},
            )

        if _has_permission_error(request):
            return _build_compare_unavailable_payload(
                event_id=event_id,
                fallback_reason="permission_denied",
            )

        reasons = [reason.to_dict() for reason in event_reason_store.list_by_event(event_id)]
        if _has_missing_source_metadata(reasons):
            return _build_compare_unavailable_payload(
                event_id=event_id,
                fallback_reason="missing_source_metadata",
                evidence_count=len(reasons),
            )

        payload = build_evidence_compare_payload(event_id=event_id, evidences=reasons)
        payload["sources"] = _collect_source_meta(payload["axes"])
        return payload


def _has_permission_error(request: Request) -> bool:
    authorization = request.headers.get("authorization", "").strip()
    if not authorization:
        return False
    try:
        require_authenticated_user(request)
    except HTTPException:
        return True
    return False


def _has_missing_source_metadata(reasons: list[dict[str, object]]) -> bool:
    for reason in reasons:
        source_url = str(reason.get("source_url") or "").strip()
        published_at = str(reason.get("published_at") or "").strip()
        if not source_url or not published_at:
            return True
        try:
            parse_utc_datetime(published_at)
        except Exception:  # noqa: BLE001 - malformed timestamp should mark compare as unavailable.
            return True
    return False


def _build_compare_unavailable_payload(
    *,
    event_id: str,
    fallback_reason: str,
    evidence_count: int = 0,
) -> dict[str, Any]:
    generated_at = to_utc_iso(datetime.now(timezone.utc))
    empty_axes = {axis: [] for axis in _AXES}
    empty_counts = {axis: 0 for axis in _AXES}
    return {
        "event_id": event_id,
        "status": "compare_unavailable",
        "compare_ready": False,
        "fallback_reason": fallback_reason,
        "bias_warning": "비교 근거가 충분하지 않거나 접근 권한이 없어 비교 카드를 표시하지 않습니다.",
        "axes": empty_axes,
        "axis_counts": empty_counts,
        "comparable_axis_count": 0,
        "evidence_count": evidence_count,
        "dropped_missing_metadata_count": 0,
        "generated_at_utc": generated_at,
        "sources": [],
    }


def _collect_source_meta(axes: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for axis in _AXES:
        for item in axes.get(axis, []):
            collected.append(
                {
                    "axis": axis,
                    "source_url": item["source_url"],
                    "published_at": item["published_at"],
                    "summary": item["summary"],
                }
            )
    collected.sort(key=lambda item: (str(item["published_at"]), str(item["source_url"])), reverse=True)
    return collected
