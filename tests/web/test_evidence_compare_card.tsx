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
  const session = createMemorySession({
    userId: "user-1",
    accessToken: "token-1",
  });
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
    change_pct: 4.1,
    window_minutes: 5,
    detected_at_utc: "2026-02-18T00:00:00Z",
    exchange_timezone: "America/New_York",
    session_label: "regular",
    reasons: [],
    portfolio_impact: null,
  };
}

function baseDetailEvent(eventId: string) {
  return {
    ...baseEvent(eventId),
    reasons: [
      {
        id: "reason-1",
        rank: 1,
        reason_type: "news",
        confidence_score: 0.82,
        summary: "8-K filing and analyst reaction",
        source_url: "https://news.example/event-detail-source",
        published_at: "2026-02-18T00:01:00Z",
        explanation: {},
      },
    ],
    reason_status: "verified",
  };
}

function readyComparePayload(eventId: string) {
  return {
    event_id: eventId,
    status: "ready",
    compare_ready: true,
    fallback_reason: null,
    bias_warning: "긍정/부정 근거가 함께 존재합니다. 단일 결론보다 출처와 발행 시각을 함께 비교하세요.",
    axes: {
      positive: [
        {
          id: "cmp-pos-1",
          reason_type: "news",
          summary: "Earnings beat and guidance raised",
          source_url: "https://news.example/positive",
          published_at: "2026-02-18T00:03:00Z",
        },
      ],
      negative: [
        {
          id: "cmp-neg-1",
          reason_type: "news",
          summary: "Regulatory investigation risk remains",
          source_url: "https://news.example/negative",
          published_at: "2026-02-18T00:02:00Z",
        },
      ],
      uncertain: [
        {
          id: "cmp-unc-1",
          reason_type: "news",
          summary: "Mixed analyst commentary",
          source_url: "https://news.example/uncertain",
          published_at: "2026-02-18T00:01:00Z",
        },
      ],
    },
    axis_counts: {
      positive: 1,
      negative: 1,
      uncertain: 1,
    },
    comparable_axis_count: 3,
    evidence_count: 3,
    dropped_missing_metadata_count: 0,
    generated_at_utc: "2026-02-18T00:05:00Z",
    sources: [
      {
        axis: "positive",
        source_url: "https://news.example/positive",
        published_at: "2026-02-18T00:03:00Z",
        summary: "Earnings beat and guidance raised",
      },
      {
        axis: "negative",
        source_url: "https://news.example/negative",
        published_at: "2026-02-18T00:02:00Z",
        summary: "Regulatory investigation risk remains",
      },
      {
        axis: "uncertain",
        source_url: "https://news.example/uncertain",
        published_at: "2026-02-18T00:01:00Z",
        summary: "Mixed analyst commentary",
      },
    ],
  };
}

