/**
 * Pure side-effect-free helpers and selectors extracted from App.tsx.
 * These are pure functions, static constants, type guards, and formatters
 * with no React hooks, localStorage, or JSX dependencies.
 */
import dayjs from "dayjs";
import type {
  AlertmanagerProvenance,
  ArtifactLink,
  FeedbackAdaptationProvenance,
  FeedbackSummary,
  ClusterDetailPayload,
  DeterministicNextCheckSummary,
  LLMStats,
  NextCheckPlanCandidate,
  RunsListEntry,
} from "../types";

// ==========================================================================
// Confidence / Priority helpers
// ==========================================================================

export const confidenceWeight = (value: string): number => {
  const tier = value.toLowerCase();
  const order = ["critical", "high", "medium", "low"];
  const idx = order.indexOf(tier);
  return idx === -1 ? order.length : idx;
};

export const priorityLabel = (confidence: string): string => {
  const normalized = confidence.toLowerCase();
  if (normalized.includes("critical")) return "critical";
  if (normalized.includes("high")) return "high";
  if (normalized.includes("medium")) return "medium";
  if (normalized.includes("low")) return "low";
  return "default";
};

// ==========================================================================
// Freshness helpers
// ==========================================================================

type FreshnessLevel = "fresh" | "warning" | "stale";

// Page/data freshness thresholds: <=30s fresh, >30s and <3m warning, >=3m stale
export const getPageFreshnessLevel = (
  lastRefreshTime: dayjs.Dayjs,
  now?: dayjs.Dayjs
): FreshnessLevel => {
  const currentTime = now ?? dayjs();
  const seconds = currentTime.diff(lastRefreshTime, "second");
  if (seconds <= 30) return "fresh";
  if (seconds < 180) return "warning";
  return "stale";
};

// Run freshness thresholds: <=15m fresh, >15m and <=45m warning (Aging), >45m stale
export const getRunFreshnessLevel = (
  timestamp: string,
  now?: dayjs.Dayjs
): FreshnessLevel => {
  const currentTime = now ?? dayjs();
  const minutes = currentTime.diff(dayjs(timestamp), "minute");
  if (minutes <= 15) return "fresh";
  if (minutes <= 45) return "warning";
  return "stale";
};

export const FRESHNESS_EMOJI: Record<FreshnessLevel, string> = {
  fresh: "🟢",
  warning: "🟡",
  stale: "🔴",
};

export const FRESHNESS_LABEL: Record<FreshnessLevel, string> = {
  fresh: "Fresh",
  warning: "Aging",
  stale: "Stale",
};

export const FRESHNESS_THRESHOLD_MINUTES = 10;

export const isStaleTimestamp = (timestamp: string, now?: dayjs.Dayjs): boolean => {
  const currentTime = now ?? dayjs();
  return currentTime.diff(dayjs(timestamp), "minute") >= FRESHNESS_THRESHOLD_MINUTES;
};

// ==========================================================================
// Duration formatting
// ==========================================================================

/**
 * Format duration for age display in past-run notice.
 * Rules:
 * - under 1 hour: X minutes
 * - under 1 day: X hours Y minutes
 * - 1 day+: X days Y hours Z minutes
 * - no seconds
 */
