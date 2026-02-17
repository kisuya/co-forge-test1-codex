from __future__ import annotations

from uuid import uuid4

from apps.domain.reason_report_models import (
    ReasonReport,
    ReasonReportConflictError,
    ReasonReportNotFoundError,
    ReasonReportStatusTransition,
    ReasonRevision,
    ensure_transition_order,
    normalize_confidence,
    normalize_non_empty,
    normalize_note,
    normalize_optional_note,
    normalize_report_type,
    utc_now_iso,
)
from apps.domain.reasons import event_reason_store


class ReasonReportStore:
    def __init__(self) -> None:
        self._reports_by_id: dict[str, ReasonReport] = {}
        self._report_ids_by_event: dict[str, list[str]] = {}
        self._open_report_ids_by_scope: dict[tuple[str, str, str], str] = {}
        self._transitions_by_event: dict[str, list[ReasonReportStatusTransition]] = {}
        self._revisions_by_event: dict[str, list[ReasonRevision]] = {}
        self._failure_mode: str | None = None

    def clear(self) -> None:
        self._reports_by_id.clear()
        self._report_ids_by_event.clear()
        self._open_report_ids_by_scope.clear()
        self._transitions_by_event.clear()
        self._revisions_by_event.clear()
        self._failure_mode = None

    def set_failure_mode(self, mode: str | None) -> None:
        self._failure_mode = mode

    def submit(
        self,
        *,
        user_id: str,
        event_id: str,
        reason_id: str,
        report_type: str,
        note: str,
    ) -> ReasonReport:
        self._raise_if_transient_failure()

        normalized_user_id = normalize_non_empty(user_id, field_name="user_id")
        normalized_event_id = normalize_non_empty(event_id, field_name="event_id")
        normalized_reason_id = normalize_non_empty(reason_id, field_name="reason_id")
        normalized_report_type = normalize_report_type(report_type)
        normalized_note = normalize_note(note)
        _validate_reason_belongs_to_event(event_id=normalized_event_id, reason_id=normalized_reason_id)

        scope_key = (normalized_user_id, normalized_event_id, normalized_reason_id)
        if scope_key in self._open_report_ids_by_scope:
            raise ReasonReportConflictError("duplicate open reason report")

        now_utc = utc_now_iso()
        report = ReasonReport(
            id=str(uuid4()),
            user_id=normalized_user_id,
            event_id=normalized_event_id,
            reason_id=normalized_reason_id,
            report_type=normalized_report_type,
            note=normalized_note,
            status="received",
            created_at_utc=now_utc,
            updated_at_utc=now_utc,
        )

        self._reports_by_id[report.id] = report
        self._report_ids_by_event.setdefault(normalized_event_id, []).append(report.id)
        self._open_report_ids_by_scope[scope_key] = report.id
        self._append_transition(
            report_id=report.id,
            event_id=report.event_id,
            reason_id=report.reason_id,
            from_status=None,
            to_status=report.status,
            note=None,
            changed_at_utc=report.created_at_utc,
        )
        return report

    def discard(self, report_id: str) -> None:
        normalized_report_id = (report_id or "").strip()
        if not normalized_report_id:
            return
        report = self._reports_by_id.pop(normalized_report_id, None)
        if report is None:
            return

        scope_key = (report.user_id, report.event_id, report.reason_id)
        if self._open_report_ids_by_scope.get(scope_key) == report.id:
            self._open_report_ids_by_scope.pop(scope_key, None)

        report_ids = self._report_ids_by_event.get(report.event_id, [])
        self._report_ids_by_event[report.event_id] = [item for item in report_ids if item != report.id]

        transitions = self._transitions_by_event.get(report.event_id, [])
        self._transitions_by_event[report.event_id] = [item for item in transitions if item.report_id != report.id]

        revisions = self._revisions_by_event.get(report.event_id, [])
        self._revisions_by_event[report.event_id] = [item for item in revisions if item.report_id != report.id]

    def get_report(self, report_id: str) -> ReasonReport | None:
        self._raise_if_transient_failure()
        normalized_report_id = normalize_non_empty(report_id, field_name="report_id")
        return self._reports_by_id.get(normalized_report_id)

    def mark_reviewed(self, *, report_id: str, note: str | None = None) -> ReasonReport:
        self._raise_if_transient_failure()
        report = self._require_report(report_id)
        ensure_transition_order(current_status=report.status, target_status="reviewed")

        updated = ReasonReport(
            id=report.id,
            user_id=report.user_id,
            event_id=report.event_id,
            reason_id=report.reason_id,
            report_type=report.report_type,
            note=report.note,
            status="reviewed",
            created_at_utc=report.created_at_utc,
            updated_at_utc=utc_now_iso(),
        )
        self._reports_by_id[updated.id] = updated
        self._append_transition(
            report_id=updated.id,
            event_id=updated.event_id,
            reason_id=updated.reason_id,
            from_status=report.status,
            to_status=updated.status,
            note=normalize_optional_note(note),
            changed_at_utc=updated.updated_at_utc,
        )
        return updated

    def resolve_report(
        self,
        *,
        report_id: str,
        revision_reason: str,
        confidence_before: float,
        confidence_after: float,
        note: str | None = None,
    ) -> tuple[ReasonReport, ReasonRevision]:
        self._raise_if_transient_failure()
        report = self._require_report(report_id)
        ensure_transition_order(current_status=report.status, target_status="resolved")

        normalized_revision_reason = normalize_non_empty(revision_reason, field_name="revision_reason")
        normalized_confidence_before = normalize_confidence(confidence_before, field_name="confidence_before")
        normalized_confidence_after = normalize_confidence(confidence_after, field_name="confidence_after")
        resolved_at_utc = utc_now_iso()

        updated = ReasonReport(
            id=report.id,
            user_id=report.user_id,
            event_id=report.event_id,
            reason_id=report.reason_id,
            report_type=report.report_type,
            note=report.note,
            status="resolved",
            created_at_utc=report.created_at_utc,
            updated_at_utc=resolved_at_utc,
        )
        self._reports_by_id[updated.id] = updated

        scope_key = (updated.user_id, updated.event_id, updated.reason_id)
        if self._open_report_ids_by_scope.get(scope_key) == updated.id:
            self._open_report_ids_by_scope.pop(scope_key, None)

        self._append_transition(
            report_id=updated.id,
            event_id=updated.event_id,
            reason_id=updated.reason_id,
            from_status=report.status,
            to_status=updated.status,
            note=normalize_optional_note(note),
            changed_at_utc=updated.updated_at_utc,
        )

        revision = ReasonRevision(
            id=str(uuid4()),
            report_id=updated.id,
            event_id=updated.event_id,
            reason_id=updated.reason_id,
            revision_reason=normalized_revision_reason,
            confidence_before=normalized_confidence_before,
            confidence_after=normalized_confidence_after,
            revised_at_utc=resolved_at_utc,
        )
        self._revisions_by_event.setdefault(updated.event_id, []).append(revision)
        return updated, revision

    def list_event_history(self, event_id: str) -> tuple[list[ReasonRevision], list[ReasonReportStatusTransition]]:
        self._raise_if_transient_failure()
        normalized_event_id = normalize_non_empty(event_id, field_name="event_id")
        revisions = list(self._revisions_by_event.get(normalized_event_id, []))
        transitions = list(self._transitions_by_event.get(normalized_event_id, []))
        return revisions, transitions

    def _require_report(self, report_id: str) -> ReasonReport:
        normalized_report_id = normalize_non_empty(report_id, field_name="report_id")
        report = self._reports_by_id.get(normalized_report_id)
        if report is None:
            raise ReasonReportNotFoundError("reason report not found")
        return report

    def _append_transition(
        self,
        *,
        report_id: str,
        event_id: str,
        reason_id: str,
        from_status: str | None,
        to_status: str,
        note: str | None,
        changed_at_utc: str,
    ) -> None:
        transition = ReasonReportStatusTransition(
            report_id=report_id,
            event_id=event_id,
            reason_id=reason_id,
            from_status=from_status,
            to_status=to_status,
            changed_at_utc=changed_at_utc,
            note=note,
        )
        self._transitions_by_event.setdefault(event_id, []).append(transition)

    def _raise_if_transient_failure(self) -> None:
        if self._failure_mode == "transient":
            raise RuntimeError("reason report store temporarily unavailable")


def _validate_reason_belongs_to_event(*, event_id: str, reason_id: str) -> None:
    reasons = event_reason_store.list_by_event(event_id)
    valid_reason_ids = {reason.id for reason in reasons}
    if reason_id not in valid_reason_ids:
        raise ReasonReportNotFoundError("reason_id not found for event")


reason_report_store = ReasonReportStore()
