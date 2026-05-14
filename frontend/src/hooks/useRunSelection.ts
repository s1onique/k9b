/**
 * useRunSelection hook — manages runs list UI (pagination, filtering, navigation).
 *
 * Ownership model:
 *   - RunControl is the single authoritative owner for run list loading and freshness.
 *   - useRunSelection receives runs data as INPUT (from RunControl).
 *   - useRunSelection owns only:
 *     - autoRefreshInterval preference and localStorage persistence
 *     - pagination state (page, pageSize)
 *     - filter state (runsFilter)
 *     - navigation helpers (computePageForRunId, navigateToPageContainingRun, handleShowSelectedRun)
 *
 * Auto-refresh timer is owned by App.tsx. App.tsx reads autoRefreshInterval from this hook
 * and calls RunControl's poll() on each interval tick. This hook does NOT own the timer.
 *
 * Inputs (via UseRunSelectionOptions):
 *   - selectedRunId: string | null - selected run from useRunControl (REQUIRED INPUT)
 *     Used for: highlighting, "show selected" button, following/detached navigation
 *   - runs: RunsListEntry[] - run list from RunControl model (REQUIRED INPUT)
 *     Used for: filtering, pagination, computing latestRunId
 *   - isLoading: boolean - loading state from RunControl (REQUIRED INPUT)
 *     Used for: showing loading indicator in list
 *
 * Returns:
 *   - runs: RunsListEntry[] - echo of the input (passed-through for convenience)
 *   - isLoading: boolean - echo of the input (passed-through for convenience)
 *   - selectedRunId: string | null - echo of the input, for convenience
 *   - latestRunId: string | null - the most recent run ID (derived from runs input)
 *   - isLatest: boolean - whether the selected run is the latest
 *   - autoRefreshInterval: number | null - the auto-refresh interval (owned by this hook, read by App.tsx)
 *   - handleAutoRefreshChange: (value: string) => void
 *   - runsFilter: RunsReviewFilter - current filter for runs list
 *   - setRunsFilter: (filter: RunsReviewFilter) => void
 *   - runsPageSize: number - number of runs per page
 *   - setRunsPageSize: (size: number) => void
 *   - runsPage: number - current page number (1-indexed)
 *   - setRunsPage: (page: number) => void
 *   - isRunsListFollowingSelection: boolean - following vs detached mode
 *     - true (following): auto-navigate to page containing selectedRunId after runs list loads
 *     - false (detached): user has manually navigated away from selected run's page
 *   - setIsRunsListFollowingSelection: (following: boolean) => void
 *   - filteredRunsList: RunsListEntry[] - runs filtered by runsFilter
 *   - runsFilterCounts: Record<RunsReviewFilter, number> - counts per filter
 *   - paginatedRunsList: RunsListEntry[] - runs for current page
 *   - totalRunsPages: number - total number of pages
 *   - isSelectedRunVisibleOnCurrentRunsPage: boolean
 *   - handleRunsFilterChange: (filter: RunsReviewFilter) => void
 *   - handleRunsPageSizeChange: (size: number) => void
 *   - handleRunsPageChange: (page: number) => void
 *   - computePageForRunId: (runId: string | null) => number
 *   - navigateToPageContainingRun: (runId: string | null) => void - enables following mode
 *   - handleShowSelectedRun: () => void - navigate to and highlight the selected run
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import type { BatchExecutionSummary, RunsListEntry } from "../types";

export const AUTOREFRESH_STORAGE_KEY = "dashboard-autorefresh-interval";
const DEFAULT_AUTOREFRESH_SECONDS = 5;

// ==========================================================================
// Filter types and options - derived from executionSummary when available
// ==========================================================================

/**
 * Filter buckets for Recent Runs panel.
 * These now derive from executionSummary instead of stale reviewStatus.
 * 
 * Mapping from executionSummary:
 * - no-candidates → no-executable-work
 * - not-started + pending > 0 → no-executions-yet
 * - partially-executed → partially-executed
 * - fully-executed + failed > 0 → needs-attention
 * - fully-executed + failed == 0 → fully-executed
 */
export type RunsReviewFilter = 
  | "all" 
  | "no-executable-work" 
  | "no-executions-yet" 
  | "partially-executed" 
  | "fully-executed" 
  | "needs-attention";

export const RUNS_REVIEW_FILTER_OPTIONS: { label: string; value: RunsReviewFilter }[] = [
  { label: "All runs", value: "all" },
  { label: "No executable work", value: "no-executable-work" },
  { label: "No executions yet", value: "no-executions-yet" },
  { label: "Partially executed", value: "partially-executed" },
  { label: "Fully executed", value: "fully-executed" },
  { label: "Needs attention", value: "needs-attention" },
];

