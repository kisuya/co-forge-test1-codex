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

describe("watchlist input accessibility and resilience", () => {
  it("exposes combobox accessibility attrs and keeps focus flow consistent", async () => {
    const watchlist: Array<{
      id: string;
      user_id: string;
      market: "KR" | "US";
      symbol: string;
      created_at_utc: string;
    }> = [];

    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/watchlists/items" && method === "GET") {
        return makeResponse(200, { items: watchlist, total: watchlist.length, page: 1, size: 20 });
      }
      if (url.pathname === "/v1/events" && method === "GET") {
        return makeResponse(200, { items: [], count: 0, next_cursor: null });
      }
      if (url.pathname === "/v1/symbols/search" && method === "GET") {
        return makeResponse(200, {
          items: [{ ticker: "MSFT", name: "Microsoft Corporation", market: "US" }],
          count: 1,
          catalog_version: "v1",
          catalog_refreshed_at_utc: "2026-02-17T00:00:00Z",
        });
      }
      if (url.pathname === "/v1/watchlists/items" && method === "POST") {
        const body = JSON.parse(String(init?.body ?? "{}")) as { symbol: string; market: "KR" | "US" };
        const item = {
          id: "item-1",
          user_id: "user-1",
          symbol: body.symbol,
          market: body.market,
          created_at_utc: "2026-02-17T03:00:00Z",
        };
        watchlist.push(item);
        return makeResponse(201, { item, is_duplicate: false });
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    await screen.findByTestId("watchlist-empty");

    const input = screen.getByRole("combobox", { name: "종목코드" });
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(input).toHaveAttribute("aria-autocomplete", "list");
    expect(input).toHaveAttribute("aria-controls");
    expect(input).toHaveAttribute("aria-expanded", "false");

    fireEvent.change(input, { target: { value: "ms" } });
    await screen.findByRole("button", { name: /US:MSFT · Microsoft Corporation/ });

    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });

    const addButton = screen.getByRole("button", { name: "추가" });
    expect(addButton).toHaveFocus();

    fireEvent.click(addButton);

    await waitFor(() => {
      expect(screen.getByText("US:MSFT")).toBeInTheDocument();
    });
    expect(input).toHaveFocus();
  });

  it("shows retry/cancel recovery actions when save fails", async () => {
    const watchlist: Array<{
      id: string;
      user_id: string;
      market: "KR" | "US";
      symbol: string;
      created_at_utc: string;
    }> = [];
    let postAttempts = 0;

    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/watchlists/items" && method === "GET") {
        return makeResponse(200, { items: watchlist, total: watchlist.length, page: 1, size: 20 });
      }
      if (url.pathname === "/v1/events" && method === "GET") {
        return makeResponse(200, { items: [], count: 0, next_cursor: null });
      }
      if (url.pathname === "/v1/symbols/search" && method === "GET") {
        return makeResponse(200, {
          items: [{ ticker: "NVDA", name: "NVIDIA Corporation", market: "US" }],
          count: 1,
          catalog_version: "v1",
          catalog_refreshed_at_utc: "2026-02-17T00:00:00Z",
        });
      }
      if (url.pathname === "/v1/watchlists/items" && method === "POST") {
        postAttempts += 1;
        if (postAttempts === 1) {
          return makeResponse(503, {
            code: "upstream_unavailable",
            message: "일시적 오류가 발생했습니다.",
            details: { retryable: true },
          });
        }
        const body = JSON.parse(String(init?.body ?? "{}")) as { symbol: string; market: "KR" | "US" };
        const item = {
          id: "item-2",
          user_id: "user-1",
          symbol: body.symbol,
          market: body.market,
          created_at_utc: "2026-02-17T04:00:00Z",
        };
        watchlist.push(item);
        return makeResponse(201, { item, is_duplicate: false });
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    await screen.findByTestId("watchlist-empty");

    const input = screen.getByLabelText("종목코드");
    fireEvent.change(input, { target: { value: "nv" } });
    fireEvent.click(await screen.findByRole("button", { name: /US:NVDA · NVIDIA Corporation/ }));
    fireEvent.click(screen.getByRole("button", { name: "추가" }));

    expect((await screen.findAllByText("일시적 오류가 발생했습니다.")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "저장 다시 시도" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "취소" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "저장 다시 시도" }));

    await waitFor(() => {
      expect(screen.getByText("US:NVDA")).toBeInTheDocument();
    });
    expect(postAttempts).toBe(2);
  });

  it("guards query boundaries and blocks duplicate submit clicks", async () => {
    const watchlist: Array<{
      id: string;
      user_id: string;
      market: "KR" | "US";
      symbol: string;
      created_at_utc: string;
    }> = [];
    let postAttempts = 0;

    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/watchlists/items" && method === "GET") {
        return makeResponse(200, { items: watchlist, total: watchlist.length, page: 1, size: 20 });
      }
      if (url.pathname === "/v1/events" && method === "GET") {
        return makeResponse(200, { items: [], count: 0, next_cursor: null });
      }
      if (url.pathname === "/v1/symbols/search" && method === "GET") {
        return makeResponse(200, {
          items: [{ ticker: "AAPL", name: "Apple Inc.", market: "US" }],
          count: 1,
          catalog_version: "v1",
          catalog_refreshed_at_utc: "2026-02-17T00:00:00Z",
        });
      }
      if (url.pathname === "/v1/watchlists/items" && method === "POST") {
        postAttempts += 1;
        await new Promise((resolve) => setTimeout(resolve, 40));
        const body = JSON.parse(String(init?.body ?? "{}")) as { symbol: string; market: "KR" | "US" };
        const item = {
          id: `item-${watchlist.length + 1}`,
          user_id: "user-1",
          symbol: body.symbol,
          market: body.market,
          created_at_utc: "2026-02-17T05:00:00Z",
        };
        watchlist.push(item);
        return makeResponse(201, { item, is_duplicate: false });
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    await screen.findByTestId("watchlist-empty");

    const input = screen.getByLabelText("종목코드");
    fireEvent.change(input, { target: { value: "a" } });
    fireEvent.click(screen.getByRole("button", { name: "추가" }));

    expect(await screen.findByText("검색어를 2자 이상 입력하세요.")).toBeInTheDocument();
    expect(postAttempts).toBe(0);

    fireEvent.change(input, { target: { value: "aa" } });
    fireEvent.click(await screen.findByRole("button", { name: /US:AAPL · Apple Inc\./ }));

    const addButton = screen.getByRole("button", { name: "추가" });
    fireEvent.click(addButton);
    fireEvent.click(addButton);

    await waitFor(() => {
      expect(postAttempts).toBe(1);
    });
    await waitFor(() => {
      expect(screen.getByText("US:AAPL")).toBeInTheDocument();
    });
  });
});
