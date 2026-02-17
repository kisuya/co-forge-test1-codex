from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
import unittest

try:
    from playwright.sync_api import expect, sync_playwright

    _PLAYWRIGHT_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime dependency
    _PLAYWRIGHT_AVAILABLE = False


class ReasonReportRevisionFlowE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.getenv("RUN_E2E") != "1":
            raise unittest.SkipTest("Set RUN_E2E=1 to run Playwright E2E tests")
        if not _PLAYWRIGHT_AVAILABLE:
            raise unittest.SkipTest("playwright is not installed")

    def test_reason_report_to_revision_user_journey(self) -> None:
        base_url = os.getenv("E2E_BASE_URL", "http://127.0.0.1:3000")
        screenshots_dir = Path("artifacts/e2e")
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                self._run_step_with_retry(
                    step_name="success-delayed",
                    run_step=lambda attempt: self._run_success_with_delayed_revision_step(
                        browser=browser,
                        base_url=base_url,
                        screenshots_dir=screenshots_dir,
                        attempt=attempt,
                    ),
                )
                self._run_step_with_retry(
                    step_name="duplicate-report",
                    run_step=lambda attempt: self._run_duplicate_report_step(
                        browser=browser,
                        base_url=base_url,
                        screenshots_dir=screenshots_dir,
                        attempt=attempt,
                    ),
                )
                self._run_step_with_retry(
                    step_name="forbidden-event",
                    run_step=lambda attempt: self._run_forbidden_event_access_step(
                        browser=browser,
                        base_url=base_url,
                        screenshots_dir=screenshots_dir,
                        attempt=attempt,
                    ),
                )
            finally:
                browser.close()

    def _run_step_with_retry(self, *, step_name: str, run_step) -> None:
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

    def _run_success_with_delayed_revision_step(
        self,
        *,
        browser,
        base_url: str,
        screenshots_dir: Path,
        attempt: int,
    ) -> None:
        event_id = "evt-success"
        reason_id = "reason-success"

        context = self._new_authenticated_context(
            browser=browser,
            user_id="user-success",
            access_token="token-success",
        )
        page = context.new_page()
        try:
            self._mock_common_dashboard_endpoints(page=page, user_id="user-success")
            self._mock_success_event_flow(page=page, event_id=event_id, reason_id=reason_id)

            page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")

            report_button = page.get_by_test_id(f"reason-report-button-{reason_id}")
            expect(report_button).to_be_visible()
            expect(page.get_by_test_id("reason-revision-empty")).to_be_visible()

            report_button.click()
            expect(page.get_by_test_id(f"reason-report-spinner-{reason_id}")).to_be_visible()
            expect(page.get_by_text("원인 신고가 접수되었습니다.")).to_be_visible()

            status_badge = page.get_by_test_id(f"reason-report-status-badge-{reason_id}")
            expect(status_badge).to_contain_text("접수됨")

            transition_items = page.get_by_test_id("reason-status-transition-list").locator("li")
            expect(transition_items).to_have_count(3)
            expect(transition_items.nth(0)).to_contain_text("접수됨")
            expect(transition_items.nth(1)).to_contain_text("검토 중")
            expect(transition_items.nth(2)).to_contain_text("정정 완료")
            expect(page.get_by_test_id("reason-revision-timeline")).to_be_visible()
            expect(page.get_by_text("근거 재검증 후 점수 조정 (2026-02-17T01:10:00Z)")).to_be_visible()
            expect(page.get_by_text("confidence 0.82 → 0.61 (-0.21)")).to_be_visible()

            page.screenshot(
                path=str(screenshots_dir / f"reason-report-revision-flow-{attempt}-success-delayed.png"),
                full_page=True,
            )
        finally:
            context.close()

    def _run_duplicate_report_step(
        self,
        *,
        browser,
        base_url: str,
        screenshots_dir: Path,
        attempt: int,
    ) -> None:
        event_id = "evt-duplicate"
        reason_id = "reason-duplicate"

        context = self._new_authenticated_context(
            browser=browser,
            user_id="user-duplicate",
            access_token="token-duplicate",
        )
        page = context.new_page()
        try:
            self._mock_common_dashboard_endpoints(page=page, user_id="user-duplicate")
            self._mock_duplicate_event_flow(page=page, event_id=event_id, reason_id=reason_id)

            page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")

            report_button = page.get_by_test_id(f"reason-report-button-{reason_id}")
            expect(report_button).to_be_visible()
            report_button.click()

            expect(page.get_by_test_id(f"reason-report-spinner-{reason_id}")).to_be_visible()
            expect(page.get_by_text("이미 접수된 신고가 있어 처리 결과를 기다려 주세요.")).to_be_visible()
            expect(report_button).to_be_enabled()

            page.screenshot(
                path=str(screenshots_dir / f"reason-report-revision-flow-{attempt}-duplicate-report.png"),
                full_page=True,
            )
        finally:
            context.close()

    def _run_forbidden_event_access_step(
        self,
        *,
        browser,
        base_url: str,
        screenshots_dir: Path,
        attempt: int,
    ) -> None:
        event_id = "evt-forbidden"

        context = self._new_authenticated_context(
            browser=browser,
            user_id="user-forbidden",
            access_token="token-forbidden",
        )
        page = context.new_page()
        try:
            self._mock_common_dashboard_endpoints(page=page, user_id="user-forbidden")
            self._mock_forbidden_event_flow(page=page, event_id=event_id)

            page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")

            expect(page.get_by_role("alert")).to_contain_text("Forbidden resource access")
            expect(page.get_by_role("button", name="원인 신고")).to_have_count(0)

            page.screenshot(
                path=str(screenshots_dir / f"reason-report-revision-flow-{attempt}-forbidden-event.png"),
                full_page=True,
            )
        finally:
            context.close()

    def _new_authenticated_context(self, *, browser, user_id: str, access_token: str):
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.add_init_script(
            (
                "window.localStorage.setItem("
                "'oh-my-stock.auth.session',"
                f"JSON.stringify({{userId: '{user_id}', accessToken: '{access_token}'}}));"
            )
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
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body='{"items":[],"total":0,"page":1,"size":20}',
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

    def _mock_success_event_flow(self, *, page, event_id: str, reason_id: str) -> None:
        revision_request_count = {"count": 0}

        page.route(
            re.compile(r".*/v1/events\?size=20$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(self._events_payload(event_id=event_id)),
            ),
        )
        page.route(
            re.compile(rf".*/v1/events/{event_id}$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"event": self._event_detail_payload(event_id=event_id, reason_id=reason_id)}),
            ),
        )

        def handle_revision_history(route) -> None:
            revision_request_count["count"] += 1
            if revision_request_count["count"] == 1:
                route.fulfill(
                    status=404,
                    content_type="application/json",
                    body=(
                        '{"code":"reason_revision_history_not_found",'
                        '"message":"Reason revision history not found",'
                        f'"details":{{"event_id":"{event_id}"}}}}'
                    ),
                )
                return
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(self._revision_history_payload(event_id=event_id, reason_id=reason_id)),
            )

        page.route(re.compile(rf".*/v1/events/{event_id}/reason-revisions$"), handle_revision_history)

        def handle_reason_report(route) -> None:
            time.sleep(0.25)
            route.fulfill(
                status=201,
                content_type="application/json",
                body='{"report_id":"report-1","status":"received","queued":true}',
            )

        page.route(re.compile(rf".*/v1/events/{event_id}/reason-reports$"), handle_reason_report)

    def _mock_duplicate_event_flow(self, *, page, event_id: str, reason_id: str) -> None:
        page.route(
            re.compile(r".*/v1/events\?size=20$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(self._events_payload(event_id=event_id)),
            ),
        )
        page.route(
            re.compile(rf".*/v1/events/{event_id}$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"event": self._event_detail_payload(event_id=event_id, reason_id=reason_id)}),
            ),
        )
        page.route(
            re.compile(rf".*/v1/events/{event_id}/reason-revisions$"),
            lambda route: route.fulfill(
                status=404,
                content_type="application/json",
                body=(
                    '{"code":"reason_revision_history_not_found",'
                    '"message":"Reason revision history not found",'
                    f'"details":{{"event_id":"{event_id}"}}}}'
                ),
            ),
        )

        def handle_duplicate_report(route) -> None:
            time.sleep(0.15)
            route.fulfill(
                status=400,
                content_type="application/json",
                body=(
                    '{"code":"duplicate_reason_report",'
                    '"message":"An open reason report already exists for this reason",'
                    f'"details":{{"event_id":"{event_id}","reason_id":"{reason_id}"}}}}'
                ),
            )

        page.route(re.compile(rf".*/v1/events/{event_id}/reason-reports$"), handle_duplicate_report)

    def _mock_forbidden_event_flow(self, *, page, event_id: str) -> None:
        page.route(
            re.compile(r".*/v1/events\?size=20$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(self._events_payload(event_id=event_id)),
            ),
        )
        page.route(
            re.compile(rf".*/v1/events/{event_id}$"),
            lambda route: route.fulfill(
                status=403,
                content_type="application/json",
                body='{"code":"forbidden","message":"Forbidden resource access","retryable":false}',
            ),
        )

    def _events_payload(self, *, event_id: str) -> dict[str, object]:
        return {
            "items": [
                {
                    "id": event_id,
                    "symbol": "AAPL",
                    "market": "US",
                    "change_pct": 4.2,
                    "window_minutes": 5,
                    "detected_at_utc": "2026-02-17T01:00:00Z",
                    "exchange_timezone": "America/New_York",
                    "session_label": "regular",
                    "reasons": [],
                    "portfolio_impact": None,
                }
            ],
            "count": 1,
            "next_cursor": None,
        }

    def _event_detail_payload(self, *, event_id: str, reason_id: str) -> dict[str, object]:
        return {
            "id": event_id,
            "symbol": "AAPL",
            "market": "US",
            "change_pct": 4.2,
            "window_minutes": 5,
            "detected_at_utc": "2026-02-17T01:00:00Z",
            "exchange_timezone": "America/New_York",
            "session_label": "regular",
            "portfolio_impact": None,
            "reason_status": "verified",
            "confidence_breakdown": {
                "weights": {"source_reliability": 0.4, "event_match": 0.3, "time_proximity": 0.3},
                "signals": {"source_reliability": 0.9, "event_match": 0.8, "time_proximity": 0.7},
                "score_breakdown": {
                    "source_reliability": 0.36,
                    "event_match": 0.24,
                    "time_proximity": 0.21,
                    "total": 0.81,
                },
            },
            "explanation_text": "confidence 계산 근거 설명",
            "revision_hint": None,
            "reasons": [
                {
                    "id": reason_id,
                    "rank": 1,
                    "reason_type": "filing",
                    "confidence_score": 0.81,
                    "summary": "8-K filed before move",
                    "source_url": "https://sec.example/8k",
                    "published_at": "2026-02-17T00:59:00Z",
                    "explanation": {},
                }
            ],
        }

    def _revision_history_payload(self, *, event_id: str, reason_id: str) -> dict[str, object]:
        return {
            "event_id": event_id,
            "revision_history": [
                {
                    "id": "rev-1",
                    "report_id": "report-1",
                    "event_id": event_id,
                    "reason_id": reason_id,
                    "revision_reason": "근거 재검증 후 점수 조정",
                    "confidence_before": 0.82,
                    "confidence_after": 0.61,
                    "revised_at_utc": "2026-02-17T01:10:00Z",
                }
            ],
            "status_transitions": [
                {
                    "report_id": "report-1",
                    "event_id": event_id,
                    "reason_id": reason_id,
                    "from_status": None,
                    "to_status": "received",
                    "changed_at_utc": "2026-02-17T01:02:00Z",
                    "note": None,
                },
                {
                    "report_id": "report-1",
                    "event_id": event_id,
                    "reason_id": reason_id,
                    "from_status": "received",
                    "to_status": "reviewed",
                    "changed_at_utc": "2026-02-17T01:06:00Z",
                    "note": "triaged",
                },
                {
                    "report_id": "report-1",
                    "event_id": event_id,
                    "reason_id": reason_id,
                    "from_status": "reviewed",
                    "to_status": "resolved",
                    "changed_at_utc": "2026-02-17T01:10:00Z",
                    "note": "resolved",
                },
            ],
            "count": 1,
            "meta": {
                "has_revision_history": True,
                "latest_status": "resolved",
            },
        }


if __name__ == "__main__":
    unittest.main()
