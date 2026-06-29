/**
 * UsefulnessFeedbackControl.tsx
 *
 * User feedback widget for rating check usefulness.
 */

import { useState } from "react";
import type { NextCheckExecutionHistoryEntry } from "../../types";

const USEFULNESS_CLASSES = [
  { value: "useful", label: "Useful" },
  { value: "partial", label: "Partial" },
  { value: "noisy", label: "Noisy" },
  { value: "empty", label: "Empty" },
] as const;

interface UsefulnessFeedbackControlProps {
  entry: NextCheckExecutionHistoryEntry;
  onSubmit: (artifactPath: string, usefulnessClass: string, summary: string | undefined) => Promise<void>;
}

export const UsefulnessFeedbackControl = ({
  entry,
  onSubmit,
}: UsefulnessFeedbackControlProps) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedClass, setSelectedClass] = useState<"useful" | "partial" | "noisy" | "empty" | null>(null);
  const [summary, setSummary] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  if (entry.usefulnessClass) {
    return null;
  }

  if (!entry.artifactPath) {
    return null;
  }

  const handleSubmit = async () => {
    if (!selectedClass || !entry.artifactPath) {
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      await onSubmit(entry.artifactPath, selectedClass, summary.trim() || undefined);
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit feedback");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (success) {
    return (
      <div className="usefulness-feedback-success">
        <span className="muted small">✓ Feedback recorded</span>
      </div>
    );
  }

  return (
    <div className="usefulness-feedback-control">
      {!isExpanded ? (
        <button
          type="button"
          className="link tiny"
          onClick={() => setIsExpanded(true)}
        >
          Rate usefulness
        </button>
      ) : (
        <div className="usefulness-feedback-form">
          <p className="tiny muted">Was this check useful?</p>
          <div className="usefulness-feedback-options">
            {USEFULNESS_CLASSES.map((cls) => (
              <label key={cls.value} className="usefulness-feedback-option">
                <input
                  type="radio"
                  name={`usefulness-${entry.artifactPath}`}
                  value={cls.value}
                  checked={selectedClass === cls.value}
                  onChange={() => setSelectedClass(cls.value as "useful" | "partial" | "noisy" | "empty")}
                />
                <span>{cls.label}</span>
              </label>
            ))}
          </div>
          <input
            type="text"
            placeholder="Optional note"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            className="usefulness-feedback-summary"
            maxLength={200}
          />
          <div className="usefulness-feedback-actions">
            <button
              type="button"
              className="button primary tiny"
              onClick={handleSubmit}
              disabled={!selectedClass || isSubmitting}
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
          {error && <p className="usefulness-feedback-error">{error}</p>}
        </div>
      )}
    </div>
  );
};

export default UsefulnessFeedbackControl;