export const formatAgeDuration = (minutes: number): string => {
  if (minutes < 0) {
    return "—";
  }
  if (minutes < 60) {
    return `${Math.round(minutes)} minute${Math.round(minutes) === 1 ? "" : "s"}`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = Math.round(minutes % 60);
  if (hours < 24) {
    const hourStr = `${hours} hour${hours === 1 ? "" : "s"}`;
    if (remainingMinutes === 0) {
      return hourStr;
    }
    return `${hourStr} ${remainingMinutes} minute${remainingMinutes === 1 ? "" : "s"}`;
  }
  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  const dayStr = `${days} day${days === 1 ? "" : "s"}`;
  if (remainingHours === 0) {
    if (remainingMinutes === 0) {
      return dayStr;
    }
    return `${dayStr} ${remainingMinutes} minute${remainingMinutes === 1 ? "" : "s"}`;
  }
  const hourStr = `${remainingHours} hour${remainingHours === 1 ? "" : "s"}`;
  if (remainingMinutes === 0) {
    return `${dayStr} ${hourStr}`;
  }
  return `${dayStr} ${hourStr} ${remainingMinutes} minute${remainingMinutes === 1 ? "" : "s"}`;
};

// ==========================================================================
// Static workflow / UI config
// ==========================================================================

// Workflow lanes for operator guidance
export const WORKFLOW_LANES = {
  diagnose: {
    label: "Diagnose now",
    description: "Understand the current problem and review candidate evidence to gather",
  },
  work: {
    label: "Work next checks",
    description: "Run or review the shortlist of actionable checks",
  },
  improve: {
    label: "Improve the system",
    description: "Review durable policy and config changes suggested by what we learned",
  },
};

// Autorefresh options and storage key used by header UI
export const AUTOREFRESH_STORAGE_KEY = "dashboard-autorefresh-interval";
export const AUTOREFRESH_OPTIONS = [
  { label: "Off", value: "off" },
  { label: "5s", value: "5" },
  { label: "10s", value: "10" },
  { label: "30s", value: "30" },
  { label: "1m", value: "60" },
  { label: "5m", value: "300" },
];

// ==========================================================================
// LLM stats helpers
// ==========================================================================

export const getLlmScopeLabel = (scope?: string | null): string =>
  scope === "retained_history" ? "Historical LLM" : "Run LLM";

export const buildLlmStatEntries = (stats: LLMStats) => {
  // Note: We import formatLatency from ./formatters.ts in the caller
  // or use it directly here. For selectors.ts (no side effects), we
  // return the raw data structure that the caller formats.
  const scopeLabel = getLlmScopeLabel(stats.scope ?? null);
  return [
    { label: `${scopeLabel} calls`, value: String(stats.totalCalls) },
    { label: "OK", value: String(stats.successfulCalls) },
    { label: "Failed", value: String(stats.failedCalls) },
    { label: "P50", value: String(stats.p50LatencyMs) },
    { label: "P95", value: String(stats.p95LatencyMs) },
    { label: "P99", value: String(stats.p99LatencyMs) },
    { label: "Last call", value: stats.lastCallTimestamp ? stats.lastCallTimestamp : "—" },
  ];
};

// ==========================================================================
// Artifact helpers
// ==========================================================================

export const buildClusterRecommendedArtifacts = (detail?: ClusterDetailPayload): ArtifactLink[] => {
  if (!detail) {
    return [];
  }
  const seen = new Map<string, ArtifactLink>();
  const add = (artifact: ArtifactLink | null | undefined) => {
    if (!artifact || !artifact.path) {
      return;
    }
    if (seen.has(artifact.path)) {
      return;
    }
    seen.set(artifact.path, artifact);
  };
  if (detail.assessment?.artifactPath) {
    add({ label: "Assessment artifact", path: detail.assessment.artifactPath });
  }
  detail.artifacts.forEach((artifact) => add(artifact));
  detail.drilldownCoverage.forEach((entry) => {
    if (entry.available && entry.artifactPath) {
      add({ label: `${entry.label} drilldown`, path: entry.artifactPath });
    }
  });
  return Array.from(seen.values()).slice(0, 3);
};

// ==========================================================================
// Sorting helpers
// ==========================================================================

export const sortDeterministicSummaries = (
  summaries: DeterministicNextCheckSummary[] = []
): DeterministicNextCheckSummary[] =>
  [...summaries].sort((first, second) => (second.priorityScore ?? 0) - (first.priorityScore ?? 0));

// ==========================================================================
// CSS class helpers
// ==========================================================================

export const safetyClass = (value?: string): string => {
  const normalized = value ? value.replace(/[^a-z0-9]+/gi, "-").toLowerCase() : "";
  return `safety-pill ${normalized ? `safety-pill-${normalized}` : ""}`.trim();
};

// ==========================================================================
// Formatting helpers
// ==========================================================================

export const formatSourceType = (value?: string | null): string | null => {
  if (!value) return null;
  if (value === "deterministic") {
    return "Deterministic evidence";
  }
  return `${value.charAt(0).toUpperCase()}${value.slice(1)}`;
};

export const humanizeReason = (value?: string | null): string | null => {
  if (!value) {
    return null;
  }
  return value
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
};

export const formatCandidatePriority = (value?: string | null): string => {
  const normalized = (value ?? "secondary").toLowerCase();
  return `${normalized.charAt(0).toUpperCase()}${normalized.slice(1)}`;
};

// ==========================================================================
// Next-check status helpers
// ==========================================================================

export const ALLOWED_MANUAL_FAMILIES = new Set([
  "kubectl-get",
  "kubectl-describe",
  "kubectl-logs",
  "kubectl-get-crd",
  "kubectl-top",
]);

export const approvalStatusLabels: Record<string, string> = {
  approved: "Approved candidate",
  "approval-required": "Approval needed",
  "approval-stale": "Approval stale",
  "approval-orphaned": "Orphaned approval",
  "not-required": "Safe candidate",
};

export type NextCheckStatusVariant = "safe" | "approval" | "approved" | "duplicate" | "stale";

export const determineNextCheckStatusVariant = (
  candidate: NextCheckPlanCandidate
): NextCheckStatusVariant => {
  if (candidate.duplicateOfExistingEvidence) {
    return "duplicate";
  }
  if (candidate.requiresOperatorApproval) {
    if (candidate.approvalStatus === "approved") {
      return "approved";
    }
    if (candidate.approvalStatus === "approval-stale") {
      return "stale";
    }
    return "approval";
  }
  return "safe";
};

export const nextCheckStatusLabel = (variant: NextCheckStatusVariant): string => {
  switch (variant) {
    case "approval":
      return "Approval needed";
    case "approved":
      return "Approved candidate";
    case "duplicate":
      return "Duplicate / already covered";
    case "stale":
      return "Approval stale";
    default:
      return "Safe candidate";
  }
};

/** Ordered variants for discovery variant display. */
export const DISCOVERY_VARIANT_ORDER: NextCheckStatusVariant[] = [
  "safe",
  "approval",
  "approved",
  "duplicate",
  "stale",
];

/** Count next-check candidates by their status variant.
 * Used for the RunSummaryPanel discovery summary.
 */
export const buildDiscoveryVariantCounts = (
  candidates: NextCheckPlanCandidate[]
): Record<NextCheckStatusVariant, number> => {
  const counts: Record<NextCheckStatusVariant, number> = {
    safe: 0,
    approval: 0,
    approved: 0,
    duplicate: 0,
    stale: 0,
  };
  candidates.forEach((candidate) => {
    const variant = determineNextCheckStatusVariant(candidate);
    counts[variant] = (counts[variant] ?? 0) + 1;
  });
  return counts;
};

export const getPlanStatusLabel = (
  variant: NextCheckStatusVariant,
  candidate: NextCheckPlanCandidate
): string => {
  if (candidate.approvalStatus) {
    const override = approvalStatusLabels[candidate.approvalStatus];
    if (override) {
      return override;
    }
  }
  return nextCheckStatusLabel(variant);
};

// ==========================================================================
// Queue status helpers
// ==========================================================================

export type NextCheckQueueStatus =
  | "approved-ready"
  | "safe-ready"
  | "approval-needed"
  | "failed"
  | "completed"
  | "duplicate-or-stale";

export const NEXT_CHECK_QUEUE_STATUS_LABELS: Record<NextCheckQueueStatus, string> = {
  "approved-ready": "Approved & ready",
  "safe-ready": "Safe to automate",
  "approval-needed": "Approval needed",
  "failed": "Failed executions",
  "completed": "Completed",
  "duplicate-or-stale": "Duplicate / stale",
};

export const NEXT_CHECK_QUEUE_STATUS_ORDER: NextCheckQueueStatus[] = [
  "approved-ready",
  "safe-ready",
  "approval-needed",
  "failed",
  "completed",
  "duplicate-or-stale",
];

export const QUEUE_SORT_OPTIONS = [
  { label: "Backend order", value: "default" },
  { label: "Priority", value: "priority" },
  { label: "Cluster", value: "cluster" },
  { label: "Latest activity", value: "activity" },
] as const;

export type QueueSortOption = (typeof QUEUE_SORT_OPTIONS)[number]["value"];

export const QUEUE_PRIORITY_ORDER: Record<string, number> = {
  primary: 0,
  secondary: 1,
  fallback: 2,
};

export type QueueFocusMode = "none" | "work" | "review";
export const QUEUE_FOCUS_FILTERS: Record<QueueFocusMode, NextCheckQueueStatus[]> = {
  none: [],
  work: ["approved-ready", "safe-ready", "failed"],
  review: ["approval-needed", "duplicate-or-stale"],
};

// ==========================================================================
// Runs review filter helpers
// ==========================================================================

// Review status filter types for recent runs panel
export type RunsReviewFilter =
  | "all"
  | "no-executions"
  | "awaiting-review"
  | "partially-reviewed"
  | "fully-reviewed"
  | "needs-attention";

export const RUNS_REVIEW_FILTER_OPTIONS: { label: string; value: RunsReviewFilter }[] = [
  { label: "All runs", value: "all" },
  { label: "No executions yet", value: "no-executions" },
  { label: "Awaiting review", value: "awaiting-review" },
  { label: "Partially reviewed", value: "partially-reviewed" },
  { label: "Fully reviewed", value: "fully-reviewed" },
  { label: "Needs attention", value: "needs-attention" },
];

// Compute filter counts from runs list
export const computeRunsFilterCounts = (
  runs: RunsListEntry[]
): Record<RunsReviewFilter, number> => {
  const counts: Record<RunsReviewFilter, number> = {
    all: runs.length,
    "no-executions": 0,
    "awaiting-review": 0,
    "partially-reviewed": 0,
    "fully-reviewed": 0,
    "needs-attention": 0,
  };

  runs.forEach((run) => {
    if (run.reviewStatus === "no-executions") {
      counts["no-executions"]++;
    } else if (run.reviewStatus === "unreviewed") {
      counts["awaiting-review"]++;
      counts["needs-attention"]++;
    } else if (run.reviewStatus === "partially-reviewed") {
      counts["partially-reviewed"]++;
      counts["needs-attention"]++;
    } else if (run.reviewStatus === "fully-reviewed") {
      counts["fully-reviewed"]++;
    }
  });

  return counts;
};

export const RUNS_REVIEW_FILTER_VALUES: RunsReviewFilter[] = [
  "all",
  "no-executions",
  "awaiting-review",
  "partially-reviewed",
  "fully-reviewed",
  "needs-attention",
];

export const isRunsReviewFilterValue = (value: unknown): value is RunsReviewFilter =>
  typeof value === "string" && RUNS_REVIEW_FILTER_VALUES.includes(value as RunsReviewFilter);

// ==========================================================================
// Queue priority helpers
// ==========================================================================

export const normalizeQueuePriority = (value: string | null | undefined): string =>
  (value ?? "unknown").toLowerCase();

export const queuePriorityRank = (value: string | null | undefined): number =>
  QUEUE_PRIORITY_ORDER[normalizeQueuePriority(value)] ?? Object.keys(QUEUE_PRIORITY_ORDER).length;

export const queueTimestampValue = (value: string | null | undefined): number => {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
};

// ==========================================================================
// Outcome status helpers
// ==========================================================================

export const outcomeStatusLabels: Record<string, string> = {
  "executed-success": "Executed (success)",
  "executed-failed": "Executed (failed)",
  "timed-out": "Execution timed out",
  "approval-required": "Awaiting approval",
  approved: "Approved",
  "approval-stale": "Approval stale",
  "approval-orphaned": "Orphaned approval",
  "not-used": "Not used",
  unknown: "Unknown",
};

export const outcomeStatusDisplay = (status?: string | null): string =>
  outcomeStatusLabels[status ?? "unknown"] || (status ? status : "Unknown");

export const outcomeStatusClass = (status?: string | null): string =>
  `outcome-pill outcome-pill-${((status ?? "unknown").replace(/[^a-z0-9]+/gi, "-").toLowerCase())}`;

// ==========================================================================
// Next-check entry parsing
// ==========================================================================

export type ParsedNextCheck = {
  intent: string;
  targetCluster: string | null;
  commandPreview: string | null;
};

/**
 * Parse a raw next-check string into structured fields.
 * Handles:
 *   - Optional [cluster-name] prefix → targetCluster
 *   - Optional kubectl / k9s command in the text → commandPreview
 *   - Remaining text → intent
 * Keeps string surgery out of JSX.
 */
export const parseNextCheckEntry = (raw: string): ParsedNextCheck => {
  const clusterPrefixMatch = raw.match(/^\[([^\]]{1,60})\]\s*/);
  const withoutPrefix = clusterPrefixMatch ? raw.slice(clusterPrefixMatch[0].length) : raw;
  const targetCluster = clusterPrefixMatch ? clusterPrefixMatch[1] : null;

  const cmdMatch = withoutPrefix.match(/\b(kubectl\s+\S+(?:\s+[^\n]+)?|k9s\b[^\n]*)/);

  if (!cmdMatch) {
    return {
      intent: withoutPrefix.slice(0, 120).trim(),
      targetCluster,
      commandPreview: null,
    };
  }

  const commandRaw = cmdMatch[1].trim();
  const cmdStart = withoutPrefix.indexOf(cmdMatch[0]);
  const beforeCmd = withoutPrefix.slice(0, cmdStart).trim().replace(/[:\-–]+$/, "").trim();

  if (!beforeCmd) {
    // Whole entry is a command - show as intent, no separate preview
    return {
      intent: commandRaw.slice(0, 80).trim(),
      targetCluster,
      commandPreview: null,
    };
  }

  return {
    intent: beforeCmd,
    targetCluster,
    commandPreview: commandRaw.slice(0, 90),
  };
};

