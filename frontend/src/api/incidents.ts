/**
 * incidents.ts — API client for incident operations.
 *
 * Covers: listIncidents, getIncident, captureIncidentSnapshot,
 *         generateIncidentReviewPacket, getAutomaticDiagnosisReviewHandoff.
 *
 * GET operations use the generated OpenAPI client (IncidentsApi).
 * POST operations with request bodies use raw fetch to preserve
 * exact request format since API schema doesn't define request bodies.
 *
 * Auth/session behavior: Uses generated client configuration with credentials: "include"
 * to preserve existing browser auth (cookies, session headers).
 *
 * Hard constraints:
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 * - NO external tool invocation
 * - NO automatic scheduling
 * - NO background jobs
 */

// Re-export all incident types from the types module
export type {
  IncidentSignal,
  IncidentEvidenceLink,
  IncidentReviewPacketPayload,
  IncidentEvent,
  IncidentSuggestedCheck,
  AutomaticDiagnosisReviewPayload,
  IncidentSummaryPayload,
  EvidenceArtifact,
  DiagnosisLoopStatus,
  AutomaticDiagnosisLoopSummary,
  AutomaticDiagnosisReviewHandoffPayload,
  IncidentDetailPayload,
  IncidentsListResponse,
  IncidentSnapshotRequest,
  IncidentCandidateSignal,
  IncidentCandidate,
  IncidentSnapshotSummary,
  IncidentSnapshotBundle,
  IncidentSnapshotResponse,
  IncidentReviewPacketRequest,
  IncidentReviewPacketResponse,
} from "./incidents-types";

// Import types for local use
import type {
  IncidentSnapshotRequest,
  IncidentSnapshotResponse,
  IncidentReviewPacketRequest,
  IncidentReviewPacketResponse,
  IncidentDetailPayload,
  IncidentsListResponse,
  AutomaticDiagnosisReviewHandoffPayload,
} from "./incidents-types";

// Generated client imports
import { IncidentsApi } from "../generated/k9b-api";
import { createK9bApiConfiguration, normalizeGeneratedApiError } from "./generatedClient";

// Import extractErrorMessage for raw fetch error handling
import { extractErrorMessage } from "./client";

// =============================================================================
// API Factory
// =============================================================================

/**
 * Create an IncidentsApi client with the standard configuration.
 * Uses credentials: "include" to preserve session cookies.
 */
function createIncidentsApi(): IncidentsApi {
  return new IncidentsApi(createK9bApiConfiguration());
}

// =============================================================================
// GET Operations (use generated client)
// =============================================================================

/**
 * List incidents from the in-memory store.
 *
 * @param status - Optional status filter (e.g., "open", "collecting_evidence")
 */
export const listIncidents = async (status?: string): Promise<IncidentsListResponse> => {
  try {
    const api = createIncidentsApi();
    const result = await api.listIncidents({ status });
    return result as IncidentsListResponse;
  } catch (error) {
    throw await normalizeGeneratedApiError(error);
  }
};

/**
 * Get a specific incident by ID.
 *
 * @param incidentId - The incident ID to look up
 */
export const getIncident = async (incidentId: string): Promise<IncidentDetailPayload> => {
  try {
    const api = createIncidentsApi();
    const result = await api.getIncidentDetail({ incidentId });
    return result as IncidentDetailPayload;
  } catch (error) {
    // Preserve 404 not-found behavior
    const normalizedError = await normalizeGeneratedApiError(error);
    if (normalizedError.message.includes("404") || normalizedError.message.includes("Not Found")) {
      throw new Error("Incident not found");
    }
    throw normalizedError;
  }
};

/**
 * Get automatic diagnosis review handoff for an incident.
 *
 * This is a read-only endpoint that provides a sanitized markdown handoff
 * suitable for human/ChatGPT review.
 *
 * @param incidentId - The incident ID to look up
 */
export const getAutomaticDiagnosisReviewHandoff = async (
  incidentId: string
): Promise<AutomaticDiagnosisReviewHandoffPayload> => {
  try {
    const api = createIncidentsApi();
    const result = await api.getIncidentDiagnosisReviewHandoff({ incidentId });
    return result as AutomaticDiagnosisReviewHandoffPayload;
  } catch (error) {
    throw await normalizeGeneratedApiError(error);
  }
};

// =============================================================================
// POST Operations (use raw fetch - API schema doesn't define request bodies)
// =============================================================================

/**
 * Capture an incident snapshot.
 *
 * Uses raw fetch because the generated client doesn't have request body support
 * (API schema doesn't define request body for this endpoint).
 *
 * @param request - Snapshot request with namespace and optional time window
 */
export const captureIncidentSnapshot = async (
  request: IncidentSnapshotRequest
): Promise<IncidentSnapshotResponse> => {
  const response = await fetch("/api/incidents/snapshot", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    cache: "no-store",
  });

  if (!response.ok) {
    const message = await extractErrorMessage(response);
    throw new Error(message || "Failed to capture incident snapshot");
  }

  return (await response.json()) as IncidentSnapshotResponse;
};

/**
 * Generate an incident review packet from a snapshot bundle.
 *
 * Uses raw fetch because the generated client doesn't have request body support
 * (API schema doesn't define request body for this endpoint).
 *
 * @param request - Review packet request with bundle data
 */
export const generateIncidentReviewPacket = async (
  request: IncidentReviewPacketRequest
): Promise<IncidentReviewPacketResponse> => {
  const response = await fetch("/api/incidents/review-packet", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    cache: "no-store",
  });

  if (!response.ok) {
    const message = await extractErrorMessage(response);
    throw new Error(message || "Failed to generate incident review packet");
  }

  return (await response.json()) as IncidentReviewPacketResponse;
};
