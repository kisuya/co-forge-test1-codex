from __future__ import annotations

from dataclasses import dataclass
import math
from uuid import uuid4

from apps.infra.models import create_core_schema, execute_statement, fetch_all
from apps.infra.postgres import get_database_runtime

_PLACEHOLDER_HASH = "system-generated-password-hash"
_UTC_NOW_SQL = "STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now')"


@dataclass(frozen=True)
class PortfolioHoldingRecord:
    id: str
    user_id: str
    symbol: str
    qty: float
    avg_price: float
    created_at_utc: str
    updated_at_utc: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "symbol": self.symbol,
            "qty": self.qty,
            "avg_price": self.avg_price,
            "created_at_utc": self.created_at_utc,
            "updated_at_utc": self.updated_at_utc,
        }


class PortfolioHoldingsDbService:
    def upsert_holding(
        self,
        *,
        user_id: str,
        symbol: str,
        qty: float,
        avg_price: float,
    ) -> tuple[PortfolioHoldingRecord, bool]:
        normalized_user_id = _normalize_user_id(user_id)
        normalized_symbol = _normalize_symbol(symbol)
        normalized_qty = _normalize_positive_float(qty, field_name="qty")
        normalized_avg_price = _normalize_positive_float(avg_price, field_name="avg_price")

        runtime = get_database_runtime()
        create_core_schema(runtime.engine)
        self._ensure_user(user_id=normalized_user_id)

        existing = self.get_by_symbol(user_id=normalized_user_id, symbol=normalized_symbol)
        if existing is None:
            holding_id = str(uuid4())
            execute_statement(
                runtime.engine,
                """
                INSERT INTO portfolio_holdings (id, user_id, symbol, qty, avg_price)
                VALUES (?, ?, ?, ?, ?)
                """,
                (holding_id, normalized_user_id, normalized_symbol, normalized_qty, normalized_avg_price),
            )
            created = self.get_by_id(user_id=normalized_user_id, holding_id=holding_id)
            if created is None:
                raise RuntimeError("portfolio holding insert succeeded but lookup failed")
            return created, True

        execute_statement(
            runtime.engine,
            f"""
            UPDATE portfolio_holdings
            SET qty = ?, avg_price = ?, updated_at_utc = ({_UTC_NOW_SQL})
            WHERE id = ? AND user_id = ?
            """,
            (normalized_qty, normalized_avg_price, existing.id, normalized_user_id),
        )
        updated = self.get_by_id(user_id=normalized_user_id, holding_id=existing.id)
        if updated is None:
            raise RuntimeError("portfolio holding update succeeded but lookup failed")
        return updated, False

    def list_holdings(self, *, user_id: str) -> list[PortfolioHoldingRecord]:
        normalized_user_id = _normalize_user_id(user_id)
        runtime = get_database_runtime()
        create_core_schema(runtime.engine)
        rows = fetch_all(
            runtime.engine,
            """
            SELECT id, user_id, symbol, qty, avg_price, created_at_utc, updated_at_utc
            FROM portfolio_holdings
            WHERE user_id = ?
            ORDER BY symbol ASC, id ASC
            """,
            (normalized_user_id,),
        )
        return [_row_to_holding(row) for row in rows]

    def delete_holding(self, *, holding_id: str, user_id: str) -> bool:
        normalized_holding_id = (holding_id or "").strip()
        if not normalized_holding_id:
            return False

        normalized_user_id = _normalize_user_id(user_id)
        runtime = get_database_runtime()
        create_core_schema(runtime.engine)
        row = fetch_all(
            runtime.engine,
            "SELECT id FROM portfolio_holdings WHERE id = ? AND user_id = ? LIMIT 1",
            (normalized_holding_id, normalized_user_id),
        )
        if not row:
            return False

        execute_statement(
            runtime.engine,
            "DELETE FROM portfolio_holdings WHERE id = ? AND user_id = ?",
            (normalized_holding_id, normalized_user_id),
        )
        return True

    def get_by_id(self, *, user_id: str, holding_id: str) -> PortfolioHoldingRecord | None:
        normalized_holding_id = (holding_id or "").strip()
        if not normalized_holding_id:
            return None

        normalized_user_id = _normalize_user_id(user_id)
        runtime = get_database_runtime()
        rows = fetch_all(
            runtime.engine,
            """
            SELECT id, user_id, symbol, qty, avg_price, created_at_utc, updated_at_utc
            FROM portfolio_holdings
            WHERE id = ? AND user_id = ?
            LIMIT 1
            """,
            (normalized_holding_id, normalized_user_id),
        )
        if not rows:
            return None
        return _row_to_holding(rows[0])

    def get_by_symbol(self, *, user_id: str, symbol: str) -> PortfolioHoldingRecord | None:
        normalized_user_id = _normalize_user_id(user_id)
        normalized_symbol = _normalize_symbol(symbol)
        runtime = get_database_runtime()
        rows = fetch_all(
            runtime.engine,
            """
            SELECT id, user_id, symbol, qty, avg_price, created_at_utc, updated_at_utc
            FROM portfolio_holdings
            WHERE user_id = ? AND symbol = ?
            LIMIT 1
            """,
            (normalized_user_id, normalized_symbol),
        )
        if not rows:
            return None
        return _row_to_holding(rows[0])

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


def _row_to_holding(row: tuple[object, ...]) -> PortfolioHoldingRecord:
    return PortfolioHoldingRecord(
        id=str(row[0]),
        user_id=str(row[1]),
        symbol=str(row[2]),
        qty=float(row[3]),
        avg_price=float(row[4]),
        created_at_utc=str(row[5]),
        updated_at_utc=str(row[6]),
    )


def _normalize_user_id(user_id: str) -> str:
    normalized = (user_id or "").strip()
    if not normalized:
        raise ValueError("user_id must not be empty")
    return normalized


def _normalize_symbol(symbol: str) -> str:
    normalized = (symbol or "").strip().upper()
    if not normalized:
        raise ValueError("symbol must not be empty")
    return normalized


def _normalize_positive_float(raw: float, *, field_name: str) -> float:
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return round(value, 8)


def _placeholder_email(user_id: str) -> str:
    safe = "".join(char if char.isalnum() else "-" for char in user_id.lower())
    return f"{safe}@local.portfolio"


portfolio_holdings_db_service = PortfolioHoldingsDbService()
