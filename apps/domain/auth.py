from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from apps.domain.auth_tokens import decode_access_token, issue_access_token
from apps.domain.passwords import PasswordInputError, hash_password, normalize_password, verify_password
from apps.infra.models import create_core_schema, execute_statement, fetch_all
from apps.infra.postgres import get_database_runtime


class AuthInputError(ValueError):
    """Raised when signup/login payload fields are invalid."""


class DuplicateEmailError(RuntimeError):
    """Raised when attempting to create a user with an existing email."""


class InvalidCredentialsError(RuntimeError):
    """Raised when user credentials are invalid."""


@dataclass(frozen=True)
class AuthResult:
    user_id: str
    access_token: str


class AuthService:
    def signup(self, *, email: str, password: str) -> AuthResult:
        normalized_email = _normalize_email(email)
        runtime = get_database_runtime()
        create_core_schema(runtime.engine)

        try:
            password_hash = hash_password(password)
        except PasswordInputError as exc:
            raise AuthInputError(str(exc)) from exc

        user_id = str(uuid4())
        try:
            execute_statement(
                runtime.engine,
                "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
                (user_id, normalized_email, password_hash),
            )
        except Exception as exc:  # noqa: BLE001 - DB implementation varies across runtimes.
            if _is_duplicate_email_error(exc):
                raise DuplicateEmailError("email already exists") from exc
            raise

        return AuthResult(
            user_id=user_id,
            access_token=issue_access_token(user_id=user_id, email=normalized_email),
        )

    def login(self, *, email: str, password: str) -> AuthResult:
        normalized_email = _normalize_email(email)

        try:
            normalize_password(password)
        except PasswordInputError as exc:
            raise AuthInputError(str(exc)) from exc

        runtime = get_database_runtime()
        create_core_schema(runtime.engine)
        rows = fetch_all(
            runtime.engine,
            "SELECT id, email, password_hash FROM users WHERE email = ?",
            (normalized_email,),
        )
        if not rows:
            raise InvalidCredentialsError("invalid credentials")

        user_id, persisted_email, password_hash = rows[0]
        try:
            is_valid = verify_password(password, str(password_hash))
        except PasswordInputError as exc:
            raise AuthInputError(str(exc)) from exc

        if not is_valid:
            raise InvalidCredentialsError("invalid credentials")

        return AuthResult(
            user_id=str(user_id),
            access_token=issue_access_token(user_id=str(user_id), email=str(persisted_email)),
        )


def _normalize_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if not normalized or "@" not in normalized:
        raise AuthInputError("email must be a valid address")

    local_part, _, domain_part = normalized.partition("@")
    if not local_part or "." not in domain_part:
        raise AuthInputError("email must be a valid address")
    return normalized


def _is_duplicate_email_error(exc: Exception) -> bool:
    message = str(exc).upper()
    return "UNIQUE" in message and "USERS.EMAIL" in message


auth_service = AuthService()

__all__ = [
    "AuthInputError",
    "AuthResult",
    "AuthService",
    "DuplicateEmailError",
    "InvalidCredentialsError",
    "auth_service",
    "decode_access_token",
]
