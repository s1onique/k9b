/**
 * localStorage persistence helpers for queue view state.
 */

import type { QueueViewState } from "./types";
import {
  DEFAULT_QUEUE_VIEW_STATE,
  QUEUE_VIEW_STORAGE_KEY,
} from "./constants";
import {
  isQueueStatusFilterValue,
  isQueueSortOptionValue,
  isQueueFocusModeValue,
} from "./validation";

/** Read queue view state from localStorage. Falls back to defaults. */
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

/** Persist queue view state to localStorage. */
export const persistQueueViewState = (state: QueueViewState) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(QUEUE_VIEW_STORAGE_KEY, JSON.stringify(state));
};
