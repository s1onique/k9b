/**
 * incidentDiagnosisLoopSelectors.ts — Derived view data selectors.
 *
 * Pure functions that extract view-friendly data from the model.
 * Keep presentation logic separate from state machine logic.
 */

import type { DiagnosisLoopState } from "./incidentDiagnosisLoopModel";
import type { IncidentSuggestedCheck } from "../../api";
import type { DiagnosisLoopOnePassResponse } from "../../api/incidentDiagnosisLoop";

/**
 * Is the diagnosis loop currently running?
 */
export const selectIsRunning = (state: DiagnosisLoopState): boolean =>
  state.tag === "running";

/**
 * Did the diagnosis loop complete successfully?
 */
export const selectIsSuccess = (state: DiagnosisLoopState): boolean =>
  state.tag === "success";

/**
 * Did the diagnosis loop fail?
 */
export const selectIsError = (state: DiagnosisLoopState): boolean =>
  state.tag === "error";

/**
 * Can the user trigger a new run?
 * Allows running from idle, success (run another pass), or error (retry).
 */
export const selectCanRun = (state: DiagnosisLoopState): boolean =>
  state.tag === "idle" || state.tag === "success" || state.tag === "error";

/**
 * Can the user toggle check selections?
 */
export const selectCanToggleChecks = (state: DiagnosisLoopState): boolean =>
  state.tag === "idle";

/**
 * Get the current incident ID.
 */
export const selectIncidentId = (state: DiagnosisLoopState): string => {
  switch (state.tag) {
    case "empty":
      return "";
    case "idle":
    case "loading":
    case "running":
    case "success":
    case "error":
      return state.incidentId;
  }
};

/**
 * Get selected check IDs.
 */
export const selectSelectedCheckIds = (state: DiagnosisLoopState): Set<string> => {
  switch (state.tag) {
    case "empty":
    case "loading":
      return new Set();
    case "idle":
    case "running":
    case "success":
    case "error":
      return state.selectedCheckIds;
  }
};

/**
 * Get the response if the run was successful.
 */
export const selectResponse = (state: DiagnosisLoopState): DiagnosisLoopOnePassResponse | null =>
  state.tag === "success" ? state.response : null;

/**
 * Get the error message if the run failed.
 */
export const selectErrorMessage = (state: DiagnosisLoopState): string | null =>
  state.tag === "error" ? state.errorMessage : null;

/**
 * Filter suggested checks to only valid ones (non-empty check_id).
 */
export const selectValidSuggestedChecks = (checks: IncidentSuggestedCheck[]): IncidentSuggestedCheck[] =>
  checks.filter((check) => check.check_id && check.check_id.trim() !== "");

/**
 * Get counts for display.
 */
export interface DiagnosisLoopCounts {
  totalChecks: number;
  selectedChecks: number;
}

export const selectCounts = (
  state: DiagnosisLoopState,
  suggestedChecks: IncidentSuggestedCheck[]
): DiagnosisLoopCounts => {
  const validChecks = selectValidSuggestedChecks(suggestedChecks);
  const selectedCount =
    state.tag === "idle" ||
    state.tag === "running" ||
    state.tag === "success" ||
    state.tag === "error"
      ? state.selectedCheckIds.size
      : 0;

  return {
    totalChecks: validChecks.length,
    selectedChecks: selectedCount,
  };
};
