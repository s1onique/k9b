/**
 * Demo Finding Selection Module
 *
 * Deterministic finding selection for the real-cluster demo shell.
 * Follows priority: live critical → live warning → historical real → clean fallback.
 *
 * Truth boundaries:
 * - No fake incidents injected
 * - Real cluster evidence first
 * - Historical real evidence fallback only
 * - Clean-cluster honest fallback when no findings exist
 * - Recommended actions are preview-only, not executable
 */

import type { DemoFinding, EvidenceSource, SeverityLevel } from "../../components/demo-shell/DemoShellTypes";

// =============================================================================
// Input/Output Types
// =============================================================================

/** Input for finding selection from UI/run/incident-report data */
export interface DemoFindingSelectionInput {
  /** Live incident report from current health run */
  incidentReport?: {
    status?: "critical" | "degraded" | "warning" | "healthy";
    severity?: SeverityLevel;
    resource?: string;
    findingType?: string;
  };
  /** Live operator worklist items from current run */
  operatorWorklist?: Array<{
    severity?: SeverityLevel;
    resource?: string;
    status?: string;
    message?: string;
  }>;
  /** Freshness indicator for current run */
  freshness?: {
    age?: number;
    isStale?: boolean;
  };
  /** Run identifier */
  runId?: string;
  /** Cluster label */
  clusterLabel?: string;
}

/** Result of finding selection */
export interface DemoFindingSelectionResult {
  /** Selected findings */
  findings: DemoFinding[];
  /** Evidence source classification */
  source: EvidenceSource;
  /** Whether cluster is healthy */
  cleanCluster: boolean;
  /** Human-readable explanation */
  explanation: string;
}

// =============================================================================
// Severity Signal Patterns
// =============================================================================

/** Critical severity signals */
const CRITICAL_SIGNALS = [
  "CrashLoopBackOff",
  "ImagePullBackOff",
  "ErrImagePull",
  "FailedScheduling",
  "OOMKilled",
  "NotReady",
  "Unknown",
  "Failed",
];

/** Warning severity signals */
const WARNING_SIGNALS = [
  "Pending",
  "Evicted",
  "Terminating",
  "Terminated",
  "Warning",
  "WarningEvent",
  "WarningAlert",
  "stale",
  "noisy",
  "partial",
];

/** Evidence freshness thresholds (in seconds) */
const FRESH_THRESHOLD_SECONDS = 300; // 5 minutes

// =============================================================================
// Helper Functions
// =============================================================================

/** Classify severity from finding type/message */
function classifySeverity(
  incidentReport?: DemoFindingSelectionInput["incidentReport"],
  worklistItem?: DemoFindingSelectionInput["operatorWorklist"][number]
): SeverityLevel {
  // Check incident report first
  if (incidentReport?.status) {
    if (incidentReport.status === "critical" || incidentReport.status === "degraded") {
      return "critical";
    }
    if (incidentReport.status === "warning") {
      return "warning";
    }
  }

  if (incidentReport?.severity) {
    return incidentReport.severity;
  }

  if (incidentReport?.findingType) {
    const findingType = incidentReport.findingType;
    if (CRITICAL_SIGNALS.some((s) => findingType.includes(s))) {
      return "critical";
    }
    if (WARNING_SIGNALS.some((s) => findingType.includes(s))) {
      return "warning";
    }
  }

  // Check worklist item
  if (worklistItem?.severity) {
    return worklistItem.severity;
  }

  if (worklistItem?.status) {
    const status = worklistItem.status;
    if (CRITICAL_SIGNALS.some((s) => status.includes(s))) {
      return "critical";
    }
    if (WARNING_SIGNALS.some((s) => status.includes(s))) {
      return "warning";
    }
  }

  // Check worklist message
  if (worklistItem?.message) {
    const message = worklistItem.message;
    if (CRITICAL_SIGNALS.some((s) => message.includes(s))) {
      return "critical";
    }
    if (WARNING_SIGNALS.some((s) => message.includes(s))) {
      return "warning";
    }
  }

  return "info";
}

/** Determine evidence source from freshness */
function determineEvidenceSource(
  freshness?: DemoFindingSelectionInput["freshness"]
): EvidenceSource {
  if (!freshness) {
    return "live"; // Default to live if no freshness info
  }

  if (freshness.isStale) {
    return "stale";
  }

  if (freshness.age !== undefined && freshness.age > FRESH_THRESHOLD_SECONDS) {
    return "stale";
  }

  return "live";
}

