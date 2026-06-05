/**
 * useBatchExecutionController.ts - Thin React adapter for batch execution Elm-ish reducer.
 *
 * Wires the pure update() function and effect runner into React state via useReducer.
 * Provides a clean interface for App.tsx while keeping Elm-ish architecture.
 *
 * Architecture:
 * - State shape is exactly BatchExecutionModel (not wrapped in UpdateResult)
 * - dispatch(msg) calls update(model, msg), updates state, then executes Cmd effects
 * - Cmd.ExecuteBatch triggers async API call, dispatching result messages back
 *
 * @module app/batchExecution/useBatchExecutionController
 */
import { useCallback, useReducer } from "react";
import type { BatchExecutionModel, Msg, Cmd } from "./batchExecutionModel";
import { initialModel } from "./batchExecutionModel";
import { update, isExecuting, getError, isAnyExecuting } from "./batchExecutionUpdate";
import { runEffect, BatchExecutionRefreshCallbacks } from "./batchExecutionEffects";

/**
 * Reducer that wraps update() - state shape is BatchExecutionModel (not wrapped).
 * Cmd execution happens in the dispatch wrapper, not in the reducer.
 */
function reducer(model: BatchExecutionModel, msg: Msg): BatchExecutionModel {
  return update(model, msg).model;
}

export interface UseBatchExecutionControllerArgs {
  selectedRunId: string | null;
  callbacks: BatchExecutionRefreshCallbacks;
}

export interface UseBatchExecutionControllerReturn {
  // State (from model)
  executingBatchRunId: string | null;
  batchExecutionError: Record<string, string>;
  // Handlers
  handleBatchExecution: (runId: string) => Promise<void>;
  // State accessors
  isExecuting: (runId: string) => boolean;
  getError: (runId: string) => string | undefined;
  isAnyExecuting: () => boolean;
  // Clear error for a specific run
  clearBatchExecutionError: (runId: string) => void;
}

/**
 * Thin React hook that adapts the Elm-ish batch execution logic to React.
 *
 * Uses useReducer where state IS the model (not wrapped).
 * dispatch(msg) calls update(), updates state, then executes Cmd side effects.
 */
export function useBatchExecutionController({
  selectedRunId,
  callbacks,
}: UseBatchExecutionControllerArgs): UseBatchExecutionControllerReturn {
  // State shape is exactly BatchExecutionModel
  const [model, dispatch] = useReducer(reducer, initialModel);

  // Dispatch wrapper that also executes Cmd side effects
  // Note: update() is called once to get the command; React's reducer handles state
  const dispatchWithEffects = useCallback(
    (msg: Msg) => {
      // Extract command from update() - React state updated via dispatch(msg)
      const { cmd } = update(model, msg);
      dispatch(msg);

      // Execute side effects from cmd
      if (cmd.type === "ExecuteBatch") {
        runEffect(cmd, dispatchWithEffects, callbacks, selectedRunId).catch(console.error);
      }
      // NoOp: nothing to do
    },
    [model, callbacks, selectedRunId]
  );

  // Handle batch execution - dispatch message, Cmd triggers API call
  const handleBatchExecution = useCallback(
    async (runId: string) => {
      dispatchWithEffects({ type: "BatchExecutionRequested", runId });
    },
    [dispatchWithEffects]
  );

  // Clear batch execution error for a specific run
  const clearBatchExecutionError = useCallback(
    (runId: string) => {
      dispatchWithEffects({ type: "ClearBatchExecutionError", runId });
    },
    [dispatchWithEffects]
  );

  return {
    // State from model
    executingBatchRunId: model.executingBatchRunId,
    batchExecutionError: model.batchExecutionError,
    // Handlers
    handleBatchExecution,
    // State accessors
    isExecuting: (runId: string) => isExecuting(model, runId),
    getError: (runId: string) => getError(model, runId),
    isAnyExecuting: () => isAnyExecuting(model),
    // Clear error
    clearBatchExecutionError,
  };
}
