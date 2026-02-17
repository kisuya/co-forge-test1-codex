from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from apps.domain.reason_report_models import utc_now_iso


@dataclass(frozen=True)
class ReasonReevaluationTask:
    id: str
    report_id: str
    event_id: str
    reason_id: str
    user_id: str
    report_type: str
    note: str
    queued_at_utc: str
    status: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "report_id": self.report_id,
            "event_id": self.event_id,
            "reason_id": self.reason_id,
            "user_id": self.user_id,
            "report_type": self.report_type,
            "note": self.note,
            "queued_at_utc": self.queued_at_utc,
            "status": self.status,
        }


class ReasonReevaluationQueue:
    def __init__(self) -> None:
        self._tasks: list[ReasonReevaluationTask] = []
        self._next_error: Exception | None = None

    def enqueue(self, task: ReasonReevaluationTask) -> ReasonReevaluationTask:
        if self._next_error is not None:
            error = self._next_error
            self._next_error = None
            raise error
        self._tasks.append(task)
        return task

    def list_tasks(self) -> list[ReasonReevaluationTask]:
        return list(self._tasks)

    def clear(self) -> None:
        self._tasks.clear()
        self._next_error = None

    def fail_next_enqueue(self, exc: Exception) -> None:
        self._next_error = exc


reason_reevaluation_queue = ReasonReevaluationQueue()


def build_reason_reevaluation_task(
    *,
    report_id: str,
    event_id: str,
    reason_id: str,
    user_id: str,
    report_type: str,
    note: str,
) -> ReasonReevaluationTask:
    return ReasonReevaluationTask(
        id=str(uuid4()),
        report_id=report_id,
        event_id=event_id,
        reason_id=reason_id,
        user_id=user_id,
        report_type=report_type,
        note=note,
        queued_at_utc=utc_now_iso(),
        status="queued",
    )
