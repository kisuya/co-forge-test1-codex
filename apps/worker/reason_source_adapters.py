from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from apps.domain.events import parse_utc_datetime, to_utc_iso
from apps.infra.observability import log_error


class ReasonSourceError(RuntimeError):
    def __init__(self, source: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.source = source
        self.retryable = retryable


class RetryableReasonSourceError(ReasonSourceError):
    def __init__(self, source: str, message: str) -> None:
        super().__init__(source, message, retryable=True)


class ReasonSourceAdapter(Protocol):
    source_name: str

    def fetch_by_symbol(
        self,
        *,
        symbol: str,
        time_window: tuple[datetime | str, datetime | str],
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class _AdapterError:
    source: str
    retryable: bool
    message: str

    def to_dict(self) -> dict[str, object]:
        return {"source": self.source, "retryable": self.retryable, "message": self.message}


class SecSourceAdapter:
    source_name = "sec"

    def __init__(self, records_by_symbol: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._records_by_symbol = records_by_symbol or {}

    def fetch_by_symbol(
        self,
        *,
        symbol: str,
        time_window: tuple[datetime | str, datetime | str],
    ) -> list[dict[str, Any]]:
        _normalize_time_window(time_window)
        return list(self._records_by_symbol.get(symbol.upper(), []))


class DartSourceAdapter:
    source_name = "dart"

    def __init__(self, records_by_symbol: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._records_by_symbol = records_by_symbol or {}

    def fetch_by_symbol(
        self,
        *,
        symbol: str,
        time_window: tuple[datetime | str, datetime | str],
    ) -> list[dict[str, Any]]:
        _normalize_time_window(time_window)
        return list(self._records_by_symbol.get(symbol.upper(), []))


class NewsSourceAdapter:
    source_name = "news"

    def __init__(self, records_by_symbol: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._records_by_symbol = records_by_symbol or {}

    def fetch_by_symbol(
        self,
        *,
        symbol: str,
        time_window: tuple[datetime | str, datetime | str],
    ) -> list[dict[str, Any]]:
        _normalize_time_window(time_window)
        return list(self._records_by_symbol.get(symbol.upper(), []))


def collect_reason_candidates(
    *,
    symbol: str,
    time_window: tuple[datetime | str, datetime | str],
    adapters: list[ReasonSourceAdapter],
    request_id: str | None = None,
) -> dict[str, object]:
    normalized_symbol = (symbol or "").strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol must not be empty")
    window_start, window_end = _normalize_time_window(time_window)

    candidates: list[dict[str, Any]] = []
    errors: list[_AdapterError] = []
    for adapter in adapters:
        source_name = getattr(adapter, "source_name", adapter.__class__.__name__.lower())
        try:
            source_items = adapter.fetch_by_symbol(
                symbol=normalized_symbol,
                time_window=(window_start, window_end),
            )
        except Exception as exc:  # noqa: BLE001 - adapter failures are isolated and reported per source.
            adapter_error = _normalize_adapter_error(source_name, exc)
            errors.append(adapter_error)
            log_error(
                feature="reason-002",
                event="reason_source_fetch_failed",
                request_id=request_id,
                logger_name="oh_my_stock.worker",
                source=source_name,
                retryable=adapter_error.retryable,
                error=adapter_error.message,
            )
            continue

        for item in source_items:
            if not isinstance(item, dict):
                continue
            normalized_item = dict(item)
            normalized_item.setdefault("source", source_name)
            candidates.append(normalized_item)

    return {
        "candidates": candidates,
        "errors": [error.to_dict() for error in errors],
    }


def _normalize_time_window(
    time_window: tuple[datetime | str, datetime | str],
) -> tuple[str, str]:
    start_raw, end_raw = time_window
    start_utc = parse_utc_datetime(start_raw)
    end_utc = parse_utc_datetime(end_raw)
    if start_utc > end_utc:
        raise ValueError("time_window start must be before end")
    return to_utc_iso(start_utc), to_utc_iso(end_utc)


def _normalize_adapter_error(source_name: str, exc: Exception) -> _AdapterError:
    if isinstance(exc, ReasonSourceError):
        return _AdapterError(source=source_name, retryable=exc.retryable, message=str(exc))

    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()
    is_retryable = isinstance(exc, TimeoutError) or "429" in lowered or "rate limit" in lowered
    if is_retryable:
        return _AdapterError(source=source_name, retryable=True, message=f"retryable: {message}")
    return _AdapterError(source=source_name, retryable=False, message=message)
