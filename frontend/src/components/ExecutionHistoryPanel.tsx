/**
 * ExecutionHistoryPanel component and related execution history utilities.
 *
 * Provides:
 * - ExecutionHistoryPanel: Main panel displaying check execution history with filtering
 * - ExecutionHistorySummaryStrip: Summary strip showing useful/noisy/repeated checks
 * - UsefulnessFeedbackControl: User feedback widget for rating check usefulness
 * - Filter utilities: filterExecutionHistory, extractClustersFromHistory, etc.
 * - Types: ExecutionHistoryFilterState, ExecutionOutcomeFilter, UsefulnessReviewFilter
 */

import { useMemo, useState } from "react";
import {
  NextCheckExecutionHistoryEntry,
  NextCheckPlanCandidate,
  NextCheckQueueItem,
} from "../types";
import {
  artifactUrl,
  formatTimestamp,
  relativeRecency,
  statusClass,
  truncateText,
} from "../utils";
import { ResultInterpretationBlock } from "./ResultInterpretationBlock";
import { FailureFollowUpBlock } from "./FailureFollowUpBlock";

// ============================================================================
// Filter types
// ============================================================================

/**
 * Filters for execution outcome/status: success, failure, timeout
 */
export type ExecutionOutcomeFilter = "all" | "success" | "failure" | "timeout";

/**
 * Filters for usefulness/review classification: useful, partial, noisy, empty, unreviewed
 */
export type UsefulnessReviewFilter = "all" | "useful" | "partial" | "noisy" | "empty" | "unreviewed";

export type ExecutionHistoryFilterState = {
  outcomeFilter: ExecutionOutcomeFilter;
  usefulnessFilter: UsefulnessReviewFilter;
  commandFamilyFilter: string;
  clusterFilter: string;
};

// ============================================================================
// Filter options
// ============================================================================

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

// ============================================================================
// Filter persistence
// ============================================================================

export const EXECUTION_HISTORY_FILTER_STORAGE_KEY = "dashboard-execution-history-filter";

export const persistExecutionHistoryFilter = (filter: ExecutionHistoryFilterState) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(EXECUTION_HISTORY_FILTER_STORAGE_KEY, JSON.stringify(filter));
};

const EXECUTION_HISTORY_FILTER_VALUES: ExecutionOutcomeFilter[] = ["all", "success", "failure", "timeout"];
const USEFULNESS_REVIEW_FILTER_VALUES: UsefulnessReviewFilter[] = ["all", "useful", "partial", "noisy", "empty", "unreviewed"];

const isExecutionOutcomeFilterValue = (value: unknown): value is ExecutionOutcomeFilter =>
  typeof value === "string" && EXECUTION_HISTORY_FILTER_VALUES.includes(value as ExecutionOutcomeFilter);

const isUsefulnessReviewFilterValue = (value: unknown): value is UsefulnessReviewFilter =>
  typeof value === "string" && USEFULNESS_REVIEW_FILTER_VALUES.includes(value as UsefulnessReviewFilter);

export const readStoredExecutionHistoryFilter = (): ExecutionHistoryFilterState => {
  if (typeof window === "undefined") {
    return {
      outcomeFilter: "all",
      usefulnessFilter: "all",
      commandFamilyFilter: "all",
      clusterFilter: "all",
    };
  }
  const stored = window.localStorage.getItem(EXECUTION_HISTORY_FILTER_STORAGE_KEY);
  if (!stored) {
    return {
      outcomeFilter: "all",
      usefulnessFilter: "all",
      commandFamilyFilter: "all",
      clusterFilter: "all",
    };
  }
  try {
    const parsed = JSON.parse(stored);
    if (!parsed || typeof parsed !== "object") {
      return {
        outcomeFilter: "all",
        usefulnessFilter: "all",
        commandFamilyFilter: "all",
        clusterFilter: "all",
      };
    }
    const candidate = parsed as Record<string, unknown>;
    return {
      outcomeFilter: isExecutionOutcomeFilterValue(candidate.outcomeFilter)
        ? candidate.outcomeFilter
        : "all",
      usefulnessFilter: isUsefulnessReviewFilterValue(candidate.usefulnessFilter)
        ? candidate.usefulnessFilter
        : "all",
      commandFamilyFilter: typeof candidate.commandFamilyFilter === "string"
        ? candidate.commandFamilyFilter
        : "all",
      clusterFilter: typeof candidate.clusterFilter === "string"
        ? candidate.clusterFilter
        : "all",
    };
  } catch {
    return {
      outcomeFilter: "all",
      usefulnessFilter: "all",
      commandFamilyFilter: "all",
      clusterFilter: "all",
    };
  }
};

// ============================================================================
// Usefulness feedback constants
// ============================================================================

