/**
 * batchExecutionEffects.ts - Effect runner for batch execution commands.
 *
 * Contains async side effects that cannot be in the pure update() function.
 * These effects dispatch results back to the reducer.
 *
 * @module app/batchExecution/batchExecutionEffects
 */
import type { Cmd, Msg } from "./batchExecutionModel";
import { runBatchExecution } from "../../api";

export interface BatchExecutionRefreshCallbacks {
  poll: () => void;
  retrySelectedRun: () => void;
}

/**
 * Effect runner that executes a command and dispatches results.
 *
 * @param cmd - The command to execute
 * @param dispatch - Callback to dispatch messages back to the reducer
 * @param callbacks - Refresh callbacks for after successful execution
 * @param selectedRunId - Currently selected run ID
 */
export async function runEffect(
  cmd: Cmd,
  dispatch: (msg: Msg) => void,
  callbacks: BatchExecutionRefreshCallbacks,
  selectedRunId: string | null
): Promise<void> {
  switch (cmd.type) {
    case "ExecuteBatch": {
      const { runId } = cmd;

      // Step 1: Call batch execution API
      try {
        await runBatchExecution({ runId, dryRun: false });
        dispatch({ type: "BatchExecutionSucceeded", runId });
      } catch (err) {
        // Batch execution failed - dispatch failure and do not refresh
        const message = err instanceof Error ? err.message : "Batch execution failed";
        dispatch({ type: "BatchExecutionFailed", runId, error: message });
        return;
      }

      // Step 2: Refresh runs list after successful execution
      try {
        callbacks.poll();
      } catch {
        // Refresh errors are non-fatal after batch execution succeeds.
        // Do not dispatch anything - the execution already succeeded.
      }

      // Step 3: If the executed run is selected, refresh its payload
      if (selectedRunId === runId) {
        try {
          callbacks.retrySelectedRun();
        } catch {
          // Refresh errors are non-fatal after batch execution succeeds.
          // Do not dispatch anything - the execution already succeeded.
        }
      }

      break;
    }
    case "NoOp": {
      // No-op, nothing to do
      break;
    }
  }
}
