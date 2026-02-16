from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from uuid import uuid4

from apps.domain.events import parse_utc_datetime, to_utc_iso
from apps.domain.session_labeling import classify_market_session, normalize_session_label
from apps.domain.user_thresholds import user_threshold_store
from apps.infra.models import create_core_schema
from apps.infra.observability import log_error, log_info
from apps.infra.postgres import get_database_runtime
from apps.infra.redis_client import RedisClient, RetryableRedisError
from apps.infra.unit_of_work import UnitOfWork
from apps.worker.detection import MARKET_TIMEZONES, WINDOW_THRESHOLDS
try:  # pragma: no cover - fallback path is covered when SQLAlchemy is unavailable.
    from sqlalchemy import text as sa_text
except ModuleNotFoundError:  # pragma: no cover - default in local test runtime.
    sa_text = None

_SQLITE_INSERT = """
INSERT INTO price_events (
  id, user_id, symbol, market, change_pct, window_minutes, detected_at_utc, session_label
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""
_SQLALCHEMY_INSERT = """
INSERT INTO price_events (
  id, user_id, symbol, market, change_pct, window_minutes, detected_at_utc, session_label
) VALUES (:id, :user_id, :symbol, :market, :change_pct, :window_minutes, :detected_at_utc, :session_label)
"""
_WINDOW_DEBOUNCE_SECONDS = {
    5: 5 * 60,
    1440: 1440 * 60,
}
@dataclass(frozen=True)
class PersistedPriceEvent:
    id: str
    user_id: str
    symbol: str
    market: str
    change_pct: float
    window_minutes: int
    detected_at_utc: str
    session_label: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
@dataclass(frozen=True)
class DetectionRetryTask:
    event_id: str
    user_id: str
    symbol: str
    market: str
    window_minutes: int
    error: str

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


class DetectionRetryQueue:
    def __init__(self) -> None:
        self._tasks: list[DetectionRetryTask] = []

    def enqueue(self, *, event: PersistedPriceEvent, error: str) -> DetectionRetryTask:
        task = DetectionRetryTask(
            event_id=event.id,
            user_id=event.user_id,
            symbol=event.symbol,
            market=event.market,
            window_minutes=event.window_minutes,
            error=error,
        )
        self._tasks.append(task)
        return task

    def list_tasks(self) -> list[DetectionRetryTask]:
        return list(self._tasks)

    def clear(self) -> None:
        self._tasks.clear()


detection_retry_queue = DetectionRetryQueue()
_detection_redis_client: RedisClient | None = None
def detect_price_event_to_db(
    *,
    user_id: str,
    symbol: str,
    market: str,
    baseline_price: float,
    current_price: float,
    window_minutes: int,
    detected_at_utc: datetime | str,
    session_label: str | None = None,
    request_id: str | None = None,
) -> dict[str, object] | None:
    normalized_user_id = _normalize_user_id(user_id)
    normalized_symbol = _normalize_symbol(symbol)
    normalized_market = _normalize_market(market)
    _validate_window_minutes(window_minutes)
    _validate_baseline_price(baseline_price)

    change_pct = ((current_price - baseline_price) / baseline_price) * 100
    threshold = user_threshold_store.get_threshold(
        user_id=normalized_user_id,
        window_minutes=window_minutes,
    ) or WINDOW_THRESHOLDS[window_minutes]
    if abs(change_pct) < threshold:
        log_info(
            feature="detect-002",
            event="worker_detection_skipped",
            request_id=request_id,
            logger_name="oh_my_stock.worker",
            user_id=normalized_user_id,
            symbol=normalized_symbol,
            market=normalized_market,
            change_pct=round(change_pct, 4),
            threshold=threshold,
        )
        return None

    direction = "up" if change_pct >= 0 else "down"
    if _should_suppress_with_redis(
        symbol=normalized_symbol,
        window_minutes=window_minutes,
        direction=direction,
        request_id=request_id,
    ):
        log_info(
            feature="detect-003",
            event="worker_detection_suppressed",
            request_id=request_id,
            logger_name="oh_my_stock.worker",
            user_id=normalized_user_id,
            symbol=normalized_symbol,
            market=normalized_market,
            window_minutes=window_minutes,
            direction=direction,
        )
        return None

    detected_at = parse_utc_datetime(detected_at_utc)
    resolved_session_label = normalize_session_label(session_label)
    if resolved_session_label is None:
        resolved_session_label = classify_market_session(market=normalized_market, detected_at_utc=detected_at)
    event = PersistedPriceEvent(
        id=str(uuid4()),
        user_id=normalized_user_id,
        symbol=normalized_symbol,
        market=normalized_market,
        change_pct=round(change_pct, 4),
        window_minutes=window_minutes,
        detected_at_utc=to_utc_iso(detected_at),
        session_label=resolved_session_label,
    )

    try:
        _persist_event(event)
    except Exception as exc:  # noqa: BLE001 - enqueue retry for any persistence failure.
        retry_task = detection_retry_queue.enqueue(event=event, error=str(exc))
        log_error(
            feature="detect-002",
            event="worker_detection_persist_failed",
            request_id=request_id,
            logger_name="oh_my_stock.worker",
            event_id=event.id,
            user_id=event.user_id,
            symbol=event.symbol,
            market=event.market,
            window_minutes=event.window_minutes,
            error=str(exc),
        )
        return {
            "saved": False,
            "queued_for_retry": True,
            "event_id": event.id,
            "retry_task": retry_task.to_dict(),
        }

    log_info(
        feature="detect-002",
        event="worker_detection_persisted",
        request_id=request_id,
        logger_name="oh_my_stock.worker",
        event_id=event.id,
        user_id=event.user_id,
        symbol=event.symbol,
        market=event.market,
        change_pct=event.change_pct,
    )
    return {"saved": True, "queued_for_retry": False, "event_id": event.id}


def get_detection_redis_client() -> RedisClient:
    global _detection_redis_client
    if _detection_redis_client is None:
        _detection_redis_client = RedisClient()
    return _detection_redis_client


def set_detection_redis_client(client: RedisClient) -> None:
    global _detection_redis_client
    _detection_redis_client = client


def reset_detection_redis_client() -> None:
    global _detection_redis_client
    _detection_redis_client = None


def _persist_event(event: PersistedPriceEvent) -> None:
    runtime = get_database_runtime()
    create_core_schema(runtime.engine)
    with UnitOfWork(runtime.session_factory) as uow:
        _insert_price_event(uow.session, event)


def _insert_price_event(session: object, event: PersistedPriceEvent) -> None:
    params = event.to_dict()
    if sa_text is not None and hasattr(session, "bind"):
        session.execute(sa_text(_SQLALCHEMY_INSERT), params)
        return

    execute = getattr(session, "execute", None)
    if execute is None:
        raise RuntimeError("session does not support execute")
    execute(
        _SQLITE_INSERT,
        (
            event.id,
            event.user_id,
            event.symbol,
            event.market,
            event.change_pct,
            event.window_minutes,
            event.detected_at_utc,
            event.session_label,
        ),
    )


def _should_suppress_with_redis(
    *,
    symbol: str,
    window_minutes: int,
    direction: str,
    request_id: str | None,
) -> bool:
    try:
        return get_detection_redis_client().should_debounce(
            symbol=symbol,
            window_seconds=window_minutes * 60,
            direction=direction,
            ttl_seconds=_WINDOW_DEBOUNCE_SECONDS[window_minutes],
        )
    except RetryableRedisError as exc:
        log_error(
            feature="detect-003",
            event="worker_detection_debounce_unavailable",
            request_id=request_id,
            logger_name="oh_my_stock.worker",
            symbol=symbol,
            window_minutes=window_minutes,
            direction=direction,
            error=str(exc),
        )
        return False


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


def _normalize_market(market: str) -> str:
    normalized = (market or "").strip().upper()
    if normalized not in MARKET_TIMEZONES:
        raise ValueError("market must be KR or US")
    return normalized


def _validate_window_minutes(window_minutes: int) -> None:
    if window_minutes not in WINDOW_THRESHOLDS:
        raise ValueError("window_minutes must be one of 5 or 1440")


def _validate_baseline_price(baseline_price: float) -> None:
    if baseline_price <= 0:
        raise ValueError("baseline_price must be greater than 0")
