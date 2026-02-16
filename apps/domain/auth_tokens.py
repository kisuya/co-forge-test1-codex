from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any

_DEFAULT_TOKEN_TTL_SECONDS = 3600


class InvalidTokenError(ValueError):
    """Raised when token signature or claims are invalid."""


def issue_access_token(
    *,
    user_id: str,
    email: str,
    ttl_seconds: int = _DEFAULT_TOKEN_TTL_SECONDS,
    now_utc: datetime | None = None,
) -> str:
    issued_at = int((now_utc or datetime.now(timezone.utc)).timestamp())
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "iat": issued_at,
        "exp": issued_at + max(ttl_seconds, 1),
    }
    return _encode_jwt(payload, secret=_jwt_secret())


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        header_part, payload_part, signature_part = token.split(".")
    except ValueError as exc:
        raise InvalidTokenError("invalid token format") from exc

    signing_input = f"{header_part}.{payload_part}".encode("utf-8")
    expected_signature = _sign_hs256(signing_input, secret=_jwt_secret())
    if not hmac.compare_digest(signature_part, expected_signature):
        raise InvalidTokenError("invalid token signature")

    payload = _json_loads(payload_part)
    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise InvalidTokenError("invalid token payload")

    iat = payload.get("iat")
    if not isinstance(iat, int):
        raise InvalidTokenError("invalid token payload")

    now_epoch = int(datetime.now(timezone.utc).timestamp())
    clock_skew_seconds = 30
    if exp + clock_skew_seconds < now_epoch:
        raise InvalidTokenError("token expired")
    if iat > now_epoch + clock_skew_seconds:
        raise InvalidTokenError("token issued in the future")
    return payload


def _encode_jwt(payload: dict[str, Any], *, secret: str) -> str:
    header_part = _json_dumps({"alg": "HS256", "typ": "JWT"})
    payload_part = _json_dumps(payload)
    signing_input = f"{header_part}.{payload_part}".encode("utf-8")
    signature = _sign_hs256(signing_input, secret=secret)
    return f"{header_part}.{payload_part}.{signature}"


def _sign_hs256(value: bytes, *, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), value, hashlib.sha256).digest()
    return _urlsafe_b64encode(digest)


def _json_dumps(value: Any) -> str:
    serialized = json.dumps(value, separators=(",", ":"), sort_keys=True)
    return _urlsafe_b64encode(serialized.encode("utf-8"))


def _json_loads(encoded: str) -> dict[str, Any]:
    decoded = _urlsafe_b64decode(encoded)
    loaded = json.loads(decoded.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise InvalidTokenError("invalid token payload")
    return loaded


def _urlsafe_b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _jwt_secret() -> str:
    configured = os.environ.get("JWT_SECRET", "").strip()
    return configured or "oh-my-stock-dev-secret"
