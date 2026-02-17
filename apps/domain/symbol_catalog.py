from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from apps.domain.symbol_catalog_utils import (
    BOOTSTRAP_VERSION,
    SOURCE_EMBEDDED,
    SOURCE_REMOTE,
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    SyncValidationError,
    assert_market_coverage,
    assert_no_duplicates,
    execute_transaction,
    normalize_market,
    normalize_mode,
    normalize_symbol,
    normalize_timestamp,
    normalize_version,
    utc_now_iso,
)
from apps.infra.models import create_core_schema, fetch_all
from apps.infra.postgres import get_database_runtime

@dataclass(frozen=True)
class CatalogRecord:
    symbol: str
    name: str
    market: str
    is_active: bool = True

@dataclass(frozen=True)
class CatalogSnapshot:
    version: str
    records: list[CatalogRecord]
    mode: str = "full"
    fetched_at_utc: str | None = None
    is_partial: bool = False

@dataclass(frozen=True)
class CatalogSyncResult:
    status: str
    active_version: str | None
    active_applied_at_utc: str | None
    reason: str | None = None

class SymbolCatalogSource(Protocol):
    def fetch(self, *, since_version: str | None) -> CatalogSnapshot: ...

class SymbolCatalogService:
    def __init__(self, *, bootstrap_records: list[CatalogRecord] | None = None) -> None:
        seeds = bootstrap_records or _default_bootstrap_records()
        self._bootstrap_records = [_normalize_record(record) for record in seeds]

    def search(self, *, query: str, market: str) -> list[CatalogRecord]:
        self._ensure_bootstrap()
        active_version = self.active_version()
        if active_version is None:
            return []
        like_query = f"%{(query or '').strip().upper()}%"
        runtime = get_database_runtime()
        rows = fetch_all(
            runtime.engine,
            """
            SELECT symbol, name, market, is_active
            FROM symbol_catalog_items
            WHERE catalog_version = ? AND market = ? AND is_active = 1
              AND (symbol LIKE ? OR UPPER(name) LIKE ?)
            ORDER BY symbol ASC
            """,
            (active_version, normalize_market(market), like_query, like_query),
        )
        return [_row_to_record(row) for row in rows]

    def sync_from_source(self, *, source: SymbolCatalogSource) -> CatalogSyncResult:
        self._ensure_bootstrap()
        previous_version = self.active_version()
        try:
            snapshot = source.fetch(since_version=previous_version)
        except Exception:  # noqa: BLE001 - adapters can raise transport-specific errors.
            return self._fallback("source_unavailable")
        try:
            version = normalize_version(snapshot.version)
            mode = normalize_mode(snapshot.mode)
            fetched_at_utc = normalize_timestamp(snapshot.fetched_at_utc)
            if snapshot.is_partial:
                raise SyncValidationError("partial_failure")
            incoming_records = [_normalize_record(record) for record in snapshot.records]
            assert_no_duplicates([(record.market, record.symbol) for record in incoming_records])
            records = self._materialize_records(mode=mode, incoming_records=incoming_records, base_version=previous_version)
        except SyncValidationError as exc:
            return self._fallback(exc.reason)
        if previous_version == version:
            return CatalogSyncResult(status="noop", active_version=previous_version, active_applied_at_utc=self.active_applied_at_utc())

        self._persist_version(
            version=version,
            records=records,
            mode=mode,
            source_name=SOURCE_REMOTE,
            fetched_at_utc=fetched_at_utc or utc_now_iso(),
        )
        active_version, applied = self._active_state()
        return CatalogSyncResult(status="synced", active_version=active_version, active_applied_at_utc=applied)

    def rollback_to_version(self, *, version: str) -> bool:
        self._ensure_bootstrap()
        normalized = normalize_version(version)
        if not self._version_exists(normalized):
            return False
        runtime = get_database_runtime()
        execute_transaction(
            runtime.engine,
            [
                ("UPDATE symbol_catalog_versions SET status = ?", (STATUS_INACTIVE,)),
                (
                    "UPDATE symbol_catalog_versions SET status = ?, activated_at_utc = ? WHERE version = ?",
                    (STATUS_ACTIVE, utc_now_iso(), normalized),
                ),
            ],
        )
        return True

    def active_version(self) -> str | None:
        self._ensure_bootstrap()
        return self._active_state()[0]

    def active_applied_at_utc(self) -> str | None:
        self._ensure_bootstrap()
        return self._active_state()[1]

    def _ensure_bootstrap(self) -> None:
        runtime = get_database_runtime()
        create_core_schema(runtime.engine)
        if self._active_state()[0] is not None:
            return
        self._persist_version(
            version=BOOTSTRAP_VERSION,
            records=self._bootstrap_records,
            mode="full",
            source_name=SOURCE_EMBEDDED,
            fetched_at_utc=utc_now_iso(),
        )

    def _active_state(self) -> tuple[str | None, str | None]:
        runtime = get_database_runtime()
        rows = fetch_all(
            runtime.engine,
            """
            SELECT version, activated_at_utc
            FROM symbol_catalog_versions
            WHERE status = ?
            ORDER BY activated_at_utc DESC, version DESC
            LIMIT 1
            """,
            (STATUS_ACTIVE,),
        )
        if not rows:
            return None, None
        return str(rows[0][0]), str(rows[0][1])

    def _materialize_records(
        self,
        *,
        mode: str,
        incoming_records: list[CatalogRecord],
        base_version: str | None,
    ) -> list[CatalogRecord]:
        if mode == "full":
            assert_market_coverage({record.market for record in incoming_records})
            return sorted(incoming_records, key=lambda record: (record.market, record.symbol))
        if base_version is None:
            raise SyncValidationError("missing_base_version")
        merged: dict[tuple[str, str], CatalogRecord] = {}
        for record in self._list_records(version=base_version, include_inactive=True):
            merged[(record.market, record.symbol)] = record
        for record in incoming_records:
            merged[(record.market, record.symbol)] = record
        records = sorted(merged.values(), key=lambda record: (record.market, record.symbol))
        assert_market_coverage({record.market for record in records})
        return records

    def _list_records(self, *, version: str, include_inactive: bool) -> list[CatalogRecord]:
        runtime = get_database_runtime()
        clause = "" if include_inactive else "AND is_active = 1"
        rows = fetch_all(
            runtime.engine,
            f"""
            SELECT symbol, name, market, is_active
            FROM symbol_catalog_items
            WHERE catalog_version = ?
            {clause}
            ORDER BY market ASC, symbol ASC
            """,
            (version,),
        )
        return [_row_to_record(row) for row in rows]

    def _persist_version(
        self,
        *,
        version: str,
        records: list[CatalogRecord],
        mode: str,
        source_name: str,
        fetched_at_utc: str,
    ) -> None:
        runtime = get_database_runtime()
        create_core_schema(runtime.engine)
        activated_at_utc = utc_now_iso()
        statements: list[tuple[str, Sequence[object] | None]] = []
        if self._version_exists(version):
            statements.append(("DELETE FROM symbol_catalog_items WHERE catalog_version = ?", (version,)))
            statements.append(("DELETE FROM symbol_catalog_versions WHERE version = ?", (version,)))
        statements.append(
            (
                """
                INSERT INTO symbol_catalog_versions
                (version, source_name, sync_mode, status, item_count, fetched_at_utc, activated_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (version, source_name, mode, STATUS_INACTIVE, len(records), fetched_at_utc, activated_at_utc),
            )
        )
        for record in records:
            statements.append(
                (
                    """
                    INSERT INTO symbol_catalog_items
                    (catalog_version, market, symbol, name, is_active)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (version, record.market, record.symbol, record.name, 1 if record.is_active else 0),
                )
            )
        statements.append(("UPDATE symbol_catalog_versions SET status = ? WHERE status = ? AND version != ?", (STATUS_INACTIVE, STATUS_ACTIVE, version)))
        statements.append(("UPDATE symbol_catalog_versions SET status = ?, activated_at_utc = ? WHERE version = ?", (STATUS_ACTIVE, activated_at_utc, version)))
        execute_transaction(runtime.engine, statements)

    def _version_exists(self, version: str) -> bool:
        runtime = get_database_runtime()
        rows = fetch_all(runtime.engine, "SELECT 1 FROM symbol_catalog_versions WHERE version = ? LIMIT 1", (version,))
        return bool(rows)

    def _fallback(self, reason: str) -> CatalogSyncResult:
        active_version, applied = self._active_state()
        return CatalogSyncResult(status="fallback", active_version=active_version, active_applied_at_utc=applied, reason=reason)


