/**
 * incidentDiagnosisLoopEffects.ts — Side effects (API calls) for diagnosis loop.
 *
 * Effects are intentionally separate from the reducer.
 * This allows the reducer to remain pure and testable.
 *
 * Each effect function:
 * - Takes the current state and props
 * - Performs async work
 * - Dispatches result messages back to the reducer
 *
 * Pattern: "Pure reducer + effect helper" — no formal Cmd abstraction needed yet.
 *
 * IMPORTANT: The runId is set by the event handler (message-owned),
 * not generated here. The effect uses state.runId to include in completion messages,
 * allowing the reducer to verify ownership and reject stale responses.
 */

import type { DiagnosisLoopMsg } from "./incidentDiagnosisLoopModel";
import type { DiagnosisLoopState } from "./incidentDiagnosisLoopModel";
import type { IncidentSuggestedCheck } from "../../api";
import {
  runIncidentDiagnosisLoopOnePass,
  buildDiagnosisReportFromSelectedChecks,
  createMinimalDiagnosisReport,
} from "../../api/incidentDiagnosisLoop";

// =============================================================================
// Constants
// =============================================================================

/** Maximum error message length to prevent leaking arbitrary error content. */
const BOUND_ERROR_MAX_LENGTH = 500;

// =============================================================================
// Effect Helpers
// =============================================================================

/**
 * Bound an error message to a maximum length.
 * Prevents arbitrary error content (stack traces, internal paths) from leaking.
 */
const boundErrorMessage = (message: string, maxLength: number = BOUND_ERROR_MAX_LENGTH): string => {
  if (message.length <= maxLength) {
    return message;
  }
  return message.slice(0, maxLength) + "...";
};

// =============================================================================
// Effects
// =============================================================================

/**
 * Run the diagnosis loop one-pass effect.
 *
 * This is the main async effect that:
 * 1. Builds the diagnosis report from selected checks
 * 2. Calls the API
 * 3. Dispatches success or failure message with runId for ownership verification
 *
 * The runId is NOT generated here - it comes from the state (set by runRequested message).
 * This ensures the reducer can verify that completion messages match the current run.
 *
 * @param state - Current state (must be running state with runId set)
 * @param suggestedChecks - All available suggested checks
 * @param dispatch - Message dispatcher
 */
export const runDiagnosisLoopEffect = (
  state: DiagnosisLoopState,
  suggestedChecks: IncidentSuggestedCheck[],
  dispatch: (msg: DiagnosisLoopMsg) => void
): void => {
  // Only run from valid running state
  if (state.tag !== "running") {
    return;
  }

  // Use runId from state (set by runRequested message)
  const { incidentId, runId } = state;

  // Build diagnosis report based on selected checks
  const selectedChecksToUse = suggestedChecks.filter((c) =>
    state.selectedCheckIds.has(c.check_id)
  );
  const diagnosisReport =
    selectedChecksToUse.length > 0
      ? buildDiagnosisReportFromSelectedChecks(selectedChecksToUse)
      : createMinimalDiagnosisReport();

  // Run async operation with runId ownership
  runDiagnosisLoopAsync(incidentId, runId, diagnosisReport, dispatch);
};

/**
 * Async wrapper that handles the API call and dispatches result messages.
 *
 * Includes incidentId and runId in completion messages so the reducer can
 * verify ownership and reject stale responses.
 */
const runDiagnosisLoopAsync = (
  incidentId: string,
  runId: string,
  diagnosisReport: Parameters<typeof runIncidentDiagnosisLoopOnePass>[1]["diagnosis_report"],
  dispatch: (msg: DiagnosisLoopMsg) => void
): void => {
  runIncidentDiagnosisLoopOnePass(incidentId, {
    run_id: runId,
    diagnosis_report: diagnosisReport,
  })
    .then((response) => {
      // Include incidentId and runId for ownership verification
      dispatch({ type: "runCompleted", incidentId, runId, response });
    })
    .catch((err: unknown) => {
      const rawMessage = err instanceof Error ? err.message : "Unknown error";
      const boundedMessage = boundErrorMessage(rawMessage);
      // Include incidentId and runId for ownership verification
      dispatch({ type: "runFailed", incidentId, runId, errorMessage: boundedMessage });
    });
};
