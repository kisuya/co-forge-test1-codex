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


class EvidenceCompareFlowE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.getenv("RUN_E2E") != "1":
            raise unittest.SkipTest("Set RUN_E2E=1 to run Playwright E2E tests")
        if not _PLAYWRIGHT_AVAILABLE:
            raise unittest.SkipTest("playwright is not installed")

    def test_evidence_compare_flow_ready_unavailable_link_and_mobile(self) -> None:
        base_url = os.getenv("E2E_BASE_URL", "http://127.0.0.1:3000")
        screenshots_dir = Path("artifacts/e2e")
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                self._run_step_with_retry(
                    step_name="desktop-ready-unavailable",
                    run_step=lambda attempt: self._run_desktop_ready_unavailable_step(
                        browser=browser,
                        base_url=base_url,
                        screenshots_dir=screenshots_dir,
                        attempt=attempt,
                    ),
                )
                self._run_step_with_retry(
                    step_name="mobile-compact",
                    run_step=lambda attempt: self._run_mobile_compact_layout_step(
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
            raise RuntimeError(f"E2E step failed: {step_name}") from errors[-1]

    def _run_desktop_ready_unavailable_step(
        self,
        *,
        browser,
        base_url: str,
        screenshots_dir: Path,
        attempt: int,
    ) -> None:
        ready_event_id = "evt-compare-ready"
        unavailable_event_id = "evt-compare-unavailable"

        context = self._new_authenticated_context(
            browser=browser,
            user_id="user-compare-desktop",
            access_token="token-compare-desktop",
            viewport={"width": 1440, "height": 1000},
        )
        page = context.new_page()

        try:
            self._mock_common_dashboard_endpoints(page=page, user_id="user-compare-desktop")
            self._mock_evidence_compare_flow(
                page=page,
                ready_event_id=ready_event_id,
                unavailable_event_id=unavailable_event_id,
            )
            context.route(
                re.compile(r"https://news\\.example/positive$"),
                lambda route: route.fulfill(
                    status=200,
                    content_type="text/html",
                    body="<html><body><h1 data-testid='external-article'>positive article</h1></body></html>",
                ),
            )

            page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")

            expect(page.get_by_test_id("evidence-compare-error")).to_contain_text("일부 출처 응답 지연")
            expect(page.get_by_role("button", name="비교 카드 다시 시도")).to_be_visible()
            expect(page.get_by_test_id("reason-status-badge")).to_contain_text("검증 완료")
            page.screenshot(
                path=str(screenshots_dir / f"evidence-compare-flow-{attempt}-desktop-retryable-error.png"),
                full_page=True,
            )

            page.get_by_role("button", name="비교 카드 다시 시도").click()
            expect(page.get_by_test_id("evidence-compare-ready")).to_be_visible()
            expect(page.get_by_test_id("evidence-compare-axis-positive")).to_be_visible()
            expect(page.get_by_test_id("evidence-compare-axis-negative")).to_be_visible()
            expect(page.get_by_test_id("evidence-compare-axis-uncertain")).to_be_visible()
            expect(page.get_by_text("출처 균형을 유지해 해석 편향을 줄여보세요.")).to_be_visible()
            page.screenshot(
                path=str(screenshots_dir / f"evidence-compare-flow-{attempt}-desktop-ready.png"),
                full_page=True,
            )

            positive_axis = page.get_by_test_id("evidence-compare-axis-positive")
            source_link = positive_axis.get_by_role("link", name="원문 보기").first
            with context.expect_page() as popup_info:
                source_link.click()
            popup = popup_info.value
            popup.wait_for_load_state("domcontentloaded")
            expect(popup).to_have_url(re.compile(r"https://news\\.example/positive$"))
            expect(popup.locator("[data-testid='external-article']")).to_contain_text("positive article")
            popup.close()

            page.get_by_role("button", name=re.compile(r"US:TSLA")).click()
            expect(page.get_by_test_id("evidence-compare-unavailable")).to_be_visible()
            expect(page.get_by_test_id("evidence-compare-unavailable")).to_contain_text("비교 근거 부족")
            expect(page.get_by_test_id("evidence-compare-unavailable")).to_contain_text("긍정/부정 축이 불균형")
            expect(page.get_by_text("접근 불가 링크")).to_be_visible()
            expect(page.get_by_test_id("reason-status-badge")).to_contain_text("근거 수집 중")
            page.screenshot(
                path=str(screenshots_dir / f"evidence-compare-flow-{attempt}-desktop-unavailable.png"),
                full_page=True,
            )
        finally:
            context.close()

    def _run_mobile_compact_layout_step(
        self,
        *,
        browser,
        base_url: str,
        screenshots_dir: Path,
        attempt: int,
    ) -> None:
        mobile_event_id = "evt-compare-mobile"

        context = self._new_authenticated_context(
            browser=browser,
            user_id="user-compare-mobile",
            access_token="token-compare-mobile",
            viewport={"width": 390, "height": 844},
        )
        page = context.new_page()

        try:
            self._mock_common_dashboard_endpoints(page=page, user_id="user-compare-mobile")
            self._mock_mobile_evidence_compare_flow(page=page, event_id=mobile_event_id)

            page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")

            expect(page.get_by_test_id("evidence-compare-ready")).to_be_visible()
            compare_card = page.get_by_test_id("evidence-compare-card")
            expect(compare_card).to_be_visible()
            compare_card_box = compare_card.bounding_box()
            self.assertIsNotNone(compare_card_box)
            assert compare_card_box is not None  # satisfy type checker
            self.assertLessEqual(compare_card_box["x"] + compare_card_box["width"], 390)

            for axis in ("positive", "negative", "uncertain"):
                axis_section = page.get_by_test_id(f"evidence-compare-axis-{axis}")
                expect(axis_section).to_be_visible()
                axis_box = axis_section.bounding_box()
                self.assertIsNotNone(axis_box)
                assert axis_box is not None  # satisfy type checker
                self.assertLessEqual(axis_box["x"] + axis_box["width"], 390)

            page.screenshot(
                path=str(screenshots_dir / f"evidence-compare-flow-{attempt}-mobile-compact.png"),
                full_page=True,
            )
        finally:
            context.close()

    def _new_authenticated_context(self, *, browser, user_id: str, access_token: str, viewport: dict[str, int]):
        context = browser.new_context(viewport=viewport)
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
                body='{"items":[],"unread_count":0}',
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

    def _mock_evidence_compare_flow(self, *, page, ready_event_id: str, unavailable_event_id: str) -> None:
        compare_attempt_count = {"count": 0}

        page.route(
            re.compile(r".*/v1/events\?size=20$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "items": [
                            self._event_summary(event_id=ready_event_id, symbol="AAPL", change_pct=5.12),
                            self._event_summary(event_id=unavailable_event_id, symbol="TSLA", change_pct=-3.48),
                        ],
                        "count": 2,
                        "next_cursor": None,
                    }
                ),
            ),
        )

        def handle_event_detail(route) -> None:
            path = route.request.url.split("?")[0]
            if path.endswith(f"/v1/events/{ready_event_id}"):
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "event": self._event_detail(
                                event_id=ready_event_id,
                                symbol="AAPL",
                                reason_status="verified",
                                reason_summary="실적 서프라이즈 이후 매수세 확대",
                                reason_source_url="https://news.example/reason-ready",
                            )
                        }
                    ),
                )
                return

            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "event": self._event_detail(
                            event_id=unavailable_event_id,
                            symbol="TSLA",
                            reason_status="collecting_evidence",
                            reason_summary="상충 근거 수집 중",
                            reason_source_url="https://news.example/reason-unavailable",
                        )
                    }
                ),
            )

        page.route(re.compile(r".*/v1/events/(evt-compare-ready|evt-compare-unavailable)$"), handle_event_detail)

        page.route(
            re.compile(r".*/v1/events/(evt-compare-ready|evt-compare-unavailable)/reason-revisions$"),
            lambda route: route.fulfill(
                status=404,
                content_type="application/json",
                body='{"code":"reason_revision_history_not_found","message":"Reason revision history not found","retryable":false}',
            ),
        )

        def handle_compare(route) -> None:
            path = route.request.url.split("?")[0]
            if path.endswith(f"/v1/events/{ready_event_id}/evidence-compare"):
                compare_attempt_count["count"] += 1
                if compare_attempt_count["count"] == 1:
                    route.fulfill(
                        status=503,
                        content_type="application/json",
                        body='{"code":"compare_source_timeout","message":"일부 출처 응답 지연으로 비교 근거를 다시 수집 중입니다.","retryable":true}',
                    )
                    return
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(self._ready_compare_payload(event_id=ready_event_id)),
                )
                return

            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(self._unavailable_compare_payload(event_id=unavailable_event_id)),
            )

        page.route(re.compile(r".*/v1/events/(evt-compare-ready|evt-compare-unavailable)/evidence-compare$"), handle_compare)

    def _mock_mobile_evidence_compare_flow(self, *, page, event_id: str) -> None:
        page.route(
            re.compile(r".*/v1/events\?size=20$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "items": [self._event_summary(event_id=event_id, symbol="NVDA", change_pct=4.66)],
                        "count": 1,
                        "next_cursor": None,
                    }
                ),
            ),
        )
        page.route(
            re.compile(r".*/v1/events/evt-compare-mobile$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "event": self._event_detail(
                            event_id=event_id,
                            symbol="NVDA",
                            reason_status="verified",
                            reason_summary="AI 수요 기대가 지속",
                            reason_source_url="https://news.example/reason-mobile",
                        )
                    }
                ),
            ),
        )
        page.route(
            re.compile(r".*/v1/events/evt-compare-mobile/reason-revisions$"),
            lambda route: route.fulfill(
                status=404,
                content_type="application/json",
                body='{"code":"reason_revision_history_not_found","message":"Reason revision history not found","retryable":false}',
            ),
        )
        page.route(
            re.compile(r".*/v1/events/evt-compare-mobile/evidence-compare$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(self._ready_compare_payload(event_id=event_id)),
            ),
        )

    def _event_summary(self, *, event_id: str, symbol: str, change_pct: float) -> dict[str, object]:
        return {
            "id": event_id,
            "symbol": symbol,
            "market": "US",
            "change_pct": change_pct,
            "window_minutes": 5,
            "detected_at_utc": "2026-02-18T01:00:00Z",
            "exchange_timezone": "America/New_York",
            "session_label": "regular",
            "reasons": [],
            "portfolio_impact": None,
        }

    def _event_detail(
        self,
        *,
        event_id: str,
        symbol: str,
        reason_status: str,
        reason_summary: str,
        reason_source_url: str,
    ) -> dict[str, object]:
        return {
            "id": event_id,
            "symbol": symbol,
            "market": "US",
            "change_pct": 4.11,
            "window_minutes": 5,
            "detected_at_utc": "2026-02-18T01:00:00Z",
            "exchange_timezone": "America/New_York",
            "session_label": "regular",
            "portfolio_impact": None,
            "reason_status": reason_status,
            "reasons": [
                {
                    "id": f"reason-{event_id}",
                    "rank": 1,
                    "reason_type": "news",
                    "confidence_score": 0.78,
                    "summary": reason_summary,
                    "source_url": reason_source_url,
                    "published_at": "2026-02-18T01:02:00Z",
                    "explanation": {},
                }
            ],
        }

    def _ready_compare_payload(self, *, event_id: str) -> dict[str, object]:
        return {
            "event_id": event_id,
            "status": "ready",
            "compare_ready": True,
            "fallback_reason": None,
            "bias_warning": "출처 균형을 유지해 해석 편향을 줄여보세요.",
            "axes": {
                "positive": [
                    {
                        "id": f"{event_id}-pos-1",
                        "reason_type": "news",
                        "summary": "가이던스 상향과 매출 성장",
                        "source_url": "https://news.example/positive",
                        "published_at": "2026-02-18T01:05:00Z",
                        "axis": "positive",
                    }
                ],
                "negative": [
                    {
                        "id": f"{event_id}-neg-1",
                        "reason_type": "news",
                        "summary": "단기 수급 과열 경고",
                        "source_url": "https://news.example/negative",
                        "published_at": "2026-02-18T01:04:00Z",
                        "axis": "negative",
                    }
                ],
                "uncertain": [
                    {
                        "id": f"{event_id}-unc-1",
                        "reason_type": "news",
                        "summary": "해석이 엇갈리는 코멘트",
                        "source_url": "https://news.example/uncertain",
                        "published_at": "2026-02-18T01:03:00Z",
                        "axis": "uncertain",
                    }
                ],
            },
            "axis_counts": {
                "positive": 1,
                "negative": 1,
                "uncertain": 1,
            },
            "comparable_axis_count": 3,
            "evidence_count": 3,
            "dropped_missing_metadata_count": 0,
            "generated_at_utc": "2026-02-18T01:06:00Z",
            "sources": [
                {
                    "axis": "positive",
                    "source_url": "https://news.example/positive",
                    "published_at": "2026-02-18T01:05:00Z",
                    "summary": "가이던스 상향과 매출 성장",
                },
                {
                    "axis": "negative",
                    "source_url": "https://news.example/negative",
                    "published_at": "2026-02-18T01:04:00Z",
                    "summary": "단기 수급 과열 경고",
                },
                {
                    "axis": "uncertain",
                    "source_url": "https://news.example/uncertain",
                    "published_at": "2026-02-18T01:03:00Z",
                    "summary": "해석이 엇갈리는 코멘트",
                },
            ],
        }

    def _unavailable_compare_payload(self, *, event_id: str) -> dict[str, object]:
        return {
            "event_id": event_id,
            "status": "compare_unavailable",
            "compare_ready": False,
            "fallback_reason": "axis_imbalance",
            "bias_warning": "상충 근거가 충분하지 않아 단정형 결론을 제공하지 않습니다.",
            "axes": {
                "positive": [],
                "negative": [],
                "uncertain": [
                    {
                        "id": f"{event_id}-unc-1",
                        "reason_type": "news",
                        "summary": "출처 일부 미응답으로 불확실 축만 유지",
                        "source_url": "ftp://blocked.example/compare",
                        "published_at": "2026-02-18T01:07:00Z",
                        "axis": "uncertain",
                    }
                ],
            },
            "axis_counts": {
                "positive": 0,
                "negative": 0,
                "uncertain": 1,
            },
            "comparable_axis_count": 1,
            "evidence_count": 1,
            "dropped_missing_metadata_count": 0,
            "generated_at_utc": "2026-02-18T01:08:00Z",
            "sources": [
                {
                    "axis": "uncertain",
                    "source_url": "ftp://blocked.example/compare",
                    "published_at": "2026-02-18T01:07:00Z",
                    "summary": "출처 일부 미응답으로 불확실 축만 유지",
                }
            ],
        }


if __name__ == "__main__":
    unittest.main()
