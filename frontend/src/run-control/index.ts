/**
 * run-control/index.ts — Elm-ish Run Control Plane public exports.
 *
 * Phase 1: Types, reducer, selectors, initializer.
 */

// Types
export type {
  RunControlModel,
  RunsState,
  SelectedRunState,
  SelectionState,
  FreshnessState,
  DebugState,
  RunControlMsg,
  RunControlEffect,
  CreateInitialModelConfig,
  BootMsg,
  DebugModeDetectedMsg,
  RunsRequestedMsg,
  RunsLoadedMsg,
  RunsFailedMsg,
  RunSelectedMsg,
  LatestClickedMsg,
  SelectionClearedMsg,
  RunLoadedMsg,
  RunFailedMsg,
  RunSlowThresholdReachedMsg,
  ManualRefreshClickedMsg,
  PollTickMsg,
  RetrySelectedRunClickedMsg,
  FetchRunsEffect,
  FetchRunEffect,
  ScheduleSlowRunTimerEffect,
  CancelSlowRunTimerEffect,
  DebugLogEffect,
  AbortRunFetchEffect,
} from "./runControlTypes";

// Initializer
export { createInitialRunControlModel } from "./runControlReducer";

// Reducer
export { updateRunControl } from "./runControlReducer";

// Selectors
export {
  getSelectedRunId,
  getLatestRunId,
  getSelectedRunPayload,
  getSelectedRunStatus,
  getSelectedRunError,
  shouldShowRunLoading,
  shouldShowRunSlow,
  shouldShowRunError,
  shouldShowLatestJump,
  getHeaderRunId,
  getRunOwnedPanelState,
} from "./runControlReducer";
