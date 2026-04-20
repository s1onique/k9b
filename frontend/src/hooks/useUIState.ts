/**
 * useUIState hook - manages non-queue UI state for the dashboard.
 *
 * Owns: filter state, sort state, active tab, highlight state, expanded sections.
 *
 * This hook does NOT own queue-specific state (queueClusterFilter, queueStatusFilter, etc.)
 * Those belong to useQueueState (Phase 4).
 *
 * Inputs: (none - all state is internal with localStorage persistence)
 *
 * Returns:
 *   - statusFilter: string - current status filter
 *   - setStatusFilter: (v: string) => void
 *   - searchText: string - current search text
 *   - setSearchText: (v: string) => void
 *   - sortKey: SortKey - current sort key
 *   - setSortKey: (v: SortKey) => void
 *   - activeTab: "findings" | "hypotheses" | "checks" - current active tab
 *   - setActiveTab: (v: "findings" | "hypotheses" | "checks") => void
 *   - clusterDetailExpanded: boolean - whether cluster detail is expanded
 *   - setClusterDetailExpanded: (v: boolean) => void
 *   - highlightedClusterLabel: string | null - currently highlighted cluster
 *   - setHighlightedClusterLabel: (v: string | null) => void
 *   - incidentExpandedClusters: Record<string, boolean> - expanded incident clusters
 *   - setIncidentExpandedClusters: React.Dispatch<React.SetStateAction<Record<string, boolean>>>
 *   - executionHistoryHighlightKey: string | null - highlighted execution history entry
 *   - setExecutionHistoryHighlightKey: (v: string | null) => void
 *   - queueHighlightKey: string | null - highlighted queue item
 *   - setQueueHighlightKey: (v: string | null) => void
 *   - executionHistoryFilter: ExecutionHistoryFilterState - execution history filter
 *   - setExecutionHistoryFilter: React.Dispatch<React.SetStateAction<ExecutionHistoryFilterState>>
 *   - expandedQueueItems: Record<string, boolean> - expanded queue items
 *   - setExpandedQueueItems: React.Dispatch<React.SetStateAction<Record<string, boolean>>>
 *   - toggleQueueDetails: (key: string) => void - toggle queue item expanded state
 */
import { useCallback, useEffect, useState } from "react";

// ============================================================================
// Types (duplicated from App.tsx to avoid circular dependencies)
// ============================================================================

export type SortKey = "proposalId" | "confidence" | "status";

// Filters for execution outcome/status: success, failure, timeout
export type ExecutionOutcomeFilter = "all" | "success" | "failure" | "timeout";

export type UsefulnessReviewFilter = "all" | "useful" | "partial" | "noisy" | "empty" | "unreviewed";

export const EXECUTION_HISTORY_FILTER_STORAGE_KEY = "dashboard-execution-history-filter";

const EXECUTION_OUTCOME_FILTER_VALUES: ExecutionOutcomeFilter[] = ["all", "success", "failure", "timeout"];
const USEFULNESS_REVIEW_FILTER_VALUES: UsefulnessReviewFilter[] = ["all", "useful", "partial", "noisy", "empty", "unreviewed"];

const isExecutionOutcomeFilterValue = (value: unknown): value is ExecutionOutcomeFilter =>
  typeof value === "string" && EXECUTION_OUTCOME_FILTER_VALUES.includes(value as ExecutionOutcomeFilter);

const isUsefulnessReviewFilterValue = (value: unknown): value is UsefulnessReviewFilter =>
  typeof value === "string" && USEFULNESS_REVIEW_FILTER_VALUES.includes(value as UsefulnessReviewFilter);

const DEFAULT_EXECUTION_HISTORY_FILTER: ExecutionHistoryFilterState = {
  outcomeFilter: "all",
  usefulnessFilter: "all",
  commandFamilyFilter: "all",
  clusterFilter: "all",
};

export type ExecutionHistoryFilterState = {
  outcomeFilter: ExecutionOutcomeFilter;
  usefulnessFilter: UsefulnessReviewFilter;
  commandFamilyFilter: string;
  clusterFilter: string;
};

