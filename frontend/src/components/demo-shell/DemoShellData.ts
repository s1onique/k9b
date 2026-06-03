/**
 * Demo Shell Data and Constants
 *
 * Constants, labels, and helper functions for DemoShell component.
 */

import type { ActionRiskLevel, ActionType, DemoStep, EvidenceSource, SafetyMode, SeverityLevel } from "./DemoShellTypes";

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

// =============================================================================
// Action Panel Helper Functions
// =============================================================================

/**
 * Get detailed safety mode copy for the action panel.
 * Provides user-friendly messaging about what the mode means.
 */
export function getActionSafetyCopy(mode: SafetyMode): {
  title: string;
  description: string;
  warning?: string;
} {
  switch (mode) {
    case "read-only":
      return {
        title: "Read-only Mode",
        description: "No cluster mutations will be performed.",
        warning: "Use this action as a diagnostic recommendation.",
      };
    case "operator-approved":
      return {
        title: "Operator-Approved Mode",
        description: "Requires explicit operator approval before execution.",
        warning: "No action runs automatically.",
      };
    case "preview-only":
      return {
        title: "Preview Only",
        description: "Command/action is shown for review only.",
        warning: "Execution is disabled in this demo step.",
      };
  }
}

/**
 * Get the CTA (Call-to-Action) label for the action panel.
 * Returns a disabled/non-executing label based on safety mode.
 */
export function getActionCta(mode: SafetyMode): {
  label: string;
  disabled: boolean;
  hint: string;
} {
  switch (mode) {
    case "read-only":
      return {
        label: "Preview command",
        disabled: true,
        hint: "Execution disabled — read-only mode",
      };
    case "operator-approved":
      return {
        label: "Operator approval required",
        disabled: true,
        hint: "Requires explicit operator approval",
      };
    case "preview-only":
      return {
        label: "Copy recommendation",
        disabled: false,
        hint: "Copy to clipboard for review",
      };
  }
}

/**
 * Determine if an action is executable in the demo.
 * Always returns false in this ACT — no real execution allowed.
 */
export function isActionExecutableInDemo(mode: SafetyMode): boolean {
  // In this ACT, no actions are executable in demo mode
  return false;
}

/**
 * Get risk level display label.
 */
export function getActionRiskLabel(riskLevel?: ActionRiskLevel): {
  label: string;
  colorClass: string;
} {
  const configs: Record<ActionRiskLevel, { label: string; colorClass: string }> = {
    low: { label: "Low Risk", colorClass: "demo-risk-low" },
    medium: { label: "Medium Risk", colorClass: "demo-risk-medium" },
    high: { label: "High Risk", colorClass: "demo-risk-high" },
    unknown: { label: "Unknown Risk", colorClass: "demo-risk-unknown" },
  };
  return riskLevel ? configs[riskLevel] : configs.unknown;
}

/**
 * Get action type display label.
 */
export function getActionTypeLabel(actionType?: ActionType): string {
  const labels: Record<ActionType, string> = {
    diagnostic: "Diagnostic",
    configuration: "Configuration",
    restart: "Restart",
    scale: "Scale",
    unknown: "Unknown",
  };
  return actionType ? labels[actionType] : labels.unknown;
}

/**
 * Forbidden CTA labels that must never appear.
 */
export const FORBIDDEN_CTA_LABELS = [
  "fix now",
  "auto-fix",
  "repair cluster",
  "apply production fix",
  "run remediation",
];

/**
 * Check if a CTA label is forbidden.
 */
export function isForbiddenCtaLabel(label: string): boolean {
  const lowerLabel = label.toLowerCase();
  return FORBIDDEN_CTA_LABELS.some((forbidden) => lowerLabel.includes(forbidden));
}
