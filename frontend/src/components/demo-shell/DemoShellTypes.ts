/**
 * Demo Shell Type Definitions
 *
 * Exported types for DemoShell component.
 */

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

/** Action risk level */
export type ActionRiskLevel = "low" | "medium" | "high" | "unknown";

/** Action type classification */
export type ActionType = "diagnostic" | "configuration" | "restart" | "scale" | "unknown";

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
  /** Optional command preview for remediation */
  commandPreview?: string;
  /** Expected outcome description */
  expectedOutcome?: string;
  /** Risk level for the recommended action */
  riskLevel?: ActionRiskLevel;
  /** Scope of the action (e.g., "namespace", "pod", "cluster") */
  actionScope?: string;
  /** Type of action being recommended */
  actionType?: ActionType;
  safetyMode: SafetyMode;
}

/** Props for DemoShell component */
export interface DemoShellProps {
  /** Callback when demo shell is closed */
  onClose?: () => void;
  /** Initial step for testing */
  initialStep?: DemoStep;
}