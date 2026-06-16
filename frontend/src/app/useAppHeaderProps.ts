/**
 * useAppHeaderProps — Hook for App header derived props and freshness state
 *
 * Extracts from App.tsx:
 * - headerRunTimestamp, runFresh, runAgeMinutes (freshness-related derived values)
 * - AppHeader props construction
 *
 * Dependencies shared with useAppDemoShellOverlayProps:
 * - headerRunTimestamp (used for runCapturedAt in realContext)
 * - runFresh (used for isFresh in realContext)
 * - runAgeMinutes (passed through to finding selection input)
 *
 * Does NOT change AppHeader rendering, freshness thresholds, latest/past semantics,
 * refresh/auto-refresh behavior, or demo shell realContext derivation.
 */

import dayjs from "dayjs";

import type { RunPayload, RunsListEntry } from "../types";
import { formatDuration } from "../components/ExecutionHistoryPanel";
import { relativeRecency } from "../utils";
import { isStaleTimestamp } from "../utils/selectors";
import type { AppHeaderProps } from "./AppHeader";

export interface UseAppHeaderPropsArgs {
  /** Selected run payload */
  run: RunPayload | null;
  /** List of all runs (from RunControl) */
  runsList: RunsListEntry[];
  /** Currently selected run ID */
  selectedRunId: string | null;
  /** Whether the selected run is the latest run */
  isSelectedRunLatest: boolean;
  /** Run ID of the latest run */
  latestRunId: string | null;
  /** Last refresh timestamp as Dayjs object */
  lastRefresh: ReturnType<typeof dayjs>;
  /** Auto-refresh interval in seconds */
  autoRefreshInterval: number | undefined;
  /** Refresh handler */
  refresh: () => void;
  /** Auto-refresh interval change handler */
  handleAutoRefreshChange: (value: string) => void;
  /** Click to jump to latest run handler */
  clickLatest: () => void;
  /** Clock seam for testability (optional, defaults to real time) */
  clock?: dayjs.Dayjs;
}

export interface UseAppHeaderPropsReturn {
  /** Props for AppHeader component (excludes onOpenDemo - provided by App.tsx) */
  headerDerivedProps: Omit<AppHeaderProps, "onOpenDemo">;
  /** Timestamp when the run was captured (used by demo shell realContext) */
  headerRunTimestamp: string;
  /** Whether the run is fresh (not stale per freshness threshold) */
  runFresh: boolean;
  /** Age of the run in minutes */
  runAgeMinutes: number;
  /** Run duration statistics for display in run summary */
  headerStats: Array<{ label: string; value: string }>;
}

/**
 * Derives App header props and freshness-related values from App.tsx.
 *
 * Centralizes:
 * - Selected run list entry lookup
 * - Header timestamp derivation
 * - Freshness computation (runFresh, runAgeMinutes)
 * - AppHeader prop construction
 *
 * These values are derived from the same source data (run, runsList, selectedRunId, latestRunId)
 * but are needed by both AppHeader for display and useAppDemoShellOverlayProps for realContext.
 *
 * Must be called BEFORE the loading guard in App.tsx because:
 * - headerRunTimestamp/headerRunId/headerRunLabel are used by AppHeader rendering
 * - runFresh/runAgeMinutes are needed by useAppDemoShellOverlayProps
 */
export function useAppHeaderProps({
  run,
  runsList,
  selectedRunId,
  isSelectedRunLatest,
  latestRunId,
  lastRefresh,
  autoRefreshInterval,
  refresh,
  handleAutoRefreshChange,
  clickLatest,
  clock,
}: UseAppHeaderPropsArgs): UseAppHeaderPropsReturn {
  const currentTime = clock ?? dayjs();

  // Find selected run in the runs list for timestamp/label/id
  const selectedRunListEntry = runsList.find((r) => r.runId === selectedRunId) ?? null;

  // Header timestamp: derive from list entry or run payload
  // This is used by AppHeader for freshness indicator and by demo shell for runCapturedAt
  const headerRunTimestamp = selectedRunListEntry?.timestamp ?? run?.timestamp ?? "";

  // Freshness computation
  // runFresh controls whether the freshness indicator is shown in AppHeader
  // runAgeMinutes is passed through to useAppDemoShellOverlayProps
  const runFresh = !isStaleTimestamp(headerRunTimestamp, currentTime);
  const runAgeMinutes = headerRunTimestamp
    ? Math.floor(currentTime.diff(dayjs(headerRunTimestamp), "minute"))
    : 0;

  // Run header display values from list entry or run payload
  const headerRunId = selectedRunListEntry?.runId ?? run?.runId ?? "—";
  const headerRunLabel = selectedRunListEntry?.runLabel ?? run?.label ?? "—";

  // Recency string for selected run (used in AppHeader)
  const runRecency = headerRunTimestamp ? relativeRecency(headerRunTimestamp) : "—";

  // Latest run recency (shown when selected run is NOT the latest)
  const latestRunTimestamp = latestRunId
    ? runsList.find((r) => r.runId === latestRunId)?.timestamp ?? headerRunTimestamp
    : headerRunTimestamp;
  const latestRunRecency = latestRunTimestamp ? relativeRecency(latestRunTimestamp) : "—";

  // Run duration stats for run summary (moved from useRunHeaderModel)
  const headerStats = run
    ? [
        { label: "Last", value: formatDuration(run.runStats.lastRunDurationSeconds) },
        { label: "Runs", value: String(run.runStats.totalRuns) },
        { label: "P50", value: formatDuration(run.runStats.p50RunDurationSeconds) },
        { label: "P95", value: formatDuration(run.runStats.p95RunDurationSeconds) },
        { label: "P99", value: formatDuration(run.runStats.p99RunDurationSeconds) },
      ]
    : [];

  // Build header derived props (excludes onOpenDemo - provided by App.tsx)
  const headerDerivedProps: Omit<AppHeaderProps, "onOpenDemo"> = {
    headerRunId,
    headerRunLabel,
    headerRunTimestamp,
    isSelectedRunLatest,
    latestRunRecency,
    runRecency,
    lastRefresh,
    onRefresh: refresh,
    autoRefreshInterval,
    onAutoRefreshChange: handleAutoRefreshChange,
    onClickLatest: clickLatest,
    clock: currentTime,
  };

  return {
    headerDerivedProps,
    headerRunTimestamp,
    runFresh,
    runAgeMinutes,
    headerStats,
  };
}
