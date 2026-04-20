/**
 * useQueueState hook - manages queue filtering, sorting, and derived state.
 *
 * Owns: queue filter/sort state, derived option lists, filtered/sorted queue.
 *
 * Inputs:
 *   - runQueue: NextCheckQueueItem[] | null | undefined (from run?.nextCheckQueue)
 *
 * Returns:
 *   - queueClusterFilter: string
 *   - queueStatusFilter: NextCheckQueueStatus | "all"
 *   - queueCommandFamilyFilter: string
 *   - queuePriorityFilter: string
 *   - queueWorkstreamFilter: string
 *   - queueSearch: string
 *   - queueSortOption: QueueSortOption
 *   - queueFocusMode: QueueFocusMode
 *   - setQueueClusterFilter: (v: string) => void
 *   - setQueueStatusFilter: (v: NextCheckQueueStatus | "all") => void
 *   - setQueueCommandFamilyFilter: (v: string) => void
 *   - setQueuePriorityFilter: (v: string) => void
 *   - setQueueWorkstreamFilter: (v: string) => void
 *   - setQueueSearch: (v: string) => void
 *   - setQueueSortOption: (v: QueueSortOption) => void
 *   - setQueueFocusMode: (v: QueueFocusMode) => void
 *   - queueClusterOptions: string[]
 *   - queueCommandFamilyOptions: string[]
 *   - queuePriorityOptions: string[]
 *   - queueWorkstreamOptions: string[]
 *   - filteredQueue: NextCheckQueueItem[]
 *   - sortedQueue: NextCheckQueueItem[]
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import type { NextCheckQueueItem } from "../types";

// ============================================================================
// Types (duplicated from App.tsx to avoid circular dependencies)
// ============================================================================

export type NextCheckQueueStatus =
  | "approved-ready"
  | "safe-ready"
  | "approval-needed"
  | "failed"
  | "completed"
  | "duplicate-or-stale";

type QueueFocusMode = "none" | "work" | "review";

// ============================================================================
// Constants (duplicated from App.tsx)
// ============================================================================

export const QUEUE_VIEW_STORAGE_KEY = "dashboard-queue-view-state";

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

export type QueueSortOption = (typeof QUEUE_SORT_OPTIONS)[number]["value"];

const QUEUE_PRIORITY_ORDER: Record<string, number> = {
  primary: 0,
  secondary: 1,
  fallback: 2,
};

const QUEUE_FOCUS_FILTERS: Record<QueueFocusMode, NextCheckQueueStatus[]> = {
  none: [],
  work: ["approved-ready", "safe-ready", "failed"],
  review: ["approval-needed", "duplicate-or-stale"],
};

const QUEUE_STATUS_FILTER_VALUES = new Set<NextCheckQueueStatus | "all">([
  "all",
  ...NEXT_CHECK_QUEUE_STATUS_ORDER,
]);

const QUEUE_SORT_VALUES = QUEUE_SORT_OPTIONS.map((option) => option.value);
const QUEUE_FOCUS_MODE_VALUES: QueueFocusMode[] = ["none", "work", "review"];

// ============================================================================
// Queue view state types and defaults
// ============================================================================

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

// ============================================================================
// Validation helpers
// ============================================================================

const isQueueStatusFilterValue = (
  value: unknown
): value is NextCheckQueueStatus | "all" =>
  typeof value === "string" && QUEUE_STATUS_FILTER_VALUES.has(value as NextCheckQueueStatus | "all");

const isQueueSortOptionValue = (value: unknown): value is QueueSortOption =>
  typeof value === "string" && QUEUE_SORT_VALUES.includes(value as QueueSortOption);

const isQueueFocusModeValue = (value: unknown): value is QueueFocusMode =>
  typeof value === "string" && QUEUE_FOCUS_MODE_VALUES.includes(value as QueueFocusMode);

// ============================================================================
// Storage helpers
// ============================================================================

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

// ============================================================================
// Queue utility functions
// ============================================================================

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

const normalizeFilterValue = (value: string | null | undefined) =>
  value && value.trim() ? value : "unknown";

const formatCluster = (cluster: string | null | undefined): string => {
  if (!cluster) return "unknown";
  // Truncate very long cluster names for display
  if (cluster.length > 50) {
    return `${cluster.slice(0, 47)}…`;
  }
  return cluster;
};

const formatCommandFamily = (family: string | null | undefined): string => {
  if (!family) return "unknown";
  return normalizeFilterValue(family);
};

const formatPriority = (priority: string | null | undefined): string => {
  const normalized = (priority ?? "unknown").toLowerCase();
  if (normalized === "primary") return "Primary";
  if (normalized === "secondary") return "Secondary";
  if (normalized === "fallback") return "Fallback";
  if (normalized === "unknown") return "Unknown";
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
};

// ============================================================================
// Hook
// ============================================================================

export interface UseQueueStateParams {
  runQueue: NextCheckQueueItem[] | null | undefined;
}

export interface UseQueueStateReturn {
  // Filter state
  queueClusterFilter: string;
  queueStatusFilter: NextCheckQueueStatus | "all";
  queueCommandFamilyFilter: string;
  queuePriorityFilter: string;
  queueWorkstreamFilter: string;
  queueSearch: string;
  queueSortOption: QueueSortOption;
  queueFocusMode: QueueFocusMode;
  // Setters
  setQueueClusterFilter: (v: string) => void;
  setQueueStatusFilter: (v: NextCheckQueueStatus | "all") => void;
  setQueueCommandFamilyFilter: (v: string) => void;
  setQueuePriorityFilter: (v: string) => void;
  setQueueWorkstreamFilter: (v: string) => void;
  setQueueSearch: (v: string) => void;
  setQueueSortOption: (v: QueueSortOption) => void;
  setQueueFocusMode: (v: QueueFocusMode) => void;
  // Derived options
  queueClusterOptions: string[];
  queueCommandFamilyOptions: string[];
  queuePriorityOptions: string[];
  queueWorkstreamOptions: string[];
  // Derived queue
  filteredQueue: NextCheckQueueItem[];
  sortedQueue: NextCheckQueueItem[];
}

export const useQueueState = ({ runQueue }: UseQueueStateParams): UseQueueStateReturn => {
  // Read initial state from localStorage on first render
  const initialQueueViewState = useMemo(() => readStoredQueueViewState(), []);

  // Filter state
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

  // Persist queue view state to localStorage
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

  // Get the raw runQueue or empty array
  const queueItems = runQueue ?? [];

  // Derived: cluster options
  const queueClusterOptions = useMemo(() => {
    const values = new Set<string>();
    queueItems.forEach((entry) => values.add(formatCluster(entry.targetCluster)));
    return Array.from(values).sort();
  }, [queueItems]);

  // Derived: command family options
  const queueCommandFamilyOptions = useMemo(() => {
    const values = new Set<string>();
    queueItems.forEach((entry) => values.add(formatCommandFamily(entry.suggestedCommandFamily)));
    return Array.from(values).sort();
  }, [queueItems]);

  // Derived: priority options
  const queuePriorityOptions = useMemo(() => {
    const values = new Set<string>();
    queueItems.forEach((entry) => values.add(formatPriority(entry.priorityLabel)));
    return Array.from(values).sort();
  }, [queueItems]);

  // Derived: workstream options
  const queueWorkstreamOptions = useMemo(() => {
    const values = new Set<string>();
    queueItems.forEach((entry) => {
      if (entry.workstream && entry.workstream.trim()) {
        values.add(entry.workstream);
      }
    });
    return Array.from(values).sort();
  }, [queueItems]);

  // Derived: filtered queue
  const queueSearchTerm = queueSearch.trim().toLowerCase();
  const filteredQueue = useMemo(() => {
    const focusStatuses = QUEUE_FOCUS_FILTERS[queueFocusMode];

    return queueItems.filter((item) => {
      // Focus mode filter - only show items matching focus statuses
      if (focusStatuses.length > 0) {
        const status = (item.queueStatus as NextCheckQueueStatus) ?? "duplicate-or-stale";
        if (!focusStatuses.includes(status)) {
          return false;
        }
      }

      // Status filter
      if (queueStatusFilter !== "all") {
        const status = (item.queueStatus as NextCheckQueueStatus) ?? "duplicate-or-stale";
        if (status !== queueStatusFilter) {
          return false;
        }
      }

      // Cluster filter
      const clusterValue = formatCluster(item.targetCluster);
      if (queueClusterFilter !== "all" && clusterValue !== queueClusterFilter) {
        return false;
      }

      // Command family filter
      const commandFamilyValue = formatCommandFamily(item.suggestedCommandFamily);
      if (queueCommandFamilyFilter !== "all" && commandFamilyValue !== queueCommandFamilyFilter) {
        return false;
      }

      // Priority filter
      const priorityValue = formatPriority(item.priorityLabel);
      if (queuePriorityFilter !== "all" && priorityValue !== queuePriorityFilter) {
        return false;
      }

      // Workstream filter
      if (queueWorkstreamFilter !== "all" && item.workstream !== queueWorkstreamFilter) {
        return false;
      }

      // Search text filter
      if (queueSearchTerm) {
        const searchableText = [
          item.description,
          item.targetCluster,
          item.sourceReason,
          item.expectedSignal,
          item.suggestedCommandFamily,
          item.targetContext,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!searchableText.includes(queueSearchTerm)) {
          return false;
        }
      }

      return true;
    });
  }, [
    queueItems,
    queueFocusMode,
    queueStatusFilter,
    queueClusterFilter,
    queueCommandFamilyFilter,
    queuePriorityFilter,
    queueWorkstreamFilter,
    queueSearchTerm,
  ]);

  // Derived: sorted queue
  const sortedQueue = useMemo(() => {
    if (queueSortOption === "default") {
      return filteredQueue;
    }

    const copy = [...filteredQueue];
    if (queueSortOption === "priority") {
      copy.sort((a, b) => queuePriorityRank(a.priorityLabel) - queuePriorityRank(b.priorityLabel));
    } else if (queueSortOption === "cluster") {
      copy.sort((a, b) =>
        (a.targetCluster ?? "unknown").localeCompare(b.targetCluster ?? "unknown")
      );
    } else if (queueSortOption === "activity") {
      copy.sort((a, b) => queueTimestampValue(b.latestTimestamp) - queueTimestampValue(a.latestTimestamp));
    }
    return copy;
  }, [filteredQueue, queueSortOption]);

  return {
    // Filter state
    queueClusterFilter,
    queueStatusFilter,
    queueCommandFamilyFilter,
    queuePriorityFilter,
    queueWorkstreamFilter,
    queueSearch,
    queueSortOption,
    queueFocusMode,
    // Setters
    setQueueClusterFilter,
    setQueueStatusFilter,
    setQueueCommandFamilyFilter,
    setQueuePriorityFilter,
    setQueueWorkstreamFilter,
    setQueueSearch,
    setQueueSortOption,
    setQueueFocusMode,
    // Derived options
    queueClusterOptions,
    queueCommandFamilyOptions,
    queuePriorityOptions,
    queueWorkstreamOptions,
    // Derived queue
    filteredQueue,
    sortedQueue,
  };
};
