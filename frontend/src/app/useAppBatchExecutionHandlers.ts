/**
 * useAppBatchExecutionHandlers — extracted batch execution state and handlers.
 *
 * Responsibilities:
 * - Track executing batch run ID (transient state during batch execution)
 * - Track batch execution errors (per-run-id error storage)
 * - Handle batch execution: call API, refresh runs list, refresh selected run if needed
 *
 * Owned by this hook:
 * - executingBatchRunId state
 * - batchExecutionError state
 * - handleBatchExecution handler
 *
 * NOT owned by this hook:
 * - Run selection (useAppRunSelectionHandlers)
 * - Manual execution (useAppManualExecutionHandlers)
 * - Approval (useAppApprovalHandlers)
 * - Cluster selection (useAppClusterSelectionHandlers)
 */
import { useCallback, useState } from "react";
import { runBatchExecution } from "../api";

export interface UseAppBatchExecutionHandlersOptions {
  /** Currently selected run ID (from RunControl) */
  selectedRunId: string | null;
  /** RunControl's poll function - refreshes runs list after batch execution */
  poll: () => void;
  /** RunControl's retrySelectedRun - refreshes selected run payload if selected */
  retrySelectedRun: () => void;
}

export interface UseAppBatchExecutionHandlersResult {
  /** Currently executing batch run ID (null if no batch execution in progress) */
  executingBatchRunId: string | null;
  /** Per-run-id batch execution errors */
  batchExecutionError: Record<string, string>;
  /** Handle batch execution for a run */
  handleBatchExecution: (runId: string) => Promise<void>;
  /** Clear batch execution error for a specific run */
  clearBatchExecutionError: (runId: string) => void;
}

/**
 * useAppBatchExecutionHandlers — manages batch execution lifecycle.
 *
 * Batch execution causal chain:
 * 1. User triggers batch execution on a run
 * 2. Mark run as executing (executingBatchRunId)
 * 3. Clear any previous error for this run
 * 4. Call runBatchExecution API
 * 5. Refresh runs list via poll()
 * 6. If executed run is selected, refresh its payload via retrySelectedRun()
 * 7. On error: store error per run ID
 * 8. On complete (success or failure): clear executing state
 */
export const useAppBatchExecutionHandlers = (
  options: UseAppBatchExecutionHandlersOptions
): UseAppBatchExecutionHandlersResult => {
  const { selectedRunId, poll, retrySelectedRun } = options;

  const [executingBatchRunId, setExecutingBatchRunId] = useState<string | null>(null);
  const [batchExecutionError, setBatchExecutionError] = useState<Record<string, string>>({});

  /**
   * Handle batch execution for a run.
   *
   * 1. Mark run as executing
   * 2. Clear any previous error for this run
   * 3. Execute batch via API
   * 4. Refresh runs list and selected run if needed
   * 5. Handle errors per run ID
   * 6. Clear executing state in finally
   */
  const handleBatchExecution = useCallback(
    async (runId: string) => {
      setExecutingBatchRunId(runId);
      setBatchExecutionError((prev) => {
        const next = { ...prev };
        delete next[runId];
        return next;
      });
      try {
        // Explicitly send dryRun: false for actual execution
        // The backend defaults to False, but being explicit improves clarity and debugging
        await runBatchExecution({ runId, dryRun: false });
        // Refresh runs list via RunControl's poll() - single authoritative path
        poll();
        // If the executed run is currently selected, refresh its data through RunControl
        // This ensures the execution history / next-check state is up to date
        if (selectedRunId === runId) {
          retrySelectedRun();
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : "Batch execution failed";
        setBatchExecutionError((prev) => ({
          ...prev,
          [runId]: message,
        }));
      } finally {
        setExecutingBatchRunId((current) => (current === runId ? null : current));
      }
    },
    [selectedRunId, poll, retrySelectedRun]
  );

  /**
   * Clear batch execution error for a specific run.
   */
  const clearBatchExecutionError = useCallback((runId: string) => {
    setBatchExecutionError((prev) => {
      const next = { ...prev };
      delete next[runId];
      return next;
    });
  }, []);

  return {
    executingBatchRunId,
    batchExecutionError,
    handleBatchExecution,
    clearBatchExecutionError,
  };
};