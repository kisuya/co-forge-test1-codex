from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

CORE_TABLES = (
    "users",
    "watchlists",
    "watchlist_items",
    "price_events",
    "event_reasons",
    "notifications",
    "portfolio_holdings",
    "push_tokens",
)

_UTC_DEFAULT = "STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now')"

_CREATE_STATEMENTS = (
    f"""
    CREATE TABLE IF NOT EXISTS users (
      id TEXT PRIMARY KEY,
      email TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      created_at_utc TEXT NOT NULL DEFAULT ({_UTC_DEFAULT})
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS watchlists (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      name TEXT NOT NULL DEFAULT 'default',
      created_at_utc TEXT NOT NULL DEFAULT ({_UTC_DEFAULT}),
      UNIQUE (user_id, name),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS watchlist_items (
      id TEXT PRIMARY KEY,
      watchlist_id TEXT NOT NULL,
      user_id TEXT NOT NULL,
      market TEXT NOT NULL CHECK (market IN ('KR', 'US')),
      symbol TEXT NOT NULL,
      created_at_utc TEXT NOT NULL DEFAULT ({_UTC_DEFAULT}),
      UNIQUE (user_id, market, symbol),
      FOREIGN KEY (watchlist_id) REFERENCES watchlists(id) ON DELETE CASCADE,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_watchlist_items_user_id ON watchlist_items(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_watchlist_items_market_symbol ON watchlist_items(market, symbol)",
    f"""
    CREATE TABLE IF NOT EXISTS price_events (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      symbol TEXT NOT NULL,
      market TEXT NOT NULL CHECK (market IN ('KR', 'US')),
      change_pct REAL NOT NULL,
      window_minutes INTEGER NOT NULL,
      detected_at_utc TEXT NOT NULL,
      session_label TEXT NOT NULL,
      created_at_utc TEXT NOT NULL DEFAULT ({_UTC_DEFAULT}),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_price_events_symbol_market_detected_at
    ON price_events(symbol, market, detected_at_utc DESC)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS event_reasons (
      id TEXT PRIMARY KEY,
      event_id TEXT NOT NULL,
      rank INTEGER NOT NULL,
      reason_type TEXT NOT NULL,
      confidence_score REAL NOT NULL,
      summary TEXT NOT NULL,
      source_url TEXT NOT NULL,
      published_at_utc TEXT NOT NULL,
      created_at_utc TEXT NOT NULL DEFAULT ({_UTC_DEFAULT}),
      UNIQUE (event_id, rank),
      FOREIGN KEY (event_id) REFERENCES price_events(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_event_reasons_event_id ON event_reasons(event_id)",
    f"""
    CREATE TABLE IF NOT EXISTS notifications (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      event_id TEXT NOT NULL,
      channel TEXT NOT NULL,
      status TEXT NOT NULL,
      message TEXT NOT NULL,
      sent_at_utc TEXT NOT NULL,
      created_at_utc TEXT NOT NULL DEFAULT ({_UTC_DEFAULT}),
      UNIQUE (user_id, event_id, channel),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY (event_id) REFERENCES price_events(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_notifications_user_id_sent_at ON notifications(user_id, sent_at_utc DESC)",
    f"""
    CREATE TABLE IF NOT EXISTS portfolio_holdings (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      symbol TEXT NOT NULL,
      qty REAL NOT NULL CHECK (qty > 0),
      avg_price REAL NOT NULL CHECK (avg_price > 0),
      created_at_utc TEXT NOT NULL DEFAULT ({_UTC_DEFAULT}),
      updated_at_utc TEXT NOT NULL DEFAULT ({_UTC_DEFAULT}),
      UNIQUE (user_id, symbol),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_symbol
    ON portfolio_holdings(user_id, symbol)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS push_tokens (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      token TEXT NOT NULL,
      platform TEXT NOT NULL CHECK (platform IN ('ios', 'android')),
      created_at_utc TEXT NOT NULL DEFAULT ({_UTC_DEFAULT}),
      updated_at_utc TEXT NOT NULL DEFAULT ({_UTC_DEFAULT}),
      UNIQUE (user_id, token),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_push_tokens_user_id ON push_tokens(user_id)",
)

_DROP_STATEMENTS = (
    "DROP TABLE IF EXISTS push_tokens",
    "DROP TABLE IF EXISTS portfolio_holdings",
    "DROP TABLE IF EXISTS notifications",
    "DROP TABLE IF EXISTS event_reasons",
    "DROP TABLE IF EXISTS price_events",
    "DROP TABLE IF EXISTS watchlist_items",
    "DROP TABLE IF EXISTS watchlists",
    "DROP TABLE IF EXISTS users",
)


def create_core_schema(engine: Any) -> None:
    _execute_many(engine, _CREATE_STATEMENTS)


def drop_core_schema(engine: Any) -> None:
    _execute_many(engine, _DROP_STATEMENTS)


def list_tables(engine: Any) -> set[str]:
    rows = fetch_all(engine, "SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row[0] for row in rows}


def execute_statement(
    engine: Any,
    statement: str,
    parameters: Sequence[Any] | Mapping[str, Any] | None = None,
) -> None:
    if hasattr(engine, "dialect"):
        with engine.begin() as connection:
            connection.exec_driver_sql(statement, parameters or ())
        return

    connection = engine.connect()
    try:
        if parameters is None:
            connection.execute(statement)
        else:
            connection.execute(statement, parameters)
        connection.commit()
    finally:
        connection.close()


def fetch_all(
    engine: Any,
    statement: str,
    parameters: Sequence[Any] | Mapping[str, Any] | None = None,
) -> list[tuple[Any, ...]]:
    if hasattr(engine, "dialect"):
        with engine.connect() as connection:
            result = connection.exec_driver_sql(statement, parameters or ())
            return [tuple(row) for row in result.fetchall()]

    connection = engine.connect()
    try:
        if parameters is None:
            cursor = connection.execute(statement)
        else:
            cursor = connection.execute(statement, parameters)
        rows = cursor.fetchall()
    finally:
        connection.close()
    return [tuple(row) for row in rows]


def _execute_many(engine: Any, statements: Iterable[str]) -> None:
    if hasattr(engine, "dialect"):
        with engine.begin() as connection:
            for statement in statements:
                connection.exec_driver_sql(statement)
        return

    connection = engine.connect()
    try:
        for statement in statements:
            connection.execute(statement)
        connection.commit()
    finally:
        connection.close()
