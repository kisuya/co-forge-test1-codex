from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import datetime, timezone
import json
import logging
from typing import Any, Iterator

_REQUEST_ID: ContextVar[str] = ContextVar("request_id", default="")
_SENSITIVE_KEYWORDS = ("email", "password", "token", "secret", "authorization", "api_key")


@contextmanager
def request_context(request_id: str) -> Iterator[None]:
    token: Token[str] = _REQUEST_ID.set(request_id)
    try:
        yield
    finally:
        _REQUEST_ID.reset(token)


def log_info(*, feature: str, event: str, request_id: str | None = None, logger_name: str, **fields: Any) -> None:
    _log("info", feature=feature, event=event, request_id=request_id, logger_name=logger_name, fields=fields)


def log_error(*, feature: str, event: str, request_id: str | None = None, logger_name: str, **fields: Any) -> None:
    _log("error", feature=feature, event=event, request_id=request_id, logger_name=logger_name, fields=fields)


def _log(
    level: str,
    *,
    feature: str,
    event: str,
    request_id: str | None,
    logger_name: str,
    fields: dict[str, Any],
) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "level": level,
        "request_id": request_id or _REQUEST_ID.get() or "unknown",
        "feature": feature,
        "event": event,
    }
    payload.update(_sanitize(fields))
    logger = logging.getLogger(logger_name)
    _configure_logger(logger)
    log_method = logger.info if level == "info" else logger.error
    log_method(json.dumps(payload, sort_keys=True))


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if any(keyword in lowered for keyword in _SENSITIVE_KEYWORDS):
                sanitized[key] = _mask(item)
            else:
                sanitized[key] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize(item) for item in value)
    return value


def _mask(value: Any) -> str:
    text = str(value)
    if "@" in text:
        local, _, domain = text.partition("@")
        if not local:
            return f"***@{domain}"
        return f"{local[0]}***@{domain}"
    return "***"


def _configure_logger(logger: logging.Logger) -> None:
    if logger.handlers:
        return
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
