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

import { useState, useMemo, useEffect } from "react";
import type {
  DemoFinding,
  DemoStep,
  EvidenceSource,
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
import { selectDemoFindings, selectHistoricalFindings, getCleanClusterFallback } from "../features/demo";

// Re-export types for backward compatibility
export type { DemoStep, EvidenceSource, SeverityLevel, SafetyMode, DemoFinding, DemoShellRealContext };

// Re-export DEFAULT_CONNECTION_DELAY_MS for backward compatibility
export { DEFAULT_CONNECTION_DELAY_MS };

// Extended props including finding selection input and real context
export interface DemoShellProps {
  /** Callback when demo shell is closed */
  onClose?: () => void;
  /** Initial step for testing */
  initialStep?: DemoStep;
  /** Input for finding selection (incident report, worklist, freshness) */
  findingSelectionInput?: {
    incidentReport?: {
      status?: "critical" | "degraded" | "warning" | "healthy";
      severity?: SeverityLevel;
      resource?: string;
      findingType?: string;
    };
    operatorWorklist?: Array<{
      severity?: SeverityLevel;
      resource?: string;
      status?: string;
      message?: string;
    }>;
    freshness?: {
      age?: number;
      isStale?: boolean;
    };
    runId?: string;
    clusterLabel?: string;
  };
  /** Pre-selected historical findings for fallback */
  historicalFindings?: DemoFinding[];
  /** Real context metadata when launched from the main app */
  realContext?: {
    runId: string;
    clusterLabel?: string;
    isFresh: boolean;
    runCapturedAt?: string;
    initialSafetyMode?: SafetyMode;
  };
}

// =============================================================================
// Main Component
// =============================================================================

export const DemoShell = ({
  onClose,
  initialStep = "start",
  findingSelectionInput,
  historicalFindings,
  realContext,
}: DemoShellProps) => {
  const [currentStep, setCurrentStep] = useState<DemoStep>(initialStep);
  const [isConnecting, setIsConnecting] = useState(false);
  const [selectedFinding, setSelectedFinding] = useState<DemoFinding | null>(null);
  const [isCleanCluster, setIsCleanCluster] = useState(false);

  // Compute findings based on input data
  const { findings, evidenceSource, explanation } = useMemo(() => {
    // If no input provided, return empty result
    if (!findingSelectionInput) {
      return {
        findings: [] as DemoFinding[],
        evidenceSource: "none" as EvidenceSource,
        explanation: "No finding selection input provided",
      };
    }

    // Try to select live findings first
    const liveResult = selectDemoFindings(findingSelectionInput);

    // If live selection has findings, use them
    if (liveResult.findings.length > 0) {
      return {
        findings: liveResult.findings,
        evidenceSource: liveResult.source,
        explanation: liveResult.explanation,
      };
    }

    // Fall back to historical findings if no live findings
    if (historicalFindings && historicalFindings.length > 0) {
      const historicalResult = selectHistoricalFindings(historicalFindings);
      return {
        findings: historicalResult.findings,
        evidenceSource: historicalResult.source,
        explanation: historicalResult.explanation,
      };
    }

    // No findings available, return clean cluster fallback
    const fallbackResult = getCleanClusterFallback({
      hasHistoricalEvidence: (historicalFindings?.length ?? 0) > 0,
    });
    return {
      findings: fallbackResult.findings,
      evidenceSource: fallbackResult.source,
      explanation: fallbackResult.explanation,
    };
  }, [findingSelectionInput, historicalFindings]);

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

  // Sync clean cluster state based on findings availability (only when findingSelectionInput is provided)
  useEffect(() => {
    if (findings.length === 0 && currentStep === "dashboard" && findingSelectionInput) {
      setIsCleanCluster(true);
    }
  }, [findings.length, currentStep, findingSelectionInput]);

  // Auto-select first finding when starting at finding-detail or action-panel step
  useEffect(() => {
    if ((initialStep === "finding-detail" || initialStep === "action-panel") && findings.length > 0) {
      setSelectedFinding(findings[0]);
    }
  }, [initialStep, findings]);

  const renderDashboard = () => (
    <DashboardScreen
      realContext={realContext}
      findings={findings}
      evidenceSource={evidenceSource}
      explanation={explanation}
      onSelectFinding={handleSelectFinding}
      onCleanClusterFallback={handleCleanClusterFallback}
      isCleanCluster={isCleanCluster}
    />
  );

  const renderStep = () => {
    switch (currentStep) {
      case "start":
        return <StartScreen onConnect={handleStartDemo} />;
      case "onboarding":
        return (
          <OnboardingScreen
            onConnected={handleConnect}
            isConnecting={isConnecting}
            realContext={realContext}
          />
        );
      case "dashboard":
        return renderDashboard();
      case "finding-detail":
        return selectedFinding ? (
          <FindingDetailPanel
            finding={selectedFinding}
            onBack={handleBackToDashboard}
            onViewAction={handleViewAction}
          />
        ) : (
          renderDashboard()
        );
      case "action-panel":
        return selectedFinding ? (
          <ActionPanel finding={selectedFinding} onBack={handleBackToFinding} />
        ) : (
          renderDashboard()
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
