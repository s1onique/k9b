/**
 * Demo Shell Action Panel Screen Component
 *
 * Shows recommended action for a finding with comprehensive safety disclaimers.
 * Implements a remediation preview surface that is safe for sales demos:
 * - No real mutation
 * - No kubectl execution
 * - No autonomous remediation claims
 * - Clear safety mode labeling
 * - Explicit approval/disabled states
 */

import { useState } from "react";
import type { DemoFinding } from "./DemoShellTypes";
import { SafetyModeLabel } from "./DemoShellBadges";
import {
  getActionSafetyCopy,
  getActionCta,
  getActionRiskLabel,
  getActionTypeLabel,
  isActionExecutableInDemo,
  EVIDENCE_SOURCE_LABELS,
} from "./DemoShellData";

interface ActionPanelProps {
  finding: DemoFinding;
  onBack: () => void;
}

export const ActionPanel = ({ finding, onBack }: ActionPanelProps) => {
  // Track copy-to-clipboard state
  const [copied, setCopied] = useState(false);

  // Get helper data
  const safetyCopy = getActionSafetyCopy(finding.safetyMode);
  const ctaConfig = getActionCta(finding.safetyMode);
  const riskConfig = getActionRiskLabel(finding.riskLevel);
  const actionTypeLabel = getActionTypeLabel(finding.actionType);
  const canExecute = isActionExecutableInDemo(finding.safetyMode);

  // Handle copy recommendation
  const handleCopyRecommendation = async () => {
    if (ctaConfig.disabled) return;

    const textToCopy = [
      `Recommendation: ${finding.recommendedAction}`,
      finding.commandPreview ? `\nCommand preview:\n${finding.commandPreview}` : "",
      finding.expectedOutcome ? `\nExpected outcome: ${finding.expectedOutcome}` : "",
    ]
      .filter(Boolean)
      .join("\n");

    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API not available, silently fail
    }
  };

  return (
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

      <div className="demo-action-panel" data-testid="demo-action-panel">
        {/* Header with title and safety badge */}
        <div className="demo-action-header">
          <h2 className="demo-action-title" data-testid="action-title">
            Recommended Action
          </h2>
          <SafetyModeLabel mode={finding.safetyMode} />
        </div>

        {/* Safety Mode Panel */}
        <div className="demo-safety-mode-panel" data-testid="safety-mode-panel">
          <div className="demo-safety-mode-header">
            <span className="demo-safety-mode-icon">🛡️</span>
            <h3 className="demo-safety-mode-title">{safetyCopy.title}</h3>
          </div>
          <p className="demo-safety-mode-description">{safetyCopy.description}</p>
          {safetyCopy.warning && (
            <p className="demo-safety-mode-warning">{safetyCopy.warning}</p>
          )}
        </div>

        {/* Remediation Preview Section */}
        <div className="demo-remediation-preview" data-testid="remediation-preview">
          <h3 className="demo-section-label">Remediation preview</h3>

          <div className="demo-remediation-card">
            {/* Action title */}
            <p className="demo-remediation-action">{finding.recommendedAction}</p>

            {/* Action metadata */}
            <div className="demo-action-metadata">
              {finding.actionType && (
                <span className="demo-metadata-item">
                  <span className="demo-metadata-label">Type:</span>
                  <span className="demo-metadata-value">{actionTypeLabel}</span>
                </span>
              )}
              {finding.actionScope && (
                <span className="demo-metadata-item">
                  <span className="demo-metadata-label">Scope:</span>
                  <span className="demo-metadata-value">{finding.actionScope}</span>
                </span>
              )}
              {finding.riskLevel && (
                <span className={`demo-metadata-item demo-risk-badge ${riskConfig.colorClass}`}>
                  <span className="demo-metadata-label">Risk:</span>
                  <span className="demo-metadata-value">{riskConfig.label}</span>
                </span>
              )}
            </div>

            {/* Command preview when available */}
            {finding.commandPreview && (
              <div className="demo-command-preview">
                <h4 className="demo-command-label">Command preview</h4>
                <pre className="demo-command-code" data-testid="command-preview">
                  {finding.commandPreview}
                </pre>
              </div>
            )}

            {/* Expected outcome when available */}
            {finding.expectedOutcome && (
              <div className="demo-expected-outcome">
                <h4 className="demo-outcome-label">Expected outcome</h4>
                <p className="demo-outcome-text">{finding.expectedOutcome}</p>
              </div>
            )}
          </div>
        </div>

        {/* Provenance / Evidence Section */}
        <div className="demo-provenance-section" data-testid="provenance-section">
          <h3 className="demo-section-label">Evidence provenance</h3>

          <div className="demo-provenance-grid">
            <div className="demo-provenance-item">
              <span className="demo-provenance-label">Severity</span>
              <span className={`demo-provenance-value demo-severity-${finding.severity}`}>
                {finding.severity.charAt(0).toUpperCase() + finding.severity.slice(1)}
              </span>
            </div>

            <div className="demo-provenance-item">
              <span className="demo-provenance-label">Evidence source</span>
              <span className="demo-provenance-value">
                {EVIDENCE_SOURCE_LABELS[finding.evidenceSource]}
              </span>
            </div>

            <div className="demo-provenance-item">
              <span className="demo-provenance-label">Affected resource</span>
              <span className="demo-provenance-value">{finding.affectedResource}</span>
            </div>

            <div className="demo-provenance-item demo-provenance-item--full">
              <span className="demo-provenance-label">Diagnostic evidence</span>
              <span className="demo-provenance-value">{finding.diagnosticEvidence}</span>
            </div>

            <div className="demo-provenance-item demo-provenance-item--full">
              <span className="demo-provenance-label">Probable cause</span>
              <span className="demo-provenance-value">{finding.probableCause}</span>
            </div>
          </div>
        </div>

        {/* Approval Requirement Callout */}
        <div className="demo-approval-callout" data-testid="approval-callout">
          <div className="demo-approval-icon">⚠️</div>
          <div className="demo-approval-content">
            <h4 className="demo-approval-title">Operator approval required</h4>
            <p className="demo-approval-text">
              This is a recommendation only. No cluster mutations are performed from this panel.
              Any production action requires explicit operator approval through the CLI.
            </p>
          </div>
        </div>

        {/* CTA / Action Button */}
        <div className="demo-action-cta" data-testid="action-cta">
          {finding.safetyMode === "preview-only" ? (
            <button
              type="button"
              className="demo-button demo-button--secondary demo-button--copy"
              onClick={handleCopyRecommendation}
              data-testid="copy-recommendation-button"
            >
              {copied ? "✓ Copied!" : ctaConfig.label}
            </button>
          ) : (
            <button
              type="button"
              className="demo-button demo-button--primary demo-button--disabled"
              disabled
              data-testid="disabled-cta-button"
            >
              {ctaConfig.label}
            </button>
          )}
          <p className="demo-cta-hint">{ctaConfig.hint}</p>
          {canExecute && (
            <p className="demo-cta-warning" data-testid="execution-warning">
              ⚠️ Execution should be disabled in demo mode
            </p>
          )}
        </div>

        {/* Evidence-preserving workflow note */}
        <div className="demo-workflow-note">
          <p>
            <strong>Evidence-preserving workflow:</strong> This panel displays diagnostic
            recommendations derived from real cluster evidence. No mutations are applied
            automatically.
          </p>
        </div>
      </div>
    </div>
  );
};
