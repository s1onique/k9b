/**
 * IncidentAutomaticDiagnosisLoopCard Component
 *
 * Read-only UI card for displaying automatic diagnosis loop summary.
 * Shows current-state summary derived from incident timeline events.
 *
 * Hard constraints enforced:
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 * - NO external tool invocation
 * - NO persistence
 * - NO write actions
 * - NO raw event data
 * - NO action buttons (run, approve, apply, delete, restart, etc.)
 *
 * Safety:
 * - Displays only bounded metadata
 * - Shows status labels honestly
 * - Clearly states read-only and review-required status
 */

import type { AutomaticDiagnosisLoopSummary, DiagnosisLoopStatus } from "../api";

export interface IncidentAutomaticDiagnosisLoopCardProps {
  loopSummary: AutomaticDiagnosisLoopSummary;
}

/**
 * Status label mappings for honest display.
 */
const STATUS_LABELS: Record<DiagnosisLoopStatus, string> = {
  not_run: "Automatic diagnosis has not run for this incident.",
  running_or_started: "Automatic diagnosis started; completion has not been recorded yet.",
  completed: "Automatic diagnosis completed.",
  failed_or_unavailable: "Automatic diagnosis failed or is unavailable.",
};

/**
 * CSS class for status badge.
 */
const getStatusClass = (status: DiagnosisLoopStatus): string => {
  switch (status) {
    case "not_run":
      return "loop-status-not-run";
    case "running_or_started":
      return "loop-status-running";
    case "completed":
      return "loop-status-completed";
    case "failed_or_unavailable":
      return "loop-status-failed";
    default:
      return "loop-status-unknown";
  }
};

/**
 * Formats a timestamp for display.
 * Uses explicit UTC ISO format for consistency with incident timestamps.
 */
const formatTimestamp = (timestamp: string | null | undefined): string => {
  if (!timestamp) return "Unknown";
  try {
    const date = new Date(timestamp);
    return date.toISOString().replace("T", " ").replace("Z", " UTC");
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
 * Safety notice component.
 */
const SafetyNotice: React.FC = () => (
  <div className="automatic-diagnosis-loop-notice">
    <p className="muted small">
      Read-only evidence collected automatically. Review required before any action.
      No remediation was attempted.
    </p>
  </div>
);

/**
 * Check counts display.
 */
const CheckCounts: React.FC<{
  requested: number | null | undefined;
  run: number | null | undefined;
  rejected: number | null | undefined;
}> = ({ requested, run, rejected }) => (
  <div className="automatic-diagnosis-loop-counts">
    <div className="loop-count-row">
      <span className="muted small">Checks requested:</span>
      <span>{formatCount(requested)}</span>
    </div>
    <div className="loop-count-row">
      <span className="muted small">Checks run:</span>
      <span>{formatCount(run)}</span>
    </div>
    <div className="loop-count-row">
      <span className="muted small">Checks rejected:</span>
      <span>{formatCount(rejected)}</span>
    </div>
  </div>
);

/**
 * Timestamps display.
 */
const Timestamps: React.FC<{
  startedAt: string | null | undefined;
  completedAt: string | null | undefined;
  failedAt: string | null | undefined;
}> = ({ startedAt, completedAt, failedAt }) => (
  <div className="automatic-diagnosis-loop-timestamps">
    {startedAt && (
      <div className="loop-timestamp-row">
        <span className="muted small">Started:</span>
        <span>{formatTimestamp(startedAt)}</span>
      </div>
    )}
    {completedAt && (
      <div className="loop-timestamp-row">
        <span className="muted small">Completed:</span>
        <span>{formatTimestamp(completedAt)}</span>
      </div>
    )}
    {failedAt && (
      <div className="loop-timestamp-row">
        <span className="muted small">Failed:</span>
        <span>{formatTimestamp(failedAt)}</span>
      </div>
    )}
  </div>
);

/**
 * Unavailable reason display.
 */
const UnavailableReason: React.FC<{ reason: string | null | undefined }> = ({ reason }) => {
  if (!reason) return null;
  return (
    <div className="automatic-diagnosis-loop-unavailable">
      <span className="muted small">Reason:</span>
      <span>{reason}</span>
    </div>
  );
};

/**
 * Review packet availability display.
 */
const ReviewPacketStatus: React.FC<{
  available: boolean;
  packetId: string | null | undefined;
}> = ({ available, packetId }) => (
  <div className="automatic-diagnosis-loop-review-packet">
    <span className="muted small">Review packet:</span>
    <span>{available ? (packetId ? "Available" : "Generated") : "Not available"}</span>
    {packetId && (
      <code className="loop-packet-id">{packetId}</code>
    )}
  </div>
);

/**
 * Read-only automatic diagnosis loop summary card.
 *
 * IMPORTANT: This card is STRICTLY READ-ONLY.
 * - No action buttons (run, approve, apply, delete, restart, etc.)
 * - No raw event data
 * - No remediation controls
 *
 * Renders honestly based on status:
 * - not_run: "Automatic diagnosis has not run for this incident."
 * - running_or_started: "Automatic diagnosis started; completion has not been recorded yet."
 * - completed: "Automatic diagnosis completed."
 * - failed_or_unavailable: "Automatic diagnosis failed or is unavailable."
 */
export const IncidentAutomaticDiagnosisLoopCard: React.FC<
  IncidentAutomaticDiagnosisLoopCardProps
> = ({ loopSummary }) => {
  const status = loopSummary.status;

  return (
    <div className="incident-detail-section automatic-diagnosis-loop-card">
      <h4>Automatic diagnosis loop</h4>

      {/* Status badge and label */}
      <div className="automatic-diagnosis-loop-status">
        <span className={`loop-status-badge ${getStatusClass(status)}`}>
          {status.replace(/_/g, " ")}
        </span>
        <span className="loop-status-label">
          {STATUS_LABELS[status] || `Unknown status: ${status}`}
        </span>
      </div>

      {/* Timestamps */}
      <Timestamps
        startedAt={loopSummary.latest_started_at}
        completedAt={loopSummary.latest_completed_at}
        failedAt={loopSummary.latest_failed_at}
      />

      {/* Unavailable reason (only for failed state) */}
      {status === "failed_or_unavailable" && (
        <UnavailableReason reason={loopSummary.unavailable_reason} />
      )}

      {/* Check counts (only for completed state) */}
      {status === "completed" && (
        <CheckCounts
          requested={loopSummary.checks_requested}
          run={loopSummary.checks_run}
          rejected={loopSummary.checks_rejected}
        />
      )}

      {/* Review packet availability */}
      <ReviewPacketStatus
        available={loopSummary.review_packet_available}
        packetId={loopSummary.review_packet_id}
      />

      {/* Safety notice */}
      <SafetyNotice />
    </div>
  );
};

export default IncidentAutomaticDiagnosisLoopCard;
