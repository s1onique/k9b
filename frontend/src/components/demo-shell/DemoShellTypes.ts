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

/** Props for DemoShell component */
export interface DemoShellProps {
  /** Callback when demo shell is closed */
  onClose?: () => void;
  /** Initial step for testing */
  initialStep?: DemoStep;
}