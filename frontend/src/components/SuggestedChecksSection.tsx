/**
 * SuggestedChecksSection Component
 *
 * Suggested checks section for incident detail view.
 * Read-only compatibility projection - no execution, promotion, or remediation.
 */

import type { IncidentDetailPayload } from "../api";

export interface SuggestedChecksSectionProps {
  suggestedChecks?: IncidentDetailPayload["suggested_checks"];
}

/**
 * Suggested checks section.
 * Read-only compatibility projection - no execution, promotion, or remediation.
 */
export const SuggestedChecksSection: React.FC<SuggestedChecksSectionProps> = ({ suggestedChecks }) => {
  // Defensive: treat undefined/empty as empty state
  const checks = suggestedChecks ?? [];
  if (checks.length === 0) {
    return null; // Don't show section if no suggested checks
  }

  return (
    <div className="incident-section">
      <div className="incident-section-header">
        <h4 className="incident-section-title">Suggested Checks</h4>
      </div>
      <div className="incident-section-content">
        <p className="muted small">Read-only view. No execution, promotion, or remediation available.</p>
        <ul className="incident-suggested-checks-list">
          {checks.map((check, index) => (
            <li key={index} className="suggested-check-item">
              <div className="suggested-check-header">
                <span className="suggested-check-title">{check.title}</span>
                {check.risk_level && (
                  <span className={`risk-badge risk-${check.risk_level.toLowerCase()}`}>
                    {check.risk_level}
                  </span>
                )}
                <span className={`status-badge status-${check.status}`}>
                  {check.status}
                </span>
              </div>
              <div className="suggested-check-rationale">{check.rationale}</div>
              <div className="suggested-check-meta muted small">
                <span>Source: {check.source}</span>
                {check.artifact_id && (
                  <>
                    <span>·</span>
                    <span>Artifact: {check.artifact_id}</span>
                  </>
                )}
                {check.run_id && (
                  <>
                    <span>·</span>
                    <span>Run: {check.run_id}</span>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};
