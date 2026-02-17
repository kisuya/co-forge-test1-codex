import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WatchlistEventsDashboard } from "@/components/watchlist-events-dashboard";
import { createApiClient } from "@/lib/api-client";
import { createMemorySession } from "@/lib/auth-session";

type ResponseShape = {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
};

function makeResponse(status: number, payload: unknown): Response {
  const response: ResponseShape = {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  };
  return response as unknown as Response;
}

function buildDashboardClient(fetchImpl: typeof fetch) {
  const session = createMemorySession({ userId: "user-1", accessToken: "token-1" });
  return createApiClient({
    baseUrl: "http://localhost:8000",
    session,
    fetchImpl,
  });
}

function baseEvent(eventId: string) {
  return {
    id: eventId,
    symbol: "AAPL",
    market: "US",
    change_pct: 4.2,
    window_minutes: 5,
    detected_at_utc: "2026-02-17T01:00:00Z",
    exchange_timezone: "America/New_York",
    session_label: "regular",
    reasons: [],
    portfolio_impact: null,
  };
}

describe("reason explanation panel", () => {
  it("renders verified badge and toggles explanation panel", async () => {
    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/watchlists/items" && method === "GET") {
        return makeResponse(200, { items: [], total: 0, page: 1, size: 20 });
      }
      if (url.pathname === "/v1/events" && method === "GET") {
        return makeResponse(200, { items: [baseEvent("evt-1")], count: 1, next_cursor: null });
      }
      if (url.pathname === "/v1/events/evt-1" && method === "GET") {
        return makeResponse(200, {
          event: {
            ...baseEvent("evt-1"),
            reason_status: "verified",
            confidence_breakdown: {
              weights: { source_reliability: 0.4, event_match: 0.3, time_proximity: 0.3 },
              signals: { source_reliability: 0.9, event_match: 0.8, time_proximity: 0.7 },
              score_breakdown: { source_reliability: 0.36, event_match: 0.24, time_proximity: 0.21, total: 0.81 },
            },
            explanation_text: "8-K filing confidence explained by recency and source quality.",
            revision_hint: null,
            reasons: [
              {
                id: "reason-1",
                rank: 1,
                reason_type: "filing",
                confidence_score: 0.81,
                summary: "8-K filed before move",
                source_url: "https://sec.example/8k",
                published_at: "2026-02-17T00:59:00Z",
                explanation: {},
              },
            ],
          },
        });
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    expect(await screen.findByText("8-K filed before move")).toBeInTheDocument();
    expect(screen.getByTestId("reason-status-badge")).toHaveTextContent("검증 완료");
    expect(screen.getByText("현재 근거 기준으로 설명 가능한 상태입니다.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "설명 펼치기" }));
    expect(screen.getByText("8-K filing confidence explained by recency and source quality.")).toBeInTheDocument();
    expect(screen.getAllByText("시간 근접도").length).toBeGreaterThan(0);
    expect(screen.getByText("총합")).toBeInTheDocument();

    const sourceLink = screen.getByRole("link", { name: "근거 원문 보기" });
    expect(sourceLink).toHaveAttribute("href", "https://sec.example/8k");
    expect(sourceLink).toHaveAttribute("target", "_blank");

    fireEvent.click(screen.getByRole("button", { name: "설명 접기" }));
    expect(screen.queryByText("총합")).not.toBeInTheDocument();
  });

  it("shows collecting state, helper hint and empty evidence fallback", async () => {
    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/watchlists/items" && method === "GET") {
        return makeResponse(200, { items: [], total: 0, page: 1, size: 20 });
      }
      if (url.pathname === "/v1/events" && method === "GET") {
        return makeResponse(200, { items: [baseEvent("evt-2")], count: 1, next_cursor: null });
      }
      if (url.pathname === "/v1/events/evt-2" && method === "GET") {
        return makeResponse(200, {
          event: {
            ...baseEvent("evt-2"),
            reason_status: "collecting_evidence",
            confidence_breakdown: {
              weights: { source_reliability: 0, event_match: 0, time_proximity: 0 },
              signals: { source_reliability: 0, event_match: 0, time_proximity: 0 },
              score_breakdown: { source_reliability: 0, event_match: 0, time_proximity: 0, total: 0 },
            },
            explanation_text: "근거 수집 중입니다.",
            revision_hint: "근거 수집/검증이 진행 중이며 카드 내용이 업데이트될 수 있습니다.",
            reasons: [],
          },
        });
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    expect(await screen.findByTestId("reason-status-badge")).toHaveTextContent("근거 수집 중");
    expect(screen.getByText("근거 수집/검증이 진행 중이며 카드 내용이 업데이트될 수 있습니다.")).toBeInTheDocument();
    expect(screen.getByTestId("evidence-empty")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "설명 펼치기" }));
    expect(screen.getByText("근거 수집 중입니다.")).toBeInTheDocument();
  });

  it("shows loading fallback and missing-breakdown fallback text", async () => {
    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/watchlists/items" && method === "GET") {
        return makeResponse(200, { items: [], total: 0, page: 1, size: 20 });
      }
      if (url.pathname === "/v1/events" && method === "GET") {
        return makeResponse(200, { items: [baseEvent("evt-3")], count: 1, next_cursor: null });
      }
      if (url.pathname === "/v1/events/evt-3" && method === "GET") {
        await new Promise((resolve) => setTimeout(resolve, 40));
        return makeResponse(200, {
          event: {
            ...baseEvent("evt-3"),
            reason_status: "verified",
            explanation_text: "",
            revision_hint: null,
            reasons: [
              {
                id: "reason-3",
                rank: 1,
                reason_type: "news",
                confidence_score: 0.5,
                summary: "Rumor spread in market",
                source_url: null,
                published_at: "2026-02-17T00:59:00Z",
                explanation: {},
              },
            ],
          },
        });
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    expect(await screen.findByTestId("reason-panel-loading")).toBeInTheDocument();
    expect(await screen.findByText("Rumor spread in market")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "설명 펼치기" }));
    expect(screen.getByTestId("confidence-breakdown-fallback")).toHaveTextContent(
      "confidence 세부 점수를 아직 계산 중입니다.",
    );
    expect(screen.getByText("근거 수집 중입니다. 검증 가능한 출처가 확보되면 confidence 설명이 갱신됩니다.")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("일부 confidence 항목이 누락되어 기본값(0.00)으로 표시하고 있습니다.")).toBeInTheDocument();
    });
  });
});
