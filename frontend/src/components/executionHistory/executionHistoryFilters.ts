/**
 * executionHistoryFilters.ts
 *
 * Filter types, options, persistence, and filter implementation.
 */

import type { NextCheckExecutionHistoryEntry } from "../../types";

// =============================================================================
// Filter types
// =============================================================================

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

// =============================================================================
// Filter options
// =============================================================================

export const EXECUTION_OUTCOME_FILTER_OPTIONS: { label: string; value: ExecutionOutcomeFilter }[] = [
  { label: "All outcomes", value: "all" },
  { label: "Success", value: "success" },
  { label: "Failure", value: "failure" },
  { label: "Timeout", value: "timeout" },
];

export const USEFULNESS_REVIEW_FILTER_OPTIONS: { label: string; value: UsefulnessReviewFilter }[] = [
  { label: "Any classification", value: "all" },
  { label: "Useful", value: "useful" },
  { label: "Partial", value: "partial" },
  { label: "Noisy", value: "noisy" },
  { label: "Empty", value: "empty" },
  { label: "Unreviewed", value: "unreviewed" },
];

// =============================================================================
// Filter persistence
// =============================================================================

export const EXECUTION_HISTORY_FILTER_STORAGE_KEY = "dashboard-execution-history-filter";

export const EXECUTION_HISTORY_FILTER_VALUES: ExecutionOutcomeFilter[] = ["all", "success", "failure", "timeout"];
export const USEFULNESS_REVIEW_FILTER_VALUES: UsefulnessReviewFilter[] = ["all", "useful", "partial", "noisy", "empty", "unreviewed"];

export const isExecutionOutcomeFilterValue = (value: unknown): value is ExecutionOutcomeFilter =>
  typeof value === "string" && EXECUTION_HISTORY_FILTER_VALUES.includes(value as ExecutionOutcomeFilter);

export const isUsefulnessReviewFilterValue = (value: unknown): value is UsefulnessReviewFilter =>
  typeof value === "string" && USEFULNESS_REVIEW_FILTER_VALUES.includes(value as UsefulnessReviewFilter);

export const persistExecutionHistoryFilter = (filter: ExecutionHistoryFilterState) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(EXECUTION_HISTORY_FILTER_STORAGE_KEY, JSON.stringify(filter));
};

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

// =============================================================================
// Filter implementations
// =============================================================================

export type ExecutionHistoryFilterCounts = {
  outcome: Record<ExecutionOutcomeFilter, number>;
  usefulness: Record<UsefulnessReviewFilter, number>;
};

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
): ExecutionHistoryFilterCounts => {
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
