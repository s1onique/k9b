/**
 * Constants for the queue state module.
 */

import type {
  NextCheckQueueStatus,
  QueueFocusMode,
  QueueSortOption,
  QueueViewState,
} from "./types";

/** localStorage key for persisting queue view state. */
export const QUEUE_VIEW_STORAGE_KEY = "dashboard-queue-view-state";

/** Label map for queue status values. */
export const NEXT_CHECK_QUEUE_STATUS_LABELS: Record<NextCheckQueueStatus, string> = {
  "approved-ready": "Approved & ready",
  "safe-ready": "Safe to automate",
  "approval-needed": "Approval needed",
  "failed": "Failed executions",
  "completed": "Completed",
  "duplicate-or-stale": "Duplicate / stale",
};

/** Canonical ordering for queue status values. */
export const NEXT_CHECK_QUEUE_STATUS_ORDER: NextCheckQueueStatus[] = [
  "approved-ready",
  "safe-ready",
  "approval-needed",
  "failed",
  "completed",
  "duplicate-or-stale",
];

/** Available sort options for the queue view. */
export const QUEUE_SORT_OPTIONS = [
  { label: "Backend order", value: "default" },
  { label: "Priority", value: "priority" },
  { label: "Cluster", value: "cluster" },
  { label: "Latest activity", value: "activity" },
] as const;

/** Derived type for sort option values. */
export type QueueSortOptionValue = (typeof QUEUE_SORT_OPTIONS)[number]["value"];

/** Priority rank map (lower = higher priority). */
export const QUEUE_PRIORITY_ORDER: Record<string, number> = {
  primary: 0,
  secondary: 1,
  fallback: 2,
};

/** Focus mode filter maps status to focus mode. */
export const QUEUE_FOCUS_FILTERS: Record<QueueFocusMode, NextCheckQueueStatus[]> = {
  none: [],
  work: ["approved-ready", "safe-ready", "failed"],
  review: ["approval-needed", "duplicate-or-stale"],
};

/** Valid status filter values (including "all"). */
export const QUEUE_STATUS_FILTER_VALUES = new Set<NextCheckQueueStatus | "all">([
  "all",
  ...NEXT_CHECK_QUEUE_STATUS_ORDER,
]);

/** Valid sort option values. */
export const QUEUE_SORT_VALUES: QueueSortOption[] = QUEUE_SORT_OPTIONS.map(
  (option) => option.value
);

/** Valid focus mode values. */
export const QUEUE_FOCUS_MODE_VALUES: QueueFocusMode[] = ["none", "work", "review"];

/** Default queue view state (matches QueueViewState shape). */
export const DEFAULT_QUEUE_VIEW_STATE: QueueViewState = {
  clusterFilter: "all",
  statusFilter: "all",
  commandFamilyFilter: "all",
  priorityFilter: "all",
  workstreamFilter: "all",
  searchText: "",
  focusMode: "none",
  sortOption: "default",
};