const RUNS_REVIEW_FILTER_VALUES: RunsReviewFilter[] = [
  "all", 
  "no-executable-work", 
  "no-executions-yet", 
  "partially-executed", 
  "fully-executed", 
  "needs-attention"
];

const isRunsReviewFilterValue = (value: unknown): value is RunsReviewFilter =>
  typeof value === "string" && RUNS_REVIEW_FILTER_VALUES.includes(value as RunsReviewFilter);

export const RUNS_REVIEW_FILTER_STORAGE_KEY = "dashboard-runs-review-filter";
export const RUNS_PAGE_SIZE_STORAGE_KEY = "dashboard-runs-page-size";

const DEFAULT_RUNS_REVIEW_FILTER: RunsReviewFilter = "all";
const DEFAULT_RUNS_PAGE_SIZE = 5;
const MAX_RUNS_PAGE_SIZE = 20;
export const RUNS_PAGE_SIZE_OPTIONS = [5, 10, 20] as const;

// ==========================================================================
// Execution display status derived from executionSummary
// ==========================================================================

/**
 * Display status for runs in the Recent Runs table.
 * Uses executionSummary when available, falls back to reviewStatus otherwise.
 */
export type RunsDisplayStatus = 
  | "no-executable-work"     // batchExecutionState === "no-candidates"
  | "no-executions-yet"      // batchExecutionState === "not-started" + pending > 0
  | "partially-executed"     // batchExecutionState === "partially-executed"
  | "fully-executed"         // batchExecutionState === "fully-executed" + failed === 0
  | "needs-attention"        // batchExecutionState === "fully-executed" + failed > 0
  | "unknown";              // executionSummary absent, fallback to reviewStatus

export type RunsReviewStatus = RunsListEntry["reviewStatus"];

/**
 * Derive display status from executionSummary.
 * Returns null if executionSummary is not available.
 */
export const deriveExecutionDisplayStatusFromSummary = (
  executionSummary: BatchExecutionSummary | null
): RunsDisplayStatus | null => {
  if (!executionSummary) {
    return null;
  }

  const { batchExecutionState, failedCandidates, pendingExecutableCandidates } = executionSummary;

  switch (batchExecutionState) {
    case "no-candidates":
      return "no-executable-work";
    
    case "not-started":
      // Only show "No executions yet" if there's actual work to do
      if (pendingExecutableCandidates > 0) {
        return "no-executions-yet";
      }
      // If no pending work, treat as fully executed
      return "fully-executed";
    
    case "partially-executed":
      return "partially-executed";
    
    case "fully-executed":
      // Failed candidates need attention
      if (failedCandidates > 0) {
        return "needs-attention";
      }
      return "fully-executed";
    
    default:
      // Unknown state - should not happen but handle gracefully
      return "unknown";
  }
};

/**
 * Maps execution-based filter bucket for a run.
 * Returns the filter bucket this run belongs to, or null if it doesn't fit any bucket.
 */
const getRunFilterBucket = (executionSummary: BatchExecutionSummary | null): RunsReviewFilter | null => {
  if (!executionSummary) {
    return null;
  }

  const { batchExecutionState, failedCandidates, pendingExecutableCandidates } = executionSummary;

  switch (batchExecutionState) {
    case "no-candidates":
      return "no-executable-work";
    
    case "not-started":
      if (pendingExecutableCandidates > 0) {
        return "no-executions-yet";
      }
      return "fully-executed";
    
    case "partially-executed":
      return "partially-executed";
    
    case "fully-executed":
      if (failedCandidates > 0) {
        return "needs-attention";
      }
      return "fully-executed";
    
    default:
      return null;
  }
};

/**
 * Determines the display status for a run in the Recent Runs table.
 * Uses executionSummary when available, falls back to reviewStatus for backward compatibility.
 */
export const getRunsDisplayStatus = (
  run: RunsListEntry,
  executionCountsComplete: boolean,
): RunsDisplayStatus => {
  // Try executionSummary first (preferred source of truth)
  const executionStatus = deriveExecutionDisplayStatusFromSummary(run.executionSummary);
  if (executionStatus) {
    return executionStatus;
  }

  // Fallback: Use reviewStatus for backward compatibility with older payloads
  if (!executionCountsComplete && run.reviewStatus === "no-executions") {
    return "unknown";
  }
  
  // Map old reviewStatus to new display statuses
  // This preserves backward compatibility for payloads without executionSummary
  switch (run.reviewStatus) {
    case "no-executions":
      return "no-executions-yet";
    case "unreviewed":
    case "partially-reviewed":
      return "needs-attention";
    case "fully-reviewed":
      return "fully-executed";
    default:
      return "unknown";
  }
};

