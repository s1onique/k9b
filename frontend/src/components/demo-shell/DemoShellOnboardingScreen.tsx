/**
 * Demo Shell Onboarding Screen Component
 *
 * Shows real run context summary when launched from the main app.
 * This replaces the fake cluster connection step.
 */

import { useState } from "react";
import type { DemoShellRealContext, SafetyMode } from "./DemoShellTypes";
import { SafetyModeLabel } from "./DemoShellBadges";
import { getSafetyModeDescription, getFreshnessLabel } from "./DemoShellData";

interface OnboardingScreenProps {
  onConnected: () => void;
  isConnecting: boolean;
  /** Real context metadata when launched from the main app */
  realContext?: DemoShellRealContext;
}

/**
 * Format a run ID for display (truncate if too long)
 */
function formatRunId(runId: string | undefined): string {
  if (!runId) return "—";
  if (runId.length <= 12) return runId;
  return `${runId.slice(0, 8)}...`;
}

export const OnboardingScreen = ({ onConnected, isConnecting, realContext }: OnboardingScreenProps) => {
  const [safetyMode, setSafetyMode] = useState<SafetyMode>(realContext?.initialSafetyMode ?? "read-only");
  const hasRealContext = Boolean(realContext?.runId);

  return (
    <div className="demo-screen demo-screen--onboarding">
      <div className="demo-hero">
        <h2 className="demo-subtitle">
          {hasRealContext ? "Selected real run" : "Ready to start demo"}
        </h2>
        <p className="demo-description">
          {hasRealContext
            ? "View findings from the currently selected real run and cluster."
            : "No real run selected. You can still explore the demo shell."}
        </p>
      </div>

      <div className="demo-onboarding-form">
        {/* Real context summary - shown when launched from main app */}
        {hasRealContext && (
          <div className="demo-context-summary">
            <div className="demo-context-row">
              <span className="demo-context-label">Run ID</span>
              <span className="demo-context-value" data-testid="demo-context-run-id">
                {formatRunId(realContext.runId)}
              </span>
            </div>
            {realContext.clusterLabel && (
              <div className="demo-context-row">
                <span className="demo-context-label">Cluster</span>
                <span className="demo-context-value" data-testid="demo-context-cluster">
                  {realContext.clusterLabel}
                </span>
              </div>
            )}
            <div className="demo-context-row">
              <span className="demo-context-label">State</span>
              <span
                className={`demo-context-value demo-context-freshness ${
                  realContext.isFresh ? "demo-context-fresh" : "demo-context-stale"
                }`}
                data-testid="demo-context-freshness"
              >
                {getFreshnessLabel(realContext.isFresh)}
              </span>
            </div>
            <div className="demo-context-row">
              <span className="demo-context-label">Safety mode</span>
              <SafetyModeLabel mode={safetyMode} />
            </div>
          </div>
        )}

        {/* Safety mode selection */}
        <div className="demo-form-group">
          <label className="demo-label">Safety mode</label>
          <div className="demo-safety-modes">
            <label className="demo-radio-label">
              <input
                type="radio"
                name="safety-mode"
                value="read-only"
                checked={safetyMode === "read-only"}
                onChange={() => setSafetyMode("read-only")}
                disabled={isConnecting}
              />
              <span className="demo-radio-text">
                <strong>Read-only</strong>
                <span className="demo-radio-hint">Display analysis only, no mutations</span>
              </span>
            </label>
            <label className="demo-radio-label">
              <input
                type="radio"
                name="safety-mode"
                value="operator-approved"
                checked={safetyMode === "operator-approved"}
                onChange={() => setSafetyMode("operator-approved")}
                disabled={isConnecting}
              />
              <span className="demo-radio-text">
                <strong>Operator-approved</strong>
                <span className="demo-radio-hint">Execute after explicit approval</span>
              </span>
            </label>
            <label className="demo-radio-label">
              <input
                type="radio"
                name="safety-mode"
                value="preview-only"
                checked={safetyMode === "preview-only"}
                onChange={() => setSafetyMode("preview-only")}
                disabled={isConnecting}
              />
              <span className="demo-radio-text">
                <strong>Preview only</strong>
                <span className="demo-radio-hint">Show command without execution</span>
              </span>
            </label>
          </div>
        </div>

        <div className="demo-safety-indicator">
          <SafetyModeLabel mode={safetyMode} />
          <span className="demo-safety-description">
            {getSafetyModeDescription(safetyMode)}
          </span>
        </div>

        <button
          type="button"
          className="demo-button demo-button--primary"
          onClick={onConnected}
          disabled={isConnecting}
          data-testid="demo-connect-button"
        >
          {isConnecting ? "Loading..." : "Continue with selected run"}
        </button>
      </div>
    </div>
  );
};
