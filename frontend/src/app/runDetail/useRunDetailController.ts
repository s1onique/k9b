/**
 * useRunDetailController.ts - Elm-ish Run Detail controller hook.
 *
 * Owns the runtime boundary between the pure reducer and React.
 * This is the ONLY place where hooks are allowed for the run-detail feature.
 *
 * Responsibilities:
 * - Initialize RunDetailModel
 * - Dispatch RunDetailMsg
 * - Run update function
 * - Execute Cmd values
 * - All hooks called unconditionally at top level
 *
 * Elm-ish contract:
 * message -> pure update -> commit model -> interpret effects
 *
 * This implementation follows the same pattern as useApprovalFlowController,
 * useBatchExecutionController, and useManualExecutionController.
 *
 * @module app/runDetail/useRunDetailController
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { RunDetailModel, Msg, Cmd } from "./runDetailModel";
import { initialModel } from "./runDetailModel";
import { update, createInitialModel } from "./runDetailUpdate";
import { drainEffects } from "./runDetailEffects";

// ============================================================================
// Hook options
// ============================================================================

export interface UseRunDetailControllerOptions {
  /**
   * Automatically check debug diagnostics enabled on mount.
   * Default: true
   */
  autoCheckDebugDiagnostics?: boolean;
}

// ============================================================================
// Runtime state (pure)
// ============================================================================

/**
 * Pure runtime state for the run-detail controller.
 *
 * Using separate fields for model, pendingCmds, and effectSeq ensures:
 * 1. setState updater is pure (no mutation of refs)
 * 2. React can detect impurity if we mutate state directly
 * 3. Effect draining is driven by effectSeq changes, not model changes
 */
interface RunDetailRuntimeState {
  /** The current model state */
  model: RunDetailModel;
  /** Pending commands to execute */
  pendingCmds: Cmd[];
  /** Sequence number for effect draining (increments on each dispatch) */
  effectSeq: number;
}

/** Initial runtime state */
const initialRuntimeState: RunDetailRuntimeState = {
  model: createInitialModel(),
  pendingCmds: [],
  effectSeq: 0,
};

// ============================================================================
// Hook result
// ============================================================================

export interface UseRunDetailControllerResult {
  /** The current run detail model (read-only). */
  model: RunDetailModel;

  /** Dispatch a message to the reducer. */
  dispatch: (msg: Msg) => void;

  /** Change the active tab. */
  setActiveTab: (tab: RunDetailModel["activeTab"]) => void;

  /** Check if debug diagnostics are enabled. */
  isDebugDiagnosticsEnabled: boolean;

  /** Check if debug diagnostics check is in progress. */
  isDebugDiagnosticsLoading: boolean;

  /** Get debug diagnostics error if any. */
  debugDiagnosticsError: string | null;

  /** Check if diagnostics download is in progress. */
  isDownloadingDiagnostics: boolean;

  /** Start downloading diagnostics for a run. */
  downloadDiagnostics: (runId: string) => void;
}

// ============================================================================
// Hook implementation
// ============================================================================

/**
 * useRunDetailController — React hook that owns the runtime boundary for run detail.
 *
 * ALL hooks are called unconditionally at the top level.
 * The component only receives model values and dispatch functions.
 *
 * Effect queue is handled PURELY:
 * - dispatch() returns a new state with pendingCmds included
 * - useEffect drains pendingCmds based on effectSeq changes
 * - No mutation of refs inside setState updater
 */
