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
// Hook Instance Tracking
// ============================================================================

/**
 * Generates a stable hook instance ID for debugging.
 * This helps detect if multiple useRunControl instances are active.
 */
let hookInstanceCounter = 0;
const getHookInstanceId = (): number => {
  return ++hookInstanceCounter;
};

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

  /** Retry fetching the selected run (alias for non-error refresh paths). */
  retrySelectedRun: () => void;

  /**
   * Refresh the selected run (alias for retrySelectedRun).
   * Named for explicit operator-triggered refresh without error semantics.
   */
  refreshSelectedRun: () => void;

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

  // Debug info
  /** Unique instance ID for this hook (for debugging duplicate controller detection). */
  instanceId: number;
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

  // Generate unique instance ID for debugging
  const instanceId = useMemo(() => getHookInstanceId(), []);

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
  // Phase 5: Guard against StrictMode double-effect execution
  // When drainer is running, skip re-entry. This prevents the same queued effects
  // from being executed multiple times if React StrictMode fires the useEffect twice.
  const isDrainingRef = useRef<boolean>(false);

  // Refs for /api/run request management (Phase 5: AbortController + deduplication)
  // AbortController for cancelling stale in-flight requests
  const abortControllerRef = useRef<AbortController | null>(null);
  // Track in-flight runId and requestSeq for deduplication
  const inFlightRunIdRef = useRef<string | null>(null);
  const inFlightRequestSeqRef = useRef<number | null>(null);
  // Map from clientRequestId to abort controller for correlation
  const clientRequestIdToAbortRef = useRef<Map<string, AbortController>>(new Map());

  // Lifecycle telemetry: log hook initialization
  useEffect(() => {
    if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
      console.info("[run-control]", "hook:initialized", {
        instanceId,
        initialSelectedRunId,
        hasPersistedSelection: initialSelectedRunId !== null,
        timestamp: new Date().toISOString(),
      });
    }
  }, [instanceId, initialSelectedRunId, effectiveDebugEnabled]);

  // Cleanup timers and abort controllers on unmount
  useEffect(() => {
    return () => {
      slowTimersRef.current.forEach((timerId) => {
        clearTimeout(timerId);
      });
      slowTimersRef.current.clear();
      // Abort any in-flight request on unmount
      if (abortControllerRef.current !== null) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      inFlightRunIdRef.current = null;
      inFlightRequestSeqRef.current = null;
      clientRequestIdToAbortRef.current.clear();

      if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
        console.info("[run-control]", "hook:unmounting", {
          instanceId,
          timestamp: new Date().toISOString(),
        });
      }
    };
  }, [instanceId, effectiveDebugEnabled]);

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
          // NOTE: /api/runs is also fetched by useRunSelection for Recent Runs list UI.
          // This is intentional during the migration:
          // - RunControl owns latest/selection/run-detail causality.
          // - useRunSelection owns visible list filtering/pagination.
          // Future consolidation can merge these once the UI list state is migrated.
          if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
            console.info("[run-control]", "effect:fetchRuns:emitted", {
              instanceId,
              requestSeq,
              reason: effect.reason,
              timestamp: new Date().toISOString(),
            });
          }
          fetchRunsList()
            .then((payload: RunsListPayload) => {
              if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
                console.info("[run-control]", "fetchRuns:response-received", {
                  instanceId,
                  requestSeq,
                  runsCount: payload.runs.length,
                  latestRunId: payload.runs[0]?.runId ?? null,
                  timestamp: new Date().toISOString(),
                });
              }
              dispatch({
                type: "RunsLoaded",
                requestSeq,
                payload,
                receivedAtMs: Date.now(),
              });
            })
            .catch((error: unknown) => {
              if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
                console.info("[run-control]", "fetchRuns:failed", {
                  instanceId,
                  requestSeq,
                  error: normalizeError(error),
                  timestamp: new Date().toISOString(),
                });
              }
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

          // Log effect emission for lifecycle tracking
          if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
            console.info("[run-control]", "effect:fetchRun:emitted", {
              instanceId,
              requestSeq,
              runId,
              selectedRunId: modelRef.current.selection.selectedRunId,
              selectedReason: modelRef.current.selection.selectedReason,
              timestamp: new Date().toISOString(),
            });
          }

          // Phase 5: Deduplication - skip only if BOTH runId AND requestSeq match
          // This ensures a newer requestSeq for the same run is never dropped
          if (
            inFlightRunIdRef.current === runId &&
            inFlightRequestSeqRef.current === requestSeq
          ) {
            if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
              console.info("[run-control]", "fetchRun:duplicate-skipped", {
                instanceId,
                requestSeq,
                runId,
                inFlightRequestSeq: inFlightRequestSeqRef.current,
              });
            }
            break;
          }

          // Phase 5: Abort any previous in-flight request
          // (regardless of whether it's same runId - newer requestSeq takes precedence)
          if (abortControllerRef.current !== null) {
            abortControllerRef.current.abort();
            if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
              console.info("[run-control]", "fetchRun:aborted-previous", {
                instanceId,
                requestSeq,
                runId,
                previousInFlightRunId: inFlightRunIdRef.current,
                previousInFlightRequestSeq: inFlightRequestSeqRef.current,
              });
            }
          }

          // Create new AbortController for this request
          const abortController = new AbortController();
          abortControllerRef.current = abortController;
          inFlightRunIdRef.current = runId;
          inFlightRequestSeqRef.current = requestSeq;

          // Generate clientRequestId for correlation
          const clientRequestId = `rc-${requestSeq}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
          clientRequestIdToAbortRef.current.set(clientRequestId, abortController);

          if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
            console.info("[run-control]", "fetchRun:started", {
              instanceId,
              requestSeq,
              runId,
              clientRequestId,
              timestamp: new Date().toISOString(),
            });
          }

          fetchRun(runId, { clientRequestId, signal: abortController.signal })
            .then((payload: RunPayload) => {
              // Phase 5: Verify this response is still the current request
              // Guard cleanup by request identity - only clear if still current
              const isStale =
                inFlightRequestSeqRef.current !== requestSeq ||
                inFlightRunIdRef.current !== runId;

              if (isStale) {
                if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
                  console.info("[run-control]", "fetchRun:stale-response-ignored", {
                    instanceId,
                    requestSeq,
                    runId,
                    returnedRunId: payload.runId,
                    currentRequestSeq: inFlightRequestSeqRef.current,
                    currentRunId: inFlightRunIdRef.current,
                  });
                }
                // Don't clear refs - they belong to the current request
                clientRequestIdToAbortRef.current.delete(clientRequestId);
                return;
              }

              // Log acceptance with full context for acceptance verification
              if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
                console.info("[run-control]", "fetchRun:accepted", {
                  instanceId,
                  requestSeq,
                  runId,
                  clientRequestId,
                  returnedRunId: payload.runId,
                  acceptedAt: new Date().toISOString(),
                  currentModelStatus: modelRef.current.selectedRun.status,
                  currentSelectedRunId: modelRef.current.selection.selectedRunId,
                });
              }

              dispatch({
                type: "RunLoaded",
                requestSeq,
                runId,
                payload,
                receivedAtMs: Date.now(),
              });

              // Log model state after RunLoaded
              if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
                console.info("[run-control]", "model:RunLoaded-processed", {
                  instanceId,
                  requestSeq,
                  runId,
                  newStatus: modelRef.current.selectedRun.status,
                  payloadRunId: payload.runId,
                  timestamp: new Date().toISOString(),
                });
              }

              // Clean up - only if still the current request
              if (
                inFlightRequestSeqRef.current === requestSeq &&
                inFlightRunIdRef.current === runId
              ) {
                inFlightRunIdRef.current = null;
                inFlightRequestSeqRef.current = null;
                abortControllerRef.current = null;
              }
              clientRequestIdToAbortRef.current.delete(clientRequestId);
            })
            .catch((error: unknown) => {
              // Broad AbortError detection: DOMException AbortError or Error with name === "AbortError"
              const isAbortError =
                (error instanceof DOMException && error.name === "AbortError") ||
                (error instanceof Error && error.name === "AbortError");

              if (isAbortError) {
                // Guard cleanup: only clear refs if this request is still the current one
                // This prevents old aborted requests from clearing the active controller for newer requests
                if (
                  inFlightRequestSeqRef.current === requestSeq &&
                  inFlightRunIdRef.current === runId
                ) {
                  if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
                    console.info("[run-control]", "fetchRun:aborted-current", {
                      instanceId,
                      requestSeq,
                      runId,
                      clientRequestId,
                    });
                  }
                  // This was the current request - clean up
                  inFlightRunIdRef.current = null;
                  inFlightRequestSeqRef.current = null;
                  abortControllerRef.current = null;
                } else {
                  if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
                    console.info("[run-control]", "fetchRun:aborted-stale", {
                      instanceId,
                      requestSeq,
                      runId,
                      clientRequestId,
                      currentRequestSeq: inFlightRequestSeqRef.current,
                      currentRunId: inFlightRunIdRef.current,
                    });
                  }
                  // This was a stale request - don't clear current request's refs
                }
                clientRequestIdToAbortRef.current.delete(clientRequestId);
                return;
              }

              if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
                console.info("[run-control]", "fetchRun:failed", {
                  instanceId,
                  requestSeq,
                  runId,
                  clientRequestId,
                  error: normalizeError(error),
                });
              }

              // Guard cleanup: only clear if this is still the current request
              if (
                inFlightRequestSeqRef.current === requestSeq &&
                inFlightRunIdRef.current === runId
              ) {
                dispatch({
                  type: "RunFailed",
                  requestSeq,
                  runId,
                  error: normalizeError(error),
                  failedAtMs: Date.now(),
                });
                inFlightRunIdRef.current = null;
                inFlightRequestSeqRef.current = null;
                abortControllerRef.current = null;
              }
              clientRequestIdToAbortRef.current.delete(clientRequestId);
            });
          break;
        }

        case "scheduleSlowRunTimer": {
          const { requestSeq, runId, delayMs } = effect;
          if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
            console.info("[run-control]", "effect:scheduleSlowRunTimer:emitted", {
              instanceId,
              requestSeq,
              runId,
              delayMs,
              timestamp: new Date().toISOString(),
            });
          }
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
          if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
            console.info("[run-control]", "effect:cancelSlowRunTimer:emitted", {
              instanceId,
              requestSeq,
              timestamp: new Date().toISOString(),
            });
          }
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
            console.info("[run-control]", event, { instanceId, ...fields });
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
    [effectiveDebugEnabled, instanceId] // dispatch is stable via ref
  );

  // --------------------------------------------------------------------------
  // Effect drainer
  // --------------------------------------------------------------------------

  /**
   * Drains pending effects after each model change.
   * This is the "interpret effects" step of Elm-ish architecture:
   * pure update -> commit model -> interpret effects
   * 
   * Phase 5: Uses isDrainingRef to guard against StrictMode double-effect execution.
   * This prevents the same queued effects from being executed multiple times.
   */
  useEffect(() => {
    // Guard against re-entry (e.g., StrictMode double-effect)
    if (isDrainingRef.current) {
      return;
    }
    isDrainingRef.current = true;
    
    try {
      const effects = pendingEffectsRef.current.splice(0);
      for (const effect of effects) {
        executeEffect(effect);
      }
    } finally {
      isDrainingRef.current = false;
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

      // Log dispatch for lifecycle tracking
      if (modelRef.current.debug.enabled) {
        console.info("[run-control]", "dispatch", {
          instanceId,
          msgType: msg.type,
          modelDelta: {
            runsStatus: `${prevModel.runs.status} -> ${newModel.runs.status}`,
            selectedRunStatus: `${prevModel.selectedRun.status} -> ${newModel.selectedRun.status}`,
            selectedRunId: `${prevModel.selection.selectedRunId} -> ${newModel.selection.selectedRunId}`,
          },
          effectsCount: effects.length,
          effectTypes: effects.map(e => e.type),
          timestamp: new Date().toISOString(),
        });
      }

      return newModel;
    });
  }, [instanceId]);

  // --------------------------------------------------------------------------
  // Public commands
  // --------------------------------------------------------------------------

  const boot = useCallback(() => {
    // Phase 5: Idempotency guard - protect against React StrictMode/dev double effects
    // and any app-level duplicate boot calls. The reducer also guards this, but we
    // guard here to avoid the dispatch entirely when already in progress.
    const currentStatus = modelRef.current.runs.status;
    if (currentStatus === "loading" || currentStatus === "loaded") {
      if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
        console.info("[run-control]", "command:boot:ignored", {
          instanceId,
          runsStatus: currentStatus,
          timestamp: new Date().toISOString(),
        });
      }
      return;
    }

    if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
      console.info("[run-control]", "command:boot", {
        instanceId,
        currentSelectedRunId: modelRef.current.selection.selectedRunId,
        currentLatestRunId: modelRef.current.selection.latestRunId,
        timestamp: new Date().toISOString(),
      });
    }
    dispatch({ type: "Boot", nowMs: Date.now() });
  }, [dispatch, instanceId, effectiveDebugEnabled]);

  const selectRun = useCallback(
    (runId: string) => {
      if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
        console.info("[run-control]", "command:selectRun", {
          instanceId,
          runId,
          previousSelectedRunId: modelRef.current.selection.selectedRunId,
          timestamp: new Date().toISOString(),
        });
      }
      dispatch({ type: "RunSelected", runId, nowMs: Date.now() });
    },
    [dispatch, instanceId, effectiveDebugEnabled]
  );

  const clickLatest = useCallback(() => {
    if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
      console.info("[run-control]", "command:clickLatest", {
        instanceId,
        currentLatestRunId: modelRef.current.selection.latestRunId,
        previousSelectedRunId: modelRef.current.selection.selectedRunId,
        timestamp: new Date().toISOString(),
      });
    }
    dispatch({ type: "LatestClicked", nowMs: Date.now() });
  }, [dispatch, instanceId, effectiveDebugEnabled]);

  const manualRefresh = useCallback(() => {
    if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
      console.info("[run-control]", "command:manualRefresh", {
        instanceId,
        timestamp: new Date().toISOString(),
      });
    }
    dispatch({ type: "ManualRefreshClicked", nowMs: Date.now() });
  }, [dispatch, instanceId, effectiveDebugEnabled]);

  const poll = useCallback(() => {
    if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
      console.info("[run-control]", "command:poll", {
        instanceId,
        currentSelectedRunId: modelRef.current.selection.selectedRunId,
        currentSelectedRunStatus: modelRef.current.selectedRun.status,
        timestamp: new Date().toISOString(),
      });
    }
    dispatch({ type: "PollTick", nowMs: Date.now() });
  }, [dispatch, instanceId, effectiveDebugEnabled]);

  const retrySelectedRun = useCallback(() => {
    if (effectiveDebugEnabled || modelRef.current.debug.enabled) {
      console.info("[run-control]", "command:retrySelectedRun", {
        instanceId,
        currentSelectedRunId: modelRef.current.selection.selectedRunId,
        requestedRunId: modelRef.current.selectedRun.requestedRunId,
        currentStatus: modelRef.current.selectedRun.status,
        timestamp: new Date().toISOString(),
      });
    }
    dispatch({ type: "RetrySelectedRunClicked", nowMs: Date.now() });
  }, [dispatch, instanceId, effectiveDebugEnabled]);

  // Alias: refreshSelectedRun for non-error refresh paths
  const refreshSelectedRun = retrySelectedRun;

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
    refreshSelectedRun,
    selectedRunId,
    latestRunId,
    selectedRun,
    selectedRunStatus,
    selectedRunError,
    runOwnedPanelState,
    showLatestJump,
    instanceId,
  };
}