const readStoredExecutionHistoryFilter = (): ExecutionHistoryFilterState => {
  if (typeof window === "undefined") {
    return DEFAULT_EXECUTION_HISTORY_FILTER;
  }
  const stored = window.localStorage.getItem(EXECUTION_HISTORY_FILTER_STORAGE_KEY);
  if (!stored) {
    return DEFAULT_EXECUTION_HISTORY_FILTER;
  }
  try {
    const parsed = JSON.parse(stored);
    if (!parsed || typeof parsed !== "object") {
      return DEFAULT_EXECUTION_HISTORY_FILTER;
    }
    const candidate = parsed as Record<string, unknown>;
    return {
      outcomeFilter: isExecutionOutcomeFilterValue(candidate.outcomeFilter)
        ? candidate.outcomeFilter
        : DEFAULT_EXECUTION_HISTORY_FILTER.outcomeFilter,
      usefulnessFilter: isUsefulnessReviewFilterValue(candidate.usefulnessFilter)
        ? candidate.usefulnessFilter
        : DEFAULT_EXECUTION_HISTORY_FILTER.usefulnessFilter,
      commandFamilyFilter: typeof candidate.commandFamilyFilter === "string"
        ? candidate.commandFamilyFilter
        : DEFAULT_EXECUTION_HISTORY_FILTER.commandFamilyFilter,
      clusterFilter: typeof candidate.clusterFilter === "string"
        ? candidate.clusterFilter
        : DEFAULT_EXECUTION_HISTORY_FILTER.clusterFilter,
    };
  } catch {
    return DEFAULT_EXECUTION_HISTORY_FILTER;
  }
};

const persistExecutionHistoryFilter = (filter: ExecutionHistoryFilterState) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(EXECUTION_HISTORY_FILTER_STORAGE_KEY, JSON.stringify(filter));
};

// ============================================================================
// Hook Interface
// ============================================================================

export interface UseUIStateReturn {
  statusFilter: string;
  setStatusFilter: (v: string) => void;
  searchText: string;
  setSearchText: (v: string) => void;
  sortKey: SortKey;
  setSortKey: (v: SortKey) => void;
  activeTab: "findings" | "hypotheses" | "checks";
  setActiveTab: (v: "findings" | "hypotheses" | "checks") => void;
  clusterDetailExpanded: boolean;
  setClusterDetailExpanded: (v: boolean) => void;
  highlightedClusterLabel: string | null;
  setHighlightedClusterLabel: (v: string | null) => void;
  incidentExpandedClusters: Record<string, boolean>;
  setIncidentExpandedClusters: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  executionHistoryHighlightKey: string | null;
  setExecutionHistoryHighlightKey: (v: string | null) => void;
  queueHighlightKey: string | null;
  setQueueHighlightKey: (v: string | null) => void;
  executionHistoryFilter: ExecutionHistoryFilterState;
  setExecutionHistoryFilter: React.Dispatch<React.SetStateAction<ExecutionHistoryFilterState>>;
  expandedQueueItems: Record<string, boolean>;
  setExpandedQueueItems: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  toggleQueueDetails: (key: string) => void;
}

// ============================================================================
// Hook Implementation
// ============================================================================

export const useUIState = (): UseUIStateReturn => {
  // Filter and sort state
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchText, setSearchText] = useState<string>("");
  const [sortKey, setSortKey] = useState<SortKey>("proposalId");
  const [activeTab, setActiveTab] = useState<"findings" | "hypotheses" | "checks">("findings");

  // Cluster detail expanded state
  const [clusterDetailExpanded, setClusterDetailExpanded] = useState<boolean>(false);

  // Highlight state
  const [highlightedClusterLabel, setHighlightedClusterLabel] = useState<string | null>(null);
  const [incidentExpandedClusters, setIncidentExpandedClusters] = useState<Record<string, boolean>>({});
  const [executionHistoryHighlightKey, setExecutionHistoryHighlightKey] = useState<string | null>(null);
  const [queueHighlightKey, setQueueHighlightKey] = useState<string | null>(null);

  // Execution history filter state
  const [executionHistoryFilter, setExecutionHistoryFilter] = useState<ExecutionHistoryFilterState>(
    readStoredExecutionHistoryFilter
  );

  // Persist execution history filter state
  useEffect(() => {
    persistExecutionHistoryFilter(executionHistoryFilter);
  }, [executionHistoryFilter]);

  // Expanded queue items
  const [expandedQueueItems, setExpandedQueueItems] = useState<Record<string, boolean>>({});

  // Toggle function for queue details
  const toggleQueueDetails = useCallback((key: string) => {
    setExpandedQueueItems((current) => ({
      ...current,
      [key]: !current[key],
    }));
  }, []);

  return {
    // Filter and sort state
    statusFilter,
    setStatusFilter,
    searchText,
    setSearchText,
    sortKey,
    setSortKey,
    activeTab,
    setActiveTab,
    clusterDetailExpanded,
    setClusterDetailExpanded,

    // Highlight state
    highlightedClusterLabel,
    setHighlightedClusterLabel,
    incidentExpandedClusters,
    setIncidentExpandedClusters,
    executionHistoryHighlightKey,
    setExecutionHistoryHighlightKey,
    queueHighlightKey,
    setQueueHighlightKey,

    // Execution history filter
    executionHistoryFilter,
    setExecutionHistoryFilter,

    // Expanded queue items
    expandedQueueItems,
    setExpandedQueueItems,
    toggleQueueDetails,
  };
};

// Re-export types for consumers
export type { ExecutionHistoryFilterState, ExecutionOutcomeFilter, UsefulnessReviewFilter };
