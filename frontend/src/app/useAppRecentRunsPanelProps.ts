/**
 * useAppRecentRunsPanelProps — Hook for RecentRunsPanel prop wiring
 *
 * Extracts from App.tsx:
 * - RecentRunsPanel prop construction
 *
 * Does NOT change RecentRunsPanel rendering, run selection behavior,
 * pagination, batch execution, or selected-run loading/error behavior.
 */

import type { RecentRunsPanelProps } from "../components/RunsPanel";
import type { RunsListEntry, RunsReviewFilter } from "../types";

export interface UseAppRecentRunsPanelPropsArgs {
  /** List of all runs */
  runsList: RunsListEntry[];
  /** Currently selected run ID */
  selectedRunId: string | null;
  /** Current filter value */
  runsFilter: RunsReviewFilter;
  /** Filter counts for each filter option */
  runsFilterCounts: Record<RunsReviewFilter, number>;
  /** Paginated list of runs for current filter/page */
  paginatedRunsList: RunsListEntry[];
  /** Runs filtered by current filter */
  filteredRunsList: RunsListEntry[];
  /** Whether runs list is loading */
  runsListLoading: boolean;
  /** Error message if runs list fetch failed */
  runsListError: string | null;
  /** Current page number (1-indexed) */
  runsPage: number;
  /** Total number of pages */
  totalRunsPages: number;
  /** Current page size */
  runsPageSize: number;
  /** Whether the list is following the selection */
  isRunsListFollowingSelection: boolean;
  /** Whether selected run is visible on current page */
  isSelectedRunVisibleOnCurrentRunsPage: boolean;
  /** ID of run currently being batch-executed */
  executingBatchRunId: string | null;
  /** Error keyed by run ID for batch execution */
  batchExecutionError: Record<string, string>;
  /** Handler for filter change */
  onRunsFilterChange: (filter: RunsReviewFilter) => void;
  /** Handler for page change */
  onRunsPageChange: (page: number) => void;
  /** Handler for page size change */
  onRunsPageSizeChange: (size: number) => void;
  /** Handler for run selection */
  onRunSelection: (runId: string) => void;
  /** Handler for batch execution trigger */
  onBatchExecution: (runId: string) => void;
  /** Handler to show the selected run */
  onShowSelectedRun: () => void;
  /** Handler to focus cluster for next checks */
  onFocusClusterForNextChecks: (clusterLabel?: string | null) => void;
}

/**
 * Builds RecentRunsPanel props from App.tsx state and handlers.
 *
 * Centralizes:
 * - runsListRefreshing derivation (stale-while-refresh)
 * - RecentRunsPanel prop construction
 *
 * This hook is prop-wiring only. It does not change behavior.
 */
export function useAppRecentRunsPanelProps({
  runsList,
  selectedRunId,
  runsFilter,
  runsFilterCounts,
  paginatedRunsList,
  filteredRunsList,
  runsListLoading,
  runsListError,
  runsPage,
  totalRunsPages,
  runsPageSize,
  isRunsListFollowingSelection,
  isSelectedRunVisibleOnCurrentRunsPage,
  executingBatchRunId,
  batchExecutionError,
  onRunsFilterChange,
  onRunsPageChange,
  onRunsPageSizeChange,
  onRunSelection,
  onBatchExecution,
  onShowSelectedRun,
  onFocusClusterForNextChecks,
}: UseAppRecentRunsPanelPropsArgs): RecentRunsPanelProps {
  // Stale-while-refresh: only show "Refreshing..." when loading AND we have existing rows
  // Use runsList.length (not filteredRunsList) so stale-while-refresh preserves
  // the table even when a filter returns zero results but the underlying list has rows.
  const runsListRefreshing = runsListLoading && runsList.length > 0;

  return {
    runsList,
    selectedRunId,
    runsFilter,
    runsFilterCounts,
    paginatedRunsList,
    filteredRunsList,
    runsListLoading,
    runsListError,
    runsListRefreshing,
    runsPage,
    totalRunsPages,
    runsPageSize,
    isRunsListFollowingSelection,
    isSelectedRunVisibleOnCurrentRunsPage,
    executingBatchRunId,
    batchExecutionError,
    onRunsFilterChange,
    onRunsPageChange,
    onRunsPageSizeChange,
    onRunSelection,
    onBatchExecution,
    onShowSelectedRun,
    onFocusClusterForNextChecks,
  };
}