/** Build recommended action from severity and resource */
function buildRecommendedAction(
  severity: SeverityLevel,
  resource: string
): string {
  switch (severity) {
    case "critical":
      return "Review diagnostic evidence and run the recommended read-only next check.";
    case "warning":
      return "Review evidence and consider running a diagnostic scan to gather more context.";
    default:
      return "No action required; continue monitoring.";
  }
}

/** Build probable cause from severity */
function buildProbableCause(
  severity: SeverityLevel,
  incidentReport?: DemoFindingSelectionInput["incidentReport"]
): string {
  if (incidentReport?.findingType) {
    return `Detected ${incidentReport.findingType} condition on ${incidentReport.resource || "target resource"}.`;
  }

  switch (severity) {
    case "critical":
      return "Active critical condition detected. Immediate review recommended.";
    case "warning":
      return "Non-critical condition detected. Monitor for resolution.";
    default:
      return "No significant issues detected.";
  }
}

// =============================================================================
// Main Selection Function
// =============================================================================

/**
 * Select demo findings from input data following priority:
 * 1. Live critical findings from current health run
 * 2. Live warning findings from current health run
 * 3. Historical real findings from previous runs
 * 4. Clean-cluster fallback with honest messaging
 *
 * @param input - Selection input from UI/run/incident-report data
 * @returns Selected findings with source classification
 */
export function selectDemoFindings(
  input: DemoFindingSelectionInput
): DemoFindingSelectionResult {
  const { incidentReport, operatorWorklist, freshness } = input;

  // Determine evidence source from freshness
  const evidenceSource = determineEvidenceSource(freshness);

  // If stale, still show findings but with stale badge
  const isStale = evidenceSource === "stale";

  // Collect all available findings
  const allFindings: DemoFinding[] = [];

  // Process incident report
  if (incidentReport) {
    const severity = classifySeverity(incidentReport);
    const resource = incidentReport.resource || "cluster";

    if (severity === "critical" || severity === "warning") {
      allFindings.push({
        id: `incident-report-${Date.now()}`,
        title: formatFindingTitle(severity, incidentReport.findingType),
        severity,
        affectedResource: resource,
        evidenceSource: isStale ? "stale" : "live",
        probableCause: buildProbableCause(severity, incidentReport),
        diagnosticEvidence: incidentReport.findingType
          ? `Finding type: ${incidentReport.findingType}`
          : "Diagnostic scan evidence available",
        recommendedAction: buildRecommendedAction(severity, resource),
        safetyMode: "preview-only",
      });
    }
  }

  // Process operator worklist items
  if (operatorWorklist && operatorWorklist.length > 0) {
    for (const item of operatorWorklist) {
      const severity = classifySeverity(undefined, item);

      if (severity === "critical" || severity === "warning") {
        const resource = item.resource || "cluster";

        // Avoid duplicates
        const exists = allFindings.some(
          (f) =>
            f.affectedResource === resource &&
            f.severity === severity &&
            f.title.includes(severity)
        );

        if (!exists) {
          allFindings.push({
            id: `worklist-item-${Date.now()}-${Math.random()}`,
            title: formatWorklistTitle(severity, item.message),
            severity,
            affectedResource: resource,
            evidenceSource: isStale ? "stale" : "live",
            probableCause: item.message || "Worklist item requires attention.",
            diagnosticEvidence: "Operator worklist item from diagnostic scan.",
            recommendedAction: buildRecommendedAction(severity, resource),
            safetyMode: "operator-approved",
          });
        }
      }
    }
  }

  // Sort by severity priority
  allFindings.sort((a, b) => {
    const priority = { critical: 0, warning: 1, info: 2 };
    return priority[a.severity] - priority[b.severity];
  });

  // Determine final source label
  let finalSource: EvidenceSource = evidenceSource;
  let cleanCluster = false;
  let explanation: string;

  if (allFindings.length === 0) {
    cleanCluster = true;
    finalSource = "none";
    explanation = "No critical or warning findings from current health run.";

    return {
      findings: [],
      source: finalSource,
      cleanCluster,
      explanation,
    };
  }

  // Build explanation based on source
  switch (finalSource) {
    case "live":
      explanation = `${allFindings.filter((f) => f.severity === "critical").length} critical, ${allFindings.filter((f) => f.severity === "warning").length} warning findings from live scan.`;
      break;
    case "stale":
      explanation = `${allFindings.filter((f) => f.severity === "critical").length} critical, ${allFindings.filter((f) => f.severity === "warning").length} warning findings from stale scan. Run a fresh scan for current state.`;
      break;
    case "historical":
      explanation = `${allFindings.length} finding(s) from historical real run.`;
      break;
    default:
      explanation = `${allFindings.length} finding(s) available.`;
  }

  return {
    findings: allFindings,
    source: finalSource,
    cleanCluster,
    explanation,
  };
}

