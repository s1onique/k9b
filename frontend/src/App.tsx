import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import utc from "dayjs/plugin/utc";
import {
  approveNextCheckCandidate,
  executeNextCheckCandidate,
  fetchClusterDetail,
  fetchFleet,
  fetchNotifications,
  fetchProposals,
  fetchRun,
  fetchRunsList,
  promoteDeterministicNextCheck,
  runBatchExecution,
  submitUsefulnessFeedback,
} from "./api";
import type {
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
  ReviewEnrichmentStatus,
  RunPayload,
  RunsListEntry,
  RunsListPayload,
  DeterministicNextCheckSummary,
  NextCheckApprovalResponse,
  DeterministicNextCheckPromotionRequest,
} from "./types";
import "./index.css";

dayjs.extend(relativeTime);
dayjs.extend(utc);

type SortKey = "proposalId" | "confidence" | "status";

const confidenceWeight = (value: string) => {
  const tier = value.toLowerCase();
  const order = ["critical", "high", "medium", "low"];
  const idx = order.indexOf(tier);
  return idx === -1 ? order.length : idx;
};

const truncateText = (value: string, length = 160) => {
  if (value.length <= length) {
    return value;
  }
  return `${value.slice(0, length).trim()}…`;
};

const FRESHNESS_THRESHOLD_MINUTES = 10;
const relativeRecency = (timestamp: string) => dayjs(timestamp).fromNow();
const isStaleTimestamp = (timestamp: string) =>
  dayjs().diff(timestamp, "minute") >= FRESHNESS_THRESHOLD_MINUTES;

const statusClass = (value: string) => {
  const normalized = value.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
  return `status-pill status-pill-${normalized}`;
};

const formatTimestamp = (value: string) => dayjs.utc(value).format("MMM D, YYYY HH:mm [UTC]");

const formatDuration = (value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) {
    return "—";
  }
  const seconds = Math.max(0, Math.round(value));
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder === 0 ? `${minutes}m` : `${minutes}m ${remainder}s`;
};

const formatLatency = (value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) {
    return "—";
  }
  return `${Math.round(value)}ms`;
};

