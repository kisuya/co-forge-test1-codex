"use client";

import type { BriefSummaryItem } from "@/lib/api-client";

type BriefSectionProps = {
  title: string;
  emptyMessage: string;
  briefs: BriefSummaryItem[];
  selectedBriefId: string | null;
  onSelect: (briefId: string) => void;
  testId: string;
  toGeneratedAtLabel: (value: string) => string;
};

export function BriefInboxSection({
  title,
  emptyMessage,
  briefs,
  selectedBriefId,
  onSelect,
  testId,
  toGeneratedAtLabel,
}: BriefSectionProps): JSX.Element {
  return (
    <section data-testid={testId} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: 10 }}>
      <h3 style={{ margin: "0 0 8px" }}>{title}</h3>
      {briefs.length === 0 ? <p style={{ margin: 0 }}>{emptyMessage}</p> : null}
      {briefs.length > 0 ? (
        <ul style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 8 }}>
          {briefs.map((brief) => {
            const isSelected = selectedBriefId === brief.id;
            return (
              <li key={brief.id}>
                <button
                  data-testid={`brief-card-${brief.id}`}
                  type="button"
                  onClick={() => onSelect(brief.id)}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    border: isSelected ? "1px solid #0f172a" : "1px solid #cbd5e1",
                    background: isSelected ? "#f1f5f9" : "#fff",
                    borderRadius: 8,
                    padding: "8px 10px",
                  }}
                >
                  <p style={{ margin: 0 }}>
                    <strong>{brief.title}</strong>
                  </p>
                  <p style={{ margin: "4px 0 0", color: "#334155" }}>{brief.summary}</p>
                  <p style={{ margin: "4px 0 0", color: "#475569" }}>{toGeneratedAtLabel(brief.generated_at_utc)}</p>
                  <p data-testid={`brief-card-status-${brief.id}`} style={{ margin: "4px 0 0", color: "#334155" }}>
                    {brief.status === "read" ? "읽음" : "읽지 않음"}
                  </p>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
