from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import os
from typing import Any

from apps.domain.events import parse_utc_datetime, to_utc_iso
from apps.worker.brief_delivery_scheduler_support import (
    collect_existing_dedupe_keys,
    index_user_settings,
    schedule_jobs_for_briefs,
    schedule_retry_and_compensation,
)


@dataclass(frozen=True)
class BriefDeliveryPolicy:
    pre_market_lead_minutes: int
    post_close_delay_minutes: int
    retry_delay_minutes: int
    max_retry_attempts: int

    @classmethod
    def from_env(cls) -> "BriefDeliveryPolicy":
        return cls(
            pre_market_lead_minutes=_parse_int(
                os.getenv("BRIEF_PRE_MARKET_LEAD_MINUTES"),
                fallback=45,
                variable_name="BRIEF_PRE_MARKET_LEAD_MINUTES",
                minimum=1,
            ),
            post_close_delay_minutes=_parse_int(
                os.getenv("BRIEF_POST_CLOSE_DELAY_MINUTES"),
                fallback=20,
                variable_name="BRIEF_POST_CLOSE_DELAY_MINUTES",
                minimum=0,
            ),
            retry_delay_minutes=_parse_int(
                os.getenv("BRIEF_RETRY_DELAY_MINUTES"),
                fallback=5,
                variable_name="BRIEF_RETRY_DELAY_MINUTES",
                minimum=1,
            ),
            max_retry_attempts=_parse_int(
                os.getenv("BRIEF_MAX_RETRY_ATTEMPTS"),
                fallback=3,
                variable_name="BRIEF_MAX_RETRY_ATTEMPTS",
                minimum=1,
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def schedule_brief_deliveries(
    *,
    user_settings: list[dict[str, Any]],
    pre_market_briefs: list[dict[str, Any]],
    post_close_briefs: list[dict[str, Any]],
    existing_jobs: list[dict[str, Any]] | None,
    channel_failures: list[dict[str, Any]] | None,
    now_utc: datetime | str,
    policy: BriefDeliveryPolicy | None = None,
) -> dict[str, object]:
    evaluated_at = parse_utc_datetime(now_utc)
    try:
        active_policy = policy or BriefDeliveryPolicy.from_env()
    except ValueError:
        return {
            "scheduled_jobs": [],
            "retry_jobs": [],
            "compensations": [],
            "skipped_duplicates": [],
            "policy": None,
            "evaluated_at_utc": to_utc_iso(evaluated_at),
            "fallback_reason": "policy_missing",
        }

    settings = index_user_settings(user_settings)
    dedupe_keys = collect_existing_dedupe_keys(existing_jobs or [])

    scheduled_jobs: list[dict[str, object]] = []
    skipped_duplicates: list[str] = []
    scheduled_jobs.extend(
        schedule_jobs_for_briefs(
            brief_type="pre_market",
            briefs=pre_market_briefs,
            user_settings=settings,
            policy=active_policy,
            now_utc=evaluated_at,
            dedupe_keys=dedupe_keys,
            skipped_duplicates=skipped_duplicates,
        )
    )
    scheduled_jobs.extend(
        schedule_jobs_for_briefs(
            brief_type="post_close",
            briefs=post_close_briefs,
            user_settings=settings,
            policy=active_policy,
            now_utc=evaluated_at,
            dedupe_keys=dedupe_keys,
            skipped_duplicates=skipped_duplicates,
        )
    )

    retry_jobs, compensations = schedule_retry_and_compensation(
        channel_failures=channel_failures or [],
        policy=active_policy,
        now_utc=evaluated_at,
    )

    return {
        "scheduled_jobs": scheduled_jobs,
        "retry_jobs": retry_jobs,
        "compensations": compensations,
        "skipped_duplicates": sorted(set(skipped_duplicates)),
        "policy": active_policy.to_dict(),
        "evaluated_at_utc": to_utc_iso(evaluated_at),
        "fallback_reason": None,
    }


def _parse_int(value: str | None, *, fallback: int, variable_name: str, minimum: int) -> int:
    if value is None or value.strip() == "":
        return fallback
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{variable_name} must be an integer") from exc
    if parsed < minimum:
        raise ValueError(f"{variable_name} must be >= {minimum}")
    return parsed
