"use client";

import { useEffect, useMemo, useState } from "react";

import { ReasonFeedbackButtons } from "@/components/reason-feedback-buttons";
import { Toast } from "@/components/toast";
import { WatchlistComposer } from "@/components/watchlist-composer";
import {
  ApiClientError,
  type ApiClient,
  type EventPayload,
  type EventReason,
} from "@/lib/api-client";

type LoadStatus = "loading" | "success" | "error";
type DetailStatus = "idle" | "loading" | "success" | "error";
type UiError = { message: string; retryable: boolean };

type DashboardProps = {
  client: ApiClient;
};

function isAccessibleExternalUrl(sourceUrl: string | null): sourceUrl is string {
  if (!sourceUrl) {
    return false;
  }
  try {
    const parsed = new URL(sourceUrl);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function ReasonSourceLink({ reason }: { reason: EventReason }): JSX.Element {
  if (isAccessibleExternalUrl(reason.source_url)) {
    return (
      <a href={reason.source_url} target="_blank" rel="noopener noreferrer" style={{ color: "#1d4ed8" }}>
        근거 원문 보기
      </a>
    );
  }

  return (
    <span aria-disabled="true" style={{ color: "#64748b" }}>
      접근 불가 링크
    </span>
  );
}

function toUiError(error: unknown, fallbackMessage: string): UiError {
  if (error instanceof ApiClientError) {
    return {
      message: error.payload.message || fallbackMessage,
      retryable: Boolean(error.payload.retryable ?? error.payload.details?.retryable),
    };
  }
  return {
    message: fallbackMessage,
    retryable: false,
  };
}

export function WatchlistEventsDashboard({ client }: DashboardProps): JSX.Element {
  const [eventsStatus, setEventsStatus] = useState<LoadStatus>("loading");
  const [events, setEvents] = useState<EventPayload[]>([]);
  const [eventsError, setEventsError] = useState<UiError | null>(null);

  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [detailStatus, setDetailStatus] = useState<DetailStatus>("idle");
  const [detailEvent, setDetailEvent] = useState<EventPayload | null>(null);
  const [detailError, setDetailError] = useState<UiError | null>(null);

  const [toast, setToast] = useState<{ kind: "error" | "success"; message: string } | null>(null);

  async function loadEvents(): Promise<void> {
    setEventsStatus("loading");
    setEventsError(null);
    try {
      const response = await client.listEvents({ size: 20 });
      setEvents(response.items);
      setEventsStatus("success");
      if (response.items.length > 0) {
        setSelectedEventId((previous) => previous ?? response.items[0].id);
      }
    } catch (error) {
      setEventsError(toUiError(error, "이벤트를 불러오지 못했습니다."));
      setEventsStatus("error");
    }
  }

  useEffect(() => {
    void loadEvents();
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadDetail(eventId: string): Promise<void> {
      setDetailStatus("loading");
      setDetailError(null);
      try {
        const response = await client.getEventDetail(eventId);
        if (!cancelled) {
          setDetailEvent(response.event);
          setDetailStatus("success");
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        setDetailError(toUiError(error, "이벤트 상세를 불러오지 못했습니다."));
        setDetailStatus("error");
      }
    }

    if (!selectedEventId) {
      setDetailEvent(null);
      setDetailStatus("idle");
      return;
    }

    void loadDetail(selectedEventId);

    return () => {
      cancelled = true;
    };
  }, [client, selectedEventId]);

  const selectedEvent = useMemo(
    () => events.find((event) => event.id === selectedEventId) ?? detailEvent,
    [detailEvent, events, selectedEventId],
  );

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <WatchlistComposer client={client} onToast={setToast} />

      <section style={{ border: "1px solid #cbd5e1", borderRadius: 12, background: "#fff", padding: 16 }}>
        <h2 style={{ marginTop: 0 }}>이벤트 피드</h2>
        {eventsStatus === "loading" ? <p data-testid="events-loading">이벤트 로딩 중...</p> : null}
        {eventsStatus === "error" && eventsError ? (
          <div role="alert">
            <p>{eventsError.message}</p>
            <p>{eventsError.retryable ? "재시도 가능한 오류입니다." : "재시도 불가 오류입니다."}</p>
            {eventsError.retryable ? (
              <button type="button" onClick={() => void loadEvents()}>
                다시 시도
              </button>
            ) : null}
          </div>
        ) : null}
        {eventsStatus === "success" && events.length === 0 ? <p data-testid="events-empty">최근 이벤트가 없습니다.</p> : null}
        {eventsStatus === "success" && events.length > 0 ? (
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {events.map((event) => (
              <li key={event.id}>
                <button type="button" onClick={() => setSelectedEventId(event.id)}>
                  {event.market}:{event.symbol} ({event.change_pct.toFixed(2)}%)
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section style={{ border: "1px solid #cbd5e1", borderRadius: 12, background: "#fff", padding: 16 }}>
        <h2 style={{ marginTop: 0 }}>이벤트 상세</h2>
        {!selectedEvent ? <p>선택된 이벤트가 없습니다.</p> : null}
        {detailStatus === "loading" ? <p>상세 로딩 중...</p> : null}
        {detailStatus === "error" && detailError ? <p role="alert">{detailError.message}</p> : null}
        {detailStatus === "success" && detailEvent ? (
          <div>
            <p>
              <strong>{detailEvent.market}:{detailEvent.symbol}</strong> {detailEvent.change_pct.toFixed(2)}%
            </p>
            {detailEvent.reasons.length === 0 ? <p>근거 수집 중입니다.</p> : null}
            {detailEvent.reasons.length > 0 ? (
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {detailEvent.reasons.map((reason) => (
                  <li key={`${detailEvent.id}-${reason.rank}`}>
                    <p style={{ margin: "0 0 4px" }}>{reason.summary}</p>
                    <ReasonSourceLink reason={reason} />
                    <ReasonFeedbackButtons
                      client={client}
                      eventId={detailEvent.id}
                      reasonId={reason.id}
                      onToast={setToast}
                    />
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </section>

      {toast ? <Toast kind={toast.kind} message={toast.message} /> : null}
    </div>
  );
}
