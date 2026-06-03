/**
 * DemoShell Component
 *
 * Clickable real-cluster demo path shell for the K8s Accelerator 2-minute sales walkthrough.
 *
 * Implements the path: Start → Onboarding → Dashboard → Finding Detail → Recommended Action
 *
 * Truth boundaries (from docs/reports/k8s-accelerator-real-cluster-demo-storyline.md):
 * - No fake incidents injected
 * - Real cluster evidence first
 * - Historical real evidence fallback
 * - Clean-cluster honest fallback
 * - No autonomous remediation claims
 * - Read-only safety mode by default
 */

import { useState } from "react";
import type {
  DemoFinding,
  DemoShellProps,
  DemoStep,
  EvidenceSource,
  SeverityLevel,
  SafetyMode,
} from "./demo-shell/DemoShellTypes";
import { DEFAULT_CONNECTION_DELAY_MS, getStepName } from "./demo-shell/DemoShellData";
import {
  StartScreen,
  OnboardingScreen,
  DashboardScreen,
  FindingDetailPanel,
  ActionPanel,
} from "./demo-shell";

// Re-export types for backward compatibility
export type { DemoStep, EvidenceSource, SeverityLevel, SafetyMode, DemoFinding };
export type { DemoShellProps };

// Re-export DEFAULT_CONNECTION_DELAY_MS for backward compatibility
export { DEFAULT_CONNECTION_DELAY_MS };

// =============================================================================
// Main Component
// =============================================================================

export const DemoShell = ({ onClose, initialStep = "start" }: DemoShellProps) => {
  const [currentStep, setCurrentStep] = useState<DemoStep>(initialStep);
  const [isConnecting, setIsConnecting] = useState(false);
  const [selectedFinding, setSelectedFinding] = useState<DemoFinding | null>(null);
  const [isCleanCluster, setIsCleanCluster] = useState(false);

  const handleStartDemo = () => {
    setCurrentStep("onboarding");
  };

  const handleConnect = () => {
    setIsConnecting(true);
    // Simulate connection delay
    setTimeout(() => {
      setIsConnecting(false);
      setCurrentStep("dashboard");
    }, DEFAULT_CONNECTION_DELAY_MS);
  };

  const handleSelectFinding = (finding: DemoFinding) => {
    setSelectedFinding(finding);
    setCurrentStep("finding-detail");
  };

  const handleViewAction = () => {
    setCurrentStep("action-panel");
  };

  const handleBackToDashboard = () => {
    setSelectedFinding(null);
    setCurrentStep("dashboard");
  };

  const handleBackToFinding = () => {
    setCurrentStep("finding-detail");
  };

  const handleCleanClusterFallback = () => {
    setIsCleanCluster(true);
    setCurrentStep("dashboard");
  };

  const renderStep = () => {
    switch (currentStep) {
      case "start":
        return <StartScreen onConnect={handleStartDemo} />;
      case "onboarding":
        return (
          <OnboardingScreen
            onConnected={handleConnect}
            isConnecting={isConnecting}
          />
        );
      case "dashboard":
        return (
          <DashboardScreen
            clusterName="minikube"
            onSelectFinding={handleSelectFinding}
            onCleanClusterFallback={handleCleanClusterFallback}
            isCleanCluster={isCleanCluster}
          />
        );
      case "finding-detail":
        return selectedFinding ? (
          <FindingDetailPanel
            finding={selectedFinding}
            onBack={handleBackToDashboard}
            onViewAction={handleViewAction}
          />
        ) : (
          <DashboardScreen
            clusterName="minikube"
            onSelectFinding={handleSelectFinding}
            onCleanClusterFallback={handleCleanClusterFallback}
            isCleanCluster={isCleanCluster}
          />
        );
      case "action-panel":
        return selectedFinding ? (
          <ActionPanel finding={selectedFinding} onBack={handleBackToFinding} />
        ) : (
          <DashboardScreen
            clusterName="minikube"
            onSelectFinding={handleSelectFinding}
            onCleanClusterFallback={handleCleanClusterFallback}
            isCleanCluster={isCleanCluster}
          />
        );
      default:
        return <StartScreen onConnect={handleStartDemo} />;
    }
  };

  return (
    <div
      className="demo-shell-overlay"
      data-testid="demo-shell"
      data-demo-step={currentStep}
      data-demo-clean-cluster={isCleanCluster}
    >
      <div className="demo-shell-container">
        <div className="demo-shell-header">
          <h1 className="demo-shell-title">K8s Accelerator Demo</h1>
          <div className="demo-shell-meta">
            <span className="demo-step-indicator">
              Step: {getStepName(currentStep)}
            </span>
            {onClose && (
              <button
                type="button"
                className="demo-close-button"
                onClick={onClose}
                aria-label="Close demo"
                data-testid="demo-close-button"
              >
                ✕
              </button>
            )}
          </div>
        </div>
        <div className="demo-shell-content">{renderStep()}</div>
        <div className="demo-shell-footer">
          <p className="demo-footer-text">
            Real cluster evidence · No fake incidents · Safety-first design
          </p>
        </div>
      </div>
    </div>
  );
};

export default DemoShell;