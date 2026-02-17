from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

from apps.domain.events import to_utc_iso
from apps.worker.brief_market_clock import build_market_window_utc, normalize_market, to_market_local_iso

VALID_BRIEF_CHANNELS = {"in_app", "email"}


def index_user_settings(settings: list[dict[str, Any]]) -> dict[str, dict[str, object]]:
    indexed: dict[str, dict[str, object]] = {}
    for raw in settings:
        user_id = str(raw.get("user_id", "")).strip()
        if not user_id:
            continue

        markets: set[str] = set()
        for market in raw.get("markets", []):
            try:
                markets.add(normalize_market(str(market)))
            except ValueError:
                continue

        channels = {str(channel).strip() for channel in raw.get("channels", []) if str(channel).strip()}
        valid_channels = channels & VALID_BRIEF_CHANNELS
        if not valid_channels:
            valid_channels = {"in_app", "email"}

        indexed[user_id] = {"markets": markets, "channels": valid_channels}
    return indexed


def collect_existing_dedupe_keys(existing_jobs: list[dict[str, Any]]) -> set[str]:
    active: set[str] = set()
    for job in existing_jobs:
        status = str(job.get("status", "")).strip().lower()
        if status in {"failed", "cancelled"}:
            continue
        dedupe_key = str(job.get("dedupe_key", "")).strip()
        if dedupe_key:
            active.add(dedupe_key)
    return active


def schedule_jobs_for_briefs(
    *,
    brief_type: str,
    briefs: list[dict[str, Any]],
    user_settings: dict[str, dict[str, object]],
    policy: Any,
    now_utc: datetime,
    dedupe_keys: set[str],
    skipped_duplicates: list[str],
) -> list[dict[str, object]]:
    jobs: list[dict[str, object]] = []
    for brief in briefs:
        user_id = str(brief.get("user_id", "")).strip()
        if not user_id or user_id not in user_settings:
            continue

        try:
            market = normalize_market(str(brief.get("market", "")).strip())
        except ValueError:
            continue

        settings = user_settings[user_id]
        allowed_markets = settings.get("markets", set())
        if isinstance(allowed_markets, set) and allowed_markets and market not in allowed_markets:
            continue

        trade_date_local = _resolve_trade_date_local(brief=brief, market=market, now_utc=now_utc)
        scheduled_for = _resolve_schedule_time(
            brief_type=brief_type,
            market=market,
            trade_date_local=trade_date_local,
            policy=policy,
        )
        is_catchup = False
        if scheduled_for < now_utc:
            scheduled_for = now_utc
            is_catchup = True

        brief_id = str(brief.get("brief_id", "")).strip() or str(uuid4())
        channels = settings.get("channels", {"in_app", "email"})
        if not isinstance(channels, set):
            channels = {"in_app", "email"}

        for channel in sorted(channels):
            dedupe_key = build_dedupe_key(
                user_id=user_id,
                brief_type=brief_type,
                market=market,
                trade_date_local=trade_date_local,
                channel=channel,
            )
            if dedupe_key in dedupe_keys:
                skipped_duplicates.append(dedupe_key)
                continue

            jobs.append(
                {
                    "id": str(uuid4()),
                    "user_id": user_id,
                    "brief_id": brief_id,
                    "brief_type": brief_type,
                    "market": market,
                    "trade_date_local": trade_date_local,
                    "channel": channel,
                    "scheduled_for_utc": to_utc_iso(scheduled_for),
                    "status": "scheduled",
                    "dedupe_key": dedupe_key,
                    "attempt": 0,
                    "is_catchup": is_catchup,
                    "created_at_utc": to_utc_iso(now_utc),
                }
            )
            dedupe_keys.add(dedupe_key)
    return jobs


def schedule_retry_and_compensation(
    *,
    channel_failures: list[dict[str, Any]],
    policy: Any,
    now_utc: datetime,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    retry_jobs: list[dict[str, object]] = []
    compensations: list[dict[str, object]] = []
    for failure in channel_failures:
        dedupe_key = str(failure.get("dedupe_key", "")).strip()
        channel = str(failure.get("channel", "")).strip()
        retryable = bool(failure.get("retryable", False))
        attempt = _to_attempt(failure.get("attempt"))
        next_attempt = attempt + 1

        if not retryable or next_attempt > int(policy.max_retry_attempts):
            compensations.append(
                {
                    "dedupe_key": dedupe_key,
                    "channel": channel,
                    "action": "mark_failed",
                    "reason": str(failure.get("error", "")).strip() or "delivery_failed",
                    "attempt": attempt,
                    "recorded_at_utc": to_utc_iso(now_utc),
                }
            )
            continue

        backoff_multiplier = 2 ** max(0, attempt - 1)
        retry_at = now_utc + timedelta(minutes=int(policy.retry_delay_minutes) * backoff_multiplier)
        retry_jobs.append(
            {
                "id": str(uuid4()),
                "dedupe_key": dedupe_key,
                "channel": channel,
                "status": "retry_scheduled",
                "attempt": next_attempt,
                "scheduled_for_utc": to_utc_iso(retry_at),
                "created_at_utc": to_utc_iso(now_utc),
                "last_error": str(failure.get("error", "")).strip(),
            }
        )
    return retry_jobs, compensations


def build_dedupe_key(
    *,
    user_id: str,
    brief_type: str,
    market: str,
    trade_date_local: str,
    channel: str,
) -> str:
    return f"{user_id}:{brief_type}:{market}:{trade_date_local}:{channel}"


def _resolve_schedule_time(
    *,
    brief_type: str,
    market: str,
    trade_date_local: str,
    policy: Any,
) -> datetime:
    open_utc, close_utc = build_market_window_utc(market=market, trade_date_local=trade_date_local)
    if brief_type == "pre_market":
        return open_utc - timedelta(minutes=int(policy.pre_market_lead_minutes))
    return close_utc + timedelta(minutes=int(policy.post_close_delay_minutes))


def _resolve_trade_date_local(*, brief: dict[str, Any], market: str, now_utc: datetime) -> str:
    raw_trade_date = str(brief.get("trade_date_local", "")).strip()
    if raw_trade_date:
        return date.fromisoformat(raw_trade_date).isoformat()

    generated = brief.get("generated_at_utc")
    if generated is not None:
        generated_local = to_market_local_iso(market=market, timestamp_utc=generated)
        return datetime.fromisoformat(generated_local).date().isoformat()

    now_local = to_market_local_iso(market=market, timestamp_utc=now_utc)
    return datetime.fromisoformat(now_local).date().isoformat()


def _to_attempt(value: object) -> int:
    if isinstance(value, bool):
        return 1
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 1
    return parsed if parsed >= 1 else 1
