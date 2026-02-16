from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import os
from uuid import uuid4

from apps.infra.observability import log_error, log_info
from apps.infra.redis_client import RedisClient, RetryableRedisError

_EMAIL_COOLDOWN_KEY_PREFIX = "email:cooldown"


@dataclass(frozen=True)
class EmailRetryConfig:
    max_attempts: int
    base_delay_seconds: int

    @classmethod
    def from_env(cls) -> "EmailRetryConfig":
        max_attempts = _parse_positive_int(
            os.getenv("EMAIL_RETRY_MAX_ATTEMPTS"),
            fallback=3,
            variable_name="EMAIL_RETRY_MAX_ATTEMPTS",
        )
        base_delay_seconds = _parse_positive_int(
            os.getenv("EMAIL_RETRY_BASE_DELAY_SECONDS"),
            fallback=5,
            variable_name="EMAIL_RETRY_BASE_DELAY_SECONDS",
        )
        return cls(max_attempts=max_attempts, base_delay_seconds=base_delay_seconds)


@dataclass(frozen=True)
class DeadLetterEntry:
    id: str
    user_id: str
    event_id: str
    attempts: int
    error: str
    retryable: bool
    created_at_utc: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class EmailDeliveryAdapter:
    def send(self, *, user_id: str, event_id: str, message: str) -> None:
        raise NotImplementedError


class DeadLetterQueue:
    def __init__(self) -> None:
        self._entries: list[DeadLetterEntry] = []

    def add(self, entry: DeadLetterEntry) -> DeadLetterEntry:
        self._entries.append(entry)
        return entry

    def list_entries(self) -> list[DeadLetterEntry]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries.clear()


email_dead_letter_queue = DeadLetterQueue()


def send_email_with_retry(
    *,
    user_id: str,
    event_id: str,
    message: str,
    adapter: EmailDeliveryAdapter,
    redis_client: RedisClient | None = None,
    retry_config: EmailRetryConfig | None = None,
    cooldown_ttl_seconds: int = 30 * 60,
    request_id: str | None = None,
) -> dict[str, object]:
    config = retry_config or EmailRetryConfig.from_env()
    redis = redis_client or RedisClient()
    cooldown_key = _cooldown_key(user_id=user_id, event_id=event_id)
    if _in_cooldown(redis, cooldown_key):
        return {"status": "cooldown", "attempts": 0, "attempt_states": []}

    attempt_states: list[dict[str, object]] = []
    for attempt in range(1, config.max_attempts + 1):
        try:
            adapter.send(user_id=user_id, event_id=event_id, message=message)
        except Exception as exc:  # noqa: BLE001 - adapter exceptions are classified and handled explicitly.
            retryable = _is_retryable_email_error(exc)
            if retryable and attempt < config.max_attempts:
                delay_seconds = config.base_delay_seconds * (2 ** (attempt - 1))
                attempt_states.append(
                    {
                        "attempt": attempt,
                        "status": "retrying",
                        "next_delay_seconds": delay_seconds,
                    }
                )
                log_error(
                    feature="notify-003",
                    event="email_send_retrying",
                    request_id=request_id,
                    logger_name="oh_my_stock.worker",
                    user_id=user_id,
                    event_id=event_id,
                    attempt=attempt,
                    next_delay_seconds=delay_seconds,
                    error=str(exc),
                )
                continue

            dead_letter = email_dead_letter_queue.add(
                DeadLetterEntry(
                    id=str(uuid4()),
                    user_id=user_id,
                    event_id=event_id,
                    attempts=attempt,
                    error=str(exc),
                    retryable=retryable,
                    created_at_utc=_utc_now_iso(),
                )
            )
            log_error(
                feature="notify-003",
                event="email_send_failed",
                request_id=request_id,
                logger_name="oh_my_stock.worker",
                user_id=user_id,
                event_id=event_id,
                attempt=attempt,
                error=str(exc),
            )
            return {
                "status": "failed",
                "attempts": attempt,
                "attempt_states": attempt_states,
                "dead_letter_id": dead_letter.id,
            }

        _mark_cooldown(redis, cooldown_key, cooldown_ttl_seconds=cooldown_ttl_seconds)
        log_info(
            feature="notify-003",
            event="email_send_succeeded",
            request_id=request_id,
            logger_name="oh_my_stock.worker",
            user_id=user_id,
            event_id=event_id,
            attempt=attempt,
        )
        return {"status": "sent", "attempts": attempt, "attempt_states": attempt_states}

    raise RuntimeError("email retry loop exited unexpectedly")


def _cooldown_key(*, user_id: str, event_id: str) -> str:
    return f"{_EMAIL_COOLDOWN_KEY_PREFIX}:{user_id}:{event_id}"


def _in_cooldown(redis_client: RedisClient, cooldown_key: str) -> bool:
    try:
        return redis_client.get(cooldown_key) is not None
    except RetryableRedisError:
        return False


def _mark_cooldown(redis_client: RedisClient, cooldown_key: str, *, cooldown_ttl_seconds: int) -> None:
    try:
        redis_client.set(cooldown_key, "1", ttl_seconds=cooldown_ttl_seconds)
    except RetryableRedisError:
        return


def _is_retryable_email_error(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    lowered = str(exc).lower()
    return "timeout" in lowered or "temporary" in lowered or "429" in lowered


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_positive_int(value: str | None, *, fallback: int, variable_name: str) -> int:
    if value is None or value.strip() == "":
        return fallback
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{variable_name} must be an integer") from exc
    if parsed < 1:
        raise ValueError(f"{variable_name} must be >= 1")
    return parsed
