/**
 * IncidentDiagnosisLoopPanel Component — Refactored to Elmish pattern.
 *
 * Manual one-pass diagnosis loop trigger for incident detail.
 * Bounded UI seam - runs exactly one read-only pass, displays safe result metadata.
 *
 * Architecture:
 * - Model: incidentDiagnosisLoopModel.ts (state machine types)
 * - Update: incidentDiagnosisLoopUpdate.ts (pure reducer)
 * - Selectors: incidentDiagnosisLoopSelectors.ts (derived view data)
 * - Effects: incidentDiagnosisLoopEffects.ts (API calls)
 *
 * Hard constraints enforced:
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 * - NO external tool invocation
 * - NO automatic scheduling
 * - NO background jobs
 * - NO raw case file display
 * - NO raw runner result display
 * - NO raw artifact content display
 */

import React, { useReducer, useEffect, useMemo } from "react";
import type { IncidentSuggestedCheck } from "../../api";
import type { DiagnosisLoopOnePassResponse } from "../../api/incidentDiagnosisLoop";

// Import Elmish modules
import { update } from "./incidentDiagnosisLoopUpdate";
import type { DiagnosisLoopState } from "./incidentDiagnosisLoopModel";
import { createInitialModel } from "./incidentDiagnosisLoopModel";
import { runDiagnosisLoopEffect } from "./incidentDiagnosisLoopEffects";

// Re-export the type from api for consumers
export type { DiagnosisLoopOnePassResponse } from "../../api/incidentDiagnosisLoop";

export interface IncidentDiagnosisLoopPanelProps {
  incidentId: string;
  suggestedChecks?: IncidentSuggestedCheck[];
}

// =============================================================================
// View Components (dumb renderers - stay simple)
// =============================================================================

/**
 * Safety badge component.
 */
const SafetyBadge: React.FC<{ label: string; variant: "info" | "warning" | "success" }> = ({
  label,
  variant,
}) => <span className={`diagnosis-loop-badge diagnosis-loop-badge-${variant}`}>{label}</span>;

/**
 * Artifact row component - displays artifact name only, no paths.
 */
const ArtifactRow: React.FC<{
  label: string;
  written: boolean;
  name: string | null;
}> = ({ label, written, name }) => (
  <div className="diagnosis-loop-artifact-row">
    <span className="diagnosis-loop-artifact-label">{label}:</span>
    {written && name ? (
      <code className="diagnosis-loop-artifact-name">{name}</code>
    ) : (
      <span className="diagnosis-loop-artifact-not-written muted small">not written</span>
    )}
  </div>
);

/**
 * Result summary component - displays bounded response metadata.
 */
const ResultSummary: React.FC<{ response: DiagnosisLoopOnePassResponse }> = ({ response }) => (
  <div className="diagnosis-loop-result">
    <div className="diagnosis-loop-result-header">
      <h5>One-pass result</h5>
    </div>

    {/* Decision */}
    <div className="diagnosis-loop-result-row">
      <span className="muted small">Decision:</span>
      <span className="diagnosis-loop-decision">{response.decision || "no decision"}</span>
    </div>

    {/* Check counts */}
    <div className="diagnosis-loop-result-row">
      <span className="muted small">Checks:</span>
      <span className="diagnosis-loop-counts">
        requested={response.checks_requested}, run={response.checks_run}, skipped=
        {response.checks_skipped}, rejected={response.checks_rejected}
      </span>
    </div>

    {/* Case file linked */}
    <div className="diagnosis-loop-result-row">
      <span className="muted small">Case file linked:</span>
      <span>{response.case_file_linked_artifact ? "yes" : "no"}</span>
    </div>

    {/* Artifacts */}
    <div className="diagnosis-loop-artifacts">
      <ArtifactRow
        label="read-only-check-results"
        written={response.artifacts.read_only_check_results.written}
        name={response.artifacts.read_only_check_results.name}
      />
      <ArtifactRow
        label="diagnosis-loop-pass"
        written={response.artifacts.diagnosis_loop_pass.written}
        name={response.artifacts.diagnosis_loop_pass.name}
      />
    </div>

    {/* Safety metadata summary */}
    <div className="diagnosis-loop-safety-summary muted small">
      Read-only: {response.safety_metadata.read_only ? "yes" : "no"} · Fake runner:{" "}
      {response.safety_metadata.fake_runner ? "yes" : "no"} · One-pass only:{" "}
      {response.safety_metadata.one_pass_only ? "yes" : "no"}
    </div>
  </div>
);

