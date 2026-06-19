/**
 * IncidentAutomaticDiagnosisReviewPanel Component
 *
 * Read-only UI for displaying automatic diagnosis review packet summary.
 * Shows bounded metadata from the latest automatic diagnosis loop review packet.
 *
 * Hard constraints enforced:
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 * - NO external tool invocation
 * - NO persistence
 * - NO write actions
 * - NO raw packet contents
 * - NO absolute paths
 * - NO action buttons (run, approve, apply, delete, restart, etc.)
 *
 * Safety:
 * - Displays only bounded metadata
 * - Shows artifact filename only (no paths)
 * - Clearly states read-only and review-required status
 */

import type { AutomaticDiagnosisReviewPayload } from "../api";

export interface IncidentAutomaticDiagnosisReviewPanelProps {
  automaticDiagnosisReview: AutomaticDiagnosisReviewPayload;
}

/**
 * Formats a timestamp for display.
 */
const formatTimestamp = (timestamp: string | null | undefined): string => {
  if (!timestamp) return "Unknown";
  try {
    const date = new Date(timestamp);
    return date.toLocaleString();
  } catch {
    return timestamp;
  }
};

/**
 * Formats check counts for display.
 */
const formatCount = (count: number | null | undefined): string => {
  if (count === null || count === undefined) return "0";
  return String(count);
};

/**
 * Renders the unavailable state when no review packet exists.
 */
const UnavailableState: React.FC<{ reason: string | null | undefined }> = ({ reason }) => {
  return (
    <div className="automatic-diagnosis-review-unavailable">
      <span className="muted small">Automatic diagnosis evidence: not collected yet</span>
      {reason && reason !== "no_review_packet" && (
        <span className="muted small">Reason: {reason}</span>
      )}
    </div>
  );
};

/**
 * Renders the available state with bounded summary.
 */
const AvailableState: React.FC<{ review: AutomaticDiagnosisReviewPayload }> = ({ review }) => {
  return (
    <div className="automatic-diagnosis-review-content">
      {/* Safety notices */}
      <div className="automatic-diagnosis-review-notice">
        <p className="muted small">
          Read-only evidence collected automatically.
          Review required before any action.
          No remediation was attempted.
        </p>
      </div>

      {/* Decision */}
      {review.decision && (
        <div className="automatic-diagnosis-review-row">
          <span className="muted small">Decision:</span>
          <span>{review.decision}</span>
        </div>
      )}

      {/* Check counts */}
      <div className="automatic-diagnosis-review-row">
        <span className="muted small">Checks requested:</span>
        <span>{formatCount(review.checks_requested)}</span>
      </div>
      <div className="automatic-diagnosis-review-row">
        <span className="muted small">Checks run:</span>
        <span>{formatCount(review.checks_run)}</span>
      </div>
      <div className="automatic-diagnosis-review-row">
        <span className="muted small">Checks rejected:</span>
        <span>{formatCount(review.checks_rejected)}</span>
      </div>

      {/* Generated timestamp */}
      <div className="automatic-diagnosis-review-row">
        <span className="muted small">Generated:</span>
        <span>{formatTimestamp(review.generated_at)}</span>
      </div>

      {/* Artifact name (filename only, no path) */}
      {review.artifact_name && (
        <div className="automatic-diagnosis-review-row">
          <span className="muted small">Review packet:</span>
          <code className="automatic-diagnosis-review-artifact-name">{review.artifact_name}</code>
        </div>
      )}

      {/* Eligibility info */}
      {review.eligibility_reason && (
        <div className="automatic-diagnosis-review-row">
          <span className="muted small">Eligibility:</span>
          <span>{review.eligibility_reason}</span>
        </div>
      )}
    </div>
  );
};

/**
 * Read-only automatic diagnosis review panel.
 * Displays bounded summary of automatic diagnosis loop review packet.
 *
 * IMPORTANT: This panel is STRICTLY READ-ONLY.
 * - No action buttons (run, approve, apply, delete, restart, etc.)
 * - No raw packet contents
 * - No absolute paths
 * - No remediation controls
 */
export const IncidentAutomaticDiagnosisReviewPanel: React.FC<
  IncidentAutomaticDiagnosisReviewPanelProps
> = ({ automaticDiagnosisReview }) => {
  return (
    <div className="incident-detail-section automatic-diagnosis-review-panel">
      <h4>Automatic diagnosis evidence</h4>

      {automaticDiagnosisReview.available ? (
        <AvailableState review={automaticDiagnosisReview} />
      ) : (
        <UnavailableState reason={automaticDiagnosisReview.unavailable_reason} />
      )}
    </div>
  );
};

export default IncidentAutomaticDiagnosisReviewPanel;