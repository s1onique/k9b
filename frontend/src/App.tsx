import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import utc from "dayjs/plugin/utc";
import {
  approveNextCheckCandidate,
  executeNextCheckCandidate,
  fetchNotifications,
  runBatchExecution,
  submitUsefulnessFeedback,
} from "./api";
import { useAppData } from "./hooks/useAppData";
import { useRunData } from "./hooks/useRunData";
import { useRunSelection } from "./hooks/useRunSelection";
import { useUIState } from "./hooks/useUIState";
import { useQueueState } from "./hooks/useQueueState";
import type {
  AlertmanagerProvenance,
  FeedbackAdaptationProvenance,
  AutoInterpretation,
  ClusterDetailPayload,
  FleetPayload,
  LLMPolicy,
  LLMStats,
  NextCheckExecutionHistoryEntry,
  NextCheckExecutionResponse,
  NextCheckPlanCandidate,
  NextCheckQueueItem,
  NotificationDetail,
  NotificationEntry,
  NotificationsPayload,
  ProposalEntry,
  ProposalsPayload,
  ProviderExecution,
  ProviderExecutionBranch,
  DeterministicNextCheckPromotionRequest,
} from "./types";
import "./index.css";
import { ThemeSwitch } from "./ThemeSwitch";
import Pagination from "./components/Pagination";
import { HeaderBranding } from "./components/HeaderBranding";
import { InterpretationBlock } from "./components/InterpretationBlock";
import { RunDiagnosticPackPanel } from "./components/RunDiagnosticPackPanel";
import { LLMActivityPanel } from "./components/LLMActivityPanel";
import { FailureFollowUpBlock } from "./components/FailureFollowUpBlock";
import { ResultInterpretationBlock } from "./components/ResultInterpretationBlock";
import { EvidenceDetails } from "./components/EvidenceDetails";
import {
  AdvisoryTopConcernsSection,
  AdvisoryEvidenceGapsSection,
  AdvisoryNextChecksSection,
  AdvisoryFocusNotesSection,
} from "./components/AdvisorySections";
import { ReviewEnrichmentPanel } from "./components/ReviewEnrichmentPanel";
import { DiagnosticPackReviewList } from "./components/DiagnosticPackReviewList";
import { DiagnosticPackReviewPanel } from "./components/DiagnosticPackReviewPanel";
import { ExecutionLine, ProviderExecutionPanel } from "./components/ProviderExecutionComponents";
import {
  ExecutionHistoryPanel,
  buildExecutionEntryKey,
  formatDuration,
} from "./components/ExecutionHistoryPanel";
import { NotificationHistoryTable } from "./components/NotificationHistoryTable";
import { DeterministicNextChecksPanel } from "./components/DeterministicNextChecksPanel";
import { QueuePanel } from "./components/QueuePanel";
import { AlertmanagerSnapshotPanel, AlertmanagerSourcesPanel } from "./components/AlertmanagerPanel";
import { ClusterDetailSection } from "./components/ClusterDetailSection";
export { AlertmanagerSnapshotPanel, AlertmanagerSourcesPanel };
import { RecentRunsPanel, RunSummaryPanel } from "./components/RunsPanel";
export type { RecentRunsPanelProps, RunSummaryPanelProps } from "./components/RunsPanel";
import {
  artifactUrl,
  formatTimestamp,
  formatLatency,
  normalizeFilterValue,
  relativeRecency,
  statusClass,
  truncateText,
} from "./utils";

dayjs.extend(relativeTime);
dayjs.extend(utc);

type SortKey = "proposalId" | "confidence" | "status";

const confidenceWeight = (value: string) => {
  const tier = value.toLowerCase();
  const order = ["critical", "high", "medium", "low"];
  const idx = order.indexOf(tier);
  return idx === -1 ? order.length : idx;
};

type FreshnessLevel = "fresh" | "warning" | "stale";

// Page/data freshness thresholds: <=30s fresh, >30s and <3m warning, >=3m stale
const getPageFreshnessLevel = (lastRefreshTime: dayjs.Dayjs): FreshnessLevel => {
  const seconds = dayjs().diff(lastRefreshTime, "second");
  if (seconds <= 30) return "fresh";
  if (seconds < 180) return "warning";
  return "stale";
};

// Run freshness thresholds: <=15m fresh, >15m and <=45m warning (Aging), >45m stale
const getRunFreshnessLevel = (timestamp: string): FreshnessLevel => {
  const minutes = dayjs().diff(dayjs(timestamp), "minute");
  if (minutes <= 15) return "fresh";
  if (minutes <= 45) return "warning";
  return "stale";
};

const FRESHNESS_EMOJI: Record<FreshnessLevel, string> = {
  fresh: "🟢",
  warning: "🟡",
  stale: "🔴",
};

// Run freshness labels: green=Fresh, yellow=Aging, red=Stale
const FRESHNESS_LABEL: Record<FreshnessLevel, string> = {
  fresh: "Fresh",
  warning: "Aging",
  stale: "Stale",
};

const FRESHNESS_THRESHOLD_MINUTES = 10;
const isStaleTimestamp = (timestamp: string) =>
  dayjs().diff(timestamp, "minute") >= FRESHNESS_THRESHOLD_MINUTES;

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


// Workflow lanes for operator guidance
const WORKFLOW_LANES = {
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

const NAVIGATION_HIGHLIGHT_DURATION_MS = 2200;

const getLlmScopeLabel = (scope?: string | null) =>
  scope === "retained_history" ? "Historical LLM" : "Run LLM";

const buildLlmStatEntries = (stats: LLMStats) => {
  const scopeLabel = getLlmScopeLabel(stats.scope ?? null);
  const lastCallValue = stats.lastCallTimestamp ? relativeRecency(stats.lastCallTimestamp) : "—";
  return [
    { label: `${scopeLabel} calls`, value: String(stats.totalCalls) },
    { label: "OK", value: String(stats.successfulCalls) },
    { label: "Failed", value: String(stats.failedCalls) },
    { label: "P50", value: formatLatency(stats.p50LatencyMs) },
    { label: "P95", value: formatLatency(stats.p95LatencyMs) },
    { label: "P99", value: formatLatency(stats.p99LatencyMs) },
    { label: "Last call", value: lastCallValue },
  ];
};

const renderLlmStatsLine = (stats: LLMStats, modifier?: string) => {
  const entries = buildLlmStatEntries(stats);
  const classNames = [
    "run-header-inline-stats",
    "llm-stats-line",
    "muted",
    "small",
    modifier,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <p className={classNames}>
      {entries.map((stat) => (
        <span key={`${stat.label}-${stat.value}`}>
          <span className="run-stat-label">{stat.label}: </span>
          <strong>{stat.value}</strong>
        </span>
      ))}
    </p>
  );
};

export const AUTOREFRESH_STORAGE_KEY = "dashboard-autorefresh-interval";
const DEFAULT_AUTOREFRESH_SECONDS = 5;
const AUTOREFRESH_OPTIONS = [
  { label: "Off", value: "off" },
  { label: "5s", value: "5" },
  { label: "10s", value: "10" },
  { label: "30s", value: "30" },
  { label: "1m", value: "60" },
  { label: "5m", value: "300" },
];

const readStoredAutoRefreshInterval = () => {
  if (typeof window === "undefined") {
    return DEFAULT_AUTOREFRESH_SECONDS;
  }
  const stored = window.localStorage.getItem(AUTOREFRESH_STORAGE_KEY);
  if (!stored) {
    return DEFAULT_AUTOREFRESH_SECONDS;
  }
  if (stored === "off") {
    return null;
  }
  const parsed = Number(stored);
  if (Number.isNaN(parsed) || parsed <= 0) {
    return DEFAULT_AUTOREFRESH_SECONDS;
  }
  return parsed;
};

const persistAutoRefreshInterval = (value: string) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(AUTOREFRESH_STORAGE_KEY, value);
};


