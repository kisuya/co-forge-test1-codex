"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";

import { ApiClientError, type ApiClient } from "@/lib/api-client";
import { Toast } from "@/components/toast";

type AuthMode = "login" | "signup";

type FieldErrorState = {
  email?: string;
  password?: string;
};

type AuthScreenProps = {
  mode: AuthMode;
  client: ApiClient;
  onAuthenticated: () => void;
};

function normalizeFieldErrors(error: ApiClientError): FieldErrorState {
  const fieldErrors: FieldErrorState = {};
  const detailError = error.payload.details?.error;

  if (typeof detailError === "string") {
    if (error.payload.code === "email_already_exists") {
      fieldErrors.email = detailError;
    } else if (error.payload.code === "invalid_credentials") {
      fieldErrors.password = detailError;
    } else {
      fieldErrors.email = detailError;
      fieldErrors.password = detailError;
    }
  }

  if (!fieldErrors.email && error.payload.code === "email_already_exists") {
    fieldErrors.email = "이미 가입된 이메일입니다.";
  }
  if (!fieldErrors.password && error.payload.code === "invalid_credentials") {
    fieldErrors.password = "이메일 또는 비밀번호를 확인하세요.";
  }

  return fieldErrors;
}

function validateInput(email: string, password: string): FieldErrorState {
  const errors: FieldErrorState = {};
  if (!email.trim() || !email.includes("@")) {
    errors.email = "유효한 이메일을 입력하세요.";
  }
  if (password.length < 8) {
    errors.password = "비밀번호는 8자 이상이어야 합니다.";
  }
  return errors;
}

export function AuthScreen({ mode, client, onAuthenticated }: AuthScreenProps): JSX.Element {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrorState>({});
  const [toast, setToast] = useState<{ kind: "error" | "success"; message: string } | null>(null);
  const [isSubmitting, setSubmitting] = useState(false);
  const [isHydrated, setHydrated] = useState(process.env.NODE_ENV === "test");

  const isLogin = mode === "login";
  const headline = useMemo(() => (isLogin ? "로그인" : "회원가입"), [isLogin]);
  const submitLabel = isSubmitting ? "처리 중..." : isHydrated ? headline : "준비 중...";

  useEffect(() => {
    setHydrated(true);
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const validationErrors = validateInput(email, password);
    setFieldErrors(validationErrors);
    setToast(null);

    if (validationErrors.email || validationErrors.password) {
      return;
    }

    setSubmitting(true);
    try {
      if (isLogin) {
        await client.login({ email, password });
      } else {
        await client.signup({ email, password });
      }
      setToast({ kind: "success", message: `${headline}에 성공했습니다.` });
      onAuthenticated();
    } catch (error) {
      if (error instanceof ApiClientError) {
        setFieldErrors(normalizeFieldErrors(error));
        setToast({ kind: "error", message: error.payload.message });
      } else {
        setToast({ kind: "error", message: "요청 처리 중 오류가 발생했습니다." });
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
      <section
        style={{
          width: "100%",
          maxWidth: 420,
          border: "1px solid #e5e7eb",
          borderRadius: 12,
          padding: 24,
          background: "#fff",
        }}
      >
        <h1 style={{ fontSize: 28, marginBottom: 16 }}>{headline}</h1>
        <form onSubmit={onSubmit} noValidate>
          <label htmlFor="email" style={{ display: "block", marginBottom: 6 }}>
            이메일
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.currentTarget.value)}
            disabled={isSubmitting || !isHydrated}
            style={{ width: "100%", padding: 10, borderRadius: 8, border: "1px solid #d1d5db" }}
          />
          {fieldErrors.email ? (
            <p role="alert" style={{ color: "#b91c1c", marginTop: 4 }}>
              {fieldErrors.email}
            </p>
          ) : null}

          <label htmlFor="password" style={{ display: "block", marginTop: 14, marginBottom: 6 }}>
            비밀번호
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete={isLogin ? "current-password" : "new-password"}
            value={password}
            onChange={(event) => setPassword(event.currentTarget.value)}
            disabled={isSubmitting || !isHydrated}
            style={{ width: "100%", padding: 10, borderRadius: 8, border: "1px solid #d1d5db" }}
          />
          {fieldErrors.password ? (
            <p role="alert" style={{ color: "#b91c1c", marginTop: 4 }}>
              {fieldErrors.password}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={isSubmitting || !isHydrated}
            style={{
              marginTop: 16,
              width: "100%",
              border: "none",
              borderRadius: 8,
              padding: 12,
              color: "#fff",
              background: isSubmitting || !isHydrated ? "#475569" : "#0f172a",
              fontWeight: 600,
              cursor: isSubmitting || !isHydrated ? "not-allowed" : "pointer",
            }}
          >
            {submitLabel}
          </button>
        </form>

        <p style={{ marginTop: 16, fontSize: 14 }}>
          {isLogin ? "계정이 없나요?" : "이미 계정이 있나요?"} {" "}
          <a href={isLogin ? "/signup" : "/login"} style={{ color: "#1d4ed8" }}>
            {isLogin ? "회원가입" : "로그인"}
          </a>
        </p>

        {toast ? <Toast kind={toast.kind} message={toast.message} /> : null}
      </section>
    </main>
  );
}
