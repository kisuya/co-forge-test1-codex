import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/app-shell";
import { AuthScreen } from "@/components/auth-screen";
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

describe("auth shell flow", () => {
  it("login success saves token and triggers dashboard transition", async () => {
    const session = createMemorySession();
    const fetchImpl = vi.fn(async () => {
      return makeResponse(200, {
        user_id: "user-1",
        access_token: "token-1",
      });
    }) as unknown as typeof fetch;
    const client = createApiClient({
      baseUrl: "http://localhost:8000",
      session,
      fetchImpl,
    });
    const onAuthenticated = vi.fn();

    render(<AuthScreen mode="login" client={client} onAuthenticated={onAuthenticated} />);

    fireEvent.change(screen.getByLabelText("이메일"), {
      target: { value: "user@example.com" },
    });
    fireEvent.change(screen.getByLabelText("비밀번호"), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "로그인" }));

    await waitFor(() => {
      expect(onAuthenticated).toHaveBeenCalledTimes(1);
    });
    expect(session.get()).toEqual({
      userId: "user-1",
      accessToken: "token-1",
    });
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://localhost:8000/v1/auth/login",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("login failure renders field error and toast", async () => {
    const session = createMemorySession();
    const fetchImpl = vi.fn(async () => {
      return makeResponse(401, {
        code: "invalid_credentials",
        message: "Invalid email or password",
        details: {
          error: "email/password mismatch",
        },
        request_id: "req-1",
      });
    }) as unknown as typeof fetch;
    const client = createApiClient({
      baseUrl: "http://localhost:8000",
      session,
      fetchImpl,
    });

    render(<AuthScreen mode="login" client={client} onAuthenticated={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("이메일"), {
      target: { value: "user@example.com" },
    });
    fireEvent.change(screen.getByLabelText("비밀번호"), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "로그인" }));

    expect(await screen.findByText("Invalid email or password")).toBeInTheDocument();
    expect(screen.getByText("email/password mismatch")).toBeInTheDocument();
    expect(session.get()).toBeNull();
  });

  it("expired token clears session and shows re-login guidance", async () => {
    const session = createMemorySession({ userId: "user-1", accessToken: "expired-token" });
    const onSessionExpired = vi.fn();
    const fetchImpl = vi.fn(async () => {
      return makeResponse(401, {
        code: "invalid_token",
        message: "Invalid or expired access token",
        details: { error: "token expired" },
        request_id: "req-2",
      });
    }) as unknown as typeof fetch;
    const client = createApiClient({
      baseUrl: "http://localhost:8000",
      session,
      fetchImpl,
      onSessionExpired,
    });

    render(
      <AppShell client={client} session={session}>
        <div>dashboard</div>
      </AppShell>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "세션이 만료되었습니다. 다시 로그인하세요.",
    );
    expect(session.get()).toBeNull();
    expect(onSessionExpired).toHaveBeenCalledTimes(1);
  });
});
