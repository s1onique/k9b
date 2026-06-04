/**
 * useAppApprovalHandlers - Hook for approval handler state and logic.
 *
 * Extracts approval state and handlers from App.tsx.
 * Owns:
 *   - approvalResults state
 *   - approvingCandidate state
 *   - handleApproveCandidate handler
 *
 * Does NOT own manual execution state (executionResults, executingCandidate,
 * handleManualExecution, etc.) - that lives in useAppManualExecutionHandlers.
 *
 * @module app/useAppApprovalHandlers
 */
import { useCallback, useState } from "react";
import type { NextCheckPlanCandidate } from "../types";
import { approveNextCheckCandidate } from "../api";

/**
 * Approval result shape - mirrors the shape used by ClusterNextCheckPlanSection.
 */
export interface ApprovalResult {
  status: "success" | "error";
  summary: string;
  artifactPath?: string | null;
  approvalTimestamp?: string | null;
}

export interface UseAppApprovalHandlersArgs {
  /** Current selected cluster label - used as fallback when candidate has no target cluster */
  selectedClusterLabel: string | null;
  /** Refresh callback - called after successful approval to reconcile state */
  refresh: () => Promise<void>;
}

export interface UseAppApprovalHandlersReturn {
  // State
  approvalResults: Record<string, ApprovalResult>;
  approvingCandidate: string | null;
  // Handlers
  handleApproveCandidate: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;
  // Clear results after refresh
  clearApprovalResults: () => void;
}

/**
 * Hook for approval handler state and logic.
 *
 * Extracts approval logic from App.tsx to reduce component size
 * and improve testability of approval-related behavior.
 */
export function useAppApprovalHandlers({
  selectedClusterLabel,
  refresh,
}: UseAppApprovalHandlersArgs): UseAppApprovalHandlersReturn {
  // Approval state
  const [approvalResults, setApprovalResults] = useState<Record<string, ApprovalResult>>({});
  const [approvingCandidate, setApprovingCandidate] = useState<string | null>(null);

  // Handle candidate approval
  const handleApproveCandidate = useCallback(
    async (candidate: NextCheckPlanCandidate, candidateKey: string) => {
      const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
      const candidateId = candidate.candidateId?.trim() ? candidate.candidateId : undefined;
      const candidateIndex = candidate.candidateIndex;

      if (!targetLabel || (candidateIndex == null && !candidateId)) {
        setApprovalResults((prev) => ({
          ...prev,
          [candidateKey]: {
            status: "error",
            summary: "Unable to determine candidate target",
          },
        }));
        return;
      }

      setApprovingCandidate(candidateKey);
      try {
        const result = await approveNextCheckCandidate({
          candidateId,
          candidateIndex: candidateIndex ?? undefined,
          clusterLabel: targetLabel,
        });
        setApprovalResults((prev) => ({
          ...prev,
          [candidateKey]: {
            status: result.status === "success" ? "success" : "error",
            summary:
              result.summary ||
              (result.status === "success" ? "Candidate approved" : "Approval failed"),
            artifactPath: result.artifactPath,
            approvalTimestamp: result.approvalTimestamp,
          },
        }));
        await refresh();
      } catch (err) {
        const message = err instanceof Error ? err.message : "Approval failed";
        setApprovalResults((prev) => ({
          ...prev,
          [candidateKey]: { status: "error", summary: message },
        }));
      } finally {
        setApprovingCandidate((current) => (current === candidateKey ? null : current));
      }
    },
    [selectedClusterLabel, refresh]
  );

  // Clear approval results
  const clearApprovalResults = useCallback(() => {
    setApprovalResults({});
  }, []);

  return {
    // State
    approvalResults,
    approvingCandidate,
    // Handlers
    handleApproveCandidate,
    // Clear results
    clearApprovalResults,
  };
}
