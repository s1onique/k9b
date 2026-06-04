/**
 * useManualExecutionController.ts - Thin React adapter for manual execution Elm-ish reducer.
 *
 * Wires the pure update() function and effect runner into React state via useReducer.
 * Provides a clean interface for App.tsx while keeping Elm-ish architecture.
 *
 * Architecture:
 * - State shape is exactly ManualExecutionModel (not wrapped in UpdateResult)
 * - dispatch(msg) calls update(model, msg), updates state, then executes Cmd effects
 * - Cmd.ExecuteCandidate triggers async API call, dispatching result messages back
 *
 * @module app/manualExecution/useManualExecutionController
 */
import { useCallback, useReducer } from "react";
import type { NextCheckPlanCandidate } from "../../types";
import { isItemExecuted } from "../../utils";
import { humanizeReason, ALLOWED_MANUAL_FAMILIES } from "../../utils/selectors";
import type {
  ManualExecutionModel,
  Msg,
  Cmd,
  ExecuteCandidateRequest,
  ExecutionResult,
} from "./manualExecutionModel";
import { initialModel } from "./manualExecutionModel";
import { update, isExecuting, getResult, isAnyExecuting } from "./manualExecutionUpdate";
import { runEffect, runHighlightEffect } from "./manualExecutionEffects";

/**
 * Reducer that wraps update() - state shape is ManualExecutionModel (not wrapped).
 * Cmd execution happens in the dispatch wrapper, not in the reducer.
 */
function reducer(model: ManualExecutionModel, msg: Msg): ManualExecutionModel {
  return update(model, msg).model;
}

export interface UseManualExecutionControllerArgs {
  selectedClusterLabel: string | null;
  highlightQueueCard: (key: string) => void;
}

export interface UseManualExecutionControllerReturn {
  // State (from model)
  executionResults: Record<string, ExecutionResult>;
  executingCandidate: string | null;
  // Handlers
  handleManualExecution: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;
  // Helpers
  getNotRunnableExplanation: (candidate: NextCheckPlanCandidate) => string | null;
  isManualExecutionAllowed: (candidate: NextCheckPlanCandidate) => boolean;
  buildCandidateKey: (candidate: NextCheckPlanCandidate, index: number) => string;
  // State accessors
  isExecuting: (candidateKey: string) => boolean;
  getResult: (candidateKey: string) => ExecutionResult | undefined;
  isAnyExecuting: () => boolean;
  // Clear results after refresh
  clearExecutionResults: () => void;
  // Post-execution highlight callback
  handlePostExecutionHighlight: () => void;
}

/**
 * Thin React hook that adapts the Elm-ish manual execution logic to React.
 *
 * Uses useReducer where state IS the model (not wrapped).
 * dispatch(msg) calls update(), updates state, then executes Cmd side effects.
 */
