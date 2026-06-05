/**
 * batchExecutionUpdate.ts - Pure Elm-ish update function for batch execution.
 *
 * Contains the pure state transition logic (no side effects, no async).
 * All effects are returned as Cmd and executed by the effect runner.
 *
 * @module app/batchExecution/batchExecutionUpdate
 */
import type { BatchExecutionModel, Msg, Cmd, UpdateResult } from "./batchExecutionModel";
import { initialModel } from "./batchExecutionModel";

/**
 * Pure state transition function following Elm architecture.
 *
 * Given a model and a message, returns a new model and optionally a command
 * to execute (side effects handled outside update).
 *
 * @param model - Current model state
 * @param msg - Message describing what happened
 * @returns UpdateResult with new model and command to execute
 */
export function update(model: BatchExecutionModel, msg: Msg): UpdateResult {
  switch (msg.type) {
    case "BatchExecutionRequested": {
      // User triggered batch execution - set executing state and clear any previous error
      // Create a new error map without the runId being executed
      const { [msg.runId]: _removed, ...remainingErrors } = model.batchExecutionError;
      return {
        model: {
          ...model,
          executingBatchRunId: msg.runId,
          batchExecutionError: remainingErrors,
        },
        cmd: { type: "ExecuteBatch", runId: msg.runId },
      };
    }

    case "BatchExecutionSucceeded": {
      // API call succeeded - clear executing state
      return {
        model: {
          ...model,
          executingBatchRunId: null,
        },
        cmd: { type: "NoOp" },
      };
    }

    case "BatchExecutionFailed": {
      // API call failed - store error and clear executing state
      return {
        model: {
          ...model,
          executingBatchRunId: null,
          batchExecutionError: {
            ...model.batchExecutionError,
            [msg.runId]: msg.error,
          },
        },
        cmd: { type: "NoOp" },
      };
    }

    case "ClearBatchExecutionError": {
      // Clear error for a specific run
      const { [msg.runId]: _removed, ...remainingErrors } = model.batchExecutionError;
      return {
        model: {
          ...model,
          batchExecutionError: remainingErrors,
        },
        cmd: { type: "NoOp" },
      };
    }

    default: {
      // Exhaustiveness check - if we get here, TypeScript will warn about unhandled cases
      const _exhaustive: never = msg;
      return { model, cmd: { type: "NoOp" } };
    }
  }
}

/**
 * Create the initial model for a new reducer instance.
 * Useful for testing and initial hook state.
 */
export function createInitialModel(): BatchExecutionModel {
  return { ...initialModel };
}

/**
 * Check if a run is currently being executed.
 */
export function isExecuting(model: BatchExecutionModel, runId: string): boolean {
  return model.executingBatchRunId === runId;
}

/**
 * Get the error for a specific run.
 */
export function getError(model: BatchExecutionModel, runId: string): string | undefined {
  return model.batchExecutionError[runId];
}

/**
 * Check if any batch execution is in progress.
 */
export function isAnyExecuting(model: BatchExecutionModel): boolean {
  return model.executingBatchRunId !== null;
}
