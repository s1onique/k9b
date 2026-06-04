/**
 * useAppManualExecutionHandlers - Hook for manual execution handler state and logic.
 *
 * Extracts manual execution state and handlers from App.tsx.
 * Owns:
 *   - executionResults state
 *   - executingCandidate state
 *   - handleManualExecution handler
 *   - getNotRunnableExplanation helper
 *   - isManualExecutionAllowed helper
 *   - buildCandidateKey helper
 *
 * Does NOT own approval state (approvalResults, approvingCandidate, handleApproveCandidate).
 *
 * @module app/useAppManualExecutionHandlers
 */
import { useCallback, useRef, useState } from "react";
import type { NextCheckPlanCandidate, NextCheckExecutionResponse } from "../types";
import { executeNextCheckCandidate } from "../api";
import {
  ALLOWED_MANUAL_FAMILIES,
  humanizeReason,
  isItemExecuted,
} from "../utils";

export interface ExecutionErrorResult {
  status: "error";
  summary: string;
  blockingReason?: string | null;
}

export type ExecutionResult = NextCheckExecutionResponse | ExecutionErrorResult;

export interface UseAppManualExecutionHandlersArgs {
  selectedClusterLabel: string | null;
  highlightQueueCard: (key: string) => void;
}

export interface UseAppManualExecutionHandlersReturn {
  // State
  executionResults: Record<string, ExecutionResult>;
  executingCandidate: string | null;
  // Handlers
  handleManualExecution: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;
  // Helpers
  getNotRunnableExplanation: (candidate: NextCheckPlanCandidate) => string | null;
  isManualExecutionAllowed: (candidate: NextCheckPlanCandidate) => boolean;
  buildCandidateKey: (candidate: NextCheckPlanCandidate, index: number) => string;
  // Clear results after refresh
  clearExecutionResults: () => void;
  // Post-execution highlight callback
  handlePostExecutionHighlight: () => void;
}

/**
 * Hook for manual execution handler state and logic.
 *
 * Extracts manual execution logic from App.tsx to reduce component size
 * and improve testability of execution-related behavior.
 */
