/**
 * EvidenceNeededSection Component
 *
 * Evidence needed section for incident detail view.
 */

import type { IncidentDetailPayload } from "../api";

export interface EvidenceNeededSectionProps {
  evidenceNeeded: IncidentDetailPayload["evidence_needed"];
}

/**
 * Evidence needed section.
 */
export const EvidenceNeededSection: React.FC<EvidenceNeededSectionProps> = ({ evidenceNeeded }) => {
  if (evidenceNeeded.length === 0) {
    return null; // Don't show section if no evidence needed
  }

  return (
    <div className="incident-section">
      <div className="incident-section-header">
        <h4 className="incident-section-title">Evidence Needed</h4>
      </div>
      <div className="incident-section-content">
        <ul className="incident-evidence-needed-list">
          {evidenceNeeded.map((item, index) => (
            <li key={index} className="evidence-needed-item">
              {item}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};
