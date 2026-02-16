"use client";

import { type ReactNode, useEffect, useMemo, useState } from "react";

import {
  ApiClientError,
  SessionExpiredError,
  type ApiClient,
  type AuthMeResponse,
} from "@/lib/api-client";
import type { AuthSession } from "@/lib/auth-session";

type ShellStatus = "loading" | "authenticated" | "anonymous" | "expired" | "error";

type AppShellProps = {
  client: ApiClient;
  session: AuthSession;
  children: ReactNode;
};

export function AppShell({ client, session, children }: AppShellProps): JSX.Element {
  const [status, setStatus] = useState<ShellStatus>("loading");
  const [user, setUser] = useState<AuthMeResponse["user"] | null>(null);
  const [message, setMessage] = useState<string>("");

  useEffect(() => {
    let isCancelled = false;

    async function bootstrap(): Promise<void> {
      if (!session.get()?.accessToken) {
        setStatus("anonymous");
        return;
      }

      try {
        const response = await client.getMe();
        if (!isCancelled) {
          setUser(response.user);
          setStatus("authenticated");
        }
      } catch (error) {
        if (isCancelled) {
          return;
        }
        if (error instanceof SessionExpiredError) {
          setStatus("expired");
          setMessage("세션이 만료되었습니다. 다시 로그인하세요.");
          return;
        }
        if (error instanceof ApiClientError) {
          setStatus("error");
          setMessage(error.payload.message);
          return;
        }
        setStatus("error");
        setMessage("세션 확인 중 오류가 발생했습니다.");
      }
    }

    void bootstrap();

    return () => {
      isCancelled = true;
    };
  }, [client, session]);

  const subtitle = useMemo(() => {
    if (!user) {
      return "실시간 급등락 이벤트를 확인하세요";
    }
    return `${user.email ?? user.id} 계정으로 로그인됨`;
  }, [user]);

  function renderBody(): JSX.Element {
    if (status === "loading") {
      return <p>세션 확인 중...</p>;
    }
    if (status === "anonymous") {
      return (
        <p>
          로그인이 필요합니다. <a href="/login">로그인</a>
        </p>
      );
    }
    if (status === "expired") {
      return (
        <p role="alert">
          {message} <a href="/login">다시 로그인</a>
        </p>
      );
    }
    if (status === "error") {
      return <p role="alert">{message}</p>;
    }

    return <>{children}</>;
  }

  return (
    <div style={{ minHeight: "100vh", background: "#f8fafc", color: "#0f172a" }}>
      <header style={{ borderBottom: "1px solid #cbd5e1", background: "#fff" }}>
        <div style={{ maxWidth: 960, margin: "0 auto", padding: "16px 24px" }}>
          <h1 style={{ margin: 0, fontSize: 24 }}>oh-my-stock</h1>
          <p style={{ margin: "6px 0 0", color: "#334155" }}>{subtitle}</p>
        </div>
      </header>
      <main style={{ maxWidth: 960, margin: "0 auto", padding: 24 }}>{renderBody()}</main>
    </div>
  );
}
