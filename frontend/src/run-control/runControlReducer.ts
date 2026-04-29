/**
 * runControlReducer.ts — Pure Elm-ish Run Control Plane reducer.
 *
 * Phase 1: Pure reducer with no side effects.
 *
 * Design constraints:
 * - No Date.now() inside reducer or selectors.
 * - No fetch, setTimeout, setInterval, window access, or console logging.
 * - All time enters via message fields: nowMs, receivedAtMs, failedAtMs.
 * - Effects are data only.
 * 
 * Persistence note: localStorage access is handled in useRunControl hook,
 * not in this reducer. The reducer receives initialSelectedRunId via config.
 */

import type { RunPayload } from "../types";
import type {
  RunControlModel,
  RunControlMsg,
  RunControlEffect,
  CreateInitialModelConfig,
} from "./runControlTypes";

// ============================================================================
// Initializer
// ============================================================================

/**
 * Creates the initial run control model.
 *
 * @param config - Optional configuration overrides.
 * @returns The initial model with sensible defaults.
 */
export function createInitialRunControlModel(
  config?: CreateInitialModelConfig
): RunControlModel {
  const slowAfterMs = config?.slowAfterMs ?? 10_000;
  const debugEnabled = config?.debugEnabled ?? false;

  // Phase 3: Use initialSelectedRunId from config (passed by hook after reading localStorage)
  const initialSelectedRunId = config?.initialSelectedRunId ?? null;

  return {
    nextRequestSeq: 1,
    runs: {
      status: "idle",
      requestSeq: null,
      items: [],
      error: null,
      lastLoadedAtMs: null,
      lastRefreshReason: null,
    },
    selection: {
      // Initialize with persisted selection if available
      selectedRunId: initialSelectedRunId,
      latestRunId: null,
      // selectedReason will be set properly when runs are loaded
      selectedReason: initialSelectedRunId ? "boot" : null,
    },
    selectedRun: {
      status: "idle",
      requestSeq: null,
      requestedRunId: null,
      payload: null,
      error: null,
      startedAtMs: null,
      lastLoadedRunId: null,
      lastLoadedAtMs: null,
      lastErrorAtMs: null,
      slowAfterMs,
    },
    freshness: {
      hasNewerLatest: false,
      latestKnownAtMs: null,
    },
    debug: {
      enabled: debugEnabled,
    },
  };
}

// ============================================================================
// Helpers
// ============================================================================

/**
 * Allocates the next request sequence number and returns the new model.
 */
function allocateRequestSeq(
  model: RunControlModel
): { model: RunControlModel; requestSeq: number } {
  const requestSeq = model.nextRequestSeq;
  const newModel: RunControlModel = {
    ...model,
    nextRequestSeq: model.nextRequestSeq + 1,
  };
  return { model: newModel, requestSeq };
}

/**
 * Emits the fetchRuns effect.
 */
function emitFetchRuns(
  effects: RunControlEffect[],
  requestSeq: number,
  reason: "boot" | "manual" | "poll"
): RunControlEffect[] {
  return [
    ...effects,
    {
      type: "fetchRuns",
      requestSeq,
      reason,
      includeExpensive: false,
    } as const,
  ];
}

/**
 * Emits the fetchRun effect.
 */
function emitFetchRun(
  effects: RunControlEffect[],
  requestSeq: number,
  runId: string
): RunControlEffect[] {
  return [
    ...effects,
    {
      type: "fetchRun",
      requestSeq,
      runId,
    } as const,
  ];
}

/**
 * Emits the scheduleSlowRunTimer effect.
 */
function emitScheduleSlowRunTimer(
  effects: RunControlEffect[],
  requestSeq: number,
  runId: string,
  delayMs: number
): RunControlEffect[] {
  return [
    ...effects,
    {
      type: "scheduleSlowRunTimer",
      requestSeq,
      runId,
      delayMs,
    } as const,
  ];
}

