#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("JWT_SECRET", "oh-my-stock-dev-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/oh-my-stock-dev.db")

from apps.api.main import app  # noqa: E402
from apps.domain.briefs import brief_inbox_store  # noqa: E402
from apps.domain.events import PriceEvent, price_event_store, to_utc_iso  # noqa: E402
from apps.domain.feedback import reason_feedback_store  # noqa: E402
from apps.domain.notifications import notification_store  # noqa: E402
from apps.domain.passwords import hash_password  # noqa: E402
from apps.domain.portfolio_holdings_db import portfolio_holdings_db_service  # noqa: E402
from apps.domain.reason_reports import reason_report_store  # noqa: E402
from apps.domain.reasons import event_reason_store  # noqa: E402
from apps.domain.user_thresholds import user_threshold_store  # noqa: E402
from apps.domain.watchlists_db import watchlist_db_service  # noqa: E402
from apps.infra.models import create_core_schema, execute_statement, fetch_all  # noqa: E402
from apps.infra.postgres import get_database_runtime  # noqa: E402
from apps.worker.reason_reevaluation_queue import reason_reevaluation_queue  # noqa: E402

_DEFAULT_API_HOST = "127.0.0.1"
_DEFAULT_API_PORT = 18001
_DEFAULT_EMAIL = "kisu@test.com"
_DEFAULT_PASSWORD = "thekain007"
_DEFAULT_CORS_ORIGINS = (
    "http://127.0.0.1:13002",
    "http://localhost:13002",
    "http://127.0.0.1:13000",
    "http://localhost:13000",
)


@dataclass(frozen=True)
class AdapterConfig:
    host: str
    port: int
    email: str
    password: str
    cors_origins: tuple[str, ...]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _confidence_from_signals(signals: dict[str, float]) -> tuple[float, dict[str, Any]]:
    weights = {
        "source_reliability": 0.35,
        "event_match": 0.40,
        "time_proximity": 0.25,
    }
    score_breakdown = {
        "source_reliability": round(weights["source_reliability"] * signals["source_reliability"], 4),
        "event_match": round(weights["event_match"] * signals["event_match"], 4),
        "time_proximity": round(weights["time_proximity"] * signals["time_proximity"], 4),
    }
    total = round(
        score_breakdown["source_reliability"]
        + score_breakdown["event_match"]
        + score_breakdown["time_proximity"],
        4,
    )
    explanation = {
        "weights": weights,
        "signals": signals,
        "score_breakdown": {**score_breakdown, "total": total},
        "explanation_text": "출처 신뢰도·이벤트 일치도·시간 근접도를 결합해 confidence를 계산했습니다.",
    }
    return total, explanation


def _ensure_user(email: str, password: str) -> str:
    runtime = get_database_runtime()
    create_core_schema(runtime.engine)

    rows = fetch_all(runtime.engine, "SELECT id FROM users WHERE email = ? LIMIT 1", (email,))
    if rows:
        user_id = str(rows[0][0])
        execute_statement(
            runtime.engine,
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(password), user_id),
        )
        return user_id

    import uuid

    user_id = str(uuid.uuid4())
    execute_statement(
        runtime.engine,
        "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
        (user_id, email, hash_password(password)),
    )
    return user_id


def _clear_user_state(user_id: str) -> None:
    runtime = get_database_runtime()
    create_core_schema(runtime.engine)

    execute_statement(runtime.engine, "DELETE FROM notifications WHERE user_id = ?", (user_id,))
    execute_statement(
        runtime.engine,
        "DELETE FROM event_reasons WHERE event_id IN (SELECT id FROM price_events WHERE user_id = ?)",
        (user_id,),
    )
    execute_statement(runtime.engine, "DELETE FROM price_events WHERE user_id = ?", (user_id,))
    execute_statement(runtime.engine, "DELETE FROM portfolio_holdings WHERE user_id = ?", (user_id,))
    execute_statement(runtime.engine, "DELETE FROM watchlist_items WHERE user_id = ?", (user_id,))
    execute_statement(runtime.engine, "DELETE FROM watchlists WHERE user_id = ?", (user_id,))