// ==========================================================================
// Filter counts computation
// ==========================================================================

// Compute filter counts from runs list
export const computeRunsFilterCounts = (
  runs: RunsListEntry[],
  executionCountsComplete: boolean = true
): Record<RunsReviewFilter, number> => {
  const counts: Record<RunsReviewFilter, number> = {
    all: runs.length,
    'no-executable-work': 0,
    'no-executions-yet': 0,
    'partially-executed': 0,
    'fully-executed': 0,
    'needs-attention': 0,
  };

  runs.forEach((run) => {
    const bucket = getRunFilterBucket(run.executionSummary);
    
    if (bucket) {
      counts[bucket]++;
    } else {
      // Fallback to reviewStatus for backward compatibility
      switch (run.reviewStatus) {
        case "no-executions":
          if (executionCountsComplete) {
            counts['no-executions-yet']++;
          }
          break;
        case "unreviewed":
        case "partially-reviewed":
          counts['needs-attention']++;
          break;
        case "fully-reviewed":
          counts['fully-executed']++;
          break;
      }
    }
  });

  return counts;
};

// ==========================================================================
// Storage helpers
// ==========================================================================

const readStoredRunsReviewFilter = (): RunsReviewFilter => {
  if (typeof window === "undefined") {
    return DEFAULT_RUNS_REVIEW_FILTER;
  }
  const stored = window.localStorage.getItem(RUNS_REVIEW_FILTER_STORAGE_KEY);
  if (!stored) {
    return DEFAULT_RUNS_REVIEW_FILTER;
  }
  if (isRunsReviewFilterValue(stored)) {
    return stored;
  }
  return DEFAULT_RUNS_REVIEW_FILTER;
};

const persistRunsReviewFilter = (value: RunsReviewFilter) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(RUNS_REVIEW_FILTER_STORAGE_KEY, value);
};

const readStoredRunsPageSize = (): number => {
  if (typeof window === "undefined") {
    return DEFAULT_RUNS_PAGE_SIZE;
  }
  const stored = window.localStorage.getItem(RUNS_PAGE_SIZE_STORAGE_KEY);
  if (!stored) {
    return DEFAULT_RUNS_PAGE_SIZE;
  }
  const parsed = Number(stored);
  if (Number.isNaN(parsed) || parsed < 1 || parsed > MAX_RUNS_PAGE_SIZE) {
    return DEFAULT_RUNS_PAGE_SIZE;
  }
  return parsed;
};

const persistRunsPageSize = (value: number) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(RUNS_PAGE_SIZE_STORAGE_KEY, String(value));
};

const readStoredAutoRefreshInterval = (): number | null => {
  if (typeof window === "undefined") {
    return DEFAULT_AUTOREFRESH_SECONDS;
  }
  const stored = window.localStorage.getItem(AUTOREFRESH_STORAGE_KEY);
  if (!stored) {
    return DEFAULT_AUTOREFRESH_SECONDS;
  }
  if (stored === "off") {
    return null;
  }
  const parsed = Number(stored);
  if (Number.isNaN(parsed) || parsed <= 0) {
    return DEFAULT_AUTOREFRESH_SECONDS;
  }
  return parsed;
};

const persistAutoRefreshInterval = (value: string) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(AUTOREFRESH_STORAGE_KEY, value);
};

// ==========================================================================
// Run filtering logic
// ==========================================================================

/**
 * Check if a run matches a given filter bucket.
 * Uses executionSummary when available, falls back to reviewStatus only when executionSummary is absent.
 */
const runMatchesFilter = (run: RunsListEntry, filter: RunsReviewFilter, executionCountsComplete: boolean): boolean => {
  // "all" always matches
  if (filter === "all") {
    return true;
  }

  // Use executionSummary as source of truth when present
  const bucket = getRunFilterBucket(run.executionSummary);
  
  // If executionSummary is present and maps to a bucket, use it exclusively
  if (bucket !== null) {
    return bucket === filter;
  }

  // Fallback to reviewStatus only when executionSummary is null/missing
  // This preserves backward compatibility for older payloads without executionSummary
  switch (filter) {
    case "no-executions-yet":
      return run.reviewStatus === "no-executions" && executionCountsComplete;
    case "needs-attention":
      return run.reviewStatus === "unreviewed" || run.reviewStatus === "partially-reviewed";
    case "fully-executed":
      return run.reviewStatus === "fully-reviewed";
    case "no-executable-work":
    case "partially-executed":
      // These filter buckets don't have reviewStatus fallbacks - only executionSummary defines them
      return false;
    default:
      return false;
  }
};

