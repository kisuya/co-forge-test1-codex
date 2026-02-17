from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from apps.domain.events import parse_utc_datetime, to_utc_iso


def extract_str_list(payload: Mapping[str, object], keys: tuple[str, ...]) -> list[str]:
    merged: list[str] = []
    for key in keys:
        raw = payload.get(key)
        if isinstance(raw, list):
            merged.extend(str(item).strip() for item in raw if str(item).strip())
    deduped: list[str] = []
    for value in merged:
        if value not in deduped:
            deduped.append(value)
    return deduped


def extract_float(payload: Mapping[str, object], *, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
    return None


def extract_metric_value(metric_payload: object) -> float | None:
    if not isinstance(metric_payload, Mapping):
        return None
    value = metric_payload.get("value")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def normalize_status(payload: Mapping[str, object]) -> str | None:
    raw_status = payload.get("status")
    if isinstance(raw_status, str):
        normalized = raw_status.strip().lower()
        if normalized in {"pass", "fail", "flaky"}:
            return normalized
    passed = payload.get("passed")
    if isinstance(passed, bool):
        return "pass" if passed else "fail"
    return None


def normalize_generated_at(value: datetime | str | None) -> str:
    if value is None:
        return to_utc_iso(datetime.now(timezone.utc))
    return to_utc_iso(parse_utc_datetime(value))


def build_summary(*, release_gate: str, failure_reasons: list[dict[str, str]]) -> str:
    if release_gate == "pass":
        return "Release gate passed: all required quality gates satisfied."
    parts = [f"{item['gate']}:{item['code']}" for item in failure_reasons]
    return "Release gate failed: " + ", ".join(parts)
