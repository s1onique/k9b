/**
 * useQueueFilterHandlers — extracted queue filter/reset handlers.
 *
 * Responsibilities:
 * - Toggle queue focus preset (work/review/none modes)
 * - Reset all queue filters to defaults
 * - Reset queue view state (filters + persisted storage)
 *
 * Owned by this hook:
 * - toggleQueueFocusPreset handler
 * - resetQueueFilters handler
 * - resetQueueView handler
 *
 * NOT owned by this hook:
 * - Queue filter state (useQueueState)
 * - Queue sorting/grouping (useQueueState)
 * - Queue persisted storage helpers (persistence.ts imports only)
 */
import type { Dispatch, SetStateAction } from "react";
import type { QueueFocusMode } from "../utils/selectors";
import { DEFAULT_QUEUE_VIEW_STATE, clearStoredQueueViewState } from "../utils/persistence";

export interface UseQueueFilterHandlersOptions {
  /** Set cluster filter */
  setQueueClusterFilter: Dispatch<SetStateAction<string>>;
  /** Set status filter */
  setQueueStatusFilter: Dispatch<SetStateAction<string>>;
  /** Set command family filter */
  setQueueCommandFamilyFilter: Dispatch<SetStateAction<string>>;
  /** Set priority filter */
  setQueuePriorityFilter: Dispatch<SetStateAction<string>>;
  /** Set workstream filter */
  setQueueWorkstreamFilter: Dispatch<SetStateAction<string>>;
  /** Set search text */
  setQueueSearch: Dispatch<SetStateAction<string>>;
  /** Set sort option */
  setQueueSortOption: Dispatch<SetStateAction<string>>;
  /** Set focus mode */
  setQueueFocusMode: Dispatch<SetStateAction<QueueFocusMode>>;
}

export interface UseQueueFilterHandlersResult {
  /** Toggle queue focus preset between work/review/none modes */
  toggleQueueFocusPreset: (mode: QueueFocusMode) => void;
  /** Reset all queue filters to defaults */
  resetQueueFilters: () => void;
  /** Reset queue filters and clear persisted queue view state */
  resetQueueView: () => void;
}

/**
 * useQueueFilterHandlers — manages queue filter and reset handlers.
 *
 * Extracts three handlers from App.tsx:
 * 1. toggleQueueFocusPreset: toggles between the given focus mode and "none"
 * 2. resetQueueFilters: resets all filter fields to DEFAULT_QUEUE_VIEW_STATE values
 * 3. resetQueueView: calls resetQueueFilters then clears localStorage
 *
 * Behavior preserved exactly:
 * - toggleQueueFocusPreset sets queue focus mode to mode if current !== mode, else "none"
 * - resetQueueFilters resets cluster, status, commandFamily, priority, workstream, search, sort, focus
 * - resetQueueView calls resetQueueFilters then clearStoredQueueViewState()
 */
export const useQueueFilterHandlers = (
  options: UseQueueFilterHandlersOptions
): UseQueueFilterHandlersResult => {
  const {
    setQueueClusterFilter,
    setQueueStatusFilter,
    setQueueCommandFamilyFilter,
    setQueuePriorityFilter,
    setQueueWorkstreamFilter,
    setQueueSearch,
    setQueueSortOption,
    setQueueFocusMode,
  } = options;

  /**
   * Toggle queue focus preset between work/review/none modes.
   * If current mode matches, reset to "none"; otherwise set to the given mode.
   */
  const toggleQueueFocusPreset = (mode: QueueFocusMode) => {
    setQueueFocusMode((current) => (current === mode ? "none" : mode));
  };

  /**
   * Reset all queue filters to their default values.
   * Uses DEFAULT_QUEUE_VIEW_STATE values for each filter field.
   */
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

  /**
   * Reset queue filters and clear persisted queue view state from localStorage.
   * Calls resetQueueFilters first, then clearStoredQueueViewState().
   */
  const resetQueueView = () => {
    resetQueueFilters();
    clearStoredQueueViewState();
  };

  return {
    toggleQueueFocusPreset,
    resetQueueFilters,
    resetQueueView,
  };
};
