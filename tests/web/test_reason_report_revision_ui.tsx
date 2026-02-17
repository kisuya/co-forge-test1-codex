import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

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

function detailEvent(eventId: string, reasonId: string) {
  return {
    ...baseEvent(eventId),
    reason_status: "verified",
    confidence_breakdown: {
      weights: { source_reliability: 0.4, event_match: 0.3, time_proximity: 0.3 },
      signals: { source_reliability: 0.9, event_match: 0.8, time_proximity: 0.7 },
      score_breakdown: { source_reliability: 0.36, event_match: 0.24, time_proximity: 0.21, total: 0.81 },
    },
    explanation_text: "confidence 계산 근거 설명",
    revision_hint: null,
    reasons: [
      {
        id: reasonId,
        rank: 1,
        reason_type: "filing",
        confidence_score: 0.81,
        summary: "8-K filed before move",
        source_url: "https://sec.example/8k",
        published_at: "2026-02-17T00:59:00Z",
        explanation: {},
      },
    ],
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("reason report + revision UI flow", () => {
  it("submits report with loading state, updates badge, and renders revision timeline", async () => {
    let revisionRequestCount = 0;
    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/watchlists/items" && method === "GET") {
        return makeResponse(200, { items: [], total: 0, page: 1, size: 20 });
      }
      if (url.pathname === "/v1/events" && method === "GET") {
        return makeResponse(200, { items: [baseEvent("evt-success")], count: 1, next_cursor: null });
      }
      if (url.pathname === "/v1/events/evt-success" && method === "GET") {
        return makeResponse(200, { event: detailEvent("evt-success", "reason-success") });
      }
      if (url.pathname === "/v1/events/evt-success/reason-revisions" && method === "GET") {
        revisionRequestCount += 1;
        if (revisionRequestCount === 1) {
          return makeResponse(404, {
            code: "reason_revision_history_not_found",
            message: "Reason revision history not found",
            details: { event_id: "evt-success" },
          });
        }
        return makeResponse(200, {
          event_id: "evt-success",
          revision_history: [
            {
              id: "rev-1",
              report_id: "report-1",
              event_id: "evt-success",
              reason_id: "reason-success",
              revision_reason: "근거 재검증 후 점수 조정",
              confidence_before: 0.82,
              confidence_after: 0.61,
              revised_at_utc: "2026-02-17T01:10:00Z",
            },
          ],
          status_transitions: [
            {
              report_id: "report-1",
              event_id: "evt-success",
              reason_id: "reason-success",
              from_status: null,
              to_status: "received",
              changed_at_utc: "2026-02-17T01:02:00Z",
              note: null,
            },
            {
              report_id: "report-1",
              event_id: "evt-success",
              reason_id: "reason-success",
              from_status: "received",
              to_status: "reviewed",
              changed_at_utc: "2026-02-17T01:06:00Z",
              note: "triaged",
            },
            {
              report_id: "report-1",
              event_id: "evt-success",
              reason_id: "reason-success",
              from_status: "reviewed",
              to_status: "resolved",
              changed_at_utc: "2026-02-17T01:10:00Z",
              note: "resolved",
            },
          ],
          count: 1,
          meta: {
            has_revision_history: true,
            latest_status: "resolved",
          },
        });
      }
      if (url.pathname === "/v1/events/evt-success/reason-reports" && method === "POST") {
        await new Promise((resolve) => setTimeout(resolve, 30));
        return makeResponse(201, {
          report_id: "report-1",
          status: "received",
          queued: true,
        });
      }
      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    const reportButton = await screen.findByRole("button", { name: "원인 신고" });
    fireEvent.click(reportButton);

    expect(await screen.findByTestId("reason-report-spinner-reason-success")).toBeInTheDocument();
    expect(reportButton).toBeDisabled();

    expect(await screen.findByText("원인 신고가 접수되었습니다.")).toBeInTheDocument();
    expect(screen.getByTestId("reason-report-status-badge-reason-success")).toHaveTextContent("접수됨");
    expect(await screen.findByText("근거 재검증 후 점수 조정 (2026-02-17T01:10:00Z)")).toBeInTheDocument();
    expect(screen.getByText("confidence 0.82 → 0.61 (-0.21)")).toBeInTheDocument();

    expect(screen.getByTestId("reason-revision-section")).toMatchSnapshot();
  });

  it("shows user-friendly duplicate submission error", async () => {
    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/watchlists/items" && method === "GET") {
        return makeResponse(200, { items: [], total: 0, page: 1, size: 20 });
      }
      if (url.pathname === "/v1/events" && method === "GET") {
        return makeResponse(200, { items: [baseEvent("evt-dup")], count: 1, next_cursor: null });
      }
      if (url.pathname === "/v1/events/evt-dup" && method === "GET") {
        return makeResponse(200, { event: detailEvent("evt-dup", "reason-dup") });
      }
      if (url.pathname === "/v1/events/evt-dup/reason-revisions" && method === "GET") {
        return makeResponse(404, {
          code: "reason_revision_history_not_found",
          message: "Reason revision history not found",
          details: { event_id: "evt-dup" },
        });
      }
      if (url.pathname === "/v1/events/evt-dup/reason-reports" && method === "POST") {
        return makeResponse(400, {
          code: "duplicate_reason_report",
          message: "An open reason report already exists for this reason",
          details: { event_id: "evt-dup", reason_id: "reason-dup" },
        });
      }
      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    const reportButton = await screen.findByRole("button", { name: "원인 신고" });
    fireEvent.click(reportButton);

    expect(await screen.findByText("이미 접수된 신고가 있어 처리 결과를 기다려 주세요.")).toBeInTheDocument();
    await waitFor(() => {
      expect(reportButton).not.toBeDisabled();
    });
  });

  it("shows offline guidance without submitting to API", async () => {
    let reportRequests = 0;
    vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(false);

    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/watchlists/items" && method === "GET") {
        return makeResponse(200, { items: [], total: 0, page: 1, size: 20 });
      }
      if (url.pathname === "/v1/events" && method === "GET") {
        return makeResponse(200, { items: [baseEvent("evt-offline")], count: 1, next_cursor: null });
      }
      if (url.pathname === "/v1/events/evt-offline" && method === "GET") {
        return makeResponse(200, { event: detailEvent("evt-offline", "reason-offline") });
      }
      if (url.pathname === "/v1/events/evt-offline/reason-revisions" && method === "GET") {
        return makeResponse(404, {
          code: "reason_revision_history_not_found",
          message: "Reason revision history not found",
          details: { event_id: "evt-offline" },
        });
      }
      if (url.pathname === "/v1/events/evt-offline/reason-reports" && method === "POST") {
        reportRequests += 1;
        return makeResponse(201, { report_id: "report-offline", status: "received", queued: true });
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    fireEvent.click(await screen.findByRole("button", { name: "원인 신고" }));

    expect(
      await screen.findByText("오프라인 상태에서는 신고를 보낼 수 없습니다. 네트워크를 확인해 주세요."),
    ).toBeInTheDocument();
    expect(reportRequests).toBe(0);
  });

  it("shows forbidden submission error guidance", async () => {
    const fetchImpl = vi.fn(async (input, init) => {
      const url = new URL(String(input));
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.pathname === "/v1/watchlists/items" && method === "GET") {
        return makeResponse(200, { items: [], total: 0, page: 1, size: 20 });
      }
      if (url.pathname === "/v1/events" && method === "GET") {
        return makeResponse(200, { items: [baseEvent("evt-forbidden")], count: 1, next_cursor: null });
      }
      if (url.pathname === "/v1/events/evt-forbidden" && method === "GET") {
        return makeResponse(200, { event: detailEvent("evt-forbidden", "reason-forbidden") });
      }
      if (url.pathname === "/v1/events/evt-forbidden/reason-revisions" && method === "GET") {
        return makeResponse(404, {
          code: "reason_revision_history_not_found",
          message: "Reason revision history not found",
          details: { event_id: "evt-forbidden" },
        });
      }
      if (url.pathname === "/v1/events/evt-forbidden/reason-reports" && method === "POST") {
        return makeResponse(403, {
          code: "forbidden",
          message: "Forbidden resource access",
          details: { event_id: "evt-forbidden" },
        });
      }

      throw new Error(`Unhandled request ${method} ${url.toString()}`);
    }) as unknown as typeof fetch;

    render(<WatchlistEventsDashboard client={buildDashboardClient(fetchImpl)} />);

    fireEvent.click(await screen.findByRole("button", { name: "원인 신고" }));

    expect(await screen.findByText("이 이벤트에 대한 신고 권한이 없습니다.")).toBeInTheDocument();
  });
});
