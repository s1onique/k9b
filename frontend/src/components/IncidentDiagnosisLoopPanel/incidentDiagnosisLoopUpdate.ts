/**
 * incidentDiagnosisLoopUpdate.ts — Pure reducer for Elm-style state transitions.
 *
 * This module contains ONLY pure state transition logic.
 * No side effects, no API calls, no React hooks.
 *
 * The reducer is exported for unit testing without mounting React components.
 *
 * Key safety features:
 * - runId ownership: stale completions are rejected by verifying runId matches
 * - incidentId tracking: init while running resets to idle
 * - exhaustive switch handling: TypeScript enforces all cases
 */

import type { DiagnosisLoopState, DiagnosisLoopMsg } from "./incidentDiagnosisLoopModel";

// =============================================================================
// Reducer
// =============================================================================

/**
 * Pure state transition function following Elm/TEA pattern.
 *
 * Rules:
 * - Returns new state object (never mutates)
 * - Only processes messages valid for current state
 * - Ignores invalid transitions (returns current state)
 * - All state tags must be handled (exhaustiveness checked by TypeScript)
 *
 * @param state - Current state
 * @param msg - Incoming message/event
 * @returns New state (or same state if transition is invalid)
 */
export function update(state: DiagnosisLoopState, msg: DiagnosisLoopMsg): DiagnosisLoopState {
  switch (state.tag) {
    // -------------------------------------------------------------------------
    // empty state — waiting for init
    // -------------------------------------------------------------------------
    case "empty":
      switch (msg.type) {
        case "init":
          return {
            tag: "idle",
            incidentId: msg.incidentId,
            selectedCheckIds: new Set(),
          };
        default:
          // Ignore all other messages while empty
          return state;
      }

    // -------------------------------------------------------------------------
    // idle state — ready to run
    // -------------------------------------------------------------------------
    case "idle":
      switch (msg.type) {
        case "init":
          // Re-init: only if incidentId changed
          if (msg.incidentId !== state.incidentId) {
            return {
              tag: "idle",
              incidentId: msg.incidentId,
              selectedCheckIds: new Set(),
            };
          }
          return state;

        case "checkToggled":
          return {
            ...state,
            selectedCheckIds: toggleCheckId(state.selectedCheckIds, msg.checkId),
          };

        case "runRequested":
          // runId comes from the event handler, ensures ownership
          return {
            tag: "running",
            incidentId: state.incidentId,
            runId: msg.runId,
            selectedCheckIds: state.selectedCheckIds,
          };

        case "resetRequested":
          // Nothing to reset in idle state
          return state;

        case "runCompleted":
          // Invalid: cannot complete when idle
          return state;

        case "runFailed":
          // Invalid: cannot fail when idle
          return state;
      }

    // -------------------------------------------------------------------------
    // loading state — incident detail is loading (forward compatibility)
    // -------------------------------------------------------------------------
    case "loading":
      switch (msg.type) {
        case "runCompleted":
          // Invalid: cannot complete while loading
          return state;

        case "runFailed":
          // Invalid: cannot fail while loading
          return state;

        case "checkToggled":
          // Cannot toggle checks while loading
          return state;

        case "runRequested":
          // Cannot run while loading
          return state;

        case "resetRequested":
          // Cannot reset while loading
          return state;

        case "init":
          // Re-init with new incident - transition to idle
          return {
            tag: "idle",
            incidentId: msg.incidentId,
            selectedCheckIds: new Set(),
          };
      }

    // -------------------------------------------------------------------------
    // running state — diagnosis in progress
    // -------------------------------------------------------------------------
    case "running":
      switch (msg.type) {
        case "runCompleted":
          // Stale completion rejection: verify both incidentId AND runId match
          if (
            msg.incidentId !== state.incidentId ||
            msg.runId !== state.runId
          ) {
            // Response is for a different incident or stale runId, ignore
            return state;
          }
          return {
            tag: "success",
            incidentId: state.incidentId,
            runId: state.runId,
            selectedCheckIds: state.selectedCheckIds,
            response: msg.response,
          };

        case "runFailed":
          // Stale failure rejection: verify both incidentId AND runId match
          if (
            msg.incidentId !== state.incidentId ||
            msg.runId !== state.runId
          ) {
            // Failure is for a different incident or stale runId, ignore
            return state;
          }
          return {
            tag: "error",
            incidentId: state.incidentId,
            runId: state.runId,
            selectedCheckIds: state.selectedCheckIds,
            errorMessage: msg.errorMessage,
          };

        case "runRequested":
          // Already running, ignore duplicate
          return state;

        case "checkToggled":
          // Cannot toggle checks while running
          return state;

        case "resetRequested":
          // Cannot reset while running, must wait for completion or failure
          return state;

        case "init":
          // Stale incident: reset to idle with new incidentId
          // This prevents old requests from polluting the UI
          return {
            tag: "idle",
            incidentId: msg.incidentId,
            selectedCheckIds: new Set(),
          };
      }

    // -------------------------------------------------------------------------
    // success state — diagnosis completed
    // -------------------------------------------------------------------------
    case "success":
      switch (msg.type) {
        case "runRequested":
          // Run another pass
          return {
            tag: "running",
            incidentId: state.incidentId,
            runId: msg.runId,
            selectedCheckIds: state.selectedCheckIds,
          };

        case "resetRequested":
          return {
            tag: "idle",
            incidentId: state.incidentId,
            selectedCheckIds: state.selectedCheckIds,
          };

        case "init":
          // Re-init with new incident
          if (msg.incidentId !== state.incidentId) {
            return {
              tag: "idle",
              incidentId: msg.incidentId,
              selectedCheckIds: new Set(),
            };
          }
          return state;

        case "checkToggled":
          // Check toggles don't affect current success state
          return state;

        case "runCompleted":
          // Already succeeded, ignore duplicate
          return state;

        case "runFailed":
          // Invalid: already completed successfully
          return state;
      }

    // -------------------------------------------------------------------------
    // error state — diagnosis failed
    // -------------------------------------------------------------------------
    case "error":
      switch (msg.type) {
        case "runRequested":
          // Retry
          return {
            tag: "running",
            incidentId: state.incidentId,
            runId: msg.runId,
            selectedCheckIds: state.selectedCheckIds,
          };

        case "resetRequested":
          return {
            tag: "idle",
            incidentId: state.incidentId,
            selectedCheckIds: state.selectedCheckIds,
          };

        case "init":
          // Re-init with new incident
          if (msg.incidentId !== state.incidentId) {
            return {
              tag: "idle",
              incidentId: msg.incidentId,
              selectedCheckIds: new Set(),
            };
          }
          return state;

        case "checkToggled":
          // Check toggles don't affect current error state
          return state;

        case "runCompleted":
          // Invalid: already failed
          return state;

        case "runFailed":
          // Update error message on repeated failure
          // Note: For error state, we accept the failure regardless of runId
          // since the previous run already failed
          return {
            ...state,
            errorMessage: msg.errorMessage,
          };
      }
  }
}

// =============================================================================
// Pure Helpers
// =============================================================================

/**
 * Toggle a check ID in the set.
 * Returns a new Set (does not mutate).
 */
export function toggleCheckId(selectedCheckIds: Set<string>, checkId: string): Set<string> {
  const next = new Set(selectedCheckIds);
  if (next.has(checkId)) {
    next.delete(checkId);
  } else {
    next.add(checkId);
  }
  return next;
}
