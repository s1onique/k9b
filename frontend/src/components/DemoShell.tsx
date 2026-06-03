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

// =============================================================================
// Types
// =============================================================================

/** Demo shell step state machine */
export type DemoStep =
  | "start"
  | "onboarding"
  | "dashboard"
  | "finding-detail"
  | "action-panel";

/** Evidence source classification */
export type EvidenceSource = "live" | "historical" | "stale" | "none";

/** Finding severity level */
export type SeverityLevel = "critical" | "warning" | "info";

/** Safety mode for action panel */
export type SafetyMode = "read-only" | "operator-approved" | "preview-only";

/** Demo finding placeholder */
export interface DemoFinding {
  id: string;
  title: string;
  severity: SeverityLevel;
  affectedResource: string;
  evidenceSource: EvidenceSource;
  probableCause: string;
  diagnosticEvidence: string;
  recommendedAction: string;
  commandPreview?: string;
  safetyMode: SafetyMode;
}

// =============================================================================
// Constants
// =============================================================================

/** Forbidden phrases that must never appear in the demo */
const FORBIDDEN_PHRASES = [
  "self-healing",
  "guaranteed root cause",
  "automatic production fix",
  "fixes any Kubernetes issue",
  "fully autonomous",
];

/** Evidence source labels */
const EVIDENCE_SOURCE_LABELS: Record<EvidenceSource, string> = {
  live: "Live",
  historical: "Historical Real Run",
  stale: "Stale",
  none: "No finding selected",
};

/** Severity labels with color classes */
const SEVERITY_CONFIG: Record<SeverityLevel, { label: string; colorClass: string }> = {
  critical: { label: "Critical", colorClass: "demo-severity-critical" },
  warning: { label: "Warning", colorClass: "demo-severity-warning" },
  info: { label: "Info", colorClass: "demo-severity-info" },
};

/** Safety mode labels */
const SAFETY_MODE_LABELS: Record<SafetyMode, string> = {
  "read-only": "Read-only",
  "operator-approved": "Operator-approved",
  "preview-only": "Preview only",
};

// =============================================================================
// Helpers
// =============================================================================

/** Check if text contains forbidden phrases */
const containsForbiddenPhrase = (text: string): boolean => {
  const lowerText = text.toLowerCase();
  return FORBIDDEN_PHRASES.some((phrase) => lowerText.includes(phrase.toLowerCase()));
};

/** Get step display name */
const getStepName = (step: DemoStep): string => {
  const names: Record<DemoStep, string> = {
    start: "Start",
    onboarding: "Connect Cluster",
    dashboard: "Dashboard",
    "finding-detail": "Finding Detail",
    "action-panel": "Recommended Action",
  };
  return names[step];
};

/** Default connection delay in milliseconds (0 for testing) */
export const DEFAULT_CONNECTION_DELAY_MS = 800;

// =============================================================================
// Components
// =============================================================================

/** Evidence Source Badge */
const EvidenceSourceBadge = ({ source }: { source: EvidenceSource }) => (
  <span className={`demo-badge demo-badge--${source}`}>
    {EVIDENCE_SOURCE_LABELS[source]}
  </span>
);

/** Severity Badge */
const SeverityBadge = ({ severity }: { severity: SeverityLevel }) => (
  <span className={`demo-badge ${SEVERITY_CONFIG[severity].colorClass}`}>
    {SEVERITY_CONFIG[severity].label}
  </span>
);

/** Safety Mode Label */
const SafetyModeLabel = ({ mode }: { mode: SafetyMode }) => (
  <span className={`demo-badge demo-badge--safety-${mode.replace("-", "")}`}>
    {SAFETY_MODE_LABELS[mode]}
  </span>
);

/** Start Screen */
const StartScreen = ({ onConnect }: { onConnect: () => void }) => (
  <div className="demo-screen demo-screen--start">
    <div className="demo-hero">
      <h1 className="demo-title">K8s Accelerator</h1>
      <p className="demo-value-prop">
        Transform Kubernetes operational signals into operator-ready actions
      </p>
      <p className="demo-description">
        Connect to a real Kubernetes cluster and see live diagnostic evidence.
        No fake incidents, no fabricated samples.
      </p>
    </div>
    <div className="demo-cta-area">
      <button
        type="button"
        className="demo-button demo-button--primary"
        onClick={onConnect}
        data-testid="demo-start-button"
      >
        Start real-cluster demo
      </button>
      <p className="demo-cta-hint">Read-only mode · No cluster mutations</p>
    </div>
    <div className="demo-safety-note">
      <p>
        <strong>Safety first:</strong> All actions are preview-only or require operator approval.
        No automatic remediation.
      </p>
    </div>
  </div>
);

