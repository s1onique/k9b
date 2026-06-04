/**
 * manualExecution - Elm-ish manual execution state machine.
 *
 * @module app/manualExecution
 */

// Model types
export type {
  ManualExecutionModel,
  Msg,
  Cmd,
  ExecutionResult,
  ExecutionErrorResult,
  ExecuteCandidateRequest,
  UpdateResult,
} from "./manualExecutionModel";
export { initialModel } from "./manualExecutionModel";

// Pure update function
export { update, createInitialModel, isExecuting, getResult, isAnyExecuting } from "./manualExecutionUpdate";

// Effect runner
export { runEffect, runHighlightEffect } from "./manualExecutionEffects";

// React adapter hook
export { useManualExecutionController } from "./useManualExecutionController";
export type {
  UseManualExecutionControllerArgs,
  UseManualExecutionControllerReturn,
} from "./useManualExecutionController";