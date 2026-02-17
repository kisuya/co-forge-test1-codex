from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from apps.domain.events import parse_utc_datetime, to_utc_iso

_VALID_BRIEF_TYPES = {"pre_market", "post_close"}
_VALID_MARKETS = {"KR", "US"}
_VALID_STATUSES = {"unread", "read"}


class BriefValidationError(ValueError):
    """Raised when brief payload does not satisfy the API contract."""


class BriefNotFoundError(LookupError):
    """Raised when a requested brief does not exist for the user."""


class BriefExpiredError(LookupError):
    """Raised when a requested brief detail link has expired."""


@dataclass(frozen=True)
class BriefContentItem:
    event_id: str
    symbol: str
    market: str
    summary: str
    event_detail_url: str
    source_url: str

    def to_dict(self) -> dict[str, str]:
        return {
            "event_id": self.event_id,
            "symbol": self.symbol,
            "market": self.market,
            "summary": self.summary,
            "event_detail_url": self.event_detail_url,
            "source_url": self.source_url,
        }


@dataclass(frozen=True)
class BriefRecord:
    id: str
    user_id: str
    brief_type: str
    title: str
    summary: str
    generated_at_utc: str
    markets: tuple[str, ...]
    fallback_reason: str | None
    status: str
    expires_at_utc: str | None
    items: tuple[BriefContentItem, ...]


class BriefInboxStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], BriefRecord] = {}

    def clear(self) -> None:
        self._records.clear()

    def upsert_brief(
        self,
        *,
        brief_id: str,
        user_id: str,
        brief_type: str,
        title: str,
        summary: str,
        generated_at_utc: datetime | str,
        markets: list[str],
        items: list[dict[str, Any]],
        fallback_reason: str | None = None,
        status: str = "unread",
        expires_at_utc: datetime | str | None = None,
    ) -> BriefRecord:
        normalized_id = _require_non_empty(brief_id, field_name="brief_id")
        normalized_user_id = _require_non_empty(user_id, field_name="user_id")
        normalized_type = _normalize_brief_type(brief_type)
        normalized_title = _require_non_empty(title, field_name="title")
        normalized_summary = (summary or "").strip()
        normalized_generated_at = to_utc_iso(parse_utc_datetime(generated_at_utc))
        normalized_markets = tuple(_normalize_markets(markets))
        normalized_status = _normalize_status(status)
        normalized_items = tuple(_normalize_items(items))
        normalized_fallback = _normalize_optional_text(fallback_reason)
        normalized_expires_at = _normalize_optional_datetime(expires_at_utc)

        record = BriefRecord(
            id=normalized_id,
            user_id=normalized_user_id,
            brief_type=normalized_type,
            title=normalized_title,
            summary=normalized_summary,
            generated_at_utc=normalized_generated_at,
            markets=normalized_markets,
            fallback_reason=normalized_fallback,
            status=normalized_status,
            expires_at_utc=normalized_expires_at,
            items=normalized_items,
        )
        self._records[(normalized_user_id, normalized_id)] = record
        return record

    def list_briefs(self, *, user_id: str, limit: int = 20) -> list[BriefRecord]:
        normalized_user_id = _require_non_empty(user_id, field_name="user_id")
        safe_limit = max(1, min(limit, 50))
        items = [record for (owner_id, _), record in self._records.items() if owner_id == normalized_user_id]
        items.sort(key=lambda record: (record.generated_at_utc, record.id), reverse=True)
        return items[:safe_limit]

    def count_unread(self, *, user_id: str) -> int:
        normalized_user_id = _require_non_empty(user_id, field_name="user_id")
        return sum(
            1
            for (owner_id, _), record in self._records.items()
            if owner_id == normalized_user_id and record.status == "unread"
        )

    def get_brief(self, *, user_id: str, brief_id: str) -> BriefRecord:
        record = self._find_record(user_id=user_id, brief_id=brief_id)
        if self._is_expired(record):
            raise BriefExpiredError("brief detail link has expired")
        return record

    def mark_read(self, *, user_id: str, brief_id: str) -> BriefRecord:
        record = self._find_record(user_id=user_id, brief_id=brief_id)
        if record.status == "read":
            return record
        updated = BriefRecord(
            id=record.id,
            user_id=record.user_id,
            brief_type=record.brief_type,
            title=record.title,
            summary=record.summary,
            generated_at_utc=record.generated_at_utc,
            markets=record.markets,
            fallback_reason=record.fallback_reason,
            status="read",
            expires_at_utc=record.expires_at_utc,
            items=record.items,
        )
        self._records[(record.user_id, record.id)] = updated
        return updated

    def to_summary_dict(self, record: BriefRecord) -> dict[str, object]:
        return {
            "id": record.id,
            "brief_type": record.brief_type,
            "title": record.title,
            "summary": record.summary,
            "generated_at_utc": record.generated_at_utc,
            "markets": list(record.markets),
            "item_count": len(record.items),
            "fallback_reason": record.fallback_reason,
            "status": record.status,
            "is_expired": self._is_expired(record),
        }

    def to_detail_dict(self, record: BriefRecord) -> dict[str, object]:
        payload = self.to_summary_dict(record)
        payload["items"] = [item.to_dict() for item in record.items]
        return payload

    def _find_record(self, *, user_id: str, brief_id: str) -> BriefRecord:
        normalized_user_id = _require_non_empty(user_id, field_name="user_id")
        normalized_brief_id = _require_non_empty(brief_id, field_name="brief_id")
        record = self._records.get((normalized_user_id, normalized_brief_id))
        if record is None:
            raise BriefNotFoundError("brief not found")
        return record

    def _is_expired(self, record: BriefRecord) -> bool:
        if not record.expires_at_utc:
            return False
        expires_at = parse_utc_datetime(record.expires_at_utc)
        return expires_at <= datetime.now(timezone.utc)


