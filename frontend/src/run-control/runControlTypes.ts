/**
 * runControlTypes.ts — Elm-ish Run Control Plane type definitions.
 *
 * Phase 1: Pure types, reducer, selectors, initializer.
 *
 * Design constraints:
 * - No Date.now() inside reducer or selectors.
 * - No fetch, setTimeout, setInterval, localStorage, window access, or console logging inside reducer.
 * - All time enters via message fields: nowMs, receivedAtMs, failedAtMs.
 * - Effects are data only.
 * - Slow state is explicit: loading becomes slow only after RunSlowThresholdReached.
 */

import type { RunPayload, RunsListEntry, RunsListPayload } from "../types";

// ============================================================================
// Model
// ============================================================================

/**
 * Runs list state.
 */
export interface RunsState {
  status: "idle" | "loading" | "loaded" | "failed";
  requestSeq: number | null;
  items: RunsListEntry[];
  error: string | null;
  lastLoadedAtMs: number | null;
  lastRefreshReason: "boot" | "manual" | "poll" | null;
}

/**
 * Selected run state.
 */
export interface SelectedRunState {
  status: "idle" | "loading" | "slow" | "loaded" | "failed";
  requestSeq: number | null;
  requestedRunId: string | null;
  payload: RunPayload | null;
  error: string | null;
  startedAtMs: number | null;
  lastLoadedRunId: string | null;
  lastLoadedAtMs: number | null;
  lastErrorAtMs: number | null;
  slowAfterMs: number;
}

/**
 * Selection tracking state.
 */
export interface SelectionState {
  selectedRunId: string | null;
  latestRunId: string | null;
  selectedReason:
    | "boot"
    | "user"
    | "latest-click"
    | "manual-refresh-preserve-selection"
    | "poll-preserve-selection"
    | "fallback-to-latest"
    | null;
}

/**
 * Freshness tracking state.
 */
export interface FreshnessState {
  hasNewerLatest: boolean;
  latestKnownAtMs: number | null;
}

/**
 * Debug state.
 */
export interface DebugState {
  enabled: boolean;
}

/**
 * The root run control model.
 */
export interface RunControlModel {
  nextRequestSeq: number;
  runs: RunsState;
  selection: SelectionState;
  selectedRun: SelectedRunState;
  freshness: FreshnessState;
  debug: DebugState;
}

// ============================================================================
// Messages
// ============================================================================

/**
 * Boot message — initiates the app load sequence.
 */
export type BootMsg = {
  type: "Boot";
  nowMs: number;
};

/**
 * Debug mode toggle message.
 */
export type DebugModeDetectedMsg = {
  type: "DebugModeDetected";
  enabled: boolean;
};

/**
 * Request runs list.
 */
export type RunsRequestedMsg = {
  type: "RunsRequested";
  reason: "boot" | "manual" | "poll";
  nowMs: number;
};

/**
 * Runs list loaded successfully.
 */
export type RunsLoadedMsg = {
  type: "RunsLoaded";
  requestSeq: number;
  payload: RunsListPayload;
  receivedAtMs: number;
};

/**
 * Runs list fetch failed.
 */
export type RunsFailedMsg = {
  type: "RunsFailed";
  requestSeq: number;
  error: string;
  failedAtMs: number;
};

/**
 * User selects a run from the runs list.
 */
export type RunSelectedMsg = {
  type: "RunSelected";
  runId: string;
  nowMs: number;
};

/**
 * User clicks the "Latest" button.
 */
export type LatestClickedMsg = {
  type: "LatestClicked";
  nowMs: number;
};

/**
 * User clears the selection.
 */
export type SelectionClearedMsg = {
  type: "SelectionCleared";
};

/**
 * Selected run loaded successfully.
 */
export type RunLoadedMsg = {
  type: "RunLoaded";
  requestSeq: number;
  runId: string;
  payload: RunPayload;
  receivedAtMs: number;
};

/**
 * Selected run fetch failed.
 */
export type RunFailedMsg = {
  type: "RunFailed";
  requestSeq: number;
  runId: string;
  error: string;
  failedAtMs: number;
};

/**
 * Slow threshold timer fired for selected run.
 */
export type RunSlowThresholdReachedMsg = {
  type: "RunSlowThresholdReached";
  requestSeq: number;
  runId: string;
};

/**
 * User clicks manual refresh button.
 */
export type ManualRefreshClickedMsg = {
  type: "ManualRefreshClicked";
  nowMs: number;
};

/**
 * Polling tick fires.
 */
export type PollTickMsg = {
  type: "PollTick";
  nowMs: number;
};

/**
 * User clicks retry button for selected run.
 */
export type RetrySelectedRunClickedMsg = {
  type: "RetrySelectedRunClicked";
  nowMs: number;
};

/**
 * Union of all run control messages.
 */
export type RunControlMsg =
  | BootMsg
  | DebugModeDetectedMsg
  | RunsRequestedMsg
  | RunsLoadedMsg
  | RunsFailedMsg
  | RunSelectedMsg
  | LatestClickedMsg
  | SelectionClearedMsg
  | RunLoadedMsg
  | RunFailedMsg
  | RunSlowThresholdReachedMsg
  | ManualRefreshClickedMsg
  | PollTickMsg
  | RetrySelectedRunClickedMsg;

// ============================================================================
// Effects
// ============================================================================

/**
 * Effect: fetch runs list.
 */
export type FetchRunsEffect = {
  type: "fetchRuns";
  requestSeq: number;
  reason: "boot" | "manual" | "poll";
  includeExpensive: false;
};

/**
 * Effect: fetch individual run.
 */
export type FetchRunEffect = {
  type: "fetchRun";
  requestSeq: number;
  runId: string;
};

/**
 * Effect: schedule slow-run timer.
 */
export type ScheduleSlowRunTimerEffect = {
  type: "scheduleSlowRunTimer";
  requestSeq: number;
  runId: string;
  delayMs: number;
};

/**
 * Effect: cancel slow-run timer.
 */
export type CancelSlowRunTimerEffect = {
  type: "cancelSlowRunTimer";
  requestSeq: number;
};

/**
 * Effect: debug log.
 */
export type DebugLogEffect = {
  type: "debugLog";
  event: string;
  fields: Record<string, unknown>;
};

/**
 * Effect: abort stale run fetch.
 */
export type AbortRunFetchEffect = {
  type: "abortRunFetch";
  requestSeq: number;
};

/**
 * Union of all run control effects.
 */
export type RunControlEffect =
  | FetchRunsEffect
  | FetchRunEffect
  | ScheduleSlowRunTimerEffect
  | CancelSlowRunTimerEffect
  | DebugLogEffect
  | AbortRunFetchEffect;

// ============================================================================
// Config
// ============================================================================

/**
 * Configuration options for createInitialRunControlModel.
 */
export interface CreateInitialModelConfig {
  slowAfterMs?: number;
  debugEnabled?: boolean;
}
