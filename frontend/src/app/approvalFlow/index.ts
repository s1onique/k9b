/**
 * approvalFlow - Elm-ish approval flow state machine.
 *
 * @module app/approvalFlow
 */

// Model types
export type {
  ApprovalFlowModel,
  Msg,
  Cmd,
  ApprovalResult,
  ApproveCandidateRequest,
  ApprovalApiResponse,
  UpdateResult,
} from "./approvalFlowModel";
export { initialModel, buildApprovalRequest } from "./approvalFlowModel";

// Pure update function
export { update, createInitialModel, isApproving, getResult, isAnyApproving } from "./approvalFlowUpdate";

// Effect runner
export { runEffect } from "./approvalFlowEffects";

// React adapter hook
export { useApprovalFlowController } from "./useApprovalFlowController";
export type {
  UseApprovalFlowControllerArgs,
  UseApprovalFlowControllerReturn,
} from "./useApprovalFlowController";