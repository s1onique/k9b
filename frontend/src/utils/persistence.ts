/**
 * localStorage persistence helpers for App.tsx UI state.
 * Extracted from App.tsx as part of the App.tsx split epic.
 *
 * Behavior contract:
 * - All functions guard against SSR (typeof window === "undefined").
 * - Validation functions use the same type guards as selectors.ts.
 * - Fallback defaults match the original App.tsx values exactly.
 * - No hooks, no JSX, no side effects beyond localStorage.
 */
import type { NextCheckQueueStatus, QueueFocusMode, QueueSortOption, RunsReviewFilter } from "./selectors";
import {
  isRunsReviewFilterValue,
  NEXT_CHECK_QUEUE_STATUS_ORDER,
  QUEUE_SORT_OPTIONS,
} from "./selectors";

// ==========================================================================
// Storage keys
// ==========================================================================

export const QUEUE_VIEW_STORAGE_KEY = "dashboard-queue-view-state";
export const RUNS_REVIEW_FILTER_STORAGE_KEY = "dashboard-runs-review-filter";
export const SELECTED_RUN_STORAGE_KEY = "dashboard-selected-run-id";
export const RUNS_PAGE_SIZE_STORAGE_KEY = "dashboard-runs-page-size";

// ==========================================================================
// Runs review filter persistence
// ==========================================================================

const DEFAULT_RUNS_REVIEW_FILTER: RunsReviewFilter = "all";

export const readStoredRunsReviewFilter = (): RunsReviewFilter => {
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

export const persistRunsReviewFilter = (value: RunsReviewFilter) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(RUNS_REVIEW_FILTER_STORAGE_KEY, value);
};

// ==========================================================================
// Selected run ID persistence
// ==========================================================================

export const readStoredSelectedRunId = (): string | null => {
  if (typeof window === "undefined") {
    return null;
  }
  const stored = window.localStorage.getItem(SELECTED_RUN_STORAGE_KEY);
  if (!stored) {
    return null;
  }
  return stored;
};

export const persistSelectedRunId = (runId: string | null) => {
  if (typeof window === "undefined") {
    return;
  }
  if (runId) {
    window.localStorage.setItem(SELECTED_RUN_STORAGE_KEY, runId);
  } else {
    window.localStorage.removeItem(SELECTED_RUN_STORAGE_KEY);
  }
};

// ==========================================================================
// Runs page size persistence
// ==========================================================================

const DEFAULT_RUNS_PAGE_SIZE = 5;
const MAX_RUNS_PAGE_SIZE = 20;
const RUNS_PAGE_SIZE_OPTIONS = [5, 10, 20] as const;

export const isRunsPageSizeValue = (value: unknown): value is (typeof RUNS_PAGE_SIZE_OPTIONS)[number] =>
  typeof value === "number" && RUNS_PAGE_SIZE_OPTIONS.includes(value as (typeof RUNS_PAGE_SIZE_OPTIONS)[number]);

export const readStoredRunsPageSize = (): number => {
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

export const persistRunsPageSize = (value: number) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(RUNS_PAGE_SIZE_STORAGE_KEY, String(value));
};

// ==========================================================================
// Queue view state persistence
// ==========================================================================

const QUEUE_STATUS_FILTER_VALUES = new Set<NextCheckQueueStatus | "all">([
  "all",
  ...NEXT_CHECK_QUEUE_STATUS_ORDER,
]);
const QUEUE_SORT_VALUES = QUEUE_SORT_OPTIONS.map((option) => option.value);
const QUEUE_FOCUS_MODE_VALUES: QueueFocusMode[] = ["none", "work", "review"];

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

const isQueueStatusFilterValue = (value: unknown): value is NextCheckQueueStatus | "all" =>
  typeof value === "string" && QUEUE_STATUS_FILTER_VALUES.has(value as NextCheckQueueStatus | "all");

const isQueueSortOptionValue = (value: unknown): value is QueueSortOption =>
  typeof value === "string" && QUEUE_SORT_VALUES.includes(value as QueueSortOption);

const isQueueFocusModeValue = (value: unknown): value is QueueFocusMode =>
  typeof value === "string" && QUEUE_FOCUS_MODE_VALUES.includes(value as QueueFocusMode);

export const readStoredQueueViewState = (): QueueViewState => {
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

export const persistQueueViewState = (state: QueueViewState) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(QUEUE_VIEW_STORAGE_KEY, JSON.stringify(state));
};

export const clearStoredQueueViewState = () => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(QUEUE_VIEW_STORAGE_KEY);
};