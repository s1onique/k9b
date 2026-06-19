/**
 * incidentDiagnosisLoop.ts — API client for manual one-pass diagnosis loop.
 *
 * Runs exactly one read-only diagnosis pass for an incident.
 * This is a safe, bounded UI seam only.
 *
 * Auth/session behavior: Uses raw fetch which preserves existing browser auth
 * (cookies, session headers). This matches existing frontend API conventions.
 *
 * Hard constraints:
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 * - NO external tool invocation
 * - NO automatic scheduling
 * - NO background jobs
 */

import type { IncidentSuggestedCheck } from "../api";
import type { DiagnosisLoopOnePassRequest, DiagnosisLoopOnePassResponse } from "./types";

// =============================================================================
// Types
// =============================================================================

/**
 * Investigation recommendation for diagnosis report.
 * Bounded shape - no freeform fields.
 */
export type DiagnosisInvestigation = {
  check_id?: string;
  title?: string;
  read_only?: boolean;
  source?: string;
};

/**
 * Diagnosis section of the request.
 */
export type DiagnosisSection = {
  recommended_investigations: DiagnosisInvestigation[];
};

/**
 * Diagnosis report - bounded caller-provided guidance.
 */
export type DiagnosisReport = {
  diagnosis: DiagnosisSection;
};

/**
 * Request shape for one-pass diagnosis loop.
 * Bounded - no filesystem paths, no action-control fields.
 */
export type DiagnosisLoopOnePassRequest = {
  run_id: string;
  diagnosis_report: DiagnosisReport;
};

/**
 * Artifact reference (name only, no path).
 */
export type DiagnosisArtifactRef = {
  written: boolean;
  name: string | null;
};

/**
 * Artifacts written by the loop pass.
 */
export type DiagnosisArtifacts = {
  read_only_check_results: DiagnosisArtifactRef;
  diagnosis_loop_pass: DiagnosisArtifactRef;
};

/**
 * Safety metadata returned by the backend.
 */
export type DiagnosisSafetyMetadata = {
  read_only: boolean;
  allowed_actions: string[];
  no_kubernetes_client: boolean;
  no_shell: boolean;
  no_subprocess: boolean;
  no_kubectl: boolean;
  no_mutation: boolean;
  fake_runner: boolean;
  one_pass_only: boolean;
};

/**
 * Response from one-pass diagnosis loop.
 * Bounded - no raw artifact contents, no runner internals.
 */
export type DiagnosisLoopOnePassResponse = {
  schema_version: string;
  incident_id: string;
  run_id: string;
  read_only: true;
  allowed_actions: [];
  decision: string;
  checks_requested: number;
  checks_run: number;
  checks_skipped: number;
  checks_rejected: number;
  artifacts: DiagnosisArtifacts;
  case_file_linked_artifact: boolean;
  safety_metadata: DiagnosisSafetyMetadata;
  error?: string;
};

// =============================================================================
// Constants
// =============================================================================

/** Maximum number of suggested checks that can be selected per pass. */
const MAX_SELECTABLE_CHECKS = 5;

/** Maximum length for check_id field in request. */
const MAX_CHECK_ID_LENGTH = 100;

/** Maximum length for title field in request. */
const MAX_TITLE_LENGTH = 200;

/** Fixed source value for manual suggested check selection. */
const MANUAL_SUGGESTED_CHECK_SOURCE = "manual_suggested_check";

// =============================================================================
// Safety Filtering
// =============================================================================

/**
 * Forbidden field patterns that indicate unsafe/mutation actions.
 * Any check containing these patterns should not be forwarded.
 */
const FORBIDDEN_PATTERNS = [
  "mutate", "delete", "patch", "scale", "restart", "rollout",
  "apply", "remediate", "kubectl", "exec", "run", "execute",
  "external_analysis_dir", "artifact_root", "path",
];

/**
 * Check if a suggested check appears to advertise unsafe actions.
 * Frontend safety filter - backend policy remains authoritative.
 */
const isCheckPotentiallyUnsafe = (check: IncidentSuggestedCheck): boolean => {
  // Check for forbidden patterns in check_id
  const checkIdLower = (check.check_id || "").toLowerCase();
  for (const pattern of FORBIDDEN_PATTERNS) {
    if (checkIdLower.includes(pattern)) {
      return true;
    }
  }
  // Check title for forbidden patterns
  const titleLower = (check.title || "").toLowerCase();
  for (const pattern of FORBIDDEN_PATTERNS) {
    if (titleLower.includes(pattern)) {
      return true;
    }
  }
  return false;
};

