from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request

from apps.domain.b2b_auth import (
    ExpiredApiKeyError,
    InvalidApiKeyError,
    MissingApiKeyError,
    RateLimitExceededError,
    b2b_auth_service,
)
from apps.infra.observability import log_error, log_info


@dataclass(frozen=True)
class B2BRequestContext:
    tenant_id: str
    key_id: str
    allowed_symbols: tuple[str, ...]


class B2BRateLimitException(RuntimeError):
    def __init__(self, *, retry_after_seconds: int) -> None:
        super().__init__("b2b rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


def require_b2b_context(request: Request) -> B2BRequestContext:
    raw_api_key = request.headers.get("x-api-key", "").strip()
    try:
        principal = b2b_auth_service.authenticate(api_key=raw_api_key)
    except MissingApiKeyError as exc:
        _log_b2b_auth_failure(request=request, reason="missing_key", key_id="missing")
        raise HTTPException(
            status_code=401,
            code="invalid_api_key",
            message="Missing or invalid API key",
            details={"error": str(exc)},
        ) from exc
    except (InvalidApiKeyError, ExpiredApiKeyError) as exc:
        _log_b2b_auth_failure(request=request, reason="invalid_or_expired", key_id="unknown")
        raise HTTPException(
            status_code=401,
            code="invalid_api_key",
            message="Missing or invalid API key",
            details={"error": str(exc)},
        ) from exc

    try:
        b2b_auth_service.enforce_rate_limit(principal=principal)
    except RateLimitExceededError as exc:
        log_error(
            feature="b2b-001",
            event="b2b_rate_limited",
            request_id=request.request_id,
            logger_name="oh_my_stock.api",
            tenant_id=principal.tenant_id,
            key_id=principal.key_id,
            retry_after_seconds=exc.retry_after_seconds,
        )
        raise B2BRateLimitException(retry_after_seconds=exc.retry_after_seconds) from exc

    log_info(
        feature="b2b-001",
        event="b2b_authenticated",
        request_id=request.request_id,
        logger_name="oh_my_stock.api",
        tenant_id=principal.tenant_id,
        key_id=principal.key_id,
    )
    return B2BRequestContext(
        tenant_id=principal.tenant_id,
        key_id=principal.key_id,
        allowed_symbols=principal.allowed_symbols,
    )


def _log_b2b_auth_failure(*, request: Request, reason: str, key_id: str) -> None:
    log_error(
        feature="b2b-001",
        event="b2b_auth_failed",
        request_id=request.request_id,
        logger_name="oh_my_stock.api",
        reason=reason,
        key_id=key_id,
    )