def _normalize_record(record: CatalogRecord) -> CatalogRecord:
    name = (record.name or "").strip()
    if not name:
        raise SyncValidationError("invalid_name")
    return CatalogRecord(
        symbol=normalize_symbol(record.symbol),
        name=name,
        market=normalize_market(record.market),
        is_active=bool(record.is_active),
    )


def _row_to_record(row: tuple[Any, ...]) -> CatalogRecord:
    return CatalogRecord(symbol=str(row[0]), name=str(row[1]), market=str(row[2]), is_active=bool(row[3]))


def _default_bootstrap_records() -> list[CatalogRecord]:
    return [
        CatalogRecord(symbol="AAPL", name="Apple Inc.", market="US"),
        CatalogRecord(symbol="MSFT", name="Microsoft Corporation", market="US"),
        CatalogRecord(symbol="META", name="Meta Platforms", market="US"),
        CatalogRecord(symbol="NVDA", name="NVIDIA Corporation", market="US"),
        CatalogRecord(symbol="TSLA", name="Tesla Inc.", market="US"),
        CatalogRecord(symbol="005930", name="Samsung Electronics", market="KR"),
        CatalogRecord(symbol="000660", name="SK Hynix", market="KR"),
        CatalogRecord(symbol="035420", name="NAVER", market="KR"),
    ]


_symbol_catalog_service: SymbolCatalogService | None = None


def get_symbol_catalog_service() -> SymbolCatalogService:
    global _symbol_catalog_service
    if _symbol_catalog_service is None:
        _symbol_catalog_service = SymbolCatalogService()
    return _symbol_catalog_service


def set_symbol_catalog_service(service: SymbolCatalogService) -> None:
    global _symbol_catalog_service
    _symbol_catalog_service = service


def reset_symbol_catalog_service() -> None:
    global _symbol_catalog_service
    _symbol_catalog_service = None
