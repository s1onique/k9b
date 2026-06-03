/**
 * Demo Shell Data and Constants
 *
 * Constants, labels, and helper functions for DemoShell component.
 */

import type { DemoStep, EvidenceSource, SafetyMode, SeverityLevel } from "./DemoShellTypes";

/** Forbidden phrases that must never appear in the demo */
export const FORBIDDEN_PHRASES = [
  "self-healing",
  "guaranteed root cause",
  "automatic production fix",
  "fixes any Kubernetes issue",
  "fully autonomous",
];

/** Evidence source labels */
export const EVIDENCE_SOURCE_LABELS: Record<EvidenceSource, string> = {
  live: "Live",
  historical: "Historical Real Run",
  stale: "Stale",
  none: "No finding selected",
};

/** Severity labels with color classes */
export const SEVERITY_CONFIG: Record<SeverityLevel, { label: string; colorClass: string }> = {
  critical: { label: "Critical", colorClass: "demo-severity-critical" },
  warning: { label: "Warning", colorClass: "demo-severity-warning" },
  info: { label: "Info", colorClass: "demo-severity-info" },
};

/** Safety mode labels */
export const SAFETY_MODE_LABELS: Record<SafetyMode, string> = {
  "read-only": "Read-only",
  "operator-approved": "Operator-approved",
  "preview-only": "Preview only",
};

/** Default connection delay in milliseconds (0 for testing) */
export const DEFAULT_CONNECTION_DELAY_MS = 800;

/** Check if text contains forbidden phrases */
export const containsForbiddenPhrase = (text: string): boolean => {
  const lowerText = text.toLowerCase();
  return FORBIDDEN_PHRASES.some((phrase) => lowerText.includes(phrase.toLowerCase()));
};

/** Get step display name */
export const getStepName = (step: DemoStep): string => {
  const names: Record<DemoStep, string> = {
    start: "Start",
    onboarding: "Connect Cluster",
    dashboard: "Dashboard",
    "finding-detail": "Finding Detail",
    "action-panel": "Recommended Action",
  };
  return names[step];
};

/** Get safety mode description */
export const getSafetyModeDescription = (mode: SafetyMode): string => {
  const descriptions: Record<SafetyMode, string> = {
    "read-only": "No cluster mutations will be performed",
    "operator-approved": "Actions require explicit operator click",
    "preview-only": "Commands shown but not executed",
  };
  return descriptions[mode];
};