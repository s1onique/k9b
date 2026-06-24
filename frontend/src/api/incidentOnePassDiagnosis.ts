/**
 * incidentOnePassDiagnosis.ts — API client for incident one-pass diagnosis service.
 *
 * Runs exactly one read-only diagnosis pass for an incident using the
 * one-pass diagnosis service route: POST /api/incidents/{incident_id}/one-pass-diagnosis
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

// =============================================================================
// Types
// =============================================================================

/**
 * Response from one-pass diagnosis service.
 * Bounded shape - no freeform fields, no raw artifact contents.
 */
export type IncidentOnePassDiagnosisResponse = {
  schema_version: string;
  incident_id: string;
  run_id: string;
  category: string;
  root_cause: string;
  confidence: string;
  description: string;
  evidence_refs: string[];
  read_only: boolean;
  allowed_actions: string[];
  forbidden_actions_observed: string[];
  mutation_proposals_observed: string[];
  decision: string;
  checks_run: number;
  next_checks: NextCheck[];
  artifact_written: boolean;
  artifact_name: string | null;
  error: string | null;
};

/**
 * Next check from the diagnosis service.
 * Bounded shape - no paths, no action-control fields.
 */
export type NextCheck = {
  check_id?: string;
  title?: string;
  read_only?: boolean;
  source?: string;
};

/**
 * Request options for running one-pass diagnosis.
 */
export type IncidentOnePassDiagnosisOptions = {
  /** Optional run ID for tracking. Auto-generated if not provided. */
  runId?: string;
};

// =============================================================================
// Constants
// =============================================================================

/** Maximum error message length for safety. */
const BOUND_ERROR_MAX_LENGTH = 500;

// =============================================================================
// Request Building
// =============================================================================

/**
 * Generate a safe run ID for one-pass diagnosis.
 * Format: one-pass-{timestamp}
 */
export const generateOnePassRunId = (): string => {
  const now = new Date();
  const timestamp = now.toISOString().replace(/[:.]/g, "-").slice(0, 19);
  return `one-pass-${timestamp}`;
};

/**
 * Build a minimal request body for one-pass diagnosis.
 * The incident_id is taken from the URL path, not the body.
 */
export const buildOnePassDiagnosisRequest = (
  options?: IncidentOnePassDiagnosisOptions
): Record<string, unknown> => {
  const body: Record<string, unknown> = {};
  if (options?.runId) {
    body.run_id = options.runId;
  }
  return body;
};

// =============================================================================
// Safety Validation
// =============================================================================

/**
 * Forbidden field patterns that indicate unsafe/mutation actions.
 * These are checked in responses to fail closed on safety violations.
 */
const FORBIDDEN_ACTION_PATTERNS = [
  "mutate",
  "delete",
  "patch",
  "scale",
  "restart",
  "rollout",
  "apply",
  "remediate",
  "kubectl",
  "exec",
  "run",
  "execute",
  "external_analysis_dir",
  "external_analysis_path",
  "artifact_root",
  "fs_path",
  "path",
];

/**
 * Check if a next check appears to advertise unsafe actions.
 * Used for safety filtering in the UI.
 */
const isNextCheckPotentiallyUnsafe = (check: NextCheck): boolean => {
  const checkIdLower = (check.check_id || "").toLowerCase();
  for (const pattern of FORBIDDEN_ACTION_PATTERNS) {
    if (checkIdLower.includes(pattern)) {
      return true;
    }
  }
  const titleLower = (check.title || "").toLowerCase();
  for (const pattern of FORBIDDEN_ACTION_PATTERNS) {
    if (titleLower.includes(pattern)) {
      return true;
    }
  }
  return false;
};

/**
 * Safety validation result for one-pass diagnosis response.
 */
export type OnePassSafetyValidation = {
  isValid: boolean;
  readOnlyViolation: boolean;
  allowedActionsViolation: boolean;
  mutationProposalsViolation: boolean;
  nextChecksViolation: boolean;
  unsafeNextChecks: NextCheck[];
};

/**
 * Check if a value is an array, returning empty array on null/undefined/non-array.
 * Used for fail-closed safety validation.
 */
const toArray = <T>(value: T[] | null | undefined): T[] => {
  if (Array.isArray(value)) {
    return value;
  }
  return [];
};

/**
 * Validate that a one-pass diagnosis response passes safety checks.
 * Returns validation result with violation details.
 * Fails closed on missing or malformed array fields.
 */
export const validateOnePassSafety = (
  response: IncidentOnePassDiagnosisResponse
): OnePassSafetyValidation => {
  const readOnlyViolation = response.read_only !== true;

  // Treat non-array as safety violation (fail closed)
  const allowedActions = toArray(response.allowed_actions);
  const allowedActionsViolation =
    !Array.isArray(response.allowed_actions) || allowedActions.length > 0;

  // Treat non-array as safety violation (fail closed)
  const mutationProposals = toArray(response.mutation_proposals_observed);
  const mutationProposalsViolation =
    !Array.isArray(response.mutation_proposals_observed) || mutationProposals.length > 0;

  // Treat non-array as safety violation (fail closed)
  const nextChecksIsArray = Array.isArray(response.next_checks);
  const nextChecks = toArray(response.next_checks);
  const nextChecksViolation = !nextChecksIsArray;
  const unsafeNextChecks = nextChecks.filter(isNextCheckPotentiallyUnsafe);

  const isValid =
    !readOnlyViolation &&
    !allowedActionsViolation &&
    !mutationProposalsViolation &&
    !nextChecksViolation &&
    unsafeNextChecks.length === 0;

  return {
    isValid,
    readOnlyViolation,
    allowedActionsViolation,
    mutationProposalsViolation,
    nextChecksViolation,
    unsafeNextChecks,
  };
};

// =============================================================================
// API Client
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

/**
 * Run one read-only diagnosis pass for an incident.
 *
 * This calls POST /api/incidents/{incident_id}/one-pass-diagnosis
 * which runs the incident diagnosis service in one-pass mode.
 *
 * The response must pass safety validation before being presented as valid.
 *
 * @param incidentId - The incident ID to run diagnosis for
 * @param options - Optional run ID for tracking
 * @returns Bounded response with diagnosis outcome
 * @throws Error on network failure, malformed JSON, or non-ok response
 */
export const runIncidentOnePassDiagnosis = async (
  incidentId: string,
  options?: IncidentOnePassDiagnosisOptions
): Promise<IncidentOnePassDiagnosisResponse> => {
  // Build minimal request body
  const requestBody = buildOnePassDiagnosisRequest(options);

  let response: Response;
  try {
    response = await fetch(
      `/api/incidents/${encodeURIComponent(incidentId)}/one-pass-diagnosis`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody),
        cache: "no-store",
      }
    );
  } catch (networkError) {
    throw new Error(
      boundErrorMessage(
        networkError instanceof Error ? networkError.message : String(networkError)
      ) || "Network error during one-pass diagnosis"
    );
  }

  if (!response.ok) {
    let message = response.statusText;
    try {
      const payload = await response.json();
      if (payload && typeof payload === "object" && "error" in payload) {
        message = String((payload as Record<string, unknown>).error);
      }
    } catch {
      // ignore - fall back to statusText
    }
    throw new Error(boundErrorMessage(message) || "Failed to run one-pass diagnosis");
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch (jsonError) {
    throw new Error(
      boundErrorMessage(
        jsonError instanceof Error ? jsonError.message : String(jsonError)
      ) || "Malformed JSON in response"
    );
  }
  return data as IncidentOnePassDiagnosisResponse;
};
