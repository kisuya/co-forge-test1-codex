from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
import unittest
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

try:
    from playwright.sync_api import expect, sync_playwright

    _PLAYWRIGHT_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime dependency
    _PLAYWRIGHT_AVAILABLE = False


class WatchlistTrustFlowE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.getenv("RUN_E2E") != "1":
            raise unittest.SkipTest("Set RUN_E2E=1 to run Playwright E2E tests")
        if not _PLAYWRIGHT_AVAILABLE:
            raise unittest.SkipTest("playwright is not installed")

    def test_watchlist_trust_flow_signup_error_and_mobile(self) -> None:
        errors: list[Exception] = []
        for attempt in (1, 2):
            try:
                self._run_once(attempt=attempt)
                return
            except Exception as exc:  # noqa: BLE001 - retry once for flaky browser/network
                errors.append(exc)
                if attempt == 2:
                    raise
        if errors:
            raise errors[-1]

    def _run_once(self, *, attempt: int) -> None:
        base_url = os.getenv("E2E_BASE_URL", "http://127.0.0.1:3000")
        screenshots_dir = Path("artifacts/e2e")
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()

            desktop_context = browser.new_context(viewport={"width": 1440, "height": 1000})
            desktop_page = desktop_context.new_page()
            self._mock_watchlist_flow_api(page=desktop_page, profile="desktop")
            self._run_desktop_flow(page=desktop_page, base_url=base_url, screenshots_dir=screenshots_dir, attempt=attempt)
            desktop_context.close()

            mobile_context = browser.new_context(viewport={"width": 390, "height": 844})
            mobile_context.add_init_script(
                (
                    "window.localStorage.setItem("
                    "'oh-my-stock.auth.session',"
                    "JSON.stringify({userId: 'user-mobile', accessToken: 'token-mobile'}));"
                )
            )
            mobile_page = mobile_context.new_page()
            self._mock_watchlist_flow_api(page=mobile_page, profile="mobile")
            self._run_mobile_flow(page=mobile_page, base_url=base_url, screenshots_dir=screenshots_dir, attempt=attempt)
            mobile_context.close()

            browser.close()

    def _run_desktop_flow(self, *, page, base_url: str, screenshots_dir: Path, attempt: int) -> None:
        email = f"watch-e2e-{uuid4().hex[:8]}@example.com"
        password = "e2e-password-123"

        page.goto(f"{base_url}/signup", wait_until="domcontentloaded")
        page.get_by_label("이메일").fill(email)
        page.get_by_label("비밀번호").fill(password)
        page.get_by_role("button", name="회원가입").click()
        expect(page).to_have_url(re.compile(r"/dashboard$"))
        expect(page.get_by_test_id("watchlist-empty")).to_be_visible()
        page.screenshot(path=str(screenshots_dir / f"watchlist-trust-flow-{attempt}-desktop-auth.png"), full_page=True)

        query_input = page.get_by_label("종목코드")
        add_button = page.get_by_role("button", name="추가")

        query_input.fill("ap")
        retry_search_button = page.get_by_role("button", name="검색 다시 시도")
        expect(retry_search_button).to_be_visible()
        expect(page.get_by_text("일시적인 검색 오류입니다.")).to_be_visible()
        page.screenshot(path=str(screenshots_dir / f"watchlist-trust-flow-{attempt}-desktop-search-error.png"), full_page=True)

        retry_search_button.click()
        aapl_option = page.get_by_role("button", name="US:AAPL · Apple Inc.")
        expect(aapl_option).to_be_visible()
        aapl_option.click()
        add_button.click()
        expect(page.get_by_text("US:AAPL")).to_be_visible()
        page.screenshot(path=str(screenshots_dir / f"watchlist-trust-flow-{attempt}-desktop-add-success.png"), full_page=True)

        query_input.fill("ap")
        expect(page.get_by_role("button", name="US:AAPL · Apple Inc.")).to_be_visible()
        page.get_by_role("button", name="US:AAPL · Apple Inc.").click()
        add_button.click()
        expect(page.get_by_text("이미 등록된 관심종목입니다.")).to_be_visible()

        query_input.fill("bad")
        bad_option = page.get_by_role("button", name="US:BAD1 · Broken Symbol")
        expect(bad_option).to_be_visible()
        bad_option.click()
        add_button.click()
        expect(page.get_by_text("카탈로그에 없는 심볼입니다.")).to_be_visible()
        expect(page.get_by_role("button", name="저장 다시 시도")).to_be_visible()
        expect(page.get_by_role("button", name="취소")).to_be_visible()
        page.get_by_role("button", name="취소").click()

        page.get_by_label("시장").select_option("KR")
        query_input.fill("00")
        kr_option = page.get_by_role("button", name="KR:005930 · Samsung Electronics")
        expect(kr_option).to_be_visible()
        kr_option.click()
        add_button.click()
        expect(page.get_by_text("시장과 심볼이 일치하지 않습니다.")).to_be_visible()
        mismatch_retry_button = page.get_by_role("button", name="저장 다시 시도")
        mismatch_retry_button.click()
        expect(page.get_by_text("KR:005930")).to_be_visible()
        page.screenshot(path=str(screenshots_dir / f"watchlist-trust-flow-{attempt}-desktop-error-recovery.png"), full_page=True)

    def _run_mobile_flow(self, *, page, base_url: str, screenshots_dir: Path, attempt: int) -> None:
        page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")

        composer = page.get_by_test_id("watchlist-composer")
        expect(composer).to_be_visible()
        box = composer.bounding_box()
        self.assertIsNotNone(box)
        assert box is not None  # satisfy type checker
        self.assertLessEqual(box["x"] + box["width"], 390)

        query_input = page.get_by_label("종목코드")
        query_input.fill("ms")
        msft_option = page.get_by_role("button", name="US:MSFT · Microsoft Corporation")
        expect(msft_option).to_be_visible()
        msft_option.click()
        page.get_by_role("button", name="추가").click()
        expect(page.get_by_text("US:MSFT")).to_be_visible()
        page.screenshot(path=str(screenshots_dir / f"watchlist-trust-flow-{attempt}-mobile.png"), full_page=True)

    def _mock_watchlist_flow_api(self, *, page, profile: str) -> None:
        watchlist_items: list[dict[str, str]] = []
        search_attempts: dict[str, int] = {}
        create_attempts: dict[str, int] = {}

        def count_attempt(target: dict[str, int], key: str) -> int:
            target[key] = target.get(key, 0) + 1
            return target[key]

        page.route(
            re.compile(r".*/v1/auth/signup$"),
            lambda route: route.fulfill(
                status=201,
                content_type="application/json",
                body='{"user_id":"user-e2e","access_token":"token-e2e"}',
            ),
        )
        page.route(
            re.compile(r".*/v1/auth/me$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body='{"user":{"id":"user-e2e","email":"watch-e2e@example.com"}}',
            ),
        )

        def handle_watchlist(route) -> None:
            method = route.request.method.upper()
            if method == "GET":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "items": watchlist_items,
                            "total": len(watchlist_items),
                            "page": 1,
                            "size": 20,
                        }
                    ),
                )
                return

            if method == "POST":
                body = json.loads(route.request.post_data or "{}")
                symbol = str(body.get("symbol", "")).upper()
                market = str(body.get("market", "")).upper()
                create_count = count_attempt(create_attempts, f"{market}:{symbol}")

                if symbol == "AAPL" and market == "US":
                    if any(
                        item["symbol"].upper() == "AAPL" and item["market"] == "US"
                        for item in watchlist_items
                    ):
                        route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps(
                                {
                                    "item": {
                                        "id": "wl-us-aapl",
                                        "user_id": "user-e2e",
                                        "symbol": "AAPL",
                                        "market": "US",
                                        "created_at_utc": "2026-02-17T00:00:00Z",
                                    },
                                    "is_duplicate": True,
                                }
                            ),
                        )
                        return

                    item = {
                        "id": "wl-us-aapl",
                        "user_id": "user-e2e",
                        "symbol": "AAPL",
                        "market": "US",
                        "created_at_utc": "2026-02-17T00:00:00Z",
                    }
                    watchlist_items.append(item)
                    route.fulfill(
                        status=201,
                        content_type="application/json",
                        body=json.dumps({"item": item, "is_duplicate": False}),
                    )
                    return

                if symbol == "BAD1":
                    route.fulfill(
                        status=400,
                        content_type="application/json",
                        body='{"code":"symbol_not_found","message":"카탈로그에 없는 심볼입니다.","retryable":false}',
                    )
                    return

                if symbol == "005930" and market == "KR":
                    if profile == "desktop" and create_count == 1:
                        route.fulfill(
                            status=400,
                            content_type="application/json",
                            body=(
                                '{"code":"market_mismatch","message":"시장과 심볼이 일치하지 않습니다.",'
                                '"details":{"market":"KR","symbol":"005930"},"retryable":false}'
                            ),
                        )
                        return
                    item = {
                        "id": "wl-kr-005930",
                        "user_id": "user-e2e",
                        "symbol": "005930",
                        "market": "KR",
                        "created_at_utc": "2026-02-17T00:00:00Z",
                    }
                    watchlist_items.append(item)
                    route.fulfill(
                        status=201,
                        content_type="application/json",
                        body=json.dumps({"item": item, "is_duplicate": False}),
                    )
                    return

                if symbol == "MSFT" and market == "US":
                    item = {
                        "id": "wl-us-msft",
                        "user_id": "user-e2e",
                        "symbol": "MSFT",
                        "market": "US",
                        "created_at_utc": "2026-02-17T00:00:00Z",
                    }
                    watchlist_items.append(item)
                    route.fulfill(
                        status=201,
                        content_type="application/json",
                        body=json.dumps({"item": item, "is_duplicate": False}),
                    )
                    return

                route.fulfill(
                    status=400,
                    content_type="application/json",
                    body='{"code":"invalid_input","message":"지원하지 않는 테스트 입력입니다.","retryable":false}',
                )
                return

            route.fulfill(
                status=405,
                content_type="application/json",
                body='{"code":"method_not_allowed","message":"지원하지 않는 메서드입니다.","retryable":false}',
            )

        page.route(re.compile(r".*/v1/watchlists/items(\?.*)?$"), handle_watchlist)

        def handle_search(route) -> None:
            parsed = urlparse(route.request.url)
            params = parse_qs(parsed.query)
            query = (params.get("q", [""])[0] or "").strip().upper()
            market = (params.get("market", ["US"])[0] or "US").strip().upper()
            key = f"{market}:{query}"
            search_count = count_attempt(search_attempts, key)

            if profile == "desktop" and key == "US:AP" and search_count == 1:
                route.fulfill(
                    status=503,
                    content_type="application/json",
                    body='{"code":"temporarily_unavailable","message":"일시적인 검색 오류입니다.","retryable":true}',
                )
                return

            if profile == "desktop":
                time.sleep(0.2)

            items: list[dict[str, str]] = []
            if key == "US:AP":
                items = [{"ticker": "AAPL", "name": "Apple Inc.", "market": "US"}]
            elif key == "US:BAD":
                items = [{"ticker": "BAD1", "name": "Broken Symbol", "market": "US"}]
            elif key == "KR:00":
                items = [{"ticker": "005930", "name": "Samsung Electronics", "market": "KR"}]
            elif key == "US:MS":
                items = [{"ticker": "MSFT", "name": "Microsoft Corporation", "market": "US"}]

            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "items": items,
                        "count": len(items),
                        "catalog_version": "v2026-02-17",
                        "catalog_refreshed_at_utc": "2026-02-17T00:00:00Z",
                    }
                ),
            )

        page.route(re.compile(r".*/v1/symbols/search\?.*"), handle_search)

        page.route(
            re.compile(r".*/v1/events\?size=20$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body='{"items":[],"count":0,"next_cursor":null}',
            ),
        )
        page.route(
            re.compile(r".*/v1/events/.*$"),
            lambda route: route.fulfill(
                status=404,
                content_type="application/json",
                body='{"code":"not_found","message":"이벤트를 찾을 수 없습니다.","retryable":false}',
            ),
        )

        page.route(
            re.compile(r".*/v1/notifications$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=(
                    '{"items":[{"id":"n1","user_id":"user-e2e","event_id":"evt-1","channel":"in_app",'
                    '"status":"cooldown","message":"재알림 쿨다운 적용","sent_at_utc":"2026-02-17T00:00:00Z"}],'
                    '"unread_count":1}'
                ),
            ),
        )
        page.route(
            re.compile(r".*/v1/thresholds$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body='{"items":[],"count":0}',
            ),
        )


if __name__ == "__main__":
    unittest.main()