describe("evidence compare card", () => {
  it("renders positive/negative/uncertain comparison axes with source metadata", async () => {
    const eventId = "evt-ready";
    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/watchlists/items" && method === "GET") {
        return makeResponse(200, { items: [], total: 0, page: 1, size: 20 });
      }
      if (url.pathname === "/v1/events" && method === "GET") {
        return makeResponse(200, { items: [baseEvent(eventId)], count: 1, next_cursor: null });
      }
      if (url.pathname === `/v1/events/${eventId}` && method === "GET") {
        return makeResponse(200, { event: baseDetailEvent(eventId) });
      }
      if (url.pathname === `/v1/events/${eventId}/reason-revisions` && method === "GET") {
        return makeResponse(404, {
          code: "reason_revision_history_not_found",
          message: "Reason revision history not found",
          details: {},
          retryable: false,
        });
      }
      if (url.pathname === `/v1/events/${eventId}/evidence-compare` && method === "GET") {
        return makeResponse(200, readyComparePayload(eventId));
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    expect(await screen.findByTestId("evidence-compare-ready")).toBeInTheDocument();
    expect(screen.getByText("긍정 축")).toBeInTheDocument();
    expect(screen.getByText("부정 축")).toBeInTheDocument();
    expect(screen.getByText("불확실 축")).toBeInTheDocument();
    expect(screen.getByText("Earnings beat and guidance raised")).toBeInTheDocument();
    expect(screen.getByText("Regulatory investigation risk remains")).toBeInTheDocument();
    expect(screen.getByText("Mixed analyst commentary")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "원문 보기" })).toHaveLength(3);
  });

  it("shows compare_unavailable state with explicit fallback guidance", async () => {
    const eventId = "evt-unavailable";
    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/watchlists/items" && method === "GET") {
        return makeResponse(200, { items: [], total: 0, page: 1, size: 20 });
      }
      if (url.pathname === "/v1/events" && method === "GET") {
        return makeResponse(200, { items: [baseEvent(eventId)], count: 1, next_cursor: null });
      }
      if (url.pathname === `/v1/events/${eventId}` && method === "GET") {
        return makeResponse(200, { event: baseDetailEvent(eventId) });
      }
      if (url.pathname === `/v1/events/${eventId}/reason-revisions` && method === "GET") {
        return makeResponse(404, {
          code: "reason_revision_history_not_found",
          message: "Reason revision history not found",
          details: {},
          retryable: false,
        });
      }
      if (url.pathname === `/v1/events/${eventId}/evidence-compare` && method === "GET") {
        return makeResponse(200, {
          event_id: eventId,
          status: "compare_unavailable",
          compare_ready: false,
          fallback_reason: "axis_imbalance",
          bias_warning: "상충 근거가 충분하지 않아 불확실 축으로 표시합니다. 단정형 결론은 제공하지 않습니다.",
          axes: {
            positive: [],
            negative: [],
            uncertain: [
              {
                id: "cmp-u-1",
                reason_type: "news",
                summary: "Evidence skewed to one side",
                source_url: "https://news.example/uncertain-only",
                published_at: "2026-02-18T00:04:00Z",
              },
            ],
          },
          axis_counts: { positive: 0, negative: 0, uncertain: 1 },
          comparable_axis_count: 1,
          evidence_count: 1,
          dropped_missing_metadata_count: 0,
          generated_at_utc: "2026-02-18T00:05:00Z",
          sources: [],
        });
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    const unavailableCard = await screen.findByTestId("evidence-compare-unavailable");
    expect(unavailableCard).toHaveTextContent("비교 근거 부족");
    expect(unavailableCard).toHaveTextContent("긍정/부정 축이 불균형하여 신뢰 가능한 비교를 제공하기 어렵습니다.");
    expect(screen.getByText("Evidence skewed to one side")).toBeInTheDocument();
  });

  it("renders loading state and supports retry on retryable compare API failures", async () => {
    const eventId = "evt-retry";
    let compareRequestCount = 0;

    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/watchlists/items" && method === "GET") {
        return makeResponse(200, { items: [], total: 0, page: 1, size: 20 });
      }
      if (url.pathname === "/v1/events" && method === "GET") {
        return makeResponse(200, { items: [baseEvent(eventId)], count: 1, next_cursor: null });
      }
      if (url.pathname === `/v1/events/${eventId}` && method === "GET") {
        return makeResponse(200, { event: baseDetailEvent(eventId) });
      }
      if (url.pathname === `/v1/events/${eventId}/reason-revisions` && method === "GET") {
        return makeResponse(404, {
          code: "reason_revision_history_not_found",
          message: "Reason revision history not found",
          details: {},
          retryable: false,
        });
      }
      if (url.pathname === `/v1/events/${eventId}/evidence-compare` && method === "GET") {
        compareRequestCount += 1;
        if (compareRequestCount === 1) {
          await new Promise((resolve) => setTimeout(resolve, 40));
          return makeResponse(503, {
            code: "compare_upstream_timeout",
            message: "비교 근거 수집이 지연되고 있습니다.",
            details: { retryable: true },
            retryable: true,
          });
        }
        return makeResponse(200, readyComparePayload(eventId));
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    expect(await screen.findByTestId("evidence-compare-loading")).toBeInTheDocument();
    expect(await screen.findByTestId("evidence-compare-error")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "비교 카드 다시 시도" }));

    await waitFor(() => {
      expect(screen.getByTestId("evidence-compare-ready")).toBeInTheDocument();
    });
    expect(compareRequestCount).toBe(2);
  });

  it("falls back safely when compare payload contains partial item metadata", async () => {
    const eventId = "evt-partial";
    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/watchlists/items" && method === "GET") {
        return makeResponse(200, { items: [], total: 0, page: 1, size: 20 });
      }
      if (url.pathname === "/v1/events" && method === "GET") {
        return makeResponse(200, { items: [baseEvent(eventId)], count: 1, next_cursor: null });
      }
      if (url.pathname === `/v1/events/${eventId}` && method === "GET") {
        return makeResponse(200, { event: baseDetailEvent(eventId) });
      }
      if (url.pathname === `/v1/events/${eventId}/reason-revisions` && method === "GET") {
        return makeResponse(404, {
          code: "reason_revision_history_not_found",
          message: "Reason revision history not found",
          details: {},
          retryable: false,
        });
      }
      if (url.pathname === `/v1/events/${eventId}/evidence-compare` && method === "GET") {
        return makeResponse(200, {
          ...readyComparePayload(eventId),
          axes: {
            positive: [
              {
                id: "cmp-partial-1",
                reason_type: "news",
                summary: " ",
                source_url: "ftp://invalid-link.example/file",
                published_at: "",
              },
            ],
            negative: [],
            uncertain: [],
          },
          axis_counts: { positive: 1, negative: 0, uncertain: 0 },
          comparable_axis_count: 1,
          evidence_count: 1,
          sources: [],
        });
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    expect(await screen.findByTestId("evidence-compare-ready")).toBeInTheDocument();
    expect(screen.getByText("요약 정보 없음")).toBeInTheDocument();
    expect(screen.getByText("발행 시각: 발행 시각 확인 중")).toBeInTheDocument();
    expect(screen.getByText("접근 불가 링크")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "원문 보기" })).not.toBeInTheDocument();
  });
});