const buildClusterRecommendedArtifacts = (detail?: ClusterDetailPayload) => {
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

const sortDeterministicSummaries = (
  summaries: DeterministicNextCheckSummary[] = []
) => [...summaries].sort((first, second) => (second.priorityScore ?? 0) - (first.priorityScore ?? 0));

const safetyClass = (value?: string) => {
  const normalized = value ? value.replace(/[^a-z0-9]+/gi, "-").toLowerCase() : "";
  return `safety-pill ${normalized ? `safety-pill-${normalized}` : ""}`.trim();
};

const priorityLabel = (confidence: string) => {
  const normalized = confidence.toLowerCase();
  if (normalized.includes("critical")) return "critical";
  if (normalized.includes("high")) return "high";
  if (normalized.includes("medium")) return "medium";
  if (normalized.includes("low")) return "low";
  return "default";
};

const formatSourceType = (value?: string | null) => {
  if (!value) return null;
  if (value === "deterministic") {
    return "Deterministic evidence";
  }
  return `${value.charAt(0).toUpperCase()}${value.slice(1)}`;
};

const humanizeReason = (value?: string | null) => {
  if (!value) {
    return null;
  }
  return value
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
};

const formatCandidatePriority = (value?: string | null) => {
  const normalized = (value ?? "secondary").toLowerCase();
  return `${normalized.charAt(0).toUpperCase()}${normalized.slice(1)}`;
};

const ALLOWED_MANUAL_FAMILIES = new Set([
  "kubectl-get",
  "kubectl-describe",
  "kubectl-logs",
  "kubectl-get-crd",
  "kubectl-top",
]);

type ExecutionErrorResult = {
  status: "error";
  summary: string;
  blockingReason?: string | null;
};

type ExecutionResult = NextCheckExecutionResponse | ExecutionErrorResult;

type ApprovalResult = {
  status: "success" | "error";
  summary: string;
  artifactPath?: string | null;
  approvalTimestamp?: string | null;
};

type PromotionStatus = {
  status: "idle" | "pending" | "success" | "error";
  message?: string | null;
};

const approvalStatusLabels: Record<string, string> = {
  approved: "Approved candidate",
  "approval-required": "Approval needed",
  "approval-stale": "Approval stale",
  "approval-orphaned": "Orphaned approval",
  "not-required": "Safe candidate",
};

type NextCheckStatusVariant = "safe" | "approval" | "approved" | "duplicate" | "stale";

type NextCheckQueueStatus =
  | "approved-ready"
  | "safe-ready"
  | "approval-needed"
  | "failed"
  | "completed"
  | "duplicate-or-stale";

const determineNextCheckStatusVariant = (
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

const nextCheckStatusLabel = (variant: NextCheckStatusVariant) => {
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

const getPlanStatusLabel = (variant: NextCheckStatusVariant, candidate: NextCheckPlanCandidate) => {
  if (candidate.approvalStatus) {
    const override = approvalStatusLabels[candidate.approvalStatus];
    if (override) {
      return override;
    }
  }
  return nextCheckStatusLabel(variant);
};

const NEXT_CHECK_QUEUE_STATUS_LABELS: Record<NextCheckQueueStatus, string> = {
  "approved-ready": "Approved & ready",
  "safe-ready": "Safe to automate",
  "approval-needed": "Approval needed",
  "failed": "Failed executions",
  "completed": "Completed",
  "duplicate-or-stale": "Duplicate / stale",
};

const NEXT_CHECK_QUEUE_STATUS_ORDER: NextCheckQueueStatus[] = [
  "approved-ready",
  "safe-ready",
  "approval-needed",
  "failed",
  "completed",
  "duplicate-or-stale",
];

const QUEUE_SORT_OPTIONS = [
  { label: "Backend order", value: "default" },
  { label: "Priority", value: "priority" },
  { label: "Cluster", value: "cluster" },
  { label: "Latest activity", value: "activity" },
] as const;

type QueueSortOption = (typeof QUEUE_SORT_OPTIONS)[number]["value"];

const QUEUE_PRIORITY_ORDER: Record<string, number> = {
  primary: 0,
  secondary: 1,
  fallback: 2,
};

type QueueFocusMode = "none" | "work" | "review";
const QUEUE_FOCUS_FILTERS: Record<QueueFocusMode, NextCheckQueueStatus[]> = {
  none: [],
  work: ["approved-ready", "safe-ready", "failed"],
  review: ["approval-needed", "duplicate-or-stale"],
};

// Review status filter types for recent runs panel
// Uses reviewStatus from backend: "no-executions", "unreviewed", "partially-reviewed", "fully-reviewed"
type RunsReviewFilter = "all" | "no-executions" | "awaiting-review" | "partially-reviewed" | "fully-reviewed" | "needs-attention";
const RUNS_REVIEW_FILTER_OPTIONS: { label: string; value: RunsReviewFilter }[] = [
  { label: "All runs", value: "all" },
  { label: "No executions yet", value: "no-executions" },
  { label: "Awaiting review", value: "awaiting-review" },
  { label: "Partially reviewed", value: "partially-reviewed" },
  { label: "Fully reviewed", value: "fully-reviewed" },
  { label: "Needs attention", value: "needs-attention" },
];

// Compute filter counts from runs list
const computeRunsFilterCounts = (
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

const RUNS_REVIEW_FILTER_VALUES: RunsReviewFilter[] = ["all", "no-executions", "awaiting-review", "partially-reviewed", "fully-reviewed", "needs-attention"];

const isRunsReviewFilterValue = (value: unknown): value is RunsReviewFilter =>
  typeof value === "string" && RUNS_REVIEW_FILTER_VALUES.includes(value as RunsReviewFilter);

export const QUEUE_VIEW_STORAGE_KEY = "dashboard-queue-view-state";
export const RUNS_REVIEW_FILTER_STORAGE_KEY = "dashboard-runs-review-filter";
export const SELECTED_RUN_STORAGE_KEY = "dashboard-selected-run-id";
export const RUNS_PAGE_SIZE_STORAGE_KEY = "dashboard-runs-page-size";

const DEFAULT_RUNS_REVIEW_FILTER: RunsReviewFilter = "all";
const DEFAULT_RUNS_PAGE_SIZE = 5;
const MAX_RUNS_PAGE_SIZE = 20;
const RUNS_PAGE_SIZE_OPTIONS = [5, 10, 20] as const;

const readStoredRunsReviewFilter = (): RunsReviewFilter => {
  if (typeof window === "undefined") {
    return DEFAULT_RUNS_REVIEW_FILTER;
  }
  const stored = window.localStorage.getItem(RUNS_REVIEW_FILTER_STORAGE_KEY);
  if (!stored) {
    return DEFAULT_RUNS_REVIEW_FILTER;
  }
  if (isRunsReviewFilterValue(stored)) {
    return stored;
  }
  return DEFAULT_RUNS_REVIEW_FILTER;
};

const persistRunsReviewFilter = (value: RunsReviewFilter) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(RUNS_REVIEW_FILTER_STORAGE_KEY, value);
};

const readStoredSelectedRunId = (): string | null => {
  if (typeof window === "undefined") {
    return null;
  }
  const stored = window.localStorage.getItem(SELECTED_RUN_STORAGE_KEY);
  if (!stored) {
    return null;
  }
  return stored;
};

const persistSelectedRunId = (runId: string | null) => {
  if (typeof window === "undefined") {
    return;
  }
  if (runId) {
    window.localStorage.setItem(SELECTED_RUN_STORAGE_KEY, runId);
  } else {
    window.localStorage.removeItem(SELECTED_RUN_STORAGE_KEY);
  }
};

const isRunsPageSizeValue = (value: unknown): value is typeof RUNS_PAGE_SIZE_OPTIONS[number] =>
  typeof value === "number" && RUNS_PAGE_SIZE_OPTIONS.includes(value as typeof RUNS_PAGE_SIZE_OPTIONS[number]);

const readStoredRunsPageSize = (): number => {
  if (typeof window === "undefined") {
    return DEFAULT_RUNS_PAGE_SIZE;
  }
  const stored = window.localStorage.getItem(RUNS_PAGE_SIZE_STORAGE_KEY);
  if (!stored) {
    return DEFAULT_RUNS_PAGE_SIZE;
  }
  const parsed = Number(stored);
  if (Number.isNaN(parsed) || parsed < 1 || parsed > MAX_RUNS_PAGE_SIZE) {
    return DEFAULT_RUNS_PAGE_SIZE;
  }
  return parsed;
};

const persistRunsPageSize = (value: number) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(RUNS_PAGE_SIZE_STORAGE_KEY, String(value));
};

const QUEUE_STATUS_FILTER_VALUES = new Set<NextCheckQueueStatus | "all">([
  "all",
  ...NEXT_CHECK_QUEUE_STATUS_ORDER,
]);
const QUEUE_SORT_VALUES = QUEUE_SORT_OPTIONS.map((option) => option.value);
const QUEUE_FOCUS_MODE_VALUES: QueueFocusMode[] = ["none", "work", "review"];

type QueueViewState = {
  clusterFilter: string;
  statusFilter: NextCheckQueueStatus | "all";
  commandFamilyFilter: string;
  priorityFilter: string;
  workstreamFilter: string;
  searchText: string;
  focusMode: QueueFocusMode;
  sortOption: QueueSortOption;
};

const DEFAULT_QUEUE_VIEW_STATE: QueueViewState = {
  clusterFilter: "all",
  statusFilter: "all",
  commandFamilyFilter: "all",
  priorityFilter: "all",
  workstreamFilter: "all",
  searchText: "",
  focusMode: "none",
  sortOption: "default",
};

const isQueueStatusFilterValue = (
  value: unknown
): value is NextCheckQueueStatus | "all" =>
  typeof value === "string" && QUEUE_STATUS_FILTER_VALUES.has(value as NextCheckQueueStatus | "all");

const isQueueSortOptionValue = (value: unknown): value is QueueSortOption =>
  typeof value === "string" && QUEUE_SORT_VALUES.includes(value as QueueSortOption);

const isQueueFocusModeValue = (value: unknown): value is QueueFocusMode =>
  typeof value === "string" && QUEUE_FOCUS_MODE_VALUES.includes(value as QueueFocusMode);

const readStoredQueueViewState = (): QueueViewState => {
  if (typeof window === "undefined") {
    return DEFAULT_QUEUE_VIEW_STATE;
  }
  const stored = window.localStorage.getItem(QUEUE_VIEW_STORAGE_KEY);
  if (!stored) {
    return DEFAULT_QUEUE_VIEW_STATE;
  }
  try {
    const parsed = JSON.parse(stored);
    if (!parsed || typeof parsed !== "object") {
      return DEFAULT_QUEUE_VIEW_STATE;
    }
    const candidate = parsed as Record<string, unknown>;
    return {
      clusterFilter:
        typeof candidate.clusterFilter === "string"
          ? candidate.clusterFilter
          : DEFAULT_QUEUE_VIEW_STATE.clusterFilter,
      statusFilter: isQueueStatusFilterValue(candidate.statusFilter)
        ? candidate.statusFilter
        : DEFAULT_QUEUE_VIEW_STATE.statusFilter,
      commandFamilyFilter:
        typeof candidate.commandFamilyFilter === "string"
          ? candidate.commandFamilyFilter
          : DEFAULT_QUEUE_VIEW_STATE.commandFamilyFilter,
      priorityFilter:
        typeof candidate.priorityFilter === "string"
          ? candidate.priorityFilter
          : DEFAULT_QUEUE_VIEW_STATE.priorityFilter,
      workstreamFilter:
        typeof candidate.workstreamFilter === "string"
          ? candidate.workstreamFilter
          : DEFAULT_QUEUE_VIEW_STATE.workstreamFilter,
      searchText:
        typeof candidate.searchText === "string"
          ? candidate.searchText
          : DEFAULT_QUEUE_VIEW_STATE.searchText,
      focusMode: isQueueFocusModeValue(candidate.focusMode)
        ? candidate.focusMode
        : DEFAULT_QUEUE_VIEW_STATE.focusMode,
      sortOption: isQueueSortOptionValue(candidate.sortOption)
        ? candidate.sortOption
        : DEFAULT_QUEUE_VIEW_STATE.sortOption,
    };
  } catch {
    return DEFAULT_QUEUE_VIEW_STATE;
  }
};

const persistQueueViewState = (state: QueueViewState) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(QUEUE_VIEW_STORAGE_KEY, JSON.stringify(state));
};

const clearStoredQueueViewState = () => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(QUEUE_VIEW_STORAGE_KEY);
};

