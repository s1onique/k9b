/**
 * useAppWorkNextChecksLaneProps - Hook for constructing WorkNextChecksLane props.
 *
 * Extracts WorkNextChecksLane prop wiring from App.tsx.
 *
 * @module app/useAppWorkNextChecksLaneProps
 */
import type { ComponentProps } from "react";
import { WorkNextChecksLane } from "../components/WorkNextChecksLane";

type WorkNextChecksLaneProps = ComponentProps<typeof WorkNextChecksLane>;

export interface UseAppWorkNextChecksLanePropsArgs {
  run: WorkNextChecksLaneProps["run"];
  executionHistory: WorkNextChecksLaneProps["history"];
  runQueue: WorkNextChecksLaneProps["runQueue"];
  executionHistoryHighlightKey: WorkNextChecksLaneProps["executionHistoryHighlightKey"];
  handleUsefulnessFeedback: WorkNextChecksLaneProps["onSubmitFeedback"];
  handleAlertmanagerRelevanceFeedback: WorkNextChecksLaneProps["onSubmitAlertmanagerRelevanceFeedback"];
  executionHistoryFilter: WorkNextChecksLaneProps["executionHistoryFilter"];
  setExecutionHistoryFilter: WorkNextChecksLaneProps["onExecutionHistoryFilterChange"];
  highlightQueueCard: WorkNextChecksLaneProps["onHighlightQueueCard"];
  queuePanelProps: WorkNextChecksLaneProps["queuePanelProps"];
}

export function useAppWorkNextChecksLaneProps({
  run,
  executionHistory,
  runQueue,
  executionHistoryHighlightKey,
  handleUsefulnessFeedback,
  handleAlertmanagerRelevanceFeedback,
  executionHistoryFilter,
  setExecutionHistoryFilter,
  highlightQueueCard,
  queuePanelProps,
}: UseAppWorkNextChecksLanePropsArgs): WorkNextChecksLaneProps {
  return {
    run,
    history: executionHistory,
    queueCandidateCount: runQueue.length,
    executionHistoryHighlightKey,
    onSubmitFeedback: handleUsefulnessFeedback,
    onSubmitAlertmanagerRelevanceFeedback: handleAlertmanagerRelevanceFeedback,
    executionHistoryFilter,
    onExecutionHistoryFilterChange: setExecutionHistoryFilter,
    runQueue,
    onHighlightQueueCard: highlightQueueCard,
    queuePanelProps,
  };
}