/**
 * Emits the cancelSlowRunTimer effect.
 */
function emitCancelSlowRunTimer(
  effects: RunControlEffect[],
  requestSeq: number
): RunControlEffect[] {
  return [
    ...effects,
    {
      type: "cancelSlowRunTimer",
      requestSeq,
    } as const,
  ];
}

/**
 * Emits the debugLog effect.
 */
function emitDebugLog(
  effects: RunControlEffect[],
  event: string,
  fields: Record<string, unknown>
): RunControlEffect[] {
  return [
    ...effects,
    {
      type: "debugLog",
      event,
      fields,
    } as const,
  ];
}

// ============================================================================
// Main Reducer
// ============================================================================

/**
 * Updates the run control model based on the given message.
 *
 * @param model - The current model.
 * @param msg - The message to process.
 * @returns The updated model and list of effects.
 */
export function updateRunControl(
  model: RunControlModel,
  msg: RunControlMsg
): { model: RunControlModel; effects: RunControlEffect[] } {
  switch (msg.type) {
    // -----------------------------------------------------------------------
    // Boot
    // -----------------------------------------------------------------------
    case "Boot": {
      const { model: m1, requestSeq } = allocateRequestSeq(model);
      const newModel: RunControlModel = {
        ...m1,
        runs: {
          ...m1.runs,
          status: "loading",
          requestSeq,
          lastRefreshReason: "boot",
        },
      };
      const effects = emitFetchRuns([], requestSeq, "boot");
      return { model: newModel, effects };
    }

    // -----------------------------------------------------------------------
    // Debug mode
    // -----------------------------------------------------------------------
    case "DebugModeDetected": {
      const newModel: RunControlModel = {
        ...model,
        debug: {
          ...model.debug,
          enabled: msg.enabled,
        },
      };
      return { model: newModel, effects: [] };
    }

    // -----------------------------------------------------------------------
    // RunsRequested
    // -----------------------------------------------------------------------
    case "RunsRequested": {
      const { model: m1, requestSeq } = allocateRequestSeq(model);
      const newModel: RunControlModel = {
        ...m1,
        runs: {
          ...m1.runs,
          status: "loading",
          requestSeq,
          lastRefreshReason: msg.reason,
          error: null,
        },
      };
      const effects = emitFetchRuns([], requestSeq, msg.reason);
      return { model: newModel, effects };
    }

    // -----------------------------------------------------------------------
    // RunsLoaded
    // -----------------------------------------------------------------------
    case "RunsLoaded": {
      // Ignore stale requestSeq
      if (model.runs.requestSeq !== msg.requestSeq) {
        const effects = model.debug.enabled
          ? emitDebugLog([], "RunsLoaded:stale", {
              expectedSeq: model.runs.requestSeq,
              gotSeq: msg.requestSeq,
            })
          : [];
        return { model, effects };
      }

      const latestRunId = msg.payload.runs[0]?.runId ?? null;
      const latestExists = latestRunId !== null;
      const { selectedRunId } = model.selection;

      // Case 1: No selection yet and latest exists -> select latest
      if (!selectedRunId && latestExists) {
        const { model: m1, requestSeq } = allocateRequestSeq(model);
        const newSelectedRun: RunControlModel["selectedRun"] = {
          ...model.selectedRun,
          status: "loading",
          requestSeq,
          requestedRunId: latestRunId,
          startedAtMs: msg.receivedAtMs,
          error: null,
          payload: null,
        };
        const newModel: RunControlModel = {
          ...m1,
          runs: {
            ...m1.runs,
            status: "loaded",
            items: msg.payload.runs,
            error: null,
            lastLoadedAtMs: msg.receivedAtMs,
          },
          selection: {
            ...model.selection,
            selectedRunId: latestRunId,
            latestRunId,
            selectedReason: "boot",
          },
          selectedRun: newSelectedRun,
          freshness: {
            ...model.freshness,
            hasNewerLatest: false,
            latestKnownAtMs: msg.receivedAtMs,
          },
        };
        let effects: RunControlEffect[] = [];
        effects = emitFetchRun(effects, requestSeq, latestRunId);
        effects = emitScheduleSlowRunTimer(
          effects,
          requestSeq,
          latestRunId,
          model.selectedRun.slowAfterMs
        );
        return { model: newModel, effects };
      }

      // Case 2: Selection exists and still in list -> preserve AND fetch detail
      const selectedStillInList =
        selectedRunId !== null &&
        msg.payload.runs.some((r) => r.runId === selectedRunId);

      let hasNewerLatest = false;
      if (selectedRunId && latestExists && selectedRunId !== latestRunId) {
        hasNewerLatest = true;
      }

      if (selectedStillInList) {
        const { model: m1, requestSeq } = allocateRequestSeq(model);
        const newSelectedRun: RunControlModel["selectedRun"] = {
          ...model.selectedRun,
          status: "loading",
          requestSeq,
          requestedRunId: selectedRunId,
          startedAtMs: msg.receivedAtMs,
          error: null,
          payload: null,
        };
        const newModel: RunControlModel = {
          ...m1,
          runs: {
            ...m1.runs,
            status: "loaded",
            items: msg.payload.runs,
            error: null,
            lastLoadedAtMs: msg.receivedAtMs,
          },
          selection: {
            ...model.selection,
            latestRunId,
          },
          selectedRun: newSelectedRun,
          freshness: {
            ...model.freshness,
            hasNewerLatest,
            latestKnownAtMs: msg.receivedAtMs,
          },
        };
        let effects: RunControlEffect[] = [];
        effects = emitFetchRun(effects, requestSeq, selectedRunId);
        effects = emitScheduleSlowRunTimer(
          effects,
          requestSeq,
          selectedRunId,
          model.selectedRun.slowAfterMs
        );
        return { model: newModel, effects };
      }

      // Case 3: Selection exists but no longer in list and latest exists -> fallback
      if (selectedRunId && latestExists && !selectedStillInList) {
        const { model: m1, requestSeq } = allocateRequestSeq(model);
        const newSelectedRun: RunControlModel["selectedRun"] = {
          ...model.selectedRun,
          status: "loading",
          requestSeq,
          requestedRunId: latestRunId,
          startedAtMs: msg.receivedAtMs,
          error: null,
          payload: null,
        };
        const newModel: RunControlModel = {
          ...m1,
          runs: {
            ...m1.runs,
            status: "loaded",
            items: msg.payload.runs,
            error: null,
            lastLoadedAtMs: msg.receivedAtMs,
          },
          selection: {
            ...model.selection,
            selectedRunId: latestRunId,
            latestRunId,
            selectedReason: "fallback-to-latest",
          },
          selectedRun: newSelectedRun,
          freshness: {
            ...model.freshness,
            hasNewerLatest: false,
            latestKnownAtMs: msg.receivedAtMs,
          },
        };
        let effects: RunControlEffect[] = [];
        effects = emitFetchRun(effects, requestSeq, latestRunId);
        effects = emitScheduleSlowRunTimer(
          effects,
          requestSeq,
          latestRunId,
          model.selectedRun.slowAfterMs
        );
        return { model: newModel, effects };
      }

      // Case 4: Empty list, no selection
      const newModel: RunControlModel = {
        ...model,
        runs: {
          ...model.runs,
          status: "loaded",
          items: msg.payload.runs,
          error: null,
          lastLoadedAtMs: msg.receivedAtMs,
        },
        selection: {
          ...model.selection,
          latestRunId,
        },
        freshness: {
          ...model.freshness,
          hasNewerLatest: false,
          latestKnownAtMs: msg.receivedAtMs,
        },
      };
      return { model: newModel, effects: [] };
    }

    // -----------------------------------------------------------------------
    // RunsFailed
    // -----------------------------------------------------------------------
    case "RunsFailed": {
      // Ignore stale requestSeq
      if (model.runs.requestSeq !== msg.requestSeq) {
        const effects = model.debug.enabled
          ? emitDebugLog([], "RunsFailed:stale", {
              expectedSeq: model.runs.requestSeq,
              gotSeq: msg.requestSeq,
            })
          : [];
        return { model, effects };
      }

      const newModel: RunControlModel = {
        ...model,
        runs: {
          ...model.runs,
          status: "failed",
          error: msg.error,
        },
      };
      return { model: newModel, effects: [] };
    }

    // -----------------------------------------------------------------------
    // RunSelected
    // -----------------------------------------------------------------------
    case "RunSelected": {
      const { model: m1, requestSeq } = allocateRequestSeq(model);
      const runId = msg.runId;

      // Preserve payload if it belongs to the same run; otherwise null it
      const existingPayload =
        model.selectedRun.payload?.runId === runId
          ? model.selectedRun.payload
          : null;

      // hasNewerLatest is true when latestRunId exists and differs from selected run
      const hasNewerLatest =
        model.selection.latestRunId !== null &&
        model.selection.latestRunId !== runId;

      const newModel: RunControlModel = {
        ...m1,
        selection: {
          ...model.selection,
          selectedRunId: runId,
          selectedReason: "user",
        },
        selectedRun: {
          ...model.selectedRun,
          status: "loading",
          requestSeq,
          requestedRunId: runId,
          startedAtMs: msg.nowMs,
          error: null,
          payload: existingPayload,
        },
        freshness: {
          ...model.freshness,
          hasNewerLatest,
        },
      };

      let effects: RunControlEffect[] = [];
      effects = emitFetchRun(effects, requestSeq, runId);
      effects = emitScheduleSlowRunTimer(
        effects,
        requestSeq,
        runId,
        model.selectedRun.slowAfterMs
      );
      return { model: newModel, effects };
    }

    // -----------------------------------------------------------------------
    // LatestClicked
    // -----------------------------------------------------------------------
    case "LatestClicked": {
      const latestRunId = model.selection.latestRunId;

      // No-op if no latest run
      if (latestRunId === null) {
        return { model, effects: [] };
      }

      const { model: m1, requestSeq } = allocateRequestSeq(model);

      // Preserve same-run payload to prevent flicker
      const existingPayload =
        model.selectedRun.payload?.runId === latestRunId
          ? model.selectedRun.payload
          : null;

      const newModel: RunControlModel = {
        ...m1,
        selection: {
          ...model.selection,
          selectedRunId: latestRunId,
          selectedReason: "latest-click",
        },
        selectedRun: {
          ...model.selectedRun,
          status: "loading",
          requestSeq,
          requestedRunId: latestRunId,
          startedAtMs: msg.nowMs,
          error: null,
          payload: existingPayload,
        },
        freshness: {
          ...model.freshness,
          hasNewerLatest: false,
        },
      };

      let effects: RunControlEffect[] = [];
      effects = emitFetchRun(effects, requestSeq, latestRunId);
      effects = emitScheduleSlowRunTimer(
        effects,
        requestSeq,
        latestRunId,
        model.selectedRun.slowAfterMs
      );
      return { model: newModel, effects };
    }

    // -----------------------------------------------------------------------
    // SelectionCleared
    // -----------------------------------------------------------------------
    case "SelectionCleared": {
      const newModel: RunControlModel = {
        ...model,
        selection: {
          ...model.selection,
          selectedRunId: null,
          selectedReason: null,
        },
        selectedRun: {
          ...model.selectedRun,
          status: "idle",
          requestSeq: null,
          requestedRunId: null,
          payload: null,
          error: null,
          startedAtMs: null,
          lastLoadedRunId: null,
          lastLoadedAtMs: null,
          lastErrorAtMs: null,
        },
        freshness: {
          ...model.freshness,
          hasNewerLatest: false,
        },
      };
      return { model: newModel, effects: [] };
    }

    // -----------------------------------------------------------------------
    // RunLoaded
    // -----------------------------------------------------------------------
    case "RunLoaded": {
      const { requestSeq, requestedRunId } = model.selectedRun;

      // Accept only if requestSeq and runId match
      if (requestSeq !== msg.requestSeq || requestedRunId !== msg.runId) {
        const effects = model.debug.enabled
          ? emitDebugLog([], "RunLoaded:stale", {
              expectedSeq: requestSeq,
              gotSeq: msg.requestSeq,
              expectedRunId: requestedRunId,
              gotRunId: msg.runId,
            })
          : [];
        return { model, effects };
      }

      const newModel: RunControlModel = {
        ...model,
        selectedRun: {
          ...model.selectedRun,
          status: "loaded",
          payload: msg.payload,
          error: null,
          lastLoadedRunId: msg.runId,
          lastLoadedAtMs: msg.receivedAtMs,
        },
      };

      const effects = emitCancelSlowRunTimer([], msg.requestSeq);
      return { model: newModel, effects };
    }

    // -----------------------------------------------------------------------
    // RunFailed
    // -----------------------------------------------------------------------
    case "RunFailed": {
      const { requestSeq, requestedRunId } = model.selectedRun;

      // Accept only if requestSeq and runId match
      if (requestSeq !== msg.requestSeq || requestedRunId !== msg.runId) {
        const effects = model.debug.enabled
          ? emitDebugLog([], "RunFailed:stale", {
              expectedSeq: requestSeq,
              gotSeq: msg.requestSeq,
              expectedRunId: requestedRunId,
              gotRunId: msg.runId,
            })
          : [];
        return { model, effects };
      }

      // Preserve payload only if runId matches
      const payload =
        model.selectedRun.payload?.runId === msg.runId
          ? model.selectedRun.payload
          : null;

      const newModel: RunControlModel = {
        ...model,
        selectedRun: {
          ...model.selectedRun,
          status: "failed",
          error: msg.error,
          lastErrorAtMs: msg.failedAtMs,
          payload,
        },
      };

      const effects = emitCancelSlowRunTimer([], msg.requestSeq);
      return { model: newModel, effects };
    }

    // -----------------------------------------------------------------------
    // RunSlowThresholdReached
    // -----------------------------------------------------------------------
    case "RunSlowThresholdReached": {
      const { requestSeq, requestedRunId, status } = model.selectedRun;

      // Accept only if requestSeq and runId match and status is "loading"
      if (
        requestSeq !== msg.requestSeq ||
        requestedRunId !== msg.runId ||
        status !== "loading"
      ) {
        return { model, effects: [] };
      }

      const newModel: RunControlModel = {
        ...model,
        selectedRun: {
          ...model.selectedRun,
          status: "slow",
        },
      };
      return { model: newModel, effects: [] };
    }

    // -----------------------------------------------------------------------
    // ManualRefreshClicked
    // -----------------------------------------------------------------------
    case "ManualRefreshClicked": {
      const { model: m1, requestSeq } = allocateRequestSeq(model);
      const newModel: RunControlModel = {
        ...m1,
        runs: {
          ...m1.runs,
          status: "loading",
          requestSeq,
          lastRefreshReason: "manual",
          error: null,
        },
      };
      const effects = emitFetchRuns([], requestSeq, "manual");
      return { model: newModel, effects };
    }

    // -----------------------------------------------------------------------
    // PollTick
    // -----------------------------------------------------------------------
    case "PollTick": {
      const { model: m1, requestSeq } = allocateRequestSeq(model);
      const newModel: RunControlModel = {
        ...m1,
        runs: {
          ...m1.runs,
          status: "loading",
          requestSeq,
          lastRefreshReason: "poll",
          error: null,
        },
      };
      const effects = emitFetchRuns([], requestSeq, "poll");
      return { model: newModel, effects };
    }

    // -----------------------------------------------------------------------
    // RetrySelectedRunClicked
    // -----------------------------------------------------------------------
    case "RetrySelectedRunClicked": {
      const runId = model.selectedRun.requestedRunId ?? model.selection.selectedRunId;

      // No-op if no run ID
      if (runId === null) {
        return { model, effects: [] };
      }

      const { model: m1, requestSeq } = allocateRequestSeq(model);
      const newModel: RunControlModel = {
        ...m1,
        selectedRun: {
          ...model.selectedRun,
          status: "loading",
          requestSeq,
          requestedRunId: runId,
          startedAtMs: msg.nowMs,
          error: null,
          // Preserve same-run payload
          payload:
            model.selectedRun.payload?.runId === runId
              ? model.selectedRun.payload
              : null,
        },
      };

      let effects: RunControlEffect[] = [];
      effects = emitFetchRun(effects, requestSeq, runId);
      effects = emitScheduleSlowRunTimer(
        effects,
        requestSeq,
        runId,
        model.selectedRun.slowAfterMs
      );
      return { model: newModel, effects };
    }

    // -----------------------------------------------------------------------
    // Default (exhaustive check)
    // -----------------------------------------------------------------------
    default: {
      const _exhaustive: never = msg;
      return { model, effects: [] };
    }
  }
}