const USEFULNESS_CLASSES = [
  { value: "useful", label: "Useful" },
  { value: "partial", label: "Partial" },
  { value: "noisy", label: "Noisy" },
  { value: "empty", label: "Empty" },
] as const;

// ============================================================================
// Utility functions
// ============================================================================

/**
 * Format duration in seconds to human-readable string
 */
export const formatDuration = (value: number | null | undefined) => {
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

/**
 * Build a unique key for an execution history entry
 */
export const buildExecutionEntryKey = (entry: NextCheckExecutionHistoryEntry) =>
  `${entry.clusterLabel ?? "global"}::${entry.candidateDescription ?? ""}::${entry.timestamp ?? ""}::${
    entry.artifactPath ?? ""
  }`;

/**
 * Build a unique key for a queue candidate
 */
const buildCandidateKey = (candidate: NextCheckPlanCandidate, index: number) =>
  `next-check-${candidate.candidateId ?? candidate.candidateIndex ?? index}-${index}`;

// ============================================================================
// Filter implementations
// ============================================================================

/**
 * Filter execution history entries based on current filter state
 */
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

/**
 * Extract unique clusters from history entries
 */
export const extractClustersFromHistory = (entries: NextCheckExecutionHistoryEntry[]): string[] => {
  const clusters = new Set<string>();
  entries.forEach((entry) => {
    if (entry.clusterLabel) {
      clusters.add(entry.clusterLabel);
    }
  });
  return Array.from(clusters).sort();
};

/**
 * Extract unique command families from history entries
 */
export const extractCommandFamiliesFromHistory = (entries: NextCheckExecutionHistoryEntry[]): string[] => {
  const families = new Set<string>();
  entries.forEach((entry) => {
    if (entry.commandFamily) {
      families.add(entry.commandFamily);
    }
  });
  return Array.from(families).sort();
};

/**
 * Compute filter counts for execution history
 */
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

// ============================================================================
// Execution History Summary types
// ============================================================================

export type RepeatedFailureGroup = {
  failurePattern: string;
  count: number;
  entries: NextCheckExecutionHistoryEntry[];
  label: string;
};

export type ExecutionHistorySummary = {
  usefulChecks: NextCheckExecutionHistoryEntry[];
  noisyEmptyChecks: NextCheckExecutionHistoryEntry[];
  repeatedFailures: RepeatedFailureGroup[];
};

/**
 * Detect repeated failure patterns using a simple deterministic heuristic.
 */
const detectRepeatedFailures = (entries: NextCheckExecutionHistoryEntry[]): RepeatedFailureGroup[] => {
  // Only consider failed or timed-out entries
  const failureEntries = entries.filter((e) => {
    const isFailure = e.status === "failed" || e.status === "error";
    const isTimeout = e.timedOut === true;
    const hasFailureClass = Boolean(e.failureClass);
    return isFailure || isTimeout || hasFailureClass;
  });

  if (failureEntries.length === 0) {
    return [];
  }

  // Build a key for grouping similar failures
  const getFailureKey = (entry: NextCheckExecutionHistoryEntry): string => {
    if (entry.failureClass) {
      return `class:${entry.failureClass}`;
    }
    if (entry.timedOut) {
      return entry.commandFamily ? `timeout:${entry.commandFamily}` : "timeout:generic";
    }
    if (entry.status === "failed" || entry.status === "error") {
      return entry.commandFamily ? `failed:${entry.commandFamily}` : "failed:generic";
    }
    const prefix = (entry.candidateDescription || "").slice(0, 30).toLowerCase().trim();
    return `desc:${prefix}`;
  };

  const getFailureLabel = (entry: NextCheckExecutionHistoryEntry, key: string): string => {
    if (key.startsWith("class:")) {
      const failureClass = key.slice(6);
      const labels: Record<string, string> = {
        "timed-out": "Timed out",
        "command-unavailable": "Command unavailable",
        "context-unavailable": "Context unavailable",
        "command-failed": "Command failed",
        "blocked-by-gating": "Blocked",
        "approval-missing-or-stale": "Approval needed",
        "unknown-failure": "Unknown failure",
      };
      return labels[failureClass] || failureClass.replace(/-/g, " ");
    }
    if (key.startsWith("timeout:")) {
      const cmd = key.slice(8);
      return cmd === "generic" ? "Timed out" : `${cmd} timed out`;
    }
    if (key.startsWith("failed:")) {
      const cmd = key.slice(7);
      return cmd === "generic" ? "Command failed" : `${cmd} failed`;
    }
    return "Similar failures";
  };

  // Group entries by failure key
  const groups = new Map<string, NextCheckExecutionHistoryEntry[]>();
  failureEntries.forEach((entry) => {
    const key = getFailureKey(entry);
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key)!.push(entry);
  });

  // Only include groups with 2+ entries (repeated)
  const repeated: RepeatedFailureGroup[] = [];
  groups.forEach((groupEntries, key) => {
    if (groupEntries.length >= 2) {
      repeated.push({
        failurePattern: key,
        count: groupEntries.length,
        entries: groupEntries,
        label: getFailureLabel(groupEntries[0], key),
      });
    }
  });

  // Sort by count descending, then by label
  repeated.sort((a, b) => {
    if (b.count !== a.count) {
      return b.count - a.count;
    }
    return a.label.localeCompare(b.label);
  });

  return repeated;
};

