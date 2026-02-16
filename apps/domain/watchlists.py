from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import uuid4

VALID_MARKETS = {"KR", "US"}
DEFAULT_USER_ID = "demo-user"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class WatchlistItem:
    id: str
    user_id: str
    symbol: str
    market: str
    created_at_utc: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class WatchlistService:
    def __init__(self) -> None:
        self._items_by_id: dict[str, WatchlistItem] = {}
        self._unique_index: dict[tuple[str, str, str], str] = {}

    def clear(self) -> None:
        self._items_by_id.clear()
        self._unique_index.clear()

    def create_item(
        self, *, symbol: str, market: str, user_id: str | None = None
    ) -> tuple[WatchlistItem, bool]:
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_market = self._normalize_market(market)
        normalized_user = (user_id or DEFAULT_USER_ID).strip() or DEFAULT_USER_ID

        unique_key = (normalized_user, normalized_market, normalized_symbol)
        existing_item_id = self._unique_index.get(unique_key)
        if existing_item_id:
            return self._items_by_id[existing_item_id], True

        item = WatchlistItem(
            id=str(uuid4()),
            user_id=normalized_user,
            symbol=normalized_symbol,
            market=normalized_market,
            created_at_utc=_utc_now_iso(),
        )
        self._items_by_id[item.id] = item
        self._unique_index[unique_key] = item.id
        return item, False

    def delete_item(self, item_id: str) -> bool:
        item = self._items_by_id.pop(item_id, None)
        if not item:
            return False
        unique_key = (item.user_id, item.market, item.symbol)
        self._unique_index.pop(unique_key, None)
        return True

    def list_items(self, *, user_id: str | None = None) -> list[WatchlistItem]:
        if user_id is None:
            return list(self._items_by_id.values())
        return [item for item in self._items_by_id.values() if item.user_id == user_id]

    def _normalize_symbol(self, symbol: str) -> str:
        normalized = (symbol or "").strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty")
        return normalized

    def _normalize_market(self, market: str) -> str:
        normalized = (market or "").strip().upper()
        if normalized not in VALID_MARKETS:
            raise ValueError("market must be KR or US")
        return normalized


watchlist_service = WatchlistService()
