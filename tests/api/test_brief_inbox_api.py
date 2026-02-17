from __future__ import annotations

import os
import tempfile
import unittest

from apps.api.main import app
from apps.domain.briefs import brief_inbox_store
from apps.infra.models import create_core_schema, drop_core_schema
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from fastapi.testclient import TestClient


class BriefInboxApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="brief-inbox-api-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/briefs.sqlite"
        os.environ["JWT_SECRET"] = "brief-inbox-secret"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-brief-inbox-setup")
        create_core_schema(self.runtime.engine)
        self.client = TestClient(app)

        self.user_a = self.client.post(
            "/v1/auth/signup",
            json={"email": "brief-a@example.com", "password": "brief-password-a"},
        ).json()
        self.user_b = self.client.post(
            "/v1/auth/signup",
            json={"email": "brief-b@example.com", "password": "brief-password-b"},
        ).json()

        brief_inbox_store.clear()
        brief_inbox_store.upsert_brief(
            brief_id="brief-pre-a-1",
            user_id=self.user_a["user_id"],
            brief_type="pre_market",
            title="개장 전 브리프",
            summary="오늘의 체크포인트",
            generated_at_utc="2026-02-17T22:40:00Z",
            markets=["US"],
            status="unread",
            items=[
                {
                    "event_id": "evt-a-1",
                    "symbol": "AAPL",
                    "market": "US",
                    "summary": "실적 발표 전 점검",
                    "event_detail_url": "/events/evt-a-1",
                    "source_url": "https://news.example/aapl-pre",
                }
            ],
        )
        brief_inbox_store.upsert_brief(
            brief_id="brief-post-a-1",
            user_id=self.user_a["user_id"],
            brief_type="post_close",
            title="장마감 브리프",
            summary="오늘 변동 요약",
            generated_at_utc="2026-02-17T06:40:00Z",
            markets=["US"],
            status="read",
            items=[
                {
                    "event_id": "evt-a-2",
                    "symbol": "MSFT",
                    "market": "US",
                    "summary": "종가 기준 변동 +3.10%",
                    "event_detail_url": "/events/evt-a-2",
                    "source_url": "https://news.example/msft-post",
                }
            ],
        )
        brief_inbox_store.upsert_brief(
            brief_id="brief-expired-a-1",
            user_id=self.user_a["user_id"],
            brief_type="pre_market",
            title="만료 브리프",
            summary="만료 링크 테스트",
            generated_at_utc="2026-02-17T00:00:00Z",
            expires_at_utc="2026-02-17T00:05:00Z",
            markets=["US"],
            status="unread",
            items=[
                {
                    "event_id": "evt-a-3",
                    "symbol": "TSLA",
                    "market": "US",
                    "summary": "만료된 브리프",
                    "event_detail_url": "/events/evt-a-3",
                    "source_url": "https://news.example/tsla-pre",
                }
            ],
        )
        brief_inbox_store.upsert_brief(
            brief_id="brief-pre-b-1",
            user_id=self.user_b["user_id"],
            brief_type="pre_market",
            title="다른 사용자 브리프",
            summary="격리 검증",
            generated_at_utc="2026-02-17T22:00:00Z",
            markets=["US"],
            status="unread",
            items=[
                {
                    "event_id": "evt-b-1",
                    "symbol": "NVDA",
                    "market": "US",
                    "summary": "다른 사용자 항목",
                    "event_detail_url": "/events/evt-b-1",
                    "source_url": "https://news.example/nvda-pre",
                }
            ],
        )

    def tearDown(self) -> None:
        brief_inbox_store.clear()
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_list_briefs_returns_user_scoped_sections_and_meta(self) -> None:
        response = self.client.get(
            "/v1/briefs?size=20",
            headers=self._auth(self.user_a["access_token"]),
        )
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["count"], 3)
        self.assertEqual(body["meta"]["pre_market_count"], 2)
        self.assertEqual(body["meta"]["post_close_count"], 1)
        self.assertEqual(body["meta"]["unread_count"], 2)
        self.assertTrue(all(item["id"].startswith("brief-") for item in body["items"]))
        self.assertTrue(all(item["id"] != "brief-pre-b-1" for item in body["items"]))

    def test_get_brief_detail_returns_event_and_source_links(self) -> None:
        response = self.client.get(
            "/v1/briefs/brief-pre-a-1",
            headers=self._auth(self.user_a["access_token"]),
        )
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["brief"]["id"], "brief-pre-a-1")
        self.assertEqual(body["brief"]["brief_type"], "pre_market")
        self.assertEqual(len(body["brief"]["items"]), 1)
        item = body["brief"]["items"][0]
        self.assertEqual(item["event_detail_url"], "/events/evt-a-1")
        self.assertTrue(item["source_url"].startswith("https://"))

    def test_mark_brief_read_updates_status_and_unread_count(self) -> None:
        response = self.client.patch(
            "/v1/briefs/brief-pre-a-1/read",
            headers=self._auth(self.user_a["access_token"]),
        )
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["brief"]["id"], "brief-pre-a-1")
        self.assertEqual(body["brief"]["status"], "read")
        self.assertEqual(body["unread_count"], 1)

    def test_expired_brief_detail_returns_410_contract(self) -> None:
        response = self.client.get(
            "/v1/briefs/brief-expired-a-1",
            headers=self._auth(self.user_a["access_token"]),
        )

        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.json()["code"], "brief_link_expired")

    def test_cross_user_brief_access_returns_not_found(self) -> None:
        response = self.client.get(
            "/v1/briefs/brief-pre-a-1",
            headers=self._auth(self.user_b["access_token"]),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "brief_not_found")

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}


if __name__ == "__main__":
    unittest.main()
