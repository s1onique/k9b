/**
 * incidents.ts — API client for incident operations.
 *
 * Covers: listIncidents, getIncident, captureIncidentSnapshot,
 *         generateIncidentReviewPacket, getAutomaticDiagnosisReviewHandoff.
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

// Import extractErrorMessage helper
import { extractErrorMessage } from "./client";

// =============================================================================
// API Calls
// =============================================================================

/**
 * List incidents from the in-memory store.
 *
 * Hard constraints:
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 * - NO external tool invocation
 * - NO persistence (in-memory only)
 *
 * @param status - Optional status filter (e.g., "open", "collecting_evidence")
 */
export const listIncidents = async (status?: string): Promise<IncidentsListResponse> => {
  const params = new URLSearchParams();
  if (status) {
    params.append("status", status);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";

  const response = await fetch(`/api/incidents${suffix}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    const message = await extractErrorMessage(response);
    throw new Error(message || "Failed to list incidents");
  }

  return (await response.json()) as IncidentsListResponse;
};

/**
 * Get a specific incident by ID.
 *
 * @param incidentId - The incident ID to look up
 */
export const getIncident = async (incidentId: string): Promise<IncidentDetailPayload> => {
  const response = await fetch(`/api/incidents/${encodeURIComponent(incidentId)}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    let message = response.statusText;
    if (response.status === 404) {
      throw new Error("Incident not found");
    }
    const extracted = await extractErrorMessage(response);
    if (extracted !== response.statusText) {
      message = extracted;
    }
    throw new Error(message || "Failed to get incident");
  }

  return (await response.json()) as IncidentDetailPayload;
};

/**
 * Capture an incident snapshot.
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

/**
 * Get automatic diagnosis review handoff for an incident.
 *
 * This is a read-only endpoint that provides a sanitized markdown handoff
 * suitable for human/ChatGPT review. It does not expose raw packet contents,
 * absolute paths, secrets, or action controls.
 *
 * @param incidentId - The incident ID to look up
 */
export const getAutomaticDiagnosisReviewHandoff = async (
  incidentId: string
): Promise<AutomaticDiagnosisReviewHandoffPayload> => {
  const response = await fetch(
    `/api/incidents/${encodeURIComponent(incidentId)}/automatic-diagnosis-review/handoff`,
    {
      cache: "no-store",
    }
  );

  if (!response.ok) {
    const message = await extractErrorMessage(response);
    throw new Error(message || "Failed to get review handoff");
  }

  return (await response.json()) as AutomaticDiagnosisReviewHandoffPayload;
};
