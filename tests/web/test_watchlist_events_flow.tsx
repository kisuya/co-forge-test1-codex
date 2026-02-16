import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

describe("watchlist + events flow", () => {
  it("separates loading and empty states for watchlist and event feed", async () => {
    const fetchImpl = vi.fn(async (input) => {
      const url = String(input);
      if (url.endsWith("/v1/watchlists/items?page=1&size=20")) {
        return makeResponse(200, { items: [], total: 0, page: 1, size: 20 });
      }
      if (url.endsWith("/v1/events?size=20")) {
        return makeResponse(200, { items: [], count: 0, next_cursor: null });
      }
      throw new Error(`Unhandled request: ${url}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    expect(screen.getByTestId("watchlist-loading")).toBeInTheDocument();
    expect(screen.getByTestId("events-loading")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId("watchlist-empty")).toBeInTheDocument();
      expect(screen.getByTestId("events-empty")).toBeInTheDocument();
    });
  });

  it("supports watchlist add/delete and opens valid source link in new tab", async () => {
    const watchlist = [
      {
        id: "item-1",
        user_id: "user-1",
        market: "US",
        symbol: "AAPL",
        created_at_utc: "2026-02-17T00:00:00Z",
      },
    ];
    const fetchImpl = vi.fn(async (input, init) => {
      const url = String(input);
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.endsWith("/v1/watchlists/items?page=1&size=20") && method === "GET") {
        return makeResponse(200, {
          items: [...watchlist],
          total: watchlist.length,
          page: 1,
          size: 20,
        });
      }

      if (url.endsWith("/v1/watchlists/items") && method === "POST") {
        const body = JSON.parse(String(init?.body ?? "{}")) as { symbol: string; market: string };
        const newItem = {
          id: `item-${watchlist.length + 1}`,
          user_id: "user-1",
          market: body.market,
          symbol: body.symbol,
          created_at_utc: "2026-02-17T00:10:00Z",
        };
        watchlist.unshift(newItem);
        return makeResponse(201, { item: newItem, is_duplicate: false });
      }

      if (url.includes("/v1/watchlists/items/") && method === "DELETE") {
        const itemId = url.split("/").pop() ?? "";
        const index = watchlist.findIndex((item) => item.id === itemId);
        if (index >= 0) {
          watchlist.splice(index, 1);
        }
        return makeResponse(200, { deleted: true, item_id: itemId });
      }

      if (url.endsWith("/v1/events?size=20") && method === "GET") {
        return makeResponse(200, {
          items: [
            {
              id: "evt-1",
              symbol: "AAPL",
              market: "US",
              change_pct: 4.2,
              window_minutes: 5,
              detected_at_utc: "2026-02-17T01:00:00Z",
              exchange_timezone: "America/New_York",
              session_label: "regular",
              reasons: [],
              portfolio_impact: null,
            },
          ],
          count: 1,
          next_cursor: null,
        });
      }

      if (url.endsWith("/v1/events/evt-1") && method === "GET") {
        return makeResponse(200, {
          event: {
            id: "evt-1",
            symbol: "AAPL",
            market: "US",
            change_pct: 4.2,
            window_minutes: 5,
            detected_at_utc: "2026-02-17T01:00:00Z",
            exchange_timezone: "America/New_York",
            session_label: "regular",
            reasons: [
              {
                id: "reason-1",
                rank: 1,
                reason_type: "filing",
                confidence_score: 0.9,
                summary: "8-K filed",
                source_url: "https://sec.example/8k",
                published_at: "2026-02-17T00:59:00Z",
                explanation: { weights: {}, signals: {}, score_breakdown: { total: 0.9 } },
              },
            ],
            portfolio_impact: null,
          },
        });
      }

      throw new Error(`Unhandled request ${method} ${url}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    expect(await screen.findByText("US:AAPL")).toBeInTheDocument();
    const sourceLink = await screen.findByRole("link", { name: "근거 원문 보기" });
    expect(sourceLink).toHaveAttribute("href", "https://sec.example/8k");
    expect(sourceLink).toHaveAttribute("target", "_blank");

    fireEvent.change(screen.getByLabelText("종목코드"), {
      target: { value: "msft" },
    });
    fireEvent.click(screen.getByRole("button", { name: "추가" }));

    await waitFor(() => {
      expect(screen.getByText("US:MSFT")).toBeInTheDocument();
    });

    const msftRow = screen.getByText("US:MSFT").closest("li");
    expect(msftRow).not.toBeNull();
    fireEvent.click(within(msftRow as HTMLElement).getByRole("button", { name: "삭제" }));
    await waitFor(() => {
      expect(screen.queryByText("US:MSFT")).not.toBeInTheDocument();
    });
  });

  it("renders inaccessible source url as disabled text", async () => {
    const fetchImpl = vi.fn(async (input, init) => {
      const url = String(input);
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.endsWith("/v1/watchlists/items?page=1&size=20") && method === "GET") {
        return makeResponse(200, { items: [], total: 0, page: 1, size: 20 });
      }
      if (url.endsWith("/v1/events?size=20") && method === "GET") {
        return makeResponse(200, {
          items: [
            {
              id: "evt-2",
              symbol: "TSLA",
              market: "US",
              change_pct: -3.3,
              window_minutes: 5,
              detected_at_utc: "2026-02-17T02:00:00Z",
              exchange_timezone: "America/New_York",
              session_label: "regular",
              reasons: [],
              portfolio_impact: null,
            },
          ],
          count: 1,
          next_cursor: null,
        });
      }
      if (url.endsWith("/v1/events/evt-2") && method === "GET") {
        return makeResponse(200, {
          event: {
            id: "evt-2",
            symbol: "TSLA",
            market: "US",
            change_pct: -3.3,
            window_minutes: 5,
            detected_at_utc: "2026-02-17T02:00:00Z",
            exchange_timezone: "America/New_York",
            session_label: "regular",
            reasons: [
              {
                id: "reason-2",
                rank: 1,
                reason_type: "news",
                confidence_score: 0.5,
                summary: "Rumor",
                source_url: "ftp://unreachable.example/file",
                published_at: "2026-02-17T01:59:00Z",
                explanation: { weights: {}, signals: {}, score_breakdown: { total: 0.5 } },
              },
            ],
            portfolio_impact: null,
          },
        });
      }

      throw new Error(`Unhandled request ${method} ${url}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    expect(await screen.findByText("Rumor")).toBeInTheDocument();
    const disabled = screen.getByText("접근 불가 링크");
    expect(disabled).toHaveAttribute("aria-disabled", "true");
    expect(screen.queryByRole("link", { name: "근거 원문 보기" })).not.toBeInTheDocument();
  });
});
