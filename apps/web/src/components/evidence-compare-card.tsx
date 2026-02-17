"use client";

import { useEffect, useMemo, useState } from "react";

import type {
  ApiClient,
  EvidenceCompareAxis,
  EvidenceCompareAxisItem,
  EvidenceCompareResponse,
} from "@/lib/api-client";
import { ApiClientError } from "@/lib/api-client";

type CompareLoadStatus = "loading" | "success" | "error";
type CompareUiError = { message: string; retryable: boolean };

type EvidenceCompareCardProps = {
  eventId: string;
  client: ApiClient;
};

const AXIS_ORDER: EvidenceCompareAxis[] = ["positive", "negative", "uncertain"];

const AXIS_META: Record<
  EvidenceCompareAxis,
  { label: string; accentColor: string; background: string; description: string }
> = {
  positive: {
    label: "긍정 축",
    accentColor: "#166534",
    background: "#f0fdf4",
    description: "호재/상향 신호 중심 근거",
  },
  negative: {
    label: "부정 축",
    accentColor: "#991b1b",
    background: "#fef2f2",
    description: "악재/하향 신호 중심 근거",
  },
  uncertain: {
    label: "불확실 축",
    accentColor: "#1e3a8a",
    background: "#eff6ff",
    description: "해석이 엇갈리거나 분류가 어려운 근거",
  },
};

const FALLBACK_REASON_MESSAGES: Record<string, string> = {
  insufficient_evidence: "비교 가능한 근거 수가 부족합니다.",
  axis_imbalance: "긍정/부정 축이 불균형하여 신뢰 가능한 비교를 제공하기 어렵습니다.",
  ambiguous_classification: "근거 해석이 모호해 상충 축을 확정하지 못했습니다.",
  missing_source_metadata: "출처 URL 또는 발행 시각이 누락된 근거가 있어 비교를 보류했습니다.",
  permission_denied: "현재 권한으로는 비교 근거를 조회할 수 없습니다.",
};

function toUiError(error: unknown): CompareUiError {
  if (error instanceof ApiClientError) {
    return {
      message: error.payload.message || "근거 비교 카드를 불러오지 못했습니다.",
      retryable: Boolean(error.payload.retryable ?? error.payload.details?.retryable),
    };
  }
  return {
    message: "근거 비교 카드를 불러오지 못했습니다.",
    retryable: false,
  };
}

function toUnavailableMessage(fallbackReason: string | null): string {
  if (!fallbackReason) {
    return "비교 가능한 근거가 충분하지 않습니다.";
  }
  return FALLBACK_REASON_MESSAGES[fallbackReason] ?? "비교 근거를 정리하는 중입니다.";
}

function normalizeNonEmptyText(value: unknown, fallback: string): string {
  const normalized = String(value ?? "").trim();
  if (!normalized) {
    return fallback;
  }
  return normalized;
}

function normalizePublishedAt(value: unknown): string {
  const normalized = String(value ?? "").trim();
  if (!normalized) {
    return "발행 시각 확인 중";
  }
  return normalized;
}

