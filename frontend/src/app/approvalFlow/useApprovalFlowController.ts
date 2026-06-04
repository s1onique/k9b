/**
 * useApprovalFlowController.ts - Thin React adapter for approval flow Elm-ish reducer.
 *
 * Wires the pure update() function and effect runner into React state via useReducer.
 * Provides a clean interface for App.tsx while keeping Elm-ish architecture.
 *
 * Architecture:
 * - State shape is exactly ApprovalFlowModel (not wrapped in UpdateResult)
 * - dispatch(msg) calls update(model, msg), updates state, then executes Cmd effects
 * - Cmd.ApproveCandidate triggers async API call, dispatching result messages back
 *
 * @module app/approvalFlow/useApprovalFlowController
 */
import { useCallback, useReducer } from "react";
import type { NextCheckPlanCandidate } from "../../types";
import type {
  ApprovalFlowModel,
  Msg,
  Cmd,
  ApproveCandidateRequest,
  ApprovalResult,
} from "./approvalFlowModel";
import { initialModel, buildApprovalRequest } from "./approvalFlowModel";
import { update, isApproving, getResult, isAnyApproving } from "./approvalFlowUpdate";
import { runEffect } from "./approvalFlowEffects";

/**
 * Reducer that wraps update() - state shape is ApprovalFlowModel (not wrapped).
 * Cmd execution happens in the dispatch wrapper, not in the reducer.
 */
function reducer(model: ApprovalFlowModel, msg: Msg): ApprovalFlowModel {
  return update(model, msg).model;
}

export interface UseApprovalFlowControllerArgs {
  selectedClusterLabel: string | null;
  refresh: () => Promise<void>;
}

export interface UseApprovalFlowControllerReturn {
  // State (from model)
  approvalResults: Record<string, ApprovalResult>;
  approvingCandidate: string | null;
  // Handlers
  handleApproveCandidate: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;
  // Helpers
  isApproving: (candidateKey: string) => boolean;
  getResult: (candidateKey: string) => ApprovalResult | undefined;
  isAnyApproving: () => boolean;
  // Clear results after refresh
  clearApprovalResults: () => void;
}

/**
 * Thin React hook that adapts the Elm-ish approval flow logic to React.
 *
 * Uses useReducer where state IS the model (not wrapped).
 * dispatch(msg) calls update(), updates state, then executes Cmd side effects.
 */
export function useApprovalFlowController({
  selectedClusterLabel,
  refresh,
}: UseApprovalFlowControllerArgs): UseApprovalFlowControllerReturn {
  // State shape is exactly ApprovalFlowModel
  const [model, dispatch] = useReducer(reducer, initialModel);

  // Dispatch wrapper that also executes Cmd side effects
  // Note: update() is called once to get the command; React's reducer handles state
  const dispatchWithEffects = useCallback(
    (msg: Msg) => {
      // Extract command from update() - React state updated via dispatch(msg)
      const { cmd } = update(model, msg);
      dispatch(msg);

      // Execute side effects from cmd
      if (cmd.type === "ApproveCandidate") {
        runEffect(cmd, dispatchWithEffects, refresh).catch(console.error);
      }
      // NoOp: nothing to do
    },
    [model, refresh]
  );

  // Handle approval - dispatch message, Cmd triggers API call
  const handleApproveCandidate = useCallback(
    async (candidate: NextCheckPlanCandidate, candidateKey: string) => {
      // Build request first to validate
      const request = buildApprovalRequest(candidate, selectedClusterLabel);
      if (!request) {
        // Dispatch error message directly
        dispatchWithEffects({
          type: "ApprovalFailed",
          candidateKey,
          summary: "Unable to determine candidate target",
        });
        return;
      }

      // Dispatch ApprovalRequested with the request - this sets approving state
      // and emits Cmd.ApproveCandidate which triggers the API call.
      // Refresh will be called by runEffect() AFTER successful approval.
      dispatchWithEffects({ type: "ApprovalRequested", candidateKey, request });
    },
    [dispatchWithEffects, selectedClusterLabel]
  );

  // Clear approval results
  const clearApprovalResults = useCallback(() => {
    dispatchWithEffects({ type: "ClearResults" });
  }, [dispatchWithEffects]);

  return {
    // State from model
    approvalResults: model.approvalResults,
    approvingCandidate: model.approvingCandidate,
    // Handlers
    handleApproveCandidate,
    // State accessors
    isApproving: (key: string) => isApproving(model, key),
    getResult: (key: string) => getResult(model, key),
    isAnyApproving: () => isAnyApproving(model),
    // Clear
    clearApprovalResults,
  };
}