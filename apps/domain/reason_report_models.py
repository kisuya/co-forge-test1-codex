from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from numbers import Real

_VALID_REPORT_TYPES = {
    "inaccurate_reason",
    "wrong_source",
    "outdated_information",
    "other",
}


class ReasonReportValidationError(ValueError):
    pass


class ReasonReportConflictError(RuntimeError):
    pass


class ReasonReportNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReasonReport:
    id: str
    user_id: str
    event_id: str
    reason_id: str
    report_type: str
    note: str
    status: str
    created_at_utc: str
    updated_at_utc: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "event_id": self.event_id,
            "reason_id": self.reason_id,
            "report_type": self.report_type,
            "note": self.note,
            "status": self.status,
            "created_at_utc": self.created_at_utc,
            "updated_at_utc": self.updated_at_utc,
        }


@dataclass(frozen=True)
class ReasonReportStatusTransition:
    report_id: str
    event_id: str
    reason_id: str
    from_status: str | None
    to_status: str
    changed_at_utc: str
    note: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "report_id": self.report_id,
            "event_id": self.event_id,
            "reason_id": self.reason_id,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "changed_at_utc": self.changed_at_utc,
            "note": self.note,
        }


@dataclass(frozen=True)
class ReasonRevision:
    id: str
    report_id: str
    event_id: str
    reason_id: str
    revision_reason: str
    confidence_before: float
    confidence_after: float
    revised_at_utc: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "report_id": self.report_id,
            "event_id": self.event_id,
            "reason_id": self.reason_id,
            "revision_reason": self.revision_reason,
            "confidence_before": self.confidence_before,
            "confidence_after": self.confidence_after,
            "revised_at_utc": self.revised_at_utc,
        }


def normalize_non_empty(value: str, *, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ReasonReportValidationError(f"{field_name} must not be empty")
    return normalized


def normalize_report_type(report_type: str) -> str:
    normalized = (report_type or "").strip().lower()
    if normalized not in _VALID_REPORT_TYPES:
        raise ReasonReportValidationError(
            "report_type must be one of inaccurate_reason, wrong_source, outdated_information, other"
        )
    return normalized


def normalize_note(note: str) -> str:
    if not isinstance(note, str):
        raise ReasonReportValidationError("note must be a string")
    normalized = note.strip()
    if len(normalized) > 500:
        raise ReasonReportValidationError("note must be <= 500 characters")
    return normalized


def normalize_optional_note(note: str | None) -> str | None:
    if note is None:
        return None
    return normalize_note(note)


def normalize_confidence(value: float, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ReasonReportValidationError(f"{field_name} must be a number")
    normalized = float(value)
    if normalized < 0.0 or normalized > 1.0:
        raise ReasonReportValidationError(f"{field_name} must be between 0 and 1")
    return round(normalized, 4)


def ensure_transition_order(*, current_status: str, target_status: str) -> None:
    if target_status == "reviewed" and current_status != "received":
        raise ReasonReportValidationError("status transition must follow received -> reviewed -> resolved")
    if target_status == "resolved" and current_status != "reviewed":
        raise ReasonReportValidationError("status transition must follow received -> reviewed -> resolved")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
