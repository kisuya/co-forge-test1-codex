from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from apps.api.auth_guard import require_authenticated_user
from apps.domain.events import parse_utc_datetime
from apps.domain.feedback import reason_feedback_store
from apps.domain.reason_report_models import (
    ReasonReportConflictError,
    ReasonReportNotFoundError,
    ReasonReportValidationError,
)
from apps.domain.reason_reports import reason_report_store
from apps.infra.models import create_core_schema, fetch_all
from apps.infra.postgres import get_database_runtime
from apps.worker.reason_reevaluation_queue import (
    build_reason_reevaluation_task,
    reason_reevaluation_queue,
)

_VALID_MARKETS = {"KR", "US"}


def register_feedback_routes(app: FastAPI) -> None:
    @app.post("/v1/events/{event_id}/feedback")
    def submit_reason_feedback(event_id: str, request: Request, body: dict[str, object]) -> tuple[dict[str, object], int]:
        user = require_authenticated_user(request)
        reason_id = str(body.get("reason_id", ""))
        feedback_value = str(body.get("feedback", ""))
        try:
            feedback, overwritten = reason_feedback_store.submit(
                user_id=user.user_id,
                event_id=event_id,
                reason_id=reason_id,
                feedback=feedback_value,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                code="invalid_input",
                message="Invalid feedback payload",
                details={"error": str(exc)},
            ) from exc
        status_code = 200 if overwritten else 201
        return {"feedback": feedback.to_dict(), "overwritten": overwritten}, status_code

    @app.get("/v1/feedback/aggregation")
    def aggregate_feedback(request: Request) -> dict[str, object]:
        require_authenticated_user(request)
        query = request.query_params
        from_utc = _parse_optional_datetime(query.get("from"), field_name="from")
        to_utc = _parse_optional_datetime(query.get("to"), field_name="to")
        if from_utc and to_utc and from_utc > to_utc:
            raise HTTPException(
                status_code=400,
                code="invalid_input",
                message="from must be <= to",
                details={"from": query.get("from"), "to": query.get("to")},
            )

        market = (query.get("market") or "").strip().upper() or None
        if market and market not in _VALID_MARKETS:
            raise HTTPException(
                status_code=400,
                code="invalid_input",
                message="market must be KR or US",
                details={"market": market},
            )
        min_samples = _parse_min_samples(query.get("min_samples"))
        symbol = (query.get("symbol") or "").strip().upper() or None

        try:
            items = reason_feedback_store.aggregate(
                from_utc=from_utc,
                to_utc=to_utc,
                symbol=symbol,
                market=market,
                min_samples=min_samples,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                code="invalid_input",
                message="Invalid aggregation filters",
                details={"error": str(exc)},
            ) from exc
        return {"items": items, "count": len(items)}

    @app.post("/v1/events/{event_id}/reason-reports")
    def submit_reason_report(event_id: str, request: Request, body: dict[str, object]) -> tuple[dict[str, object], int]:
        user = require_authenticated_user(request)
        _enforce_event_scope(event_id=event_id, user_id=user.user_id)

        reason_id, report_type, note = _parse_reason_report_payload(body)
        try:
            report = reason_report_store.submit(
                user_id=user.user_id,
                event_id=event_id,
                reason_id=reason_id,
                report_type=report_type,
                note=note,
            )
        except ReasonReportConflictError as exc:
            raise HTTPException(
                status_code=400,
                code="duplicate_reason_report",
                message="An open reason report already exists for this reason",
                details={"event_id": event_id, "reason_id": reason_id},
            ) from exc
        except ReasonReportNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                code="reason_not_found",
                message="Reason not found for event",
                details={"event_id": event_id, "reason_id": reason_id},
            ) from exc
        except ReasonReportValidationError as exc:
            raise HTTPException(
                status_code=400,
                code="invalid_input",
                message="Invalid reason report payload",
                details={"error": str(exc)},
            ) from exc

        task = build_reason_reevaluation_task(
            report_id=report.id,
            event_id=report.event_id,
            reason_id=report.reason_id,
            user_id=report.user_id,
            report_type=report.report_type,
            note=report.note,
        )
        try:
            reason_reevaluation_queue.enqueue(task)
        except Exception as exc:  # noqa: BLE001 - queue backend should not leave a dangling report.
            reason_report_store.discard(report.id)
            raise HTTPException(
                status_code=503,
                code="temporarily_unavailable",
                message="Reason report queue is temporarily unavailable",
                details={"retryable": True, "error": str(exc)},
            ) from exc

        return {"report_id": report.id, "status": report.status, "queued": True}, 201

    @app.get("/v1/events/{event_id}/reason-revisions")
    def get_reason_revisions(event_id: str, request: Request) -> dict[str, object]:
        user = require_authenticated_user(request)
        _enforce_event_scope(event_id=event_id, user_id=user.user_id)
        try:
            revisions, transitions = reason_report_store.list_event_history(event_id)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                code="temporarily_unavailable",
                message="Reason revision history is temporarily unavailable",
                details={"retryable": True, "error": str(exc)},
            ) from exc
        except ReasonReportValidationError as exc:
            raise HTTPException(
                status_code=400,
                code="invalid_input",
                message="Invalid event id",
                details={"error": str(exc)},
            ) from exc

        if not revisions and not transitions:
            raise HTTPException(
                status_code=404,
                code="reason_revision_history_not_found",
                message="Reason revision history not found",
                details={"event_id": event_id},
            )

        latest_status = transitions[-1].to_status if transitions else None
        return {
            "event_id": event_id,
            "revision_history": [revision.to_dict() for revision in revisions],
            "status_transitions": [transition.to_dict() for transition in transitions],
            "count": len(revisions),
            "meta": {
                "has_revision_history": bool(revisions),
                "latest_status": latest_status,
            },
        }


def _parse_optional_datetime(value: str | None, *, field_name: str):
    if not value:
        return None
    try:
        return parse_utc_datetime(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message=f"Invalid datetime format for '{field_name}'",
            details={"field": field_name, "value": value},
        ) from exc


def _parse_min_samples(value: str | None) -> int:
    raw = (value or "3").strip()
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="min_samples must be an integer",
            details={"min_samples": raw},
        ) from exc
    if parsed < 1:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="min_samples must be >= 1",
            details={"min_samples": parsed},
        )
    return parsed


def _parse_reason_report_payload(body: dict[str, object]) -> tuple[str, str, str]:
    reason_id = body.get("reason_id")
    report_type = body.get("report_type")
    note = body.get("note", "")
    if not isinstance(reason_id, str) or not isinstance(report_type, str):
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="Invalid reason report payload",
            details={"error": "reason_id and report_type must be strings"},
        )
    if note is None:
        note = ""
    if not isinstance(note, str):
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="Invalid reason report payload",
            details={"error": "note must be a string"},
        )
    return reason_id, report_type, note


def _enforce_event_scope(*, event_id: str, user_id: str) -> None:
    owner_user_id = _lookup_event_owner_user_id(event_id)
    if owner_user_id is not None and owner_user_id != user_id:
        raise HTTPException(
            status_code=403,
            code="forbidden",
            message="Forbidden resource access",
            details={"event_id": event_id},
        )


def _lookup_event_owner_user_id(event_id: str) -> str | None:
    normalized_event_id = (event_id or "").strip()
    if not normalized_event_id:
        return None

    runtime = get_database_runtime()
    create_core_schema(runtime.engine)
    rows = fetch_all(
        runtime.engine,
        "SELECT user_id FROM price_events WHERE id = ? LIMIT 1",
        (normalized_event_id,),
    )
    if not rows:
        return None
    return str(rows[0][0])
