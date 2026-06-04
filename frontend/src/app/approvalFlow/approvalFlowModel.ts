/**
 * approvalFlowModel.ts - Elm-ish model types for approval flow.
 *
 * Defines the core state, messages, and commands for the approval
 * feature-local Elm-ish reducer.
 *
 * @module app/approvalFlow/approvalFlowModel
 */
import type { NextCheckPlanCandidate } from "../../types";

/**
 * Approval result shape - mirrors the shape used by ClusterNextCheckPlanSection.
 */
export interface ApprovalResult {
  status: "success" | "error";
  summary: string;
  artifactPath?: string | null;
  approvalTimestamp?: string | null;
}

/**
 * Request parameters for candidate approval.
 */
export interface ApproveCandidateRequest {
  candidateId?: string;
  candidateIndex?: number;
  clusterLabel: string;
}

/**
 * Feature-local state model for approval flow.
 *
 * Owns:
 * - approvalResults: map of candidate keys to approval results
 * - approvingCandidate: currently approving candidate key (null when idle)
 */
export interface ApprovalFlowModel {
  approvalResults: Record<string, ApprovalResult>;
  approvingCandidate: string | null;
}

/**
 * Initial state for the approval flow reducer.
 */
export const initialModel: ApprovalFlowModel = {
  approvalResults: {},
  approvingCandidate: null,
};

/**
 * Discriminated union of all messages that can occur in the approval flow.
 */
export type Msg =
  /** User requested approval for a candidate */
  | { type: "ApprovalRequested"; candidateKey: string; request: ApproveCandidateRequest }
  /** API call succeeded */
  | { type: "ApprovalSucceeded"; candidateKey: string; result: ApprovalApiResponse }
  /** API call failed */
  | { type: "ApprovalFailed"; candidateKey: string; summary: string }
  /** Clear all approval results (e.g., after refresh reconciliation) */
  | { type: "ClearResults" };

/**
 * Response from the approval API.
 */
export interface ApprovalApiResponse {
  status: "success" | "error";
  summary?: string;
  artifactPath?: string | null;
  approvalTimestamp?: string | null;
}

/**
 * Discriminated union of all side effects (commands) that the reducer can emit.
 *
 * Effects stay OUTSIDE update() and are executed by the effect runner.
 */
export type Cmd =
  /** Approve a next-check candidate via the API */
  | { type: "ApproveCandidate"; candidateKey: string; request: ApproveCandidateRequest }
  /** No-op command for states that don't need side effects */
  | { type: "NoOp" };

/**
 * Result from update() - pure state transition.
 */
export type UpdateResult = {
  model: ApprovalFlowModel;
  cmd: Cmd;
};

/**
 * Build approval request from a candidate.
 */
export function buildApprovalRequest(
  candidate: NextCheckPlanCandidate,
  selectedClusterLabel: string | null
): ApproveCandidateRequest | null {
  const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
  const candidateId = candidate.candidateId?.trim() ? candidate.candidateId : undefined;
  const candidateIndex = candidate.candidateIndex;

  if (!targetLabel || (candidateIndex == null && !candidateId)) {
    return null;
  }

  return {
    candidateId,
    candidateIndex: candidateIndex ?? undefined,
    clusterLabel: targetLabel,
  };
}