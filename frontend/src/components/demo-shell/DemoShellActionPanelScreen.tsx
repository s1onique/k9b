/**
 * Demo Shell Action Panel Screen Component
 *
 * Shows recommended action for a finding with safety disclaimers.
 */

import type { DemoFinding } from "./DemoShellTypes";
import { SafetyModeLabel } from "./DemoShellBadges";

interface ActionPanelProps {
  finding: DemoFinding;
  onBack: () => void;
}

export const ActionPanel = ({ finding, onBack }: ActionPanelProps) => (
  <div className="demo-screen demo-screen--action-panel">
    <div className="demo-panel-header">
      <button
        type="button"
        className="demo-back-button"
        onClick={onBack}
        data-testid="demo-back-to-finding"
      >
        ← Back to Finding Detail
      </button>
    </div>

    <div className="demo-action-panel">
      <div className="demo-action-header">
        <h2 className="demo-action-title">Recommended Action</h2>
        <SafetyModeLabel mode={finding.safetyMode} />
      </div>

      <div className="demo-action-content">
        <p className="demo-action-description">{finding.recommendedAction}</p>

        {finding.commandPreview && (
          <div className="demo-command-preview">
            <h3 className="demo-section-label">Command preview</h3>
            <pre className="demo-command-code">{finding.commandPreview}</pre>
          </div>
        )}

        <div className="demo-action-safety">
          <p className="demo-safety-statement">
            <strong>Evidence-based analysis</strong>
          </p>
          <p className="demo-safety-note">
            {finding.safetyMode === "read-only" && "No execution. Display only."}
            {finding.safetyMode === "operator-approved" && "Requires explicit operator click to execute."}
            {finding.safetyMode === "preview-only" && "Command shown but not executed. No mutations."}
          </p>
        </div>

        <div className="demo-action-disclaimer">
          <p>
            This is a recommendation, not autonomous execution.
            Operator-visible evidence and approval required.
          </p>
        </div>
      </div>
    </div>
  </div>
);