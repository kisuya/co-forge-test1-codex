from __future__ import annotations

import os
import tempfile
import unittest

from apps.infra.migrations import HEAD_REVISION, downgrade_base, get_current_revision, upgrade_head
from apps.infra.models import CORE_TABLES, fetch_all, list_tables
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime


class AlembicMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="alembic-migration-")
        db_file = os.path.join(self._tmpdir.name, "migrate.sqlite")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_file}"
        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-migrate-startup")

    def tearDown(self) -> None:
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_upgrade_head_prepares_schema_on_fresh_db(self) -> None:
        result = upgrade_head(self.runtime.engine)

        self.assertEqual(result, "upgraded")
        self.assertEqual(get_current_revision(self.runtime.engine), HEAD_REVISION)

        tables = list_tables(self.runtime.engine)
        self.assertTrue(set(CORE_TABLES).issubset(tables))

    def test_downgrade_base_removes_schema_without_errors(self) -> None:
        upgrade_head(self.runtime.engine)

        result = downgrade_base(self.runtime.engine)
        second = downgrade_base(self.runtime.engine)

        self.assertEqual(result, "downgraded")
        self.assertEqual(second, "noop")
        self.assertIsNone(get_current_revision(self.runtime.engine))

        tables_after = list_tables(self.runtime.engine)
        self.assertTrue(set(CORE_TABLES).isdisjoint(tables_after))

    def test_reapplying_upgrade_head_is_safe_noop(self) -> None:
        first = upgrade_head(self.runtime.engine)
        second = upgrade_head(self.runtime.engine)

        version_rows = fetch_all(self.runtime.engine, "SELECT version_num FROM alembic_version")

        self.assertEqual(first, "upgraded")
        self.assertEqual(second, "noop")
        self.assertEqual(len(version_rows), 1)
        self.assertEqual(version_rows[0][0], HEAD_REVISION)


if __name__ == "__main__":
    unittest.main()
