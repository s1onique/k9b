/**
 * Demo Shell Finding Detail Screen Component
 *
 * Shows detailed information about a selected finding.
 */

import type { DemoFinding } from "./DemoShellTypes";
import { SeverityBadge } from "./DemoShellBadges";
import { EvidenceSourceBadge } from "./DemoShellBadges";

interface FindingDetailPanelProps {
  finding: DemoFinding;
  onBack: () => void;
  onViewAction: () => void;
}

export const FindingDetailPanel = ({ finding, onBack, onViewAction }: FindingDetailPanelProps) => (
  <div className="demo-screen demo-screen--finding-detail">
    <div className="demo-panel-header">
      <button
        type="button"
        className="demo-back-button"
        onClick={onBack}
        data-testid="demo-back-to-dashboard"
      >
        ← Back to Dashboard
      </button>
    </div>

    <div className="demo-finding-detail">
      <div className="demo-finding-header">
        <div className="demo-finding-badges">
          <SeverityBadge severity={finding.severity} />
          <EvidenceSourceBadge source={finding.evidenceSource} />
        </div>
        <h2 className="demo-finding-title">{finding.title}</h2>
        <p className="demo-finding-resource">
          Affected resource: <strong>{finding.affectedResource}</strong>
        </p>
      </div>

      <div className="demo-finding-section">
        <h3 className="demo-section-label">Probable cause</h3>
        <p className="demo-section-content">{finding.probableCause}</p>
      </div>

      <div className="demo-finding-section">
        <h3 className="demo-section-label">Diagnostic evidence</h3>
        <p className="demo-section-content">{finding.diagnosticEvidence}</p>
      </div>

      <div className="demo-finding-section">
        <h3 className="demo-section-label">Recommended action</h3>
        <p className="demo-section-content">{finding.recommendedAction}</p>
      </div>

      <div className="demo-finding-actions">
        <button
          type="button"
          className="demo-button demo-button--primary"
          onClick={onViewAction}
          data-testid="demo-view-action-button"
        >
          View recommended action
        </button>
      </div>
    </div>
  </div>
);