export function useAppManualExecutionHandlers({
  selectedClusterLabel,
  highlightQueueCard,
}: UseAppManualExecutionHandlersArgs): UseAppManualExecutionHandlersReturn {
  // Execution state
  const [executionResults, setExecutionResults] = useState<Record<string, ExecutionResult>>({});
  const [executingCandidate, setExecutingCandidate] = useState<string | null>(null);

  // Track the last executed candidate key for post-execution highlighting
  const lastExecutedCandidateKey = useRef<string | null>(null);

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
      if (!hasCandidateIdentifier) {
        return false;
      }
      if (!candidate.safeToAutomate) {
        return false;
      }
      if (candidate.requiresOperatorApproval && candidate.approvalStatus !== "approved") {
        return false;
      }
      if (candidate.duplicateOfExistingEvidence) {
        return false;
      }
      if (!candidate.suggestedCommandFamily) {
        return false;
      }
      if (!ALLOWED_MANUAL_FAMILIES.has(candidate.suggestedCommandFamily)) {
        return false;
      }
      const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
      if (!targetLabel) {
        return false;
      }
      // Do not allow re-execution of already executed items
      if (isItemExecuted(candidate)) {
        return false;
      }
      return true;
    },
    [selectedClusterLabel]
  );

  // Get explanation for why a candidate is not runnable
  const getNotRunnableExplanation = useCallback(
    (candidate: NextCheckPlanCandidate): string | null => {
      // Check in the same order as isManualExecutionAllowed to ensure consistency
      // 1. Candidate identifier
      const hasCandidateIdentifier =
        Boolean(candidate.candidateId?.trim()) || candidate.candidateIndex != null;
      if (!hasCandidateIdentifier) {
        return "Not runnable: missing candidate identifier";
      }

      // 2. Safe to automate
      if (!candidate.safeToAutomate) {
        const reason = candidate.safetyReason || "not marked safe to automate";
        return `Not runnable: ${humanizeReason(reason) || reason}`;
      }

      // 3. Approval required
      if (candidate.requiresOperatorApproval && candidate.approvalStatus !== "approved") {
        const reason = candidate.approvalReason || "approval required";
        return `Not runnable: ${humanizeReason(reason) || reason}`;
      }

      // 4. Duplicate
      if (candidate.duplicateOfExistingEvidence) {
        const reason = candidate.duplicateReason || "duplicate of existing evidence";
        return `Not runnable: ${humanizeReason(reason) || reason}`;
      }

      // 5. Command family exists
      if (!candidate.suggestedCommandFamily) {
        return "Not runnable: no command family specified";
      }

      // 6. Command family allowed
      if (!ALLOWED_MANUAL_FAMILIES.has(candidate.suggestedCommandFamily)) {
        return `Not runnable: unsupported command family '${candidate.suggestedCommandFamily}'`;
      }

      // 7. Target cluster resolved
      const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
      if (!targetLabel) {
        return "Not runnable: target cluster unresolved";
      }

      // Fallback - should not reach here if logic is correct
      return "Not eligible for manual execution";
    },
    [selectedClusterLabel]
  );

  // Handle manual execution
  const handleManualExecution = useCallback(
    async (candidate: NextCheckPlanCandidate, candidateKey: string) => {
      const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
      const candidateId = candidate.candidateId?.trim() ? candidate.candidateId : undefined;
      const candidateIndex = candidate.candidateIndex;
      const planArtifactPath = candidate.planArtifactPath?.trim()
        ? candidate.planArtifactPath
        : undefined;

      if (!targetLabel || (candidateIndex == null && !candidateId)) {
        setExecutionResults((prev) => ({
          ...prev,
          [candidateKey]: { status: "error", summary: "Unable to determine candidate target." },
        }));
        return;
      }

      setExecutingCandidate(candidateKey);
      // Track the candidate key so we can highlight it after refresh reconciliation
      lastExecutedCandidateKey.current = candidateKey;

      try {
        const result = await executeNextCheckCandidate({
          candidateId,
          candidateIndex: candidateIndex ?? undefined,
          clusterLabel: targetLabel,
          planArtifactPath: planArtifactPath ?? null,
        });
        setExecutionResults((prev) => ({
          ...prev,
          [candidateKey]: result,
        }));
      } catch (err) {
        const message = err instanceof Error ? err.message : "Manual execution failed";
        const blockingReason =
          err instanceof Error && "blockingReason" in err
            ? (err as Error & { blockingReason?: string | null }).blockingReason
            : undefined;
        setExecutionResults((prev) => ({
          ...prev,
          [candidateKey]: {
            status: "error",
            summary: message,
            blockingReason: blockingReason ?? null,
          },
        }));
      } finally {
        setExecutingCandidate((current) => (current === candidateKey ? null : current));
      }
    },
    [selectedClusterLabel]
  );

  // Clear execution results after refresh
  const clearExecutionResults = useCallback(() => {
    setExecutionResults({});
  }, []);

  // Post-execution highlight callback (called by App.tsx after refresh)
  const handlePostExecutionHighlight = useCallback(() => {
    if (lastExecutedCandidateKey.current) {
      const keyToHighlight = lastExecutedCandidateKey.current;
      lastExecutedCandidateKey.current = null;
      requestAnimationFrame(() => {
        highlightQueueCard(keyToHighlight);
      });
    }
  }, [highlightQueueCard]);

  return {
    // State
    executionResults,
    executingCandidate,
    // Handlers
    handleManualExecution,
    // Helpers
    getNotRunnableExplanation,
    isManualExecutionAllowed,
    buildCandidateKey,
    clearExecutionResults,
    handlePostExecutionHighlight,
  };
}
