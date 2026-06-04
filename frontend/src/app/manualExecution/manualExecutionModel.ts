/**
 * manualExecutionModel.ts - Elm-ish model types for manual execution flow.
 *
 * Defines the core state, messages, and commands for the manual execution
 * feature-local Elm-ish reducer.
 *
 * @module app/manualExecution/manualExecutionModel
 */
import type { NextCheckExecutionResponse } from "../../types";

/**
 * Error result shape for execution failures.
 */
export interface ExecutionErrorResult {
  status: "error";
  summary: string;
  blockingReason?: string | null;
}

/**
 * Union type for execution results (success or error).
 */
export type ExecutionResult = NextCheckExecutionResponse | ExecutionErrorResult;

/**
 * Feature-local state model for manual execution.
 *
 * Owns:
 * - executionResults: map of candidate keys to execution results
 * - executingCandidate: currently executing candidate key (null when idle)
 * - lastSucceededKey: last candidate key that successfully completed (for highlighting)
 */
export interface ManualExecutionModel {
  executionResults: Record<string, ExecutionResult>;
  executingCandidate: string | null;
  lastSucceededKey: string | null;
}

/**
 * Initial state for the manual execution reducer.
 */
export const initialModel: ManualExecutionModel = {
  executionResults: {},
  executingCandidate: null,
  lastSucceededKey: null,
};

/**
 * Discriminated union of all messages that can occur in the manual execution flow.
 */
export type Msg =
  /** User requested execution for a candidate with the built request */
  | { type: "ExecuteRequested"; candidateKey: string; request: ExecuteCandidateRequest }
  /** API call succeeded */
  | { type: "ExecutionSucceeded"; candidateKey: string; result: NextCheckExecutionResponse }
  /** API call failed */
  | { type: "ExecutionFailed"; candidateKey: string; error: ExecutionErrorResult }
  /** Clear all execution results (e.g., after refresh reconciliation) */
  | { type: "ClearResults" }
  /** Consume and return the last succeeded key for highlighting */
  | { type: "ConsumeLastSucceededKey" };

/**
 * Discriminated union of all side effects (commands) that the reducer can emit.
 *
 * Effects stay OUTSIDE update() and are executed by the effect runner.
 */
export type Cmd =
  /** Execute a next-check candidate via the API */
  | { type: "ExecuteCandidate"; candidateKey: string; request: ExecuteCandidateRequest }
  /** Highlight a queue card after successful execution */
  | { type: "HighlightCandidate"; key: string }
  /** No-op command for states that don't need side effects */
  | { type: "NoOp" };

/**
 * Request parameters for candidate execution.
 */
export interface ExecuteCandidateRequest {
  candidateId?: string;
  candidateIndex?: number;
  clusterLabel: string;
  planArtifactPath?: string | null;
}

/**
 * Result from update() - pure state transition.
 */
export type UpdateResult = {
  model: ManualExecutionModel;
  cmd: Cmd;
};