const normalizeQueuePriority = (value: string | null | undefined) =>
  (value ?? "unknown").toLowerCase();

const queuePriorityRank = (value: string | null | undefined) =>
  QUEUE_PRIORITY_ORDER[normalizeQueuePriority(value)] ?? Object.keys(QUEUE_PRIORITY_ORDER).length;

const queueTimestampValue = (value: string | null | undefined) => {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
};

const outcomeStatusLabels: Record<string, string> = {
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

const outcomeStatusDisplay = (status?: string | null) =>
  outcomeStatusLabels[status ?? "unknown"] || (status ? status : "Unknown");

const outcomeStatusClass = (status?: string | null) =>
  `outcome-pill outcome-pill-${((status ?? "unknown").replace(/[^a-z0-9]+/gi, "-").toLowerCase())}`;


const LLMPolicyPanel = ({ policy }: { policy?: LLMPolicy | null }) => {
  const auto = policy?.autoDrilldown;
  const budgetStatus = auto
    ? auto.budgetExhausted === null
      ? "Budget status unknown"
      : auto.budgetExhausted
      ? "Budget exhausted"
      : "Within budget"
    : "Budget status unknown";
  const statusModifier = auto?.enabled ? "status-pill-healthy" : "status-pill-pending";
  return (
    <section className="panel llm-policy-panel" id="llm-policy">
      <div className="section-head">
        <div>
          <h2>LLM policy</h2>
          <p className="muted small">Auto drilldown policy and current usage.</p>
        </div>
        {auto ? (
          <span className={`status-pill ${statusModifier}`}>
            Auto drilldown {auto.enabled ? "enabled" : "disabled"}
          </span>
        ) : null}
      </div>
      {auto ? (
        <div className="llm-policy-grid">
          <div>
            <p className="tiny">Provider</p>
            <strong>{auto.provider || "default"}</strong>
          </div>
          <div>
            <p className="tiny">Budget</p>
            <strong>{auto.maxPerRun} per run</strong>
          </div>
          <div>
            <p className="tiny">Used this run</p>
            <strong>{auto.usedThisRun}</strong>
          </div>
          <div>
            <p className="tiny">Success / Failed / Skipped</p>
            <strong>
              {auto.successfulThisRun} / {auto.failedThisRun} / {auto.skippedThisRun}
            </strong>
          </div>
          <div>
            <p className="tiny">Budget status</p>
            <strong>{budgetStatus}</strong>
          </div>
        </div>
      ) : (
        <p className="muted small">LLM policy data is unavailable.</p>
      )}
    </section>
  );
};

// ==========================================================================
// Advisory lower-section view-model helpers
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
// Specialized lower advisory section components
// ==========================================================================

/** Top concerns - compact concern rows with left accent */

/** Evidence gaps - uncertainty-oriented rows with gap marker */

/** Next checks - action rows with parsed intent, cluster badge, and command preview */

/** Focus notes - demoted secondary guidance hints */


// Operator-friendly labels for Alertmanager ranking promotion display.
// Maps internal match dimensions to concise, trustworthy operator-facing text.
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
const formatAlertmanagerPromotion = (rankingReason: string): string => {
  // Remove internal prefix
  const internal = rankingReason.replace(/^alertmanager-context:/, "");
  
  // Split into parts: "promoted" + "matched {dimensions}: {values}"
  const parts = internal.split(":");
  if (parts.length < 2) {
    return "Promoted by Alertmanager";
  }
  
  // Parse "promoted" and "matched {dims}: {values}"
  const action = parts[0]; // "promoted"
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
const getAlertmanagerPromotionSubtext = (rankingReason: string): string | null => {
  // If internal reason has multiple match dimensions, provide subtext
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
const formatAlertmanagerProvenance = (provenance: AlertmanagerProvenance): string => {
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
const getAlertmanagerProvenanceSubtext = (provenance: AlertmanagerProvenance): string => {
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

const formatFeedbackAdaptationProvenance = (provenance: FeedbackAdaptationProvenance): string => {
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

const getFeedbackAdaptationProvenanceSubtext = (provenance: FeedbackAdaptationProvenance): string => {
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
    parts.push(`Feedback: ${feedbackSummary}`);
  }
  
  return parts.length > 0 ? parts.join(" · ") : "Feedback adaptation applied";
};
export const ProposalList = ({
  proposals,
  filter,
  sortKey,
  searchText,
  expanded,
  toggle,
}: {
  proposals: ProposalEntry[];
  filter: string;
  sortKey: SortKey;
  searchText: string;
  expanded: Set<string>;
  toggle: (id: string) => void;
}) => {
  const visible = useMemo(() => {
    return proposals
      .filter((entry) => {
        if (filter !== "all" && entry.status !== filter) {
          return false;
        }
        if (!searchText) {
          return true;
        }
        const needle = searchText.toLowerCase();
        return (
          entry.target.toLowerCase().includes(needle) ||
          entry.rationale.toLowerCase().includes(needle)
        );
      })
      .sort((a, b) => {
        if (sortKey === "confidence") {
          return confidenceWeight(a.confidence) - confidenceWeight(b.confidence);
        }
        return a[sortKey].localeCompare(b[sortKey]);
      });
  }, [filter, proposals, searchText, sortKey]);

  if (!visible.length) {
    return <p className="muted">No proposals match the current filters.</p>;
  }

  return (
    <div className="proposal-table">
      {visible.map((proposal) => {
        const expandedEntry = expanded.has(proposal.proposalId);
        const summaryRationale = expandedEntry
          ? proposal.rationale
          : truncateText(proposal.rationale, 180);
        return (
          <article
            className="proposal-row"
            key={proposal.proposalId}
            data-testid="proposal-row"
            data-proposal-id={proposal.proposalId}
          >
            <div className="proposal-row-summary">
              <div>
                <p className="eyebrow compact">{proposal.target}</p>
                <strong>{proposal.proposalId}</strong>
                <div className="proposal-status-line">
                  <span className={statusClass(proposal.status)}>{proposal.status}</span>
                  <span
                    className={`confidence-badge level-${priorityLabel(proposal.confidence)}`}
                  >
                    {proposal.confidence} confidence
                  </span>
                </div>
              </div>
              <div className="proposal-row-actions">
                <span className="small">Run {proposal.sourceRunId}</span>
                <button type="button" className="text-button" onClick={() => toggle(proposal.proposalId)}>
                  {expandedEntry ? "Hide details" : "Show details"}
                </button>
              </div>
            </div>
            <div className={`proposal-row-details ${expandedEntry ? "is-visible" : ""}`}>
              <p className="proposal-rationale">{summaryRationale}</p>
              <div className="proposal-meta-grid">
                <div>
                  <p className="small">Expected benefit</p>
                  <p className="small">{proposal.expectedBenefit}</p>
                </div>
                <div>
                  <p className="small">Lifecycle</p>
                  <div className="lifecycle-row">
                    {proposal.lifecycle.map((step) => (
                      <span className="lifecycle-chip" key={`${step.status}-${step.timestamp}`}>
                        {step.status}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="small">Latest note</p>
                  <p className="small">{proposal.latestNote || "n/a"}</p>
                </div>
              </div>
              <div className="proposal-artifacts">
                {proposal.artifacts.map((artifact) => {
                  const url = artifactUrl(artifact.path);
                  return (
                    url && (
                      <a
                        key={artifact.label}
                        className="artifact-chip"
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {artifact.label}
                      </a>
                    )
                  );
                })}
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
};

const App = () => {
  // Run selection state - extracted to useRunSelection hook
  // MUST be called BEFORE useRunData because useRunData needs selectedRunId
  const {
    runs: runsList,
    selectedRunId,
    selectRun: setSelectedRunId,
    isLoading: runsListLoading,
    error: runsListError,
    refreshRuns,
    latestRunId,
    isLatest: isSelectedRunLatest,
    autoRefreshInterval,
    handleAutoRefreshChange,
    // Pagination and filter state
    runsFilter,
    setRunsFilter,
    runsPageSize,
    setRunsPageSize,
    runsPage,
    setRunsPage,
    isRunsListFollowingSelection,
    setIsRunsListFollowingSelection,
    filteredRunsList,
    runsFilterCounts,
    paginatedRunsList,
    totalRunsPages,
    isSelectedRunVisibleOnCurrentRunsPage,
    handleRunsFilterChange,
    handleRunsPageSizeChange,
    handleRunsPageChange,
    computePageForRunId,
    navigateToPageContainingRun,
    handleShowSelectedRun,
    handleRunSelection,
    jumpToLatest,
  } = useRunSelection();

  // Run data state - extracted to useRunData hook
  const {
    run,
    isLoading: runDataLoading,
    isError: runDataError,
    lastRefresh,
    refresh: refreshRunData,
  } = useRunData({
    selectedRunId,
  });

  // App data state - extracted to useAppData hook
  const {
    fleet,
    proposals,
    expandedProposals,
    handleToggleProposal,
    statusOptions,
    clusterDetail,
    selectedClusterLabel: hookSelectedClusterLabel,
    handleClusterSelection: hookHandleClusterSelection,
    promotionStatus: hookPromotionStatus,
    refreshAppData,
    handlePromoteDeterministicCheck,
    handleUsefulnessFeedback,
    handleAlertmanagerRelevanceFeedback,
    error,
  } = useAppData({
    selectedRunId,
    lastRefresh,
    refreshRuns,
    refreshRunData,
  });

  // Derive combined loading and error state
  const isLoading = runDataLoading || runsListLoading;
  const isError = runDataError || error;

  // UI state - extracted to useUIState hook
  const {
    statusFilter,
    setStatusFilter,
    searchText,
    setSearchText,
    sortKey,
    setSortKey,
    activeTab,
    setActiveTab,
    clusterDetailExpanded,
    setClusterDetailExpanded,
    highlightedClusterLabel,
    setHighlightedClusterLabel,
    incidentExpandedClusters,
    setIncidentExpandedClusters,
    executionHistoryHighlightKey,
    setExecutionHistoryHighlightKey,
    queueHighlightKey,
    setQueueHighlightKey,
    executionHistoryFilter,
    setExecutionHistoryFilter,
    expandedQueueItems,
    setExpandedQueueItems,
    toggleQueueDetails,
  } = useUIState();

  // Queue state - derived from run data
  const runQueue: NextCheckQueueItem[] = run?.nextCheckQueue ?? [];

  // Queue state - managed by useQueueState hook
  const {
    queueClusterFilter,
    queueStatusFilter,
    queueCommandFamilyFilter,
    queuePriorityFilter,
    queueWorkstreamFilter,
    queueSearch,
    queueSortOption,
    queueFocusMode,
    setQueueClusterFilter,
    setQueueStatusFilter,
    setQueueCommandFamilyFilter,
    setQueuePriorityFilter,
    setQueueWorkstreamFilter,
    setQueueSearch,
    setQueueSortOption,
    setQueueFocusMode,
    queueClusterOptions,
    queueCommandFamilyOptions,
    queuePriorityOptions,
    queueWorkstreamOptions,
    filteredQueue,
    sortedQueue,
    queueGroups,
  } = useQueueState({ runQueue });

  // Execution/approval transient state - stays in App.tsx (per-execution lifecycle)
  const [executionResults, setExecutionResults] = useState<Record<string, ExecutionResult>>({});
  const [executingCandidate, setExecutingCandidate] = useState<string | null>(null);
  const [approvalResults, setApprovalResults] = useState<Record<string, ApprovalResult>>({});
  const [approvingCandidate, setApprovingCandidate] = useState<string | null>(null);
  const clusterHighlightTimer = useRef<number | null>(null);
  const executionHighlightTimer = useRef<number | null>(null);
  const queueHighlightTimer = useRef<number | null>(null);
  // Track the last executed candidate key so we can highlight it after refresh
  const lastExecutedCandidateKey = useRef<string | null>(null);

  // Batch execution state for recent runs
  const [executingBatchRunId, setExecutingBatchRunId] = useState<string | null>(null);
  const [batchExecutionError, setBatchExecutionError] = useState<Record<string, string>>({});

  // Handle batch execution for a run - refreshes runs list and selected run via hooks
  const handleBatchExecution = useCallback(async (runId: string) => {
    setExecutingBatchRunId(runId);
    setBatchExecutionError((prev) => {
      const next = { ...prev };
      delete next[runId];
      return next;
    });
    try {
      // Explicitly send dryRun: false for actual execution
      // The backend defaults to False, but being explicit improves clarity and debugging
      await runBatchExecution({ runId, dryRun: false });
      // Refresh runs list and run data through hooks after successful execution
      await refreshRuns();
      // If the selected run is the one we just executed, refresh its data too
      if (selectedRunId === runId) {
        await refreshRunData();
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Batch execution failed";
      setBatchExecutionError((prev) => ({
        ...prev,
        [runId]: message,
      }));
    } finally {
      setExecutingBatchRunId((current) => (current === runId ? null : current));
    }
  }, [selectedRunId, refreshRuns, refreshRunData]);

  // Derive selectedClusterLabel from hook (with local clusterDetailExpanded handling)
  const selectedClusterLabel = hookSelectedClusterLabel;

  // Handle cluster selection - combines hook logic with local clusterDetailExpanded state
  const handleClusterSelection = (label: string, options?: { expand?: boolean }) => {
    hookHandleClusterSelection(label, options);
    if (options?.expand) {
      setClusterDetailExpanded(true);
    }
  };

  // App-level refresh wrapper - calls hook refresh and handles App-specific side effects
  const refresh = useCallback(async () => {
    await refreshAppData();
    // Clear local execution results after successful refresh reconciliation.
    // This allows the UI to transition from transient local execution state
    // to refreshed artifact-backed payload as the durable source of truth.
    setExecutionResults({});
    // After successful refresh reconciliation, highlight the last executed candidate
    // if we have a tracked key from a recent manual execution.
    if (lastExecutedCandidateKey.current) {
      const keyToHighlight = lastExecutedCandidateKey.current;
      // Clear the ref so we don't keep highlighting on subsequent auto-refreshes
      lastExecutedCandidateKey.current = null;
      // Trigger the highlight after state updates have settled
      requestAnimationFrame(() => {
        highlightQueueCard(keyToHighlight);
      });
    }
  }, [refreshAppData]);

  // Build promotion key helper
  const buildPromotionKey = (clusterLabel: string, description: string, index: number) =>
    `${clusterLabel}::${description}::${index}`;

  const scrollToSection = (id: string) => {
    if (typeof document === "undefined") {
      return;
    }
    const section = document.getElementById(id);
    if (!section) {
      return;
    }
    section.scrollIntoView?.({ behavior: "smooth", block: "start" });
  };

  const highlightCluster = (label: string | null) => {
    setHighlightedClusterLabel(label);
    if (clusterHighlightTimer.current) {
      window.clearTimeout(clusterHighlightTimer.current);
    }
    if (!label) {
      return;
    }
    clusterHighlightTimer.current = window.setTimeout(() => {
      setHighlightedClusterLabel(null);
    }, NAVIGATION_HIGHLIGHT_DURATION_MS);
  };

  const highlightExecutionEntry = (key: string | null) => {
    setExecutionHistoryHighlightKey(key);
    if (executionHighlightTimer.current) {
      window.clearTimeout(executionHighlightTimer.current);
    }
    if (!key) {
      return;
    }
    executionHighlightTimer.current = window.setTimeout(() => {
      setExecutionHistoryHighlightKey(null);
    }, NAVIGATION_HIGHLIGHT_DURATION_MS);
  };

  const highlightQueueCard = (key: string | null) => {
    setQueueHighlightKey(key);
    if (queueHighlightTimer.current) {
      window.clearTimeout(queueHighlightTimer.current);
    }
    if (!key) {
      return;
    }
    queueHighlightTimer.current = window.setTimeout(() => {
      setQueueHighlightKey(null);
    }, NAVIGATION_HIGHLIGHT_DURATION_MS);
    // Scroll the highlighted queue card into view
    requestAnimationFrame(() => {
      const element = document.querySelector(`[data-queue-key="${CSS.escape(key)}"]`);
      if (element) {
        element.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
  };

  const toggleIncidentExpansion = (label: string) => {
    setIncidentExpandedClusters((current) => ({
      ...current,
      [label]: !current[label],
    }));
  };

  const buildCandidateKey = (candidate: NextCheckPlanCandidate, index: number) =>
    `next-check-${candidate.candidateId ?? candidate.candidateIndex ?? index}-${
      candidate.targetCluster ?? selectedClusterLabel ?? "global"
    }`;

  const executionHistory: NextCheckExecutionHistoryEntry[] = run?.nextCheckExecutionHistory ?? [];
  const queueExplanation = run?.nextCheckQueueExplanation ?? null;

  const findExecutionHistoryEntry = (candidate: NextCheckQueueItem) => {
    if (!executionHistory.length) {
      return null;
    }
    if (candidate.latestArtifactPath) {
      const artifactMatch = executionHistory.find(
        (entry) => entry.artifactPath === candidate.latestArtifactPath
      );
      if (artifactMatch) {
        return artifactMatch;
      }
    }
    const normalizedDescription = candidate.description?.trim();
    if (candidate.targetCluster && normalizedDescription) {
      const contextMatch = executionHistory.find(
        (entry) =>
          entry.clusterLabel === candidate.targetCluster &&
          entry.candidateDescription === normalizedDescription
      );
      if (contextMatch) {
        return contextMatch;
      }
    }
    if (normalizedDescription) {
      const descriptionMatch = executionHistory.find(
        (entry) => entry.candidateDescription === normalizedDescription
      );
      if (descriptionMatch) {
        return descriptionMatch;
      }
    }
    return null;
  };

  const toggleQueueFocusPreset = (mode: QueueFocusMode) => {
    setQueueFocusMode((current) => (current === mode ? "none" : mode));
  };

  const resetQueueFilters = () => {
    setQueueClusterFilter(DEFAULT_QUEUE_VIEW_STATE.clusterFilter);
    setQueueStatusFilter(DEFAULT_QUEUE_VIEW_STATE.statusFilter);
    setQueueCommandFamilyFilter(DEFAULT_QUEUE_VIEW_STATE.commandFamilyFilter);
    setQueuePriorityFilter(DEFAULT_QUEUE_VIEW_STATE.priorityFilter);
    setQueueWorkstreamFilter(DEFAULT_QUEUE_VIEW_STATE.workstreamFilter);
    setQueueSearch(DEFAULT_QUEUE_VIEW_STATE.searchText);
    setQueueSortOption(DEFAULT_QUEUE_VIEW_STATE.sortOption);
    setQueueFocusMode(DEFAULT_QUEUE_VIEW_STATE.focusMode);
  };

  const resetQueueView = () => {
    resetQueueFilters();
    clearStoredQueueViewState();
  };

  const isManualExecutionAllowed = (candidate: NextCheckPlanCandidate) => {
    const hasCandidateIdentifier = Boolean(candidate.candidateId?.trim()) || candidate.candidateIndex != null;
    if (!hasCandidateIdentifier) {
      return false;
    }
    if (!candidate.safeToAutomate) {
      return false;
    }
    if (candidate.requiresOperatorApproval && candidate.approvalStatus !== "approved") {
      return false;
    }
    if (candidate.duplicateOfExistingEvidence) {
      return false;
    }
    if (!candidate.suggestedCommandFamily) {
      return false;
    }
    if (!ALLOWED_MANUAL_FAMILIES.has(candidate.suggestedCommandFamily)) {
      return false;
    }
    const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
    if (!targetLabel) {
      return false;
    }
    return true;
  };

  const getNotRunnableExplanation = (candidate: NextCheckPlanCandidate): string | null => {
    // Check in the same order as isManualExecutionAllowed to ensure consistency
    // 1. Candidate identifier
    const hasCandidateIdentifier = Boolean(candidate.candidateId?.trim()) || candidate.candidateIndex != null;
    if (!hasCandidateIdentifier) {
      return "Not runnable: missing candidate identifier";
    }

    // 2. Safe to automate
    if (!candidate.safeToAutomate) {
      const reason = candidate.safetyReason || "not marked safe to automate";
      return `Not runnable: ${humanizeReason(reason) || reason}`;
    }

    // 3. Approval required
    if (candidate.requiresOperatorApproval && candidate.approvalStatus !== "approved") {
      const reason = candidate.approvalReason || "approval required";
      return `Not runnable: ${humanizeReason(reason) || reason}`;
    }

    // 4. Duplicate
    if (candidate.duplicateOfExistingEvidence) {
      const reason = candidate.duplicateReason || "duplicate of existing evidence";
      return `Not runnable: ${humanizeReason(reason) || reason}`;
    }

    // 5. Command family exists
    if (!candidate.suggestedCommandFamily) {
      return "Not runnable: no command family specified";
    }

    // 6. Command family allowed
    if (!ALLOWED_MANUAL_FAMILIES.has(candidate.suggestedCommandFamily)) {
      return `Not runnable: unsupported command family '${candidate.suggestedCommandFamily}'`;
    }

    // 7. Target cluster resolved
    const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
    if (!targetLabel) {
      return "Not runnable: target cluster unresolved";
    }

    // Fallback - should not reach here if logic is correct
    return "Not eligible for manual execution";
  };

  const handleManualExecution = async (candidate: NextCheckPlanCandidate, candidateKey: string) => {
    const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
    const candidateId = candidate.candidateId?.trim() ? candidate.candidateId : undefined;
    const candidateIndex = candidate.candidateIndex;
    const planArtifactPath = candidate.planArtifactPath?.trim() ? candidate.planArtifactPath : undefined;
    if (!targetLabel || (candidateIndex == null && !candidateId)) {
      setExecutionResults((prev) => ({
        ...prev,
        [candidateKey]: { status: "error", summary: "Unable to determine candidate target." },
      }));
      return;
    }
    setExecutingCandidate(candidateKey);
    // Track the candidate key so we can highlight it after refresh reconciliation
    lastExecutedCandidateKey.current = candidateKey;
    try {
      const result = await executeNextCheckCandidate({
        candidateId,
        candidateIndex: candidateIndex ?? undefined,
        clusterLabel: targetLabel,
        planArtifactPath: planArtifactPath ?? null,
      });
      setExecutionResults((prev) => ({
        ...prev,
        [candidateKey]: result,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Manual execution failed";
      const blockingReason =
        err instanceof Error && "blockingReason" in err
          ? (err as ExecutionErrorResult).blockingReason
          : undefined;
      setExecutionResults((prev) => ({
        ...prev,
        [candidateKey]: {
          status: "error",
          summary: message,
          blockingReason: blockingReason ?? null,
        },
      }));
    } finally {
      setExecutingCandidate((current) => (current === candidateKey ? null : current));
    }
  };

  const handleApproveCandidate = async (
    candidate: NextCheckPlanCandidate,
    candidateKey: string
  ) => {
    const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
    const candidateId = candidate.candidateId?.trim() ? candidate.candidateId : undefined;
    const candidateIndex = candidate.candidateIndex;
    if (!targetLabel || (candidateIndex == null && !candidateId)) {
      setApprovalResults((prev) => ({
        ...prev,
        [candidateKey]: {
          status: "error",
          summary: "Unable to determine candidate target",
        },
      }));
      return;
    }
    setApprovingCandidate(candidateKey);
    try {
      const result = await approveNextCheckCandidate({
        candidateId,
        candidateIndex: candidateIndex ?? undefined,
        clusterLabel: targetLabel,
      });
      setApprovalResults((prev) => ({
        ...prev,
        [candidateKey]: {
          status: result.status === "success" ? "success" : "error",
          summary:
            result.summary ||
            (result.status === "success" ? "Candidate approved" : "Approval failed"),
          artifactPath: result.artifactPath,
          approvalTimestamp: result.approvalTimestamp,
        },
      }));
      await refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Approval failed";
      setApprovalResults((prev) => ({
        ...prev,
        [candidateKey]: { status: "error", summary: message },
      }));
    } finally {
      setApprovingCandidate((current) => (current === candidateKey ? null : current));
    }
  };

  if (!run || !fleet || !proposals) {
    return (
      <div className="app-shell loading">
        <div>
          <p>Loading operator data…</p>
          {error && <div className="alert">{error}</div>}
        </div>
      </div>
    );
  }

  // Derive header display metadata directly from the runs list so that clicking
  // "← Latest" or selecting a different run updates the header immediately, before
  // the async run-detail fetch completes. runsList is always populated before this
  // point (we are past the loading guard) and is updated on every refresh cycle.
  const selectedRunListEntry = runsList.find((r) => r.runId === selectedRunId) ?? null;
  const headerRunId = selectedRunListEntry?.runId ?? run.runId;
  const headerRunLabel = selectedRunListEntry?.runLabel ?? run.label;
  const headerRunTimestamp = selectedRunListEntry?.timestamp ?? run.timestamp;
  const runRecency = relativeRecency(headerRunTimestamp);
  const latestRunRecency = latestRunId ? relativeRecency(runsList.find(r => r.runId === latestRunId)?.timestamp ?? run.timestamp) : runRecency;
  const runFresh = !isStaleTimestamp(headerRunTimestamp);
  const runAgeMinutes = Math.floor(dayjs().diff(headerRunTimestamp, "minute"));
  const degradedCount =
    fleet.fleetStatus.ratingCounts.find((entry) => entry.rating.toLowerCase() === "degraded")?.count ?? 0;
  const hasDegradedClusters = degradedCount > 0;
  const headerStats = [
    { label: "Last", value: formatDuration(run.runStats.lastRunDurationSeconds) },
    { label: "Runs", value: String(run.runStats.totalRuns) },
    { label: "P50", value: formatDuration(run.runStats.p50RunDurationSeconds) },
    { label: "P95", value: formatDuration(run.runStats.p95RunDurationSeconds) },
    { label: "P99", value: formatDuration(run.runStats.p99RunDurationSeconds) },
  ];
  const runStatsSummary = headerStats.map((stat) => `${stat.label} ${stat.value}`).join(" · ");
  const runSummaryStats = [
    { label: "Clusters", value: run.clusterCount },
    { label: "Degraded", value: degradedCount },
    { label: "Proposals", value: run.proposalCount },
    { label: "Notifications", value: run.notificationCount },
    { label: "Drilldowns", value: run.drilldownCount },
  ];
  const selectedCluster = fleet.clusters.find((cluster) => cluster.label === selectedClusterLabel) ?? null;
  const clusterRecency = selectedCluster?.latestRunTimestamp
    ? relativeRecency(selectedCluster.latestRunTimestamp)
    : null;
  const clusterFresh = selectedCluster ? !isStaleTimestamp(selectedCluster.latestRunTimestamp) : true;
  const autoRefreshSelectValue = autoRefreshInterval ? String(autoRefreshInterval) : "off";
  const autoRefreshStatusText = autoRefreshInterval
    ? `Auto refresh every ${autoRefreshInterval}s`
    : "Auto refresh is off";
  const interpretation: AutoInterpretation | null = clusterDetail?.autoInterpretation || null;
  const recommendedArtifacts = buildClusterRecommendedArtifacts(clusterDetail);
  const clusterTriggerReason =
    selectedCluster?.topTriggerReason ||
    clusterDetail?.findings?.[0]?.triggerReasons?.[0] ||
    clusterDetail?.topProblem?.title ||
    "Trigger reason pending";

  const drilldownAvailability = clusterDetail?.drilldownAvailability;
  const drilldownSummary = drilldownAvailability
    ? `${drilldownAvailability.available}/${drilldownAvailability.totalClusters} drilldown${
        drilldownAvailability.available === 1 ? "" : "s"
      } ready`
    : "Drilldown data pending";
  const recencyTimestamp = selectedCluster?.latestRunTimestamp
    ? formatTimestamp(selectedCluster.latestRunTimestamp)
    : "Awaiting run";
  const planCandidates: NextCheckPlanCandidate[] = clusterDetail?.nextCheckPlan ?? [];
  const runPlan = run.nextCheckPlan;
  const orphanedApprovals = runPlan?.orphanedApprovals ?? [];
  const planArtifactLink = runPlan?.artifactPath ? artifactUrl(runPlan.artifactPath) : null;
  const plannerAvailability = run.plannerAvailability ?? null;
  const plannerReason = plannerAvailability?.reason;
  const plannerHint = plannerAvailability?.hint;
  const plannerArtifactPath = plannerAvailability?.artifactPath ?? runPlan?.artifactPath ?? null;
  const plannerArtifactUrl = plannerArtifactPath ? artifactUrl(plannerArtifactPath) : null;
  const plannerNextActionHint = plannerAvailability?.nextActionHint;
  const planSummaryText =
    runPlan?.summary ?? plannerReason ?? "Provider-assisted next-check candidates are available.";
  const plannerReasonText = plannerReason ?? "Planner data is not available for this run.";
  const planCandidateCountLabel =
    runPlan?.candidateCount != null
      ? `${runPlan.candidateCount} candidate${runPlan.candidateCount === 1 ? "" : "s"}`
      : `${planCandidates.length} candidate${planCandidates.length === 1 ? "" : "s"}`;
  const planStatusText = runPlan?.status ?? null;
  const outcomeSummary = runPlan?.outcomeCounts ?? [];

  const runPlanCandidates: NextCheckPlanCandidate[] = runPlan?.candidates ?? [];
  const discoveryVariantOrder: NextCheckStatusVariant[] = [
    "safe",
    "approval",
    "approved",
    "duplicate",
    "stale",
  ];
  const discoveryVariantCounts: Record<NextCheckStatusVariant, number> = {
    safe: 0,
    approval: 0,
    approved: 0,
    duplicate: 0,
    stale: 0,
  };
  runPlanCandidates.forEach((candidate) => {
    const variant = determineNextCheckStatusVariant(candidate);
    discoveryVariantCounts[variant] = (discoveryVariantCounts[variant] ?? 0) + 1;
  });
  const discoveryClusters = Array.from(
    new Set(
      runPlanCandidates
        .map((candidate) => candidate.targetCluster)
        .filter((label): label is string => Boolean(label))
    )
  );

  const deterministicChecks = run.deterministicNextChecks;
  const deterministicClusters = deterministicChecks?.clusters ?? [];
  const hasDeterministicNextChecks = deterministicClusters.length > 0;
  const deterministicSummary = hasDeterministicNextChecks
    ? `${deterministicChecks?.totalNextCheckCount ?? 0} candidate check${
        (deterministicChecks?.totalNextCheckCount ?? 0) === 1 ? "" : "s"
      } to review and promote to the work list`
    : "Review the cluster detail to generate candidate checks.";

  const focusClusterForNextChecks = (clusterLabel?: string | null) => {
    const target =
      clusterLabel ||
      discoveryClusters[0] ||
      selectedClusterLabel ||
      fleet.clusters[0]?.label ||
      null;
    if (!target) {
      return;
    }
    handleClusterSelection(target, { expand: true });
    highlightCluster(target);
    if (typeof document !== "undefined") {
      scrollToSection("cluster");
    }
  };

  const handleBackToQueue = () => {
    scrollToSection("next-check-queue");
  };

  const handleQueueClusterJump = (candidate: NextCheckQueueItem) => {
    focusClusterForNextChecks(candidate.targetCluster ?? undefined);
  };

  const handleQueueExecutionJump = (candidate: NextCheckQueueItem) => {
    const entry = findExecutionHistoryEntry(candidate);
    highlightExecutionEntry(entry ? buildExecutionEntryKey(entry) : null);
    scrollToSection("execution-history");
  };

  const runLlmStatsLine = renderLlmStatsLine(run.llmStats);
  const historicalLlmStatsLine = run.historicalLlmStats
    ? renderLlmStatsLine(run.historicalLlmStats, "llm-stats-line-historical")
    : null;
  const providerBreakdown = run.llmStats.providerBreakdown
    .map((entry) => `${entry.provider} ${entry.calls} (${entry.failedCalls} failed)`)
    .join(" · ");

  return (
    <div className="app-shell">
      <header className="panel hero compact">
        <div className="hero-content">
          <HeaderBranding />
          <div className="hero-run">
            <div className="hero-run-identity">
              <div className="hero-run-header">
                <p className="eyebrow hero-run-label">Selected run</p>
                <span className={`run-badge run-badge--${isSelectedRunLatest ? "latest" : "past"}`}>
                  {isSelectedRunLatest ? "Latest" : "Past run"}
                </span>
              </div>
              <div className="hero-run-title">
                <strong>Run {headerRunLabel}</strong>
                <span className="hero-run-id">ID {headerRunId}</span>
              </div>
              <p className="hero-run-captured">Captured {runRecency}</p>
            </div>
            <div className="hero-run-freshness">
              {isSelectedRunLatest && (
                <span className={`freshness-indicator freshness-indicator--${getRunFreshnessLevel(headerRunTimestamp)}`}>
                  <span className="freshness-indicator__emoji">{FRESHNESS_EMOJI[getRunFreshnessLevel(headerRunTimestamp)]}</span>
                  <span className="freshness-indicator__label">{FRESHNESS_LABEL[getRunFreshnessLevel(headerRunTimestamp)]}</span>
                </span>
              )}
              {!isSelectedRunLatest && (
                <button
                  type="button"
                  className="link tiny"
                  onClick={jumpToLatest}
                  title="Jump back to the latest run"
                >
                  ← Latest
                </button>
              )}
            </div>
            {!isSelectedRunLatest && (
              <p className="hero-run-latest-hint">
                Latest run available: {latestRunRecency}
              </p>
            )}
          </div>
        </div>
        <div className="hero-actions">
          <div className="refresh-controls">
            <span
              className={`page-freshness-indicator page-freshness-indicator--${getPageFreshnessLevel(lastRefresh)}`}
              title={`Page data refreshed ${relativeRecency(lastRefresh.toISOString())}`}
              aria-label={`Page data freshness: ${getPageFreshnessLevel(lastRefresh)}`}
            >
              {FRESHNESS_EMOJI[getPageFreshnessLevel(lastRefresh)]}
            </span>
            <button type="button" onClick={refresh}>
              Refresh
            </button>
            <div className="autorefresh-control">
              <label htmlFor="auto-refresh-interval">Auto</label>
              <select
                id="auto-refresh-interval"
                value={autoRefreshSelectValue}
                onChange={(event) => handleAutoRefreshChange(event.target.value)}
              >
                {AUTOREFRESH_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <ThemeSwitch />
        </div>
      </header>
      <nav className="cockpit-nav" aria-label="Fleet cockpit sections">
        <a className="cockpit-nav__item" href="#recent-runs">Recent runs</a>
        <a className="cockpit-nav__item" href="#run-detail">Run summary</a>
        <a className="cockpit-nav__item" href="#review-enrichment">Provider-assisted advisory</a>
        <a className="cockpit-nav__item" href="#provider-execution">Provider-assisted branches</a>
        <a className="cockpit-nav__item" href="#diagnostic-pack-download">Diagnostic package</a>
        {run.diagnosticPackReview && (
          <a className="cockpit-nav__item" href="#diagnostic-pack-review">Review insights</a>
        )}
        <a className="cockpit-nav__item" href="#deterministic-next-checks">Evidence checks</a>
        <a className="cockpit-nav__item" href="#execution-history">Execution review</a>
        <a className="cockpit-nav__item" href="#next-check-queue">Work list</a>
        <a className="cockpit-nav__item" href="#fleet">Fleet overview</a>
        <a className="cockpit-nav__item" href="#cluster">Cluster detail</a>
        <a className="cockpit-nav__item" href="#proposals">Action proposals</a>
        <a className="cockpit-nav__item" href="#notifications">Notifications</a>
        <a className="cockpit-nav__item" href="#llm-policy">LLM policy</a>
        <a className="cockpit-nav__item" href="#llm-activity">LLM activity</a>
      </nav>
      {error && <div className="alert">{error}</div>}
      <RecentRunsPanel
        runsList={runsList}
        selectedRunId={selectedRunId}
        runsFilter={runsFilter}
        runsFilterCounts={runsFilterCounts}
        paginatedRunsList={paginatedRunsList}
        filteredRunsList={filteredRunsList}
        runsListLoading={runsListLoading}
        runsListError={runsListError}
        runsPage={runsPage}
        totalRunsPages={totalRunsPages}
        runsPageSize={runsPageSize}
        isRunsListFollowingSelection={isRunsListFollowingSelection}
        isSelectedRunVisibleOnCurrentRunsPage={isSelectedRunVisibleOnCurrentRunsPage}
        executingBatchRunId={executingBatchRunId}
        batchExecutionError={batchExecutionError}
        onRunsFilterChange={handleRunsFilterChange}
        onRunsPageChange={handleRunsPageChange}
        onRunsPageSizeChange={handleRunsPageSizeChange}
        onRunSelection={handleRunSelection}
        onBatchExecution={handleBatchExecution}
        onShowSelectedRun={handleShowSelectedRun}
        onFocusClusterForNextChecks={focusClusterForNextChecks}
      />
      <RunSummaryPanel
        run={run}
        isSelectedRunLatest={isSelectedRunLatest}
        selectedClusterLabel={selectedClusterLabel}
        onFocusClusterForNextChecks={focusClusterForNextChecks}
        runSummaryStats={runSummaryStats}
        runStatsSummary={runStatsSummary}
        runLlmStatsLine={runLlmStatsLine}
        historicalLlmStatsLine={historicalLlmStatsLine}
        providerBreakdown={providerBreakdown}
        runPlan={runPlan}
        runPlanCandidates={runPlanCandidates}
        planSummaryText={planSummaryText}
        planStatusText={planStatusText}
        plannerReasonText={plannerReasonText}
        plannerHint={plannerHint}
        plannerNextActionHint={plannerNextActionHint}
        plannerArtifactUrl={plannerArtifactUrl}
        planCandidateCountLabel={planCandidateCountLabel}
        discoveryVariantOrder={discoveryVariantOrder}
        discoveryVariantCounts={discoveryVariantCounts}
        discoveryClusters={discoveryClusters}
      />
      {/* Workflow Lane: Diagnose Now */}
      <div className="workflow-lane-header">
        <div className="workflow-lane-label">
          <span className="workflow-lane-icon">🔍</span>
          <span className="workflow-lane-title">{WORKFLOW_LANES.diagnose.label}</span>
        </div>
        <p className="workflow-lane-description muted small">{WORKFLOW_LANES.diagnose.description}</p>
      </div>
      <ReviewEnrichmentPanel
        reviewEnrichment={run.reviewEnrichment}
        reviewEnrichmentStatus={run.reviewEnrichmentStatus}
        nextCheckPlan={run.nextCheckPlan}
        onNavigateToQueue={() => scrollToSection("next-check-queue")}
        onFocusQueueReview={() => setQueueFocusMode("review")}
      />
      <ProviderExecutionPanel execution={run.providerExecution} />
      <RunDiagnosticPackPanel diagnosticPack={run.diagnosticPack} />
      <DiagnosticPackReviewPanel review={run.diagnosticPackReview} />
      <AlertmanagerSnapshotPanel compact={run.alertmanagerCompact} clusterLabel={selectedClusterLabel} />
      {run.alertmanagerSources && (
        <AlertmanagerSourcesPanel
          sources={run.alertmanagerSources}
          runId={run.runId}
          clusterLabel={selectedClusterLabel}
          onRefresh={refresh}
        />
      )}
    <DeterministicNextChecksPanel
      deterministicChecks={deterministicChecks}
      deterministicSummary={deterministicSummary}
      hookPromotionStatus={hookPromotionStatus}
      incidentExpandedClusters={incidentExpandedClusters}
      onPromoteCheck={handlePromoteDeterministicCheck}
      onToggleIncidentExpansion={toggleIncidentExpansion}
      onFocusClusterForNextChecks={focusClusterForNextChecks}
      onSetQueueStatusFilter={setQueueStatusFilter}
      onSetQueueClusterFilter={setQueueClusterFilter}
      onScrollToSection={scrollToSection}
      artifactUrl={artifactUrl}
      hasDegradedClusters={hasDegradedClusters}
    />
    {/* Workflow Lane: Work Next Checks */}
    <div className="workflow-lane-header">
      <div className="workflow-lane-label">
        <span className="workflow-lane-icon">⚡</span>
        <span className="workflow-lane-title">{WORKFLOW_LANES.work.label}</span>
      </div>
      <p className="workflow-lane-description muted small">{WORKFLOW_LANES.work.description}</p>
    </div>
    <ExecutionHistoryPanel
      history={executionHistory}
      runId={run.runId}
      runLabel={run.label}
      queueCandidateCount={runQueue.length}
      highlightedKey={executionHistoryHighlightKey}
      onSubmitFeedback={handleUsefulnessFeedback}
      onSubmitAlertmanagerRelevanceFeedback={handleAlertmanagerRelevanceFeedback}
      filter={executionHistoryFilter}
      onFilterChange={setExecutionHistoryFilter}
      runQueue={runQueue}
      onHighlightQueueCard={highlightQueueCard}
    />
    <QueuePanel
      queueClusterFilter={queueClusterFilter}
      queueStatusFilter={queueStatusFilter}
      queueCommandFamilyFilter={queueCommandFamilyFilter}
      queuePriorityFilter={queuePriorityFilter}
      queueWorkstreamFilter={queueWorkstreamFilter}
      queueSearch={queueSearch}
      queueSortOption={queueSortOption}
      queueFocusMode={queueFocusMode}
      setQueueClusterFilter={setQueueClusterFilter}
      setQueueStatusFilter={setQueueStatusFilter}
      setQueueCommandFamilyFilter={setQueueCommandFamilyFilter}
      setQueuePriorityFilter={setQueuePriorityFilter}
      setQueueWorkstreamFilter={setQueueWorkstreamFilter}
      setQueueSearch={setQueueSearch}
      setQueueSortOption={setQueueSortOption}
      setQueueFocusMode={setQueueFocusMode}
      queueClusterOptions={queueClusterOptions}
      queueCommandFamilyOptions={queueCommandFamilyOptions}
      queuePriorityOptions={queuePriorityOptions}
      queueWorkstreamOptions={queueWorkstreamOptions}
      runQueue={runQueue}
      sortedQueue={sortedQueue}
      queueGroups={queueGroups}
      queueExplanation={queueExplanation}
      expandedQueueItems={expandedQueueItems}
      toggleQueueDetails={toggleQueueDetails}
      queueHighlightKey={queueHighlightKey}
      executionResults={executionResults}
      approvalResults={approvalResults}
      executingCandidate={executingCandidate}
      approvingCandidate={approvingCandidate}
      onToggleQueueFocusPreset={toggleQueueFocusPreset}
      onResetQueueFilters={resetQueueFilters}
      onResetQueueView={resetQueueView}
      onBackToQueue={handleBackToQueue}
      onManualExecution={handleManualExecution}
      onApproveCandidate={handleApproveCandidate}
      onQueueClusterJump={handleQueueClusterJump}
      onQueueExecutionJump={handleQueueExecutionJump}
      buildCandidateKey={buildCandidateKey}
      findExecutionHistoryEntry={findExecutionHistoryEntry}
      isManualExecutionAllowed={isManualExecutionAllowed}
      getNotRunnableExplanation={getNotRunnableExplanation}
      getAlertmanagerProvenanceSubtext={getAlertmanagerProvenanceSubtext}
      formatAlertmanagerProvenance={formatAlertmanagerProvenance}
      getFeedbackAdaptationProvenanceSubtext={getFeedbackAdaptationProvenanceSubtext}
      formatFeedbackAdaptationProvenance={formatFeedbackAdaptationProvenance}
      getAlertmanagerPromotionSubtext={getAlertmanagerPromotionSubtext}
      formatAlertmanagerPromotion={formatAlertmanagerPromotion}
      onRefresh={refresh}
    />
      <section className="panel" id="fleet">
        <div className="section-head">
          <div>
            <h2>Fleet overview</h2>
            <p className="muted">Top problem: {fleet.topProblem.detail}</p>
          </div>
          <div className="status-badges">
            {fleet.fleetStatus.ratingCounts.map((entry) => (
              <span key={entry.rating} className={statusClass(entry.rating)}>
                {entry.rating} · {entry.count}
              </span>
            ))}
          </div>
        </div>
        <div className="fleet-metrics">
          <article>
            <p className="eyebrow">Pending proposals</p>
            <strong>{fleet.proposalSummary.pending}</strong>
          </article>
          <article>
            <p className="eyebrow">Total proposals</p>
            <strong>{fleet.proposalSummary.total}</strong>
          </article>
        </div>
        <div className="fleet-table">
          <table>
            <thead>
              <tr>
                <th>Cluster</th>
                <th>Rating</th>
                <th>Latest run</th>
                <th>Trigger</th>
                <th>Drilldown</th>
              </tr>
            </thead>
            <tbody>
              {fleet.clusters.map((cluster) => {
                const isSelected = cluster.label === selectedClusterLabel;
                const isFleetRowHighlighted = cluster.label === highlightedClusterLabel;
                const clusterRowFresh = !isStaleTimestamp(cluster.latestRunTimestamp);
                const clusterRowRecency = relativeRecency(cluster.latestRunTimestamp);
                return (
                  <tr
                    key={cluster.label}
                    className={
                      [
                        isSelected ? "row-selected" : null,
                        isFleetRowHighlighted ? "highlighted-row" : null,
                      ]
                        .filter(Boolean)
                        .join(" ") || undefined
                    }
                    data-highlighted={isFleetRowHighlighted ? "true" : undefined}
                    onClick={() => handleClusterSelection(cluster.label)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        handleClusterSelection(cluster.label);
                      }
                    }}
                    tabIndex={0}
                  >
                    <td>
                      <strong>{cluster.label}</strong>
                      <p className="small compact">{cluster.context}</p>
                      <p className="tiny compact">
                        {cluster.clusterClass}/{cluster.clusterRole} · {cluster.baselineCohort}
                      </p>
                    </td>
                    <td>
                      <span className={statusClass(cluster.healthRating)}>{cluster.healthRating}</span>
                    </td>
                    <td>
                      <span className={`recency-pill ${clusterRowFresh ? "fresh" : "stale"}`}>
                        {clusterRowRecency}
                      </span>
                      <p className="small compact">{formatTimestamp(cluster.latestRunTimestamp)}</p>
                    </td>
                    <td>
                      <p className="small">{cluster.topTriggerReason || "Awaiting trigger"}</p>
                    </td>
                    <td>
                      <span className="small">
                        {cluster.drilldownAvailable ? "Ready" : "Missing"}
                      </span>
                      <p className="small compact">{cluster.drilldownTimestamp || "pending"}</p>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <ClusterDetailSection
        clusterDetail={clusterDetail}
        selectedClusterLabel={selectedClusterLabel}
        selectedCluster={selectedCluster}
        fleet={fleet}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        clusterDetailExpanded={clusterDetailExpanded}
        setClusterDetailExpanded={setClusterDetailExpanded}
        highlightedClusterLabel={highlightedClusterLabel}
        clusterTriggerReason={clusterTriggerReason}
        drilldownSummary={drilldownSummary}
        recencyTimestamp={recencyTimestamp}
        clusterFresh={clusterFresh}
        clusterRecency={clusterRecency}
        handleClusterSelection={handleClusterSelection}
        artifactUrl={artifactUrl}
        formatTimestamp={formatTimestamp}
        statusClass={statusClass}
        nextCheckPlanSectionProps={{
          planCandidates,
          orphanedApprovals,
          planArtifactLink,
          planSummaryText,
          planCandidateCountLabel,
          planStatusText,
          outcomeSummary,
          selectedClusterLabel,
          executionResults,
          approvalResults,
          executingCandidate,
          approvingCandidate,
          handleApproveCandidate,
          handleManualExecution,
          onRefresh: refresh,
          buildCandidateKey,
          isManualExecutionAllowed,
          artifactUrl,
          relativeRecency,
        }}
      />
    {/* Workflow Lane: Improve the System */}
    <div className="workflow-lane-header">
      <div className="workflow-lane-label">
        <span className="workflow-lane-icon">📈</span>
        <span className="workflow-lane-title">{WORKFLOW_LANES.improve.label}</span>
      </div>
      <p className="workflow-lane-description muted small">{WORKFLOW_LANES.improve.description}</p>
    </div>
      <section className="panel" id="proposals">
        <div className="section-head">
          <div>
            <p className="eyebrow">Actionable findings</p>
            <h2>Action proposals</h2>
            <p className="muted small">Findings surfaced for triage; actionable improvements for the system.</p>
          </div>
        </div>
        <div className="proposal-controls">
          <label>
            Status
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              {statusOptions.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </label>
          <label>
            Sort
            <select value={sortKey} onChange={(event) => setSortKey(event.target.value as SortKey)}>
              <option value="proposalId">Proposal ID</option>
              <option value="confidence">Confidence</option>
              <option value="status">Status</option>
            </select>
          </label>
          <label>
            Search
            <input
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              placeholder="Target or rationale"
            />
          </label>
        </div>
        <ProposalList
          proposals={proposals.proposals}
          filter={statusFilter}
          sortKey={sortKey}
          searchText={searchText}
          expanded={expandedProposals}
          toggle={handleToggleProposal}
        />
      </section>
      <section className="panel" id="notifications">
        <div className="section-head">
          <h2>Notification history</h2>
          <p className="small">Filtering applies to the entire retained archive.</p>
        </div>
        <NotificationHistoryTable />
      </section>
      <LLMPolicyPanel policy={run.llmPolicy} />
      <LLMActivityPanel activity={run.llmActivity} />
    </div>
  );
};

export default App;
