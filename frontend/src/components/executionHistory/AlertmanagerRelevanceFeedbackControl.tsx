/**
 * AlertmanagerRelevanceFeedbackControl.tsx
 *
 * User feedback widget for rating Alertmanager relevance.
 */

import { useState } from "react";
import type { NextCheckExecutionHistoryEntry } from "../../types";

const ALERTMANAGER_RELEVANCE_OPTIONS = [
  { value: "relevant", label: "Relevant" },
  { value: "not_relevant", label: "Not relevant" },
  { value: "noisy", label: "Noisy" },
  { value: "unsure", label: "Unsure" },
] as const;

interface AlertmanagerRelevanceFeedbackControlProps {
  entry: NextCheckExecutionHistoryEntry;
  onSubmit: (
    artifactPath: string,
    relevance: "relevant" | "not_relevant" | "noisy" | "unsure",
    summary: string | undefined
  ) => Promise<void>;
}

export const AlertmanagerRelevanceFeedbackControl = ({
  entry,
  onSubmit,
}: AlertmanagerRelevanceFeedbackControlProps) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedRelevance, setSelectedRelevance] = useState<"relevant" | "not_relevant" | "noisy" | "unsure" | null>(null);
  const [summary, setSummary] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  if (entry.alertmanagerRelevance) {
    return null;
  }

  if (!entry.artifactPath) {
    return null;
  }

  const handleSubmit = async () => {
    if (!selectedRelevance || !entry.artifactPath) {
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      await onSubmit(entry.artifactPath, selectedRelevance, summary.trim() || undefined);
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit feedback");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (success) {
    return (
      <div className="alertmanager-relevance-feedback-success">
        <span className="muted small">✓ Alertmanager relevance recorded</span>
      </div>
    );
  }

  return (
    <div className="alertmanager-relevance-feedback-control">
      {!isExpanded ? (
        <button
          type="button"
          className="link tiny"
          onClick={() => setIsExpanded(true)}
        >
          Rate Alertmanager relevance
        </button>
      ) : (
        <div className="alertmanager-relevance-feedback-form">
          <p className="tiny muted">Was Alertmanager influence relevant for this check?</p>
          <div className="alertmanager-relevance-feedback-options">
            {ALERTMANAGER_RELEVANCE_OPTIONS.map((option) => (
              <label key={option.value} className="alertmanager-relevance-feedback-option">
                <input
                  type="radio"
                  name={`alertmanager-relevance-${entry.artifactPath}`}
                  value={option.value}
                  checked={selectedRelevance === option.value}
                  onChange={() => setSelectedRelevance(option.value)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
          <input
            type="text"
            placeholder="Optional note"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            className="alertmanager-relevance-feedback-summary"
            maxLength={200}
          />
          <div className="alertmanager-relevance-feedback-actions">
            <button
              type="button"
              className="button primary tiny"
              onClick={handleSubmit}
              disabled={!selectedRelevance || isSubmitting}
            >
              {isSubmitting ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              className="button secondary tiny"
              onClick={() => setIsExpanded(false)}
              disabled={isSubmitting}
            >
              Cancel
            </button>
          </div>
          {error && <p className="alertmanager-relevance-feedback-error">{error}</p>}
        </div>
      )}
    </div>
  );
};

export default AlertmanagerRelevanceFeedbackControl;
