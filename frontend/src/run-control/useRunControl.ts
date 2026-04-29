/**
 * useRunControl.ts — Elm-ish Run Control Plane interpreter hook.
 *
 * Phase 2: Owns the runtime boundary between the pure reducer and React.
 *
 * This hook is the ONLY place in the run-control subsystem where these are allowed:
 * - Date.now()
 * - fetch/API client calls
 * - setTimeout/clearTimeout
 * - console.info for debug
 * - window.location search param inspection
 *
 * All other code must remain pure.
 *
 * Elm-ish contract:
 * message -> pure update -> commit model -> interpret effects
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchRun, fetchRunsList } from "../api";
import type { RunPayload, RunsListPayload } from "../types";
import type {
  RunControlModel,
  RunControlMsg,
  RunControlEffect,
} from "./runControlTypes";
import {
  createInitialRunControlModel,
  updateRunControl,
  getSelectedRunId,
  getLatestRunId,
  getSelectedRunPayload,
  getSelectedRunStatus,
  getSelectedRunError,
  getRunOwnedPanelState,
  shouldShowLatestJump,
} from "./index";

// ============================================================================
// Debug gating
// ============================================================================

/**
 * Reads ?debugUi from window.location.search.
 * Safe to call in tests (handles window undefined).
 */
function isDebugUiEnabled(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  const params = new URLSearchParams(window.location.search);
  return params.has("debugUi");
}

// ============================================================================
// Error normalization
// ============================================================================

/**
 * Normalizes an error to a string message.
 * Never throws into React render.
 */
function normalizeError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "string") {
    return error;
  }
  return String(error ?? "Unknown error");
}

// ============================================================================
// Persistence
// ============================================================================

const SELECTED_RUN_STORAGE_KEY = "dashboard-selected-run-id";

/**
 * Reads the persisted selected run ID from localStorage.
 * Safe to call in the hook (runtime boundary).
 */
function readPersistedSelectedRunId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage.getItem(SELECTED_RUN_STORAGE_KEY);
  } catch {
    return null;
  }
}

/**
 * Persists the selected run ID to localStorage.
 * Called from the hook on user selection.
 */
function persistSelectedRunId(runId: string): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(SELECTED_RUN_STORAGE_KEY, runId);
  } catch {
    // Silently fail on storage errors
  }
}

/**
 * Clears the persisted selected run ID from localStorage.
 */
function clearPersistedSelectedRunId(): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.removeItem(SELECTED_RUN_STORAGE_KEY);
  } catch {
    // Silently fail on storage errors
  }
}

// ============================================================================
// Hook options
// ============================================================================

export interface UseRunControlOptions {
  /**
   * Milliseconds after which a run fetch is considered "slow".
   * Default: 10_000 (10 seconds).
   */
  slowAfterMs?: number;

  /**
   * Enable debug logging via console.info.
   * If omitted, derives from ?debugUi query parameter.
   */
  debugEnabled?: boolean;

  /**
   * Automatically call boot() on mount.
   * Default: false (Phase 3 can decide whether App.tsx calls boot on mount).
   */
  autoBoot?: boolean;

  /**
   * Initial selected run ID to use instead of reading from localStorage.
   * If omitted, reads from localStorage.
   */
  initialSelectedRunId?: string | null;
}

// ============================================================================
// Hook result
// ============================================================================

export interface UseRunControlResult {
  /** The current run control model (read-only). */
  model: RunControlModel;

  /** Dispatch a message to the reducer. */
  dispatch: (msg: RunControlMsg) => void;

  /** Boot the run control plane (fetches runs list). */
  boot: () => void;

  /** Select a run by ID. */
  selectRun: (runId: string) => void;

  /** Click the "Latest" button. */
  clickLatest: () => void;

  /** Manually refresh the runs list. */
  manualRefresh: () => void;

  /** Trigger a poll tick. */
  poll: () => void;

  /** Retry fetching the selected run. */
  retrySelectedRun: () => void;

  // Derived values (convenience selectors)
  /** The currently selected run ID. */
  selectedRunId: string | null;
  /** The latest run ID from the runs list. */
  latestRunId: string | null;
  /** The payload of the selected run. */
  selectedRun: RunPayload | null;
  /** The status of the selected run. */
  selectedRunStatus: "idle" | "loading" | "slow" | "loaded" | "failed";
  /** Error message if selected run fetch failed. */
  selectedRunError: string | null;
  /** Panel state for the selected run display. */
  runOwnedPanelState: "no-selection" | "loading" | "slow" | "failed" | "loaded";
  /** Whether to show the "jump to latest" prompt. */
  showLatestJump: boolean;
}

