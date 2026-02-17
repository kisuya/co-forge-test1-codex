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

describe("watchlist search + selection flow", () => {
  it("stores only symbols resolved from search results and saves recent searches", async () => {
    const watchlist: Array<{
      id: string;
      user_id: string;
      market: "KR" | "US";
      symbol: string;
      created_at_utc: string;
    }> = [];
    const createdPayloads: Array<{ symbol: string; market: string }> = [];

    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/watchlists/items" && method === "GET") {
        return makeResponse(200, {
          items: watchlist,
          total: watchlist.length,
          page: 1,
          size: 20,
        });
      }

      if (url.pathname === "/v1/watchlists/items" && method === "POST") {
        const body = JSON.parse(String(init?.body ?? "{}")) as { symbol: string; market: "KR" | "US" };
        createdPayloads.push(body);
        const item = {
          id: `item-${watchlist.length + 1}`,
          user_id: "user-1",
          market: body.market,
          symbol: body.symbol,
          created_at_utc: "2026-02-17T01:00:00Z",
        };
        watchlist.push(item);
        return makeResponse(201, { item, is_duplicate: false });
      }

      if (url.pathname === "/v1/events" && method === "GET") {
        return makeResponse(200, { items: [], count: 0, next_cursor: null });
      }

      if (url.pathname === "/v1/symbols/search" && method === "GET") {
        const query = (url.searchParams.get("q") ?? "").toUpperCase();
        const market = url.searchParams.get("market") ?? "US";
        if (market === "US" && query.includes("AP")) {
          return makeResponse(200, {
            items: [{ ticker: "AAPL", name: "Apple Inc.", market: "US" }],
            count: 1,
            catalog_version: "v1",
            catalog_refreshed_at_utc: "2026-02-17T00:00:00Z",
          });
        }
        return makeResponse(200, {
          items: [],
          count: 0,
          catalog_version: "v1",
          catalog_refreshed_at_utc: "2026-02-17T00:00:00Z",
        });
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    await screen.findByTestId("watchlist-empty");

    fireEvent.change(screen.getByLabelText("종목코드"), {
      target: { value: "zzzz" },
    });
    fireEvent.click(screen.getByRole("button", { name: "추가" }));

    expect((await screen.findAllByText("검색 결과에서 종목을 선택하세요.")).length).toBeGreaterThan(0);
    expect(createdPayloads).toHaveLength(0);

    fireEvent.change(screen.getByLabelText("종목코드"), {
      target: { value: "ap" },
    });

    const candidateButton = await screen.findByRole("button", {
      name: /US:AAPL · Apple Inc\./,
    });
    fireEvent.click(candidateButton);
    fireEvent.click(screen.getByRole("button", { name: "추가" }));

    await waitFor(() => {
      expect(screen.getByText("US:AAPL")).toBeInTheDocument();
    });

    expect(createdPayloads).toEqual([{ symbol: "AAPL", market: "US" }]);

    const recentSection = screen.getByRole("region", { name: "최근검색" });
    expect(within(recentSection).getByRole("button", { name: "최근 US:AAPL" })).toBeInTheDocument();
  });

  it("supports market filtering and keyboard controls for autocomplete", async () => {
    const watchlist: Array<{
      id: string;
      user_id: string;
      market: "KR" | "US";
      symbol: string;
      created_at_utc: string;
    }> = [];
    const createdPayloads: Array<{ symbol: string; market: string }> = [];

    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/watchlists/items" && method === "GET") {
        return makeResponse(200, {
          items: watchlist,
          total: watchlist.length,
          page: 1,
          size: 20,
        });
      }

      if (url.pathname === "/v1/watchlists/items" && method === "POST") {
        const body = JSON.parse(String(init?.body ?? "{}")) as { symbol: string; market: "KR" | "US" };
        createdPayloads.push(body);
        const item = {
          id: `item-${watchlist.length + 1}`,
          user_id: "user-1",
          market: body.market,
          symbol: body.symbol,
          created_at_utc: "2026-02-17T02:00:00Z",
        };
        watchlist.push(item);
        return makeResponse(201, { item, is_duplicate: false });
      }

      if (url.pathname === "/v1/events" && method === "GET") {
        return makeResponse(200, { items: [], count: 0, next_cursor: null });
      }

      if (url.pathname === "/v1/symbols/search" && method === "GET") {
        const query = (url.searchParams.get("q") ?? "").toUpperCase();
        const market = url.searchParams.get("market") ?? "US";

        if (market === "KR" && query.includes("00")) {
          return makeResponse(200, {
            items: [
              { ticker: "005930", name: "Samsung Electronics", market: "KR" },
              { ticker: "000660", name: "SK Hynix", market: "KR" },
            ],
            count: 2,
            catalog_version: "v1",
            catalog_refreshed_at_utc: "2026-02-17T00:00:00Z",
          });
        }

        return makeResponse(200, {
          items: [],
          count: 0,
          catalog_version: "v1",
          catalog_refreshed_at_utc: "2026-02-17T00:00:00Z",
        });
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    await screen.findByTestId("watchlist-empty");

    const marketSelect = screen.getByLabelText("시장") as HTMLSelectElement;
    fireEvent.change(marketSelect, {
      target: { value: "KR" },
    });
    await waitFor(() => {
      expect(marketSelect.value).toBe("KR");
    });
    const input = screen.getByLabelText("종목코드");
    fireEvent.change(input, {
      target: { value: "00" },
    });

    await screen.findByRole("button", { name: /KR:005930/ }, { timeout: 2000 });

    fireEvent.keyDown(input, { key: "Escape" });
    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: "KR:005930 · Samsung Electronics" }),
      ).not.toBeInTheDocument();
    });

    fireEvent.change(input, {
      target: { value: "005" },
    });
    fireEvent.change(input, {
      target: { value: "00" },
    });
    await screen.findByRole("button", { name: /KR:005930/ }, { timeout: 2000 });

    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });

    const addButton = screen.getByRole("button", { name: "추가" });
    expect(addButton).toHaveFocus();
    fireEvent.click(addButton);

    await waitFor(() => {
      expect(screen.getByText("KR:000660")).toBeInTheDocument();
    });
    expect(createdPayloads).toEqual([{ symbol: "000660", market: "KR" }]);
  });

  it("shows autocomplete loading and empty states", async () => {
    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/watchlists/items" && method === "GET") {
        return makeResponse(200, { items: [], total: 0, page: 1, size: 20 });
      }
      if (url.pathname === "/v1/events" && method === "GET") {
        return makeResponse(200, { items: [], count: 0, next_cursor: null });
      }

      if (url.pathname === "/v1/symbols/search" && method === "GET") {
        await new Promise((resolve) => setTimeout(resolve, 40));
        return makeResponse(200, {
          items: [],
          count: 0,
          catalog_version: "v1",
          catalog_refreshed_at_utc: "2026-02-17T00:00:00Z",
        });
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    await screen.findByTestId("watchlist-empty");

    fireEvent.change(screen.getByLabelText("종목코드"), {
      target: { value: "xy" },
    });

    await screen.findByTestId("watchlist-search-loading");
    expect(await screen.findByTestId("watchlist-search-empty")).toBeInTheDocument();
  });
});
