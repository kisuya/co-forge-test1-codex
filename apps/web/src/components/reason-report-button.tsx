"use client";

import { useEffect, useState } from "react";

import { ApiClientError, type ApiClient, type ReasonReportStatus } from "@/lib/api-client";

type ToastPayload = { kind: "error" | "success"; message: string };

type ReasonReportButtonProps = {
  client: ApiClient;
  eventId: string;
  reasonId: string;
  initialStatus?: ReasonReportStatus | null;
  onStatusChange?: (status: ReasonReportStatus) => void;
  onSubmitted?: () => void;
  onToast: (toast: ToastPayload) => void;
};

const STATUS_LABELS: Record<ReasonReportStatus, string> = {
  received: "접수됨",
  reviewed: "검토 중",
  resolved: "정정 완료",
};

const STATUS_STYLES: Record<ReasonReportStatus, { background: string; color: string }> = {
  received: { background: "#dbeafe", color: "#1e3a8a" },
  reviewed: { background: "#fef3c7", color: "#92400e" },
  resolved: { background: "#dcfce7", color: "#166534" },
};

function isOfflineBrowser(): boolean {
  return typeof navigator !== "undefined" && navigator.onLine === false;
}

function isNetworkFailure(error: unknown): boolean {
  if (error instanceof TypeError) {
    return true;
  }
  if (error instanceof Error) {
    return /network|fetch/i.test(error.message);
  }
  return false;
}

function mapReportErrorMessage(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.payload.code === "duplicate_reason_report") {
      return "이미 접수된 신고가 있어 처리 결과를 기다려 주세요.";
    }
    if (error.payload.code === "forbidden" || error.status === 403) {
      return "이 이벤트에 대한 신고 권한이 없습니다.";
    }
    if (error.payload.code === "reason_not_found") {
      return "신고 대상 원인을 찾을 수 없습니다. 새로고침 후 다시 시도해 주세요.";
    }
    return error.payload.message || "원인 신고 처리 중 오류가 발생했습니다.";
  }
  if (isNetworkFailure(error)) {
    return "네트워크 연결이 불안정합니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.";
  }
  return "원인 신고 처리 중 오류가 발생했습니다.";
}

function canSubmit(status: ReasonReportStatus | null): boolean {
  return status !== "received" && status !== "reviewed";
}

export function ReasonReportButton({
  client,
  eventId,
  reasonId,
  initialStatus = null,
  onStatusChange,
  onSubmitted,
  onToast,
}: ReasonReportButtonProps): JSX.Element {
  const [status, setStatus] = useState<ReasonReportStatus | null>(initialStatus);
  const [isSubmitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (initialStatus) {
      setStatus(initialStatus);
    }
  }, [initialStatus]);

  async function submitReasonReport(): Promise<void> {
    if (isSubmitting || !canSubmit(status)) {
      return;
    }
    if (isOfflineBrowser()) {
      onToast({
        kind: "error",
        message: "오프라인 상태에서는 신고를 보낼 수 없습니다. 네트워크를 확인해 주세요.",
      });
      return;
    }

    setSubmitting(true);
    try {
      const response = await client.submitReasonReport({
        eventId,
        reasonId,
        reportType: "inaccurate_reason",
      });
      setStatus(response.status);
      onStatusChange?.(response.status);
      onSubmitted?.();
      onToast({
        kind: "success",
        message: "원인 신고가 접수되었습니다.",
      });
    } catch (error) {
      onToast({ kind: "error", message: mapReportErrorMessage(error) });
    } finally {
      setSubmitting(false);
    }
  }

  const disabled = isSubmitting || !canSubmit(status);

  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <button
        type="button"
        disabled={disabled}
        data-testid={`reason-report-button-${reasonId}`}
        onClick={() => void submitReasonReport()}
        style={{
          border: "1px solid #cbd5e1",
          borderRadius: 8,
          background: "#fff",
          color: "#0f172a",
          padding: "6px 10px",
          cursor: disabled ? "not-allowed" : "pointer",
        }}
      >
        원인 신고
      </button>
      {isSubmitting ? (
        <span role="status" data-testid={`reason-report-spinner-${reasonId}`} style={{ fontSize: 12, color: "#334155" }}>
          신고 처리 중...
        </span>
      ) : null}
      {status ? (
        <span
          data-testid={`reason-report-status-badge-${reasonId}`}
          aria-live="polite"
          style={{
            padding: "3px 8px",
            borderRadius: 999,
            fontSize: 12,
            fontWeight: 700,
            background: STATUS_STYLES[status].background,
            color: STATUS_STYLES[status].color,
          }}
        >
          {STATUS_LABELS[status]}
        </span>
      ) : null}
    </div>
  );
}
