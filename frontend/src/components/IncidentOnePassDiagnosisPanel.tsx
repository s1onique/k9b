/**
 * IncidentOnePassDiagnosisPanel Component
 *
 * Read-only one-pass diagnosis trigger for incident detail.
 * Bounded UI seam - runs exactly one read-only pass, displays safe result metadata.
 *
 * Hard constraints enforced:
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 * - NO external tool invocation
 * - NO automatic scheduling
 * - NO background jobs
 * - NO raw artifact content display
 * - Safety contract validation before presenting results
 */

import React, { useState, useCallback } from "react";
import {
  runIncidentOnePassDiagnosis,
  generateOnePassRunId,
  validateOnePassSafety,
  type IncidentOnePassDiagnosisResponse,
  type OnePassSafetyValidation,
} from "../api/incidentOnePassDiagnosis";

// Re-export types for consumers
export type { IncidentOnePassDiagnosisResponse, OnePassSafetyValidation } from "../api/incidentOnePassDiagnosis";

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

export interface IncidentOnePassDiagnosisPanelProps {
  incidentId: string;
}

/**
 * UI states for the one-pass diagnosis panel.
 */
type PanelState = "idle" | "running" | "success" | "safety_failure" | "error";

/**
 * Safety badge component.
 */
const SafetyBadge: React.FC<{ label: string; variant: "info" | "warning" | "success" }> = ({
  label,
  variant,
}) => (
  <span className={`one-pass-badge one-pass-badge-${variant}`}>{label}</span>
);

/**
 * Evidence ref item component - displays evidence reference safely.
 * Uses refId prop to avoid confusion with React's special ref prop.
 */
const EvidenceRefItem: React.FC<{ refId: string; index: number }> = ({ refId, index }) => (
  <li className="one-pass-evidence-ref-item">
    <span className="one-pass-evidence-ref-index muted small">{index + 1}.</span>
    <code className="one-pass-evidence-ref-id">{refId}</code>
  </li>
);

/**
 * Next check item component - displays check safely without mutation controls.
 * Omits checks that appear unsafe.
 */
const NextCheckItem: React.FC<{ check: IncidentOnePassDiagnosisResponse["next_checks"][0]; index: number }> = ({
  check,
  index,
}) => {
  const checkId = check.check_id || "unknown";
  const title = check.title || checkId;

  return (
    <li className="one-pass-next-check-item">
      <div className="one-pass-next-check-header">
        <span className="one-pass-next-check-index muted small">{index + 1}.</span>
        <span className="one-pass-next-check-title">{title}</span>
        {check.read_only === true && (
          <span className="one-pass-badge one-pass-badge-success">Read-only</span>
        )}
      </div>
      {check.check_id && check.check_id !== title && (
        <div className="one-pass-next-check-id muted small">
          {check.check_id}
        </div>
      )}
    </li>
  );
};

/**
 * Safety failure section - shows when response fails safety validation.
 */
const SafetyFailureSection: React.FC<{ validation: OnePassSafetyValidation }> = ({ validation }) => (
  <div className="one-pass-safety-failure">
    <div className="one-pass-safety-failure-header">
      <span className="one-pass-badge one-pass-badge-warning">Safety violation</span>
    </div>
    <p className="one-pass-safety-failure-message">
      The diagnosis response failed safety validation and cannot be presented as valid.
    </p>
    <ul className="one-pass-safety-failure-list">
      {validation.readOnlyViolation && (
        <li>read_only flag is not true</li>
      )}
      {validation.allowedActionsViolation && (
        <li>allowed_actions is non-empty (contains: {validation.allowedActionsViolation ? "yes" : "no"})</li>
      )}
      {validation.mutationProposalsViolation && (
        <li>mutation_proposals_observed is non-empty</li>
      )}
      {validation.unsafeNextChecks.length > 0 && (
        <li>
          {validation.unsafeNextChecks.length} next check(s) contain mutation-related terms
        </li>
      )}
    </ul>
    <p className="one-pass-safety-failure-notice muted small">
      This diagnosis cannot be trusted as read-only. No actions should be taken based on this result.
    </p>
  </div>
);

/**
 * Result summary component - displays bounded response metadata.
 */
