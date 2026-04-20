/**
 * useRunSelection hook - manages runs list fetching and selection state.
 *
 * Owns: fetching the runs list, selecting a run, navigating to latest.
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
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchRunsList } from "../api";
import type { RunsListEntry, RunsListPayload } from "../types";

export const SELECTED_RUN_STORAGE_KEY = "dashboard-selected-run-id";
export const AUTOREFRESH_STORAGE_KEY = "dashboard-autorefresh-interval";
const DEFAULT_AUTOREFRESH_SECONDS = 5;

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
}

export const useRunSelection = (): UseRunSelectionReturn => {
  const [runs, setRuns] = useState<RunsListEntry[]>([]);
  const [selectedRunId, setSelectedRunIdState] = useState<string | null>(readStoredSelectedRunId);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<number>(0);

  // Auto-refresh interval state for runs list polling
  const [autoRefreshInterval, setAutoRefreshInterval] = useState<number | null>(readStoredAutoRefreshInterval);

  const handleAutoRefreshChange = useCallback((value: string) => {
    persistAutoRefreshInterval(value);
    if (value === "off") {
      setAutoRefreshInterval(null);
    } else {
      const parsed = Number(value);
      setAutoRefreshInterval(Number.isNaN(parsed) || parsed <= 0 ? null : parsed);
    }
  }, []);

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
    }
  }, [latestRunId]);

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
  };
};
