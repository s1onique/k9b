/**
 * useRunSelection hook - manages runs list fetching, selection, pagination, and filtering.
 *
 * Owns: fetching the runs list, selecting a run, navigating to latest, pagination, filtering.
 *
 * Inputs: (none - all state is internal)
 *
 * Returns:
 *   - runs: RunsListEntry[] - the list of runs
 *   - selectedRunId: string | null - the currently selected run ID
 *   - selectRun: (runId: string) => void - select a run by ID
 *   - isLoading: boolean - whether a fetch is in progress
 *   - error: string | null - error message if fetch failed
 *   - refreshRuns: () => Promise<void> - manually trigger a refresh
 *   - latestRunId: string | null - the most recent run ID
 *   - isLatest: boolean - whether the selected run is the latest
 *   - autoRefreshInterval: number | null - the auto-refresh interval used for runs list polling
 *   - runsFilter: RunsReviewFilter - current filter for runs list
 *   - setRunsFilter: (filter: RunsReviewFilter) => void
 *   - runsPageSize: number - number of runs per page
 *   - setRunsPageSize: (size: number) => void
 *   - runsPage: number - current page number (1-indexed)
 *   - setRunsPage: (page: number) => void
 *   - isRunsListFollowingSelection: boolean - whether auto-following selection
 *   - setIsRunsListFollowingSelection: (following: boolean) => void
 *   - filteredRunsList: RunsListEntry[] - runs filtered by runsFilter
 *   - runsFilterCounts: Record<RunsReviewFilter, number> - counts per filter
 *   - paginatedRunsList: RunsListEntry[] - runs for current page
 *   - totalRunsPages: number - total number of pages
 *   - isSelectedRunVisibleOnCurrentRunsPage: boolean
 *   - handleRunsFilterChange: (filter: RunsReviewFilter) => void
 *   - handleRunsPageSizeChange: (size: number) => void
 *   - handleRunsPageChange: (page: number) => void
 *   - handleShowSelectedRun: () => void
 *   - handleRunSelection: (runId: string) => void
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchRunsList } from "../api";
import type { RunsListEntry, RunsListPayload } from "../types";

export const SELECTED_RUN_STORAGE_KEY = "dashboard-selected-run-id";
export const AUTOREFRESH_STORAGE_KEY = "dashboard-autorefresh-interval";
const DEFAULT_AUTOREFRESH_SECONDS = 5;

// Review status filter types for recent runs panel
// Uses reviewStatus from backend: "no-executions", "unreviewed", "partially-reviewed", "fully-reviewed"
export type RunsReviewFilter = "all" | "no-executions" | "awaiting-review" | "partially-reviewed" | "fully-reviewed" | "needs-attention";

export const RUNS_REVIEW_FILTER_OPTIONS: { label: string; value: RunsReviewFilter }[] = [
  { label: "All runs", value: "all" },
  { label: "No executions yet", value: "no-executions" },
  { label: "Awaiting review", value: "awaiting-review" },
  { label: "Partially reviewed", value: "partially-reviewed" },
  { label: "Fully reviewed", value: "fully-reviewed" },
  { label: "Needs attention", value: "needs-attention" },
];

const RUNS_REVIEW_FILTER_VALUES: RunsReviewFilter[] = ["all", "no-executions", "awaiting-review", "partially-reviewed", "fully-reviewed", "needs-attention"];

const isRunsReviewFilterValue = (value: unknown): value is RunsReviewFilter =>
  typeof value === "string" && RUNS_REVIEW_FILTER_VALUES.includes(value as RunsReviewFilter);

export const RUNS_REVIEW_FILTER_STORAGE_KEY = "dashboard-runs-review-filter";
export const RUNS_PAGE_SIZE_STORAGE_KEY = "dashboard-runs-page-size";

const DEFAULT_RUNS_REVIEW_FILTER: RunsReviewFilter = "all";
const DEFAULT_RUNS_PAGE_SIZE = 5;
const MAX_RUNS_PAGE_SIZE = 20;
export const RUNS_PAGE_SIZE_OPTIONS = [5, 10, 20] as const;

// Compute filter counts from runs list
export const computeRunsFilterCounts = (
  runs: RunsListEntry[]
): Record<RunsReviewFilter, number> => {
  const counts: Record<RunsReviewFilter, number> = {
    all: runs.length,
    "no-executions": 0,
    "awaiting-review": 0,
    "partially-reviewed": 0,
    "fully-reviewed": 0,
    "needs-attention": 0,
  };

  runs.forEach((run) => {
    if (run.reviewStatus === "no-executions") {
      counts["no-executions"]++;
    } else if (run.reviewStatus === "unreviewed") {
      counts["awaiting-review"]++;
      counts["needs-attention"]++;
    } else if (run.reviewStatus === "partially-reviewed") {
      counts["partially-reviewed"]++;
      counts["needs-attention"]++;
    } else if (run.reviewStatus === "fully-reviewed") {
      counts["fully-reviewed"]++;
    }
  });

  return counts;
};

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

const isRunsPageSizeValue = (value: unknown): value is typeof RUNS_PAGE_SIZE_OPTIONS[number] =>
  typeof value === "number" && RUNS_PAGE_SIZE_OPTIONS.includes(value as typeof RUNS_PAGE_SIZE_OPTIONS[number]);

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

const readStoredSelectedRunId = (): string | null => {
  if (typeof window === "undefined") {
    return null;
  }
  const stored = window.localStorage.getItem(SELECTED_RUN_STORAGE_KEY);
  if (!stored) {
    return null;
  }
  return stored;
};

const persistSelectedRunId = (runId: string | null) => {
  if (typeof window === "undefined") {
    return;
  }
  if (runId) {
    window.localStorage.setItem(SELECTED_RUN_STORAGE_KEY, runId);
  } else {
    window.localStorage.removeItem(SELECTED_RUN_STORAGE_KEY);
  }
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

export interface UseRunSelectionReturn {
  runs: RunsListEntry[];
  selectedRunId: string | null;
  selectRun: (runId: string) => void;
  isLoading: boolean;
  error: string | null;
  refreshRuns: () => Promise<void>;
  latestRunId: string | null;
  isLatest: boolean;
  jumpToLatest: () => void;
  autoRefreshInterval: number | null;
  handleAutoRefreshChange: (value: string) => void;
  // Pagination and filter state
  runsFilter: RunsReviewFilter;
  setRunsFilter: (filter: RunsReviewFilter) => void;
  runsPageSize: number;
  setRunsPageSize: (size: number) => void;
  runsPage: number;
  setRunsPage: (page: number) => void;
  isRunsListFollowingSelection: boolean;
  setIsRunsListFollowingSelection: (following: boolean) => void;
  filteredRunsList: RunsListEntry[];
  runsFilterCounts: Record<RunsReviewFilter, number>;
  paginatedRunsList: RunsListEntry[];
  totalRunsPages: number;
  isSelectedRunVisibleOnCurrentRunsPage: boolean;
  handleRunsFilterChange: (filter: RunsReviewFilter) => void;
  handleRunsPageSizeChange: (size: number) => void;
  handleRunsPageChange: (page: number) => void;
  computePageForRunId: (runId: string | null) => number;
  navigateToPageContainingRun: (runId: string | null) => void;
  handleShowSelectedRun: () => void;
  handleRunSelection: (runId: string) => void;
}

export const useRunSelection = (): UseRunSelectionReturn => {
  const [runs, setRuns] = useState<RunsListEntry[]>([]);
  const [selectedRunId, setSelectedRunIdState] = useState<string | null>(readStoredSelectedRunId);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<number>(0);

  // Auto-refresh interval state for runs list polling
  const [autoRefreshInterval, setAutoRefreshInterval] = useState<number | null>(readStoredAutoRefreshInterval);

  // Pagination and filter state for runs list
  const [runsFilter, setRunsFilter] = useState<RunsReviewFilter>(readStoredRunsReviewFilter);
  const [runsPageSize, setRunsPageSize] = useState<number>(readStoredRunsPageSize);
  const [runsPage, setRunsPage] = useState(1);

  /**
   * Follow/detached mode for Recent runs pagination.
   *
   * When `isRunsListFollowingSelection === true`:
   *   - The table auto-navigates to show the selected run after refresh.
   *   - Selecting a run, clicking ← Latest, or clicking "Show selected run"
   *     keeps follow mode active.
   *
   * When `isRunsListFollowingSelection === false` (detached):
   *   - Manual page navigation preserves the current browsing position.
   *   - Refresh does NOT jump to the selected run's page.
   *   - The operator can browse historical pages while another run is selected.
   *
   * Transitions to follow mode:
   *   - User selects a run from the table
   *   - User clicks ← Latest
   *   - User clicks "Show selected run"
   *
   * Transitions to detached mode:
   *   - User manually changes the page
   *   - User manually changes page size
   */
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

  // Reset to page 1 when filter changes
  const handleRunsFilterChange = useCallback((filter: RunsReviewFilter) => {
    setRunsFilter(filter);
    setRunsPage(1);
    persistRunsReviewFilter(filter);
  }, []);

  // Handle page size change - transitions to detached mode
  const handleRunsPageSizeChange = useCallback((newSize: number) => {
    setRunsPageSize(newSize);
    setRunsPage(1); // Reset to first page when page size changes
    setIsRunsListFollowingSelection(false); // Detach: manual page size change
    persistRunsPageSize(newSize);
  }, []);

  // Handle manual page change - transitions to detached mode
  const handleRunsPageChange = useCallback((page: number) => {
    setRunsPage(page);
    setIsRunsListFollowingSelection(false); // Detach: manual navigation
  }, []);

  // Filter runs based on selected filter
  const filteredRunsList = useMemo(() => {
    if (runsFilter === "all") {
      return runs;
    }
    return runs.filter((r) => {
      if (runsFilter === "no-executions") {
        return r.reviewStatus === "no-executions";
      }
      if (runsFilter === "awaiting-review") {
        return r.reviewStatus === "unreviewed";
      }
      if (runsFilter === "partially-reviewed") {
        return r.reviewStatus === "partially-reviewed";
      }
      if (runsFilter === "fully-reviewed") {
        return r.reviewStatus === "fully-reviewed";
      }
      if (runsFilter === "needs-attention") {
        return r.reviewStatus === "unreviewed" || r.reviewStatus === "partially-reviewed";
      }
      return true;
    });
  }, [runs, runsFilter]);

  // Compute filter counts
  const runsFilterCounts = useMemo(() => computeRunsFilterCounts(runs), [runs]);

  // Compute the page number for a given runId within the filtered list
  const computePageForRunId = useCallback((runId: string | null): number => {
    if (!runId) return 1;
    const index = filteredRunsList.findIndex((r) => r.runId === runId);
    if (index === -1) return 1;
    return Math.floor(index / runsPageSize) + 1;
  }, [filteredRunsList, runsPageSize]);

  // Navigate to the page containing the given runId
  const navigateToPageContainingRun = useCallback((runId: string | null) => {
    const page = computePageForRunId(runId);
    setRunsPage(page);
  }, [computePageForRunId]);

  // Navigate to the page containing the selected run and switch to follow mode
  const handleShowSelectedRun = useCallback(() => {
    setIsRunsListFollowingSelection(true); // Re-engage follow mode
    navigateToPageContainingRun(selectedRunId);
  }, [selectedRunId, navigateToPageContainingRun]);

  // Computed paginated runs list
  const paginatedRunsList = useMemo(() => {
    const start = (runsPage - 1) * runsPageSize;
    const end = start + runsPageSize;
    return filteredRunsList.slice(start, end);
  }, [filteredRunsList, runsPage, runsPageSize]);

  const totalRunsPages = Math.ceil(filteredRunsList.length / runsPageSize);

  // Derived boolean: true when the selected run is visible on the current page.
  // Used to suppress the detached notice when the operator can already see the selected run.
  const isSelectedRunVisibleOnCurrentRunsPage = useMemo(() => {
    if (!selectedRunId) return false;
    return paginatedRunsList.some((r) => r.runId === selectedRunId);
  }, [paginatedRunsList, selectedRunId]);

  // Ref to track if a refresh is in progress to prevent duplicate fetches
  const refreshInProgress = useRef(false);

  // Derive the latest run ID from the runs list
  // Use the first run in the list (assuming it's sorted newest first by the backend)
  const latestRunId = useMemo(() => {
    return runs.length > 0 ? runs[0].runId : null;
  }, [runs]);

  // Determine if the selected run is the latest
  const isLatest = useMemo(() => {
    if (!selectedRunId || !latestRunId) {
      return true; // Default to true if no selection or no runs
    }
    return selectedRunId === latestRunId;
  }, [selectedRunId, latestRunId]);

  const refreshRuns = useCallback(async () => {
    // Prevent overlapping refresh requests
    if (refreshInProgress.current) {
      return;
    }
    refreshInProgress.current = true;
    let active = true;
    try {
      setError(null);
      const payload: RunsListPayload = await fetchRunsList();
      if (active) {
        // Sort runs by timestamp descending (newest first)
        const sortedRuns = [...payload.runs].sort(
          (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
        );
        setRuns(sortedRuns);
        setLastFetch(Date.now());
      }
    } catch (err) {
      if (active) {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      refreshInProgress.current = false;
    }
  }, []);

  // Initial fetch when component mounts
  useEffect(() => {
    setIsLoading(true);
    refreshRuns().finally(() => {
      setIsLoading(false);
    });
  }, [refreshRuns]);

  // Auto-select the latest run if no run is selected
  useEffect(() => {
    if (!selectedRunId && latestRunId) {
      setSelectedRunIdState(latestRunId);
    }
  }, [selectedRunId, latestRunId]);

  // Auto-refresh polling for runs list - polls the runs list endpoint
  // to surface new runs without requiring a full browser reload.
  useEffect(() => {
    if (!autoRefreshInterval) return;
    const timerId = setInterval(() => {
      refreshRuns();
    }, autoRefreshInterval * 1000);
    return () => clearInterval(timerId);
  }, [autoRefreshInterval, refreshRuns]);

  const selectRun = useCallback(
    (runId: string) => {
      persistSelectedRunId(runId);
      setSelectedRunIdState(runId);
    },
    []
  );

  const jumpToLatest = useCallback(() => {
    if (latestRunId) {
      persistSelectedRunId(latestRunId);
      setSelectedRunIdState(latestRunId);
      // Also navigate to page 1 (where latest run is in default newest-first ordering)
      setRunsPage(1);
    }
  }, [latestRunId]);

  // Navigate to the page containing the selected run when it changes
  // This ensures the table shows the row for the selected run
  const handleRunSelection = useCallback((runId: string) => {
    persistSelectedRunId(runId);
    setSelectedRunIdState(runId);
    // Navigate to the page containing the selected run
    navigateToPageContainingRun(runId);
  }, [navigateToPageContainingRun]);

  // Effect: After runs list refresh, navigate to the page containing the selected run.
  // This ensures the selected row remains visible after manual refresh or auto-refresh.
  // If the selected run is filtered out, selection state is preserved but the row won't be visible.
  // Only auto-navigates when in follow mode (isRunsListFollowingSelection === true).
  useEffect(() => {
    if (!selectedRunId) return;
    if (!isRunsListFollowingSelection) return;
    // Check if selected run exists in the filtered list
    const runInFilteredList = filteredRunsList.find((r) => r.runId === selectedRunId);
    if (runInFilteredList) {
      // Selected run is in filtered dataset - navigate to its page to keep it visible
      navigateToPageContainingRun(selectedRunId);
    }
    // If not in filtered list, we intentionally do NOT change runsPage here.
    // The selection state remains intact (for the header/detail view).
  }, [selectedRunId, filteredRunsList, navigateToPageContainingRun, isRunsListFollowingSelection]);

  return {
    runs,
    selectedRunId,
    selectRun,
    isLoading,
    error,
    refreshRuns,
    latestRunId,
    isLatest,
    jumpToLatest,
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
    handleRunSelection,
  };
};
