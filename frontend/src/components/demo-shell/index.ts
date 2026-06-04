/**
 * Demo Shell Module
 *
 * Re-exports for backward compatibility with existing imports.
 */

// Types
export type {
  DemoStep,
  EvidenceSource,
  SeverityLevel,
  SafetyMode,
  DemoFinding,
  DemoShellProps,
  DemoShellRealContext,
} from "./DemoShellTypes";

// Data and constants
export {
  FORBIDDEN_PHRASES,
  EVIDENCE_SOURCE_LABELS,
  SEVERITY_CONFIG,
  SAFETY_MODE_LABELS,
  DEFAULT_CONNECTION_DELAY_MS,
  containsForbiddenPhrase,
  getStepName,
  getSafetyModeDescription,
  getFreshnessLabel,
  getActionSafetyCopy,
  getActionCta,
  getActionRiskLabel,
  getActionTypeLabel,
  isActionExecutableInDemo,
  FORBIDDEN_CTA_LABELS,
  isForbiddenCtaLabel,
} from "./DemoShellData";

// Badges
export { EvidenceSourceBadge, SeverityBadge, SafetyModeLabel } from "./DemoShellBadges";

// Screen components
export { StartScreen } from "./DemoShellStartScreen";
export { OnboardingScreen } from "./DemoShellOnboardingScreen";
export { DashboardScreen } from "./DemoShellDashboardScreen";
export { FindingDetailPanel } from "./DemoShellFindingDetailScreen";
export { ActionPanel } from "./DemoShellActionPanelScreen";

// Main component - imported from parent DemoShell.tsx
// Note: Re-exporting from parent to maintain backward compatibility
