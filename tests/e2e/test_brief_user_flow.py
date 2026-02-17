from __future__ import annotations

import json
import os
from pathlib import Path
import re
import unittest
try:
    from playwright.sync_api import expect, sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime dependency
    _PLAYWRIGHT_AVAILABLE = False
PRE_BRIEF = {
    "id": "pre-1",
    "brief_type": "pre_market",
    "title": "개장 전 브리프",
    "summary": "오늘 확인할 핵심 일정",
    "generated_at_utc": "2026-02-17T22:40:00Z",
    "markets": ["US"],
    "item_count": 1,
    "fallback_reason": None,
    "status": "unread",
    "is_expired": False,
}
POST_BRIEF = {
    "id": "post-1",
    "brief_type": "post_close",
    "title": "장마감 브리프",
    "summary": "오늘 변동 요약",
    "generated_at_utc": "2026-02-17T06:10:00Z",
    "markets": ["US"],
    "item_count": 1,
    "fallback_reason": None,
    "status": "read",
    "is_expired": False,
}
class BriefUserFlowE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.getenv("RUN_E2E") != "1":
            raise unittest.SkipTest("Set RUN_E2E=1 to run Playwright E2E tests")
        if not _PLAYWRIGHT_AVAILABLE:
            raise unittest.SkipTest("playwright is not installed")

    def test_brief_user_journey_receive_read_and_open_detail(self) -> None:
        base_url = os.getenv("E2E_BASE_URL", "http://127.0.0.1:3000")
        screenshots_dir = Path("artifacts/e2e")
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                self._run_step_with_retry(
                    run_step=lambda attempt: self._run_delivery_delay_and_read_flow_step(
                        browser=browser,
                        base_url=base_url,
                        screenshots_dir=screenshots_dir,
                        attempt=attempt,
                    ),
                )
                self._run_step_with_retry(
                    run_step=lambda attempt: self._run_empty_brief_inbox_step(
                        browser=browser,
                        base_url=base_url,
                        screenshots_dir=screenshots_dir,
                        attempt=attempt,
                    ),
                )
                self._run_step_with_retry(
                    run_step=lambda attempt: self._run_expired_link_step(
                        browser=browser,
                        base_url=base_url,
                        screenshots_dir=screenshots_dir,
                        attempt=attempt,
                    ),
                )
            finally:
                browser.close()

    def _run_step_with_retry(self, *, run_step) -> None:
        errors: list[Exception] = []
        for attempt in (1, 2):
            try:
                run_step(attempt)
                return
            except Exception as exc:  # noqa: BLE001 - retry once per step for flaky browser/network
                errors.append(exc)
                if attempt == 2:
                    raise
        if errors:
            raise errors[-1]

    def _run_delivery_delay_and_read_flow_step(self, *, browser, base_url: str, screenshots_dir: Path, attempt: int) -> None:
        context = self._new_authenticated_context(browser=browser, user_id="user-brief-delay", access_token="token-brief-delay")
        page = context.new_page()
        try:
            self._mock_common_dashboard_endpoints(page=page, user_id="user-brief-delay")
            self._mock_brief_flow(page=page, scenario="delay")
            page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")

            expect(page.get_by_role("alert")).to_contain_text("브리프 전달이 지연되고 있습니다.")
            retry_button = page.get_by_role("button", name="다시 시도")
            expect(retry_button).to_be_visible()
            page.screenshot(path=str(screenshots_dir / f"brief-user-flow-{attempt}-delivery-delay.png"), full_page=True)

            retry_button.click()
            expect(page.get_by_test_id("brief-section-pre")).to_be_visible()
            expect(page.get_by_test_id("brief-section-post")).to_be_visible()
            expect(page.get_by_test_id("brief-detail-title")).to_contain_text("개장 전 브리프")
            expect(page.get_by_test_id("brief-card-status-pre-1")).to_contain_text("읽음")
            expect(page.get_by_test_id("brief-unread-count")).to_contain_text("읽지 않음 0")
            expect(page.get_by_role("link", name="근거 원문 보기")).to_have_attribute("href", "https://news.example/pre-1")
            expect(page.get_by_role("link", name="이벤트 상세 이동")).to_have_attribute("href", "/events/evt-pre-1")
            page.screenshot(path=str(screenshots_dir / f"brief-user-flow-{attempt}-pre-market-read.png"), full_page=True)

            page.get_by_test_id("brief-card-post-1").click()
            expect(page.get_by_test_id("brief-detail-title")).to_contain_text("장마감 브리프")
            expect(page.get_by_text("종가 기준 변동 +4.10%")).to_be_visible()
            expect(page.get_by_role("link", name="이벤트 상세 이동")).to_have_attribute("href", "/events/evt-post-1")
            page.screenshot(path=str(screenshots_dir / f"brief-user-flow-{attempt}-post-close-detail.png"), full_page=True)
        finally:
            context.close()

    def _run_empty_brief_inbox_step(self, *, browser, base_url: str, screenshots_dir: Path, attempt: int) -> None:
        context = self._new_authenticated_context(browser=browser, user_id="user-brief-empty", access_token="token-brief-empty")
        page = context.new_page()
        try:
            self._mock_common_dashboard_endpoints(page=page, user_id="user-brief-empty")
            self._mock_brief_flow(page=page, scenario="empty")
            page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")

            expect(page.get_by_test_id("brief-empty")).to_be_visible()
            expect(page.get_by_test_id("brief-detail-title")).to_have_count(0)
            page.screenshot(path=str(screenshots_dir / f"brief-user-flow-{attempt}-empty-inbox.png"), full_page=True)
        finally:
            context.close()

    def _run_expired_link_step(self, *, browser, base_url: str, screenshots_dir: Path, attempt: int) -> None:
        context = self._new_authenticated_context(
            browser=browser,
            user_id="user-brief-expired",
            access_token="token-brief-expired",
        )
        page = context.new_page()
        try:
            self._mock_common_dashboard_endpoints(page=page, user_id="user-brief-expired")
            self._mock_brief_flow(page=page, scenario="expired")
            page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")

            expect(page.get_by_test_id("brief-detail-expired")).to_contain_text("브리프 링크가 만료되었습니다. 최신 브리프를 확인하세요.")
            page.screenshot(path=str(screenshots_dir / f"brief-user-flow-{attempt}-expired-link.png"), full_page=True)
        finally:
            context.close()

    def _new_authenticated_context(self, *, browser, user_id: str, access_token: str):
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.add_init_script(
            "window.localStorage.setItem("
            "'oh-my-stock.auth.session',"
            f"JSON.stringify({{userId: '{user_id}', accessToken: '{access_token}'}}));"
        )
        return context

    def _mock_common_dashboard_endpoints(self, *, page, user_id: str) -> None:
        page.route(
            re.compile(r".*/v1/auth/me$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"user": {"id": user_id, "email": f"{user_id}@example.com"}}),
            ),
        )
        page.route(
            re.compile(r".*/v1/watchlists/items\?page=1&size=20$"),
            lambda route: route.fulfill(status=200, content_type="application/json", body='{"items":[],"total":0,"page":1,"size":20}'),
        )
        page.route(
            re.compile(r".*/v1/events\?size=20$"),
            lambda route: route.fulfill(status=200, content_type="application/json", body='{"items":[],"count":0,"next_cursor":null}'),
        )
        page.route(
            re.compile(r".*/v1/notifications$"),
            lambda route: route.fulfill(status=200, content_type="application/json", body='{"items":[],"unread_count":0}'),
        )
        page.route(
            re.compile(r".*/v1/thresholds$"),
            lambda route: route.fulfill(status=200, content_type="application/json", body='{"items":[],"count":0}'),
        )

    def _mock_brief_flow(self, *, page, scenario: str) -> None:
        if scenario == "delay":
            list_attempt = {"count": 0}
            page.route(
                re.compile(r".*/v1/briefs\?size=20$"),
                lambda route: self._fulfill_brief_list_with_delay(route=route, list_attempt=list_attempt),
            )
            page.route(
                re.compile(r".*/v1/briefs/pre-1$"),
                lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"brief": self._brief_detail("pre")})),
            )
            page.route(
                re.compile(r".*/v1/briefs/post-1$"),
                lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"brief": self._brief_detail("post")})),
            )
            page.route(
                re.compile(r".*/v1/briefs/pre-1/read$"),
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"brief": PRE_BRIEF | {"status": "read"}, "unread_count": 0}),
                ),
            )
            return

        if scenario == "empty":
            page.route(
                re.compile(r".*/v1/briefs\?size=20$"),
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"items":[],"count":0,"meta":{"unread_count":0,"pre_market_count":0,"post_close_count":0}}',
                ),
            )
            return

        page.route(
            re.compile(r".*/v1/briefs\?size=20$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "items": [PRE_BRIEF | {"id": "brief-expired-1", "is_expired": True}],
                        "count": 1,
                        "meta": {"unread_count": 1, "pre_market_count": 1, "post_close_count": 0},
                    }
                ),
            ),
        )
        page.route(
            re.compile(r".*/v1/briefs/brief-expired-1$"),
            lambda route: route.fulfill(
                status=410,
                content_type="application/json",
                body='{"code":"brief_link_expired","message":"Brief link has expired","retryable":false}',
            ),
        )

    def _fulfill_brief_list_with_delay(self, *, route, list_attempt: dict[str, int]) -> None:
        list_attempt["count"] += 1
        if list_attempt["count"] == 1:
            route.fulfill(
                status=503,
                content_type="application/json",
                body='{"code":"temporarily_unavailable","message":"브리프 전달이 지연되고 있습니다.","retryable":true}',
            )
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "items": [PRE_BRIEF, POST_BRIEF],
                    "count": 2,
                    "meta": {"unread_count": 1, "pre_market_count": 1, "post_close_count": 1},
                }
            ),
        )

    def _brief_detail(self, brief_type: str) -> dict[str, object]:
        if brief_type == "pre":
            return PRE_BRIEF | {
                "items": [
                    {
                        "event_id": "evt-pre-1",
                        "symbol": "AAPL",
                        "market": "US",
                        "summary": "실적 발표 전 체크",
                        "event_detail_url": "/events/evt-pre-1",
                        "source_url": "https://news.example/pre-1",
                    }
                ]
            }
        return POST_BRIEF | {
            "items": [
                {
                    "event_id": "evt-post-1",
                    "symbol": "MSFT",
                    "market": "US",
                    "summary": "종가 기준 변동 +4.10%",
                    "event_detail_url": "/events/evt-post-1",
                    "source_url": "https://news.example/post-1",
                }
            ]
        }
if __name__ == "__main__":
    unittest.main()