const ResultSummary: React.FC<{
  response: IncidentOnePassDiagnosisResponse;
  safetyValidation: OnePassSafetyValidation;
}> = ({ response, safetyValidation }) => (
  <div className="one-pass-result">
    <div className="one-pass-result-header">
      <h5>One-pass diagnosis result</h5>
      {safetyValidation.isValid && (
        <SafetyBadge label="Read-only verified" variant="success" />
      )}
    </div>

    {/* Safety confirmation */}
    <div className="one-pass-safety-confirmation muted small">
      read_only={String(response.read_only)} · allowed_actions={response.allowed_actions.length} · mutation_proposals={response.mutation_proposals_observed.length}
    </div>

    {/* Category */}
    {response.category && (
      <div className="one-pass-result-row">
        <span className="muted small">Category:</span>
        <span className="one-pass-category">{response.category}</span>
      </div>
    )}

    {/* Root cause */}
    {response.root_cause && (
      <div className="one-pass-result-row">
        <span className="muted small">Root cause:</span>
        <span className="one-pass-root-cause">{response.root_cause}</span>
      </div>
    )}

    {/* Confidence */}
    {response.confidence && (
      <div className="one-pass-result-row">
        <span className="muted small">Confidence:</span>
        <span className={`one-pass-confidence one-pass-confidence-${response.confidence.toLowerCase()}`}>
          {response.confidence}
        </span>
      </div>
    )}

    {/* Description */}
    {response.description && (
      <div className="one-pass-result-row one-pass-result-description">
        <span className="muted small">Description:</span>
        <span className="one-pass-description">{response.description}</span>
      </div>
    )}

    {/* Evidence refs */}
    {response.evidence_refs && response.evidence_refs.length > 0 && (
      <div className="one-pass-result-row">
        <span className="muted small">Evidence refs ({response.evidence_refs.length}):</span>
        <ul className="one-pass-evidence-refs-list">
          {response.evidence_refs.slice(0, 10).map((ref, index) => (
            <EvidenceRefItem key={index} refId={ref} index={index} />
          ))}
          {response.evidence_refs.length > 10 && (
            <li className="one-pass-evidence-ref-overflow muted small">
              ... and {response.evidence_refs.length - 10} more
            </li>
          )}
        </ul>
      </div>
    )}

    {/* Checks run */}
    <div className="one-pass-result-row">
      <span className="muted small">Checks run:</span>
      <span className="one-pass-checks-run">{response.checks_run}</span>
    </div>

    {/* Decision */}
    {response.decision && (
      <div className="one-pass-result-row">
        <span className="muted small">Decision:</span>
        <span className="one-pass-decision">{response.decision}</span>
      </div>
    )}

    {/* Next checks */}
    {response.next_checks && response.next_checks.length > 0 && (
      <div className="one-pass-result-row one-pass-next-checks">
        <span className="muted small">Next read-only checks ({response.next_checks.length}):</span>
        <ul className="one-pass-next-checks-list">
          {response.next_checks.slice(0, 5).map((check, index) => (
            <NextCheckItem key={index} check={check} index={index} />
          ))}
          {response.next_checks.length > 5 && (
            <li className="one-pass-next-checks-overflow muted small">
              ... and {response.next_checks.length - 5} more
            </li>
          )}
        </ul>
      </div>
    )}

    {/* Artifact */}
    {response.artifact_written && response.artifact_name && (
      <div className="one-pass-result-row">
        <span className="muted small">Artifact:</span>
        <code className="one-pass-artifact-name">{response.artifact_name}</code>
      </div>
    )}
  </div>
);

/**
 * Read-only one-pass diagnosis panel for incident detail.
 *
 * Allows an authenticated operator to manually trigger exactly one
 * read-only diagnosis pass and view bounded result metadata.
 *
 * Safety guarantees:
 * - Always validates response safety contract before presenting results
 * - Never displays results that fail safety validation
 * - Never displays mutation-oriented controls
 * - Does not auto-run on mount
 * - Does not poll or repeat
 */
export const IncidentOnePassDiagnosisPanel: React.FC<IncidentOnePassDiagnosisPanelProps> = ({
  incidentId,
}) => {
  const [state, setState] = useState<PanelState>("idle");
  const [response, setResponse] = useState<IncidentOnePassDiagnosisResponse | null>(null);
  const [safetyValidation, setSafetyValidation] = useState<OnePassSafetyValidation | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleRun = useCallback(async () => {
    setState("running");
    setResponse(null);
    setSafetyValidation(null);
    setErrorMessage(null);

    try {
      const runId = generateOnePassRunId();

      const result = await runIncidentOnePassDiagnosis(incidentId, { runId });

      // Validate safety contract
      const validation = validateOnePassSafety(result);
      setResponse(result);
      setSafetyValidation(validation);

      if (validation.isValid) {
        setState("success");
      } else {
        setState("safety_failure");
      }
    } catch (err) {
      const rawMessage = err instanceof Error ? err.message : "Unknown error";
      // Bound error message to prevent leaking arbitrary error content
      setErrorMessage(boundErrorMessage(rawMessage));
      setState("error");
    }
  }, [incidentId]);

  const isRunning = state === "running";
  const isSuccess = state === "success";
  const isSafetyFailure = state === "safety_failure";
  const isError = state === "error";

  return (
    <section className="panel incident-one-pass-diagnosis-panel">
      {/* Header */}
      <div className="one-pass-header">
        <h4>One-pass read-only diagnosis</h4>
        <div className="one-pass-badges">
          <SafetyBadge label="Read-only" variant="success" />
          <SafetyBadge label="One pass only" variant="info" />
          <SafetyBadge label="No remediation" variant="info" />
        </div>
      </div>

      {/* Explanatory copy */}
      <div className="one-pass-description muted small">
        <p>
          Runs exactly one read-only diagnosis pass using the safe check policy.
          This does not remediate, mutate the cluster, run kubectl, or schedule future work.
          No changes will be applied to the cluster.
        </p>
      </div>

      {/* Run button */}
      <div className="one-pass-action">
        <button
          type="button"
          className="one-pass-button"
          onClick={handleRun}
          disabled={isRunning}
          aria-busy={isRunning}
          aria-label="Run read-only one-pass diagnosis"
        >
          {isRunning ? "Running read-only diagnosis…" : "Run read-only diagnosis"}
        </button>
      </div>

      {/* Success state */}
      {isSuccess && response && safetyValidation && (
        <ResultSummary response={response} safetyValidation={safetyValidation} />
      )}

      {/* Safety failure state */}
      {isSafetyFailure && response && safetyValidation && (
        <SafetyFailureSection validation={safetyValidation} />
      )}

      {/* Error state */}
      {isError && errorMessage && (
        <div className="one-pass-error">
          <span className="one-pass-error-label muted small">Error:</span>
          <span className="one-pass-error-message">{errorMessage}</span>
        </div>
      )}

      {/* Safety notice */}
      <div className="one-pass-footer muted small">
        <p>
          Read-only · No kubectl · No mutation · No remediation
        </p>
      </div>
    </section>
  );
};

export default IncidentOnePassDiagnosisPanel;
