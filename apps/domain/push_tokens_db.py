from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from apps.infra.models import create_core_schema, execute_statement, fetch_all
from apps.infra.postgres import get_database_runtime

_PLACEHOLDER_HASH = "system-generated-password-hash"
_UTC_NOW_SQL = "STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now')"
_VALID_PLATFORMS = {"ios", "android"}


@dataclass(frozen=True)
class PushTokenRecord:
    id: str
    user_id: str
    token: str
    platform: str
    created_at_utc: str
    updated_at_utc: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "token": self.token,
            "platform": self.platform,
            "created_at_utc": self.created_at_utc,
            "updated_at_utc": self.updated_at_utc,
        }


class PushTokensDbService:
    def upsert_token(self, *, user_id: str, token: str, platform: str) -> tuple[PushTokenRecord, bool]:
        normalized_user_id = _normalize_user_id(user_id)
        normalized_token = _normalize_token(token)
        normalized_platform = _normalize_platform(platform)

        runtime = get_database_runtime()
        create_core_schema(runtime.engine)
        self._ensure_user(user_id=normalized_user_id)

        existing = self.get_token(user_id=normalized_user_id, token=normalized_token)
        if existing is None:
            record_id = str(uuid4())
            execute_statement(
                runtime.engine,
                """
                INSERT INTO push_tokens (id, user_id, token, platform)
                VALUES (?, ?, ?, ?)
                """,
                (record_id, normalized_user_id, normalized_token, normalized_platform),
            )
            created = self.get_token_by_id(user_id=normalized_user_id, record_id=record_id)
            if created is None:
                raise RuntimeError("push token insert succeeded but lookup failed")
            return created, True

        if existing.platform != normalized_platform:
            execute_statement(
                runtime.engine,
                f"""
                UPDATE push_tokens
                SET platform = ?, updated_at_utc = ({_UTC_NOW_SQL})
                WHERE id = ? AND user_id = ?
                """,
                (normalized_platform, existing.id, normalized_user_id),
            )
            updated = self.get_token_by_id(user_id=normalized_user_id, record_id=existing.id)
            if updated is None:
                raise RuntimeError("push token update succeeded but lookup failed")
            return updated, False

        return existing, False

    def delete_token(self, *, user_id: str, token: str) -> bool:
        normalized_user_id = _normalize_user_id(user_id)
        normalized_token = _normalize_token(token)

        runtime = get_database_runtime()
        create_core_schema(runtime.engine)
        row = fetch_all(
            runtime.engine,
            "SELECT id FROM push_tokens WHERE user_id = ? AND token = ? LIMIT 1",
            (normalized_user_id, normalized_token),
        )
        if not row:
            return False

        execute_statement(
            runtime.engine,
            "DELETE FROM push_tokens WHERE user_id = ? AND token = ?",
            (normalized_user_id, normalized_token),
        )
        return True

    def list_tokens(self, *, user_id: str) -> list[PushTokenRecord]:
        normalized_user_id = _normalize_user_id(user_id)
        runtime = get_database_runtime()
        create_core_schema(runtime.engine)
        rows = fetch_all(
            runtime.engine,
            """
            SELECT id, user_id, token, platform, created_at_utc, updated_at_utc
            FROM push_tokens
            WHERE user_id = ?
            ORDER BY created_at_utc DESC, id DESC
            """,
            (normalized_user_id,),
        )
        return [_row_to_record(row) for row in rows]

    def get_token(self, *, user_id: str, token: str) -> PushTokenRecord | None:
        normalized_user_id = _normalize_user_id(user_id)
        normalized_token = _normalize_token(token)

        runtime = get_database_runtime()
        rows = fetch_all(
            runtime.engine,
            """
            SELECT id, user_id, token, platform, created_at_utc, updated_at_utc
            FROM push_tokens
            WHERE user_id = ? AND token = ?
            LIMIT 1
            """,
            (normalized_user_id, normalized_token),
        )
        if not rows:
            return None
        return _row_to_record(rows[0])

    def get_token_by_id(self, *, user_id: str, record_id: str) -> PushTokenRecord | None:
        normalized_user_id = _normalize_user_id(user_id)
        normalized_id = (record_id or "").strip()
        if not normalized_id:
            return None

        runtime = get_database_runtime()
        rows = fetch_all(
            runtime.engine,
            """
            SELECT id, user_id, token, platform, created_at_utc, updated_at_utc
            FROM push_tokens
            WHERE user_id = ? AND id = ?
            LIMIT 1
            """,
            (normalized_user_id, normalized_id),
        )
        if not rows:
            return None
        return _row_to_record(rows[0])

    def _ensure_user(self, *, user_id: str) -> None:
        runtime = get_database_runtime()
        row = fetch_all(runtime.engine, "SELECT id FROM users WHERE id = ? LIMIT 1", (user_id,))
        if row:
            return
        execute_statement(
            runtime.engine,
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            (user_id, _placeholder_email(user_id), _PLACEHOLDER_HASH),
        )


def _row_to_record(row: tuple[object, ...]) -> PushTokenRecord:
    return PushTokenRecord(
        id=str(row[0]),
        user_id=str(row[1]),
        token=str(row[2]),
        platform=str(row[3]),
        created_at_utc=str(row[4]),
        updated_at_utc=str(row[5]),
    )


def _normalize_user_id(user_id: str) -> str:
    normalized = (user_id or "").strip()
    if not normalized:
        raise ValueError("user_id must not be empty")
    return normalized


def _normalize_token(token: str) -> str:
    normalized = (token or "").strip()
    if not normalized:
        raise ValueError("token must not be empty")
    return normalized


def _normalize_platform(platform: str) -> str:
    normalized = (platform or "").strip().lower()
    if normalized not in _VALID_PLATFORMS:
        raise ValueError("platform must be ios or android")
    return normalized


def _placeholder_email(user_id: str) -> str:
    safe = "".join(char if char.isalnum() else "-" for char in user_id.lower())
    return f"{safe}@local.push"


push_tokens_db_service = PushTokensDbService()