def seed_data(*, email: str, password: str) -> dict[str, Any]:
    user_id = _ensure_user(email=email, password=password)
    _clear_user_state(user_id=user_id)

    # In-memory stores used by API handlers.
    price_event_store.clear()
    event_reason_store.clear()
    reason_feedback_store.clear()
    reason_report_store.clear()
    reason_reevaluation_queue.clear()
    brief_inbox_store.clear()
    user_threshold_store.clear()
    notification_store.clear()

    watchlist_symbols = [
        ("AAPL", "US"),
        ("MSFT", "US"),
        ("NVDA", "US"),
        ("TSLA", "US"),
        ("005930", "KR"),
        ("000660", "KR"),
    ]
    for symbol, market in watchlist_symbols:
        watchlist_db_service.create_item(symbol=symbol, market=market, user_id=user_id)

    portfolio_holdings_db_service.upsert_holding(user_id=user_id, symbol="AAPL", qty=12, avg_price=173.4)
    portfolio_holdings_db_service.upsert_holding(user_id=user_id, symbol="NVDA", qty=5, avg_price=812.0)
    portfolio_holdings_db_service.upsert_holding(user_id=user_id, symbol="005930", qty=18, avg_price=74200)

    now = _utc_now()
    events = [
        PriceEvent(
            id="evt-us-aapl-001",
            symbol="AAPL",
            market="US",
            change_pct=5.42,
            window_minutes=5,
            detected_at_utc=to_utc_iso(now - timedelta(minutes=18)),
            exchange_timezone="America/New_York",
            session_label="regular",
        ),
        PriceEvent(
            id="evt-us-nvda-002",
            symbol="NVDA",
            market="US",
            change_pct=-4.31,
            window_minutes=5,
            detected_at_utc=to_utc_iso(now - timedelta(minutes=34)),
            exchange_timezone="America/New_York",
            session_label="regular",
        ),
        PriceEvent(
            id="evt-kr-005930-003",
            symbol="005930",
            market="KR",
            change_pct=3.08,
            window_minutes=5,
            detected_at_utc=to_utc_iso(now - timedelta(hours=3, minutes=12)),
            exchange_timezone="Asia/Seoul",
            session_label="regular",
        ),
        PriceEvent(
            id="evt-us-tsla-004",
            symbol="TSLA",
            market="US",
            change_pct=6.77,
            window_minutes=5,
            detected_at_utc=to_utc_iso(now - timedelta(hours=6, minutes=5)),
            exchange_timezone="America/New_York",
            session_label="after-hours",
        ),
    ]

    runtime = get_database_runtime()
    create_core_schema(runtime.engine)
    for event in events:
        direction = "up" if event.change_pct >= 0 else "down"
        price_event_store.save(event, direction=direction)
        execute_statement(
            runtime.engine,
            """
            INSERT INTO price_events (id, user_id, symbol, market, change_pct, window_minutes, detected_at_utc, session_label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                user_id,
                event.symbol,
                event.market,
                event.change_pct,
                event.window_minutes,
                event.detected_at_utc,
                event.session_label,
            ),
        )

    reason_specs: dict[str, list[dict[str, Any]]] = {
        "evt-us-aapl-001": [
            {
                "rank": 1,
                "reason_type": "earnings",
                "summary": "분기 실적이 시장 예상치를 상회했고 가이던스가 상향됐습니다.",
                "source_url": "https://example.com/news/aapl-earnings-beat",
                "published_at": to_utc_iso(now - timedelta(minutes=35)),
                "signals": {"source_reliability": 0.92, "event_match": 0.93, "time_proximity": 0.88},
            },
            {
                "rank": 2,
                "reason_type": "analyst_upgrade",
                "summary": "주요 증권사가 목표가를 상향 조정했습니다.",
                "source_url": "https://example.com/news/aapl-upgrade",
                "published_at": to_utc_iso(now - timedelta(minutes=55)),
                "signals": {"source_reliability": 0.82, "event_match": 0.76, "time_proximity": 0.72},
            },
            {
                "rank": 3,
                "reason_type": "macro",
                "summary": "금리 기대 변화로 기술주 전반 변동성이 확대됐습니다.",
                "source_url": "https://example.com/news/macro-volatility",
                "published_at": to_utc_iso(now - timedelta(minutes=68)),
                "signals": {"source_reliability": 0.74, "event_match": 0.58, "time_proximity": 0.62},
            },
        ],
        "evt-us-nvda-002": [
            {
                "rank": 1,
                "reason_type": "regulatory_risk",
                "summary": "규제 이슈와 조사 가능성 보도가 악재로 반영됐습니다.",
                "source_url": "https://example.com/news/nvda-regulatory-risk",
                "published_at": to_utc_iso(now - timedelta(minutes=48)),
                "signals": {"source_reliability": 0.87, "event_match": 0.91, "time_proximity": 0.86},
            },
            {
                "rank": 2,
                "reason_type": "supply_chain",
                "summary": "공급망 지연 리스크가 재부각되었습니다.",
                "source_url": "https://example.com/news/nvda-supply-chain",
                "published_at": to_utc_iso(now - timedelta(hours=1, minutes=12)),
                "signals": {"source_reliability": 0.77, "event_match": 0.71, "time_proximity": 0.69},
            },
        ],
        "evt-kr-005930-003": [
            {
                "rank": 1,
                "reason_type": "demand_recovery",
                "summary": "메모리 수요 회복 기대와 실적 개선 전망이 반영됐습니다.",
                "source_url": "https://example.com/news/005930-demand-recovery",
                "published_at": to_utc_iso(now - timedelta(hours=3, minutes=35)),
                "signals": {"source_reliability": 0.85, "event_match": 0.88, "time_proximity": 0.82},
            },
        ],
        "evt-us-tsla-004": [
            {
                "rank": 1,
                "reason_type": "delivery_outlook",
                "summary": "인도량 가이던스 개선 기대가 장후반 강세를 이끌었습니다.",
                "source_url": "https://example.com/news/tsla-delivery-outlook",
                "published_at": to_utc_iso(now - timedelta(hours=6, minutes=28)),
                "signals": {"source_reliability": 0.79, "event_match": 0.84, "time_proximity": 0.75},
            },
            {
                "rank": 2,
                "reason_type": "short_covering",
                "summary": "공매도 숏커버링 수요가 급등 변동성을 키웠습니다.",
                "source_url": "https://example.com/news/tsla-short-cover",
                "published_at": to_utc_iso(now - timedelta(hours=6, minutes=44)),
                "signals": {"source_reliability": 0.68, "event_match": 0.64, "time_proximity": 0.71},
            },
        ],
    }

    reasons_by_event: dict[str, list[Any]] = {}
    for event_id, specs in reason_specs.items():
        built_reasons = []
        for spec in specs:
            confidence_score, explanation = _confidence_from_signals(spec["signals"])
            reason = event_reason_store.build_reason(
                event_id=event_id,
                rank=spec["rank"],
                reason_type=spec["reason_type"],
                confidence_score=confidence_score,
                summary=spec["summary"],
                source_url=spec["source_url"],
                published_at=spec["published_at"],
                explanation=explanation,
            )
            built_reasons.append(reason)
            execute_statement(
                runtime.engine,
                """
                INSERT INTO event_reasons (id, event_id, rank, reason_type, confidence_score, summary, source_url, published_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reason.id,
                    reason.event_id,
                    reason.rank,
                    reason.reason_type,
                    reason.confidence_score,
                    reason.summary,
                    reason.source_url,
                    reason.published_at,
                ),
            )
        event_reason_store.replace_event_reasons(event_id, built_reasons)
        reasons_by_event[event_id] = built_reasons

    # Keep notification tuples unique by (user_id, event_id, channel).
    notifications = [
        ("noti-inapp-001", "evt-us-aapl-001", "in_app", "unread", "AAPL 급등 이벤트 원인 업데이트"),
        ("noti-inapp-002", "evt-us-nvda-002", "in_app", "cooldown", "NVDA 급락 알림 쿨다운 적용 중"),
        ("noti-inapp-003", "evt-kr-005930-003", "in_app", "read", "005930 원인 카드가 갱신되었습니다"),
        ("noti-email-001", "evt-us-tsla-004", "email", "sent", "TSLA 급등 브리프 메일 발송 완료"),
    ]
    for index, (notification_id, event_id, channel, status, message) in enumerate(notifications):
        sent_at_utc = to_utc_iso(now - timedelta(minutes=index * 11 + 5))
        execute_statement(
            runtime.engine,
            """
            INSERT INTO notifications (id, user_id, event_id, channel, status, message, sent_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (notification_id, user_id, event_id, channel, status, message, sent_at_utc),
        )

    user_threshold_store.set_threshold(user_id=user_id, window_minutes=5, threshold_pct=2.8)
    user_threshold_store.set_threshold(user_id=user_id, window_minutes=1440, threshold_pct=6.5)

    brief_inbox_store.upsert_brief(
        brief_id="brief-pre-001",
        user_id=user_id,
        brief_type="pre_market",
        title="개장 전 핵심 브리프",
        summary="미국 대형주와 국내 반도체 중심으로 변동성 신호가 포착됐습니다.",
        generated_at_utc=now - timedelta(minutes=22),
        markets=["US", "KR"],
        fallback_reason=None,
        status="unread",
        items=[
            {
                "event_id": "evt-us-aapl-001",
                "symbol": "AAPL",
                "market": "US",
                "summary": "실적 상회 및 가이던스 상향 영향",
                "event_detail_url": "http://127.0.0.1:13002/dashboard",
                "source_url": "https://example.com/news/aapl-earnings-beat",
            },
            {
                "event_id": "evt-kr-005930-003",
                "symbol": "005930",
                "market": "KR",
                "summary": "메모리 업황 개선 기대 반영",
                "event_detail_url": "http://127.0.0.1:13002/dashboard",
                "source_url": "https://example.com/news/005930-demand-recovery",
            },
        ],
    )
    brief_inbox_store.upsert_brief(
        brief_id="brief-post-001",
        user_id=user_id,
        brief_type="post_close",
        title="장마감 요약 브리프",
        summary="장마감 이후 변동성이 큰 이벤트를 정리했습니다.",
        generated_at_utc=now - timedelta(hours=1, minutes=10),
        markets=["US"],
        fallback_reason="partial_aggregation",
        status="read",
        items=[
            {
                "event_id": "evt-us-tsla-004",
                "symbol": "TSLA",
                "market": "US",
                "summary": "장후반 숏커버링 수요로 급등",
                "event_detail_url": "http://127.0.0.1:13002/dashboard",
                "source_url": "https://example.com/news/tsla-short-cover",
            }
        ],
    )

    aapl_reason = reasons_by_event["evt-us-aapl-001"][0]
    nvda_reason = reasons_by_event["evt-us-nvda-002"][0]
    reason_feedback_store.submit(
        user_id=user_id,
        event_id="evt-us-aapl-001",
        reason_id=aapl_reason.id,
        feedback="helpful",
    )
    reason_feedback_store.submit(
        user_id=user_id,
        event_id="evt-us-nvda-002",
        reason_id=nvda_reason.id,
        feedback="not_helpful",
    )

    report = reason_report_store.submit(
        user_id=user_id,
        event_id="evt-us-aapl-001",
        reason_id=aapl_reason.id,
        report_type="outdated_information",
        note="수치가 최신 공시와 달라 보입니다.",
    )
    reason_report_store.mark_reviewed(report_id=report.id, note="검토 시작")
    reason_report_store.resolve_report(
        report_id=report.id,
        revision_reason="source_refresh",
        confidence_before=0.82,
        confidence_after=0.68,
        note="최신 공시 반영으로 confidence 재조정",
    )

    return {
        "user_id": user_id,
        "email": email,
        "password": password,
        "watchlist_count": len(watchlist_symbols),
        "event_count": len(events),
        "brief_count": len(brief_inbox_store.list_briefs(user_id=user_id)),
        "notification_count": len(notifications),
    }


class AdapterHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    allowed_origins: tuple[str, ...] = ()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._write_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._handle_api_request()

    def do_POST(self) -> None:  # noqa: N802
        self._handle_api_request()

    def do_PATCH(self) -> None:  # noqa: N802
        self._handle_api_request()

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle_api_request()

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stdout.write(f"[dev-seeded-api] {fmt % args}\n")
        sys.stdout.flush()

    def _handle_api_request(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            content_length = 0

        raw_body = self.rfile.read(content_length) if content_length > 0 else b""
        json_body: Any = None
        if raw_body:
            try:
                json_body = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError:
                self._write_json(
                    status=400,
                    payload={"code": "invalid_json", "message": "Request body must be valid JSON"},
                )
                return

        response = app.handle_request(
            method=self.command,
            url=self.path,
            json_body=json_body,
            headers={key: value for key, value in self.headers.items()},
        )
        self._write_json(status=response.status_code, payload=response.json(), extra_headers=response.headers)

    def _write_json(self, *, status: int, payload: Any, extra_headers: dict[str, str] | None = None) -> None:
        serialized = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)

        if extra_headers:
            for key, value in extra_headers.items():
                lowered = key.lower()
                if lowered in {"content-type", "content-length", "access-control-allow-origin"}:
                    continue
                self.send_header(key, str(value))

        self._write_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(serialized)))
        self.end_headers()
        self.wfile.write(serialized)

    def _write_cors_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin and origin in self.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Request-ID")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")


def _parse_config() -> AdapterConfig:
    host = os.environ.get("OMS_DEV_API_HOST", _DEFAULT_API_HOST).strip() or _DEFAULT_API_HOST
    port = int(os.environ.get("OMS_DEV_API_PORT", str(_DEFAULT_API_PORT)))
    email = os.environ.get("OMS_DEV_EMAIL", _DEFAULT_EMAIL).strip() or _DEFAULT_EMAIL
    password = os.environ.get("OMS_DEV_PASSWORD", _DEFAULT_PASSWORD).strip() or _DEFAULT_PASSWORD
    cors_origins = _parse_cors_origins(os.environ.get("OMS_CORS_ORIGINS", ""))
    return AdapterConfig(host=host, port=port, email=email, password=password, cors_origins=cors_origins)


def _parse_cors_origins(raw_value: str) -> tuple[str, ...]:
    if not raw_value.strip():
        return _DEFAULT_CORS_ORIGINS
    values = [value.strip() for value in raw_value.split(",")]
    cleaned = [value for value in values if value]
    return tuple(dict.fromkeys(cleaned)) if cleaned else _DEFAULT_CORS_ORIGINS


def main() -> None:
    parser = argparse.ArgumentParser(description="Seeded dev API adapter for manual QA")
    parser.add_argument("--seed-only", action="store_true", help="Seed data and exit")
    args = parser.parse_args()

    config = _parse_config()
    seed_summary = seed_data(email=config.email, password=config.password)
    print(json.dumps({"event": "seed_complete", **seed_summary}, ensure_ascii=False), flush=True)

    if args.seed_only:
        return

    AdapterHandler.allowed_origins = config.cors_origins
    server = ThreadingHTTPServer((config.host, config.port), AdapterHandler)
    print(
        json.dumps(
            {
                "event": "server_listening",
                "host": config.host,
                "port": config.port,
                "cors_origins": list(config.cors_origins),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
