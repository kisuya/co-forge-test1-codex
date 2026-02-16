from __future__ import annotations

from typing import Any

from apps.infra.models import create_core_schema, drop_core_schema

REVISION_ID = "0001_initial_schema"
DOWN_REVISION = None


def upgrade(engine: Any) -> None:
    create_core_schema(engine)


def downgrade(engine: Any) -> None:
    drop_core_schema(engine)