/**
 * Compute a run-scoped summary of execution history entries.
 */
export const computeExecutionHistorySummary = (
  entries: NextCheckExecutionHistoryEntry[]
): ExecutionHistorySummary => {
  // Most useful checks: entries with usefulnessClass = "useful"
  const usefulChecks = entries.filter((e) => e.usefulnessClass === "useful");

  // Noisy/empty checks: entries with usefulnessClass in ["noisy", "empty"]
  const noisyEmptyChecks = entries.filter((e) => e.usefulnessClass === "noisy" || e.usefulnessClass === "empty");

  // Repeated failures: detect patterns of repeated failures in the current run
  const repeatedFailures = detectRepeatedFailures(entries);

  return { usefulChecks, noisyEmptyChecks, repeatedFailures };
};

// ============================================================================
// ExecutionHistorySummaryStrip Component
// ============================================================================

type ExecutionHistorySummaryProps = {
  summary: ExecutionHistorySummary;
  onHighlightEntry?: (entryKey: string | null) => void;
  onFilterChange?: (filter: Partial<ExecutionHistoryFilterState>) => void;
};

// Limit displayed items in summary strips
const SUMMARY_ITEM_LIMIT = 3;

const ExecutionHistorySummaryStrip = ({
  summary,
  onHighlightEntry,
  onFilterChange,
}: ExecutionHistorySummaryProps) => {
  const hasUseful = summary.usefulChecks.length > 0;
  const hasNoisyEmpty = summary.noisyEmptyChecks.length > 0;
  const hasRepeated = summary.repeatedFailures.length > 0;

  // Don't render if no summary categories have content
  if (!hasUseful && !hasNoisyEmpty && !hasRepeated) {
    return null;
  }

  const handleEntryClick = (entry: NextCheckExecutionHistoryEntry) => {
    if (onHighlightEntry) {
      const key = buildExecutionEntryKey(entry);
      onHighlightEntry(key);
    }
  };

  const handleFilterClick = (usefulnessFilter?: UsefulnessReviewFilter) => {
    if (onFilterChange) {
      onFilterChange({
        usefulnessFilter: usefulnessFilter || "all",
      });
    }
  };

  return (
    <div className="execution-history-summary">
      {hasUseful && (
        <div className="exec-summary-strip exec-summary-strip--useful">
          <div className="exec-summary-header">
            <span className="exec-summary-label">Most useful</span>
            <span className="exec-summary-count">{summary.usefulChecks.length}</span>
          </div>
          <div className="exec-summary-items">
            {summary.usefulChecks.slice(0, SUMMARY_ITEM_LIMIT).map((entry) => (
              <button
                key={buildExecutionEntryKey(entry)}
                type="button"
                className="exec-summary-item"
                onClick={() => handleEntryClick(entry)}
                title={entry.candidateDescription || "Check"}
              >
                <span className="exec-summary-item-text">
                  {truncateText(entry.candidateDescription || "Check", 40)}
                </span>
                {entry.clusterLabel && (
                  <span className="exec-summary-item-meta">{entry.clusterLabel}</span>
                )}
              </button>
            ))}
            {summary.usefulChecks.length > SUMMARY_ITEM_LIMIT && (
              <button
                type="button"
                className="exec-summary-more"
                onClick={() => handleFilterClick("useful")}
              >
                +{summary.usefulChecks.length - SUMMARY_ITEM_LIMIT} more
              </button>
            )}
          </div>
        </div>
      )}

      {hasNoisyEmpty && (
        <div className="exec-summary-strip exec-summary-strip--noisy">
          <div className="exec-summary-header">
            <span className="exec-summary-label">Noisy / empty</span>
            <span className="exec-summary-count">{summary.noisyEmptyChecks.length}</span>
          </div>
          <div className="exec-summary-items">
            {summary.noisyEmptyChecks.slice(0, SUMMARY_ITEM_LIMIT).map((entry) => (
              <button
                key={buildExecutionEntryKey(entry)}
                type="button"
                className="exec-summary-item"
                onClick={() => handleEntryClick(entry)}
                title={entry.candidateDescription || "Check"}
              >
                <span className={`exec-summary-item-badge usefulness-badge-${entry.usefulnessClass}`}>
                  {entry.usefulnessClass}
                </span>
                <span className="exec-summary-item-text">
                  {truncateText(entry.candidateDescription || "Check", 35)}
                </span>
              </button>
            ))}
            {summary.noisyEmptyChecks.length > SUMMARY_ITEM_LIMIT && (
              <button
                type="button"
                className="exec-summary-more"
                onClick={() => handleFilterClick("noisy")}
              >
                +{summary.noisyEmptyChecks.length - SUMMARY_ITEM_LIMIT} more
              </button>
            )}
          </div>
        </div>
      )}

      {hasRepeated && (
        <div className="exec-summary-strip exec-summary-strip--repeated">
          <div className="exec-summary-header">
            <span className="exec-summary-label">Repeated failures</span>
            <span className="exec-summary-count">
              {summary.repeatedFailures.reduce((sum, g) => sum + g.count, 0)}
            </span>
          </div>
          <div className="exec-summary-items">
            {summary.repeatedFailures.slice(0, SUMMARY_ITEM_LIMIT).map((group) => (
              <button
                key={group.failurePattern}
                type="button"
                className="exec-summary-item"
                onClick={() => handleEntryClick(group.entries[0])}
                title={`${group.count} similar failures: ${group.label}`}
              >
                <span className="exec-summary-item-badge exec-summary-item-badge--repeated">
                  ×{group.count}
                </span>
                <span className="exec-summary-item-text">{group.label}</span>
              </button>
            ))}
            {summary.repeatedFailures.length > SUMMARY_ITEM_LIMIT && (
              <span className="exec-summary-more">
                +{summary.repeatedFailures.length - SUMMARY_ITEM_LIMIT} more patterns
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

// ============================================================================
// UsefulnessFeedbackControl Component
// ============================================================================

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

// ============================================================================
// ExecutionHistoryPanel Props and Component
// ============================================================================

export interface ExecutionHistoryPanelProps {
  history: NextCheckExecutionHistoryEntry[];
  runId: string;
  runLabel: string;
  queueCandidateCount: number;
  highlightedKey: string | null;
  onSubmitFeedback?: (artifactPath: string, usefulnessClass: string, summary: string | undefined) => Promise<void>;
  filter: ExecutionHistoryFilterState;
  onFilterChange: (filter: ExecutionHistoryFilterState) => void;
  runQueue?: NextCheckQueueItem[];
  onHighlightQueueCard?: (key: string) => void;
}

export const ExecutionHistoryPanel = ({
  history,
  runId,
  runLabel,
  queueCandidateCount,
  highlightedKey,
  onSubmitFeedback,
  filter,
  onFilterChange,
  runQueue,
  onHighlightQueueCard,
}: ExecutionHistoryPanelProps) => {
  const filteredHistory = useMemo(
    () => filterExecutionHistory(history, filter),
    [history, filter],
  );

  const clusters = useMemo(() => extractClustersFromHistory(history), [history]);
  const commandFamilies = useMemo(() => extractCommandFamiliesFromHistory(history), [history]);
  const counts = useMemo(() => computeExecutionHistoryFilterCounts(history), [history]);

  // Compute run-scoped summary for the summary strips (based on filtered entries)
  const summary = useMemo(() => computeExecutionHistorySummary(filteredHistory), [filteredHistory]);

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
      <ExecutionHistorySummaryStrip
        summary={summary}
        onHighlightEntry={highlightedKey !== undefined ? (key) => {
          // Bubble up highlight request if onHighlightEntry prop is provided in the future
        } : undefined}
      />
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
                {entry.candidateId && runQueue && onHighlightQueueCard && (
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
                          onHighlightQueueCard(key);
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
                  resultSummary={entry.resultSummary ? truncateText(entry.resultSummary, 120) : null}
                  suggestedNextOperatorMove={entry.suggestedNextOperatorMove}
                />
                <FailureFollowUpBlock
                  failureClass={entry.failureClass}
                  failureSummary={entry.failureSummary}
                  suggestedNextOperatorMove={entry.suggestedNextOperatorMove}
                />
                {entry.usefulnessClass ? (
                  <div className="usefulness-indicator">
                    <span className={`usefulness-badge usefulness-badge-${entry.usefulnessClass}`}>
                      {entry.usefulnessClass}
                    </span>
                    {entry.usefulnessSummary && (
                      <span className="muted small"> — {truncateText(entry.usefulnessSummary, 80)}</span>
                    )}
                  </div>
                ) : (
                  <div className="usefulness-indicator unreviewed">
                    <span className="muted small">Not reviewed</span>
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
