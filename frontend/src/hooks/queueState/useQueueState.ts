/**
 * useQueueState hook — manages queue filtering, sorting, and derived state.
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

import { useEffect, useMemo, useState } from "react";

import type {
  NextCheckQueueItem,
  NextCheckQueueStatus,
  QueueFocusMode,
  QueueSortOption,
  UseQueueStateParams,
  UseQueueStateResult,
  QueueGroup,
} from "./types";

import {
  NEXT_CHECK_QUEUE_STATUS_LABELS,
  NEXT_CHECK_QUEUE_STATUS_ORDER,
  QUEUE_FOCUS_FILTERS,
} from "./constants";

import { readStoredQueueViewState, persistQueueViewState } from "./storage";

import {
  normalizeQueuePriority,
  queuePriorityRank,
  queueTimestampValue,
  formatCluster,
  formatCommandFamily,
  deriveClusterOptions,
  deriveCommandFamilyOptions,
  derivePriorityOptions,
  deriveWorkstreamOptions,
} from "./selectors";

export const useQueueState = ({
  runQueue,
}: UseQueueStateParams): UseQueueStateResult => {
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
  const queueClusterOptions = useMemo(
    () => deriveClusterOptions(queueItems),
    [queueItems]
  );

  // Derived: command family options
  const queueCommandFamilyOptions = useMemo(
    () => deriveCommandFamilyOptions(queueItems),
    [queueItems]
  );

  // Derived: priority options (canonical lowercase values for state/filter/storage)
  const queuePriorityOptions = useMemo(
    () => derivePriorityOptions(queueItems),
    [queueItems]
  );

  // Derived: workstream options
  const queueWorkstreamOptions = useMemo(
    () => deriveWorkstreamOptions(queueItems),
    [queueItems]
  );

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
      if (
        queueCommandFamilyFilter !== "all" &&
        commandFamilyValue !== queueCommandFamilyFilter
      ) {
        return false;
      }

      // Priority filter (compare canonical lowercase values)
      const priorityValue = normalizeQueuePriority(item.priorityLabel);
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
      copy.sort(
        (a, b) =>
          queuePriorityRank(a.priorityLabel) - queuePriorityRank(b.priorityLabel)
      );
    } else if (queueSortOption === "cluster") {
      copy.sort((a, b) =>
        (a.targetCluster ?? "unknown").localeCompare(b.targetCluster ?? "unknown")
      );
    } else if (queueSortOption === "activity") {
      copy.sort(
        (a, b) =>
          queueTimestampValue(b.latestTimestamp) - queueTimestampValue(a.latestTimestamp)
      );
    }
    return copy;
  }, [filteredQueue, queueSortOption]);

  // Derived: queue groups (status buckets with non-empty groups only)
  const queueGroups: QueueGroup[] = NEXT_CHECK_QUEUE_STATUS_ORDER.map((status) => ({
    status,
    label: NEXT_CHECK_QUEUE_STATUS_LABELS[status],
    items: sortedQueue.filter(
      (entry) =>
        ((entry.queueStatus as NextCheckQueueStatus) ?? "duplicate-or-stale") === status
    ),
  })).filter((group) => group.items.length > 0);

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
    // Derived queue groups
    queueGroups,
  };
};
