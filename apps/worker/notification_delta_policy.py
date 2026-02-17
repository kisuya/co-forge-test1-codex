from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from numbers import Real
import os
from typing import Any

from apps.domain.events import parse_utc_datetime, to_utc_iso


@dataclass(frozen=True)
class NotificationDeltaPolicyConfig:
    min_confidence_delta: float
    min_added_sources: int
    min_removed_sources: int
    cooldown_minutes: int

    @classmethod
    def from_env(cls) -> "NotificationDeltaPolicyConfig":
        min_confidence_delta = _parse_float(
            os.getenv("NOTIFY_DELTA_CONFIDENCE_THRESHOLD"),
            fallback=0.05,
            variable_name="NOTIFY_DELTA_CONFIDENCE_THRESHOLD",
            minimum=0.0,
        )
        min_added_sources = _parse_int(
            os.getenv("NOTIFY_DELTA_MIN_ADDED_SOURCES"),
            fallback=1,
            variable_name="NOTIFY_DELTA_MIN_ADDED_SOURCES",
            minimum=1,
        )
        min_removed_sources = _parse_int(
            os.getenv("NOTIFY_DELTA_MIN_REMOVED_SOURCES"),
            fallback=1,
            variable_name="NOTIFY_DELTA_MIN_REMOVED_SOURCES",
            minimum=1,
        )
        cooldown_minutes = _parse_int(
            os.getenv("NOTIFY_DELTA_COOLDOWN_MINUTES"),
            fallback=30,
            variable_name="NOTIFY_DELTA_COOLDOWN_MINUTES",
            minimum=1,
        )
        return cls(
            min_confidence_delta=min_confidence_delta,
            min_added_sources=min_added_sources,
            min_removed_sources=min_removed_sources,
            cooldown_minutes=cooldown_minutes,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def evaluate_notification_delta_policy(
    *,
    delta_payload: dict[str, Any],
    cooldown_state: dict[str, Any] | None,
    now_utc: datetime | str,
    policy: NotificationDeltaPolicyConfig | None = None,
) -> dict[str, Any]:
    try:
        active_policy = policy or NotificationDeltaPolicyConfig.from_env()
    except ValueError:
        parsed_now = parse_utc_datetime(now_utc)
        return {
            "should_send": False,
            "history_only": True,
            "reason_code": "policy_missing",
            "matched_reasons": [],
            "cooldown_until_utc": None,
            "evaluated_at_utc": to_utc_iso(parsed_now),
            "policy": None,
        }

    evaluated_at = parse_utc_datetime(now_utc)
    cooldown_until = _resolve_cooldown_until(
        cooldown_state=cooldown_state,
        cooldown_minutes=active_policy.cooldown_minutes,
    )
    if cooldown_until is not None and evaluated_at < cooldown_until:
        return {
            "should_send": False,
            "history_only": True,
            "reason_code": "cooldown_active",
            "matched_reasons": [],
            "cooldown_until_utc": to_utc_iso(cooldown_until),
            "evaluated_at_utc": to_utc_iso(evaluated_at),
            "policy": active_policy.to_dict(),
        }

    parsed = _parse_delta_payload(delta_payload)
    if parsed is None:
        return {
            "should_send": False,
            "history_only": True,
            "reason_code": "policy_data_missing",
            "matched_reasons": [],
            "cooldown_until_utc": None,
            "evaluated_at_utc": to_utc_iso(evaluated_at),
            "policy": active_policy.to_dict(),
        }

    matched_reasons = _match_policy_reasons(
        added_sources=parsed["added_sources"],
        removed_sources=parsed["removed_sources"],
        confidence_delta=parsed["confidence_delta"],
        policy=active_policy,
    )
    if not matched_reasons:
        return {
            "should_send": False,
            "history_only": True,
            "reason_code": "delta_below_threshold",
            "matched_reasons": [],
            "cooldown_until_utc": None,
            "evaluated_at_utc": to_utc_iso(evaluated_at),
            "policy": active_policy.to_dict(),
        }

    primary = _to_reason_code(matched_reasons)
    return {
        "should_send": True,
        "history_only": False,
        "reason_code": primary,
        "matched_reasons": matched_reasons,
        "cooldown_until_utc": to_utc_iso(evaluated_at + timedelta(minutes=active_policy.cooldown_minutes)),
        "evaluated_at_utc": to_utc_iso(evaluated_at),
        "policy": active_policy.to_dict(),
    }


def _resolve_cooldown_until(
    *,
    cooldown_state: dict[str, Any] | None,
    cooldown_minutes: int,
) -> datetime | None:
    if not isinstance(cooldown_state, dict):
        return None

    until_value = cooldown_state.get("cooldown_until_utc")
    if until_value:
        return parse_utc_datetime(until_value)

    last_sent = cooldown_state.get("last_sent_at_utc")
    if last_sent:
        return parse_utc_datetime(last_sent) + timedelta(minutes=cooldown_minutes)

    return None


def _parse_delta_payload(delta_payload: dict[str, Any]) -> dict[str, object] | None:
    if not isinstance(delta_payload, dict):
        return None
    added = delta_payload.get("added_sources")
    removed = delta_payload.get("removed_sources")
    confidence_delta = delta_payload.get("confidence_delta")

    if not isinstance(added, list) or not isinstance(removed, list):
        return None
    if isinstance(confidence_delta, bool) or not isinstance(confidence_delta, Real):
        return None

    normalized_added = [str(item).strip() for item in added if str(item).strip()]
    normalized_removed = [str(item).strip() for item in removed if str(item).strip()]
    normalized_delta = abs(float(confidence_delta))

    return {
        "added_sources": normalized_added,
        "removed_sources": normalized_removed,
        "confidence_delta": normalized_delta,
    }


def _match_policy_reasons(
    *,
    added_sources: list[str],
    removed_sources: list[str],
    confidence_delta: float,
    policy: NotificationDeltaPolicyConfig,
) -> list[str]:
    matched: list[str] = []
    if confidence_delta >= policy.min_confidence_delta:
        matched.append("confidence_delta")
    if len(added_sources) >= policy.min_added_sources:
        matched.append("source_added")
    if len(removed_sources) >= policy.min_removed_sources:
        matched.append("source_removed")
    return matched


def _to_reason_code(matched_reasons: list[str]) -> str:
    if "confidence_delta" in matched_reasons:
        return "confidence_changed"
    if "source_added" in matched_reasons:
        return "source_added"
    return "source_removed"


def _parse_float(
    value: str | None,
    *,
    fallback: float,
    variable_name: str,
    minimum: float,
) -> float:
    if value is None or value.strip() == "":
        return fallback
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{variable_name} must be a float") from exc
    if parsed < minimum:
        raise ValueError(f"{variable_name} must be >= {minimum}")
    return parsed


def _parse_int(
    value: str | None,
    *,
    fallback: int,
    variable_name: str,
    minimum: int,
) -> int:
    if value is None or value.strip() == "":
        return fallback
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{variable_name} must be an integer") from exc
    if parsed < minimum:
        raise ValueError(f"{variable_name} must be >= {minimum}")
    return parsed
