from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from apps.domain.watchlists import VALID_MARKETS
from apps.infra.models import create_core_schema, execute_statement, fetch_all
from apps.infra.postgres import get_database_runtime

_DEFAULT_WATCHLIST_NAME = "default"
_PLACEHOLDER_HASH = "system-generated-password-hash"


@dataclass(frozen=True)
class WatchlistItemRecord:
    id: str
    user_id: str
    symbol: str
    market: str
    created_at_utc: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "symbol": self.symbol,
            "market": self.market,
            "created_at_utc": self.created_at_utc,
        }


class WatchlistDbService:
    def create_item(self, *, symbol: str, market: str, user_id: str) -> tuple[WatchlistItemRecord, bool]:
        normalized_symbol = _normalize_symbol(symbol)
        normalized_market = _normalize_market(market)
        normalized_user_id = _normalize_user_id(user_id)

        runtime = get_database_runtime()
        create_core_schema(runtime.engine)
        watchlist_id = self._ensure_default_watchlist(user_id=normalized_user_id)

        item_id = str(uuid4())
        try:
            execute_statement(
                runtime.engine,
                """
                INSERT INTO watchlist_items (id, watchlist_id, user_id, market, symbol)
                VALUES (?, ?, ?, ?, ?)
                """,
                (item_id, watchlist_id, normalized_user_id, normalized_market, normalized_symbol),
            )
            created = self._get_item_by_id(item_id=item_id)
            if created is None:
                raise RuntimeError("watchlist item insert succeeded but item lookup failed")
            return created, False
        except Exception as exc:  # noqa: BLE001 - DB backend exception type can vary.
            if not _is_duplicate_item_error(exc):
                raise
            existing = self._get_item_by_scope(
                user_id=normalized_user_id,
                market=normalized_market,
                symbol=normalized_symbol,
            )
            if existing is None:
                raise RuntimeError("duplicate watchlist item detected but existing row not found") from exc
            return existing, True

    def delete_item(self, *, item_id: str, user_id: str) -> bool:
        runtime = get_database_runtime()
        create_core_schema(runtime.engine)
        normalized_item_id = (item_id or "").strip()
        normalized_user_id = _normalize_user_id(user_id)
        if not normalized_item_id:
            return False

        row = fetch_all(
            runtime.engine,
            "SELECT id FROM watchlist_items WHERE id = ? AND user_id = ? LIMIT 1",
            (normalized_item_id, normalized_user_id),
        )
        if not row:
            return False

        execute_statement(
            runtime.engine,
            "DELETE FROM watchlist_items WHERE id = ? AND user_id = ?",
            (normalized_item_id, normalized_user_id),
        )
        return True

    def list_items(self, *, user_id: str, page: int, size: int) -> tuple[list[WatchlistItemRecord], int]:
        runtime = get_database_runtime()
        create_core_schema(runtime.engine)
        normalized_user_id = _normalize_user_id(user_id)
        offset = (page - 1) * size

        total_rows = fetch_all(
            runtime.engine,
            "SELECT COUNT(*) FROM watchlist_items WHERE user_id = ?",
            (normalized_user_id,),
        )
        total = int(total_rows[0][0]) if total_rows else 0

        rows = fetch_all(
            runtime.engine,
            """
            SELECT id, user_id, symbol, market, created_at_utc
            FROM watchlist_items
            WHERE user_id = ?
            ORDER BY created_at_utc DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (normalized_user_id, size, offset),
        )
        items = [_row_to_item(row) for row in rows]
        return items, total

    def _ensure_default_watchlist(self, *, user_id: str) -> str:
        runtime = get_database_runtime()
        row = fetch_all(
            runtime.engine,
            "SELECT id FROM watchlists WHERE user_id = ? AND name = ? LIMIT 1",
            (user_id, _DEFAULT_WATCHLIST_NAME),
        )
        if row:
            return str(row[0][0])

        self._ensure_user(user_id=user_id)
        watchlist_id = str(uuid4())
        execute_statement(
            runtime.engine,
            "INSERT INTO watchlists (id, user_id, name) VALUES (?, ?, ?)",
            (watchlist_id, user_id, _DEFAULT_WATCHLIST_NAME),
        )
        return watchlist_id

    def _ensure_user(self, *, user_id: str) -> None:
        runtime = get_database_runtime()
        row = fetch_all(
            runtime.engine,
            "SELECT id FROM users WHERE id = ? LIMIT 1",
            (user_id,),
        )
        if row:
            return

        execute_statement(
            runtime.engine,
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            (user_id, _placeholder_email(user_id), _PLACEHOLDER_HASH),
        )

    def _get_item_by_id(self, *, item_id: str) -> WatchlistItemRecord | None:
        runtime = get_database_runtime()
        rows = fetch_all(
            runtime.engine,
            """
            SELECT id, user_id, symbol, market, created_at_utc
            FROM watchlist_items
            WHERE id = ?
            LIMIT 1
            """,
            (item_id,),
        )
        if not rows:
            return None
        return _row_to_item(rows[0])

    def _get_item_by_scope(self, *, user_id: str, market: str, symbol: str) -> WatchlistItemRecord | None:
        runtime = get_database_runtime()
        rows = fetch_all(
            runtime.engine,
            """
            SELECT id, user_id, symbol, market, created_at_utc
            FROM watchlist_items
            WHERE user_id = ? AND market = ? AND symbol = ?
            LIMIT 1
            """,
            (user_id, market, symbol),
        )
        if not rows:
            return None
        return _row_to_item(rows[0])


def _row_to_item(row: tuple[object, ...]) -> WatchlistItemRecord:
    return WatchlistItemRecord(
        id=str(row[0]),
        user_id=str(row[1]),
        symbol=str(row[2]),
        market=str(row[3]),
        created_at_utc=str(row[4]),
    )


def _normalize_symbol(symbol: str) -> str:
    normalized = (symbol or "").strip().upper()
    if not normalized:
        raise ValueError("symbol must not be empty")
    return normalized


def _normalize_market(market: str) -> str:
    normalized = (market or "").strip().upper()
    if normalized not in VALID_MARKETS:
        raise ValueError("market must be KR or US")
    return normalized


def _normalize_user_id(user_id: str) -> str:
    normalized = (user_id or "").strip()
    if not normalized:
        raise ValueError("user_id must not be empty")
    return normalized


def _is_duplicate_item_error(exc: Exception) -> bool:
    message = str(exc).upper()
    return "UNIQUE" in message and "WATCHLIST_ITEMS.USER_ID" in message


def _placeholder_email(user_id: str) -> str:
    safe = "".join(char if char.isalnum() else "-" for char in user_id.lower())
    return f"{safe}@local.watchlist"


watchlist_db_service = WatchlistDbService()
