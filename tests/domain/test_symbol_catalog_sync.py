from __future__ import annotations

import os
import tempfile
import unittest

from apps.domain.symbol_catalog import (
    CatalogRecord,
    CatalogSnapshot,
    SymbolCatalogService,
    reset_symbol_catalog_service,
    set_symbol_catalog_service,
)
from apps.domain.symbol_search import SymbolSearchService, reset_symbol_search_service
from apps.infra.models import create_core_schema, drop_core_schema
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from apps.infra.redis_client import InMemoryRedisBackend, RedisClient, RedisConfig


class _QueueSource:
    def __init__(self, responses: list[CatalogSnapshot | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[str | None] = []

    def fetch(self, *, since_version: str | None) -> CatalogSnapshot:
        self.calls.append(since_version)
        if not self._responses:
            raise AssertionError("source response queue exhausted")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class SymbolCatalogSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="symbol-catalog-sync-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/catalog.sqlite"

        reset_database_runtime()
        reset_symbol_catalog_service()
        reset_symbol_search_service()

        self.runtime = initialize_database_runtime(request_id="req-watch-005-setup")
        create_core_schema(self.runtime.engine)

        self.catalog_service = SymbolCatalogService(
            bootstrap_records=[
                CatalogRecord(symbol="AAPL", name="Apple Inc.", market="US"),
                CatalogRecord(symbol="005930", name="Samsung Electronics", market="KR"),
            ]
        )
        set_symbol_catalog_service(self.catalog_service)

        self.search_service = SymbolSearchService(
            redis_client=RedisClient(
                config=RedisConfig(redis_url="redis://localhost:6379/0", key_prefix="test-watch-005"),
                backend=InMemoryRedisBackend(),
            ),
            cache_ttl_seconds=120,
        )

    def tearDown(self) -> None:
        drop_core_schema(self.runtime.engine)
        reset_symbol_search_service()
        reset_symbol_catalog_service()
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_full_sync_activates_new_version_for_search(self) -> None:
        source = _QueueSource(
            [
                CatalogSnapshot(
                    version="2026-02-17-v1",
                    mode="full",
                    records=[
                        CatalogRecord(symbol="META", name="Meta Platforms", market="US"),
                        CatalogRecord(symbol="005930", name="Samsung Electronics", market="KR"),
                    ],
                )
            ]
        )

        result = self.catalog_service.sync_from_source(source=source)
        records = self.search_service.search(query="ME", market="US")
        metadata = self.search_service.catalog_metadata()

        self.assertEqual(result.status, "synced")
        self.assertEqual(source.calls, ["bootstrap-v1"])
        self.assertEqual(result.active_version, "2026-02-17-v1")
        self.assertEqual([record.ticker for record in records], ["META"])
        self.assertEqual(metadata["catalog_version"], "2026-02-17-v1")
        self.assertIsNotNone(metadata["catalog_refreshed_at_utc"])

    def test_source_delay_keeps_previous_stable_version(self) -> None:
        ok_source = _QueueSource(
            [
                CatalogSnapshot(
                    version="v1",
                    mode="full",
                    records=[
                        CatalogRecord(symbol="AAPL", name="Apple Inc.", market="US"),
                        CatalogRecord(symbol="005930", name="Samsung Electronics", market="KR"),
                    ],
                )
            ]
        )
        self.catalog_service.sync_from_source(source=ok_source)

        delayed_source = _QueueSource([TimeoutError("upstream delayed")])
        delayed = self.catalog_service.sync_from_source(source=delayed_source)
        us_records = self.search_service.search(query="AA", market="US")

        self.assertEqual(delayed.status, "fallback")
        self.assertEqual(delayed.reason, "source_unavailable")
        self.assertEqual(delayed.active_version, "v1")
        self.assertEqual([record.ticker for record in us_records], ["AAPL"])

    def test_partial_full_sync_falls_back_to_previous_version(self) -> None:
        self.catalog_service.sync_from_source(
            source=_QueueSource(
                [
                    CatalogSnapshot(
                        version="v1",
                        mode="full",
                        records=[
                            CatalogRecord(symbol="AAPL", name="Apple Inc.", market="US"),
                            CatalogRecord(symbol="005930", name="Samsung Electronics", market="KR"),
                        ],
                    )
                ]
            )
        )

        partial = self.catalog_service.sync_from_source(
            source=_QueueSource(
                [
                    CatalogSnapshot(
                        version="v2",
                        mode="full",
                        records=[CatalogRecord(symbol="MSFT", name="Microsoft Corporation", market="US")],
                    )
                ]
            )
        )

        self.assertEqual(partial.status, "fallback")
        self.assertEqual(partial.reason, "partial_failure")
        self.assertEqual(self.catalog_service.active_version(), "v1")

    def test_duplicate_symbol_sync_falls_back(self) -> None:
        self.catalog_service.sync_from_source(
            source=_QueueSource(
                [
                    CatalogSnapshot(
                        version="v1",
                        mode="full",
                        records=[
                            CatalogRecord(symbol="AAPL", name="Apple Inc.", market="US"),
                            CatalogRecord(symbol="005930", name="Samsung Electronics", market="KR"),
                        ],
                    )
                ]
            )
        )

        duplicate = self.catalog_service.sync_from_source(
            source=_QueueSource(
                [
                    CatalogSnapshot(
                        version="v2",
                        mode="full",
                        records=[
                            CatalogRecord(symbol="AAPL", name="Apple Inc.", market="US"),
                            CatalogRecord(symbol="aapl", name="Apple Duplicate", market="US"),
                            CatalogRecord(symbol="005930", name="Samsung Electronics", market="KR"),
                        ],
                    )
                ]
            )
        )

        self.assertEqual(duplicate.status, "fallback")
        self.assertEqual(duplicate.reason, "duplicate_symbol")
        self.assertEqual(self.catalog_service.active_version(), "v1")

    def test_incremental_sync_and_rollback_switch_active_version(self) -> None:
        self.catalog_service.sync_from_source(
            source=_QueueSource(
                [
                    CatalogSnapshot(
                        version="v1",
                        mode="full",
                        records=[
                            CatalogRecord(symbol="AAPL", name="Apple Inc.", market="US"),
                            CatalogRecord(symbol="005930", name="Samsung Electronics", market="KR"),
                        ],
                    )
                ]
            )
        )

        self.search_service.search(query="AA", market="US")  # cache for v1

        self.catalog_service.sync_from_source(
            source=_QueueSource(
                [
                    CatalogSnapshot(
                        version="v2",
                        mode="incremental",
                        records=[
                            CatalogRecord(symbol="AAPL", name="Apple Inc.", market="US", is_active=False),
                            CatalogRecord(symbol="MSFT", name="Microsoft Corporation", market="US", is_active=True),
                        ],
                    )
                ]
            )
        )

        current_records = self.search_service.search(query="MS", market="US")
        self.assertEqual([record.ticker for record in current_records], ["MSFT"])

        rolled_back = self.catalog_service.rollback_to_version(version="v1")
        after_rollback_msft = self.search_service.search(query="MS", market="US")
        after_rollback_aapl = self.search_service.search(query="AA", market="US")

        self.assertTrue(rolled_back)
        self.assertEqual(self.catalog_service.active_version(), "v1")
        self.assertEqual(after_rollback_msft, [])
        self.assertEqual([record.ticker for record in after_rollback_aapl], ["AAPL"])


if __name__ == "__main__":
    unittest.main()