// ==========================================================================
// Alertmanager provenance formatters
// ==========================================================================

// Operator-friendly labels for Alertmanager ranking promotion display.
const ALERTMANAGER_PROMOTION_LABELS: Record<string, string> = {
  namespace: "Matched namespace",
  namespaces: "Matched namespaces",
  cluster: "Matched cluster",
  clusters: "Matched clusters",
  service: "Matched service",
  services: "Matched services",
};

/** Format Alertmanager promotion text for operator display.
 * Converts internal format like "promoted:matched namespace(s): monitoring"
 * into human-friendly text like "Promoted: Matched namespace monitoring".
 */
export const formatAlertmanagerPromotion = (rankingReason: string): string => {
  // Remove internal prefix
  const internal = rankingReason.replace(/^alertmanager-context:/, "");

  // Split into parts: "promoted" + "matched {dimensions}: {values}"
  const parts = internal.split(":");
  if (parts.length < 2) {
    return "Promoted by Alertmanager";
  }

  // Parse "promoted" and "matched {dims}: {values}"
  const rest = parts.slice(1).join(":"); // "matched namespace(s): monitoring"

  // Extract dimension and values
  const matchPartMatch = rest.match(/^matched\s+(.+?):\s*(.+)$/);
  if (!matchPartMatch) {
    return "Promoted by Alertmanager";
  }

  const dimensionRaw = matchPartMatch[1];
  const values = matchPartMatch[2];

  // Normalize dimension name (namespace(s) -> namespace/namespaces)
  let normalizedDim = dimensionRaw;
  if (dimensionRaw.includes("namespace")) {
    normalizedDim = dimensionRaw.includes("(") && dimensionRaw.includes(")")
      ? "namespaces"
      : "namespace";
  } else if (dimensionRaw.includes("cluster")) {
    normalizedDim = dimensionRaw.includes("(") && dimensionRaw.includes(")")
      ? "clusters"
      : "cluster";
  } else if (dimensionRaw.includes("service")) {
    normalizedDim = dimensionRaw.includes("(") && dimensionRaw.includes(")")
      ? "services"
      : "service";
  }

  const label = ALERTMANAGER_PROMOTION_LABELS[normalizedDim] || normalizedDim;

  return `${label}: ${values}`;
};