brief_inbox_store = BriefInboxStore()


def _normalize_items(items: list[dict[str, Any]]) -> list[BriefContentItem]:
    normalized_items: list[BriefContentItem] = []
    for index, item in enumerate(items):
        event_id = _require_non_empty(str(item.get("event_id", "")), field_name=f"items[{index}].event_id")
        symbol = _require_non_empty(str(item.get("symbol", "")).upper(), field_name=f"items[{index}].symbol")
        market = _normalize_market(str(item.get("market", "")), field_name=f"items[{index}].market")
        summary = _require_non_empty(str(item.get("summary", "")), field_name=f"items[{index}].summary")
        event_detail_url = _require_non_empty(
            str(item.get("event_detail_url", "")),
            field_name=f"items[{index}].event_detail_url",
        )
        source_url = _require_non_empty(str(item.get("source_url", "")), field_name=f"items[{index}].source_url")
        normalized_items.append(
            BriefContentItem(
                event_id=event_id,
                symbol=symbol,
                market=market,
                summary=summary,
                event_detail_url=event_detail_url,
                source_url=source_url,
            )
        )
    return normalized_items


def _normalize_brief_type(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in _VALID_BRIEF_TYPES:
        raise BriefValidationError("brief_type must be pre_market or post_close")
    return normalized


def _normalize_markets(markets: list[str]) -> list[str]:
    return sorted({_normalize_market(market, field_name="markets") for market in markets if market.strip()})


def _normalize_market(value: str, *, field_name: str) -> str:
    normalized = (value or "").strip().upper()
    if normalized not in _VALID_MARKETS:
        raise BriefValidationError(f"{field_name} must be KR or US")
    return normalized


def _normalize_status(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in _VALID_STATUSES:
        raise BriefValidationError("status must be unread or read")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_optional_datetime(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    return to_utc_iso(parse_utc_datetime(value))


def _require_non_empty(value: str, *, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise BriefValidationError(f"{field_name} must not be empty")
    return normalized
