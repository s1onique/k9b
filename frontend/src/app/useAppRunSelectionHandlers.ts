/**
 * useAppRunSelectionHandlers — extracted run selection coordination handlers.
 *
 * Responsibilities:
 * - Coordinate run selection through RunControl (fetching run payload, updating header)
 * - Keep the Recent Runs list page in sync with the selected run
 *
 * Owned by this hook:
 * - handleRunSelectionViaRunControl: wires runControlSelectRun + navigateToPageContainingRun
 *
 * NOT owned by this hook (already extracted elsewhere):
 * - clickLatest: from useRunControl
 * - handleShowSelectedRun: from useRunSelection
 * - navigateToPageContainingRun: from useRunSelection
 * - runControlSelectRun: from useRunControl
 */
import { useCallback } from "react";

export interface UseAppRunSelectionHandlersOptions {
  /** RunControl's selectRun function */
  runControlSelectRun: (runId: string) => void;
  /** Navigate to the page containing the given run */
  navigateToPageContainingRun: (runId: string | null) => void;
}

export interface UseAppRunSelectionHandlersResult {
  /** Handle run selection via RunControl - selects run and navigates to its page */
  handleRunSelectionViaRunControl: (runId: string) => void;
}

/**
 * useAppRunSelectionHandlers — coordinates run selection through RunControl
 * and list navigation.
 *
 * Run selection causal chain:
 * 1. runControlSelectRun triggers RunControl to fetch /api/run for the selected run
 * 2. navigateToPageContainingRun keeps the Recent Runs list page in sync
 *
 * RunControl owns selected-run data; useRunSelection owns list navigation.
 * This hook wires these two systems together for user-initiated run selection.
 */
export const useAppRunSelectionHandlers = (
  options: UseAppRunSelectionHandlersOptions
): UseAppRunSelectionHandlersResult => {
  const { runControlSelectRun, navigateToPageContainingRun } = options;

  /**
   * Handle run selection via RunControl.
   * 
   * 1. Select run in RunControl (fetches run payload, updates header)
   * 2. Navigate to the page containing the selected run so it becomes visible in the list
   */
  const handleRunSelectionViaRunControl = useCallback(
    (runId: string) => {
      // Select run in RunControl (fetches run payload, updates header)
      runControlSelectRun(runId);
      // Navigate to the page containing the selected run so it becomes visible in the list
      navigateToPageContainingRun(runId);
    },
    [runControlSelectRun, navigateToPageContainingRun]
  );

  return {
    handleRunSelectionViaRunControl,
  };
};