/** Get subtext for Alertmanager promotion tooltip.
 * Provides detail when multiple dimensions are matched.
 */
export const getAlertmanagerPromotionSubtext = (rankingReason: string): string | null => {
  const internal = rankingReason.replace(/^alertmanager-context:/, "");
  const parts = internal.split(":");
  if (parts.length >= 2) {
    return "Ranking influenced by Alertmanager snapshot for selected run";
  }
  return null;
};

/** Format structured Alertmanager provenance for operator display.
 * Converts AlertmanagerProvenance into human-friendly text.
 */
export const formatAlertmanagerProvenance = (provenance: AlertmanagerProvenance): string => {
  const { matchedDimensions, matchedValues, appliedBonus } = provenance;

  if (matchedDimensions.length === 0) {
    return "Promoted by Alertmanager";
  }

  // Format matched dimensions and values
  const parts = matchedDimensions.map((dim) => {
    const values = matchedValues[dim] ?? [];
    const valuesStr = values.length > 0 ? `: ${values.join(", ")}` : "";
    return `${dim}${valuesStr}`;
  });

  const bonusStr = appliedBonus > 0 ? ` (+${appliedBonus})` : "";
  return `Matched ${parts.join(", ")}${bonusStr}`;
};

/** Get subtext for structured Alertmanager provenance tooltip.
 * Provides bonus and severity detail when available.
 */
