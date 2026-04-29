/**
 * useRunSelection hook — manages runs list UI (fetching, pagination, filtering).
 *
 * PHASE 3/4: This hook is list UI only. It does NOT own selected-run data.
 *
 * selectedRunId ownership:
 *   - RunControl owns selectedRunId as the source of truth for selected-run causality.
 *   - useRunSelection receives selectedRunId as an INPUT (from RunControl).
 *   - selectedRunId is used for:
 *     - Highlighting the selected run in the list
 *     - "Show Selected" / handleShowSelectedRun button
 *     - Following mode: auto-navigate to the page containing the selected run
 *     - Detached mode: when isRunsListFollowingSelection is false, the user has
 *       manually navigated away from the selected run's page
 *
 * NOTE: This hook fetches /api/runs for list UI purposes (visible list filtering/pagination).
 * During the migration, useRunControl also fetches /api/runs for runs list ownership.
 * Future consolidation can merge these once the UI list state is migrated to RunControl.
 *
 * Inputs:
 *   - selectedRunId: string | null - selected run from useRunControl (REQUIRED INPUT)
 *     Used for: highlighting, "show selected" button, following/detached navigation
 *
 * Returns:
 *   - runs: RunsListEntry[] - the list of runs (fetched for list UI)
 *   - executionCountsComplete: boolean - whether execution counts are complete
 *     NOTE: When false, "no-executions" filter may be unreliable (counts may be stale/incomplete).
 *     The backend may not have finished computing execution counts for recent runs.
 *   - selectedRunId: string | null - echo of the input, for convenience
 *   - isLoading: boolean - whether a fetch is in progress
 *   - error: string | null - error message if fetch failed
 *   - refreshRuns: () => Promise<void> - manually trigger a refresh
 *   - latestRunId: string | null - the most recent run ID
 *   - isLatest: boolean - whether the selected run is the latest
 *   - autoRefreshInterval: number | null - the auto-refresh interval used for runs list polling
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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchRunsList } from "../api";
import type { RunsListEntry, RunsListPayload } from "../types";

export const AUTOREFRESH_STORAGE_KEY = "dashboard-autorefresh-interval";
const DEFAULT_AUTOREFRESH_SECONDS = 5;

// Review status filter types for recent runs panel
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
  runs: RunsListEntry[],
  executionCountsComplete: boolean = true
): Record<RunsReviewFilter, number> => {
  const counts: Record<RunsReviewFilter, number> = {
    all: runs.length,
    'no-executions': 0,
    'awaiting-review': 0,
    'partially-reviewed': 0,
    'fully-reviewed': 0,
    'needs-attention': 0,
  };

  runs.forEach((run) => {
    if (run.reviewStatus === 'no-executions') {
      if (executionCountsComplete) {
        counts['no-executions']++;
      }
    } else if (run.reviewStatus === 'unreviewed') {
      counts['awaiting-review']++;
      counts['needs-attention']++;
    } else if (run.reviewStatus === 'partially-reviewed') {
      counts['partially-reviewed']++;
      counts['needs-attention']++;
    } else if (run.reviewStatus === 'fully-reviewed') {
      counts['fully-reviewed']++;
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

/**
 * Determines the display status for a run in the Recent Runs table.
 */
export type RunsDisplayStatus = "no-executions" | "unreviewed" | "partially-reviewed" | "fully-reviewed" | "unknown";

export type RunsReviewStatus = RunsListEntry["reviewStatus"];

export const getRunsDisplayStatus = (
  reviewStatus: RunsReviewStatus,
  executionCountsComplete: boolean,
): RunsDisplayStatus => {
  if (!executionCountsComplete && reviewStatus === "no-executions") {
    return "unknown";
  }
  return reviewStatus;
};

export interface UseRunSelectionReturn {
  runs: RunsListEntry[];
  executionCountsComplete: boolean;
  selectedRunId: string | null;
  isLoading: boolean;
  error: string | null;
  refreshRuns: () => Promise<void>;
  latestRunId: string | null;
  isLatest: boolean;
  autoRefreshInterval: number | null;
  handleAutoRefreshChange: (value: string) => void;
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
}

export interface UseRunSelectionOptions {
  /**
   * Selected run ID from useRunControl.
   * PHASE 3: useRunSelection no longer owns selectedRunId - useRunControl is the sole owner.
   * Default: null (no selection)
   */
  selectedRunId?: string | null;
}

export const useRunSelection = (options: UseRunSelectionOptions = {}): UseRunSelectionReturn => {
  // PHASE 3: selectedRunId is controlled via props from useRunControl
  const { selectedRunId = null } = options;

  const [runs, setRuns] = useState<RunsListEntry[]>([]);
  const [executionCountsComplete, setExecutionCountsComplete] = useState<boolean>(true);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  const refreshInProgress = useRef(false);

  const latestRunId = useMemo(() => {
    return runs.length > 0 ? runs[0].runId : null;
  }, [runs]);

  const isLatest = useMemo(() => {
    if (!selectedRunId || !latestRunId) {
      return true;
    }
    return selectedRunId === latestRunId;
  }, [selectedRunId, latestRunId]);

  const refreshRuns = useCallback(async () => {
    if (refreshInProgress.current) {
      return;
    }
    refreshInProgress.current = true;
    let active = true;
    try {
      setError(null);
      const payload: RunsListPayload = await fetchRunsList();
      if (active) {
        const sortedRuns = [...payload.runs].sort(
          (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
        );
        setRuns(sortedRuns);
        setExecutionCountsComplete(payload.executionCountsComplete ?? true);
      }
    } catch (err) {
      if (active) {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      refreshInProgress.current = false;
    }
  }, []);

  useEffect(() => {
    setIsLoading(true);
    refreshRuns().finally(() => {
      setIsLoading(false);
    });
  }, [refreshRuns]);

  useEffect(() => {
    if (!autoRefreshInterval) return;
    const timerId = setInterval(() => {
      refreshRuns();
    }, autoRefreshInterval * 1000);
    return () => clearInterval(timerId);
  }, [autoRefreshInterval, refreshRuns]);

  // Effect: After runs list refresh, navigate to the page containing the selected run.
  useEffect(() => {
    if (!selectedRunId) return;
    if (!isRunsListFollowingSelection) return;
    const runInFilteredList = filteredRunsList.find((r) => r.runId === selectedRunId);
    if (runInFilteredList) {
      navigateToPageContainingRun(selectedRunId);
    }
  }, [selectedRunId, filteredRunsList, navigateToPageContainingRun, isRunsListFollowingSelection]);

  return {
    runs,
    executionCountsComplete,
    selectedRunId,
    isLoading,
    error,
    refreshRuns,
    latestRunId,
    isLatest,
    autoRefreshInterval,
    handleAutoRefreshChange,
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
