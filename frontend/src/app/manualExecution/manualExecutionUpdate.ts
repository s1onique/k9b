/**
 * manualExecutionUpdate.ts - Pure Elm-ish update function for manual execution.
 *
 * Contains the pure state transition logic (no side effects, no async).
 * All effects are returned as Cmd and executed by the effect runner.
 *
 * @module app/manualExecution/manualExecutionUpdate
 */
import type { ManualExecutionModel, Msg, Cmd, UpdateResult, ExecutionResult } from "./manualExecutionModel";
import { initialModel } from "./manualExecutionModel";

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
export function update(model: ManualExecutionModel, msg: Msg): UpdateResult {
  switch (msg.type) {
    case "ExecuteRequested": {
      // User triggered execution - set executing state and emit ExecuteCandidate command
      return {
        model: {
          ...model,
          executingCandidate: msg.candidateKey,
        },
        cmd: { type: "ExecuteCandidate", candidateKey: msg.candidateKey, request: msg.request },
      };
    }

    case "ExecutionSucceeded": {
      // API call succeeded - store result, clear executing state, track succeeded key
      return {
        model: {
          ...model,
          executingCandidate: null,
          lastSucceededKey: msg.candidateKey,
          executionResults: {
            ...model.executionResults,
            [msg.candidateKey]: msg.result,
          },
        },
        cmd: { type: "NoOp" },
      };
    }

    case "ExecutionFailed": {
      // API call failed - store error and clear executing state
      return {
        model: {
          ...model,
          executingCandidate: null,
          executionResults: {
            ...model.executionResults,
            [msg.candidateKey]: msg.error,
          },
        },
        cmd: { type: "NoOp" },
      };
    }

    case "ClearResults": {
      // Clear all execution results (e.g., after refresh reconciliation)
      return {
        model: {
          ...model,
          executionResults: {},
        },
        cmd: { type: "NoOp" },
      };
    }

    case "ConsumeLastSucceededKey": {
      // Consume and clear the last succeeded candidate key for highlighting
      const key = model.lastSucceededKey;
      return {
        model: {
          ...model,
          lastSucceededKey: null,
        },
        cmd: key ? { type: "HighlightCandidate", key } : { type: "NoOp" },
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
export function createInitialModel(): ManualExecutionModel {
  return { ...initialModel };
}

/**
 * Check if a candidate is currently being executed.
 */
export function isExecuting(model: ManualExecutionModel, candidateKey: string): boolean {
  return model.executingCandidate === candidateKey;
}

/**
 * Get the result for a specific candidate.
 */
export function getResult(model: ManualExecutionModel, candidateKey: string): ExecutionResult | undefined {
  return model.executionResults[candidateKey];
}

/**
 * Check if any execution is in progress.
 */
export function isAnyExecuting(model: ManualExecutionModel): boolean {
  return model.executingCandidate !== null;
}