export const getAlertmanagerProvenanceSubtext = (provenance: AlertmanagerProvenance): string => {
  const { baseBonus, appliedBonus, severitySummary, signalStatus } = provenance;

  const parts: string[] = [];

  if (baseBonus !== appliedBonus) {
    parts.push(`Base bonus: ${baseBonus}, Applied: ${appliedBonus}`);
  } else if (appliedBonus > 0) {
    parts.push(`Bonus: ${appliedBonus}`);
  }

  if (Object.keys(severitySummary).length > 0) {
    const severityParts = Object.entries(severitySummary)
      .map(([sev, count]) => `${sev}: ${count}`)
      .join(", ");
    parts.push(`Severity: ${severityParts}`);
  }

  if (signalStatus) {
    parts.push(`Signal: ${signalStatus}`);
  }

  if (parts.length === 0) {
    return "Ranking influenced by Alertmanager snapshot";
  }

  return parts.join(" · ");
};

// ==========================================================================
// Feedback adaptation provenance formatters
// ==========================================================================

/** Format feedback adaptation provenance for display. */
export const formatFeedbackAdaptationProvenance = (
  provenance: FeedbackAdaptationProvenance
): string => {
  const { feedbackAdaptation, adaptationReason, suppressedBonus, penaltyApplied } = provenance;

  if (!feedbackAdaptation) {
    return "No feedback adaptation";
  }

  const parts: string[] = [];

  if (adaptationReason) {
    parts.push(adaptationReason);
  }

  if (suppressedBonus > 0) {
    parts.push(`Suppressed: ${suppressedBonus}`);
  }

  if (penaltyApplied !== 0) {
    parts.push(`Penalty: ${penaltyApplied}`);
  }

  return parts.length > 0 ? parts.join(" · ") : "Feedback adaptation applied";
};