// ==========================================================================
// Hook interface
// ==========================================================================

export interface UseRunSelectionReturn {
  /** Run list from RunControl (passed-through for convenience) */
  runs: RunsListEntry[];
  /** Loading state from RunControl (passed-through for convenience) */
  isLoading: boolean;
  /** Error state from RunControl (passed-through for convenience) */
  error: string | null;
  /** Selected run ID (echo of input) */
  selectedRunId: string | null;
  /** Whether execution counts are complete (derived from runs input) */
  executionCountsComplete: boolean;
  /** The most recent run ID (derived from runs input) */
  latestRunId: string | null;
  /** Whether the selected run is the latest */
  isLatest: boolean;
  /** The auto-refresh interval (owned by this hook, read by App.tsx for timer) */
  autoRefreshInterval: number | null;
  /** Handler for auto-refresh interval changes */
  handleAutoRefreshChange: (value: string) => void;
  /** Current filter for runs list */
  runsFilter: RunsReviewFilter;
  /** Setter for runs filter */
  setRunsFilter: (filter: RunsReviewFilter) => void;
  /** Number of runs per page */
  runsPageSize: number;
  /** Setter for page size */
  setRunsPageSize: (size: number) => void;
  /** Current page number (1-indexed) */
  runsPage: number;
  /** Setter for page number */
  setRunsPage: (page: number) => void;
  /** Following vs detached mode */
  isRunsListFollowingSelection: boolean;
  /** Setter for following mode */
  setIsRunsListFollowingSelection: (following: boolean) => void;
  /** Runs filtered by runsFilter */
  filteredRunsList: RunsListEntry[];
  /** Counts per filter */
  runsFilterCounts: Record<RunsReviewFilter, number>;
  /** Runs for current page */
  paginatedRunsList: RunsListEntry[];
  /** Total number of pages */
  totalRunsPages: number;
  /** Whether selected run is visible on current page */
  isSelectedRunVisibleOnCurrentRunsPage: boolean;
  /** Handler for filter changes */
  handleRunsFilterChange: (filter: RunsReviewFilter) => void;
  /** Handler for page size changes */
  handleRunsPageSizeChange: (size: number) => void;
  /** Handler for page changes */
  handleRunsPageChange: (page: number) => void;
  /** Compute page number for a given run ID */
  computePageForRunId: (runId: string | null) => number;
  /** Navigate to the page containing the given run ID */
  navigateToPageContainingRun: (runId: string | null) => void;
  /** Navigate to and highlight the selected run */
  handleShowSelectedRun: () => void;
}

export interface UseRunSelectionOptions {
  /**
   * Selected run ID from useRunControl.
   * This is an INPUT only. RunControl is the sole owner of selectedRunId.
   * Used for: highlighting, "show selected" button, following/detached navigation
   * Default: null (no selection)
   */
  selectedRunId?: string | null;

  /**
   * Run list from RunControl model.
   * REQUIRED INPUT - RunControl owns this data.
   * useRunSelection derives pagination and filtering from this input.
   * Default: [] (empty list)
   */
  runs?: RunsListEntry[];

  /**
   * Whether the runs list is loading.
   * REQUIRED INPUT - RunControl owns loading state.
   * Default: false
   */
  isLoading?: boolean;

  /**
   * Error message if runs list fetch failed.
   * REQUIRED INPUT - RunControl owns error state.
   * Default: null
   */
  error?: string | null;
}

