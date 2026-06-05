/**
 * batchExecutionModel.ts - Elm-ish model types for batch execution flow.
 *
 * Defines the core state, messages, and commands for the batch execution
 * feature-local Elm-ish reducer.
 *
 * @module app/batchExecution/batchExecutionModel
 */

/**
 * Feature-local state model for batch execution.
 *
 * Owns:
 * - executingBatchRunId: currently executing batch run ID (null when idle)
 * - batchExecutionError: map of run IDs to error messages
 */
export interface BatchExecutionModel {
  executingBatchRunId: string | null;
  batchExecutionError: Record<string, string>;
}

/**
 * Initial state for the batch execution reducer.
 */
export const initialModel: BatchExecutionModel = {
  executingBatchRunId: null,
  batchExecutionError: {},
};

/**
 * Discriminated union of all messages that can occur in the batch execution flow.
 */
export type Msg =
  /** User requested batch execution for a run */
  | { type: "BatchExecutionRequested"; runId: string }
  /** API call succeeded */
  | { type: "BatchExecutionSucceeded"; runId: string }
  /** API call failed */
  | { type: "BatchExecutionFailed"; runId: string; error: string }
  /** Clear batch execution error for a specific run */
  | { type: "ClearBatchExecutionError"; runId: string };

/**
 * Discriminated union of all side effects (commands) that the reducer can emit.
 *
 * Effects stay OUTSIDE update() and are executed by the effect runner.
 */
export type Cmd =
  /** Execute batch execution for a run via the API */
  | { type: "ExecuteBatch"; runId: string }
  /** No-op command for states that don't need side effects */
  | { type: "NoOp" };

/**
 * Request parameters for batch execution.
 */
export interface BatchExecutionRequest {
  runId: string;
}

/**
 * Result from update() - pure state transition.
 */
export type UpdateResult = {
  model: BatchExecutionModel;
  cmd: Cmd;
};
