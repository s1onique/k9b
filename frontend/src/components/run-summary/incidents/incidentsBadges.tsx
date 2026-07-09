/**
 * incidentsBadges.tsx — Badge and indicator components for incidents.
 *
 * Pure view components for status badges and indicators.
 * All state is passed in as props; no local state or effects.
 */

import React from "react";
import {
  incidentDiagnosisLoopClass,
  incidentDiagnosisLoopLabel,
  type DiagnosisLoopStatus,
} from "../../incident-view-model";

// ============================================================================
// Diagnosis status badge
// ============================================================================

/**
 * Renders a diagnosis status indicator.
 */
export const DiagnosisStatusBadge: React.FC<{ status: DiagnosisLoopStatus }> = ({
  status,
}) => (
  <span className={incidentDiagnosisLoopClass(status)}>
    {incidentDiagnosisLoopLabel(status)}
  </span>
);

// ============================================================================
// Review packet indicator
// ============================================================================

/**
 * Renders a review packet status indicator.
 */
export const ReviewPacketIndicator: React.FC<{
  status: string;
  errorMessage?: string | null;
}> = ({ status, errorMessage }) => {
  switch (status) {
    case "available":
      return (
        <span className="review-packet-indicator review-packet-available">
          present
        </span>
      );
    case "generating":
      return (
        <span className="review-packet-indicator review-packet-generating">
          generating
        </span>
      );
    case "failed":
      return (
        <span
          className="review-packet-indicator review-packet-failed"
          title={errorMessage || "Failed"}
        >
          failed
        </span>
      );
    case "not_generated":
    default:
      return (
        <span className="review-packet-indicator review-packet-absent">
          absent
        </span>
      );
  }
};
