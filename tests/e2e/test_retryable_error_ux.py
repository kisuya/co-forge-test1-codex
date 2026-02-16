from __future__ import annotations

import os
from pathlib import Path
import re
import unittest

try:
    from playwright.sync_api import expect, sync_playwright

    _PLAYWRIGHT_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime dependency
    _PLAYWRIGHT_AVAILABLE = False


class RetryableErrorUxE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.getenv("RUN_E2E") != "1":
            raise unittest.SkipTest("Set RUN_E2E=1 to run Playwright E2E tests")
        if not _PLAYWRIGHT_AVAILABLE:
            raise unittest.SkipTest("playwright is not installed")

    def test_retryable_banner_retry_button_and_cooldown_message(self) -> None:
        base_url = os.getenv("E2E_BASE_URL", "http://127.0.0.1:3000")
        screenshots_dir = Path("artifacts/e2e")
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context()
            context.add_init_script(
                "window.localStorage.setItem('oh-my-stock.auth.session', JSON.stringify({userId: 'user-1', accessToken: 'token-1'}));"
            )
            page = context.new_page()

            self._mock_dashboard_api(page=page)

            page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")

            retryable_alert = page.get_by_role("alert")
            expect(retryable_alert).to_contain_text("재시도 가능한 오류입니다.")
            expect(page.get_by_role("button", name="다시 시도")).to_be_visible()
            expect(page.get_by_text("쿨다운 중")).to_be_visible()
            page.screenshot(path=str(screenshots_dir / "retryable-error-ux-step1.png"), full_page=True)

            page.get_by_role("button", name="다시 시도").click()
            expect(retryable_alert).to_contain_text("재시도 불가 오류입니다.")
            expect(page.get_by_role("button", name="다시 시도")).to_have_count(0)
            page.screenshot(path=str(screenshots_dir / "retryable-error-ux-step2.png"), full_page=True)

            context.close()
            browser.close()

    def _mock_dashboard_api(self, *, page) -> None:
        event_attempt = {"count": 0}

        page.route(
            re.compile(r".*/v1/auth/me$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body='{"user":{"id":"user-1","email":"e2e@example.com"}}',
            ),
        )
        page.route(
            re.compile(r".*/v1/watchlists/items\?page=1&size=20$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body='{"items":[],"total":0,"page":1,"size":20}',
            ),
        )

        def fulfill_events(route) -> None:
            event_attempt["count"] += 1
            if event_attempt["count"] == 1:
                route.fulfill(
                    status=503,
                    content_type="application/json",
                    body='{"code":"temporarily_unavailable","message":"Temporary service issue. Please retry.","retryable":true}',
                )
                return
            route.fulfill(
                status=400,
                content_type="application/json",
                body='{"code":"invalid_input","message":"Invalid filter","retryable":false}',
            )

        page.route(re.compile(r".*/v1/events\?size=20$"), fulfill_events)

        page.route(
            re.compile(r".*/v1/notifications$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=(
                    '{"items":[{"id":"n1","user_id":"user-1","event_id":"evt-1",'
                    '"channel":"in_app","status":"cooldown","message":"재알림 쿨다운 적용",'
                    '"sent_at_utc":"2026-02-17T00:00:00Z"}],"unread_count":1}'
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
