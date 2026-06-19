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
