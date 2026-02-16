from __future__ import annotations

from datetime import datetime, timezone
import os
import tempfile
import unittest

from apps.infra.models import (
    CORE_TABLES,
    create_core_schema,
    drop_core_schema,
    execute_statement,
    fetch_all,
    list_tables,
)
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime


class ModelsSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="models-schema-")
        database_path = os.path.join(self._tmpdir.name, "schema.sqlite")
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path}"
        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-models-startup")
        drop_core_schema(self.runtime.engine)

    def tearDown(self) -> None:
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_core_schema_creates_expected_tables_and_indexes(self) -> None:
        create_core_schema(self.runtime.engine)

        tables = list_tables(self.runtime.engine)
        self.assertTrue(set(CORE_TABLES).issubset(tables))

        index_rows = fetch_all(self.runtime.engine, "SELECT name FROM sqlite_master WHERE type = 'index'")
        index_names = {row[0] for row in index_rows}
        self.assertIn("idx_watchlist_items_user_id", index_names)
        self.assertIn("idx_watchlist_items_market_symbol", index_names)
        self.assertIn("idx_price_events_symbol_market_detected_at", index_names)
        self.assertIn("idx_event_reasons_event_id", index_names)
        self.assertIn("idx_notifications_user_id_sent_at", index_names)

    def test_unique_and_foreign_key_violations_raise_db_errors(self) -> None:
        create_core_schema(self.runtime.engine)
        self._seed_user_watchlist()

        execute_statement(
            self.runtime.engine,
            """
            INSERT INTO watchlist_items (id, watchlist_id, user_id, market, symbol)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("item-1", "watch-1", "user-1", "KR", "005930"),
        )

        with self.assertRaises(Exception) as duplicate_error:  # noqa: BLE001
            execute_statement(
                self.runtime.engine,
                """
                INSERT INTO watchlist_items (id, watchlist_id, user_id, market, symbol)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("item-2", "watch-1", "user-1", "KR", "005930"),
            )
        self.assertIn("UNIQUE", str(duplicate_error.exception).upper())

        with self.assertRaises(Exception) as fk_error:  # noqa: BLE001
            execute_statement(
                self.runtime.engine,
                """
                INSERT INTO watchlist_items (id, watchlist_id, user_id, market, symbol)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("item-3", "watch-missing", "user-1", "US", "AAPL"),
            )
        self.assertIn("FOREIGN", str(fk_error.exception).upper())

    def test_created_at_defaults_use_utc_timestamp(self) -> None:
        create_core_schema(self.runtime.engine)

        execute_statement(
            self.runtime.engine,
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            ("user-utc", "utc@example.com", "hashed-password"),
        )

        created_at = fetch_all(
            self.runtime.engine,
            "SELECT created_at_utc FROM users WHERE id = ?",
            ("user-utc",),
        )[0][0]
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

        self.assertTrue(created_at.endswith("Z"))
        self.assertIsNotNone(parsed.tzinfo)
        self.assertEqual(parsed.utcoffset(), timezone.utc.utcoffset(parsed))

    def _seed_user_watchlist(self) -> None:
        execute_statement(
            self.runtime.engine,
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            ("user-1", "u1@example.com", "hash"),
        )
        execute_statement(
            self.runtime.engine,
            "INSERT INTO watchlists (id, user_id, name) VALUES (?, ?, ?)",
            ("watch-1", "user-1", "default"),
        )


if __name__ == "__main__":
    unittest.main()
