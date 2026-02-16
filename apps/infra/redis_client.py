from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from typing import Any, Protocol

_MIN_TTL_SECONDS = 1


class RetryableRedisError(RuntimeError):
    """Raised when a Redis operation failed due to transient connectivity issues."""


class RedisBackend(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str, *, ttl_seconds: int) -> None: ...

    def ttl(self, key: str) -> int | None: ...

    def acquire_lock(self, key: str, *, ttl_seconds: int) -> bool: ...

    def release_lock(self, key: str) -> None: ...


@dataclass(frozen=True)
class RedisConfig:
    redis_url: str
    key_prefix: str

    @classmethod
    def from_env(cls) -> "RedisConfig":
        redis_url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
        key_prefix = (os.getenv("REDIS_KEY_PREFIX") or "oh-my-stock").strip() or "oh-my-stock"
        return cls(redis_url=redis_url, key_prefix=key_prefix)


class InMemoryRedisBackend:
    def __init__(self) -> None:
        self._store: dict[str, tuple[str, datetime | None]] = {}
        self._locks: dict[str, datetime] = {}

    def get(self, key: str) -> str | None:
        record = self._store.get(key)
        if record is None:
            return None
        value, expires_at = record
        if expires_at is not None and expires_at <= _utc_now():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        expires_at = _utc_now() + timedelta(seconds=ttl_seconds)
        self._store[key] = (value, expires_at)

    def ttl(self, key: str) -> int | None:
        record = self._store.get(key)
        if record is None:
            return None
        _, expires_at = record
        if expires_at is None:
            return None
        remaining = int((expires_at - _utc_now()).total_seconds())
        if remaining < 0:
            self._store.pop(key, None)
            return None
        return remaining

    def acquire_lock(self, key: str, *, ttl_seconds: int) -> bool:
        now = _utc_now()
        expires_at = self._locks.get(key)
        if expires_at is not None and expires_at > now:
            return False
        self._locks[key] = now + timedelta(seconds=ttl_seconds)
        return True

    def release_lock(self, key: str) -> None:
        self._locks.pop(key, None)


class RedisClient:
    def __init__(self, config: RedisConfig | None = None, backend: RedisBackend | None = None) -> None:
        self.config = config or RedisConfig.from_env()
        self._backend = backend or InMemoryRedisBackend()

    def get(self, key: str) -> str | None:
        scoped_key = self._scoped_key(key)
        return self._call_with_retryable_error(lambda: self._backend.get(scoped_key))

    def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        _validate_ttl(ttl_seconds)
        scoped_key = self._scoped_key(key)
        self._call_with_retryable_error(
            lambda: self._backend.set(scoped_key, value, ttl_seconds=ttl_seconds)
        )

    def ttl(self, key: str) -> int | None:
        scoped_key = self._scoped_key(key)
        return self._call_with_retryable_error(lambda: self._backend.ttl(scoped_key))

    def lock(self, key: str, *, ttl_seconds: int = 30) -> bool:
        _validate_ttl(ttl_seconds)
        scoped_key = self._scoped_key(f"lock:{key}")
        return self._call_with_retryable_error(
            lambda: self._backend.acquire_lock(scoped_key, ttl_seconds=ttl_seconds)
        )

    def release_lock(self, key: str) -> None:
        scoped_key = self._scoped_key(f"lock:{key}")
        self._call_with_retryable_error(lambda: self._backend.release_lock(scoped_key))

    def should_debounce(
        self,
        *,
        symbol: str,
        window_seconds: int,
        direction: str,
        ttl_seconds: int,
    ) -> bool:
        _validate_ttl(ttl_seconds)
        redis_key = f"debounce:{symbol.upper()}:{window_seconds}:{direction.lower()}"
        existing = self.get(redis_key)
        if existing is not None:
            return True
        self.set(redis_key, "1", ttl_seconds=ttl_seconds)
        return False

    def in_cooldown(
        self,
        *,
        user_id: str,
        event_id: str,
        channel: str,
        ttl_seconds: int,
    ) -> bool:
        _validate_ttl(ttl_seconds)
        redis_key = f"cooldown:{user_id}:{event_id}:{channel.lower()}"
        existing = self.get(redis_key)
        if existing is not None:
            return True
        self.set(redis_key, "1", ttl_seconds=ttl_seconds)
        return False

    def _scoped_key(self, key: str) -> str:
        normalized = key.strip()
        if not normalized:
            raise ValueError("redis key must not be empty")
        return f"{self.config.key_prefix}:{normalized}"

    def _call_with_retryable_error(self, operation: Any) -> Any:
        try:
            return operation()
        except RetryableRedisError:
            raise
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise RetryableRedisError("redis backend temporarily unavailable") from exc


def _validate_ttl(ttl_seconds: int) -> None:
    if ttl_seconds < _MIN_TTL_SECONDS:
        raise ValueError("ttl_seconds must be at least 1")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
