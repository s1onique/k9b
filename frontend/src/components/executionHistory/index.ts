/**
 * executionHistory/index.ts
 *
 * Public barrel export for the executionHistory module.
 * Consumers should import from this file.
 */

// Component exports
export { ExecutionHistoryEmptyState } from "./ExecutionHistoryEmptyState";
export { ExecutionHistoryFilters } from "./ExecutionHistoryFilters";
export { ExecutionHistoryRow } from "./ExecutionHistoryRow";
export { ExecutionHistorySummaryStrip } from "./ExecutionHistorySummaryStrip";
export { UsefulnessFeedbackControl } from "./UsefulnessFeedbackControl";
export { AlertmanagerRelevanceFeedbackControl } from "./AlertmanagerRelevanceFeedbackControl";

// Re-export types
export type {
  ExecutionHistoryPanelProps,
  ExecutionHistoryFilterState,
  ExecutionHistoryFilterCounts,
  ExecutionOutcomeFilter,
  UsefulnessReviewFilter,
  RepeatedFailureGroup,
  ExecutionHistorySummary,
} from "./executionHistoryTypes";

// Re-export filter constants
export {
  EXECUTION_OUTCOME_FILTER_OPTIONS,
  USEFULNESS_REVIEW_FILTER_OPTIONS,
  EXECUTION_HISTORY_FILTER_STORAGE_KEY,
} from "./executionHistoryTypes";

// Re-export filter persistence
export {
  persistExecutionHistoryFilter,
  readStoredExecutionHistoryFilter,
  isExecutionOutcomeFilterValue,
  isUsefulnessReviewFilterValue,
} from "./executionHistoryTypes";

// Re-export filter functions
export {
  filterExecutionHistory,
  extractClustersFromHistory,
  extractCommandFamiliesFromHistory,
  computeExecutionHistoryFilterCounts,
  computeExecutionHistorySummary,
  buildExecutionEntryKey,
  buildCandidateKey,
} from "./executionHistoryTypes";

// Re-export format functions
export { formatDuration, buildExecutionBadges } from "./executionHistoryFormat";
