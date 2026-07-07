/**
 * incidentDiagnosisLoopModel.ts — Elm-style model and messages for diagnosis loop.
 *
 * Defines the typed state machine for the diagnosis loop panel.
 * Uses discriminated unions for exhaustive state transition checking.
 *
 * Pattern: Elm/TEA-inspired but without Cmd abstraction.
 * Effects live in incidentDiagnosisLoopEffects.ts.
 */

import type { IncidentSuggestedCheck } from "../../api";
import type { DiagnosisLoopOnePassResponse } from "../../api/incidentDiagnosisLoop";

// =============================================================================
// Model (State)
// =============================================================================

/**
 * Core state union for the diagnosis loop panel.
 * Each tag represents a distinct UI state with its associated data.
 *
 * The runId field enables stale-completion rejection:
 * If the user changes incident while a request is in-flight,
 * the old response's runId won't match and will be ignored.
 */
export type DiagnosisLoopState =
  | { tag: "empty" }
  | { tag: "idle"; incidentId: string; selectedCheckIds: Set<string> }
  | { tag: "loading"; incidentId: string }
  | { tag: "running"; incidentId: string; runId: string; selectedCheckIds: Set<string> }
  | { tag: "success"; incidentId: string; runId: string; selectedCheckIds: Set<string>; response: DiagnosisLoopOnePassResponse }
  | { tag: "error"; incidentId: string; runId: string; selectedCheckIds: Set<string>; errorMessage: string };

/**
 * Initial state factory.
 */
export const createInitialModel = (incidentId: string): DiagnosisLoopState => ({
  tag: "idle",
  incidentId,
  selectedCheckIds: new Set(),
});

/**
 * Check if the panel is in a terminal/resetable state.
 */
export const isResetable = (state: DiagnosisLoopState): boolean =>
  state.tag === "success" || state.tag === "error";

/**
 * Check if the panel is currently running.
 */
export const isRunning = (state: DiagnosisLoopState): boolean => state.tag === "running";

/**
 * Check if checks can be toggled.
 */
export const canToggleChecks = (state: DiagnosisLoopState): boolean =>
  state.tag === "idle";

// =============================================================================
// Messages (Events)
// =============================================================================

/**
 * Discriminated union of all possible messages/events.
 * Uses event-style naming (what happened) not setter-style (what to do).
 *
 * The runId in runRequested/runCompleted/runFailed enables ownership tracking:
 * - runRequested carries the runId that was sent to the API
 * - runCompleted/runFailed must include the same runId for the reducer to accept them
 * - Mismatched runId = stale/duplicate response, ignored by reducer
 */
export type DiagnosisLoopMsg =
  | { type: "init"; incidentId: string }
  | { type: "checkToggled"; checkId: string }
  | { type: "runRequested"; runId: string }
  | { type: "runCompleted"; incidentId: string; runId: string; response: DiagnosisLoopOnePassResponse }
  | { type: "runFailed"; incidentId: string; runId: string; errorMessage: string }
  | { type: "resetRequested" };
