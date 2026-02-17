"use client";
import { useEffect, useMemo, useState } from "react";
import { BriefInboxSection } from "@/components/brief-inbox-section";
import { ApiClientError, type ApiClient, type BriefDetailResponse, type BriefSummaryItem } from "@/lib/api-client";
type LoadStatus = "loading" | "success" | "error";
type DetailStatus = "idle" | "loading" | "success" | "error";
type ViewLayout = "mobile" | "desktop";
type UiError = {
  code: string;
  message: string;
  retryable: boolean;
};
type BriefInboxProps = {
  client: ApiClient;
};
function toUiError(error: unknown, fallbackMessage: string): UiError {
  if (error instanceof ApiClientError) {
    return {
      code: error.payload.code || "unknown_error",
      message: error.payload.message || fallbackMessage,
      retryable: Boolean(error.payload.retryable ?? error.payload.details?.retryable),
    };
  }
  return { code: "unknown_error", message: fallbackMessage, retryable: false };
}
function toFallbackMessage(fallbackReason: string | null): string | null {
  if (!fallbackReason) {
    return null;
  }
  if (fallbackReason === "insufficient_data") {
    return "브리프 생성 데이터가 부족해 핵심 항목을 표시하지 못했습니다.";
  }
  if (fallbackReason === "no_events") {
    return "요약할 이벤트가 없어 빈 브리프로 표시됩니다.";
  }
  if (fallbackReason === "market_holiday") {
    return "휴장일이라 브리프 항목이 비어 있습니다.";
  }
  if (fallbackReason === "partial_aggregation") {
    return "일부 집계가 지연되어 항목이 축소되었습니다.";
  }
  return `브리프 상태: ${fallbackReason}`;
}
function toGeneratedAtLabel(value: string): string {
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return value;
  }
  return new Date(parsed).toLocaleString("ko-KR", { hour12: false });
}
function layoutFromViewport(): ViewLayout {
  if (typeof window === "undefined") {
    return "desktop";
  }
  return window.innerWidth <= 768 ? "mobile" : "desktop";
}
export function BriefInbox({ client }: BriefInboxProps): JSX.Element {
  const [listStatus, setListStatus] = useState<LoadStatus>("loading");
  const [briefs, setBriefs] = useState<BriefSummaryItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [listError, setListError] = useState<UiError | null>(null);
  const [selectedBriefId, setSelectedBriefId] = useState<string | null>(null);
  const [detailRequestNonce, setDetailRequestNonce] = useState(0);
  const [detailStatus, setDetailStatus] = useState<DetailStatus>("idle");
  const [detail, setDetail] = useState<BriefDetailResponse["brief"] | null>(null);
  const [detailError, setDetailError] = useState<UiError | null>(null);
  const [layout, setLayout] = useState<ViewLayout>(() => layoutFromViewport());

  const selectedBrief = useMemo(
    () => briefs.find((brief) => brief.id === selectedBriefId) ?? null,
    [briefs, selectedBriefId],
  );

  const preMarketBriefs = useMemo(
    () => briefs.filter((brief) => brief.brief_type === "pre_market"),
    [briefs],
  );
  const postCloseBriefs = useMemo(
    () => briefs.filter((brief) => brief.brief_type === "post_close"),
    [briefs],
  );

  useEffect(() => {
    function handleResize(): void {
      setLayout(layoutFromViewport());
    }
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  async function loadBriefs(): Promise<void> {
    setListStatus("loading");
    setListError(null);
    try {
      const response = await client.listBriefs({ size: 20 });
      setBriefs(response.items);
      setUnreadCount(response.meta.unread_count);
      setListStatus("success");
    } catch (error) {
      setListError(toUiError(error, "브리프 목록을 불러오지 못했습니다."));
      setListStatus("error");
    }
  }

  useEffect(() => {
    void loadBriefs();
  }, []);

  useEffect(() => {
    if (briefs.length === 0) {
      setSelectedBriefId(null);
      setDetail(null);
      setDetailStatus("idle");
      setDetailError(null);
      return;
    }

    const selectedExists = selectedBriefId && briefs.some((brief) => brief.id === selectedBriefId);
    if (!selectedExists) {
      setSelectedBriefId(briefs[0]?.id ?? null);
    }
  }, [briefs, selectedBriefId]);

  useEffect(() => {
    let cancelled = false;

    async function loadBriefDetail(briefId: string): Promise<void> {
      setDetailStatus("loading");
      setDetailError(null);
      try {
        const response = await client.getBriefDetail(briefId);
        if (cancelled) {
          return;
        }

        let updatedBrief = response.brief;
        if (updatedBrief.status === "unread") {
          try {
            const markRead = await client.markBriefRead(briefId);
            if (cancelled) {
              return;
            }
            setUnreadCount(markRead.unread_count);
            setBriefs((items) =>
              items.map((item) =>
                item.id === briefId
                  ? {
                      ...item,
                      status: "read",
                    }
                  : item,
              ),
            );
            updatedBrief = {
              ...updatedBrief,
              status: markRead.brief.status,
            };
          } catch {
            // Ignore read-state update failure and keep detail content visible.
          }
        }

        setDetail(updatedBrief);
        setDetailStatus("success");
      } catch (error) {
        if (cancelled) {
          return;
        }
        setDetail(null);
        setDetailStatus("error");
        setDetailError(toUiError(error, "브리프 상세를 불러오지 못했습니다."));
      }
    }

    if (!selectedBriefId) {
      setDetailStatus("idle");
      setDetail(null);
      return;
    }

    void loadBriefDetail(selectedBriefId);
    return () => {
      cancelled = true;
    };
  }, [client, selectedBriefId, detailRequestNonce]);

  const detailFallbackMessage = toFallbackMessage(detail?.fallback_reason ?? null);

  return (
    <section style={{ border: "1px solid #cbd5e1", borderRadius: 12, background: "#fff", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>브리프 인박스</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span data-testid="brief-unread-count">읽지 않음 {unreadCount}</span>
          <button type="button" onClick={() => void loadBriefs()}>
            새로고침
          </button>
        </div>
      </div>

      {listStatus === "loading" ? <p data-testid="brief-list-loading">브리프 목록 로딩 중...</p> : null}
      {listStatus === "error" && listError ? (
        <div role="alert">
          <p>{listError.message}</p>
          {listError.retryable ? <button type="button" onClick={() => void loadBriefs()}>다시 시도</button> : null}
        </div>
      ) : null}
      {listStatus === "success" && briefs.length === 0 ? <p data-testid="brief-empty">도착한 브리프가 없습니다.</p> : null}

      {listStatus === "success" && briefs.length > 0 ? (
        <div
          data-testid="brief-inbox"
          data-layout={layout}
          style={{
            marginTop: 12,
            display: "grid",
            gap: 12,
            gridTemplateColumns: layout === "mobile" ? "1fr" : "minmax(280px, 360px) 1fr",
          }}
        >
          <div style={{ display: "grid", gap: 12 }}>
            <BriefInboxSection
              title="개장 전 브리프"
              emptyMessage="개장 전 브리프가 없습니다."
              briefs={preMarketBriefs}
              selectedBriefId={selectedBriefId}
              onSelect={setSelectedBriefId}
              testId="brief-section-pre"
              toGeneratedAtLabel={toGeneratedAtLabel}
            />
            <BriefInboxSection
              title="장마감 브리프"
              emptyMessage="장마감 브리프가 없습니다."
              briefs={postCloseBriefs}
              selectedBriefId={selectedBriefId}
              onSelect={setSelectedBriefId}
              testId="brief-section-post"
              toGeneratedAtLabel={toGeneratedAtLabel}
            />
          </div>

          <div style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: 12, minHeight: 200 }}>
            {!selectedBrief ? <p>선택된 브리프가 없습니다.</p> : null}
            {detailStatus === "loading" ? <p data-testid="brief-detail-loading">브리프 상세 로딩 중...</p> : null}
            {detailStatus === "error" && detailError ? (
              <div role="alert">
                {detailError.code === "brief_link_expired" ? (
                  <p data-testid="brief-detail-expired">브리프 링크가 만료되었습니다. 최신 브리프를 확인하세요.</p>
                ) : (
                  <p>{detailError.message}</p>
                )}
                {detailError.retryable ? (
                  <button type="button" onClick={() => setDetailRequestNonce((value) => value + 1)}>
                    상세 다시 시도
                  </button>
                ) : null}
              </div>
            ) : null}
            {detailStatus === "success" && detail ? (
              <div style={{ display: "grid", gap: 8 }}>
                <h3 data-testid="brief-detail-title" style={{ margin: 0 }}>
                  {detail.title}
                </h3>
                <p style={{ margin: 0, color: "#334155" }}>{detail.summary}</p>
                <p style={{ margin: 0, color: "#334155" }}>생성 시각: {toGeneratedAtLabel(detail.generated_at_utc)}</p>
                {detailFallbackMessage ? (
                  <p data-testid="brief-detail-fallback" style={{ margin: 0, color: "#7c2d12" }}>
                    {detailFallbackMessage}
                  </p>
                ) : null}
                {detail.items.length === 0 ? <p data-testid="brief-detail-empty">브리프 항목이 없습니다.</p> : null}
                {detail.items.length > 0 ? (
                  <ul style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 8 }}>
                    {detail.items.map((item) => (
                      <li key={`${item.event_id}:${item.source_url}`}>
                        <p style={{ margin: "0 0 4px" }}>
                          <strong>
                            {item.market}:{item.symbol}
                          </strong>{" "}
                          {item.summary}
                        </p>
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                          <a href={item.event_detail_url}>이벤트 상세 이동</a>
                          <a href={item.source_url} target="_blank" rel="noreferrer">
                            근거 원문 보기
                          </a>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
