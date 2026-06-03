/**
 * Demo Shell Onboarding Screen Component
 *
 * Cluster connection and safety mode selection screen.
 */

import { useState } from "react";
import type { SafetyMode } from "./DemoShellTypes";
import { SafetyModeLabel } from "./DemoShellBadges";
import { getSafetyModeDescription } from "./DemoShellData";

interface OnboardingScreenProps {
  onConnected: () => void;
  isConnecting: boolean;
}

export const OnboardingScreen = ({ onConnected, isConnecting }: OnboardingScreenProps) => {
  const [safetyMode, setSafetyMode] = useState<SafetyMode>("read-only");

  return (
    <div className="demo-screen demo-screen--onboarding">
      <div className="demo-hero">
        <h2 className="demo-subtitle">Connect your cluster</h2>
        <p className="demo-description">
          Select a Kubernetes context and connect in read-only mode.
          The system will collect real diagnostic evidence.
        </p>
      </div>

      <div className="demo-onboarding-form">
        <div className="demo-form-group">
          <label htmlFor="kube-context" className="demo-label">
            Kubernetes context
          </label>
          <select
            id="kube-context"
            className="demo-select"
            defaultValue="minikube"
            disabled={isConnecting}
          >
            <option value="minikube">minikube</option>
            <option value="kind-dev">kind-dev</option>
            <option value="prod-cluster">prod-cluster</option>
          </select>
        </div>

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
          {isConnecting ? "Connecting..." : "Connect in read-only mode"}
        </button>
      </div>
    </div>
  );
};