/** Format structured feedback summary for tooltip display.
 * Handles both modern structured FeedbackSummary and legacy string fallback.
 */
export const formatFeedbackSummary = (summary: FeedbackSummary): string => {
  // Legacy fallback: preserve original text if summaryText is present
  if (summary.summaryText) {
    return summary.summaryText;
  }

  const parts: string[] = [];
  if (summary.totalEntries > 0) {
    parts.push(`${summary.totalEntries} entries`);
  }
  const nsCount = summary.namespacesWithFeedback.length;
  const clusterCount = summary.clustersWithFeedback.length;
  const svcCount = summary.servicesWithFeedback.length;
  if (nsCount > 0) parts.push(`${nsCount} ns`);
  if (clusterCount > 0) parts.push(`${clusterCount} cluster(s)`);
  if (svcCount > 0) parts.push(`${svcCount} service(s)`);
  return parts.length > 0 ? parts.join(", ") : "No feedback";
};

/** Get subtext for feedback adaptation provenance tooltip. */
export const getFeedbackAdaptationProvenanceSubtext = (
  provenance: FeedbackAdaptationProvenance
): string => {
  const { originalBonus, suppressedBonus, penaltyApplied, explanation, feedbackSummary } = provenance;

  const parts: string[] = [];

  if (originalBonus > 0) {
    parts.push(`Original bonus: ${originalBonus}`);
  }

  if (suppressedBonus > 0) {
    parts.push(`Suppressed: ${suppressedBonus}`);
  }

  if (penaltyApplied !== 0) {
    parts.push(`Penalty applied: ${penaltyApplied}`);
  }

  if (explanation) {
    parts.push(`Explanation: ${explanation}`);
  }

  if (feedbackSummary) {
    const summaryText =
      typeof feedbackSummary === "string"
        ? feedbackSummary
        : formatFeedbackSummary(feedbackSummary);
    parts.push(`Feedback: ${summaryText}`);
  }

  return parts.length > 0 ? parts.join(" · ") : "Feedback adaptation applied";
};