/**
 * Suggested check item component - displays selectable check with metadata.
 */
const SuggestedCheckItem: React.FC<{
  check: IncidentSuggestedCheck;
  isSelected: boolean;
  isDisabled: boolean;
  onToggle: (checkId: string) => void;
}> = ({ check, isSelected, isDisabled, onToggle }) => (
  <li className="suggested-check-item">
    <label className={`suggested-check-label ${isDisabled ? "disabled" : ""}`}>
      <input
        type="checkbox"
        className="suggested-check-checkbox"
        checked={isSelected}
        disabled={isDisabled}
        onChange={() => onToggle(check.check_id)}
        aria-label={`Select ${check.title}`}
      />
      <div className="suggested-check-content">
        <div className="suggested-check-header">
          <span className="suggested-check-title">{check.title}</span>
          <span className="suggested-check-id muted small">({check.check_id})</span>
        </div>
        <div className="suggested-check-meta muted small">
          <span className="safe-indicator">Read-only</span>
          {check.risk_level && (
            <>
              <span>·</span>
              <span className={`risk-badge risk-${check.risk_level.toLowerCase()}`}>
                {check.risk_level}
              </span>
            </>
          )}
        </div>
      </div>
    </label>
  </li>
);

/**
 * Suggested checks selection component.
 */
const SuggestedChecksSelection: React.FC<{
  checks: IncidentSuggestedCheck[];
  selectedCheckIds: Set<string>;
  isDisabled: boolean;
  onToggle: (checkId: string) => void;
}> = ({ checks, selectedCheckIds, isDisabled, onToggle }) => {
  if (checks.length === 0) {
    return null;
  }

  return (
    <div className="diagnosis-loop-suggested-checks">
      <div className="diagnosis-loop-suggested-checks-header">
        <h5>Optional read-only checks for this pass</h5>
      </div>
      <ul className="diagnosis-loop-suggested-checks-list">
        {checks.map((check) => (
          <SuggestedCheckItem
            key={check.check_id}
            check={check}
            isSelected={selectedCheckIds.has(check.check_id)}
            isDisabled={isDisabled}
            onToggle={onToggle}
          />
        ))}
      </ul>
      <p className="diagnosis-loop-suggested-checks-helper muted small">
        Only existing suggested checks are shown. Backend read-only policy still decides what can
        run.
      </p>
    </div>
  );
};

// =============================================================================
// Main Component (View + Dispatch Wiring)
// =============================================================================

/**
 * Manual diagnosis loop panel for incident detail.
 *
 * Allows an authenticated operator to manually trigger exactly one
 * read-only diagnosis loop pass and view bounded result metadata.
 *
 * Safety guarantees:
 * - Uses runId ownership to reject stale/duplicate completions
 * - Sends selected suggested checks via diagnosis_report when selected
 * - Falls back to empty recommended_investigations when nothing selected
 * - Never displays raw case files, runner results, or artifact contents
 * - Never exposes action-control fields
 * - Does not auto-run on mount
 * - Does not poll or repeat
 * - Rejects stale completions (runId + incidentId ownership)
 */
