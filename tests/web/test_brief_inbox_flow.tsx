import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BriefInbox } from "@/components/brief-inbox";
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

function buildClient(fetchImpl: typeof fetch) {
  const session = createMemorySession({ userId: "user-1", accessToken: "token-1" });
  return createApiClient({
    baseUrl: "http://localhost:8000",
    session,
    fetchImpl,
  });
}

function setViewport(width: number): void {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: width,
  });
  window.dispatchEvent(new Event("resize"));
}

describe("brief inbox flow", () => {
  it("renders pre/post sections, opens detail and marks unread brief as read", async () => {
    const briefs = [
      {
        id: "pre-1",
        brief_type: "pre_market",
        title: "개장 전 브리프",
        summary: "오늘 확인할 핵심 일정",
        generated_at_utc: "2026-02-17T22:40:00Z",
        markets: ["US"],
        item_count: 1,
        fallback_reason: null,
        status: "unread",
        is_expired: false,
      },
      {
        id: "post-1",
        brief_type: "post_close",
        title: "장마감 브리프",
        summary: "오늘 변동 요약",
        generated_at_utc: "2026-02-17T06:10:00Z",
        markets: ["US"],
        item_count: 1,
        fallback_reason: null,
        status: "read",
        is_expired: false,
      },
    ];

    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/briefs" && method === "GET") {
        return makeResponse(200, {
          items: briefs,
          count: briefs.length,
          meta: { unread_count: briefs.filter((item) => item.status === "unread").length, pre_market_count: 1, post_close_count: 1 },
        });
      }
      if (url.pathname === "/v1/briefs/pre-1" && method === "GET") {
        return makeResponse(200, {
          brief: {
            ...briefs[0],
            items: [
              {
                event_id: "evt-pre-1",
                symbol: "AAPL",
                market: "US",
                summary: "실적 발표 전 체크",
                event_detail_url: "/events/evt-pre-1",
                source_url: "https://news.example/pre-1",
              },
            ],
          },
        });
      }
      if (url.pathname === "/v1/briefs/pre-1/read" && method === "PATCH") {
        briefs[0] = {
          ...briefs[0],
          status: "read",
        };
        return makeResponse(200, {
          brief: briefs[0],
          unread_count: 0,
        });
      }
      if (url.pathname === "/v1/briefs/post-1" && method === "GET") {
        return makeResponse(200, {
          brief: {
            ...briefs[1],
            items: [
              {
                event_id: "evt-post-1",
                symbol: "MSFT",
                market: "US",
                summary: "종가 기준 변동 +4.10%",
                event_detail_url: "/events/evt-post-1",
                source_url: "https://news.example/post-1",
              },
            ],
          },
        });
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<BriefInbox client={buildClient(fetchImpl)} />);

    expect(screen.getByTestId("brief-list-loading")).toBeInTheDocument();

    expect(await screen.findByTestId("brief-inbox")).toBeInTheDocument();
    expect(screen.getByTestId("brief-section-pre")).toBeInTheDocument();
    expect(screen.getByTestId("brief-section-post")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId("brief-card-status-pre-1")).toHaveTextContent("읽음");
      expect(screen.getByTestId("brief-unread-count")).toHaveTextContent("읽지 않음 0");
    });

    expect(screen.getByTestId("brief-detail-title")).toHaveTextContent("개장 전 브리프");
    const sourceLink = screen.getByRole("link", { name: "근거 원문 보기" });
    expect(sourceLink).toHaveAttribute("href", "https://news.example/pre-1");
    expect(sourceLink).toHaveAttribute("target", "_blank");

    fireEvent.click(screen.getByTestId("brief-card-post-1"));

    expect(await screen.findByText("종가 기준 변동 +4.10%")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "이벤트 상세 이동" })).toHaveAttribute("href", "/events/evt-post-1");
  });

  it("supports retry after brief list loading failure", async () => {
    let attempts = 0;
    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/briefs" && method === "GET") {
        attempts += 1;
        if (attempts === 1) {
          return makeResponse(503, {
            code: "temporarily_unavailable",
            message: "브리프를 불러오는 중입니다.",
            retryable: true,
          });
        }
        return makeResponse(200, {
          items: [],
          count: 0,
          meta: { unread_count: 0, pre_market_count: 0, post_close_count: 0 },
        });
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<BriefInbox client={buildClient(fetchImpl)} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("브리프를 불러오는 중입니다.");
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));

    expect(await screen.findByTestId("brief-empty")).toBeInTheDocument();
  });

  it("shows expired-link guidance when detail link is no longer valid", async () => {
    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/briefs" && method === "GET") {
        return makeResponse(200, {
          items: [
            {
              id: "brief-expired-1",
              brief_type: "pre_market",
              title: "개장 전 브리프",
              summary: "만료 링크 테스트",
              generated_at_utc: "2026-02-17T01:00:00Z",
              markets: ["US"],
              item_count: 1,
              fallback_reason: null,
              status: "unread",
              is_expired: true,
            },
          ],
          count: 1,
          meta: { unread_count: 1, pre_market_count: 1, post_close_count: 0 },
        });
      }

      if (url.pathname === "/v1/briefs/brief-expired-1" && method === "GET") {
        return makeResponse(410, {
          code: "brief_link_expired",
          message: "Brief link has expired",
          retryable: false,
        });
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<BriefInbox client={buildClient(fetchImpl)} />);

    expect(await screen.findByTestId("brief-detail-expired")).toHaveTextContent(
      "브리프 링크가 만료되었습니다. 최신 브리프를 확인하세요.",
    );
  });

  it("switches inbox layout between mobile and desktop widths", async () => {
    act(() => {
      setViewport(390);
    });

    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/briefs" && method === "GET") {
        return makeResponse(200, {
          items: [
            {
              id: "brief-layout-1",
              brief_type: "pre_market",
              title: "개장 전 브리프",
              summary: "반응형 테스트",
              generated_at_utc: "2026-02-17T01:00:00Z",
              markets: ["US"],
              item_count: 1,
              fallback_reason: null,
              status: "read",
              is_expired: false,
            },
          ],
          count: 1,
          meta: { unread_count: 0, pre_market_count: 1, post_close_count: 0 },
        });
      }
      if (url.pathname === "/v1/briefs/brief-layout-1" && method === "GET") {
        return makeResponse(200, {
          brief: {
            id: "brief-layout-1",
            brief_type: "pre_market",
            title: "개장 전 브리프",
            summary: "반응형 테스트",
            generated_at_utc: "2026-02-17T01:00:00Z",
            markets: ["US"],
            item_count: 1,
            fallback_reason: null,
            status: "read",
            is_expired: false,
            items: [
              {
                event_id: "evt-layout-1",
                symbol: "AAPL",
                market: "US",
                summary: "반응형 항목",
                event_detail_url: "/events/evt-layout-1",
                source_url: "https://news.example/layout-1",
              },
            ],
          },
        });
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<BriefInbox client={buildClient(fetchImpl)} />);

    const inbox = await screen.findByTestId("brief-inbox");
    expect(inbox).toHaveAttribute("data-layout", "mobile");

    act(() => {
      setViewport(1440);
    });
    await waitFor(() => {
      expect(screen.getByTestId("brief-inbox")).toHaveAttribute("data-layout", "desktop");
    });
  });
});
