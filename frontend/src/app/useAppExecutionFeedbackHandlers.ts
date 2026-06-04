/**
 * useAppExecutionFeedbackHandlers - Hook for execution feedback handler state and logic.
 *
 * Extracts feedback handler state and handlers from useAppData.
 * Owns usefulness feedback and Alertmanager relevance feedback submission logic.
 *
 * @module app/useAppExecutionFeedbackHandlers
 */
import { useCallback } from "react";
import { submitAlertmanagerRelevanceFeedback, submitUsefulnessFeedback } from "../api";

export interface UsefulnessFeedbackState {
  isSubmitting: boolean;
  lastError: string | null;
  lastSuccess: boolean;
}

export interface AlertmanagerRelevanceFeedbackState {
  isSubmitting: boolean;
  lastError: string | null;
  lastSuccess: boolean;
}

export interface UseAppExecutionFeedbackHandlersArgs {
  refreshAppData: () => Promise<void>;
}

export interface UseAppExecutionFeedbackHandlersReturn {
  handleUsefulnessFeedback: (
    artifactPath: string,
    usefulnessClass: string,
    summary: string | undefined
  ) => Promise<void>;
  handleAlertmanagerRelevanceFeedback: (
    artifactPath: string,
    relevance: "relevant" | "not_relevant" | "noisy" | "unsure",
    summary: string | undefined
  ) => Promise<void>;
  usefulnessFeedbackState: UsefulnessFeedbackState;
  alertmanagerRelevanceFeedbackState: AlertmanagerRelevanceFeedbackState;
}

/**
 * Hook for execution feedback handler state and logic.
 *
 * Extracts feedback handlers from useAppData to allow independent usage
 * and testing of feedback submission logic.
 */
export function useAppExecutionFeedbackHandlers({
  refreshAppData,
}: UseAppExecutionFeedbackHandlersArgs): UseAppExecutionFeedbackHandlersReturn {
  // Handle usefulness feedback
  // Uses the same pattern as useAppData: submit + refresh on success
  const handleUsefulnessFeedback = useCallback(
    async (
      artifactPath: string,
      usefulnessClass: string,
      summary: string | undefined
    ) => {
      await submitUsefulnessFeedback({
        artifactPath,
        usefulnessClass: usefulnessClass as "useful" | "partial" | "noisy" | "empty",
        usefulnessSummary: summary,
      });
      // Refresh to get updated data
      await refreshAppData();
    },
    [refreshAppData]
  );

  // Handle Alertmanager relevance feedback
  // Uses the same pattern as useAppData: submit + refresh on success
  const handleAlertmanagerRelevanceFeedback = useCallback(
    async (
      artifactPath: string,
      relevance: "relevant" | "not_relevant" | "noisy" | "unsure",
      summary: string | undefined
    ) => {
      await submitAlertmanagerRelevanceFeedback({
        artifactPath,
        alertmanagerRelevance: relevance,
        alertmanagerRelevanceSummary: summary,
      });
      // Refresh to get updated data
      await refreshAppData();
    },
    [refreshAppData]
  );

  return {
    handleUsefulnessFeedback,
    handleAlertmanagerRelevanceFeedback,
    usefulnessFeedbackState: {
      isSubmitting: false,
      lastError: null,
      lastSuccess: false,
    },
    alertmanagerRelevanceFeedbackState: {
      isSubmitting: false,
      lastError: null,
      lastSuccess: false,
    },
  };
}