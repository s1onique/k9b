/**
 * executionHistoryTypes.ts
 *
 * Backward-compatibility re-export from split modules.
 * Prefer importing from individual modules directly.
 */

// Re-export everything from the split modules for backward compatibility

// Types and functions from executionHistoryFilters
export type {
  ExecutionOutcomeFilter,
  UsefulnessReviewFilter,
  ExecutionHistoryFilterState,
  ExecutionHistoryFilterCounts,
} from "./executionHistoryFiltersData";
export {
  EXECUTION_OUTCOME_FILTER_OPTIONS,
  USEFULNESS_REVIEW_FILTER_OPTIONS,
  EXECUTION_HISTORY_FILTER_STORAGE_KEY,
  EXECUTION_HISTORY_FILTER_VALUES,
  USEFULNESS_REVIEW_FILTER_VALUES,
  isExecutionOutcomeFilterValue,
  isUsefulnessReviewFilterValue,
  persistExecutionHistoryFilter,
  readStoredExecutionHistoryFilter,
  filterExecutionHistory,
  extractClustersFromHistory,
  extractCommandFamiliesFromHistory,
  computeExecutionHistoryFilterCounts,
} from "./executionHistoryFiltersData";

// Types and functions from executionHistorySummary
export type {
  RepeatedFailureGroup,
  ExecutionHistorySummary,
} from "./executionHistorySummary";
export {
  computeExecutionHistorySummary,
} from "./executionHistorySummary";

// Types and functions from executionHistoryKeys
export {
  buildExecutionEntryKey,
  buildCandidateKey,
} from "./executionHistoryKeys";

// Props contract
import type { NextCheckExecutionHistoryEntry, NextCheckQueueItem } from "../../types";

export interface ExecutionHistoryPanelProps {
  history: NextCheckExecutionHistoryEntry[];
  runId: string;
  runLabel: string;
  queueCandidateCount: number;
  highlightedKey: string | null;
  onSubmitFeedback?: (artifactPath: string, usefulnessClass: string, summary: string | undefined) => Promise<void>;
  onSubmitAlertmanagerRelevanceFeedback?: (
    artifactPath: string,
    relevance: "relevant" | "not_relevant" | "noisy" | "unsure",
    summary: string | undefined
  ) => Promise<void>;
  filter: import("./executionHistoryFiltersData").ExecutionHistoryFilterState;
  onFilterChange: (filter: import("./executionHistoryFiltersData").ExecutionHistoryFilterState) => void;
  runQueue?: NextCheckQueueItem[];
  onHighlightQueueCard?: (key: string) => void;
}
