from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4


def parse_utc_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class PriceEvent:
    id: str
    symbol: str
    market: str
    change_pct: float
    window_minutes: int
    detected_at_utc: str
    exchange_timezone: str
    session_label: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class TransientStoreError(RuntimeError):
    """Raised when the event store is temporarily unavailable."""


class PriceEventStore:
    def __init__(self) -> None:
        self._events_by_id: dict[str, PriceEvent] = {}
        self._event_order: list[str] = []
        self._last_triggered_at: dict[tuple[str, str, int, str], datetime] = {}
        self._failure_mode: str | None = None

    def clear(self) -> None:
        self._events_by_id.clear()
        self._event_order.clear()
        self._last_triggered_at.clear()
        self._failure_mode = None

    def set_failure_mode(self, mode: str | None) -> None:
        self._failure_mode = mode

    def should_debounce(
        self,
        *,
        symbol: str,
        market: str,
        window_minutes: int,
        direction: str,
        detected_at: datetime,
        debounce_minutes: int,
    ) -> bool:
        key = (symbol, market, window_minutes, direction)
        last_detected_at = self._last_triggered_at.get(key)
        if last_detected_at is None:
            return False
        return detected_at - last_detected_at < timedelta(minutes=debounce_minutes)

    def save(self, event: PriceEvent, *, direction: str) -> PriceEvent:
        self._events_by_id[event.id] = event
        self._event_order.append(event.id)
        self._last_triggered_at[(event.symbol, event.market, event.window_minutes, direction)] = (
            parse_utc_datetime(event.detected_at_utc)
        )
        return event

    def new_event(
        self,
        *,
        symbol: str,
        market: str,
        change_pct: float,
        window_minutes: int,
        detected_at: datetime,
        exchange_timezone: str,
        session_label: str,
    ) -> PriceEvent:
        return PriceEvent(
            id=str(uuid4()),
            symbol=symbol,
            market=market,
            change_pct=change_pct,
            window_minutes=window_minutes,
            detected_at_utc=to_utc_iso(detected_at),
            exchange_timezone=exchange_timezone,
            session_label=session_label,
        )

    def list_events(self) -> list[PriceEvent]:
        return [self._events_by_id[event_id] for event_id in self._event_order]

    def query_events(
        self,
        *,
        symbol: str | None = None,
        market: str | None = None,
        session_label: str | None = None,
        from_utc: datetime | None = None,
        to_utc: datetime | None = None,
        now_utc: datetime | None = None,
        max_age_days: int = 30,
        sort_desc: bool = True,
    ) -> list[PriceEvent]:
        self._raise_if_transient_failure()
        effective_now = now_utc or datetime.now(timezone.utc)
        cutoff = effective_now - timedelta(days=max_age_days)

        results: list[PriceEvent] = []
        for event in self.list_events():
            detected_at = parse_utc_datetime(event.detected_at_utc)
            if detected_at < cutoff:
                continue
            if symbol and event.symbol != symbol:
                continue
            if market and event.market != market:
                continue
            if session_label and event.session_label != session_label:
                continue
            if from_utc and detected_at < from_utc:
                continue
            if to_utc and detected_at > to_utc:
                continue
            results.append(event)

        results.sort(
            key=lambda item: (parse_utc_datetime(item.detected_at_utc), item.id),
            reverse=sort_desc,
        )
        return results

    def get_event(self, event_id: str) -> PriceEvent | None:
        self._raise_if_transient_failure()
        return self._events_by_id.get(event_id)

    def _raise_if_transient_failure(self) -> None:
        if self._failure_mode == "transient":
            raise TransientStoreError("event store temporarily unavailable")


price_event_store = PriceEventStore()