export function useRunDetailController(
  options: UseRunDetailControllerOptions = {}
): UseRunDetailControllerResult {
  const { autoCheckDebugDiagnostics = true } = options;

  // Initialize runtime state - ALL hooks at top level, unconditionally
  const [state, setState] = useState<RunDetailRuntimeState>(() => ({
    ...initialRuntimeState,
    model: createInitialModel(),
  }));

  // Ref to track executed commands for StrictMode deduplication
  // This is separate from state to avoid triggering re-renders
  const executedCmdsRef = useRef<Set<string>>(new Set());

  // --------------------------------------------------------------------------
  // Dispatch (pure)
  // --------------------------------------------------------------------------

  /**
   * Pure dispatch that:
   * 1. Calls update(currentModel, msg) - PURE
   * 2. Returns new state with updated model and pending commands
   *
   * No mutation of external state - all changes are immutable.
   */
  const dispatch = useCallback((msg: Msg): void => {
    setState((prev) => {
      const result = update(prev.model, msg);
      return {
        model: result.model,
        pendingCmds: result.cmd.type === "NoOp" ? [] : [result.cmd],
        effectSeq: prev.effectSeq + 1,
      };
    });
  }, []);

  // --------------------------------------------------------------------------
  // Effect drainer (driven by effectSeq)
  // --------------------------------------------------------------------------

  /**
   * Drains pending effects when effectSeq changes.
   *
   * Uses effectSeq as the trigger so we don't drain effects when only
   * the model changes (e.g., from other sources).
   *
   * Deduplicates commands that were already executed in StrictMode.
   */
  useEffect(() => {
    const { pendingCmds, effectSeq } = state;

    if (pendingCmds.length === 0) {
      return;
    }

    // Deduplicate: if this exact command was already executed, skip it
    // This guards against StrictMode double-effect execution
    const cmdKey = `${effectSeq}-${pendingCmds[0].type}`;
    if (pendingCmds[0].type !== "NoOp" && executedCmdsRef.current.has(cmdKey)) {
      // Already executed this command in StrictMode, clear and skip
      setState((prev) => ({
        ...prev,
        pendingCmds: [],
      }));
      return;
    }

    // Mark as executed
    executedCmdsRef.current.add(cmdKey);

    // Execute the command
    drainEffects(pendingCmds, { dispatch });

    // Clear pending commands after draining
    setState((prev) => ({
      ...prev,
      pendingCmds: [],
    }));
  }, [state.effectSeq, state.pendingCmds, dispatch]);

  // --------------------------------------------------------------------------
  // Auto-check debug diagnostics
  // --------------------------------------------------------------------------

  useEffect(() => {
    if (autoCheckDebugDiagnostics) {
      // Start by checking if debug diagnostics are enabled
      dispatch({ type: "DebugDiagnosticsCheckStarted" });
    }
  }, [autoCheckDebugDiagnostics, dispatch]);

  // --------------------------------------------------------------------------
  // Public actions
  // --------------------------------------------------------------------------

  const setActiveTab = useCallback(
    (tab: RunDetailModel["activeTab"]) => {
      dispatch({ type: "TabChanged", tab });
    },
    [dispatch]
  );

  const downloadDiagnostics = useCallback(
    (runId: string) => {
      dispatch({ type: "DiagnosticsDownloadRequested", runId });
    },
    [dispatch]
  );

  // --------------------------------------------------------------------------
  // Derived values (selectors)
  // --------------------------------------------------------------------------

  const isDebugDiagnosticsEnabled = useMemo(
    () => state.model.debugDiagnostics.enabled,
    [state.model.debugDiagnostics.enabled]
  );

  const isDebugDiagnosticsLoading = useMemo(
    () => state.model.debugDiagnostics.isLoading,
    [state.model.debugDiagnostics.isLoading]
  );

  const debugDiagnosticsError = useMemo(
    () => state.model.debugDiagnostics.error,
    [state.model.debugDiagnostics.error]
  );

  const isDownloadingDiagnostics = useMemo(
    () => state.model.isDownloadingDiagnostics,
    [state.model.isDownloadingDiagnostics]
  );

  // --------------------------------------------------------------------------
  // Return
  // --------------------------------------------------------------------------

  return {
    model: state.model,
    dispatch,
    setActiveTab,
    isDebugDiagnosticsEnabled,
    isDebugDiagnosticsLoading,
    debugDiagnosticsError,
    isDownloadingDiagnostics,
    downloadDiagnostics,
  };
}