/**
 * Filter and validate suggested checks for safety.
 * Returns only checks that appear safe to include in the request.
 */
const filterSafeSuggestedChecks = (
  checks: IncidentSuggestedCheck[]
): IncidentSuggestedCheck[] => {
  return checks.filter((check) => {
    // Must have a non-empty check_id
    if (!check.check_id || check.check_id.trim() === "") {
      return false;
    }
    // Must not advertise unsafe actions
    if (isCheckPotentiallyUnsafe(check)) {
      return false;
    }
    return true;
  });
};

// =============================================================================
// Request Mapping
// =============================================================================

/**
 * Bound a string to a maximum length, truncating with ellipsis if needed.
 */
const boundString = (value: string, maxLength: number): string => {
  if (value.length <= maxLength) {
    return value;
  }
  return value.slice(0, maxLength);
};

/**
 * Build a diagnosis report from selected suggested checks.
 *
 * This is a pure mapping helper that:
 * - Filters for safety
 * - Bounds field lengths
 * - Enforces max check count
 * - Strips all unknown/action-control fields
 * - Sets fixed source to "manual_suggested_check"
 *
 * @param selectedChecks - Array of suggested checks selected by the operator
 * @returns Bounded diagnosis report containing only safe fields
 */
export const buildDiagnosisReportFromSelectedChecks = (
  selectedChecks: IncidentSuggestedCheck[]
): DiagnosisReport => {
  // Filter for safety first
  const safeChecks = filterSafeSuggestedChecks(selectedChecks);

  // Enforce max check count (take first N if over limit)
  const boundedChecks = safeChecks.slice(0, MAX_SELECTABLE_CHECKS);

  // Map to investigation format with bounded fields
  const investigations: DiagnosisInvestigation[] = boundedChecks.map((check) => ({
    check_id: boundString(check.check_id, MAX_CHECK_ID_LENGTH),
    title: boundString(check.title || "", MAX_TITLE_LENGTH),
    read_only: true,
    source: MANUAL_SUGGESTED_CHECK_SOURCE,
  }));

  return {
    diagnosis: {
      recommended_investigations: investigations,
    },
  };
};

// =============================================================================
// API Client
// =============================================================================

/**
 * Generate a safe run ID for manual diagnosis loop passes.
 * Format: manual-loop-{timestamp}
 */
export const generateManualRunId = (): string => {
  const now = new Date();
  const timestamp = now.toISOString().replace(/[:.]/g, "-").slice(0, 19);
  return `manual-loop-${timestamp}`;
};

/**
 * Run exactly one read-only diagnosis loop pass for an incident.
 *
 * This is a bounded UI seam - no raw artifact contents are returned,
 * no remediation actions are available, and no Kubernetes calls are made.
 *
 * @param incidentId - The incident ID to run diagnosis for
 * @param request - The one-pass request with run_id and diagnosis_report
 * @returns Bounded response with decision, counts, and artifact references
 * @throws Error on network failure or non-ok response
 */
export const runIncidentDiagnosisLoopOnePass = async (
  incidentId: string,
  request: DiagnosisLoopOnePassRequest
): Promise<DiagnosisLoopOnePassResponse> => {
  // Safety: Do not include forbidden fields
  const safeRequest = {
    run_id: request.run_id,
    diagnosis_report: request.diagnosis_report,
  };

  const response = await fetch(
    `/api/incidents/${encodeURIComponent(incidentId)}/diagnosis-loop/one-pass`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(safeRequest),
      cache: "no-store",
    }
  );

  if (!response.ok) {
    let message = response.statusText;
    try {
      const payload = await response.json();
      if (payload && typeof payload === "object" && "error" in payload) {
        message = String((payload as Record<string, unknown>).error);
      }
    } catch {
      // ignore
    }
    throw new Error(message || "Failed to run diagnosis loop");
  }

  const data = await response.json();
  return data as DiagnosisLoopOnePassResponse;
};

/**
 * Create a minimal safe diagnosis report for manual passes.
 * Uses empty recommended_investigations to prove the seam safely.
 */
export const createMinimalDiagnosisReport = (): DiagnosisReport => ({
  diagnosis: {
    recommended_investigations: [],
  },
});