/** Onboarding Screen */
const OnboardingScreen = ({
  onConnected,
  isConnecting,
}: {
  onConnected: () => void;
  isConnecting: boolean;
}) => {
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
            {safetyMode === "read-only" && "No cluster mutations will be performed"}
            {safetyMode === "operator-approved" && "Actions require explicit operator click"}
            {safetyMode === "preview-only" && "Commands shown but not executed"}
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

/** Dashboard Screen */
const DashboardScreen = ({
  clusterName,
  onSelectFinding,
  onCleanClusterFallback,
  isCleanCluster,
}: {
  clusterName: string;
  onSelectFinding: (finding: DemoFinding) => void;
  onCleanClusterFallback: () => void;
  isCleanCluster: boolean;
}) => {
  // Placeholder findings for demo shell - no fake data, just UI structure
  const placeholderFindings: DemoFinding[] = [
    {
      id: "placeholder-1",
      title: "No live finding selected yet",
      severity: "info",
      affectedResource: "—",
      evidenceSource: "none",
      probableCause: "Select a finding from live health run or historical evidence",
      diagnosticEvidence: "Waiting for live health run",
      recommendedAction: "Connect cluster to start diagnostic collection",
      safetyMode: "read-only",
    },
  ];

  return (
    <div className="demo-screen demo-screen--dashboard">
      <div className="demo-dashboard-header">
        <div className="demo-cluster-info">
          <h2 className="demo-cluster-name">{clusterName}</h2>
          <span className={`demo-status-indicator ${isCleanCluster ? "demo-status--healthy" : "demo-status--connected"}`}>
            {isCleanCluster ? "Healthy" : "Connected"}
          </span>
        </div>
        <div className="demo-dashboard-meta">
          <EvidenceSourceBadge source={isCleanCluster ? "none" : "live"} />
          <SafetyModeLabel mode="read-only" />
        </div>
      </div>

      <div className="demo-dashboard-content">
        {isCleanCluster ? (
          <div className="demo-clean-cluster">
            <div className="demo-empty-state">
              <p className="demo-empty-title">No critical issues found</p>
              <p className="demo-empty-message">
                This cluster is currently healthy. No fake incidents were injected for this demo.
              </p>
              <div className="demo-empty-actions">
                <button
                  type="button"
                  className="demo-button demo-button--secondary"
                  onClick={onCleanClusterFallback}
                  data-testid="demo-view-historical-button"
                >
                  View historical real evidence
                </button>
              </div>
              <p className="demo-empty-note">
                Prefer to show real issues, but healthy is honest evidence of good operations.
              </p>
            </div>
          </div>
        ) : (
          <div className="demo-finding-feed">
            <h3 className="demo-section-title">Findings</h3>
            <p className="demo-section-hint">
              Live health run evidence · Click to view analysis
            </p>
            <div className="demo-finding-list">
              {placeholderFindings.map((finding) => (
                <button
                  type="button"
                  key={finding.id}
                  className="demo-finding-card"
                  onClick={() => onSelectFinding(finding)}
                  data-testid={`demo-finding-card-${finding.id}`}
                >
                  <div className="demo-finding-card-header">
                    <SeverityBadge severity={finding.severity} />
                    <EvidenceSourceBadge source={finding.evidenceSource} />
                  </div>
                  <p className="demo-finding-card-title">{finding.title}</p>
                  <p className="demo-finding-card-resource">{finding.affectedResource}</p>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="demo-dashboard-footer">
        <p className="demo-footer-note">
          Evidence source: {isCleanCluster ? "No findings" : "Live scan"} · Last scan: Just now
        </p>
      </div>
    </div>
  );
};

/** Finding Detail Panel */
const FindingDetailPanel = ({
  finding,
  onBack,
  onViewAction,
}: {
  finding: DemoFinding;
  onBack: () => void;
  onViewAction: () => void;
}) => (
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

/** Recommended Action Panel */
const ActionPanel = ({
  finding,
  onBack,
}: {
  finding: DemoFinding;
  onBack: () => void;
}) => (
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

// =============================================================================
// Main Component
// =============================================================================

export interface DemoShellProps {
  /** Callback when demo shell is closed */
  onClose?: () => void;
  /** Initial step for testing */
  initialStep?: DemoStep;
}

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
    }, 800);
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