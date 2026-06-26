/**
 * runDetailModel.ts - Elm-ish model types for Run Detail UI state.
 *
 * Defines the core state, messages, and commands for the run-detail
 * feature-local Elm-ish reducer.
 *
 * This refactoring addresses React #310 "Rendered more hooks than during
 * the previous render" by:
 * 1. Moving all state into a single model (no conditional hooks)
 * 2. Using pure reducer/update function for state transitions
 * 3. Isolating side effects to a narrow fetch/command interpreter
 * 4. Presentational components receive model + dispatch and do not call hooks
 *
 * @module app/runDetail/runDetailModel
 */
import type { RunPayload, NextCheckPlanCandidate, NextCheckStatusVariant } from "../../types";
import type { LlmTelemetryPreviewData } from "../../components/run-summary/RunOverviewDashboard";

// ============================================================================
// Model
// ============================================================================

/**
 * Panel display state for the run detail.
 */
export type RunDetailPanelState =
  | "no-selection"  // No run selected
  | "loading"       // Run fetch in progress
  | "slow"          // Run fetch taking too long
  | "failed"        // Run fetch failed
  | "loaded";       // Run data available

/**
 * Active tab in the run summary.
 */
export type RunDetailTabId = "overview" | "notifications" | "external-analysis";

/**
 * Debug diagnostics state.
 */
export interface DebugDiagnosticsState {
  enabled: boolean;
  error: string | null;
  isLoading: boolean;
}

/**
 * Feature-local state model for run detail UI.
 *
 * Owns:
 * - activeTab: current tab selection
 * - debugDiagnostics: debug diagnostics feature state
 * - downloadState: download-in-progress tracking
 */
export interface RunDetailModel {
  /** Currently active tab in run summary */
  activeTab: RunDetailTabId;
  /** Debug diagnostics feature state */
  debugDiagnostics: DebugDiagnosticsState;
  /** Whether a diagnostics download is in progress */
  isDownloadingDiagnostics: boolean;
}

/**
 * Initial state for the run detail reducer.
 */
export const initialModel: RunDetailModel = {
  activeTab: "overview",
  debugDiagnostics: {
    enabled: false,
    error: null,
    isLoading: false,
  },
  isDownloadingDiagnostics: false,
};

// ============================================================================
// Messages
// ============================================================================

/**
 * Discriminated union of all messages that can occur in the run detail UI.
 */
export type Msg =
  // Tab navigation
  | { type: "TabChanged"; tab: RunDetailTabId }
  // Debug diagnostics lifecycle
  | { type: "DebugDiagnosticsCheckStarted" }
  | { type: "DebugDiagnosticsEnabled"; enabled: boolean }
  | { type: "DebugDiagnosticsError"; error: string }
  // Diagnostics download - user requested download
  | { type: "DiagnosticsDownloadRequested"; runId: string }
  // Diagnostics download lifecycle (from effects)
  | { type: "DiagnosticsDownloadStarted" }
  | { type: "DiagnosticsDownloadSucceeded" }
  | { type: "DiagnosticsDownloadFailed"; error: string }
  // Debug diagnostics loading check completed
  | { type: "DebugDiagnosticsLoadingComplete" };

/**
 * Discriminated union of all side effects (commands) that the reducer can emit.
 *
 * Effects stay OUTSIDE update() and are executed by the effect runner.
 */
export type Cmd =
  /** Fetch whether debug diagnostics are enabled on the backend */
  | { type: "CheckDebugDiagnosticsEnabled" }
  /** Download execution state diagnostics bundle */
  | { type: "DownloadDiagnostics"; runId: string }
  /** No-op command for states that don't need side effects */
  | { type: "NoOp" };

/**
 * Result from update() - pure state transition.
 */
export type UpdateResult = {
  model: RunDetailModel;
  cmd: Cmd;
};

// ============================================================================
// Helpers
// ============================================================================

/**
 * Create the initial model for a new reducer instance.
 * Useful for testing and initial hook state.
 */
export function createInitialModel(): RunDetailModel {
  return { ...initialModel };
}

/**
 * Check if debug diagnostics are enabled.
 */
export function isDebugDiagnosticsEnabled(model: RunDetailModel): boolean {
  return model.debugDiagnostics.enabled;
}

/**
 * Check if debug diagnostics check is in progress.
 */
export function isDebugDiagnosticsLoading(model: RunDetailModel): boolean {
  return model.debugDiagnostics.isLoading;
}

/**
 * Check if diagnostics download is in progress.
 */
export function isDownloadingDiagnostics(model: RunDetailModel): boolean {
  return model.isDownloadingDiagnostics;
}

/**
 * Get the debug diagnostics error if any.
 */
export function getDebugDiagnosticsError(model: RunDetailModel): string | null {
  return model.debugDiagnostics.error;
}
