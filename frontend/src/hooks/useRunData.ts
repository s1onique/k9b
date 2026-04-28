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
 *   - requestedRunId: string | null - the run ID that was last requested (for debug/stale response guard)
 */
import { useCallback, useEffect, useRef, useState } from "react";
import dayjs from "dayjs";
import { fetchRun } from "../api";
import type { RunPayload } from "../types";

// ============================================================================
// Debug logging (gated by ?debugUi query parameter)
// ============================================================================

const DEBUG_UI_ENABLED = () => {
  if (typeof window === "undefined") return false;
  const params = new URLSearchParams(window.location.search);
  return params.has("debugUi");
};

const debugLog = (...args: Parameters<typeof console.log>) => {
  if (DEBUG_UI_ENABLED()) {
    console.log("[useRunData:debug]", ...args);
  }
};

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
  /** The run ID that was last requested (for debugging and stale-response guard) */
  requestedRunId: string | null;
}

export const useRunData = ({
  selectedRunId,
}: UseRunDataOptions): UseRunDataReturn => {
  const [run, setRun] = useState<RunPayload | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isError, setIsError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState(() => dayjs());
  const [autoRefreshInterval, setAutoRefreshInterval] = useState<number | null>(readStoredAutoRefreshInterval);
  const [requestedRunId, setRequestedRunId] = useState<string | null>(null);

  // Monotonic request sequence counter for stale-response guard.
  // This replaces the old single-flight lock (refreshInProgress) because that
  // pattern prevented a newer selected-run fetch from starting when an older
  // fetch was still in flight.
  //
  // Race scenario this fixes:
  // T0 latest fetch starts, requestSeq = 1
  // T1 user selects run-past, past fetch starts, requestSeq = 2
  // T2 latest fetch resolves, sees requestSeq changed to 2, ignores response
  // T3 past fetch resolves, requestSeq still 2, accepts response
  // Result: UI correctly shows past run (not split-brain)
  const requestSeqRef = useRef(0);

  const refresh = useCallback(async () => {
    // Capture the current sequence number for this fetch
    const requestSeq = ++requestSeqRef.current;
    const currentRequestedRunId = selectedRunId;
    setRequestedRunId(currentRequestedRunId);

    debugLog("fetch started", {
      requestSeq,
      selectedRunId: currentRequestedRunId,
      timestamp: new Date().toISOString(),
    });

    let active = true;
    try {
      setIsLoading(true);
      setIsError(null);
      const runPayload = await fetchRun(selectedRunId ?? undefined);

      // Guard against stale out-of-order responses:
      // If a newer fetch has started since this one began (requestSeq changed),
      // ignore this response to prevent overwriting newer data with stale data.
      if (requestSeq !== requestSeqRef.current) {
        debugLog("stale response ignored", {
          requestSeq,
          currentSeq: requestSeqRef.current,
          requestedWhenFetchStarted: currentRequestedRunId,
          returnedRunId: runPayload.runId,
        });
        return;
      }

      debugLog("fetch completed", {
        requestSeq,
        requestedRunId: currentRequestedRunId,
        returnedRunId: runPayload.runId,
        accepted: true,
      });

      if (active) {
        setRun(runPayload);
      }
      setLastRefresh(dayjs());
    } catch (err) {
      // Only set error if this is still the latest request
      if (requestSeq === requestSeqRef.current && active) {
        setIsError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      // Only clear loading if this is still the latest request
      if (requestSeq === requestSeqRef.current && active) {
        setIsLoading(false);
      }
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

  // Primary effect: fetch run data when selectedRunId changes.
  // This unconditional effect ensures refresh() is called whenever
  // selectedRunId changes, including when it transitions from/to null.
  // The refresh() function is already memoized with selectedRunId as
  // a dependency, so it captures the correct run ID at call time.
  useEffect(() => {
    refresh();
  }, [selectedRunId, refresh]);

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
    requestedRunId,
  };
};
