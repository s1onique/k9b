/**
 * ReviewPacketSection Component
 *
 * Review packet state section for incident detail view.
 */

import type { IncidentDetailPayload } from "../api";

export interface ReviewPacketSectionProps {
  reviewPacket: IncidentDetailPayload["review_packet"];
}

/**
 * Review packet state section.
 */
export const ReviewPacketSection: React.FC<ReviewPacketSectionProps> = ({ reviewPacket }) => {
  return (
    <div className="incident-section">
      <div className="incident-section-header">
        <h4 className="incident-section-title">Review Packet</h4>
      </div>
      <div className="incident-section-content">
        <div className="review-packet-state">
          {reviewPacket.status === "not_generated" && (
            <span className="review-packet-pending-text">Not generated yet</span>
          )}
          {reviewPacket.status === "generating" && (
            <span className="review-packet-generating-text">Generating…</span>
          )}
          {reviewPacket.status === "available" && (
            <div className="review-packet-info">
              <span className="review-packet-badge">Available</span>
              {reviewPacket.id && (
                <code className="review-packet-id">{reviewPacket.id}</code>
              )}
            </div>
          )}
          {reviewPacket.status === "failed" && (
            <div className="review-packet-error">
              <span className="review-packet-error-text">
                Failed: {reviewPacket.error_message || "Unknown error"}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