const DETERMINISTIC_WORKSTREAM_ORDER = ["incident", "evidence", "drift"] as const;
const DETERMINISTIC_WORKSTREAM_LABELS: Record<string, string> = {
  incident: "Firefight now",
  evidence: "Evidence gathering",
  drift: "Drift / toil follow-up",
};
const DETERMINISTIC_WORKSTREAM_DESCRIPTIONS: Record<string, string> = {
  incident: "Focus on the current degraded symptom",
  evidence: "Collect supporting telemetry and context",
  drift: "Log drift, parity, and toil follow-up",
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
const INCIDENT_PREVIEW_LIMIT = 3;

const FAILURE_FOLLOW_UP_LABELS: Record<string, string> = {
  "timed-out": "Timed out",
  "command-unavailable": "Command unavailable",
  "context-unavailable": "Context unavailable",
  "command-failed": "Command failed",
  "blocked-by-gating": "Blocked",
  "approval-missing-or-stale": "Approval needed",
  "unknown-failure": "Action needed",
};

const RESULT_FOLLOW_UP_LABELS: Record<string, string> = {
  "useful-signal": "Useful signal",
  "empty-result": "Empty result",
  "noisy-result": "Noisy result",
  "inconclusive": "Inconclusive",
  "partial-result": "Partial output",
};

type FailureFollowUpProps = {
  failureClass?: string | null;
  failureSummary?: string | null;
  suggestedNextOperatorMove?: string | null;
};

type InterpretationBlockProps = {
  badgeLabel: string;
  badgeClass?: string;
  summary?: string | null;
  suggestedNextOperatorMove?: string | null;
};

const InterpretationBlock = ({
  badgeLabel,
  badgeClass,
  summary,
  suggestedNextOperatorMove,
}: InterpretationBlockProps) => (
  <div className="follow-up-block">
    <span className={`follow-up-badge ${badgeClass ?? ""}`.trim()}>{badgeLabel}</span>
    {summary ? <p className="follow-up-summary">{summary}</p> : null}
    {suggestedNextOperatorMove ? (
      <p className="follow-up-action">
        <strong>Next step:</strong> {suggestedNextOperatorMove}
      </p>
    ) : null}
  </div>
);

const FailureFollowUpBlock = ({
  failureClass,
  failureSummary,
  suggestedNextOperatorMove,
}: FailureFollowUpProps) => {
  if (!failureClass) {
    return null;
  }
  const badgeLabel = FAILURE_FOLLOW_UP_LABELS[failureClass] ?? failureClass;
  return (
    <InterpretationBlock
      badgeLabel={badgeLabel}
      badgeClass={`follow-up-badge-${failureClass}`}
      summary={failureSummary}
      suggestedNextOperatorMove={suggestedNextOperatorMove}
    />
  );
};

const ResultInterpretationBlock = ({
  resultClass,
  resultSummary,
  suggestedNextOperatorMove,
}: {
  resultClass?: string | null;
  resultSummary?: string | null;
  suggestedNextOperatorMove?: string | null;
}) => {
  if (!resultClass) {
    return null;
  }
  const badgeLabel = RESULT_FOLLOW_UP_LABELS[resultClass] ?? resultClass;
  return (
    <InterpretationBlock
      badgeLabel={badgeLabel}
      badgeClass={`follow-up-badge-${resultClass}`}
      summary={resultSummary}
      suggestedNextOperatorMove={suggestedNextOperatorMove}
    />
  );
};

const NAVIGATION_HIGHLIGHT_DURATION_MS = 2200;

const NOTIFICATIONS_PER_PAGE = 50;

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

const artifactUrl = (path: string | null) => {
  if (!path) {
    return null;
  }
  return `/artifact?path=${encodeURIComponent(path)}`;
};

const buildExecutionEntryKey = (entry: NextCheckExecutionHistoryEntry) =>
  `${entry.clusterLabel ?? "global"}::${entry.candidateDescription ?? ""}::${entry.timestamp ?? ""}::${
    entry.artifactPath ?? ""
  }`;

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

const EvidenceDetails = ({
  title,
  entries,
}: {
  title: string;
  entries: NotificationDetail[];
}) => {
  if (!entries.length) {
    return null;
  }
  return (
    <details className="evidence-details">
      <summary>
        {title} · {entries.length} evidence point{entries.length === 1 ? "" : "s"}
      </summary>
      <ul>
        {entries.map((entry) => (
          <li key={`${entry.label}-${entry.value}`}>
            <strong>{entry.label}:</strong> {entry.value}
          </li>
        ))}
      </ul>
    </details>
  );
};

const normalizeFilterValue = (value: string | null | undefined) =>
  value && value.trim() ? value : "unknown";

const LLMActivityPanel = ({
  activity,
}: {
  activity: RunPayload["llmActivity"] | undefined;
}) => {
  const entries = activity?.entries ?? [];
  const [statusFilter, setStatusFilter] = useState("all");
  const [providerFilter, setProviderFilter] = useState("all");
  const [purposeFilter, setPurposeFilter] = useState("all");
  const [clusterFilter, setClusterFilter] = useState("all");

  const statusOptions = useMemo(() => {
    const values = new Set<string>();
    entries.forEach((entry) => values.add(normalizeFilterValue(entry.status)));
    return ["all", ...Array.from(values)];
  }, [entries]);

  const providerOptions = useMemo(() => {
    const values = new Set<string>();
    entries.forEach((entry) => values.add(normalizeFilterValue(entry.provider)));
    return ["all", ...Array.from(values)];
  }, [entries]);

  const purposeOptions = useMemo(() => {
    const values = new Set<string>();
    entries.forEach((entry) => values.add(normalizeFilterValue(entry.purpose)));
    return ["all", ...Array.from(values)];
  }, [entries]);

  const clusterOptions = useMemo(() => {
    const values = new Set<string>();
    entries.forEach((entry) => values.add(normalizeFilterValue(entry.clusterLabel)));
    return ["all", ...Array.from(values)];
  }, [entries]);

  const filteredEntries = useMemo(() => {
    return entries.filter((entry) => {
      const statusValue = normalizeFilterValue(entry.status);
      const providerValue = normalizeFilterValue(entry.provider);
      const purposeValue = normalizeFilterValue(entry.purpose);
      const clusterValue = normalizeFilterValue(entry.clusterLabel);
      return (
        (statusFilter === "all" || statusValue === statusFilter) &&
        (providerFilter === "all" || providerValue === providerFilter) &&
        (purposeFilter === "all" || purposeValue === purposeFilter) &&
        (clusterFilter === "all" || clusterValue === clusterFilter)
      );
    });
  }, [entries, statusFilter, providerFilter, purposeFilter, clusterFilter]);

  if (!activity) {
    return <p className="muted">LLM activity data is unavailable.</p>;
  }

  const summary = activity.summary;
  const displayCount = filteredEntries.length;
  const availableCount = entries.length;

  return (
    <section className="panel llm-activity-panel" id="llm-activity">
      <div className="section-head">
        <div>
          <h2>LLM activity</h2>
          <p className="muted small">Provider-assisted provenance from retained artifacts.</p>
        </div>
        <p className="muted small">
          Retained entries: {summary.retainedEntries} · Showing {displayCount} of {availableCount}
        </p>
      </div>
      <div className="llm-activity-filters">
        <label>
          Status
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            {statusOptions.map((option) => (
              <option key={option} value={option}>
                {option === "unknown" ? "Unknown" : option}
              </option>
            ))}
          </select>
        </label>
        <label>
          Provider
          <select value={providerFilter} onChange={(event) => setProviderFilter(event.target.value)}>
            {providerOptions.map((option) => (
              <option key={option} value={option}>
                {option === "unknown" ? "Unknown" : option}
              </option>
            ))}
          </select>
        </label>
        <label>
          Purpose
          <select value={purposeFilter} onChange={(event) => setPurposeFilter(event.target.value)}>
            {purposeOptions.map((option) => (
              <option key={option} value={option}>
                {option === "unknown" ? "Unknown" : option}
              </option>
            ))}
          </select>
        </label>
        <label>
          Cluster
          <select value={clusterFilter} onChange={(event) => setClusterFilter(event.target.value)}>
            {clusterOptions.map((option) => (
              <option key={option} value={option}>
                {option === "unknown" ? "Unknown" : option}
              </option>
            ))}
          </select>
        </label>
      </div>
      {displayCount ? (
        <div className="llm-activity-table-wrapper">
          <table className="llm-activity-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Cluster / Run</th>
                <th>Provider</th>
                <th>Purpose</th>
                <th>Status</th>
                <th>Latency</th>
                <th>Artifact</th>
                <th>Summary</th>
              </tr>
            </thead>
            <tbody>
              {filteredEntries.map((entry, index) => {
                const artifactLink = entry.artifactPath ? artifactUrl(entry.artifactPath) : null;
                const detailText = entry.summary || entry.errorSummary || entry.skipReason || "—";
                return (
                  <tr key={`${entry.timestamp}-${entry.runId}-${index}`}>
                    <td>
                      <strong>{entry.timestamp ? formatTimestamp(entry.timestamp) : "—"}</strong>
                      {entry.timestamp ? (
                        <p className="tiny compact">{relativeRecency(entry.timestamp)}</p>
                      ) : null}
                    </td>
                    <td>
                      <strong>{entry.clusterLabel || "—"}</strong>
                      {entry.runLabel ? (
                        <p className="tiny compact">Run {entry.runLabel}</p>
                      ) : null}
                      {entry.runId ? (
                        <p className="tiny compact">ID {entry.runId}</p>
                      ) : null}
                    </td>
                    <td>
                      <strong>{entry.provider || "—"}</strong>
                      {entry.toolName ? (
                        <p className="tiny compact">Tool {entry.toolName}</p>
                      ) : null}
                    </td>
                    <td>{entry.purpose || "—"}</td>
                    <td>
                      <span className={statusClass(entry.status || "unknown")}>
                        {entry.status || "unknown"}
                      </span>
                    </td>
                    <td>{formatLatency(entry.latencyMs)}</td>
                    <td>
                      {artifactLink ? (
                        <a className="artifact-link" href={artifactLink} target="_blank" rel="noreferrer">
                          View
                        </a>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      <p className="tiny">{truncateText(detailText, 120)}</p>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">No retained LLM activity matches the current filters.</p>
      )}
    </section>
  );
};

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

const ReviewEnrichmentList = ({
  title,
  entries,
}: {
  title: string;
  entries: string[];
}) => {
  if (!entries.length) {
    return null;
  }
  return (
    <div className="review-enrichment-item">
      <p className="tiny">{title}</p>
      <ul>
        {entries.map((entry) => (
          <li key={entry}>{entry}</li>
        ))}
      </ul>
    </div>
  );
};

const DiagnosticPackReviewList = ({
  title,
  entries,
}: {
  title: string;
  entries: string[];
}) => {
  if (!entries.length) {
    return null;
  }
  const previewLimit = 3;
  const hasMore = entries.length > previewLimit;
  const visible = entries.slice(0, previewLimit);
  return (
    <div className="diagnostic-pack-review-list">
      <p className="tiny">
        {title} · {entries.length}
      </p>
      <ul>
        {visible.map((entry) => (
          <li key={entry}>{entry}</li>
        ))}
        {hasMore && <li className="muted">…and {entries.length - previewLimit} more</li>}
      </ul>
    </div>
  );
};

const reviewEnrichmentStatusMessage = (status?: ReviewEnrichmentStatus) => {
  if (!status) {
    return "Provider-assisted review enrichment is not configured for this run.";
  }
  const reason = status.reason;
  switch (status.status) {
    case "policy-disabled":
      return reason || "Review enrichment is disabled in the current configuration.";
    case "provider-missing":
      return reason || "No provider is configured for review enrichment.";
    case "adapter-unavailable":
      return reason || "The configured adapter is not registered for review enrichment.";
    case "awaiting-next-run":
      return (
        reason || "Review enrichment is enabled now, but the latest recorded run predates this setting."
      );
    case "not-attempted":
      return (
        reason || "Review enrichment was enabled for this run, but no artifact was recorded."
      );
    case "unknown":
      return reason || "Review enrichment status cannot be determined for this run.";
    default:
      return (
        reason || "Review enrichment will run once the deterministic review artifact is available."
      );
  }
};

type ReviewEnrichmentPanelProps = {
  reviewEnrichment: RunPayload["reviewEnrichment"] | undefined;
  reviewEnrichmentStatus: RunPayload["reviewEnrichmentStatus"] | undefined;
  nextCheckPlan: RunPayload["nextCheckPlan"] | undefined;
  onNavigateToQueue?: () => void;
  onFocusQueueReview?: () => void;
};

const ReviewEnrichmentPanel = ({
  reviewEnrichment,
  reviewEnrichmentStatus,
  nextCheckPlan,
  onNavigateToQueue,
  onFocusQueueReview,
}: ReviewEnrichmentPanelProps) => {
  const status =
    reviewEnrichment?.status || reviewEnrichmentStatus?.status || "pending";
  const artifactLink = reviewEnrichment?.artifactPath
    ? artifactUrl(reviewEnrichment.artifactPath)
    : null;
  // Check if this enrichment led to planning - match by artifact path
  const enrichmentArtifactPath = reviewEnrichment?.artifactPath;
  const linkedPlan = nextCheckPlan?.enrichmentArtifactPath === enrichmentArtifactPath
    ? nextCheckPlan
    : null;
  const planCandidates = linkedPlan?.candidates ?? [];
  const planCandidateCount = linkedPlan?.candidateCount ?? planCandidates.length;
  const topPlanCandidates = planCandidates.slice(0, 3);
  const hasLinkedPlan = Boolean(linkedPlan) && planCandidateCount > 0;
  const runConfigDescription = () => {
    if (!reviewEnrichmentStatus) {
      return null;
    }
    if (reviewEnrichmentStatus.runEnabled === null) {
      return "Run metadata unavailable";
    }
    if (!reviewEnrichmentStatus.runEnabled) {
      return "Run configuration disabled review enrichment";
    }
    const runProvider = reviewEnrichmentStatus.runProvider
      ? ` (${reviewEnrichmentStatus.runProvider})`
      : "";
    return `Run configuration enabled${runProvider}`;
  };
  const providerLabel =
    reviewEnrichmentStatus?.provider ?? reviewEnrichmentStatus?.runProvider;
  const providerDisplay = providerLabel ? `Provider ${providerLabel}` : "Provider unspecified";
  return (
    <section className="panel review-enrichment" id="review-enrichment">
      <div className="section-head">
        <div>
          <p className="eyebrow">Review enrichment</p>
          <h2>Provider-assisted advisory</h2>
        </div>
        <span className={`status-pill ${statusClass(status)}`}>{status}</span>
      </div>
      {reviewEnrichment ? (
        <div className="review-enrichment-body">
          <p className="small">
            {reviewEnrichment.provider
              ? `Provider ${reviewEnrichment.provider}`
              : "Provider unspecified"}{' '}
            ·{' '}
            {reviewEnrichment.timestamp
              ? formatTimestamp(reviewEnrichment.timestamp)
              : "Timestamp unavailable"}
          </p>
          <p className="review-enrichment-summary">
            {reviewEnrichment.summary || "No advisory summary was generated."}
          </p>
          <div className="review-enrichment-grid">
            <ReviewEnrichmentList title="Triage order" entries={reviewEnrichment.triageOrder} />
            <ReviewEnrichmentList title="Top concerns" entries={reviewEnrichment.topConcerns} />
            <ReviewEnrichmentList title="Evidence gaps" entries={reviewEnrichment.evidenceGaps} />
            <ReviewEnrichmentList title="Next checks" entries={reviewEnrichment.nextChecks} />
            <ReviewEnrichmentList title="Focus notes" entries={reviewEnrichment.focusNotes} />
          </div>
          {reviewEnrichment.errorSummary ? (
            <p className="small muted">Error: {reviewEnrichment.errorSummary}</p>
          ) : null}
          {reviewEnrichment.skipReason ? (
            <p className="small muted">Skipped because {reviewEnrichment.skipReason}</p>
          ) : null}
          {artifactLink ? (
            <a className="link" href={artifactLink} target="_blank" rel="noreferrer">
              View enrichment artifact
            </a>
          ) : null}
          {hasLinkedPlan && (
            <div className="review-enrichment-planning-summary">
              <p className="eyebrow">Planning outcomes</p>
              <p className="small">
                {planCandidateCount} candidate{planCandidateCount === 1 ? "" : "s"} generated from this enrichment
              </p>
              <ul className="review-enrichment-plan-preview">
                {topPlanCandidates.map((candidate, idx) => (
                  <li key={idx}>
                    <span className="tiny">{candidate.description}</span>
                  </li>
                ))}
              </ul>
              {planCandidateCount > 3 && (
                <p className="muted tiny">…and {planCandidateCount - 3} more</p>
              )}
              <button
                type="button"
                className="link"
                onClick={() => {
                  if (onFocusQueueReview) {
                    onFocusQueueReview();
                  }
                  if (onNavigateToQueue) {
                    onNavigateToQueue();
                  }
                }}
              >
                View full queue
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="review-enrichment-body">
          <p className="small">
            {reviewEnrichmentStatusMessage(reviewEnrichmentStatus)}
          </p>
          <p className="small muted">
            {providerDisplay}
            {runConfigDescription() ? ` · ${runConfigDescription()}` : ""}
          </p>
        </div>
      )}
    </section>
  );
};

const RunDiagnosticPackPanel = ({
  diagnosticPack,
}: {
  diagnosticPack: RunPayload["diagnosticPack"] | undefined;
}) => {
  if (!diagnosticPack || !diagnosticPack.path) {
    return null;
  }
  const artifactLink = artifactUrl(diagnosticPack.path);
  if (!artifactLink) {
    return null;
  }
  const reviewBundleLink = diagnosticPack.reviewBundlePath
    ? artifactUrl(diagnosticPack.reviewBundlePath)
    : null;
  const reviewInput14bLink = diagnosticPack.reviewInput14bPath
    ? artifactUrl(diagnosticPack.reviewInput14bPath)
    : null;
  return (
    <section className="panel diagnostic-pack-download" id="diagnostic-pack-download">
      <div className="section-head">
        <div>
          <p className="eyebrow">Diagnostic pack</p>
          <h2>Run diagnostic package archive</h2>
        </div>
      </div>
      {diagnosticPack.label ? (
        <p className="muted tiny">Label: {diagnosticPack.label}</p>
      ) : null}
      <p className="muted tiny">
        {diagnosticPack.timestamp
          ? formatTimestamp(diagnosticPack.timestamp)
          : "Timestamp unavailable"}
      </p>
      <a className="link" href={artifactLink} target="_blank" rel="noreferrer">
        Download diagnostic pack
      </a>
      {reviewBundleLink && (
        <>
          <br />
          <a className="link" href={reviewBundleLink} target="_blank" rel="noreferrer">
            Review bundle
          </a>
        </>
      )}
      {reviewInput14bLink && (
        <>
          <br />
          <a className="link" href={reviewInput14bLink} target="_blank" rel="noreferrer">
            Review input (14b)
          </a>
        </>
      )}
    </section>
  );
};

const DiagnosticPackReviewPanel = ({
  review,
}: {
  review: RunPayload["diagnosticPackReview"] | undefined;
}) => {
  if (!review) {
    return null;
  }
  const artifactLink = review.artifactPath ? artifactUrl(review.artifactPath) : null;
  const providerStatus = review.providerStatus || "Status unavailable";
  const hasProviderDetails = review.providerSummary || review.providerErrorSummary || review.providerSkipReason;
  return (
    <section className="panel diagnostic-pack-review" id="diagnostic-pack-review">
      <div className="section-head">
        <div>
          <p className="eyebrow">Diagnostic pack review</p>
          <h2>Automated review insights</h2>
        </div>
        <span className={`status-pill ${statusClass(providerStatus)}`}>
          {providerStatus}
        </span>
      </div>
      <p className="muted tiny">
        {review.timestamp ? formatTimestamp(review.timestamp) : "Timestamp unavailable"}
      </p>
      {review.summary ? <p className="diagnostic-pack-summary">{review.summary}</p> : null}
      {review.confidence ? (
        <p className="muted tiny">Confidence: {review.confidence}</p>
      ) : null}
      {hasProviderDetails ? (
        <div className="diagnostic-pack-provider">
          {review.providerSummary ? (
            <p className="muted small">{review.providerSummary}</p>
          ) : null}
          {review.providerErrorSummary ? (
            <p className="muted small">Error: {review.providerErrorSummary}</p>
          ) : null}
          {review.providerSkipReason ? (
            <p className="muted small">Skipped because {review.providerSkipReason}</p>
          ) : null}
        </div>
      ) : null}
      {review.driftMisprioritized ? (
        <p className="muted tiny">
          Provider flagged suspected drift misprioritization. Review the assigned check order.
        </p>
      ) : null}
      <div className="diagnostic-pack-review-grid">
        <DiagnosticPackReviewList title="Major disagreements" entries={review.majorDisagreements} />
        <DiagnosticPackReviewList title="Missing checks" entries={review.missingChecks} />
        <DiagnosticPackReviewList title="Ranking issues" entries={review.rankingIssues} />
        <DiagnosticPackReviewList
          title="Recommended next actions"
          entries={review.recommendedNextActions}
        />
      </div>
      {artifactLink ? (
        <a className="link" href={artifactLink} target="_blank" rel="noreferrer">
          View diagnostic pack review artifact
        </a>
      ) : null}
    </section>
  );
};

const ExecutionLine = ({
  title,
  data,
}: {
  title: string;
  data: ProviderExecutionBranch | undefined | null;
}) => {
  if (!data) {
    return (
      <div className="provider-execution-line">
        <strong>{title}</strong>
        <p className="small muted">Execution data unavailable for this branch.</p>
      </div>
    );
  }
  const segments = [
    data.eligible != null && `eligible ${data.eligible}`,
    `attempted ${data.attempted}`,
    `ok ${data.succeeded}`,
    `failed ${data.failed}`,
    `skipped ${data.skipped}`,
    data.unattempted != null && `unattempted ${data.unattempted}`,
    data.budgetLimited != null && data.budgetLimited > 0 && `budget-limited ${data.budgetLimited}`,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <div className="provider-execution-line">
      <strong>{title}</strong>
      <p className="muted tiny provider-execution-summary">{segments || "No counts yet."}</p>
      {data.notes ? <p className="muted tiny provider-execution-note">{data.notes}</p> : null}
    </div>
  );
};

const ProviderExecutionPanel = ({
  execution,
}: {
  execution: ProviderExecution | undefined | null;
}) => (
  <section className="panel provider-execution" id="provider-execution">
    <div className="section-head">
      <div>
        <p className="eyebrow">Provider execution</p>
        <h2>Provider-assisted branches</h2>
      </div>
      <p className="muted small">
        Counts derived from deterministic artifacts and run-config provenance for each branch.
      </p>
    </div>
    <div className="provider-execution-body">
      <ExecutionLine title="Auto drilldown" data={execution?.autoDrilldown} />
      <ExecutionLine title="Review enrichment" data={execution?.reviewEnrichment} />
    </div>
  </section>
);

// Usefulness feedback constants
const USEFULNESS_CLASSES = [
  { value: "useful", label: "Useful" },
  { value: "partial", label: "Partial" },
  { value: "noisy", label: "Noisy" },
  { value: "empty", label: "Empty" },
] as const;

// Execution history filter types
// Filters for execution outcome/status: success, failure, timeout
export type ExecutionOutcomeFilter = "all" | "success" | "failure" | "timeout";

// Filters for usefulness/review classification: useful, partial, noisy, empty, unreviewed
export type UsefulnessReviewFilter = "all" | "useful" | "partial" | "noisy" | "empty" | "unreviewed";

const EXECUTION_OUTCOME_FILTER_OPTIONS: { label: string; value: ExecutionOutcomeFilter }[] = [
  { label: "All outcomes", value: "all" },
  { label: "Success", value: "success" },
  { label: "Failure", value: "failure" },
  { label: "Timeout", value: "timeout" },
];

const USEFULNESS_REVIEW_FILTER_OPTIONS: { label: string; value: UsefulnessReviewFilter }[] = [
  { label: "Any classification", value: "all" },
  { label: "Useful", value: "useful" },
  { label: "Partial", value: "partial" },
  { label: "Noisy", value: "noisy" },
  { label: "Empty", value: "empty" },
  { label: "Unreviewed", value: "unreviewed" },
];

// Execution history filter state
export const EXECUTION_HISTORY_FILTER_STORAGE_KEY = "dashboard-execution-history-filter";
const DEFAULT_EXECUTION_HISTORY_FILTER: ExecutionHistoryFilterState = {
  outcomeFilter: "all",
  usefulnessFilter: "all",
  commandFamilyFilter: "all",
  clusterFilter: "all",
};

export type ExecutionHistoryFilterState = {
  outcomeFilter: ExecutionOutcomeFilter;
  usefulnessFilter: UsefulnessReviewFilter;
  commandFamilyFilter: string;
  clusterFilter: string;
};

const EXECUTION_OUTCOME_FILTER_VALUES: ExecutionOutcomeFilter[] = ["all", "success", "failure", "timeout"];
const USEFULNESS_REVIEW_FILTER_VALUES: UsefulnessReviewFilter[] = ["all", "useful", "partial", "noisy", "empty", "unreviewed"];

const isExecutionOutcomeFilterValue = (value: unknown): value is ExecutionOutcomeFilter =>
  typeof value === "string" && EXECUTION_OUTCOME_FILTER_VALUES.includes(value as ExecutionOutcomeFilter);

const isUsefulnessReviewFilterValue = (value: unknown): value is UsefulnessReviewFilter =>
  typeof value === "string" && USEFULNESS_REVIEW_FILTER_VALUES.includes(value as UsefulnessReviewFilter);

const readStoredExecutionHistoryFilter = (): ExecutionHistoryFilterState => {
  if (typeof window === "undefined") {
    return DEFAULT_EXECUTION_HISTORY_FILTER;
  }
  const stored = window.localStorage.getItem(EXECUTION_HISTORY_FILTER_STORAGE_KEY);
  if (!stored) {
    return DEFAULT_EXECUTION_HISTORY_FILTER;
  }
  try {
    const parsed = JSON.parse(stored);
    if (!parsed || typeof parsed !== "object") {
      return DEFAULT_EXECUTION_HISTORY_FILTER;
    }
    const candidate = parsed as Record<string, unknown>;
    return {
      outcomeFilter: isExecutionOutcomeFilterValue(candidate.outcomeFilter)
        ? candidate.outcomeFilter
        : DEFAULT_EXECUTION_HISTORY_FILTER.outcomeFilter,
      usefulnessFilter: isUsefulnessReviewFilterValue(candidate.usefulnessFilter)
        ? candidate.usefulnessFilter
        : DEFAULT_EXECUTION_HISTORY_FILTER.usefulnessFilter,
      commandFamilyFilter: typeof candidate.commandFamilyFilter === "string"
        ? candidate.commandFamilyFilter
        : DEFAULT_EXECUTION_HISTORY_FILTER.commandFamilyFilter,
      clusterFilter: typeof candidate.clusterFilter === "string"
        ? candidate.clusterFilter
        : DEFAULT_EXECUTION_HISTORY_FILTER.clusterFilter,
    };
  } catch {
    return DEFAULT_EXECUTION_HISTORY_FILTER;
  }
};

const persistExecutionHistoryFilter = (filter: ExecutionHistoryFilterState) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(EXECUTION_HISTORY_FILTER_STORAGE_KEY, JSON.stringify(filter));
};

// Filter execution history entries based on current filter state
export const filterExecutionHistory = (
  entries: NextCheckExecutionHistoryEntry[],
  filter: ExecutionHistoryFilterState,
): NextCheckExecutionHistoryEntry[] => {
  return entries.filter((entry) => {
    // Outcome filter: success, failure, timeout
    if (filter.outcomeFilter !== "all") {
      if (filter.outcomeFilter === "timeout") {
        if (!entry.timedOut) return false;
      } else if (filter.outcomeFilter === "failure") {
        if (entry.status !== "failed" && entry.status !== "error") return false;
        if (entry.timedOut) return false; // timeout is its own category
      } else if (filter.outcomeFilter === "success") {
        if (entry.status !== "success" && entry.status !== "ok") return false;
        if (entry.timedOut) return false; // timed out is its own category
      }
    }

    // Usefulness/review filter
    if (filter.usefulnessFilter !== "all") {
      if (filter.usefulnessFilter === "unreviewed") {
        if (entry.usefulnessClass != null) return false;
      } else {
        if (entry.usefulnessClass !== filter.usefulnessFilter) return false;
      }
    }

    // Command family filter
    if (filter.commandFamilyFilter !== "all") {
      if (entry.commandFamily !== filter.commandFamilyFilter) return false;
    }

    // Cluster filter
    if (filter.clusterFilter !== "all") {
      if (entry.clusterLabel !== filter.clusterFilter) return false;
    }

    return true;
  });
};

// Extract unique clusters from history entries
export const extractClustersFromHistory = (entries: NextCheckExecutionHistoryEntry[]): string[] => {
  const clusters = new Set<string>();
  entries.forEach((entry) => {
    if (entry.clusterLabel) {
      clusters.add(entry.clusterLabel);
    }
  });
  return Array.from(clusters).sort();
};

// Extract unique command families from history entries
export const extractCommandFamiliesFromHistory = (entries: NextCheckExecutionHistoryEntry[]): string[] => {
  const families = new Set<string>();
  entries.forEach((entry) => {
    if (entry.commandFamily) {
      families.add(entry.commandFamily);
    }
  });
  return Array.from(families).sort();
};

// Compute filter counts for execution history
export const computeExecutionHistoryFilterCounts = (
  entries: NextCheckExecutionHistoryEntry[],
): { outcome: Record<ExecutionOutcomeFilter, number>; usefulness: Record<UsefulnessReviewFilter, number> } => {
  const outcome: Record<ExecutionOutcomeFilter, number> = {
    all: entries.length,
    success: 0,
    failure: 0,
    timeout: 0,
  };
  const usefulness: Record<UsefulnessReviewFilter, number> = {
    all: entries.length,
    useful: 0,
    partial: 0,
    noisy: 0,
    empty: 0,
    unreviewed: 0,
  };

  entries.forEach((entry) => {
    // Outcome counts
    if (entry.timedOut) {
      outcome.timeout++;
    } else if (entry.status === "failed" || entry.status === "error") {
      outcome.failure++;
    } else if (entry.status === "success" || entry.status === "ok") {
      outcome.success++;
    }

    // Usefulness counts
    if (entry.usefulnessClass == null) {
      usefulness.unreviewed++;
    } else if (entry.usefulnessClass === "useful") {
      usefulness.useful++;
    } else if (entry.usefulnessClass === "partial") {
      usefulness.partial++;
    } else if (entry.usefulnessClass === "noisy") {
      usefulness.noisy++;
    } else if (entry.usefulnessClass === "empty") {
      usefulness.empty++;
    }
  });

  return { outcome, usefulness };
};

type UsefulnessFeedbackState = {
  artifactPath: string;
  isSubmitting: boolean;
  error: string | null;
  isExpanded: boolean;
};

type UsefulnessFeedbackHandler = {
  onSubmitFeedback: (artifactPath: string, usefulnessClass: string, summary: string | undefined) => Promise<void>;
};

const UsefulnessFeedbackControl = ({
  entry,
  onSubmit,
}: {
  entry: NextCheckExecutionHistoryEntry;
  onSubmit: (artifactPath: string, usefulnessClass: string, summary: string | undefined) => Promise<void>;
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedClass, setSelectedClass] = useState<"useful" | "partial" | "noisy" | "empty" | null>(null);
  const [summary, setSummary] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // If usefulness is already recorded, show it in read-only mode
  if (entry.usefulnessClass) {
    return null;
  }

  // Only show feedback control if there's an artifact path
  if (!entry.artifactPath) {
    return null;
  }

  const handleSubmit = async () => {
    if (!selectedClass || !entry.artifactPath) {
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      await onSubmit(entry.artifactPath, selectedClass, summary.trim() || undefined);
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit feedback");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (success) {
    return (
      <div className="usefulness-feedback-success">
        <span className="muted small">✓ Feedback recorded</span>
      </div>
    );
  }

  return (
    <div className="usefulness-feedback-control">
      {!isExpanded ? (
        <button
          type="button"
          className="link tiny"
          onClick={() => setIsExpanded(true)}
        >
          Rate usefulness
        </button>
      ) : (
        <div className="usefulness-feedback-form">
          <p className="tiny muted">Was this check useful?</p>
          <div className="usefulness-feedback-options">
            {USEFULNESS_CLASSES.map((cls) => (
              <label key={cls.value} className="usefulness-feedback-option">
                <input
                  type="radio"
                  name={`usefulness-${entry.artifactPath}`}
                  value={cls.value}
                  checked={selectedClass === cls.value}
                  onChange={() => setSelectedClass(cls.value as "useful" | "partial" | "noisy" | "empty")}
                />
                <span>{cls.label}</span>
              </label>
            ))}
          </div>
          <input
            type="text"
            placeholder="Optional note"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            className="usefulness-feedback-summary"
            maxLength={200}
          />
          <div className="usefulness-feedback-actions">
            <button
              type="button"
              className="button primary tiny"
              onClick={handleSubmit}
              disabled={!selectedClass || isSubmitting}
            >
              {isSubmitting ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              className="button secondary tiny"
              onClick={() => setIsExpanded(false)}
              disabled={isSubmitting}
            >
              Cancel
            </button>
          </div>
          {error && <p className="usefulness-feedback-error">{error}</p>}
        </div>
      )}
    </div>
  );
};

const ExecutionHistoryPanel = ({
  history,
  runId,
  runLabel,
  queueCandidateCount,
  highlightedKey,
  onSubmitFeedback,
  filter,
  onFilterChange,
}: {
  history: NextCheckExecutionHistoryEntry[];
  runId: string;
  runLabel: string;
  queueCandidateCount: number;
  highlightedKey: string | null;
  onSubmitFeedback?: (artifactPath: string, usefulnessClass: string, summary: string | undefined) => Promise<void>;
  filter: ExecutionHistoryFilterState;
  onFilterChange: (filter: ExecutionHistoryFilterState) => void;
}) => {
  const filteredHistory = useMemo(
    () => filterExecutionHistory(history, filter),
    [history, filter],
  );

  const clusters = useMemo(() => extractClustersFromHistory(history), [history]);
  const commandFamilies = useMemo(() => extractCommandFamiliesFromHistory(history), [history]);
  const counts = useMemo(() => computeExecutionHistoryFilterCounts(history), [history]);

  const handleOutcomeChange = (value: ExecutionOutcomeFilter) => {
    onFilterChange({ ...filter, outcomeFilter: value });
  };

  const handleUsefulnessChange = (value: UsefulnessReviewFilter) => {
    onFilterChange({ ...filter, usefulnessFilter: value });
  };

  const handleClusterChange = (value: string) => {
    onFilterChange({ ...filter, clusterFilter: value });
  };

  const handleCommandFamilyChange = (value: string) => {
    onFilterChange({ ...filter, commandFamilyFilter: value });
  };

  return (
  <section className="panel execution-history-panel" id="execution-history">
    <div className="section-head">
      <div>
        <p className="eyebrow">Execution history</p>
        <h2>Check execution review</h2>
        <p className="muted small">Checks that ran in this run; review results and signal quality. Work list candidates appear here after execution.</p>
      </div>
      <div className="execution-history-context">
        <span className="muted tiny">Run {runLabel}</span>
        <span className="muted tiny">ID {runId}</span>
        <span className="muted tiny">{history.length} executed</span>
        {queueCandidateCount > 0 && history.length === 0 && (
          <span className="muted tiny">{queueCandidateCount} in work list</span>
        )}
      </div>
    </div>
    <div className="execution-history-filters">
      <div className="filter-group">
        <label className="filter-label" htmlFor="exec-outcome-filter">Outcome:</label>
        <select
          id="exec-outcome-filter"
          className="filter-select"
          value={filter.outcomeFilter}
          onChange={(e) => handleOutcomeChange(e.target.value as ExecutionOutcomeFilter)}
        >
          {EXECUTION_OUTCOME_FILTER_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label} ({counts.outcome[opt.value]})
            </option>
          ))}
        </select>
      </div>
      <div className="filter-group">
        <label className="filter-label" htmlFor="exec-usefulness-filter">Reviewed:</label>
        <select
          id="exec-usefulness-filter"
          className="filter-select"
          value={filter.usefulnessFilter}
          onChange={(e) => handleUsefulnessChange(e.target.value as UsefulnessReviewFilter)}
        >
          {USEFULNESS_REVIEW_FILTER_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label} ({counts.usefulness[opt.value]})
            </option>
          ))}
        </select>
      </div>
      {clusters.length > 1 && (
        <div className="filter-group">
          <label className="filter-label" htmlFor="exec-cluster-filter">Cluster:</label>
          <select
            id="exec-cluster-filter"
            className="filter-select"
            value={filter.clusterFilter}
            onChange={(e) => handleClusterChange(e.target.value)}
          >
            <option value="all">All clusters</option>
            {clusters.map((cluster) => (
              <option key={cluster} value={cluster}>{cluster}</option>
            ))}
          </select>
        </div>
      )}
      {commandFamilies.length > 1 && (
        <div className="filter-group">
          <label className="filter-label" htmlFor="exec-cmd-family-filter">Command:</label>
          <select
            id="exec-cmd-family-filter"
            className="filter-select"
            value={filter.commandFamilyFilter}
            onChange={(e) => handleCommandFamilyChange(e.target.value)}
          >
            <option value="all">All commands</option>
            {commandFamilies.map((family) => (
              <option key={family} value={family}>{family}</option>
            ))}
          </select>
        </div>
      )}
      {filteredHistory.length !== history.length && (
        <span className="filter-count">
          Showing {filteredHistory.length} of {history.length}
        </span>
      )}
    </div>
    {filteredHistory.length ? (
      <div className="execution-history-grid">
        {filteredHistory.map((entry) => {
          const key = `${entry.timestamp}-${entry.artifactPath ?? entry.candidateDescription ?? ""}`;
          const badges = [
            entry.timedOut ? "Timed out" : null,
            entry.stdoutTruncated ? "stdout truncated" : null,
            entry.stderrTruncated ? "stderr truncated" : null,
          ].filter(Boolean) as string[];
          const durationSeconds = entry.durationMs != null ? entry.durationMs / 1000 : null;
          const entryKey = buildExecutionEntryKey(entry);
          const cardClasses = [
            "execution-history-card",
            highlightedKey === entryKey ? "highlight-target" : null,
          ]
            .filter(Boolean)
            .join(" ");
          return (
            <article
              className={cardClasses}
              key={key}
              data-highlighted={highlightedKey === entryKey ? "true" : undefined}
            >
              <header>
                <div>
                  <p className="tiny muted">{relativeRecency(entry.timestamp)}</p>
                  <strong>{formatTimestamp(entry.timestamp)}</strong>
                </div>
                <span className={statusClass(entry.status)}>{entry.status}</span>
              </header>
              <p className="small">
                {entry.candidateDescription || "Candidate description unavailable."}
              </p>
              <div className="execution-history-meta">
                <span>Cluster: {entry.clusterLabel || "unknown"}</span>
                <span>Command: {entry.commandFamily || "—"}</span>
                <span>Duration: {formatDuration(durationSeconds)}</span>
                {entry.candidateId && (
                  <span className="provenance-hint" title={`Candidate ID: ${entry.candidateId}`}>
                    #{entry.candidateIndex != null ? entry.candidateIndex + 1 : "?"}
                  </span>
                )}
              </div>
              {/* Provenance traceability: jump link back to work list */}
              {entry.candidateId && (
                <div className="execution-history-provenance">
                  <button
                    type="button"
                    className="provenance-jump"
                    onClick={() => {
                      // Find the corresponding work list item and highlight it
                      const queueItemKey = runQueue.find(
                        (q) => q.candidateId === entry.candidateId
                      );
                      if (queueItemKey) {
                        const key = buildCandidateKey(queueItemKey, queueItemKey.candidateIndex ?? runQueue.indexOf(queueItemKey));
                        highlightQueueCard(key);
                      }
                    }}
                    title={`View candidate ${entry.candidateId} in work list`}
                  >
                    From work list #{entry.candidateIndex != null ? entry.candidateIndex + 1 : "?"}
                  </button>
                </div>
              )}
              <div className="execution-history-badges">
                {badges.map((badge) => (
                  <span key={badge} className="execution-history-badge">
                    {badge}
                  </span>
                ))}
                {entry.outputBytesCaptured != null && (
                  <span className="execution-history-badge">
                    Captured {entry.outputBytesCaptured} bytes
                  </span>
                )}
              </div>
              <ResultInterpretationBlock
                resultClass={entry.resultClass}
                resultSummary={entry.resultSummary}
                suggestedNextOperatorMove={entry.suggestedNextOperatorMove}
              />
              <FailureFollowUpBlock
                failureClass={entry.failureClass}
                failureSummary={entry.failureSummary}
                suggestedNextOperatorMove={entry.suggestedNextOperatorMove}
              />
              {entry.usefulnessClass && (
                <div className="usefulness-indicator">
                  <span className="muted small">Usefulness: {entry.usefulnessClass}</span>
                  {entry.usefulnessSummary && (
                    <span className="muted small"> — {entry.usefulnessSummary}</span>
                  )}
                </div>
              )}
              {entry.packRefreshStatus && (
                <div className="execution-history-pack-refresh">
                  <span className={entry.packRefreshStatus === "succeeded" ? "text-success" : "text-warning"}>
                    Pack refresh: {entry.packRefreshStatus}
                  </span>
                  {entry.packRefreshWarning && (
                    <span className="muted small"> — {entry.packRefreshWarning}</span>
                  )}
                </div>
              )}
              {entry.artifactPath ? (
                <a
                  className="link"
                  href={artifactUrl(entry.artifactPath)}
                  target="_blank"
                  rel="noreferrer"
                >
                  View artifact
                </a>
              ) : null}
              {onSubmitFeedback && entry.artifactPath && (
                <UsefulnessFeedbackControl
                  entry={entry}
                  onSubmit={onSubmitFeedback}
                />
              )}
            </article>
          );
        })}
      </div>
    ) : history.length === 0 ? (
      <p className="muted">No execution history for this run yet. Execute a check from the Work list above.</p>
    ) : (
      <p className="muted">No entries match the current filters. Try adjusting your filters.</p>
    )}
  </section>
);
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

const detailPreferenceKeys = ["confidence", "target"];

const getNotificationDetailText = (entry: NotificationEntry) => {
  const priorityDetail = entry.details.find((detail) =>
    detailPreferenceKeys.some((keyword) => detail.label.toLowerCase().includes(keyword))
  );
  const detailEntry = priorityDetail ?? entry.details[0];
  if (detailEntry) {
    return `${detailEntry.label}: ${detailEntry.value}`;
  }
  if (entry.context) {
    return entry.context;
  }
  return "—";
};

const NotificationHistoryTable = () => {
  const [entries, setEntries] = useState<NotificationEntry[]>([]);
  const [totalResults, setTotalResults] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [perPage, setPerPage] = useState(NOTIFICATIONS_PER_PAGE);
  const [kindFilter, setKindFilter] = useState("all");
  const [clusterFilter, setClusterFilter] = useState("all");
  const [searchFilter, setSearchFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const normalizedSearch = searchFilter.trim();

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchNotifications({
          kind: kindFilter !== "all" ? kindFilter : undefined,
          cluster_label: clusterFilter !== "all" ? clusterFilter : undefined,
          search: normalizedSearch || undefined,
          limit: NOTIFICATIONS_PER_PAGE,
          page,
        });
        if (!active) {
          return;
        }
        const limitValue = Math.max(1, response.limit ?? NOTIFICATIONS_PER_PAGE);
        const totalValue = response.total ?? response.notifications.length;
        const pages = response.total_pages && response.total_pages >= 1
          ? response.total_pages
          : Math.max(1, Math.ceil(totalValue / limitValue));
        const requestedPage = response.page ?? page;
        if (requestedPage > pages) {
          setPage(pages);
          return;
        }
        setEntries(response.notifications);
        setTotalResults(totalValue);
        setTotalPages(pages);
        setPerPage(limitValue);
      } catch (err) {
        if (!active) {
          return;
        }
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [kindFilter, clusterFilter, searchFilter, page]);

  const kindOptions = useMemo(() => {
    const values = new Set<string>();
    entries.forEach((entry) => values.add(normalizeFilterValue(entry.kind)));
    return ["all", ...Array.from(values)];
  }, [entries]);
  const clusterOptions = useMemo(() => {
    const values = new Set<string>();
    entries.forEach((entry) => values.add(normalizeFilterValue(entry.clusterLabel)));
    return ["all", ...Array.from(values)];
  }, [entries]);
  const displayStart = entries.length ? (page - 1) * perPage + 1 : 0;
  const displayEnd = entries.length ? (page - 1) * perPage + entries.length : 0;
  const handlePrev = () => setPage((current) => Math.max(1, current - 1));
  const handleNext = () => setPage((current) => Math.min(totalPages, current + 1));
  const formatFilterOption = (value: string) => {
    if (value === "all") {
      return "All";
    }
    if (value === "unknown") {
      return "Unknown";
    }
    return value;
  };
  const summaryText = loading
    ? "Loading notifications…"
    : error
    ? error
    : totalResults
    ? `Showing ${displayStart}–${displayEnd} of ${totalResults}`
    : "No notifications available.";

  return (
    <>
      <div className="notification-table-wrapper">
        <div className="notification-table-controls">
          <label>
            Kind
            <select
              aria-label="Notification kind filter"
              value={kindFilter}
              onChange={(event) => {
                setKindFilter(event.target.value);
                setPage(1);
              }}
            >
              {kindOptions.map((option) => (
                <option key={option} value={option}>
                  {formatFilterOption(option)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Cluster
            <select
              aria-label="Notification cluster filter"
              value={clusterFilter}
              onChange={(event) => {
                setClusterFilter(event.target.value);
                setPage(1);
              }}
            >
              {clusterOptions.map((option) => (
                <option key={option} value={option}>
                  {formatFilterOption(option)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Search
            <input
              type="search"
              aria-label="Notification text search"
              placeholder="Summary or detail"
              value={searchFilter}
              onChange={(event) => {
                setSearchFilter(event.target.value);
                setPage(1);
              }}
            />
          </label>
        </div>
        <p className="muted small notification-summary">
          {summaryText}
          {summaryText.startsWith("Showing") ? ` · ${perPage} per page` : ""}
        </p>
        <div className="notification-table-scroll">
          {loading ? (
            <p className="muted small">Loading notifications…</p>
          ) : error ? (
            <div className="alert alert-inline">{error}</div>
          ) : (
              <table className="notification-table" aria-label="Notification history table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Kind</th>
                  <th>Summary</th>
                  <th>Run / Cluster</th>
                  <th>Key detail</th>
                  <th>Artifact</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry, index) => {
                  const detailText = getNotificationDetailText(entry);
                  const artifactLink = entry.artifactPath ? artifactUrl(entry.artifactPath) : null;
                  const runLabels: string[] = [];
                  if (entry.runId) {
                    runLabels.push(`Run ${entry.runId}`);
                  }
                  if (entry.clusterLabel) {
                    runLabels.push(`Cluster ${entry.clusterLabel}`);
                  }
                  const runClusterLabel = runLabels.length ? runLabels.join(" · ") : "—";
                  return (
                    <tr key={`${entry.kind}-${entry.timestamp}-${index}`} data-testid="notification-row">
                      <td>
                        <strong>{formatTimestamp(entry.timestamp)}</strong>
                        <p className="tiny compact">{relativeRecency(entry.timestamp)}</p>
                      </td>
                      <td>
                        <span className={statusClass(entry.kind)}>{entry.kind}</span>
                      </td>
                      <td>
                        <p className="notification-summary">{truncateText(entry.summary, 120)}</p>
                      </td>
                      <td>
                        <p className="tiny compact notification-run-cluster">{runClusterLabel}</p>
                      </td>
                      <td>
                        <p className="notification-detail">{truncateText(detailText, 100)}</p>
                      </td>
                      <td>
                        {artifactLink ? (
                          <a
                            className="artifact-link"
                            href={artifactLink}
                            target="_blank"
                            rel="noreferrer"
                          >
                            View
                          </a>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  );
                })}
                {!entries.length && (
                  <tr>
                    <td colSpan={6} className="muted small">
                      No notifications match the current filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <div className="notification-pagination">
        <div className="notification-pagination-controls">
          <button
            type="button"
            onClick={handlePrev}
            disabled={loading || page <= 1}
            aria-label="Previous notifications page"
          >
            Previous
          </button>
          <span>
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            onClick={handleNext}
            disabled={loading || page >= totalPages}
            aria-label="Next notifications page"
          >
            Next
          </button>
        </div>
        <p className="muted small">
          Showing {displayStart}–{displayEnd} of {totalResults}
        </p>
      </div>
    </>
  );
};

const App = () => {
  const [run, setRun] = useState<RunPayload | null>(null);
  const [fleet, setFleet] = useState<FleetPayload | null>(null);
  const [proposals, setProposals] = useState<ProposalsPayload | null>(null);
  const [runsList, setRunsList] = useState<RunsListEntry[]>([]);
  const [runsListLoading, setRunsListLoading] = useState(true);
  const [runsListError, setRunsListError] = useState<string | null>(null);
  const [clusterDetail, setClusterDetail] = useState<ClusterDetailPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [searchText, setSearchText] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("proposalId");
  const [expandedProposals, setExpandedProposals] = useState<Set<string>>(new Set());
  const [activeTab, setActiveTab] = useState<"findings" | "hypotheses" | "checks">("findings");
  const [lastRefresh, setLastRefresh] = useState(() => dayjs());
  const [selectedClusterLabel, setSelectedClusterLabel] = useState<string | null>(null);
  const [clusterDetailExpanded, setClusterDetailExpanded] = useState(false);
  const [autoRefreshInterval, setAutoRefreshInterval] = useState<number | null>(() => {
    return readStoredAutoRefreshInterval();
  });
  const [executionResults, setExecutionResults] = useState<Record<string, ExecutionResult>>({});
  const [executingCandidate, setExecutingCandidate] = useState<string | null>(null);
  const [approvalResults, setApprovalResults] = useState<Record<string, ApprovalResult>>({});
  const [approvingCandidate, setApprovingCandidate] = useState<string | null>(null);
  const [promotionStatus, setPromotionStatus] = useState<Record<string, PromotionStatus>>({});
  const [promotingDeterministic, setPromotingDeterministic] = useState<Record<string, boolean>>({});
  const [promotionMessages, setPromotionMessages] = useState<Record<string, string>>({});
  const initialQueueViewState = useMemo(() => readStoredQueueViewState(), []);
  const [queueClusterFilter, setQueueClusterFilter] = useState(
    initialQueueViewState.clusterFilter
  );
  const [queueStatusFilter, setQueueStatusFilter] = useState<NextCheckQueueStatus | "all">(
    initialQueueViewState.statusFilter
  );
  const [queueCommandFamilyFilter, setQueueCommandFamilyFilter] = useState(
    initialQueueViewState.commandFamilyFilter
  );
  const [queuePriorityFilter, setQueuePriorityFilter] = useState(
    initialQueueViewState.priorityFilter
  );
  const [queueWorkstreamFilter, setQueueWorkstreamFilter] = useState(
    initialQueueViewState.workstreamFilter
  );
  const [queueSearch, setQueueSearch] = useState(initialQueueViewState.searchText);
  const [queueSortOption, setQueueSortOption] = useState<QueueSortOption>(
    initialQueueViewState.sortOption
  );
  const [queueFocusMode, setQueueFocusMode] = useState<QueueFocusMode>(
    initialQueueViewState.focusMode
  );
  const [highlightedClusterLabel, setHighlightedClusterLabel] = useState<string | null>(null);
  const [incidentExpandedClusters, setIncidentExpandedClusters] = useState<Record<string, boolean>>({});
  const [executionHistoryHighlightKey, setExecutionHistoryHighlightKey] = useState<string | null>(null);
  const [queueHighlightKey, setQueueHighlightKey] = useState<string | null>(null);
  const clusterHighlightTimer = useRef<number | null>(null);
  
  // Execution history filter state
  const [executionHistoryFilter, setExecutionHistoryFilter] = useState<ExecutionHistoryFilterState>(
    readStoredExecutionHistoryFilter
  );
  const executionHighlightTimer = useRef<number | null>(null);
  const queueHighlightTimer = useRef<number | null>(null);
  // Track the last executed candidate key so we can highlight it after refresh
  const lastExecutedCandidateKey = useRef<string | null>(null);
  
  // Runs list filter state
  const [runsFilter, setRunsFilter] = useState<RunsReviewFilter>(readStoredRunsReviewFilter);
  
  // Pagination state for runs list
  const [runsPageSize, setRunsPageSize] = useState<number>(readStoredRunsPageSize);
  const [runsPage, setRunsPage] = useState(1);
  
  // Reset to page 1 when filter changes
  const handleRunsFilterChange = useCallback((filter: RunsReviewFilter) => {
    setRunsFilter(filter);
    setRunsPage(1);
    persistRunsReviewFilter(filter);
  }, []);

  // Handle page size change
  const handleRunsPageSizeChange = useCallback((newSize: number) => {
    setRunsPageSize(newSize);
    setRunsPage(1); // Reset to first page when page size changes
    persistRunsPageSize(newSize);
  }, []);
  
  // Selected run ID (persisted)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(() => readStoredSelectedRunId());
  
  // Handle run selection from the list
  const handleRunSelection = useCallback((runId: string) => {
    persistSelectedRunId(runId);
    setSelectedRunId(runId);
  }, []);

  // Batch execution state for recent runs
  const [executingBatchRunId, setExecutingBatchRunId] = useState<string | null>(null);
  const [batchExecutionError, setBatchExecutionError] = useState<Record<string, string>>({});

  // Handle batch execution for a run
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
      // Refresh runs list after successful execution
      const payload: RunsListPayload = await fetchRunsList();
      setRunsList(payload.runs);
      // If the selected run is the one we just executed, refresh that too
      if (selectedRunId === runId) {
        const runPayload = await fetchRun(runId);
        setRun(runPayload);
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
  }, [selectedRunId]);

  // Fetch runs list on mount
  useEffect(() => {
    let active = true;
    const loadRunsList = async () => {
      setRunsListLoading(true);
      setRunsListError(null);
      try {
        const payload: RunsListPayload = await fetchRunsList();
        if (active) {
          setRunsList(payload.runs);
        }
      } catch (err) {
        if (active) {
          setRunsListError(err instanceof Error ? err.message : "Failed to load runs");
        }
      } finally {
        if (active) {
          setRunsListLoading(false);
        }
      }
    };
    loadRunsList();
    return () => {
      active = false;
    };
  }, []);
  
  // Compute filter counts
  const runsFilterCounts = useMemo(() => computeRunsFilterCounts(runsList), [runsList]);
  
  // Filter runs based on selected filter
  const filteredRunsList = useMemo(() => {
    if (runsFilter === "all") {
      return runsList;
    }
    return runsList.filter((r) => {
      if (runsFilter === "no-executions") {
        return r.reviewStatus === "no-executions";
      }
      if (runsFilter === "awaiting-review") {
        return r.reviewStatus === "unreviewed";
      }
      if (runsFilter === "partially-reviewed") {
        return r.reviewStatus === "partially-reviewed";
      }
      if (runsFilter === "fully-reviewed") {
        return r.reviewStatus === "fully-reviewed";
      }
      if (runsFilter === "needs-attention") {
        return r.reviewStatus === "unreviewed" || r.reviewStatus === "partially-reviewed";
      }
      return true;
    });
  }, [runsList, runsFilter]);

  // Computed paginated runs list
  const paginatedRunsList = useMemo(() => {
    const start = (runsPage - 1) * runsPageSize;
    const end = start + runsPageSize;
    return filteredRunsList.slice(start, end);
  }, [filteredRunsList, runsPage, runsPageSize]);

  const totalRunsPages = Math.ceil(filteredRunsList.length / runsPageSize);

  // Ref to track if a refresh is in progress to prevent duplicate fetches
  const refreshInProgress = useRef(false);

  const refresh = useCallback(async () => {
    // Prevent overlapping refresh requests - this is critical for reducing
    // server load when auto-refresh is enabled or visibility changes rapidly
    if (refreshInProgress.current) {
      return;
    }
    refreshInProgress.current = true;
    try {
      setError(null);
      const [runPayload, fleetPayload, proposalsPayload] = await Promise.all([
        fetchRun(),
        fetchFleet(),
        fetchProposals(),
      ]);
      setRun(runPayload);
      setFleet(fleetPayload);
      setProposals(proposalsPayload);
      if (!selectedClusterLabel) {
        const fallbackLabel = fleetPayload.clusters[0]?.label ?? null;
        if (fallbackLabel) {
          setSelectedClusterLabel(fallbackLabel);
        }
      }
      setLastRefresh(dayjs());
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
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      refreshInProgress.current = false;
    }
  }, [selectedClusterLabel]);

  const buildPromotionKey = (clusterLabel: string, description: string, index: number) =>
    `${clusterLabel}::${description}::${index}`;

  const handlePromoteDeterministicCheck = useCallback(
    async (
      clusterLabel: string,
      clusterContext: string | null,
      topProblem: string | null,
      check: DeterministicNextCheckSummary,
      index: number
    ) => {
      const key = buildPromotionKey(clusterLabel, check.description, index);
      setPromotionStatus((current) => ({
        ...current,
        [key]: { status: "pending", message: null },
      }));
      const request: DeterministicNextCheckPromotionRequest = {
        clusterLabel,
        context: clusterContext,
        description: check.description,
        method: check.method || null,
        evidenceNeeded: check.evidenceNeeded,
        workstream: check.workstream,
        urgency: check.urgency,
        whyNow: check.whyNow,
        topProblem,
        priorityScore: check.priorityScore ?? null,
      };
      try {
        const response = await promoteDeterministicNextCheck(request);
        setPromotionStatus((current) => ({
          ...current,
          [key]: {
            status: "success",
            message: response.summary ?? "Promoted to queue",
          },
        }));
        await refresh();
      } catch (err) {
        const message = err instanceof Error ? err.message : "Promotion failed";
        setPromotionStatus((current) => ({
          ...current,
          [key]: { status: "error", message },
        }));
      }
    },
    [refresh]
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    let timerId: ReturnType<typeof setInterval> | null = null;
    if (autoRefreshInterval) {
      timerId = setInterval(() => {
        refresh();
      }, autoRefreshInterval * 1000);
    }
    return () => {
      if (timerId !== null) {
        clearInterval(timerId);
      }
    };
  }, [autoRefreshInterval, refresh]);

  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        refresh();
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [refresh]);

  useEffect(() => {
    return () => {
      if (clusterHighlightTimer.current) {
        window.clearTimeout(clusterHighlightTimer.current);
      }
      if (executionHighlightTimer.current) {
        window.clearTimeout(executionHighlightTimer.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!selectedClusterLabel) {
      setClusterDetail(null);
      return;
    }
    let active = true;
    const loadDetail = async () => {
      try {
        const detailPayload = await fetchClusterDetail(selectedClusterLabel);
        if (active) {
          setClusterDetail(detailPayload);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : String(err));
        }
      }
    };
    loadDetail();
    return () => {
      active = false;
    };
  }, [selectedClusterLabel, lastRefresh]);

  const statusOptions = useMemo(() => {
    const entries = proposals?.statusSummary.map((entry) => entry.status) ?? [];
    return ["all", ...Array.from(new Set(entries))];
  }, [proposals]);

  const handleToggleProposal = (id: string) => {
    setExpandedProposals((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleClusterSelection = (label: string, options?: { expand?: boolean }) => {
    if (!label) {
      return;
    }
    if (label === selectedClusterLabel) {
      if (options?.expand) {
        setClusterDetailExpanded(true);
      }
      return;
    }
    setSelectedClusterLabel(label);
    setClusterDetailExpanded(Boolean(options?.expand));
  };

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

  const handleAutoRefreshChange = (value: string) => {
    if (value === "off") {
      persistAutoRefreshInterval("off");
      setAutoRefreshInterval(null);
      return;
    }
    const parsed = Number(value);
    if (!Number.isNaN(parsed) && parsed > 0) {
      persistAutoRefreshInterval(value);
      setAutoRefreshInterval(parsed);
    }
  };

  const buildCandidateKey = (candidate: NextCheckPlanCandidate, index: number) =>
    `next-check-${candidate.candidateId ?? candidate.candidateIndex ?? index}-${
      candidate.targetCluster ?? selectedClusterLabel ?? "global"
    }`;

  const runQueue: NextCheckQueueItem[] = run?.nextCheckQueue ?? [];
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
  const formatCluster = (value: string | null | undefined) =>
    value && value.trim() ? value : "Unassigned";
  const formatCommandFamily = (value: string | null | undefined) =>
    value && value.trim() ? value : "Unspecified";
  const formatPriority = (value: string | null | undefined) =>
    (value ?? "unknown").toLowerCase();

  const queueClusterOptions = useMemo(() => {
    const values = new Set<string>();
    runQueue.forEach((entry) => values.add(formatCluster(entry.targetCluster)));
    return Array.from(values).sort();
  }, [runQueue]);

  const queueCommandFamilyOptions = useMemo(() => {
    const values = new Set<string>();
    runQueue.forEach((entry) => values.add(formatCommandFamily(entry.suggestedCommandFamily)));
    return Array.from(values).sort();
  }, [runQueue]);

  const queuePriorityOptions = useMemo(() => {
    const values = new Set<string>();
    runQueue.forEach((entry) => values.add(formatPriority(entry.priorityLabel)));
    return Array.from(values).sort();
  }, [runQueue]);

  const queueWorkstreamOptions = useMemo(() => {
    const values = new Set<string>();
    runQueue.forEach((entry) => {
      if (entry.workstream && entry.workstream.trim()) {
        values.add(entry.workstream);
      }
    });
    return Array.from(values).sort();
  }, [runQueue]);

  const formatWorkstream = (value: string | null | undefined) =>
    value && value.trim() ? value : "Unassigned";

  const queueSearchTerm = queueSearch.trim().toLowerCase();
  const filteredQueue = useMemo(() => {
    const focusStatuses = QUEUE_FOCUS_FILTERS[queueFocusMode];
    return runQueue.filter((item) => {
      const status = (item.queueStatus as NextCheckQueueStatus) ?? "duplicate-or-stale";
      if (queueStatusFilter !== "all" && status !== queueStatusFilter) {
        return false;
      }
      if (focusStatuses.length && !focusStatuses.includes(status)) {
        return false;
      }
      const clusterValue = formatCluster(item.targetCluster);
      if (queueClusterFilter !== "all" && clusterValue !== queueClusterFilter) {
        return false;
      }
      const commandFamilyValue = formatCommandFamily(item.suggestedCommandFamily);
      if (queueCommandFamilyFilter !== "all" && commandFamilyValue !== queueCommandFamilyFilter) {
        return false;
      }
      const priorityValue = formatPriority(item.priorityLabel);
      if (queuePriorityFilter !== "all" && priorityValue !== queuePriorityFilter) {
        return false;
      }
      const workstreamValue = formatWorkstream(item.workstream);
      if (queueWorkstreamFilter !== "all" && workstreamValue !== queueWorkstreamFilter) {
        return false;
      }
      if (!queueSearchTerm) {
        return true;
      }
      const haystack = [item.description, item.sourceReason, item.expectedSignal]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(queueSearchTerm);
    });
  }, [
    runQueue,
    queueClusterFilter,
    queueStatusFilter,
    queueCommandFamilyFilter,
    queuePriorityFilter,
    queueWorkstreamFilter,
    queueSearchTerm,
    queueFocusMode,
  ]);

  const sortedQueue = useMemo(() => {
    if (queueSortOption === "default") {
      return filteredQueue;
    }
    const copy = [...filteredQueue];
    if (queueSortOption === "priority") {
      copy.sort(
        (a, b) => queuePriorityRank(a.priorityLabel) - queuePriorityRank(b.priorityLabel)
      );
    } else if (queueSortOption === "cluster") {
      copy.sort((a, b) =>
        formatCluster(a.targetCluster).localeCompare(formatCluster(b.targetCluster))
      );
    } else if (queueSortOption === "activity") {
      copy.sort(
        (a, b) => queueTimestampValue(b.latestTimestamp) - queueTimestampValue(a.latestTimestamp)
      );
    }
    return copy;
  }, [filteredQueue, queueSortOption]);

  const filtersActive =
    queueClusterFilter !== "all" ||
    queueStatusFilter !== "all" ||
    queueCommandFamilyFilter !== "all" ||
    queuePriorityFilter !== "all" ||
    queueWorkstreamFilter !== "all" ||
    Boolean(queueSearchTerm) ||
    queueFocusMode !== "none";

  const queueGroups = NEXT_CHECK_QUEUE_STATUS_ORDER.map((status) => ({
    status,
    label: NEXT_CHECK_QUEUE_STATUS_LABELS[status],
    items: sortedQueue.filter(
      (entry) => ((entry.queueStatus as NextCheckQueueStatus) ?? "duplicate-or-stale") === status
    ),
  })).filter((group) => group.items.length > 0);

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

  useEffect(() => {
    persistQueueViewState({
      clusterFilter: queueClusterFilter,
      statusFilter: queueStatusFilter,
      commandFamilyFilter: queueCommandFamilyFilter,
      priorityFilter: queuePriorityFilter,
      workstreamFilter: queueWorkstreamFilter,
      searchText: queueSearch,
      focusMode: queueFocusMode,
      sortOption: queueSortOption,
    });
  }, [
    queueClusterFilter,
    queueStatusFilter,
    queueCommandFamilyFilter,
    queuePriorityFilter,
    queueWorkstreamFilter,
    queueSearch,
    queueFocusMode,
    queueSortOption,
  ]);

  // Persist execution history filter state
  useEffect(() => {
    persistExecutionHistoryFilter(executionHistoryFilter);
  }, [executionHistoryFilter]);

  const [expandedQueueItems, setExpandedQueueItems] = useState<Record<string, boolean>>({});
  const toggleQueueDetails = useCallback((key: string) => {
    setExpandedQueueItems((current) => ({
      ...current,
      [key]: !current[key],
    }));
  }, []);

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

  const handleUsefulnessFeedback = useCallback(
    async (
      artifactPath: string,
      usefulnessClass: string,
      summary: string | undefined
    ) => {
      await submitUsefulnessFeedback({
        artifactPath,
        usefulnessClass: usefulnessClass as "useful" | "partial" | "noisy" | "empty",
        usefulnessSummary: summary,
      });
      // Refresh to get updated data
      await refresh();
    },
    [refresh]
  );

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

  const runRecency = relativeRecency(run.timestamp);
  const runFresh = !isStaleTimestamp(run.timestamp);
  const runAgeMinutes = Math.floor(dayjs().diff(run.timestamp, "minute"));
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
          <p className="eyebrow">Operator console</p>
          <h1>Fleet triage cockpit</h1>
          <div className="hero-run">
            <div className="hero-run-identity">
              <p className="eyebrow hero-run-label">Current run</p>
              <div className="hero-run-title">
                <strong>Run {run.label}</strong>
                <span className="hero-run-id">ID {run.runId}</span>
              </div>
            </div>
            <div className="hero-run-freshness">
              <span className={`freshness-pill ${runFresh ? "fresh" : "stale"}`}>
                {runFresh ? "Fresh data" : "Stale data"}
              </span>
              <p className="hero-run-recency small muted">Last run {runRecency}</p>
            </div>
          </div>
        </div>
        <div className="hero-actions">
          <div className="refresh-controls">
            <button type="button" onClick={refresh}>
              Refresh data
            </button>
            <div className="autorefresh-control">
              <label htmlFor="auto-refresh-interval">Auto refresh</label>
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
              <span className="autorefresh-status muted small">{autoRefreshStatusText}</span>
            </div>
          </div>
          <span className="small">Updated {dayjs(lastRefresh).fromNow()}</span>
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
      {/* Recent runs panel */}
      <section className="panel recent-runs" id="recent-runs">
        <div className="section-head">
          <div>
            <h2>Recent runs</h2>
            <p className="muted small">Historical runs with triage status for review tracking.</p>
          </div>
        </div>
        <div className="runs-filter-bar">
          <div className="runs-filter-options">
            {RUNS_REVIEW_FILTER_OPTIONS.map((option) => {
              const count = runsFilterCounts[option.value];
              const isActive = runsFilter === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  className={`runs-filter-button ${isActive ? "active" : ""}`}
                  onClick={() => handleRunsFilterChange(option.value)}
                >
                  <span className="runs-filter-label">{option.label}</span>
                  <span className="runs-filter-count">({count})</span>
                </button>
              );
            })}
          </div>
        </div>
        {runsFilter !== "all" && filteredRunsList.length > 0 && (
          <p className="runs-filter-summary small muted">
            Showing {filteredRunsList.length} of {runsList.length} runs
          </p>
        )}
        {runsListLoading ? (
          <p className="muted">Loading runs...</p>
        ) : runsListError ? (
          <div className="alert alert-inline">{runsListError}</div>
        ) : filteredRunsList.length === 0 ? (
          <p className="muted">No runs match the current filter.</p>
        ) : (
          <div className="runs-table-wrapper">
                <table className="runs-table" aria-label="Recent runs">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Status</th>
                  <th>Review</th>
                  <th>Timestamp</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {paginatedRunsList.map((runEntry) => {
                  const isSelected = selectedRunId === runEntry.runId;
                  return (
                    <tr
                      key={runEntry.runId}
                      className={`run-row ${isSelected ? "run-row-selected" : ""}`}
                      data-testid="run-entry"
                      data-run-id={runEntry.runId}
                      onClick={() => handleRunSelection(runEntry.runId)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          handleRunSelection(runEntry.runId);
                        }
                      }}
                      tabIndex={0}
                      role="button"
                      aria-pressed={isSelected}
                      aria-label={`Run ${runEntry.label}, ${runEntry.reviewStatus}, selected: ${isSelected}`}
                    >
                      <td>
                        <div className="run-cell-main">
                          <strong>Run {runEntry.label}</strong>
                          <span className="muted small">ID {runEntry.runId}</span>
                        </div>
                      </td>
                      <td>
                        <span className={statusClass(runEntry.reviewStatus)}>
                          {runEntry.reviewStatus}
                        </span>
                      </td>
                      <td>
                        {runEntry.reviewDownloadPath ? (
                          <a
                            href={artifactUrl(runEntry.reviewDownloadPath)}
                            className="btn btn-small"
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                          >
                            Download
                          </a>
                        ) : (
                          <span className="muted small">—</span>
                        )}
                      </td>
                      <td>
                        {runEntry.timestamp ? (
                          <div className="run-cell-timestamp">
                            <span className="muted small">{relativeRecency(runEntry.timestamp)}</span>
                            <span className="muted tiny" title={formatTimestamp(runEntry.timestamp)}>
                              {formatTimestamp(runEntry.timestamp)}
                            </span>
                          </div>
                        ) : (
                          <span className="muted small">—</span>
                        )}
                      </td>
                      <td>
                        {runEntry.reviewStatus === "no-executions" ? (
                          <button
                            type="button"
                            className="btn btn-small"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleBatchExecution(runEntry.runId);
                            }}
                            disabled={executingBatchRunId === runEntry.runId}
                          >
                            {executingBatchRunId === runEntry.runId ? "Running…" : "Execute"}
                          </button>
                        ) : (
                          <span className="muted small">—</span>
                        )}
                        {batchExecutionError[runEntry.runId] && (
                          <p className="muted tiny runs-execution-error">
                            {batchExecutionError[runEntry.runId]}
                          </p>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {totalRunsPages > 1 && (
          <div className="runs-pagination">
            <div className="runs-pagination-controls">
              <button
                type="button"
                onClick={() => setRunsPage((p) => Math.max(1, p - 1))}
                disabled={runsPage <= 1}
                aria-label="Previous page"
              >
                Previous
              </button>
              <span>
                Page {runsPage} of {totalRunsPages}
              </span>
              <button
                type="button"
                onClick={() => setRunsPage((p) => Math.min(totalRunsPages, p + 1))}
                disabled={runsPage >= totalRunsPages}
                aria-label="Next page"
              >
                Next
              </button>
            </div>
            <div className="runs-pagination-size-selector">
              <label htmlFor="runs-page-size">Per page:</label>
              <select
                id="runs-page-size"
                value={runsPageSize}
                onChange={(event) => handleRunsPageSizeChange(Number(event.target.value))}
              >
                {RUNS_PAGE_SIZE_OPTIONS.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </div>
            <p className="muted small">
              Showing {(runsPage - 1) * runsPageSize + 1}–{Math.min(runsPage * runsPageSize, filteredRunsList.length)} of {filteredRunsList.length}
            </p>
          </div>
        )}
      </section>
      <section className="panel run-summary" id="run-detail">
        <div className="run-summary-head">
          <div>
            <p className="eyebrow">Run summary</p>
            <h2>{run.label}</h2>
            <p className="muted tiny run-summary-collector">Collector {run.collectorVersion}</p>
          </div>
          <div className="run-summary-freshness">
            <p className="muted small">{formatTimestamp(run.timestamp)}</p>
          </div>
        </div>
        <div className="run-summary-metrics">
          <div className="run-summary-stats">
            {runSummaryStats.map((stat) => (
              <article
                className="run-stat-card"
                key={stat.label}
                aria-label={`${stat.label}: ${stat.value}`}
              >
                <strong>{stat.value}</strong>
                <span>{stat.label}</span>
              </article>
            ))}
          </div>
          <p className="run-duration-summary muted small">{runStatsSummary}</p>
        </div>
        <div className="run-summary-llm">
          <div className="run-summary-llm-heading">
            <p className="eyebrow">LLM telemetry</p>
            <span className="muted tiny">Provider call metrics from artifacts</span>
          </div>
          <div className="llm-current-line">
            {runLlmStatsLine}
            {providerBreakdown && (
              <p className="llm-provider-breakdown muted tiny">Providers: {providerBreakdown}</p>
            )}
          </div>
          {historicalLlmStatsLine && (
            <details className="llm-historical">
              <summary>Retained history stats</summary>
              {historicalLlmStatsLine}
            </details>
          )}
        </div>
        <div className="artifact-strip run-artifacts">
          {run.artifacts.map((artifact) => {
            const url = artifactUrl(artifact.path);
            return (
              url && (
                <a
                  key={artifact.label}
                  className="artifact-link run-artifact-link"
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
        <div className="run-summary-next-checks">
          <div className="run-summary-next-checks-head">
            <div>
              <p className="eyebrow">Next checks</p>
              <h3>Planner candidates</h3>
              {runPlan ? (
                <>
                  <p className="muted tiny">{planSummaryText}</p>
                  {planStatusText ? (
                    <p className="muted tiny">Planner status: {planStatusText}</p>
                  ) : null}
                </>
              ) : (
                <p className="muted tiny">{plannerReasonText}</p>
              )}
              {plannerNextActionHint ? (
                <p className="muted tiny">{plannerNextActionHint}</p>
              ) : null}
              {plannerArtifactUrl ? (
                <p className="muted tiny">
                  <a className="link" href={plannerArtifactUrl} target="_blank" rel="noreferrer">
                    View planner artifact
                  </a>
                </p>
              ) : null}
              {runPlan && runPlanCandidates.length ? (
                <p className="muted tiny">{planCandidateCountLabel}</p>
              ) : null}
            </div>
            <button
              type="button"
              className="run-summary-next-checks-button"
              onClick={() => focusClusterForNextChecks()}
              disabled={!runPlan}
            >
              Review next checks
            </button>
          </div>
          {!runPlan ? (
            <>
              <p className="muted small">No next checks generated for this run.</p>
              {plannerHint ? (
                <p className="muted tiny">{plannerHint}</p>
              ) : null}
            </>
          ) : runPlanCandidates.length ? (
            <>
              <div className="run-summary-next-checks-stats">
                {discoveryVariantOrder.map((variant) => {
                  const count = discoveryVariantCounts[variant];
                  if (!count) {
                    return null;
                  }
                  return (
                    <span
                      key={variant}
                      className={`next-check-discovery-pill next-check-discovery-pill-${variant}`}
                    >
                      <strong>{count}</strong>
                      <span>{nextCheckStatusLabel(variant)}</span>
                    </span>
                  );
                })}
              </div>
              <div className="run-summary-next-checks-clusters">
                <p className="muted tiny">
                  Affected cluster{discoveryClusters.length === 1 ? "" : "s"}: {discoveryClusters.length || "None"}
                </p>
                <div className="next-check-cluster-tags">
                  {discoveryClusters.length ? (
                    discoveryClusters.map((cluster) => (
                      <button
                        type="button"
                        className="next-check-cluster-badge"
                        key={cluster}
                        onClick={() => focusClusterForNextChecks(cluster)}
                      >
                        {cluster}
                      </button>
                    ))
                  ) : (
                    <p className="muted small">
                      Planner candidates do not target a specific cluster.
                    </p>
                  )}
                </div>
              </div>
            </>
          ) : (
            <p className="muted small">Planner created no candidates for this run.</p>
          )}
        </div>
        {!runFresh && (
          <div className="alert alert-inline">
            Latest run is {runAgeMinutes} minute{runAgeMinutes === 1 ? "" : "s"} old; ensure the scheduler is running.
          </div>
        )}
      </section>
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
    <section className="panel deterministic-next-checks-panel" id="deterministic-next-checks">
      <div className="section-head">
        <div>
          <p className="eyebrow">Deterministic evidence</p>
          <h2>Deterministic next checks</h2>
          <p className="muted tiny">{deterministicSummary}</p>
        </div>
        <span className="muted tiny">
          {deterministicChecks?.clusterCount ?? 0} degraded cluster
          {(deterministicChecks?.clusterCount ?? 0) === 1 ? "" : "s"}
        </span>
      </div>
      {hasDeterministicNextChecks ? (
        <div className="deterministic-cluster-grid">
          {deterministicClusters.map((cluster) => {
            const sortedChecks = sortDeterministicSummaries(
              cluster.deterministicNextCheckSummaries
            );
            const incidentChecks = sortedChecks.filter((check) => check.workstream === "incident");
            const evidenceChecks = sortedChecks.filter((check) => check.workstream === "evidence");
            const driftChecks = sortedChecks.filter((check) => check.workstream === "drift");
            const isIncidentExpanded = Boolean(incidentExpandedClusters[cluster.label]);
            const incidentPreview = isIncidentExpanded
              ? incidentChecks
              : incidentChecks.slice(0, INCIDENT_PREVIEW_LIMIT);
            const incidentHasMore = incidentChecks.length > INCIDENT_PREVIEW_LIMIT;
            const renderCheckItem = (
              check: DeterministicNextCheckSummary,
              index: number
            ) => {
              const promotionKey = buildPromotionKey(cluster.label, check.description, index);
              const promotionEntry = promotionStatus[promotionKey];
              const isPromoting = promotionEntry?.status === "pending";
              const isPromoted = promotionEntry?.status === "success";
              return (
                <li key={`${cluster.label}-${check.workstream}-${index}`}>
                  <div className="deterministic-check-head">
                    <div>
                      <strong>{check.description}</strong>
                      <div className="deterministic-check-badges">
                        <span
                          className={`deterministic-workstream-pill deterministic-workstream-pill-${check.workstream}`}
                        >
                          {DETERMINISTIC_WORKSTREAM_LABELS[check.workstream]}
                        </span>
                        <span
                          className={`deterministic-urgency-pill deterministic-urgency-pill-${check.urgency}`}
                        >
                          {check.urgency}
                        </span>
                        {check.isPrimaryTriage ? (
                          <span className="deterministic-primary-pill">Primary triage</span>
                        ) : null}
                      </div>
                    </div>
                  </div>
                  <div className="deterministic-check-meta">
                    <span>Method: {check.method || "—"}</span>
                    <span>Owner: {check.owner}</span>
                  </div>
                  <p className="muted tiny">{check.whyNow}</p>
                  {check.evidenceNeeded.length ? (
                    <p className="muted tiny">
                      Evidence: {check.evidenceNeeded.join(", ")}
                    </p>
                  ) : null}
                  <div className="deterministic-check-actions">
                    {isPromoted ? (
                      <span className="muted tiny">Promoted to queue</span>
                    ) : (
                      <button
                        type="button"
                        className="button tertiary tiny"
                        onClick={() =>
                          handlePromoteDeterministicCheck(
                            cluster.label,
                            cluster.context || null,
                            cluster.topProblem ?? null,
                            check,
                            index
                          )
                        }
                        disabled={isPromoting}
                      >
                        {isPromoting ? "Promoting…" : "Add to work list"}
                      </button>
                    )}
                    {promotionEntry?.message ? (
                      <p className="muted tiny deterministic-promotion-message">
                        {promotionEntry.message}
                      </p>
                    ) : null}
                    {isPromoted ? (
                      <button
                        type="button"
                        className="deterministic-promotion-view-queue-link"
                        onClick={() => {
                          setQueueStatusFilter("approval-needed");
                          setQueueClusterFilter(cluster.label);
                          scrollToSection("next-check-queue");
                        }}
                      >
                        View in work list →
                      </button>
                    ) : null}
                  </div>
                </li>
              );
            };
            const buildCheckCountLabel = (count: number) =>
              `${count} check${count === 1 ? "" : "s"}`;
            return (
              <article className="deterministic-cluster-card" key={cluster.label}>
                <div className="deterministic-cluster-head">
                  <div>
                    <p className="eyebrow">Cluster detail</p>
                    <h3>{cluster.label}</h3>
                    <p className="muted tiny">
                      {cluster.topProblem ?? "Trigger reasons pending"}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="run-summary-next-checks-button"
                    onClick={() => focusClusterForNextChecks(cluster.label)}
                  >
                    Review cluster detail
                  </button>
                </div>
                <div className="deterministic-cluster-stats">
                  <span>
                    {cluster.deterministicNextCheckCount} deterministic check
                    {cluster.deterministicNextCheckCount === 1 ? "" : "s"}
                  </span>
                  <span>
                    Drilldown: {cluster.drilldownAvailable ? "available" : "missing"}
                  </span>
                </div>
                <div className="deterministic-group-list">
                  <section className="deterministic-group">
                    <div className="deterministic-group-head">
                      <div>
                        <p className="eyebrow">{DETERMINISTIC_WORKSTREAM_LABELS.incident}</p>
                        <p className="muted tiny">
                          {DETERMINISTIC_WORKSTREAM_DESCRIPTIONS.incident}
                        </p>
                      </div>
                      <span className="muted tiny">
                        {buildCheckCountLabel(incidentChecks.length)}
                      </span>
                    </div>
                    {incidentChecks.length ? (
                      <>
                        <ul className="deterministic-check-list">
                          {incidentPreview.map(renderCheckItem)}
                        </ul>
                        {incidentHasMore ? (
                          <button
                            type="button"
                            className="text-button deterministic-show-more"
                            onClick={() => toggleIncidentExpansion(cluster.label)}
                          >
                            {isIncidentExpanded
                              ? "Show fewer incident checks"
                              : `Show all ${incidentChecks.length} incident checks`}
                          </button>
                        ) : null}
                      </>
                    ) : (
                      <p className="muted tiny deterministic-empty-bucket">No firefight checks for this cluster.</p>
                    )}
                  </section>
                  <section className="deterministic-group">
                    <div className="deterministic-group-head">
                      <div>
                        <p className="eyebrow">{DETERMINISTIC_WORKSTREAM_LABELS.evidence}</p>
                        <p className="muted tiny">
                          {DETERMINISTIC_WORKSTREAM_DESCRIPTIONS.evidence}
                        </p>
                      </div>
                      <span className="muted tiny">
                        {buildCheckCountLabel(evidenceChecks.length)}
                      </span>
                    </div>
                    {evidenceChecks.length ? (
                      <ul className="deterministic-check-list">
                        {evidenceChecks.map(renderCheckItem)}
                      </ul>
                    ) : (
                      <p className="muted tiny deterministic-empty-bucket">No evidence gathering checks for this cluster.</p>
                    )}
                  </section>
                  <details
                    className="deterministic-group deterministic-group--drift"
                    open={!hasDegradedClusters}
                  >
                    <summary className="deterministic-group-head">
                      <div>
                        <p className="eyebrow">{DETERMINISTIC_WORKSTREAM_LABELS.drift}</p>
                        <p className="muted tiny">
                          {DETERMINISTIC_WORKSTREAM_DESCRIPTIONS.drift}
                        </p>
                      </div>
                      <span className="muted tiny">
                        {buildCheckCountLabel(driftChecks.length)}
                      </span>
                    </summary>
                    {driftChecks.length ? (
                      <ul className="deterministic-check-list">
                        {driftChecks.map(renderCheckItem)}
                      </ul>
                    ) : (
                      <p className="muted tiny deterministic-empty-bucket">No drift/toil checks for this cluster.</p>
                    )}
                  </details>
                </div>
                <div className="deterministic-cluster-attachments">
                  {cluster.assessmentArtifactPath ? (
                    <a
                      className="link tiny"
                      href={artifactUrl(cluster.assessmentArtifactPath)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      View assessment artifact
                    </a>
                  ) : null}
                  {cluster.drilldownArtifactPath ? (
                    <a
                      className="link tiny"
                      href={artifactUrl(cluster.drilldownArtifactPath)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      View drilldown artifact
                    </a>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="deterministic-empty-state">
          <p className="muted small">No evidence-based checks are available for this run.</p>
          <p className="muted tiny">Review the cluster detail for evidence-based checks to promote.</p>
        </div>
      )}
    </section>
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
      filter={executionHistoryFilter}
      onFilterChange={setExecutionHistoryFilter}
    />
    <section className="panel next-check-queue-panel" id="next-check-queue">
        <div className="section-head">
          <div>
            <p className="eyebrow">Next-check queue</p>
            <h2>Work list</h2>
            <p className="muted tiny">Curated shortlist for execution; approve, run, or review what already ran.</p>
          </div>
          <span className="muted tiny">{runQueue.length} candidate{runQueue.length === 1 ? "" : "s"}</span>
        </div>
        <div className="next-check-queue-controls">
          <div className="next-check-filter-row">
            <label>
              Cluster filter
              <select
                value={queueClusterFilter}
                onChange={(event) => setQueueClusterFilter(event.target.value)}
              >
                <option value="all">All clusters</option>
                {queueClusterOptions.map((entry) => (
                  <option key={entry} value={entry}>
                    {entry}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Queue status
              <select
                value={queueStatusFilter}
                onChange={(event) =>
                  setQueueStatusFilter(event.target.value as NextCheckQueueStatus | "all")
                }
              >
                <option value="all">All statuses</option>
                {NEXT_CHECK_QUEUE_STATUS_ORDER.map((status) => (
                  <option key={status} value={status}>
                    {NEXT_CHECK_QUEUE_STATUS_LABELS[status]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Command family
              <select
                value={queueCommandFamilyFilter}
                onChange={(event) => setQueueCommandFamilyFilter(event.target.value)}
              >
                <option value="all">All command families</option>
                {queueCommandFamilyOptions.map((entry) => (
                  <option key={entry} value={entry}>
                    {entry}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Priority
              <select
                value={queuePriorityFilter}
                onChange={(event) => setQueuePriorityFilter(event.target.value)}
              >
                <option value="all">All priorities</option>
                {queuePriorityOptions.map((entry) => (
                  <option key={entry} value={entry}>
                    {entry}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Workstream
              <select
                value={queueWorkstreamFilter}
                onChange={(event) => setQueueWorkstreamFilter(event.target.value)}
              >
                <option value="all">All workstreams</option>
                {queueWorkstreamOptions.map((entry) => (
                  <option key={entry} value={entry}>
                    {entry}
                  </option>
                ))}
              </select>
            </label>
            <label className="queue-search">
              Search queue
              <input
                type="search"
                placeholder="Description, reason, or signal"
                value={queueSearch}
                onChange={(event) => setQueueSearch(event.target.value)}
              />
            </label>
            <button type="button" className="text-button" onClick={handleBackToQueue}>
              Back to queue
            </button>
          </div>
          <div className="next-check-control-row">
            <div className="focus-presets">
              <button
                type="button"
                className={`focus-preset-button ${queueFocusMode === "work" ? "active" : ""}`}
                aria-pressed={queueFocusMode === "work"}
                onClick={() => toggleQueueFocusPreset("work")}
              >
                Work now
              </button>
              <button
                type="button"
                className={`focus-preset-button ${queueFocusMode === "review" ? "active" : ""}`}
                aria-pressed={queueFocusMode === "review"}
                onClick={() => toggleQueueFocusPreset("review")}
              >
                Needs review
              </button>
            </div>
            <label>
              Sort by
              <select
                value={queueSortOption}
                onChange={(event) =>
                  setQueueSortOption(event.target.value as QueueSortOption)
                }
              >
                {QUEUE_SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="muted tiny next-check-filter-summary">
            Showing {sortedQueue.length} of {runQueue.length} candidate{runQueue.length === 1 ? "" : "s"}
            {filtersActive ? " · filters applied" : ""}
            {" "}
            <button type="button" className="link tiny" onClick={resetQueueView}>
              Reset queue view
            </button>
          </p>
        </div>
        {runQueue.length === 0 ? (
          <div className="queue-empty-state queue-empty-explanation">
            <p className="muted small">Work list is empty for this run.</p>
            {queueExplanation ? (
              <div className="queue-explanation-block">
                <div className="queue-explanation-header">
                  <div>
                    <p className="tiny">Queue status: {queueExplanation.status}</p>
                    {queueExplanation.reason ? (
                      <p>{queueExplanation.reason}</p>
                    ) : null}
                  </div>
                  {queueExplanation.plannerArtifactPath ? (
                    <a
                      className="link tiny"
                      href={artifactUrl(queueExplanation.plannerArtifactPath)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      View planner artifact
                    </a>
                  ) : null}
                </div>
                {queueExplanation.hint ? (
                  <p className="muted tiny">{queueExplanation.hint}</p>
                ) : null}
                <div className="queue-explanation-stats">
                  <span>
                    Degraded clusters: {queueExplanation.clusterState.degradedClusterCount}
                    {queueExplanation.clusterState.degradedClusterLabels.length
                      ? ` (${queueExplanation.clusterState.degradedClusterLabels.join(", ")})`
                      : ""}
                  </span>
                  <span>
                    Drilldowns ready: {queueExplanation.clusterState.drilldownReadyCount}
                  </span>
                  <span>
                    Deterministic next checks: {queueExplanation.clusterState.deterministicNextCheckCount} available
                  </span>
                </div>
                <div className="queue-explanation-accounting">
                  <span>Generated: {queueExplanation.candidateAccounting.generated}</span>
                  <span>Safe: {queueExplanation.candidateAccounting.safe}</span>
                  <span>
                    Approval needed: {queueExplanation.candidateAccounting.approvalNeeded}
                  </span>
                  <span>Duplicate: {queueExplanation.candidateAccounting.duplicate}</span>
                  <span>Completed: {queueExplanation.candidateAccounting.completed}</span>
                  <span>
                    Stale/orphaned: {queueExplanation.candidateAccounting.staleOrphaned}
                  </span>
                </div>
                <p className="muted tiny">
                  Deterministic next checks available: {queueExplanation.deterministicNextChecksAvailable ? "Yes" : "No"}
                </p>
                {queueExplanation.recommendedNextActions.length ? (
                  <div className="queue-explanation-actions">
                    <div className="queue-explanation-actions__label">Recommended next actions</div>
                    <ul>
                      {queueExplanation.recommendedNextActions.map((entry) => (
                        <li key={entry}>{entry}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : sortedQueue.length === 0 ? (
          <p className="muted small queue-empty-state">
            Filters hide all {runQueue.length} candidate{runQueue.length === 1 ? "" : "s"}.
            {filtersActive ? (
              <>
                {" "}
                <button type="button" className="link tiny" onClick={resetQueueFilters}>
                  Reset filters
                </button>
              </>
            ) : null}
          </p>
        ) : (
          queueGroups.map((group) => (
            <div className="next-check-queue-group" key={group.status}>
              <div className="next-check-queue-group-head">
                <div>
                  <h3>{group.label}</h3>
                  <p className="tiny muted">
                    {group.items.length} item{group.items.length === 1 ? "" : "s"} · {group.label}
                  </p>
                </div>
                <span className={`queue-status-pill queue-status-pill-${group.status}`}>
                  {group.label}
                </span>
              </div>
                  <div className="next-check-queue-items">
                    {group.items.map((item, index) => {
                      const queueCandidateKey = buildCandidateKey(item, index);
                      const approvalResult = approvalResults[queueCandidateKey];
                      const executionResult = executionResults[queueCandidateKey];
                      const latestArtifactLink = item.latestArtifactPath
                        ? artifactUrl(item.latestArtifactPath)
                        : null;
                      const allowRun = isManualExecutionAllowed(item);
                      const executionEntry = findExecutionHistoryEntry(item);
                      const detailsExpanded = Boolean(expandedQueueItems[queueCandidateKey]);
                      const planArtifactLink = item.planArtifactPath
                        ? artifactUrl(item.planArtifactPath)
                        : null;
                  const metadataEntries = [
                    { label: "Origin", value: formatSourceType(item.sourceType) },
                    { label: "Source reason", value: item.sourceReason },
                    { label: "Expected signal", value: item.expectedSignal },
                    { label: "Normalization", value: humanizeReason(item.normalizationReason) },
                    { label: "Safety", value: humanizeReason(item.safetyReason) },
                    { label: "Approval reason", value: humanizeReason(item.approvalReason) },
                    { label: "Duplicate reason", value: humanizeReason(item.duplicateReason) },
                    { label: "Blocking reason", value: humanizeReason(item.blockingReason) },
                    { label: "Target context", value: item.targetContext },
                  ].filter((entry) => entry.value);
                  const isQueueCardHighlighted = queueHighlightKey === queueCandidateKey;
                  const queueCardClasses = [
                    "next-check-queue-item",
                    isQueueCardHighlighted ? "highlight-target" : null,
                  ]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <article
                      className={queueCardClasses}
                      key={queueCandidateKey}
                      data-queue-key={queueCandidateKey}
                      data-highlighted={isQueueCardHighlighted ? "true" : undefined}
                    >
                      <div className="next-check-queue-item-meta">
                        <div>
                          <div className="queue-card-title">
                            <strong>{item.description}</strong>
                            {formatSourceType(item.sourceType) ? (
                              <span className="queue-source-pill">
                                {formatSourceType(item.sourceType)}
                              </span>
                            ) : null}
                          </div>
                          <p className="queue-card-reason">
                            <span className="queue-card-reason-label">Why this check: </span>
                            {humanizeReason(item.sourceReason) || item.sourceReason || humanizeReason(item.normalizationReason) || "—"}{" "}
                            {item.expectedSignal ? <span className="queue-card-signal">→ {item.expectedSignal}</span> : null}
                          </p>
                          <p className="tiny">
                            Cluster: {item.targetCluster ?? "Unassigned"}
                          </p>
                          <p className="tiny">
                            Priority: {formatCandidatePriority((item.priorityLabel ?? "secondary").toLowerCase())} · Command: {item.suggestedCommandFamily ?? "—"}
                          </p>
                        </div>
                        <div className="next-check-queue-item-status">
                          <span>Approval: {item.approvalState ?? "unknown"}</span>
                          <span>Execution: {item.executionState ?? "unknown"}</span>
                          <span>Outcome: {item.outcomeStatus ?? "unknown"}</span>
                          {item.priorityRationale ? (
                            <div className="next-check-queue-item-rationale">
                              <span className="priority-rationale-label">
                                Why not actionable now:
                              </span>
                              <span className="priority-rationale-badge">
                                {item.priorityRationale}
                              </span>
                              {item.rankingReason ? (
                                <span className="ranking-reason-badge">
                                  {item.rankingReason}
                                </span>
                              ) : null}
                            </div>
                          ) : null}
                        </div>
                      </div>
                      <div className="next-check-queue-item-flags">
                        <span>Safe to automate: <strong>{item.safeToAutomate ? "Yes" : "No"}</strong></span>
                        <span>Requires approval: <strong>{item.requiresOperatorApproval ? "Yes" : "No"}</strong></span>
                      </div>
                      <div className="next-check-queue-item-actions">
                        {item.requiresOperatorApproval && item.approvalState !== "approved" && (
                          <button
                            type="button"
                            className="button secondary small"
                            onClick={() => handleApproveCandidate(item, queueCandidateKey)}
                            disabled={approvingCandidate === queueCandidateKey}
                          >
                            {approvingCandidate === queueCandidateKey ? "Approving…" : "Approve candidate"}
                          </button>
                        )}
                        {allowRun && (
                          <button
                            type="button"
                            className="button primary small"
                            onClick={() => handleManualExecution(item, queueCandidateKey)}
                            disabled={executingCandidate === queueCandidateKey}
                          >
                            {executingCandidate === queueCandidateKey ? "Running…" : "Run candidate"}
                          </button>
                        )}
                        {!allowRun && (
                          <span className="not-runnable-explanation">
                            {getNotRunnableExplanation(item)}
                          </span>
                        )}
                        {latestArtifactLink && (
                          <a
                            className="link"
                            href={latestArtifactLink}
                            target="_blank"
                            rel="noreferrer"
                          >
                            View latest artifact
                          </a>
                        )}
                        <button
                          type="button"
                          className="queue-action-button"
                          onClick={() => handleQueueClusterJump(item)}
                          disabled={!item.targetCluster}
                        >
                          Open cluster detail
                        </button>
                        {executionEntry ? (
                          <button
                            type="button"
                            className="queue-action-button"
                            onClick={() => handleQueueExecutionJump(item)}
                          >
                            View latest execution
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className="toggle-details-button"
                          onClick={() => toggleQueueDetails(queueCandidateKey)}
                        >
                          {detailsExpanded ? "Hide details" : "Show details"}
                        </button>
                      </div>
                      {approvalResult ? (
                        <p className={`next-check-approval-note next-check-approval-note-${approvalResult.status}`}>
                          {approvalResult.summary}
                          {approvalResult.artifactPath ? (
                            <>
                              {" "}
                              <a
                                className="link"
                                href={artifactUrl(approvalResult.artifactPath)}
                                target="_blank"
                                rel="noreferrer"
                              >
                                View approval record
                              </a>
                            </>
                          ) : null}
                        </p>
                      ) : null}
                      {executionResult ? (
                        <p
                          className={`next-check-execution next-check-execution-${
                            executionResult.status === "success" ? "success" : "error"
                          }`}
                        >
                          {executionResult.summary ||
                            (executionResult.status === "success" ? "Execution recorded." : "Execution failed.")}
                          {executionResult.artifactPath ? (
                            <>
                              {" "}
                              <a
                                className="link"
                                href={artifactUrl(executionResult.artifactPath)}
                                target="_blank"
                                rel="noreferrer"
                              >
                                View artifact
                              </a>
                            </>
                          ) : null}
                        </p>
                      ) : null}
                      {executionResult?.warning ? (
                        <p className="next-check-execution next-check-execution-warning">
                          {executionResult.warning}
                        </p>
                      ) : null}
                      {executionResult?.warning ? (
                        <button
                          type="button"
                          className="link tiny next-check-refresh-action"
                          onClick={() => refresh()}
                        >
                          Refresh now
                        </button>
                      ) : null}
                      {detailsExpanded && (
                        <div className="next-check-queue-item-details">
                          <ResultInterpretationBlock
                            resultClass={item.resultClass}
                            resultSummary={item.resultSummary}
                            suggestedNextOperatorMove={item.suggestedNextOperatorMove}
                          />
                          <FailureFollowUpBlock
                            failureClass={item.failureClass}
                            failureSummary={item.failureSummary}
                            suggestedNextOperatorMove={item.suggestedNextOperatorMove}
                          />
                          <div className="next-check-queue-item-metadata">
                            {metadataEntries.map((entry) => (
                              <span key={entry.label}>
                                <strong>{entry.label}:</strong> {entry.value}
                              </span>
                            ))}
                            {planArtifactLink ? (
                              <span>
                                <strong>Plan artifact:</strong>
                                {" "}
                                <a href={planArtifactLink} target="_blank" rel="noreferrer">
                                  View planner artifact
                                </a>
                              </span>
                            ) : null}
                          </div>
                          <div className="next-check-command-preview">
                            <p className="tiny muted">Command preview</p>
                            <pre>{item.commandPreview ?? item.description}</pre>
                          </div>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            </div>
          ))
        )}
      </section>
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
      <section
        className={`panel${highlightedClusterLabel === selectedClusterLabel ? " cluster-highlighted-panel" : ""}`}
        id="cluster"
        data-highlighted={highlightedClusterLabel === selectedClusterLabel ? "true" : undefined}
      >
        <div className="section-head">
          <h2>Cluster detail</h2>
          <div className="cluster-controls">
            <label>
              Cluster
              <select
                value={selectedClusterLabel ?? ""}
                onChange={(event) => handleClusterSelection(event.target.value)}
              >
                {fleet.clusters.length ? (
                  fleet.clusters.map((cluster) => (
                    <option key={cluster.label} value={cluster.label}>
                      {cluster.label} · {cluster.context}
                    </option>
                  ))
                ) : (
                  <option value="">No clusters configured</option>
                )}
              </select>
            </label>
          </div>
        </div>
        <details
          className="cluster-detail-panel"
          open={clusterDetailExpanded}
          onToggle={(event) => setClusterDetailExpanded(event.currentTarget.open)}
        >
          <summary>
            <div className="cluster-detail-summary">
              <div>
                <p className="eyebrow">Selected cluster</p>
                <strong>
                  {clusterDetail?.selectedClusterLabel || selectedClusterLabel || "Cluster"}
                </strong>
                <p className="small compact">
                  {selectedCluster?.context || clusterDetail?.selectedClusterContext || "Context unknown"}
                </p>
              </div>
              <div className="cluster-detail-summary-meta">
                <span
                  className={statusClass(
                    clusterDetail?.assessment?.healthRating ?? selectedCluster?.healthRating ?? "pending"
                  )}
                >
                  {clusterDetail?.assessment?.healthRating ?? selectedCluster?.healthRating ?? "Pending"}
                </span>
                <span className={`recency-pill ${clusterFresh ? "fresh" : "stale"}`}>
                  {clusterRecency ?? "Awaiting run"}
                </span>
              </div>
            </div>
            <div className="cluster-detail-summary-grid">
              <article className="cluster-summary-card">
                <p className="eyebrow">Current health state</p>
                <span
                  className={statusClass(
                    clusterDetail?.assessment?.healthRating ?? selectedCluster?.healthRating ?? "pending"
                  )}
                >
                  {clusterDetail?.assessment?.healthRating ?? selectedCluster?.healthRating ?? "Pending"}
                </span>
                <p className="small">
                  Missing evidence: {clusterDetail?.assessment?.missingEvidence.join(", ") || "none"}
                </p>
              </article>
              <article className="cluster-summary-card">
                <p className="eyebrow">Top problem</p>
                <strong>{clusterDetail?.topProblem?.title || "Awaiting problem"}</strong>
                <p className="small">
                  {clusterDetail?.topProblem?.detail || "Control plane assessments are still running."}
                </p>
              </article>
              <article className="cluster-summary-card">
                <p className="eyebrow">Trigger / drilldown reason</p>
                <p className="small">{clusterTriggerReason}</p>
                <p className="small">{drilldownSummary}</p>
              </article>
              <article className="cluster-summary-card">
                <p className="eyebrow">Recency & freshness</p>
                <span className={`recency-pill ${clusterFresh ? "fresh" : "stale"}`}>
                  {clusterRecency ?? "Awaiting run"}
                </span>
                <p className="small">{recencyTimestamp}</p>
              </article>
            </div>
            <div className="cluster-detail-summary-artifacts">
              <p className="eyebrow">Recommended artifacts</p>
              {recommendedArtifacts.length ? (
                <div className="artifact-strip">
                  {recommendedArtifacts.map((artifact) => {
                    const url = artifactUrl(artifact.path);
                    return (
                      url && (
                        <a
                          key={`${artifact.label}-${artifact.path}`}
                          className="artifact-link cluster-summary-artifact-link"
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
              ) : (
                <p className="small muted">Artifacts are being captured; check back once collection finishes.</p>
              )}
            </div>
            <p className="small muted">Tap to expand findings, hypotheses, and next checks</p>
          </summary>
          <div className="cluster-detail-body">
            {clusterDetail ? (
              <>
                <div className="cluster-assessment">
                  <div className="cluster-assessment-heading">
                    <div>
                      <p className="eyebrow">Deterministic evidence</p>
                      <h3>{clusterDetail.selectedClusterLabel || "Cluster"}</h3>
                      {clusterDetail.selectedClusterContext ? (
                        <p className="small">{clusterDetail.selectedClusterContext}</p>
                      ) : null}
                    </div>
                  </div>
                  {clusterDetail.assessment ? (
                    <div className="assessment-meta">
                      <span className={statusClass(clusterDetail.assessment.healthRating)}>
                        {clusterDetail.assessment.healthRating}
                      </span>
                      <p className="small">
                        Missing evidence: {clusterDetail.assessment.missingEvidence.join(", ") || "none"}
                      </p>
                      <p className="small">
                        Confidence: {clusterDetail.assessment.overallConfidence || "unknown"}
                      </p>
                      {clusterDetail.assessment.artifactPath ? (
                        <a
                          className="link"
                          href={artifactUrl(clusterDetail.assessment.artifactPath)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          View assessment artifact
                        </a>
                      ) : null}
                    </div>
                  ) : (
                    <p className="muted">No assessment data is available yet.</p>
                  )}
                  {clusterDetail.artifacts.length ? (
                    <div className="artifact-strip cluster-artifacts">
                      {clusterDetail.artifacts.map((artifact) => {
                        const url = artifactUrl(artifact.path);
                        return (
                          url && (
                            <a
                              key={artifact.label}
                              className="artifact-link"
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
                  ) : null}
                  {clusterDetail.recommendedAction ? (
                    <div className="recommended-action">
                      <p className="eyebrow">Recommended action</p>
                      <strong>{clusterDetail.recommendedAction.description}</strong>
                      <p className="small">
                        Safety:
                        <span className={safetyClass(clusterDetail.recommendedAction.safetyLevel)}>
                          {clusterDetail.recommendedAction.safetyLevel}
                        </span>
                      </p>
                      {clusterDetail.recommendedAction.references.length ? (
                        <p className="small">
                          References: {clusterDetail.recommendedAction.references.join(", ")}
                        </p>
                      ) : null}
                    </div>
                  ) : null}
                </div>
                <div className="provider-assisted-block">
                  <p className="eyebrow">Provider-assisted advisory</p>
                  {interpretation ? (
                    <div className="llm-interpretation-card">
                      <h3>LLM drilldown interpretation</h3>
                      <p className="small">
                        Adapter: {interpretation.adapter} · Status:
                        <span className={statusClass(interpretation.status)}>{interpretation.status}</span>
                      </p>
                      <p className="small">Captured: {formatTimestamp(interpretation.timestamp)}</p>
                      {interpretation.summary ? <p className="small">{interpretation.summary}</p> : null}
                      {interpretation.artifactPath ? (
                        <a className="link" href={artifactUrl(interpretation.artifactPath)!} target="_blank" rel="noreferrer">
                          View interpretation artifact
                        </a>
                      ) : null}
                      {interpretation.errorSummary ? (
                        <p className="small muted">Error: {interpretation.errorSummary}</p>
                      ) : null}
                      {interpretation.skipReason ? (
                        <p className="small muted">Skipped because {interpretation.skipReason}</p>
                      ) : null}
                    </div>
                   ) : (
                     <p className="muted small">LLM drilldown interpretation not available.</p>
                   )}
                 </div>
                {planCandidates.length ? (
                    <div className="next-check-plan">
                      <div className="section-head next-check-plan-head">
                      <div>
                        <h3>Next check plan</h3>
                        <p className="muted small">{planSummaryText}</p>
                        <p className="muted tiny">
                          {planCandidateCountLabel}
                          {planStatusText ? ` · ${planStatusText}` : ""}
                        </p>
                        {outcomeSummary.length ? (
                          <div className="next-check-outcome-summary">
                            {outcomeSummary.map((entry) => (
                              <span key={entry.status} className={outcomeStatusClass(entry.status)}>
                                {outcomeStatusDisplay(entry.status)} · {entry.count}
                              </span>
                            ))}
                          </div>
                        ) : null}
                      </div>
                      {planArtifactLink ? (
                        <a
                          className="link"
                          href={planArtifactLink}
                          target="_blank"
                          rel="noreferrer"
                        >
                          View planner artifact
                        </a>
                        ) : null}
                      </div>
                      {orphanedApprovals.length ? (
                        <div className="next-check-orphaned">
                          <p className="tiny muted">
                            Orphaned approvals · {orphanedApprovals.length} record
                            {orphanedApprovals.length === 1 ? "" : "s"}
                          </p>
                          <ul>
                            {orphanedApprovals.map((approval, orphanIndex) => {
                              const label =
                                approval.candidateDescription || approval.candidateId || "Unknown approval";
                              const recency = approval.approvalTimestamp
                                ? ` · ${relativeRecency(approval.approvalTimestamp)}`
                                : "";
                              const target = approval.targetCluster
                                ? ` · ${approval.targetCluster}`
                                : "";
                              const artifactLink =
                                approval.approvalArtifactPath && artifactUrl(approval.approvalArtifactPath);
                              return (
                                <li key={`${label}-${orphanIndex}`}>
                                  <strong>{label}</strong>
                                  <p className="tiny muted">
                                    {approvalStatusLabels[approval.approvalStatus ?? ""] ?? "Orphaned"}
                                    {target}
                                    {recency}
                                  </p>
                                  {artifactLink ? (
                                    <a className="link" href={artifactLink} target="_blank" rel="noreferrer">
                                      View approval record
                                    </a>
                                  ) : null}
                                </li>
                              );
                            })}
                          </ul>
                        </div>
                      ) : null}
                      <div className="next-check-plan-grid">
                        {planCandidates.map((candidate, index) => {
                          const variant = determineNextCheckStatusVariant(candidate);
                          const statusLabel = getPlanStatusLabel(variant, candidate);
                          const statusClassName = `plan-status-pill plan-status-pill-${variant}`;
                          const priority = (candidate.priorityLabel ?? "secondary").toLowerCase();
                          const displayPriority = formatCandidatePriority(priority);
                          const priorityIndicatorClass = `priority-pill priority-pill-${priority}`;
                          const targetLabel =
                            candidate.targetCluster ||
                            clusterDetail?.selectedClusterLabel ||
                            selectedClusterLabel ||
                            "cluster";
                          const candidateKey = buildCandidateKey(candidate, index);
                          const manualAllowed = isManualExecutionAllowed(candidate);
                           const executionResult = executionResults[candidateKey];
                           const approvalResult = approvalResults[candidateKey];
                          const approvalArtifactPath =
                            approvalResult?.artifactPath ?? candidate.approvalArtifactPath;
                          const approvalArtifactBaseLink =
                            approvalArtifactPath && artifactUrl(approvalArtifactPath);
                          const approvalArtifactLink =
                            approvalArtifactBaseLink && approvalArtifactPath
                              ? `${approvalArtifactBaseLink}#${approvalArtifactPath}`
                              : null;
                          const approvalTimestamp =
                            candidate.approvalTimestamp ?? approvalResult?.approvalTimestamp;
                          const approvalRecency = approvalTimestamp && relativeRecency(approvalTimestamp);
                          const executionBlockingReason =
                            executionResult && executionResult.status !== "success"
                              ? (executionResult as ExecutionErrorResult).blockingReason
                              : null;
                          const rationaleEntries = [
                            {
                              label: "Normalization",
                              value: candidate.normalizationReason,
                            },
                            {
                              label: "Safety",
                              value: candidate.safetyReason,
                            },
                            {
                              label: "Approval",
                              value: candidate.approvalReason,
                            },
                            {
                              label: "Duplicate",
                              value: candidate.duplicateReason,
                            },
                            {
                              label: "Block",
                              value: candidate.blockingReason,
                            },
                          ].filter((entry) => entry.value);
                        return (
                          <article
                            className="next-check-plan-card"
                            key={`${candidate.description}-${index}`}
                          >
                            <header className="next-check-plan-card-header">
                              <div>
                                <p className="tiny muted">
                                  Source: {candidate.sourceReason || "Planner advisory"}
                                </p>
                                <strong>{candidate.description}</strong>
                                <span className={priorityIndicatorClass}>
                                  Priority: {displayPriority}
                                </span>
                              </div>
                              <span className={statusClassName}>{statusLabel}</span>
                            </header>
                            <div className="next-check-plan-meta">
                              <div>
                                <p className="tiny">Command family</p>
                                <strong>{candidate.suggestedCommandFamily || "—"}</strong>
                              </div>
                              <div>
                                <p className="tiny">Target</p>
                                <strong>{targetLabel}</strong>
                              </div>
                              <div>
                                <p className="tiny">Expected signal</p>
                                <strong>{candidate.expectedSignal || "—"}</strong>
                              </div>
                              <div>
                                <p className="tiny">Risk level</p>
                                <strong>{candidate.riskLevel}</strong>
                              </div>
                              <div>
                                <p className="tiny">Confidence</p>
                                <strong>{candidate.confidence}</strong>
                              </div>
                            </div>
                            <div className="next-check-plan-flags">
                              <span>
                                Safe to automate: <strong>{candidate.safeToAutomate ? "Yes" : "No"}</strong>
                              </span>
                              <span>
                                Operator approval: <strong>{candidate.requiresOperatorApproval ? "Yes" : "No"}</strong>
                              </span>
                              <span>
                                Estimated cost: <strong>{candidate.estimatedCost || "—"}</strong>
                              </span>
                            </div>
                              {rationaleEntries.length ? (
                                <div className="plan-rationale">
                                  {rationaleEntries.map((entry) => (
                                    <span key={entry.label} className="plan-rationale-item">
                                      <strong>{entry.label}:</strong> {humanizeReason(entry.value) || entry.value}
                                    </span>
                                  ))}
                                </div>
                              ) : null}
                              {candidate.priorityRationale ? (
                                <div className="next-check-queue-item-rationale">
                                  <span className="priority-rationale-label">
                                    Why not actionable now:
                                  </span>
                                  <span className="priority-rationale-badge">
                                    {candidate.priorityRationale}
                                  </span>
                                  {candidate.rankingReason ? (
                                    <span className="ranking-reason-badge">
                                      {candidate.rankingReason}
                                    </span>
                                  ) : null}
                                </div>
                              ) : null}
                              <div className="next-check-outcome-meta">
                                <span className={outcomeStatusClass(candidate.outcomeStatus)}>
                                  {outcomeStatusDisplay(candidate.outcomeStatus)}
                                </span>
                                <span className="muted tiny">
                                  Approval: {humanizeReason(candidate.approvalState) || candidate.approvalState || "unknown"} · Execution: {humanizeReason(candidate.executionState) || candidate.executionState || "unknown"}
                                </span>
                                {candidate.latestTimestamp ? (
                                  <span className="muted tiny">Updated {relativeRecency(candidate.latestTimestamp)}</span>
                                ) : null}
                                {candidate.latestArtifactPath ? (
                                  <a
                                    className="link"
                                    href={artifactUrl(candidate.latestArtifactPath)}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    View latest artifact
                                  </a>
                                ) : null}
                              </div>
                              {(variant === "approval" || variant === "stale") && (
                                <div className="next-check-approval-actions">
                                  <button
                                    type="button"
                                    className="button secondary small"
                                    onClick={() => handleApproveCandidate(candidate, candidateKey)}
                                    disabled={approvingCandidate === candidateKey}
                                  >
                                    {approvingCandidate === candidateKey ? "Approving…" : "Approve candidate"}
                                  </button>
                                  {approvalResult ? (
                                    <p
                                      className={`next-check-approval-note next-check-approval-note-${approvalResult.status}`}
                                    >
                                      {approvalResult.summary}
                                    </p>
                                  ) : null}
                                  {approvalArtifactLink ? (
                                    <a
                                      className="link"
                                      href={approvalArtifactLink}
                                      target="_blank"
                                      rel="noreferrer"
                                    >
                                      View approval record
                                    </a>
                                  ) : null}
                                </div>
                              )}
                              {variant === "stale" && (
                                <p className="plan-stale-note">
                                  Recorded approval belongs to a prior plan. Request a fresh approval to
                                  run this candidate.
                                </p>
                              )}
                            {variant === "approved" && (
                              <div className="next-check-approval-status">
                                <p className="next-check-approval-note next-check-approval-note-success">
                                  Approved {approvalRecency ?? "recently"}.
                                </p>
                                {approvalArtifactLink ? (
                                  <a className="link" href={approvalArtifactLink} target="_blank" rel="noreferrer">
                                    View approval record
                                  </a>
                                ) : null}
                              </div>
                            )}
                            {manualAllowed && (
                              <div className="next-check-manual-actions">
                                <button
                                  type="button"
                                  className="button primary small"
                                  onClick={() => handleManualExecution(candidate, candidateKey)}
                                  disabled={executingCandidate === candidateKey}
                                >
                                  {executingCandidate === candidateKey ? "Running…" : "Run candidate"}
                                </button>
                                {executionResult ? (
                                  <p
                                    className={`next-check-execution next-check-execution-${
                                      executionResult.status === "success" ? "success" : "error"
                                    }`}
                                  >
                                    {executionResult.summary ||
                                      (executionResult.status === "success"
                                        ? "Execution recorded."
                                        : "Execution failed.")}
                                    {executionResult.artifactPath ? (
                                      <>
                                        {" "}
                                        <a
                                          className="link"
                                          href={artifactUrl(executionResult.artifactPath)}
                                          target="_blank"
                                          rel="noreferrer"
                                        >
                                          View artifact
                                        </a>
                                      </>
                                    ) : null}
                                  </p>
                                ) : null}
                                {executionResult?.warning ? (
                                  <p className="next-check-execution next-check-execution-warning">
                                    {executionResult.warning}
                                  </p>
                                ) : null}
                                {executionResult?.warning ? (
                                  <button
                                    type="button"
                                    className="link tiny next-check-refresh-action"
                                    onClick={() => refresh()}
                                  >
                                    Refresh now
                                  </button>
                                ) : null}
                                {executionBlockingReason ? (
                                  <p className="plan-blocking-reason">
                                    Reason: {humanizeReason(executionBlockingReason)}
                                  </p>
                                ) : null}
                              </div>
                            )}
                            {candidate.normalizationReason ? (
                              <p className="plan-normalization">Normalized: {humanizeReason(candidate.normalizationReason)}</p>
                            ) : null}
                            {candidate.gatingReason ? (
                              <p className="plan-gating">Gating reason: {candidate.gatingReason}</p>
                            ) : null}
                            {candidate.duplicateEvidenceDescription ? (
                              <p className="plan-gating">
                                Duplicate evidence: {candidate.duplicateEvidenceDescription}
                              </p>
                            ) : null}
                          </article>
                        );
                      })}
                    </div>
                  </div>
                ) : null}
                <div className="tab-list" role="tablist" aria-label="Cluster detail tabs">
                  {[
                    { id: "findings", label: "Findings" },
                    { id: "hypotheses", label: "Hypotheses" },
                    { id: "checks", label: "Next checks" },
                  ].map((tab) => (
                    <button
                      key={tab.id}
                      type="button"
                      className={`tab ${activeTab === tab.id ? "active" : ""}`}
                      onClick={() => setActiveTab(tab.id as "findings" | "hypotheses" | "checks")}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
                <article className="tab-panel">
                  {activeTab === "findings" && (
                    <div className="finding-list">
                      {clusterDetail.findings.map((finding) => (
                        <article className="finding-card" key={`${finding.label}-${finding.context}`}>
                          <header>
                            <div>
                              <strong>
                                {finding.label || "cluster"} · {finding.context || "n/a"}
                              </strong>
                              <p className="muted">
                                Triggers: {finding.triggerReasons.join(", ") || "none"}
                              </p>
                              <p className="small">
                                Warnings: {finding.warningEvents} · Non-running pods: {finding.nonRunningPods}
                              </p>
                            </div>
                            {finding.artifactPath ? (
                              <a
                                className="link"
                                href={artifactUrl(finding.artifactPath)}
                                target="_blank"
                                rel="noreferrer"
                              >
                                View raw evidence
                              </a>
                            ) : null}
                          </header>
                          <EvidenceDetails title="Summary" entries={finding.summaryEntries} />
                          <EvidenceDetails title="Patterns" entries={finding.patternDetails} />
                          {finding.rolloutStatus.length ? (
                            <p className="small">Rollout status: {finding.rolloutStatus.join(", ")}</p>
                          ) : null}
                        </article>
                      ))}
                    </div>
                  )}
                  {activeTab === "hypotheses" && (
                    <div className="finding-list">
                      {clusterDetail.hypotheses.map((hypothesis) => (
                        <article className="finding-card compact" key={hypothesis.description}>
                          <strong>{hypothesis.description}</strong>
                          <p className="small">
                            Confidence: {hypothesis.confidence} · Layer: {hypothesis.probableLayer}
                          </p>
                          <p className="small">Falsifier: {hypothesis.falsifier}</p>
                        </article>
                      ))}
                    </div>
                  )}
                  {activeTab === "checks" && (
                    <div className="finding-list">
                      {clusterDetail.nextChecks.map((check) => (
                        <article className="finding-card compact" key={check.description}>
                          <strong>{check.description}</strong>
                          <p className="small">
                            Owner: {check.owner} · Method: {check.method}
                          </p>
                          <p className="small">Evidence: {check.evidenceNeeded.join(", ") || "n/a"}</p>
                        </article>
                      ))}
                    </div>
                  )}
                </article>
                <div className="cluster-lists">
                  <div className="drilldown-summary">
                    <h3>Drilldown summary</h3>
                    <p className="small">
                      {clusterDetail.drilldownAvailability.available}/
                        {clusterDetail.drilldownAvailability.totalClusters} ready ·
                      Missing: {clusterDetail.drilldownAvailability.missingClusters.join(", ") || "none"}
                    </p>
                    <div className="drilldown-grid">
                      {clusterDetail.drilldownCoverage.map((entry) => (
                        <article
                          className={`drilldown-card ${entry.available ? "available" : "missing"}`}
                          key={entry.label}
                        >
                          <header>
                            <strong>{entry.label}</strong>
                            <span>{entry.available ? "Ready" : "Missing"}</span>
                          </header>
                          <p className="small">Context: {entry.context}</p>
                          <p className="small">Captured: {entry.timestamp || "pending"}</p>
                          {entry.artifactPath ? (
                            <a
                              className="link"
                              href={artifactUrl(entry.artifactPath)}
                              target="_blank"
                              rel="noreferrer"
                            >
                              View drilldown
                            </a>
                          ) : null}
                        </article>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h3>Related proposals</h3>
                    {clusterDetail.relatedProposals.map((proposal) => (
                      <div className="related-card" key={proposal.proposalId}>
                        <p className="eyebrow">{proposal.proposalId}</p>
                        <p className="small">{proposal.target}</p>
                        <span className={statusClass(proposal.status)}>{proposal.status}</span>
                      </div>
                    ))}
                  </div>
                  <div>
                    <h3>Related notifications</h3>
                    {clusterDetail.relatedNotifications.map((notification) => (
                      <div className="related-card" key={notification.timestamp + notification.kind}>
                        <p className="eyebrow">{notification.kind}</p>
                        <p className="small">{notification.summary}</p>
                        <span className="small">{formatTimestamp(notification.timestamp)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <p className="muted">Loading cluster evidence…</p>
            )}
          </div>
        </details>
      </section>
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
