from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit, urlunsplit

try:
    from sqlalchemy import create_engine as sa_create_engine
    from sqlalchemy import text as sa_text
    from sqlalchemy.orm import sessionmaker as sa_sessionmaker
except ModuleNotFoundError:  # pragma: no cover - exercised in environments without SQLAlchemy.
    sa_create_engine = None
    sa_text = None
    sa_sessionmaker = None

DEFAULT_DATABASE_URL = "sqlite:///:memory:"
DEFAULT_POOL_SIZE = 5
DEFAULT_POOL_TIMEOUT_SECONDS = 30

_LOGGER = logging.getLogger("oh_my_stock.infra.postgres")

_db_runtime: "DatabaseRuntime | None" = None


class DatabaseConnectionError(RuntimeError):
    """Raised when the application cannot validate database connectivity."""


@dataclass(frozen=True)
class DatabaseSettings:
    database_url: str
    pool_size: int
    pool_timeout_seconds: int

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "DatabaseSettings":
        source = environ if environ is not None else os.environ
        database_url = source.get("DATABASE_URL", DEFAULT_DATABASE_URL).strip() or DEFAULT_DATABASE_URL
        pool_size = _parse_positive_int(
            source.get("DB_POOL_SIZE"),
            fallback=DEFAULT_POOL_SIZE,
            variable_name="DB_POOL_SIZE",
        )
        pool_timeout_seconds = _parse_positive_int(
            source.get("DB_POOL_TIMEOUT"),
            fallback=DEFAULT_POOL_TIMEOUT_SECONDS,
            variable_name="DB_POOL_TIMEOUT",
        )
        return cls(
            database_url=database_url,
            pool_size=pool_size,
            pool_timeout_seconds=pool_timeout_seconds,
        )


class _SQLiteEngine:
    def __init__(self, database_url: str, *, pool_timeout_seconds: int) -> None:
        self.database_url = database_url
        self.pool_timeout_seconds = pool_timeout_seconds
        self.database_path = _sqlite_path_from_url(database_url)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=float(self.pool_timeout_seconds))
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


class _SQLiteSession:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def execute(
        self,
        statement: str,
        parameters: tuple[Any, ...] | list[Any] | None = None,
    ) -> sqlite3.Cursor:
        if parameters is None:
            return self._connection.execute(statement)
        return self._connection.execute(statement, tuple(parameters))

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "_SQLiteSession":
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any) -> bool:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()
        return False


@dataclass(frozen=True)
class DatabaseRuntime:
    settings: DatabaseSettings
    engine: Any
    session_factory: Callable[[], Any]

    def health(self, *, request_id: str = "health-check") -> str:
        validate_database_connection(
            engine=self.engine,
            request_id=request_id,
            database_url=self.settings.database_url,
        )
        return "ok"


def initialize_database_runtime(
    *,
    request_id: str = "startup",
    environ: Mapping[str, str] | None = None,
) -> DatabaseRuntime:
    settings = DatabaseSettings.from_env(environ)
    try:
        runtime = _build_runtime(settings)
    except Exception as exc:  # noqa: BLE001 - startup must fail immediately for any DB setup error.
        _log_connection_failure(exc=exc, request_id=request_id, database_url=settings.database_url)
        if isinstance(exc, DatabaseConnectionError):
            raise
        raise DatabaseConnectionError("database runtime initialization failed") from exc
    validate_database_connection(
        engine=runtime.engine,
        request_id=request_id,
        database_url=settings.database_url,
    )

    global _db_runtime
    _db_runtime = runtime
    return runtime


def get_database_runtime() -> DatabaseRuntime:
    global _db_runtime
    if _db_runtime is None:
        _db_runtime = initialize_database_runtime(request_id="startup")
    return _db_runtime


def reset_database_runtime() -> None:
    global _db_runtime
    _db_runtime = None


def initialize_postgres_runtime(
    *,
    request_id: str = "startup",
    environ: Mapping[str, str] | None = None,
) -> DatabaseRuntime:
    return initialize_database_runtime(request_id=request_id, environ=environ)


def get_postgres_runtime() -> DatabaseRuntime:
    return get_database_runtime()


def validate_database_connection(*, engine: Any, request_id: str, database_url: str) -> None:
    try:
        scalar = _probe_scalar_one(engine)
    except Exception as exc:  # noqa: BLE001 - fail-fast behavior requires broad catch.
        _log_connection_failure(exc=exc, request_id=request_id, database_url=database_url)
        raise DatabaseConnectionError("database connection validation failed") from exc

    if scalar != 1:
        _log_connection_failure(
            exc=RuntimeError(f"unexpected probe result: {scalar!r}"),
            request_id=request_id,
            database_url=database_url,
        )
        raise DatabaseConnectionError("database connection validation failed")


def _build_runtime(settings: DatabaseSettings) -> DatabaseRuntime:
    if sa_create_engine is not None and sa_sessionmaker is not None:
        engine_kwargs: dict[str, Any] = {"future": True}
        if not settings.database_url.startswith("sqlite"):
            engine_kwargs.update(
                {
                    "pool_size": settings.pool_size,
                    "pool_timeout": settings.pool_timeout_seconds,
                }
            )
        engine = sa_create_engine(settings.database_url, **engine_kwargs)
        session_factory = sa_sessionmaker(
            bind=engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
        return DatabaseRuntime(settings=settings, engine=engine, session_factory=session_factory)

    engine = _SQLiteEngine(
        settings.database_url,
        pool_timeout_seconds=settings.pool_timeout_seconds,
    )

    def sqlite_session_factory() -> _SQLiteSession:
        return _SQLiteSession(engine.connect())

    return DatabaseRuntime(settings=settings, engine=engine, session_factory=sqlite_session_factory)


def _probe_scalar_one(engine: Any) -> Any:
    if sa_text is not None and hasattr(engine, "dialect"):
        with engine.connect() as connection:
            result = connection.execute(sa_text("SELECT 1"))
            if hasattr(result, "scalar_one"):
                return result.scalar_one()
            return result.scalar()

    connection = engine.connect()
    try:
        cursor = connection.execute("SELECT 1")
        row = cursor.fetchone()
        if row is None:
            return None
        return row[0]
    finally:
        connection.close()


def _parse_positive_int(value: str | None, *, fallback: int, variable_name: str) -> int:
    if value is None or value.strip() == "":
        return fallback
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{variable_name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{variable_name} must be a positive integer")
    return parsed


def _sqlite_path_from_url(database_url: str) -> str:
    if not database_url.startswith("sqlite:///"):
        raise DatabaseConnectionError(
            "SQLAlchemy is not installed. Provide sqlite:/// URL or install SQLAlchemy for PostgreSQL."
        )
    return database_url.replace("sqlite:///", "", 1)


def _log_connection_failure(*, exc: Exception, request_id: str, database_url: str) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "level": "error",
        "feature": "infra-002",
        "event": "database_connection_failed",
        "request_id": request_id,
        "database_url": _redact_database_url(database_url),
        "error": str(exc),
    }
    _LOGGER.error(json.dumps(payload, sort_keys=True))


def _redact_database_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    if "@" not in parsed.netloc:
        return database_url

    user_info, host_info = parsed.netloc.rsplit("@", 1)
    username = user_info.split(":", 1)[0]
    masked_user = f"{username}:***" if username else "***"
    return urlunsplit((parsed.scheme, f"{masked_user}@{host_info}", parsed.path, parsed.query, parsed.fragment))
