"use client";

import { useEffect, useMemo, useState } from "react";

import {
  ApiClientError,
  type ApiClient,
  type ReasonReportStatus,
  type ReasonRevisionHistoryResponse,
} from "@/lib/api-client";

type TimelineError = {
  message: string;
  retryable: boolean;
};

type TimelineLoadStatus = "loading" | "success" | "empty" | "error";

type ReasonRevisionTimelineProps = {
  client: ApiClient;
  eventId: string;
  reloadToken: number;
  onStatusesUpdated?: (statuses: Record<string, ReasonReportStatus>) => void;
};

const STATUS_LABELS: Record<ReasonReportStatus, string> = {
  received: "접수됨",
  reviewed: "검토 중",
  resolved: "정정 완료",
};

function mapStatusByReason(response: ReasonRevisionHistoryResponse): Record<string, ReasonReportStatus> {
  const result: Record<string, ReasonReportStatus> = {};
  for (const transition of response.status_transitions) {
    result[transition.reason_id] = transition.to_status;
  }
  return result;
}

function toTimelineError(error: unknown): TimelineError {
  if (error instanceof ApiClientError) {
    if (error.payload.code === "forbidden" || error.status === 403) {
      return {
        message: "이 이벤트의 정정 이력을 조회할 권한이 없습니다.",
        retryable: false,
      };
    }
    return {
      message: error.payload.message || "정정 이력을 불러오지 못했습니다.",
      retryable: Boolean(error.payload.retryable ?? error.payload.details?.retryable),
    };
  }
  return {
    message: "정정 이력을 불러오지 못했습니다.",
    retryable: false,
  };
}

function formatDelta(before: number, after: number): string {
  const delta = after - before;
  const sign = delta > 0 ? "+" : "";
  return `${sign}${delta.toFixed(2)}`;
}

export function ReasonRevisionTimeline({
  client,
  eventId,
  reloadToken,
  onStatusesUpdated,
}: ReasonRevisionTimelineProps): JSX.Element {
  const [status, setStatus] = useState<TimelineLoadStatus>("loading");
  const [history, setHistory] = useState<ReasonRevisionHistoryResponse | null>(null);
  const [error, setError] = useState<TimelineError | null>(null);

  async function loadTimeline(): Promise<void> {
    setStatus("loading");
    setError(null);
    try {
      const response = await client.listReasonRevisions(eventId);
      setHistory(response);
      onStatusesUpdated?.(mapStatusByReason(response));
      setStatus("success");
    } catch (caughtError) {
      if (caughtError instanceof ApiClientError && caughtError.payload.code === "reason_revision_history_not_found") {
        setHistory(null);
        onStatusesUpdated?.({});
        setStatus("empty");
        return;
      }
      setHistory(null);
      setError(toTimelineError(caughtError));
      setStatus("error");
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function run(): Promise<void> {
      setStatus("loading");
      setError(null);
      try {
        const response = await client.listReasonRevisions(eventId);
        if (cancelled) {
          return;
        }
        setHistory(response);
        onStatusesUpdated?.(mapStatusByReason(response));
        setStatus("success");
      } catch (caughtError) {
        if (cancelled) {
          return;
        }
        if (caughtError instanceof ApiClientError && caughtError.payload.code === "reason_revision_history_not_found") {
          setHistory(null);
          onStatusesUpdated?.({});
          setStatus("empty");
          return;
        }
        setHistory(null);
        setError(toTimelineError(caughtError));
        setStatus("error");
      }
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [client, eventId, reloadToken, onStatusesUpdated]);

  const transitionItems = useMemo(() => history?.status_transitions ?? [], [history]);
  const revisionItems = useMemo(() => history?.revision_history ?? [], [history]);

  return (
    <section
      data-testid="reason-revision-section"
      style={{ borderTop: "1px solid #e2e8f0", paddingTop: 12, display: "grid", gap: 8 }}
    >
      <h3 style={{ margin: 0, fontSize: 15 }}>정정 이력</h3>
      {status === "loading" ? <p data-testid="reason-revision-loading">정정 이력을 불러오는 중...</p> : null}
      {status === "empty" ? <p data-testid="reason-revision-empty">정정 이력이 아직 없습니다.</p> : null}
      {status === "error" && error ? (
        <div role="alert" style={{ display: "grid", gap: 6 }}>
          <p style={{ margin: 0 }}>{error.message}</p>
          {error.retryable ? (
            <button
              type="button"
              onClick={() => void loadTimeline()}
              style={{
                justifySelf: "start",
                border: "1px solid #cbd5e1",
                borderRadius: 8,
                background: "#fff",
                padding: "4px 8px",
              }}
            >
              정정 이력 다시 시도
            </button>
          ) : null}
        </div>
      ) : null}
      {status === "success" ? (
        <div style={{ display: "grid", gap: 10 }}>
          <div style={{ display: "grid", gap: 6 }}>
            <h4 style={{ margin: 0, fontSize: 14 }}>신고 처리 상태</h4>
            {transitionItems.length === 0 ? (
              <p style={{ margin: 0 }}>신고 상태 기록이 없습니다.</p>
            ) : (
              <ol data-testid="reason-status-transition-list" style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 6 }}>
                {transitionItems.map((item) => (
                  <li key={`${item.report_id}-${item.to_status}-${item.changed_at_utc}`}>
                    <strong>{STATUS_LABELS[item.to_status]}</strong> · {item.changed_at_utc}
                    {item.note ? ` · ${item.note}` : ""}
                  </li>
                ))}
              </ol>
            )}
          </div>
          <div style={{ display: "grid", gap: 6 }}>
            <h4 style={{ margin: 0, fontSize: 14 }}>정정 완료 타임라인</h4>
            {revisionItems.length === 0 ? (
              <p data-testid="reason-revision-pending" style={{ margin: 0 }}>
                정정 완료 이력이 아직 없습니다.
              </p>
            ) : (
              <ul data-testid="reason-revision-timeline" style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 6 }}>
                {revisionItems.map((item) => (
                  <li key={item.id}>
                    <p style={{ margin: 0 }}>
                      {item.revision_reason} ({item.revised_at_utc})
                    </p>
                    <p style={{ margin: 0, color: "#334155", fontSize: 13 }}>
                      confidence {item.confidence_before.toFixed(2)} → {item.confidence_after.toFixed(2)} (
                      {formatDelta(item.confidence_before, item.confidence_after)})
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}
