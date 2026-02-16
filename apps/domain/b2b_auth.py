from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os

from apps.domain.events import parse_utc_datetime

_DEFAULT_RATE_LIMIT_PER_MINUTE = 60
_DEFAULT_API_KEY = "b2b-demo-key"
_DEFAULT_TENANT_ID = "demo-tenant"


class MissingApiKeyError(ValueError):
    pass


class InvalidApiKeyError(ValueError):
    pass


class ExpiredApiKeyError(ValueError):
    pass


class RateLimitExceededError(RuntimeError):
    def __init__(self, *, retry_after_seconds: int) -> None:
        super().__init__("rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class B2BPrincipal:
    tenant_id: str
    key_id: str
    rate_limit_per_minute: int
    allowed_symbols: tuple[str, ...]


@dataclass(frozen=True)
class _ApiKeyRecord:
    key: str
    key_id: str
    tenant_id: str
    expires_at_utc: datetime | None
    rate_limit_per_minute: int
    allowed_symbols: tuple[str, ...]


class B2BAuthService:
    def __init__(self) -> None:
        self._tenant_buckets: dict[tuple[str, int], int] = {}

    def authenticate(self, *, api_key: str, now_utc: datetime | None = None) -> B2BPrincipal:
        normalized_key = (api_key or "").strip()
        if not normalized_key:
            raise MissingApiKeyError("x-api-key header is required")

        records = self._load_api_keys()
        record = records.get(normalized_key)
        if record is None:
            raise InvalidApiKeyError("api key is invalid")

        now = now_utc or datetime.now(timezone.utc)
        if record.expires_at_utc is not None and now >= record.expires_at_utc:
            raise ExpiredApiKeyError("api key is expired")

        return B2BPrincipal(
            tenant_id=record.tenant_id,
            key_id=record.key_id,
            rate_limit_per_minute=record.rate_limit_per_minute,
            allowed_symbols=record.allowed_symbols,
        )

    def enforce_rate_limit(self, *, principal: B2BPrincipal, now_utc: datetime | None = None) -> None:
        now = now_utc or datetime.now(timezone.utc)
        epoch_seconds = int(now.timestamp())
        bucket = epoch_seconds // 60
        key = (principal.tenant_id, bucket)
        count = self._tenant_buckets.get(key, 0)

        if count >= principal.rate_limit_per_minute:
            retry_after = max(1, 60 - (epoch_seconds % 60))
            raise RateLimitExceededError(retry_after_seconds=retry_after)

        self._tenant_buckets[key] = count + 1
        self._cleanup_old_buckets(current_bucket=bucket)

    def reset_rate_limits(self) -> None:
        self._tenant_buckets.clear()

    def _load_api_keys(self) -> dict[str, _ApiKeyRecord]:
        raw_json = os.getenv("B2B_API_KEYS_JSON", "").strip()
        default_limit = _parse_positive_int(
            os.getenv("B2B_RATE_LIMIT_PER_MINUTE"),
            fallback=_DEFAULT_RATE_LIMIT_PER_MINUTE,
        )

        if not raw_json:
            return {
                _DEFAULT_API_KEY: _ApiKeyRecord(
                    key=_DEFAULT_API_KEY,
                    key_id=_to_key_id(_DEFAULT_API_KEY),
                    tenant_id=_DEFAULT_TENANT_ID,
                    expires_at_utc=None,
                    rate_limit_per_minute=default_limit,
                    allowed_symbols=(),
                )
            }

        loaded = json.loads(raw_json)
        if not isinstance(loaded, list):
            raise ValueError("B2B_API_KEYS_JSON must be a JSON array")

        records: dict[str, _ApiKeyRecord] = {}
        for item in loaded:
            if not isinstance(item, dict):
                raise ValueError("B2B_API_KEYS_JSON entries must be objects")
            key = str(item.get("key", "")).strip()
            tenant_id = str(item.get("tenant_id", "")).strip()
            if not key or not tenant_id:
                raise ValueError("B2B API key entry requires key and tenant_id")

            expires_at_raw = item.get("expires_at_utc")
            expires_at = parse_utc_datetime(str(expires_at_raw)) if expires_at_raw else None
            limit = _parse_positive_int(item.get("rate_limit_per_minute"), fallback=default_limit)
            allowed_symbols = _normalize_allowed_symbols(item.get("allowed_symbols"))
            records[key] = _ApiKeyRecord(
                key=key,
                key_id=_to_key_id(key),
                tenant_id=tenant_id,
                expires_at_utc=expires_at,
                rate_limit_per_minute=limit,
                allowed_symbols=allowed_symbols,
            )
        return records

    def _cleanup_old_buckets(self, *, current_bucket: int) -> None:
        stale_keys = [key for key in self._tenant_buckets if key[1] < current_bucket - 1]
        for key in stale_keys:
            self._tenant_buckets.pop(key, None)


def _parse_positive_int(value: object, *, fallback: int) -> int:
    if value is None:
        return fallback
    raw = str(value).strip()
    if not raw:
        return fallback
    parsed = int(raw)
    if parsed < 1:
        raise ValueError("rate_limit_per_minute must be >= 1")
    return parsed


def _to_key_id(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _normalize_allowed_symbols(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("allowed_symbols must be a JSON array when provided")
    normalized: list[str] = []
    for item in raw:
        symbol = str(item).strip().upper()
        if not symbol:
            continue
        if symbol not in normalized:
            normalized.append(symbol)
    return tuple(normalized)


b2b_auth_service = B2BAuthService()
