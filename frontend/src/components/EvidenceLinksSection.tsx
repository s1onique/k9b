/**
 * EvidenceLinksSection Component
 *
 * Evidence links section for incident detail view.
 * Shows evidence artifacts attached to the incident.
 */

import type { IncidentDetailPayload } from "../api";
import { formatIncidentTimestamp } from "./incident-view-model";

export interface EvidenceLinksSectionProps {
  evidenceLinks: IncidentDetailPayload["evidence_links"];
}

/**
 * Evidence links section - shows evidence artifacts attached to the incident.
 */
export const EvidenceLinksSection: React.FC<EvidenceLinksSectionProps> = ({ evidenceLinks }) => {
  if (evidenceLinks.length === 0) {
    return (
      <div className="incident-section">
        <div className="incident-section-header">
          <h4 className="incident-section-title">Evidence</h4>
        </div>
        <div className="incident-section-content">
          <div className="incident-empty-state">
            <p className="muted small">No evidence artifacts are attached to this incident yet.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="incident-section">
      <div className="incident-section-header">
        <h4 className="incident-section-title">Evidence Links</h4>
      </div>
      <div className="incident-section-content">
        <ul className="incident-evidence-list">
          {evidenceLinks.map((link, index) => (
            <li key={index} className="evidence-item">
              <div className="evidence-header">
                <span className="evidence-kind">Evidence Artifact</span>
                <span className="evidence-role">{link.role}</span>
              </div>
              <div className="evidence-meta">
                Artifact ID: <code>{link.artifact_id}</code>
                <br />
                Attached: {formatIncidentTimestamp(link.attached_at)}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};
