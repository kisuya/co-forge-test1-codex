from __future__ import annotations

from datetime import datetime
from typing import Any

from apps.domain.events import parse_utc_datetime
from apps.domain.notifications import VALID_CHANNELS, notification_store
from apps.infra.observability import log_error, log_info


def _build_message(event: dict[str, Any], reasons: list[dict[str, Any]]) -> str:
    symbol = event.get("symbol", "UNKNOWN")
    market = event.get("market", "N/A")
    change_pct = event.get("change_pct", 0)
    window = event.get("window_minutes", 0)

    if reasons:
        top_reason = reasons[0]
        reason_type = top_reason.get("reason_type", "unknown")
        source_url = top_reason.get("source_url", "")
        return (
            f"{market}:{symbol} moved {change_pct:+.2f}% in {window}m. "
            f"Top reason: {reason_type}. Source: {source_url}"
        )
    return f"{market}:{symbol} moved {change_pct:+.2f}% in {window}m."


def dispatch_event_notifications(
    *,
    event: dict[str, Any],
    reasons: list[dict[str, Any]],
    user_id: str,
    channels: list[str] | None = None,
    now_utc: datetime | str,
    request_id: str | None = None,
) -> list[dict[str, str]]:
    active_channels = channels or ["in_app", "email"]
    sent_at = parse_utc_datetime(now_utc)
    event_id = str(event["id"])
    message = _build_message(event, reasons)

    dispatched: list[dict[str, str]] = []
    for channel in active_channels:
        if channel not in VALID_CHANNELS:
            log_error(
                feature="ops-003",
                event="worker_notification_failed",
                request_id=request_id,
                logger_name="oh_my_stock.worker",
                user_id=user_id,
                event_id=event_id,
                channel=channel,
                reason="unsupported_channel",
            )
            raise ValueError("unsupported channel")
        if notification_store.in_cooldown(
            user_id=user_id,
            event_id=event_id,
            channel=channel,
            sent_at=sent_at,
            cooldown_minutes=30,
            ):
            log_info(
                feature="ops-003",
                event="worker_notification_skipped_cooldown",
                request_id=request_id,
                logger_name="oh_my_stock.worker",
                user_id=user_id,
                event_id=event_id,
                channel=channel,
            )
            continue

        notification = notification_store.create_notification(
            user_id=user_id,
            event_id=event_id,
            channel=channel,
            sent_at=sent_at,
            message=message,
            status="sent",
        )
        notification_store.save(notification)
        dispatched.append(notification.to_dict())
        log_info(
            feature="ops-003",
            event="worker_notification_sent",
            request_id=request_id,
            logger_name="oh_my_stock.worker",
            notification_id=notification.id,
            user_id=user_id,
            event_id=event_id,
            channel=channel,
        )

    return dispatched
