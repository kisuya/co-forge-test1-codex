"use client";
import { useMemo, useState } from "react";
import { ReasonFeedbackButtons } from "@/components/reason-feedback-buttons";
import type {
  ApiClient,
  ConfidenceBreakdown,
  ConfidenceComponentBreakdown,
  EventPayload,
  EventReason,
  ReasonStatus,
} from "@/lib/api-client";
type ToastPayload = { kind: "error" | "success"; message: string };
type ReasonExplanationPanelProps = {
  event: EventPayload;
  client: ApiClient;
  onToast: (toast: ToastPayload) => void;
};
type StatusMeta = {
  label: string;
  badgeColor: string;
  textColor: string;
  helperText: string;
};
type BreakdownRow = {
  key: string;
  label: string;
};
type NormalizedConfidenceBreakdown = {
  isProvided: boolean;
  hasMissingValues: boolean;
  weights: ConfidenceComponentBreakdown;
  signals: ConfidenceComponentBreakdown;
  scoreBreakdown: ConfidenceComponentBreakdown & { total: number };
};
const STATUS_META: Record<ReasonStatus, StatusMeta> = {
  verified: {
    label: "검증 완료",
    badgeColor: "#dcfce7",
    textColor: "#166534",
    helperText: "현재 근거 기준으로 설명 가능한 상태입니다.",
  },
  collecting_evidence: {
    label: "근거 수집 중",
    badgeColor: "#fef3c7",
    textColor: "#92400e",
    helperText: "검증 가능한 출처를 수집하고 있습니다.",
  },
};
const COMPONENT_ROWS: BreakdownRow[] = [
  { key: "time_proximity", label: "시간 근접도" },
  { key: "source_reliability", label: "출처 신뢰도" },
  { key: "event_match", label: "이벤트 일치도" },
];
const SCORE_ROWS: BreakdownRow[] = [...COMPONENT_ROWS, { key: "total", label: "총합" }];
const DEFAULT_EXPLANATION_TEXT =
  "근거 수집 중입니다. 검증 가능한 출처가 확보되면 confidence 설명이 갱신됩니다.";
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
function inferReasonStatus(event: EventPayload): ReasonStatus {
  if (event.reason_status === "verified" || event.reason_status === "collecting_evidence") {
    return event.reason_status;
  }
  const hasEvidence = event.reasons.some((reason) => Boolean(reason.source_url?.trim()));
  return hasEvidence ? "verified" : "collecting_evidence";
}
function toFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  return null;
}
function normalizeComponentBreakdown(input: unknown): {
  values: ConfidenceComponentBreakdown;
  hasMissingValues: boolean;
} {
  if (!input || typeof input !== "object") {
    return {
      values: { source_reliability: 0, event_match: 0, time_proximity: 0 },
      hasMissingValues: true,
    };
  }
  const source = input as Record<string, unknown>;
  const sourceReliability = toFiniteNumber(source.source_reliability);
  const eventMatch = toFiniteNumber(source.event_match);
  const timeProximity = toFiniteNumber(source.time_proximity);
  return {
    values: {
      source_reliability: sourceReliability ?? 0,
      event_match: eventMatch ?? 0,
      time_proximity: timeProximity ?? 0,
    },
    hasMissingValues: sourceReliability === null || eventMatch === null || timeProximity === null,
  };
}
function normalizeScoreBreakdown(input: unknown): {
  values: ConfidenceComponentBreakdown & { total: number };
  hasMissingValues: boolean;
} {
  if (!input || typeof input !== "object") {
    return {
      values: { source_reliability: 0, event_match: 0, time_proximity: 0, total: 0 },
      hasMissingValues: true,
    };
  }
  const source = input as Record<string, unknown>;
  const sourceReliability = toFiniteNumber(source.source_reliability);
  const eventMatch = toFiniteNumber(source.event_match);
  const timeProximity = toFiniteNumber(source.time_proximity);
  const total = toFiniteNumber(source.total);
  return {
    values: {
      source_reliability: sourceReliability ?? 0,
      event_match: eventMatch ?? 0,
      time_proximity: timeProximity ?? 0,
      total: total ?? 0,
    },
    hasMissingValues:
      sourceReliability === null || eventMatch === null || timeProximity === null || total === null,
  };
}
function normalizeConfidenceBreakdown(
  confidenceBreakdown: ConfidenceBreakdown | undefined,
): NormalizedConfidenceBreakdown {
  if (!confidenceBreakdown) {
    return {
      isProvided: false,
      hasMissingValues: true,
      weights: { source_reliability: 0, event_match: 0, time_proximity: 0 },
      signals: { source_reliability: 0, event_match: 0, time_proximity: 0 },
      scoreBreakdown: { source_reliability: 0, event_match: 0, time_proximity: 0, total: 0 },
    };
  }
  const weights = normalizeComponentBreakdown(confidenceBreakdown.weights);
  const signals = normalizeComponentBreakdown(confidenceBreakdown.signals);
  const scoreBreakdown = normalizeScoreBreakdown(confidenceBreakdown.score_breakdown);
  return {
    isProvided: true,
    hasMissingValues: weights.hasMissingValues || signals.hasMissingValues || scoreBreakdown.hasMissingValues,
    weights: weights.values,
    signals: signals.values,
    scoreBreakdown: scoreBreakdown.values,
  };
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
function BreakdownCard({
  title,
  rows,
  values,
}: {
  title: string;
  rows: BreakdownRow[];
  values: Record<string, number>;
}): JSX.Element {
  return (
    <section style={{ border: "1px solid #e2e8f0", borderRadius: 10, background: "#f8fafc", padding: 12 }}>
      <h4 style={{ margin: "0 0 8px", fontSize: 14 }}>{title}</h4>
      <dl style={{ margin: 0, display: "grid", gap: 6 }}>
        {rows.map((row) => (
          <div
            key={`${title}-${row.key}`}
            style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 13 }}
          >
            <dt style={{ color: "#334155" }}>{row.label}</dt>
            <dd style={{ margin: 0, fontWeight: 600, color: "#0f172a" }}>{values[row.key].toFixed(2)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
export function ReasonExplanationPanel({
  event,
  client,
  onToast,
}: ReasonExplanationPanelProps): JSX.Element {
  const [isExpanded, setExpanded] = useState(false);
  const reasonStatus = inferReasonStatus(event);
  const statusMeta = STATUS_META[reasonStatus];
  const helperText = event.revision_hint?.trim() || statusMeta.helperText;
  const explanationText = event.explanation_text?.trim() || DEFAULT_EXPLANATION_TEXT;
  const confidence = useMemo(
    () => normalizeConfidenceBreakdown(event.confidence_breakdown),
    [event.confidence_breakdown],
  );
  const panelId = `reason-explanation-panel-${event.id}`;
  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <span
          data-testid="reason-status-badge"
          style={{
            display: "inline-flex",
            padding: "4px 10px",
            borderRadius: 999,
            fontSize: 12,
            fontWeight: 700,
            background: statusMeta.badgeColor,
            color: statusMeta.textColor,
          }}
        >
          {statusMeta.label}
        </span>
        <span style={{ color: "#475569", fontSize: 13 }}>{helperText}</span>
      </div>
      <button
        type="button"
        aria-expanded={isExpanded}
        aria-controls={panelId}
        onClick={() => setExpanded((previous) => !previous)}
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
        {isExpanded ? "설명 접기" : "설명 펼치기"}
      </button>
      {isExpanded ? (
        <section id={panelId} style={{ display: "grid", gap: 10 }}>
          <p style={{ margin: 0, color: "#1e293b" }}>{explanationText}</p>
          {!confidence.isProvided ? (
            <p data-testid="confidence-breakdown-fallback" style={{ margin: 0, color: "#b45309" }}>
              confidence 세부 점수를 아직 계산 중입니다.
            </p>
          ) : (
            <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))" }}>
              <BreakdownCard title="가중치" rows={COMPONENT_ROWS} values={confidence.weights} />
              <BreakdownCard title="신호 강도" rows={COMPONENT_ROWS} values={confidence.signals} />
              <BreakdownCard title="점수 분해" rows={SCORE_ROWS} values={confidence.scoreBreakdown} />
            </div>
          )}
          {confidence.hasMissingValues ? (
            <p style={{ margin: 0, color: "#92400e", fontSize: 12 }}>
              일부 confidence 항목이 누락되어 기본값(0.00)으로 표시하고 있습니다.
            </p>
          ) : null}
        </section>
      ) : null}
      <section style={{ display: "grid", gap: 8 }}>
        <h3 style={{ margin: 0, fontSize: 15 }}>근거 목록</h3>
        {event.reasons.length === 0 ? <p data-testid="evidence-empty">검증 가능한 근거를 수집 중입니다.</p> : null}
        {event.reasons.length > 0 ? (
          <ul style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 10 }}>
            {event.reasons.map((reason) => (
              <li key={`${event.id}-${reason.rank}`} style={{ display: "grid", gap: 4 }}>
                <p style={{ margin: 0 }}>{reason.summary}</p>
                <ReasonSourceLink reason={reason} />
                <ReasonFeedbackButtons client={client} eventId={event.id} reasonId={reason.id} onToast={onToast} />
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </div>
  );
}
