"use client";

import { useState } from "react";

import { ApiClientError, type ApiClient } from "@/lib/api-client";

type FeedbackValue = "helpful" | "not_helpful";

type ReasonFeedbackButtonsProps = {
  client: ApiClient;
  eventId: string;
  reasonId: string;
  onToast: (toast: { kind: "error" | "success"; message: string }) => void;
};

function labelOf(value: FeedbackValue): string {
  return value === "helpful" ? "도움됨" : "부정확";
}

export function ReasonFeedbackButtons({
  client,
  eventId,
  reasonId,
  onToast,
}: ReasonFeedbackButtonsProps): JSX.Element {
  const [selectedValue, setSelectedValue] = useState<FeedbackValue | null>(null);
  const [isSubmitting, setSubmitting] = useState(false);

  async function submit(nextValue: FeedbackValue): Promise<void> {
    const previousValue = selectedValue;
    setSelectedValue(nextValue);
    setSubmitting(true);

    try {
      await client.submitReasonFeedback({ eventId, reasonId, feedback: nextValue });
      onToast({ kind: "success", message: `${labelOf(nextValue)} 피드백이 저장되었습니다.` });
    } catch (error) {
      setSelectedValue(previousValue);
      const message =
        error instanceof ApiClientError ? error.payload.message : "피드백 저장에 실패했습니다.";
      onToast({ kind: "error", message });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
      <button
        type="button"
        disabled={isSubmitting}
        aria-pressed={selectedValue === "helpful"}
        onClick={() => void submit("helpful")}
      >
        도움됨
      </button>
      <button
        type="button"
        disabled={isSubmitting}
        aria-pressed={selectedValue === "not_helpful"}
        onClick={() => void submit("not_helpful")}
      >
        부정확
      </button>
    </div>
  );
}