// ============================================================================
// Selectors
// ============================================================================

/**
 * Returns the currently selected run ID.
 */
export function getSelectedRunId(model: RunControlModel): string | null {
  return model.selection.selectedRunId;
}

/**
 * Returns the latest run ID from the runs list.
 */
export function getLatestRunId(model: RunControlModel): string | null {
  return model.selection.latestRunId;
}

/**
 * Returns the payload of the selected run.
 */
export function getSelectedRunPayload(
  model: RunControlModel
): RunPayload | null {
  return model.selectedRun.payload;
}

/**
 * Returns the status of the selected run.
 */
export function getSelectedRunStatus(
  model: RunControlModel
): "idle" | "loading" | "slow" | "loaded" | "failed" {
  return model.selectedRun.status;
}

/**
 * Returns the error of the selected run.
 */
export function getSelectedRunError(model: RunControlModel): string | null {
  return model.selectedRun.error;
}

/**
 * Returns true when selected run is in loading state.
 */
export function shouldShowRunLoading(model: RunControlModel): boolean {
  return model.selectedRun.status === "loading";
}

/**
 * Returns true when selected run has reached slow threshold.
 */
export function shouldShowRunSlow(model: RunControlModel): boolean {
  return model.selectedRun.status === "slow";
}

/**
 * Returns true when selected run has failed.
 */
export function shouldShowRunError(model: RunControlModel): boolean {
  return model.selectedRun.status === "failed";
}

/**
 * Returns true when there's a newer latest run that the user could jump to.
 */
export function shouldShowLatestJump(model: RunControlModel): boolean {
  const { selectedRunId, latestRunId } = model.selection;
  return model.freshness.hasNewerLatest && selectedRunId !== latestRunId;
}

/**
 * Returns the run ID to show in the header.
 * Prefers selected run, falls back to latest, then null.
 */
export function getHeaderRunId(model: RunControlModel): string | null {
  return model.selection.selectedRunId ?? model.selection.latestRunId ?? null;
}

/**
 * Returns the panel state for the selected run display.
 */
export function getRunOwnedPanelState(
  model: RunControlModel
): "no-selection" | "loading" | "slow" | "failed" | "loaded" {
  if (model.selection.selectedRunId === null) {
    return "no-selection";
  }
  switch (model.selectedRun.status) {
    case "loading":
      return "loading";
    case "slow":
      return "slow";
    case "failed":
      return "failed";
    case "loaded":
      return "loaded";
    case "idle":
    default:
      return "no-selection";
  }
}