// =============================================================================
// Formatting Helpers
// =============================================================================

/** Format finding title from finding type */
function formatFindingTitle(severity: SeverityLevel, findingType?: string): string {
  if (findingType) {
    const capitalized = findingType.charAt(0).toUpperCase() + findingType.slice(1);
    return `${severity === "critical" ? "Critical" : "Warning"}: ${capitalized}`;
  }
  return `${severity === "critical" ? "Critical" : "Warning"} finding detected`;
}

/** Format worklist item title from message */
function formatWorklistTitle(severity: SeverityLevel, message?: string): string {
  if (message) {
    // Truncate long messages
    const truncated = message.length > 50 ? message.slice(0, 47) + "..." : message;
    return `${severity === "critical" ? "Critical" : "Warning"}: ${truncated}`;
  }
  return `${severity === "critical" ? "Critical" : "Warning"} worklist item`;
}

// =============================================================================
// Historical Evidence Fallback
// =============================================================================

/**
 * Select from historical real evidence when no live findings available.
 * Uses real previous run artifacts or diagnostic evidence.
 *
 * @param historicalFindings - Findings from previous real runs
 * @returns Historical finding selection result
 */
export function selectHistoricalFindings(
  historicalFindings: DemoFinding[]
): DemoFindingSelectionResult {
  if (!historicalFindings || historicalFindings.length === 0) {
    return {
      findings: [],
      source: "none",
      cleanCluster: true,
      explanation: "No historical real evidence available.",
    };
  }

  // Filter to critical and warning only
  const significantFindings = historicalFindings.filter(
    (f) => f.severity === "critical" || f.severity === "warning"
  );

  // Sort by severity
  significantFindings.sort((a, b) => {
    const priority = { critical: 0, warning: 1, info: 2 };
    return priority[a.severity] - priority[b.severity];
  });

  return {
    findings: significantFindings.map((f) => ({
      ...f,
      evidenceSource: "historical" as EvidenceSource,
    })),
    source: "historical",
    cleanCluster: false,
    explanation: `${significantFindings.length} finding(s) from historical real run.`,
  };
}

// =============================================================================
// Clean Cluster Fallback
// =============================================================================

/**
 * Generate clean cluster fallback when no findings exist.
 * Returns honest messaging about healthy cluster state.
 *
 * @param options - Fallback options
 * @returns Clean cluster fallback result
 */
export function getCleanClusterFallback(
  options: {
    clusterLabel?: string;
    hasHistoricalEvidence?: boolean;
  } = {}
): DemoFindingSelectionResult {
  return {
    findings: [],
    source: "none",
    cleanCluster: true,
    explanation: options.hasHistoricalEvidence
      ? "No critical issues in current scan. Historical evidence available."
      : "No critical issues found. Cluster appears healthy.",
  };
}

// =============================================================================
// Utility: Check for Forbidden Content
// =============================================================================

/** Forbidden phrases that must never appear */
const FORBIDDEN_PHRASES = [
  "self-healing",
  "guaranteed root cause",
  "automatic production fix",
  "fixes any Kubernetes issue",
  "fully autonomous",
];

/**
 * Check if content contains forbidden phrases.
 * Used to validate that no fake/demo language appears as real evidence.
 */
export function containsForbiddenPhrase(text: string): boolean {
  const lowerText = text.toLowerCase();
  return FORBIDDEN_PHRASES.some((phrase) => lowerText.includes(phrase.toLowerCase()));
}

/**
 * Validate findings don't contain forbidden content.
 * Returns true if findings are safe to display.
 */
export function validateFindings(findings: DemoFinding[]): boolean {
  for (const finding of findings) {
    if (containsForbiddenPhrase(finding.title)) return false;
    if (containsForbiddenPhrase(finding.recommendedAction)) return false;
    if (containsForbiddenPhrase(finding.probableCause)) return false;
  }
  return true;
}