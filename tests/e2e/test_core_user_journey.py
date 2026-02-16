from __future__ import annotations

import os
from pathlib import Path
import re
import unittest
from uuid import uuid4

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import expect, sync_playwright

    _PLAYWRIGHT_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime dependency
    _PLAYWRIGHT_AVAILABLE = False


class CoreUserJourneyE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.getenv("RUN_E2E") != "1":
            raise unittest.SkipTest("Set RUN_E2E=1 to run Playwright E2E tests")
        if not _PLAYWRIGHT_AVAILABLE:
            raise unittest.SkipTest("playwright is not installed")

    def test_signup_watchlist_event_reason_flow_with_retry(self) -> None:
        errors: list[Exception] = []
        for attempt in (1, 2):
            try:
                self._run_once(attempt=attempt)
                return
            except Exception as exc:  # noqa: BLE001 - retry once on any failure.
                errors.append(exc)
                if attempt == 2:
                    raise
        if errors:
            raise errors[-1]

    def _run_once(self, *, attempt: int) -> None:
        base_url = os.getenv("E2E_BASE_URL", "http://127.0.0.1:3000")
        api_base_url = os.getenv("E2E_API_BASE_URL", "http://127.0.0.1:8000")
        screenshots_dir = Path("artifacts/e2e")
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context()
            page = context.new_page()

            self._mock_event_endpoints(page=page, api_base_url=api_base_url)

            email = f"e2e-{uuid4().hex[:8]}@example.com"
            password = "e2e-password-123"

            page.goto(f"{base_url}/signup", wait_until="domcontentloaded")
            page.get_by_label("이메일").fill(email)
            page.get_by_label("비밀번호").fill(password)
            page.get_by_role("button", name="회원가입").click()
            expect(page).to_have_url(re.compile(r"/dashboard$"))
            page.screenshot(path=str(screenshots_dir / f"core-user-journey-{attempt}-auth.png"), full_page=True)

            page.get_by_label("종목코드").fill("AAPL")
            page.get_by_label("시장").select_option("US")
            page.get_by_role("button", name="추가").click()
            expect(page.get_by_text("US:AAPL")).to_be_visible()
            page.screenshot(path=str(screenshots_dir / f"core-user-journey-{attempt}-watchlist.png"), full_page=True)

            page.get_by_role("button", name=re.compile(r"US:AAPL")) .click()
            expect(page.get_by_text("Earnings beat")).to_be_visible()

            source_link = page.get_by_role("link", name="근거 원문 보기")
            expect(source_link).to_have_attribute("target", "_blank")
            href = source_link.get_attribute("href")
            self.assertIsNotNone(href)
            self.assertTrue(str(href).startswith("http"))
            page.screenshot(path=str(screenshots_dir / f"core-user-journey-{attempt}-reason.png"), full_page=True)

            context.close()
            browser.close()

    def _mock_event_endpoints(self, *, page, api_base_url: str) -> None:
        events_url = re.compile(r".*/v1/events\?size=20$")
        detail_url = re.compile(r".*/v1/events/evt-e2e$")

        page.route(
            events_url,
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=(
                    '{"items":[{"id":"evt-e2e","symbol":"AAPL","market":"US",'
                    '"change_pct":4.2,"window_minutes":5,"detected_at_utc":"2026-02-17T00:00:00Z",'
                    '"exchange_timezone":"America/New_York","session_label":"regular",'
                    '"reasons":[],"portfolio_impact":null}],"count":1,"next_cursor":null}'
                ),
            ),
        )
        page.route(
            detail_url,
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=(
                    '{"event":{"id":"evt-e2e","symbol":"AAPL","market":"US",'
                    '"change_pct":4.2,"window_minutes":5,"detected_at_utc":"2026-02-17T00:00:00Z",'
                    '"exchange_timezone":"America/New_York","session_label":"regular",'
                    '"portfolio_impact":null,'
                    '"reasons":[{"id":"reason-e2e-1","rank":1,"reason_type":"news",'
                    '"confidence_score":0.9,"summary":"Earnings beat",'
                    '"source_url":"https://example.com/earnings","published_at":"2026-02-17T00:00:00Z",'
                    '"explanation":{"weights":{},"signals":{},"score_breakdown":{"total":0.9}}}]}}'
                ),
            ),
        )


if __name__ == "__main__":
    unittest.main()
