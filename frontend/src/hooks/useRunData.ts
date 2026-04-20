/**
 * useRunData hook - manages run payload fetching, polling, and auto-refresh.
 *
 * Owns: fetching the current run payload, polling interval, auto-refresh state.
 *
 * Inputs:
 *   - selectedRunId: string | null - the run ID to fetch
 *
 * Returns:
 *   - run: RunPayload | null - the current run payload
 *   - isLoading: boolean - whether a fetch is in progress
 *   - isError: string | null - error message if fetch failed
 *   - lastRefresh: Dayjs - timestamp of last successful refresh
 *   - refresh: () => Promise<void> - manually trigger a refresh
 *   - autoRefreshInterval: number | null - current auto-refresh interval in seconds
 *   - handleAutoRefreshChange: (value: string) => void - handler for auto-refresh select
 */
import { useCallback, useEffect, useRef, useState } from "react";
import dayjs from "dayjs";
import { fetchRun } from "../api";
import type { RunPayload } from "../types";

export const AUTOREFRESH_STORAGE_KEY = "dashboard-autorefresh-interval";
const DEFAULT_AUTOREFRESH_SECONDS = 5;
const AUTOREFRESH_OPTIONS = [
  { label: "Off", value: "off" },
  { label: "5s", value: "5" },
  { label: "10s", value: "10" },
  { label: "30s", value: "30" },
  { label: "1m", value: "60" },
  { label: "5m", value: "300" },
] as const;

const readStoredAutoRefreshInterval = () => {
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

export interface UseRunDataOptions {
  selectedRunId: string | null;
}

export interface UseRunDataReturn {
  run: RunPayload | null;
  isLoading: boolean;
  isError: string | null;
  lastRefresh: dayjs.Dayjs;
  refresh: () => Promise<void>;
  autoRefreshInterval: number | null;
  handleAutoRefreshChange: (value: string) => void;
}

export const useRunData = ({
  selectedRunId,
}: UseRunDataOptions): UseRunDataReturn => {
  const [run, setRun] = useState<RunPayload | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isError, setIsError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState(() => dayjs());
  const [autoRefreshInterval, setAutoRefreshInterval] = useState<number | null>(readStoredAutoRefreshInterval);

  // Ref to track if a refresh is in progress to prevent duplicate fetches
  const refreshInProgress = useRef(false);

  const refresh = useCallback(async () => {
    // Prevent overlapping refresh requests
    if (refreshInProgress.current) {
      return;
    }
    refreshInProgress.current = true;
    let active = true;
    try {
      setIsLoading(true);
      setIsError(null);
      const runPayload = await fetchRun(selectedRunId ?? undefined);
      if (active) {
        setRun(runPayload);
      }
      setLastRefresh(dayjs());
    } catch (err) {
      if (active) {
        setIsError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (active) {
        setIsLoading(false);
      }
      refreshInProgress.current = false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRunId]);

  // Auto-refresh interval effect
  useEffect(() => {
    let timerId: ReturnType<typeof setInterval> | null = null;
    if (autoRefreshInterval) {
      timerId = setInterval(() => {
        refresh();
      }, autoRefreshInterval * 1000);
    }
    return () => {
      if (timerId !== null) {
        clearInterval(timerId);
      }
    };
  }, [autoRefreshInterval, refresh]);

  // Visibility change effect - refresh when tab becomes visible
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        refresh();
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [refresh]);

  const handleAutoRefreshChange = useCallback(
    (value: string) => {
      if (value === "off") {
        persistAutoRefreshInterval("off");
        setAutoRefreshInterval(null);
        return;
      }
      const parsed = Number(value);
      if (!Number.isNaN(parsed) && parsed > 0) {
        persistAutoRefreshInterval(value);
        setAutoRefreshInterval(parsed);
      }
    },
    []
  );

  return {
    run,
    isLoading,
    isError,
    lastRefresh,
    refresh,
    autoRefreshInterval,
    handleAutoRefreshChange,
  };
};
