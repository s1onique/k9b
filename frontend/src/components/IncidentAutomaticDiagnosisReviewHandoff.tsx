/**
 * IncidentAutomaticDiagnosisReviewHandoff Component
 *
 * Read-only UI control for copying/downloading automatic diagnosis review handoff.
 * Provides a safe way to copy bounded markdown content for human/ChatGPT review.
 *
 * Hard constraints enforced:
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 * - NO external tool invocation
 * - NO persistence
 * - NO write actions
 * - NO action buttons (run, approve, apply, delete, restart, etc.)
 * - NO raw packet contents exposed
 * - NO absolute paths exposed
 *
 * Safety:
 * - Only shows when review packet is available
 * - Copy to clipboard with fallback to download
 * - Shows success/failure state
 * - Displays read-only/review-required/no-remediation copy
 */

import { useState, useCallback } from "react";
import type { AutomaticDiagnosisReviewHandoffPayload } from "../api";

export interface IncidentAutomaticDiagnosisReviewHandoffProps {
  incidentId: string;
  onFetchHandoff: (incidentId: string) => Promise<AutomaticDiagnosisReviewHandoffPayload>;
}

/**
 * States for the handoff control
 */
type HandoffState = "idle" | "loading" | "success" | "copied" | "error" | "unavailable";

/**
 * Renders the handoff unavailable state when no review packet exists.
 */
const UnavailableState: React.FC<{ reason?: string | null }> = ({ reason }) => {
  return (
    <div className="handoff-unavailable">
      <span className="muted small">
        Review handoff not available
        {reason && reason !== "no_review_packet" && (
          <> — {reason}</>
        )}
      </span>
    </div>
  );
};

/**
 * Renders the error state.
 */
const ErrorState: React.FC<{ message: string; onRetry: () => void }> = ({ message, onRetry }) => {
  return (
    <div className="handoff-error">
      <span className="muted small">Failed to load handoff: {message}</span>
      <button
        type="button"
        className="btn-small"
        onClick={onRetry}
      >
        Retry
      </button>
    </div>
  );
};

/**
 * Read-only handoff control for automatic diagnosis review.
 *
 * IMPORTANT: This component is STRICTLY READ-ONLY.
 * - No action buttons (run, approve, apply, delete, restart, etc.)
 * - No raw packet contents exposed
 * - No absolute paths exposed
 * - No remediation controls
 */
export const IncidentAutomaticDiagnosisReviewHandoff: React.FC<
  IncidentAutomaticDiagnosisReviewHandoffProps
> = ({ incidentId, onFetchHandoff }) => {
  const [state, setState] = useState<HandoffState>("idle");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [handoffData, setHandoffData] = useState<AutomaticDiagnosisReviewHandoffPayload | null>(null);

  const handleFetchHandoff = useCallback(async () => {
    setState("loading");
    setErrorMessage("");

    try {
      const data = await onFetchHandoff(incidentId);
      setHandoffData(data);

      if (!data.available) {
        setState("unavailable");
      } else {
        setState("success");
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setErrorMessage(message);
      setState("error");
    }
  }, [incidentId, onFetchHandoff]);

  const handleCopyToClipboard = useCallback(async () => {
    if (!handoffData?.content) {
      return;
    }

    try {
      // Try clipboard API first
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(handoffData.content);
        setState("copied");
        // Reset after 2 seconds
        setTimeout(() => setState("success"), 2000);
      } else {
        // Fallback: download as file
        _downloadContent(handoffData);
      }
    } catch {
      // Fallback: download as file
      _downloadContent(handoffData);
    }
  }, [handoffData]);

  const _downloadContent = (data: AutomaticDiagnosisReviewHandoffPayload) => {
    if (!data.content) return;

    const blob = new Blob([data.content], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    // Use safe filename derived from incident_id
    a.download = `review-handoff-${incidentId}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setState("copied");
    setTimeout(() => setState("success"), 2000);
  };

  // Loading state
  if (state === "loading") {
    return (
      <div className="handoff-control">
        <button
          type="button"
          className="btn-small"
          disabled={true}
        >
          Loading...
        </button>
      </div>
    );
  }

  // Error state
  if (state === "error") {
    return (
      <div className="handoff-control">
        <ErrorState message={errorMessage} onRetry={handleFetchHandoff} />
      </div>
    );
  }

  // Idle state - show fetch button
  if (state === "idle") {
    return (
      <div className="handoff-control">
        <button
          type="button"
          className="btn-small"
          onClick={handleFetchHandoff}
        >
          Copy review packet
        </button>
        <span className="muted small help-text">
          Copies bounded read-only evidence for human/ChatGPT review.
          Review is required before any action.
        </span>
      </div>
    );
  }

  // Unavailable state
  if (state === "unavailable") {
    return (
      <div className="handoff-control">
        <UnavailableState reason={handoffData?.unavailable_reason} />
      </div>
    );
  }

  // Success/Copied state - show copy button
  return (
    <div className="handoff-control">
      {state === "copied" ? (
        <div className="handoff-success">
          <span className="text-success small">Copied to clipboard!</span>
        </div>
      ) : (
        <>
          <button
            type="button"
            className="btn-small"
            onClick={handleCopyToClipboard}
          >
            Copy review packet
          </button>
          <span className="muted small help-text">
            Copies bounded read-only evidence for human/ChatGPT review.
            Review is required before any action.
          </span>
        </>
      )}
    </div>
  );
};

export default IncidentAutomaticDiagnosisReviewHandoff;