// ============================================================================
// Hook implementation
// ============================================================================

/**
 * useRunControl — React hook that owns the runtime boundary for run control.
 *
 * Responsibilities:
 * - Initialize RunControlModel
 * - Dispatch RunControlMsg
 * - Run updateRunControl
 * - Execute RunControlEffect values
 * - Dispatch result messages from async work
 * - Manage slow-run timers
 * - Optionally log debug events
 *
 * Elm-ish contract:
 * message -> pure update -> commit model -> interpret effects
 *
 * This implementation uses a queue pattern:
 * 1. dispatch() pushes effects into pendingEffectsRef during setModel functional update
 * 2. useEffect drains pendingEffectsRef and calls executeEffect after model changes
 * 3. This keeps the state updater pure and separates concerns
 */
export function useRunControl(
  options: UseRunControlOptions = {}
): UseRunControlResult {
  const { slowAfterMs = 10_000, debugEnabled, autoBoot = false } = options;

  // Derive debug flag: explicit option overrides ?debugUi detection
  const effectiveDebugEnabled = useMemo(() => {
    if (debugEnabled !== undefined) {
      return debugEnabled;
    }
    return isDebugUiEnabled();
  }, [debugEnabled]);

  // Determine initial selected run ID:
  // 1. Use explicitly provided initialSelectedRunId if given
  // 2. Otherwise read from localStorage
  const initialSelectedRunId = useMemo(() => {
    if (options.initialSelectedRunId !== undefined) {
      return options.initialSelectedRunId;
    }
    return readPersistedSelectedRunId();
  }, []);

  // Initialize model with config (reads from localStorage via hook)
  const [model, setModel] = useState<RunControlModel>(() =>
    createInitialRunControlModel({
      slowAfterMs,
      debugEnabled: effectiveDebugEnabled,
      initialSelectedRunId,
    })
  );

  // Ref to track current model for effect handlers (avoids stale closure)
  const modelRef = useRef<RunControlModel>(model);
  useEffect(() => {
    modelRef.current = model;
  }, [model]);

  // Ref to store slow-run timers by requestSeq
  const slowTimersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(
    new Map()
  );

  // Ref to queue pending effects (separated from state update)
  // This keeps the state updater pure: it only updates model, effects go to queue
  const pendingEffectsRef = useRef<RunControlEffect[]>([]);

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      slowTimersRef.current.forEach((timerId) => {
        clearTimeout(timerId);
      });
      slowTimersRef.current.clear();
    };
  }, []);

  // --------------------------------------------------------------------------
  // Effect executor
  // --------------------------------------------------------------------------

  /**
   * Executes a single effect and dispatches the resulting message.
   * Effects are executed OUTSIDE the state updater to maintain purity.
   */
  const executeEffect = useCallback(
    (effect: RunControlEffect) => {
      switch (effect.type) {
        case "fetchRuns": {
          const { requestSeq } = effect;
          // RunControlEffect carries includeExpensive=false;
          // current fetchRunsList API does not expose this option yet.
          fetchRunsList()
            .then((payload: RunsListPayload) => {
              dispatch({
                type: "RunsLoaded",
                requestSeq,
                payload,
                receivedAtMs: Date.now(),
              });
            })
            .catch((error: unknown) => {
              dispatch({
                type: "RunsFailed",
                requestSeq,
                error: normalizeError(error),
                failedAtMs: Date.now(),
              });
            });
          break;
        }

        case "fetchRun": {
          const { requestSeq, runId } = effect;
          fetchRun(runId)
            .then((payload: RunPayload) => {
              dispatch({
                type: "RunLoaded",
                requestSeq,
                runId,
                payload,
                receivedAtMs: Date.now(),
              });
            })
            .catch((error: unknown) => {
              dispatch({
                type: "RunFailed",
                requestSeq,
                runId,
                error: normalizeError(error),
                failedAtMs: Date.now(),
              });
            });
          break;
        }

        case "scheduleSlowRunTimer": {
          const { requestSeq, runId, delayMs } = effect;
          // Clear any existing timer for this requestSeq
          const existingTimer = slowTimersRef.current.get(requestSeq);
          if (existingTimer !== undefined) {
            clearTimeout(existingTimer);
          }
          const timerId = setTimeout(() => {
            dispatch({
              type: "RunSlowThresholdReached",
              requestSeq,
              runId,
            });
            // Clean up after firing
            slowTimersRef.current.delete(requestSeq);
          }, delayMs);
          slowTimersRef.current.set(requestSeq, timerId);
          break;
        }

        case "cancelSlowRunTimer": {
          const { requestSeq } = effect;
          const timerId = slowTimersRef.current.get(requestSeq);
          if (timerId !== undefined) {
            clearTimeout(timerId);
            slowTimersRef.current.delete(requestSeq);
          }
          break;
        }

        case "debugLog": {
          const { event, fields } = effect;
          // Only log if debug is enabled (either via option or model state)
          if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
            console.info("[run-control]", event, fields);
          }
          break;
        }

        case "abortRunFetch": {
          // Phase 5: Request cancellation/coalescing
          // Reserved for future implementation
          // Currently a no-op
          break;
        }
      }
    },
    [effectiveDebugEnabled] // dispatch is stable via ref
  );

  // --------------------------------------------------------------------------
  // Effect drainer
  // --------------------------------------------------------------------------

  /**
   * Drains pending effects after each model change.
   * This is the "interpret effects" step of Elm-ish architecture:
   * pure update -> commit model -> interpret effects
   */
  useEffect(() => {
    const effects = pendingEffectsRef.current.splice(0);
    for (const effect of effects) {
      executeEffect(effect);
    }
  }, [model, executeEffect]);

  // --------------------------------------------------------------------------
  // Dispatch
  // --------------------------------------------------------------------------

  /**
   * Stable dispatch that:
   * 1. Calls updateRunControl(currentModel, msg) - PURE
   * 2. Commits result.model to state
   * 3. Pushes effects to pendingEffectsRef for later interpretation
   *
   * This keeps the state updater pure and separates the Elm-ish contract:
   * message -> pure update -> commit model -> interpret effects
   */
  const dispatch = useCallback((msg: RunControlMsg) => {
    setModel((prevModel) => {
      const { model: newModel, effects } = updateRunControl(prevModel, msg);
      // Queue effects for interpretation AFTER state is committed
      pendingEffectsRef.current.push(...effects);
      return newModel;
    });
  }, []);

  // --------------------------------------------------------------------------
  // Public commands
  // --------------------------------------------------------------------------

  const boot = useCallback(() => {
    dispatch({ type: "Boot", nowMs: Date.now() });
  }, [dispatch]);

  const selectRun = useCallback(
    (runId: string) => {
      dispatch({ type: "RunSelected", runId, nowMs: Date.now() });
    },
    [dispatch]
  );

  const clickLatest = useCallback(() => {
    dispatch({ type: "LatestClicked", nowMs: Date.now() });
  }, [dispatch]);

  const manualRefresh = useCallback(() => {
    dispatch({ type: "ManualRefreshClicked", nowMs: Date.now() });
  }, [dispatch]);

  const poll = useCallback(() => {
    dispatch({ type: "PollTick", nowMs: Date.now() });
  }, [dispatch]);

  const retrySelectedRun = useCallback(() => {
    dispatch({ type: "RetrySelectedRunClicked", nowMs: Date.now() });
  }, [dispatch]);

  // --------------------------------------------------------------------------
  // Auto-boot
  // --------------------------------------------------------------------------

  useEffect(() => {
    if (autoBoot) {
      boot();
    }
  }, [autoBoot, boot]);

  // --------------------------------------------------------------------------
  // Persistence side-effect
  // --------------------------------------------------------------------------

  // Persist selected run ID to localStorage when it changes
  useEffect(() => {
    const currentSelectedRunId = model.selection.selectedRunId;
    if (currentSelectedRunId !== null) {
      persistSelectedRunId(currentSelectedRunId);
    } else {
      clearPersistedSelectedRunId();
    }
  }, [model.selection.selectedRunId]);

  // --------------------------------------------------------------------------
  // Derived values (selectors)
  // --------------------------------------------------------------------------

  const selectedRunId = useMemo(() => getSelectedRunId(model), [model]);
  const latestRunId = useMemo(() => getLatestRunId(model), [model]);
  const selectedRun = useMemo(() => getSelectedRunPayload(model), [model]);
  const selectedRunStatus = useMemo(
    () => getSelectedRunStatus(model),
    [model]
  );
  const selectedRunError = useMemo(
    () => getSelectedRunError(model),
    [model]
  );
  const runOwnedPanelState = useMemo(
    () => getRunOwnedPanelState(model),
    [model]
  );
  const showLatestJump = useMemo(() => shouldShowLatestJump(model), [model]);

  // --------------------------------------------------------------------------
  // Return
  // --------------------------------------------------------------------------

  return {
    model,
    dispatch,
    boot,
    selectRun,
    clickLatest,
    manualRefresh,
    poll,
    retrySelectedRun,
    selectedRunId,
    latestRunId,
    selectedRun,
    selectedRunStatus,
    selectedRunError,
    runOwnedPanelState,
    showLatestJump,
  };
}
