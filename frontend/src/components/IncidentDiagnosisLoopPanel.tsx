/**
 * IncidentDiagnosisLoopPanel Component
 *
 * Manual one-pass diagnosis loop trigger for incident detail.
 * Bounded UI seam - runs exactly one read-only pass, displays safe result metadata.
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

import React, { useState, useCallback } from "react";
import {
  runIncidentDiagnosisLoopOnePass,
  generateManualRunId,
  createMinimalDiagnosisReport,
  type DiagnosisLoopOnePassResponse,
} from "../api/incidentDiagnosisLoop";
import type { DiagnosisLoopOnePassResponse as ApiDiagnosisLoopOnePassResponse } from "../api";

// Re-export the type from api for consumers
export type { DiagnosisLoopOnePassResponse } from "../api";

// Bounded error message helper - prevents arbitrary error content from leaking to UI
const BOUND_ERROR_MAX_LENGTH = 500;

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

export interface IncidentDiagnosisLoopPanelProps {
  incidentId: string;
}

/**
 * UI states for the diagnosis loop panel.
 */
type PanelState = "idle" | "running" | "success" | "error";

/**
 * Safety badge component.
 */
const SafetyBadge: React.FC<{ label: string; variant: "info" | "warning" | "success" }> = ({
  label,
  variant,
}) => (
  <span className={`diagnosis-loop-badge diagnosis-loop-badge-${variant}`}>{label}</span>
);

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
      <span className="diagnosis-loop-artifact-not-written muted small">
        not written
      </span>
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
        requested={response.checks_requested}, run={response.checks_run},
        skipped={response.checks_skipped}, rejected={response.checks_rejected}
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
      Read-only: {response.safety_metadata.read_only ? "yes" : "no"} ·
      Fake runner: {response.safety_metadata.fake_runner ? "yes" : "no"} ·
      One-pass only: {response.safety_metadata.one_pass_only ? "yes" : "no"}
    </div>
  </div>
);

/**
 * Manual diagnosis loop panel for incident detail.
 *
 * Allows an authenticated operator to manually trigger exactly one
 * read-only diagnosis loop pass and view bounded result metadata.
 *
 * Safety guarantees:
 * - Always uses a safe run ID format (manual-loop-{timestamp})
 * - Always sends minimal diagnosis report (empty recommended_investigations)
 * - Never displays raw case files, runner results, or artifact contents
 * - Never exposes action-control fields
 * - Does not auto-run on mount
 * - Does not poll or repeat
 */
export const IncidentDiagnosisLoopPanel: React.FC<IncidentDiagnosisLoopPanelProps> = ({
  incidentId,
}) => {
  const [state, setState] = useState<PanelState>("idle");
  const [response, setResponse] = useState<DiagnosisLoopOnePassResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleRun = useCallback(async () => {
    setState("running");
    setResponse(null);
    setErrorMessage(null);

    try {
      const runId = generateManualRunId();
      const diagnosisReport = createMinimalDiagnosisReport();

      const result = await runIncidentDiagnosisLoopOnePass(incidentId, {
        run_id: runId,
        diagnosis_report: diagnosisReport,
      });

      setResponse(result);
      setState("success");
    } catch (err) {
      const rawMessage = err instanceof Error ? err.message : "Unknown error";
      // Bound error message to prevent leaking arbitrary error content
      setErrorMessage(boundErrorMessage(rawMessage));
      setState("error");
    }
  }, [incidentId]);

  const isRunning = state === "running";
  const isSuccess = state === "success";
  const isError = state === "error";

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
          Runs exactly one read-only diagnosis pass using the safe check policy.
          This does not remediate, mutate the cluster, run kubectl, or schedule future work.
        </p>
      </div>

      {/* Run button */}
      <div className="diagnosis-loop-action">
        <button
          type="button"
          className="diagnosis-loop-button"
          onClick={handleRun}
          disabled={isRunning}
          aria-busy={isRunning}
        >
          {isRunning ? "Running one read-only pass..." : "Run one read-only pass"}
        </button>
      </div>

      {/* Success state */}
      {isSuccess && response && (
        <ResultSummary response={response} />
      )}

      {/* Error state */}
      {isError && errorMessage && (
        <div className="diagnosis-loop-error">
          <span className="diagnosis-loop-error-label muted small">Error:</span>
          <span className="diagnosis-loop-error-message">{errorMessage}</span>
        </div>
      )}

      {/* Safety notice */}
      <div className="diagnosis-loop-footer muted small">
        <p>
          Fake runner · Safe checks only · No remediation · No kubectl · No mutation
        </p>
      </div>
    </section>
  );
};

export default IncidentDiagnosisLoopPanel;