export function useManualExecutionController({
  selectedClusterLabel,
  highlightQueueCard,
}: UseManualExecutionControllerArgs): UseManualExecutionControllerReturn {
  // State shape is exactly ManualExecutionModel
  const [model, dispatch] = useReducer(reducer, initialModel);

  // Dispatch wrapper that also executes Cmd side effects
  // Note: update() is called once to get the command; React's reducer handles state
  const dispatchWithEffects = useCallback(
    (msg: Msg) => {
      // Extract command from update() - React state updated via dispatch(msg)
      const { cmd } = update(model, msg);
      dispatch(msg);

      // Execute side effects from cmd
      if (cmd.type === "ExecuteCandidate") {
        runEffect(cmd, dispatchWithEffects).catch(console.error);
      } else if (cmd.type === "HighlightCandidate") {
        runHighlightEffect(cmd.key, highlightQueueCard);
      }
      // NoOp: nothing to do
    },
    [model, highlightQueueCard]
  );

  // Build candidate key helper
  const buildCandidateKey = useCallback(
    (candidate: NextCheckPlanCandidate, index: number) =>
      `next-check-${candidate.candidateId ?? candidate.candidateIndex ?? index}-${
        candidate.targetCluster ?? selectedClusterLabel ?? "global"
      }`,
    [selectedClusterLabel]
  );

  // Check if manual execution is allowed for a candidate
  const isManualExecutionAllowed = useCallback(
    (candidate: NextCheckPlanCandidate): boolean => {
      const hasCandidateIdentifier =
        Boolean(candidate.candidateId?.trim()) || candidate.candidateIndex != null;
      if (!hasCandidateIdentifier) return false;
      if (!candidate.safeToAutomate) return false;
      if (candidate.requiresOperatorApproval && candidate.approvalStatus !== "approved") return false;
      if (candidate.duplicateOfExistingEvidence) return false;
      if (!candidate.suggestedCommandFamily) return false;
      if (!ALLOWED_MANUAL_FAMILIES.has(candidate.suggestedCommandFamily)) return false;
      const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
      if (!targetLabel) return false;
      if (isItemExecuted(candidate)) return false;
      return true;
    },
    [selectedClusterLabel]
  );

  // Get explanation for why a candidate is not runnable
  const getNotRunnableExplanation = useCallback(
    (candidate: NextCheckPlanCandidate): string | null => {
      const hasCandidateIdentifier =
        Boolean(candidate.candidateId?.trim()) || candidate.candidateIndex != null;
      if (!hasCandidateIdentifier) return "Not runnable: missing candidate identifier";
      if (!candidate.safeToAutomate) {
        const reason = candidate.safetyReason || "not marked safe to automate";
        return `Not runnable: ${humanizeReason(reason) || reason}`;
      }
      if (candidate.requiresOperatorApproval && candidate.approvalStatus !== "approved") {
        const reason = candidate.approvalReason || "approval required";
        return `Not runnable: ${humanizeReason(reason) || reason}`;
      }
      if (candidate.duplicateOfExistingEvidence) {
        const reason = candidate.duplicateReason || "duplicate of existing evidence";
        return `Not runnable: ${humanizeReason(reason) || reason}`;
      }
      if (!candidate.suggestedCommandFamily) return "Not runnable: no command family specified";
      if (!ALLOWED_MANUAL_FAMILIES.has(candidate.suggestedCommandFamily)) {
        return `Not runnable: unsupported command family '${candidate.suggestedCommandFamily}'`;
      }
      const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
      if (!targetLabel) return "Not runnable: target cluster unresolved";
      return "Not eligible for manual execution";
    },
    [selectedClusterLabel]
  );

  // Build the execution request from a candidate
  const buildExecutionRequest = useCallback(
    (candidate: NextCheckPlanCandidate): ExecuteCandidateRequest | null => {
      const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
      const candidateId = candidate.candidateId?.trim() ? candidate.candidateId : undefined;
      const candidateIndex = candidate.candidateIndex;
      const planArtifactPath = candidate.planArtifactPath?.trim() ? candidate.planArtifactPath : undefined;

      if (!targetLabel || (candidateIndex == null && !candidateId)) {
        return null;
      }

      return {
        candidateId,
        candidateIndex: candidateIndex ?? undefined,
        clusterLabel: targetLabel,
        planArtifactPath: planArtifactPath ?? null,
      };
    },
    [selectedClusterLabel]
  );

  // Handle manual execution - dispatch message, Cmd triggers API call
  const handleManualExecution = useCallback(
    async (candidate: NextCheckPlanCandidate, candidateKey: string) => {
      // Build request first to validate
      const request = buildExecutionRequest(candidate);
      if (!request) {
        // Dispatch error message directly
        dispatchWithEffects({
          type: "ExecutionFailed",
          candidateKey,
          error: { status: "error", summary: "Unable to determine candidate target." },
        });
        return;
      }

      // Dispatch ExecuteRequested with the request - this sets executing state
      // and emits Cmd.ExecuteCandidate which triggers the API call
      dispatchWithEffects({ type: "ExecuteRequested", candidateKey, request });
    },
    [dispatchWithEffects, buildExecutionRequest]
  );

  // Clear execution results
  const clearExecutionResults = useCallback(() => {
    dispatchWithEffects({ type: "ClearResults" });
  }, [dispatchWithEffects]);

  // Post-execution highlight callback
  const handlePostExecutionHighlight = useCallback(() => {
    dispatchWithEffects({ type: "ConsumeLastSucceededKey" });
  }, [dispatchWithEffects]);

  return {
    // State from model
    executionResults: model.executionResults,
    executingCandidate: model.executingCandidate,
    // Handlers
    handleManualExecution,
    // Helpers
    getNotRunnableExplanation,
    isManualExecutionAllowed,
    buildCandidateKey,
    // State accessors
    isExecuting: (key: string) => isExecuting(model, key),
    getResult: (key: string) => getResult(model, key),
    isAnyExecuting: () => isAnyExecuting(model),
    // Clear/highlight
    clearExecutionResults,
    handlePostExecutionHighlight,
  };
}