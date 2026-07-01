/**
 * Types for the queue state module.
 */
import type { NextCheckQueueItem } from "../../types";

// Re-export for convenience
export type { NextCheckQueueItem };

/** Status values for items in the next-check queue. */
export type NextCheckQueueStatus =
  | "approved-ready"
  | "safe-ready"
  | "approval-needed"
  | "failed"
  | "completed"
  | "duplicate-or-stale";

/** Focus mode for the queue view. */
export type QueueFocusMode = "none" | "work" | "review";

/** Sort option for queue ordering. */
export type QueueSortOption = "default" | "priority" | "cluster" | "activity";

/** Queue view state shape (persisted to localStorage). */
export type QueueViewState = {
  clusterFilter: string;
  statusFilter: NextCheckQueueStatus | "all";
  commandFamilyFilter: string;
  priorityFilter: string;
  workstreamFilter: string;
  searchText: string;
  focusMode: QueueFocusMode;
  sortOption: QueueSortOption;
};

/** Parameters for the useQueueState hook. */
export interface UseQueueStateParams {
  runQueue: NextCheckQueueItem[] | null | undefined;
}

/** A group of queue items sharing the same status. */
export type QueueGroup = {
  status: NextCheckQueueStatus;
  label: string;
  items: NextCheckQueueItem[];
};

/** Return type for the useQueueState hook. */
export interface UseQueueStateResult {
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
  // Derived queue groups
  queueGroups: QueueGroup[];
}

/** Backward-compatible alias for UseQueueStateResult. */
export type UseQueueStateReturn = UseQueueStateResult;