export const useRunSelection = (options: UseRunSelectionOptions = {}): UseRunSelectionReturn => {
  const {
    selectedRunId = null,
    runs = [],
    isLoading = false,
    error = null,
  } = options;

  // autoRefreshInterval is owned by this hook; App.tsx reads it for timer management.
  const [autoRefreshInterval, setAutoRefreshInterval] = useState<number | null>(readStoredAutoRefreshInterval);
  const [runsFilter, setRunsFilter] = useState<RunsReviewFilter>(readStoredRunsReviewFilter);
  const [runsPageSize, setRunsPageSize] = useState<number>(readStoredRunsPageSize);
  const [runsPage, setRunsPage] = useState(1);
  const [isRunsListFollowingSelection, setIsRunsListFollowingSelection] = useState(true);

  const handleAutoRefreshChange = useCallback((value: string) => {
    persistAutoRefreshInterval(value);
    if (value === "off") {
      setAutoRefreshInterval(null);
    } else {
      const parsed = Number(value);
      setAutoRefreshInterval(Number.isNaN(parsed) || parsed <= 0 ? null : parsed);
    }
  }, []);

  const handleRunsFilterChange = useCallback((filter: RunsReviewFilter) => {
    setRunsFilter(filter);
    setRunsPage(1);
    persistRunsReviewFilter(filter);
  }, []);

  const handleRunsPageSizeChange = useCallback((newSize: number) => {
    setRunsPageSize(newSize);
    setRunsPage(1);
    setIsRunsListFollowingSelection(false);
    persistRunsPageSize(newSize);
  }, []);

  const handleRunsPageChange = useCallback((page: number) => {
    setRunsPage(page);
    setIsRunsListFollowingSelection(false);
  }, []);

  // TODO(phase-5): RunControl model.runs should expose executionCountsComplete
  // if the backend provides it. Currently hardcoded to true which may hide
  // incomplete-count state in the "no-executions" filter.
  const executionCountsComplete = true;

  const filteredRunsList = useMemo(() => {
    if (runsFilter === "all") {
      return runs;
    }
    return runs.filter((r) => runMatchesFilter(r, runsFilter, executionCountsComplete));
  }, [runs, runsFilter, executionCountsComplete]);

  const runsFilterCounts = useMemo(() => computeRunsFilterCounts(runs, executionCountsComplete), [runs, executionCountsComplete]);

  const computePageForRunId = useCallback((runId: string | null): number => {
    if (!runId) return 1;
    const index = filteredRunsList.findIndex((r) => r.runId === runId);
    if (index === -1) return 1;
    return Math.floor(index / runsPageSize) + 1;
  }, [filteredRunsList, runsPageSize]);

  const navigateToPageContainingRun = useCallback((runId: string | null) => {
    // Enable following mode so that subsequent run selection changes also navigate
    setIsRunsListFollowingSelection(true);
    const page = computePageForRunId(runId);
    setRunsPage(page);
  }, [computePageForRunId]);

  const handleShowSelectedRun = useCallback(() => {
    setIsRunsListFollowingSelection(true);
    navigateToPageContainingRun(selectedRunId);
  }, [selectedRunId, navigateToPageContainingRun]);

  const paginatedRunsList = useMemo(() => {
    const start = (runsPage - 1) * runsPageSize;
    const end = start + runsPageSize;
    return filteredRunsList.slice(start, end);
  }, [filteredRunsList, runsPage, runsPageSize]);

  const totalRunsPages = Math.ceil(filteredRunsList.length / runsPageSize);

  const isSelectedRunVisibleOnCurrentRunsPage = useMemo(() => {
    if (!selectedRunId) return false;
    return paginatedRunsList.some((r) => r.runId === selectedRunId);
  }, [paginatedRunsList, selectedRunId]);

  // latestRunId is derived from the runs input (passed from RunControl)
  const latestRunId = useMemo(() => {
    return runs.length > 0 ? runs[0].runId : null;
  }, [runs]);

  const isLatest = useMemo(() => {
    if (!selectedRunId || !latestRunId) {
      return true;
    }
    return selectedRunId === latestRunId;
  }, [selectedRunId, latestRunId]);

  // Keep runs list page synchronized with selected run when:
  // - selectedRunId is set
  // - isRunsListFollowingSelection is true (user hasn't manually navigated away)
  // - filteredRunsList changes (runs arrive from RunControl or filter changes)
  // - the selected run exists in the filtered list
  useEffect(() => {
    if (!selectedRunId) return;
    if (!isRunsListFollowingSelection) return;
    const runInFilteredList = filteredRunsList.find((r) => r.runId === selectedRunId);
    if (runInFilteredList) {
      navigateToPageContainingRun(selectedRunId);
    }
  }, [selectedRunId, filteredRunsList, navigateToPageContainingRun, isRunsListFollowingSelection]);

  return {
    // Pass-through values from inputs
    runs,
    isLoading,
    error,
    selectedRunId,
    executionCountsComplete,
    // Derived values
    latestRunId,
    isLatest,
    // Owned by this hook (read by App.tsx for timer management)
    autoRefreshInterval,
    handleAutoRefreshChange,
    // Pagination and filter state
    runsFilter,
    setRunsFilter,
    runsPageSize,
    setRunsPageSize,
    runsPage,
    setRunsPage,
    isRunsListFollowingSelection,
    setIsRunsListFollowingSelection,
    filteredRunsList,
    runsFilterCounts,
    paginatedRunsList,
    totalRunsPages,
    isSelectedRunVisibleOnCurrentRunsPage,
    handleRunsFilterChange,
    handleRunsPageSizeChange,
    handleRunsPageChange,
    computePageForRunId,
    navigateToPageContainingRun,
    handleShowSelectedRun,
  };
};