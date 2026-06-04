/**
 * approvalFlowUpdate.ts - Pure Elm-ish update function for approval flow.
 *
 * Contains the pure state transition logic (no side effects, no async).
 * All effects are returned as Cmd and executed by the effect runner.
 *
 * @module app/approvalFlow/approvalFlowUpdate
 */
import type { ApprovalFlowModel, Msg, Cmd, UpdateResult, ApprovalResult } from "./approvalFlowModel";
import { initialModel } from "./approvalFlowModel";

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
export function update(model: ApprovalFlowModel, msg: Msg): UpdateResult {
  switch (msg.type) {
    case "ApprovalRequested": {
      // User triggered approval - set approving state and emit ApproveCandidate command
      return {
        model: {
          ...model,
          approvingCandidate: msg.candidateKey,
        },
        cmd: { type: "ApproveCandidate", candidateKey: msg.candidateKey, request: msg.request },
      };
    }

    case "ApprovalSucceeded": {
      // API call succeeded - store result and clear approving state
      const result = msg.result;
      const approvalResult: ApprovalResult = {
        status: result.status === "success" ? "success" : "error",
        summary: result.summary || (result.status === "success" ? "Candidate approved" : "Approval failed"),
        artifactPath: result.artifactPath,
        approvalTimestamp: result.approvalTimestamp,
      };
      return {
        model: {
          ...model,
          approvingCandidate: null,
          approvalResults: {
            ...model.approvalResults,
            [msg.candidateKey]: approvalResult,
          },
        },
        cmd: { type: "NoOp" },
      };
    }

    case "ApprovalFailed": {
      // API call failed - store error and clear approving state
      const approvalResult: ApprovalResult = {
        status: "error",
        summary: msg.summary,
      };
      return {
        model: {
          ...model,
          approvingCandidate: null,
          approvalResults: {
            ...model.approvalResults,
            [msg.candidateKey]: approvalResult,
          },
        },
        cmd: { type: "NoOp" },
      };
    }

    case "ClearResults": {
      // Clear all approval results (e.g., after refresh reconciliation)
      return {
        model: {
          ...model,
          approvalResults: {},
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
export function createInitialModel(): ApprovalFlowModel {
  return { ...initialModel };
}

/**
 * Check if a candidate is currently being approved.
 */
export function isApproving(model: ApprovalFlowModel, candidateKey: string): boolean {
  return model.approvingCandidate === candidateKey;
}

/**
 * Get the result for a specific candidate.
 */
export function getResult(model: ApprovalFlowModel, candidateKey: string): ApprovalResult | undefined {
  return model.approvalResults[candidateKey];
}

/**
 * Check if any approval is in progress.
 */
export function isAnyApproving(model: ApprovalFlowModel): boolean {
  return model.approvingCandidate !== null;
}