export const IncidentDiagnosisLoopPanel: React.FC<IncidentDiagnosisLoopPanelProps> = ({
  incidentId,
  suggestedChecks = [],
}) => {
  // Initialize state with incidentId
  const [state, dispatch] = useReducer(update, { tag: "empty" }, () =>
    createInitialModel(incidentId)
  );

  // Sync incidentId changes (re-init when incident changes)
  useEffect(() => {
    dispatch({ type: "init", incidentId });
  }, [incidentId]);

  // Filter suggested checks to only those with valid check_id and non-empty
  const validSuggestedChecks = useMemo(
    () => suggestedChecks.filter((check) => check.check_id && check.check_id.trim() !== ""),
    [suggestedChecks]
  );

  // Derive view data from state
  const isRunning = state.tag === "running";
  const isSuccess = state.tag === "success";
  const isError = state.tag === "error";
  const canToggleChecks = state.tag === "idle";
  const canRun = state.tag === "idle" || state.tag === "success" || state.tag === "error";

  // Get selectedCheckIds from state
  const selectedCheckIds =
    state.tag === "idle" ||
    state.tag === "running" ||
    state.tag === "success" ||
    state.tag === "error"
      ? state.selectedCheckIds
      : new Set<string>();

  // Get response for success state
  const response = state.tag === "success" ? state.response : null;
  const errorMessage = state.tag === "error" ? state.errorMessage : null;

  // Handler: toggle check selection
  const handleToggleCheck = (checkId: string) => {
    dispatch({ type: "checkToggled", checkId });
  };

  // Handler: run diagnosis - generates runId BEFORE dispatching
  // This ensures the runId is message-owned and verifiable on completion
  const handleRun = () => {
    const runId = crypto.randomUUID();
    dispatch({ type: "runRequested", runId });
  };

  // Handler: reset to idle
  const handleReset = () => {
    dispatch({ type: "resetRequested" });
  };

  // Effect: trigger API call when state transitions to running
  // Passes state.runId so effect can include it in completion messages
  useEffect(() => {
    if (state.tag === "running") {
      runDiagnosisLoopEffect(state, validSuggestedChecks, dispatch);
    }
  }, [state, validSuggestedChecks]);

  return (
    <section className="panel incident-diagnosis-loop-panel">
      {/* Header */}
      <div className="diagnosis-loop-header">
        <h4>Manual diagnosis loop</h4>
        <div className="diagnosis-loop-badges">
          <SafetyBadge label="Read-only" variant="success" />
          <SafetyBadge label="One pass only" variant="info" />
        </div>
      </div>

      {/* Explanatory copy */}
      <div className="diagnosis-loop-description muted small">
        <p>
          Runs exactly one read-only diagnosis pass using the safe check policy. This does not
          remediate, mutate the cluster, run kubectl, or schedule future work.
        </p>
      </div>

      {/* Suggested checks selection */}
      {validSuggestedChecks.length > 0 && (
        <SuggestedChecksSelection
          checks={validSuggestedChecks}
          selectedCheckIds={selectedCheckIds}
          isDisabled={!canToggleChecks}
          onToggle={handleToggleCheck}
        />
      )}

      {/* Run button */}
      <div className="diagnosis-loop-action">
        <button
          type="button"
          className="diagnosis-loop-button"
          onClick={handleRun}
          disabled={!canRun || isRunning}
          aria-busy={isRunning}
        >
          {isRunning ? "Running one read-only pass..." : "Run one read-only pass"}
        </button>
        {(isSuccess || isError) && (
          <button
            type="button"
            className="diagnosis-loop-reset-button"
            onClick={handleReset}
          >
            Reset
          </button>
        )}
      </div>

      {/* Success state */}
      {isSuccess && response && <ResultSummary response={response} />}

      {/* Error state */}
      {isError && errorMessage && (
        <div className="diagnosis-loop-error">
          <span className="diagnosis-loop-error-label muted small">Error:</span>
          <span className="diagnosis-loop-error-message">{errorMessage}</span>
        </div>
      )}

      {/* Safety notice */}
      <div className="diagnosis-loop-footer muted small">
        <p>Fake runner · Safe checks only · No remediation · No kubectl · No mutation</p>
      </div>
    </section>
  );
};

export default IncidentDiagnosisLoopPanel;