function isAccessibleSourceUrl(sourceUrl: string): boolean {
  try {
    const parsed = new URL(sourceUrl);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function axisItems(payload: EvidenceCompareResponse, axis: EvidenceCompareAxis): EvidenceCompareAxisItem[] {
  const rawItems = payload.axes?.[axis];
  if (!Array.isArray(rawItems)) {
    return [];
  }
  return rawItems;
}

function AxisEvidenceList({
  axis,
  items,
}: {
  axis: EvidenceCompareAxis;
  items: EvidenceCompareAxisItem[];
}): JSX.Element {
  const meta = AXIS_META[axis];
  const countLabel = `${items.length}건`;

  return (
    <section
      data-testid={`evidence-compare-axis-${axis}`}
      style={{
        border: `1px solid ${meta.accentColor}33`,
        borderRadius: 12,
        background: meta.background,
        padding: 12,
        display: "grid",
        gap: 8,
      }}
    >
      <header style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
        <h4 style={{ margin: 0, fontSize: 14, color: meta.accentColor }}>{meta.label}</h4>
        <span
          style={{
            borderRadius: 999,
            background: "#ffffff",
            border: "1px solid #cbd5e1",
            padding: "2px 8px",
            fontSize: 12,
            fontWeight: 600,
            color: "#0f172a",
          }}
        >
          {countLabel}
        </span>
      </header>
      <p style={{ margin: 0, fontSize: 12, color: "#334155" }}>{meta.description}</p>
      {items.length === 0 ? (
        <p data-testid={`evidence-compare-axis-empty-${axis}`} style={{ margin: 0, color: "#64748b", fontSize: 13 }}>
          근거 없음
        </p>
      ) : (
        <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 10 }}>
          {items.map((item, index) => {
            const summary = normalizeNonEmptyText(item.summary, "요약 정보 없음");
            const publishedAt = normalizePublishedAt(item.published_at);
            const sourceUrl = normalizeNonEmptyText(item.source_url, "");
            const hasAccessibleLink = isAccessibleSourceUrl(sourceUrl);

            return (
              <li
                key={`${axis}-${item.id ?? "unknown"}-${index}`}
                style={{
                  display: "grid",
                  gap: 4,
                  background: "#ffffff",
                  border: "1px solid #e2e8f0",
                  borderRadius: 10,
                  padding: 8,
                }}
              >
                <p style={{ margin: 0, color: "#0f172a", fontSize: 13 }}>{summary}</p>
                <p style={{ margin: 0, color: "#475569", fontSize: 12 }}>발행 시각: {publishedAt}</p>
                {hasAccessibleLink ? (
                  <a href={sourceUrl} target="_blank" rel="noopener noreferrer" style={{ color: "#1d4ed8", fontSize: 12 }}>
                    원문 보기
                  </a>
                ) : (
                  <span aria-disabled="true" style={{ color: "#64748b", fontSize: 12 }}>
                    접근 불가 링크
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export function EvidenceCompareCard({ eventId, client }: EvidenceCompareCardProps): JSX.Element {
  const [status, setStatus] = useState<CompareLoadStatus>("loading");
  const [compare, setCompare] = useState<EvidenceCompareResponse | null>(null);
  const [error, setError] = useState<CompareUiError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function run(): Promise<void> {
      setStatus("loading");
      setError(null);
      try {
        const response = await client.getEvidenceCompare(eventId);
        if (cancelled) {
          return;
        }
        setCompare(response);
        setStatus("success");
      } catch (caughtError) {
        if (cancelled) {
          return;
        }
        setCompare(null);
        setError(toUiError(caughtError));
        setStatus("error");
      }
    }

    void run();

    return () => {
      cancelled = true;
    };
  }, [client, eventId, reloadToken]);

  const hasAnyAxisItem = useMemo(() => {
    if (!compare) {
      return false;
    }
    return AXIS_ORDER.some((axis) => axisItems(compare, axis).length > 0);
  }, [compare]);

  return (
    <section
      data-testid="evidence-compare-card"
      style={{
        marginTop: 16,
        border: "1px solid #cbd5e1",
        borderRadius: 12,
        background: "#ffffff",
        padding: 14,
        display: "grid",
        gap: 10,
      }}
    >
      <header style={{ display: "grid", gap: 4 }}>
        <h3 style={{ margin: 0, fontSize: 16 }}>근거 비교 카드</h3>
        <p style={{ margin: 0, color: "#475569", fontSize: 13 }}>
          긍정/부정/불확실 축의 출처와 발행 시각을 함께 비교해 해석 편향을 줄입니다.
        </p>
      </header>

      {status === "loading" ? (
        <p data-testid="evidence-compare-loading" style={{ margin: 0, color: "#334155" }}>
          비교 근거를 불러오는 중...
        </p>
      ) : null}

      {status === "error" && error ? (
        <div data-testid="evidence-compare-error" role="alert" style={{ display: "grid", gap: 6 }}>
          <p style={{ margin: 0 }}>{error.message}</p>
          <p style={{ margin: 0, color: "#475569", fontSize: 13 }}>
            {error.retryable ? "일시적 오류입니다. 다시 시도할 수 있습니다." : "재시도 불가 오류입니다."}
          </p>
          {error.retryable ? (
            <button
              type="button"
              onClick={() => setReloadToken((previous) => previous + 1)}
              style={{
                justifySelf: "start",
                border: "1px solid #cbd5e1",
                borderRadius: 8,
                background: "#f8fafc",
                color: "#0f172a",
                padding: "6px 10px",
                cursor: "pointer",
              }}
            >
              비교 카드 다시 시도
            </button>
          ) : null}
        </div>
      ) : null}

      {status === "success" && compare && compare.status === "compare_unavailable" ? (
        <div data-testid="evidence-compare-unavailable" style={{ display: "grid", gap: 8 }}>
          <div
            style={{
              border: "1px solid #fed7aa",
              borderRadius: 10,
              background: "#fff7ed",
              padding: 10,
              display: "grid",
              gap: 4,
            }}
          >
            <p style={{ margin: 0, fontWeight: 700, color: "#9a3412" }}>비교 근거 부족</p>
            <p style={{ margin: 0, color: "#7c2d12", fontSize: 13 }}>{toUnavailableMessage(compare.fallback_reason)}</p>
            <p style={{ margin: 0, color: "#7c2d12", fontSize: 12 }}>{compare.bias_warning}</p>
          </div>
          {axisItems(compare, "uncertain").length > 0 ? (
            <AxisEvidenceList axis="uncertain" items={axisItems(compare, "uncertain")} />
          ) : null}
        </div>
      ) : null}

      {status === "success" && compare && compare.status === "ready" && !hasAnyAxisItem ? (
        <p data-testid="evidence-compare-empty" style={{ margin: 0, color: "#475569" }}>
          비교 가능한 근거가 아직 없습니다.
        </p>
      ) : null}

      {status === "success" && compare && compare.status === "ready" && hasAnyAxisItem ? (
        <div data-testid="evidence-compare-ready" style={{ display: "grid", gap: 10 }}>
          <p style={{ margin: 0, color: "#334155", fontSize: 13 }}>{compare.bias_warning}</p>
          <div
            style={{
              display: "grid",
              gap: 10,
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              alignItems: "start",
            }}
          >
            {AXIS_ORDER.map((axis) => (
              <AxisEvidenceList key={axis} axis={axis} items={axisItems(compare, axis)} />
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
