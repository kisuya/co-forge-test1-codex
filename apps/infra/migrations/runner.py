from __future__ import annotations

from typing import Any

from apps.infra.models import execute_statement, fetch_all
from apps.infra.migrations.versions import REVISION_ID, downgrade as downgrade_initial, upgrade as upgrade_initial

HEAD_REVISION = REVISION_ID


def upgrade_head(engine: Any) -> str:
    _ensure_version_table(engine)
    current = get_current_revision(engine)
    if current == HEAD_REVISION:
        return "noop"
    if current is not None and current != HEAD_REVISION:
        raise RuntimeError(f"unsupported revision state: {current}")

    upgrade_initial(engine)
    execute_statement(engine, "DELETE FROM alembic_version")
    execute_statement(
        engine,
        f"INSERT INTO alembic_version(version_num) VALUES ('{HEAD_REVISION}')",
    )
    return "upgraded"


def downgrade_base(engine: Any) -> str:
    _ensure_version_table(engine)
    current = get_current_revision(engine)
    if current is None:
        return "noop"
    if current != HEAD_REVISION:
        raise RuntimeError(f"unsupported revision state: {current}")

    downgrade_initial(engine)
    execute_statement(engine, "DELETE FROM alembic_version")
    return "downgraded"


def get_current_revision(engine: Any) -> str | None:
    _ensure_version_table(engine)
    rows = fetch_all(engine, "SELECT version_num FROM alembic_version LIMIT 1")
    if not rows:
        return None
    return rows[0][0]


def _ensure_version_table(engine: Any) -> None:
    execute_statement(
        engine,
        """
        CREATE TABLE IF NOT EXISTS alembic_version (
          version_num TEXT PRIMARY KEY
        )
        """,
    )
