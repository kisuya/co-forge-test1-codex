from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from apps.domain.watchlists import VALID_MARKETS

BOOTSTRAP_VERSION = "bootstrap-v1"
SYNC_MODES = {"full", "incremental"}
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
SOURCE_EMBEDDED = "embedded"
SOURCE_REMOTE = "authoritative"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SyncValidationError(ValueError):
    reason: str

    def __post_init__(self) -> None:
        super().__init__(self.reason)


def normalize_version(version: str | None) -> str:
    normalized = (version or "").strip()
    if not normalized:
        raise SyncValidationError("invalid_version")
    return normalized


def normalize_mode(mode: str | None) -> str:
    normalized = (mode or "").strip().lower()
    if normalized not in SYNC_MODES:
        raise SyncValidationError("invalid_sync_mode")
    return normalized


def normalize_market(market: str) -> str:
    normalized = (market or "").strip().upper()
    if normalized not in VALID_MARKETS:
        raise SyncValidationError("invalid_market")
    return normalized


def normalize_symbol(symbol: str) -> str:
    normalized = (symbol or "").strip().upper()
    if not normalized:
        raise SyncValidationError("invalid_symbol")
    return normalized


def normalize_timestamp(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip()
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SyncValidationError("invalid_fetched_at") from exc
    return normalized


def assert_no_duplicates(keys: list[tuple[str, str]]) -> None:
    seen: set[tuple[str, str]] = set()
    for key in keys:
        if key in seen:
            raise SyncValidationError("duplicate_symbol")
        seen.add(key)


def assert_market_coverage(markets: set[str]) -> None:
    if not VALID_MARKETS.issubset(markets):
        raise SyncValidationError("partial_failure")


def execute_transaction(engine: Any, statements: list[tuple[str, Sequence[object] | None]]) -> None:
    if hasattr(engine, "dialect"):
        with engine.begin() as connection:
            for statement, parameters in statements:
                connection.exec_driver_sql(statement, parameters or ())
        return

    connection = engine.connect()
    try:
        connection.execute("BEGIN")
        for statement, parameters in statements:
            if parameters is None:
                connection.execute(statement)
            else:
                connection.execute(statement, tuple(parameters))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
