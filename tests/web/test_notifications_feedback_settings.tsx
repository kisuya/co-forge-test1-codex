import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReasonFeedbackButtons } from "@/components/reason-feedback-buttons";
import { SettingsCenter } from "@/components/settings-center";
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

describe("notifications, feedback and settings flow", () => {
  it("applies successful notification read and threshold save immediately", async () => {
    const notifications = [
      {
        id: "noti-1",
        user_id: "user-1",
        event_id: "evt-1",
        channel: "in_app",
        status: "sent",
        message: "AAPL 급등 이벤트",
        sent_at_utc: "2026-02-17T02:00:00Z",
      },
    ];
    const thresholds = [
      {
        user_id: "user-1",
        window_minutes: 5,
        threshold_pct: 3,
      },
    ];

    const fetchImpl = vi.fn(async (input, init) => {
      const url = String(input);
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.endsWith("/v1/notifications") && method === "GET") {
        const unread = notifications.filter((item) => item.status !== "read").length;
        return makeResponse(200, { items: [...notifications], unread_count: unread });
      }

      if (url.endsWith("/v1/notifications/noti-1/read") && method === "PATCH") {
        notifications[0] = {
          ...notifications[0],
          status: "read",
        };
        return makeResponse(200, {
          notification: notifications[0],
          unread_count: 0,
        });
      }

      if (url.endsWith("/v1/thresholds") && method === "GET") {
        return makeResponse(200, {
          items: [...thresholds],
          count: thresholds.length,
        });
      }

      if (url.endsWith("/v1/thresholds") && method === "POST") {
        const body = JSON.parse(String(init?.body ?? "{}")) as {
          window_minutes: number;
          threshold_pct: number;
        };
        thresholds[0] = {
          user_id: "user-1",
          window_minutes: body.window_minutes,
          threshold_pct: body.threshold_pct,
        };
        return makeResponse(200, {
          threshold: thresholds[0],
        });
      }

      throw new Error(`Unhandled request ${method} ${url}`);
    }) as unknown as typeof fetch;

    render(<SettingsCenter client={buildClient(fetchImpl)} />);

    expect(await screen.findByText("AAPL 급등 이벤트")).toBeInTheDocument();
    expect(screen.getByText("5분: ±3%")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "읽음" }));

    await waitFor(() => {
      expect(screen.getByText("read")).toBeInTheDocument();
      expect(screen.getByText("알림을 읽음 처리했습니다.")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("임계값 퍼센트"), {
      target: { value: "4.5" },
    });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => {
      expect(screen.getByText("5분: ±4.5%")).toBeInTheDocument();
      expect(screen.getByText("임계값이 저장되었습니다.")).toBeInTheDocument();
    });
  });

  it("rolls back optimistic feedback state on failure and shows error", async () => {
    const fetchImpl = vi.fn(async (input, init) => {
      const url = String(input);
      const method = String(init?.method ?? "GET").toUpperCase();

      if (url.endsWith("/v1/events/evt-1/feedback") && method === "POST") {
        return makeResponse(400, {
          code: "invalid_input",
          message: "Invalid feedback payload",
          details: { error: "invalid reason_id" },
        });
      }

      throw new Error(`Unhandled request ${method} ${url}`);
    }) as unknown as typeof fetch;

    const client = buildClient(fetchImpl);
    const onToast = vi.fn();

    render(
      <ReasonFeedbackButtons
        client={client}
        eventId="evt-1"
        reasonId="reason-1"
        onToast={onToast}
      />,
    );

    const helpfulButton = screen.getByRole("button", { name: "도움됨" });
    expect(helpfulButton).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(helpfulButton);
    expect(helpfulButton).toHaveAttribute("aria-pressed", "true");

    await waitFor(() => {
      expect(helpfulButton).toHaveAttribute("aria-pressed", "false");
      expect(onToast).toHaveBeenCalledWith({
        kind: "error",
        message: "Invalid feedback payload",
      });
    });
  });
});
