from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request

from apps.domain.auth_tokens import InvalidTokenError
from apps.domain.auth import decode_access_token


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    email: str | None


def require_authenticated_user(request: Request) -> AuthenticatedUser:
    token = _extract_bearer_token(request)
    try:
        claims = decode_access_token(token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=401,
            code="invalid_token",
            message="Invalid or expired access token",
            details={"error": str(exc)},
        ) from exc

    user_id = claims.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(
            status_code=401,
            code="invalid_token",
            message="Invalid or expired access token",
            details={"error": "token missing subject"},
        )

    email = claims.get("email")
    normalized_email = email if isinstance(email, str) else None
    return AuthenticatedUser(user_id=user_id, email=normalized_email)


def enforce_user_scope(user: AuthenticatedUser, *, requested_user_id: str) -> None:
    if user.user_id != requested_user_id:
        raise HTTPException(
            status_code=403,
            code="forbidden",
            message="Forbidden resource access",
            details={"requested_user_id": requested_user_id},
        )


def _extract_bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "").strip()
    if not authorization:
        raise HTTPException(
            status_code=401,
            code="invalid_token",
            message="Missing bearer token",
            details={"error": "authorization header is required"},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            code="invalid_token",
            message="Missing bearer token",
            details={"error": "authorization header must use bearer token"},
        )
    return token.strip()
