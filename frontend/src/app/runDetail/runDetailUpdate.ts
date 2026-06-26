/**
 * runDetailUpdate.ts - Pure Elm-ish update function for Run Detail UI state.
 *
 * Contains the pure state transition logic (no side effects, no async).
 * All effects are returned as Cmd and executed by the effect runner.
 *
 * This refactoring addresses React #310 by:
 * - All state transitions are pure functions
 * - Side effects are isolated to Cmd values
 * - No conditional hook calls
 *
 * @module app/runDetail/runDetailUpdate
 */
import type { RunDetailModel, Msg, Cmd, UpdateResult } from "./runDetailModel";
import { initialModel } from "./runDetailModel";

/**
 * Pure state transition function following Elm architecture.
 *
 * Given a model and a message, returns a new model and optionally a command
 * to execute (side effects handled outside update).
 *
 * @param model - Current model state
 * @param msg - Message describing what happened
 * @returns UpdateResult with new model and command to execute
 */
export function update(model: RunDetailModel, msg: Msg): UpdateResult {
  switch (msg.type) {
    // -------------------------------------------------------------------------
    // Tab navigation
    // -------------------------------------------------------------------------
    case "TabChanged": {
      return {
        model: {
          ...model,
          activeTab: msg.tab,
        },
        cmd: { type: "NoOp" },
      };
    }

    // -------------------------------------------------------------------------
    // Debug diagnostics lifecycle
    // -------------------------------------------------------------------------
    case "DebugDiagnosticsCheckStarted": {
      return {
        model: {
          ...model,
          debugDiagnostics: {
            ...model.debugDiagnostics,
            isLoading: true,
            error: null,
          },
        },
        cmd: { type: "CheckDebugDiagnosticsEnabled" },
      };
    }

    case "DebugDiagnosticsEnabled": {
      return {
        model: {
          ...model,
          debugDiagnostics: {
            ...model.debugDiagnostics,
            enabled: msg.enabled,
            isLoading: false,
            error: null,
          },
        },
        cmd: { type: "NoOp" },
      };
    }

    case "DebugDiagnosticsError": {
      return {
        model: {
          ...model,
          debugDiagnostics: {
            ...model.debugDiagnostics,
            enabled: false,
            isLoading: false,
            error: msg.error,
          },
        },
        cmd: { type: "NoOp" },
      };
    }

    case "DebugDiagnosticsLoadingComplete": {
      // Mark loading as complete without changing enabled state
      // Used when the check completes but we don't have a specific enabled value
      return {
        model: {
          ...model,
          debugDiagnostics: {
            ...model.debugDiagnostics,
            isLoading: false,
          },
        },
        cmd: { type: "NoOp" },
      };
    }

    // -------------------------------------------------------------------------
    // Diagnostics download
    // -------------------------------------------------------------------------
    case "DiagnosticsDownloadRequested": {
      // User requested a download - emit a command to execute the download
      return {
        model: {
          ...model,
          isDownloadingDiagnostics: true,
          debugDiagnostics: {
            ...model.debugDiagnostics,
            error: null,
          },
        },
        cmd: { type: "DownloadDiagnostics", runId: msg.runId },
      };
    }

    case "DiagnosticsDownloadStarted": {
      return {
        model: {
          ...model,
          isDownloadingDiagnostics: true,
          debugDiagnostics: {
            ...model.debugDiagnostics,
            error: null,
          },
        },
        cmd: { type: "NoOp" },
      };
    }

    case "DiagnosticsDownloadSucceeded": {
      return {
        model: {
          ...model,
          isDownloadingDiagnostics: false,
          debugDiagnostics: {
            ...model.debugDiagnostics,
            error: null,
          },
        },
        cmd: { type: "NoOp" },
      };
    }

    case "DiagnosticsDownloadFailed": {
      return {
        model: {
          ...model,
          isDownloadingDiagnostics: false,
          debugDiagnostics: {
            ...model.debugDiagnostics,
            error: msg.error,
          },
        },
        cmd: { type: "NoOp" },
      };
    }

    // -------------------------------------------------------------------------
    // Exhaustiveness check
    // -------------------------------------------------------------------------
    default: {
      const _exhaustive: never = msg;
      return { model, cmd: { type: "NoOp" } };
    }
  }
}

/**
 * Create the initial model for a new reducer instance.
 * Useful for testing and initial hook state.
 */
export function createInitialModel(): RunDetailModel {
  return { ...initialModel };
}
