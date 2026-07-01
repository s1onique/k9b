/**
 * api.ts — Backend API client for the K9b diagnostics frontend.
 *
 * This file is a thin compatibility façade that re-exports from focused modules.
 * New code should import directly from the submodules:
 *
 *   import { fetchRun, fetchFleet } from "./api/runs";
 *   import { listIncidents, getIncident } from "./api/incidents";
 *   import { performAlertmanagerSourceAction } from "./api/alertmanager";
 *   import { fetchJson, fetchRuntimeStatus } from "./api/client";
 *
 * Exported symbols (backward-compatible):
 *   fetchRun, fetchFleet, fetchProposals, fetchNotifications,
 *   fetchClusterDetail, fetchRunsList, executeNextCheckCandidate,
 *   approveNextCheckCandidate, promoteDeterministicNextCheck,
 *   submitUsefulnessFeedback, runBatchExecution,
 *   performAlertmanagerSourceAction, promoteAlertmanagerSource,
 *   stopTrackingAlertmanagerSource, submitAlertmanagerRelevanceFeedback,
 *   fetchRuntimeStatus, fetchDebugDiagnosticsEnabled,
 *   downloadExecutionStateDiagnostics,
 *   captureIncidentSnapshot, generateIncidentReviewPacket,
 *   listIncidents, getIncident, getAutomaticDiagnosisReviewHandoff,
 *   + incident-related types
 *
 * Used by: All frontend components that load or mutate backend state.
 */

// =============================================================================
// Re-exports from client module
// =============================================================================

export {
  fetchJson,
  logFetchPhase,
  type FetchPhaseTiming,
  type FetchRunInit,
  fetchRuntimeStatus,
  fetchDebugDiagnosticsEnabled,
  downloadExecutionStateDiagnostics,
  type RuntimeStatusPayload,
  type DebugDiagnosticsEnabledResponse,
} from "./api/client";

export { extractErrorMessage } from "./api/client";

export type { FetchJsonOptions } from "./api/client";

// =============================================================================
// Re-exports from incidents module
// =============================================================================

export {
  listIncidents,
  getIncident,
  captureIncidentSnapshot,
  generateIncidentReviewPacket,
  getAutomaticDiagnosisReviewHandoff,
} from "./api/incidents";

export type {
  // List/Detail types
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
  // Snapshot types
  IncidentSnapshotRequest,
  IncidentCandidateSignal,
  IncidentCandidate,
  IncidentSnapshotSummary,
  IncidentSnapshotBundle,
  IncidentSnapshotResponse,
  // Review packet types
  IncidentReviewPacketRequest,
  IncidentReviewPacketResponse,
} from "./api/incidents-types";

// =============================================================================
// Re-exports from alertmanager module
// =============================================================================

export {
  performAlertmanagerSourceAction,
  promoteAlertmanagerSource,
  stopTrackingAlertmanagerSource,
  submitAlertmanagerRelevanceFeedback,
} from "./api/alertmanager";

// =============================================================================
// Runs API (fetchRun, fetchFleet, fetchProposals, etc.)
// =============================================================================

import { fetchJson } from "./api/client";
import type {
  RunPayload,
  FleetPayload,
  ProposalsPayload,
  NotificationsPayload,
  ClusterDetailPayload,
  RunsListPayload,
  BatchExecutionRequest,
  BatchExecutionResponse,
} from "./types";

export const fetchRun = (
  runId?: string,
  options?: { clientRequestId?: string; signal?: AbortSignal }
): Promise<RunPayload> => {
  const suffix = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  const headers: Record<string, string> = {};
  if (options?.clientRequestId) {
    headers["X-K9B-Client-Request-Id"] = options.clientRequestId;
  }
  const init = { cache: "no-store" };
  if (options?.signal) {
    init.signal = options.signal;
  }
  if (runId) {
    (init as Record<string, unknown>).__runId = runId;
  }
  (init as Record<string, unknown>).__requestKind = "run-detail";
  return fetchJson<RunPayload>(`/api/run${suffix}`, { headers }, init as Parameters<typeof fetchJson>[2]);
};

export const fetchFleet = (): Promise<FleetPayload> => fetchJson<FleetPayload>("/api/fleet");
export const fetchProposals = (): Promise<ProposalsPayload> =>
  fetchJson<ProposalsPayload>("/api/proposals");

export type NotificationsQuery = {
  kind?: string;
  cluster_label?: string;
  search?: string;
  limit?: number;
  page?: number;
};

export type NotificationsResponse = NotificationsPayload;

export const fetchNotifications = (query?: NotificationsQuery): Promise<NotificationsResponse> => {
  const params = new URLSearchParams();
  if (query?.kind) {
    params.append("kind", query.kind);
  }
  if (query?.cluster_label) {
    params.append("cluster_label", query.cluster_label);
  }
  if (query?.search) {
    params.append("search", query.search);
  }
  if (query?.limit) {
    params.append("limit", String(query.limit));
  }
  if (query?.page) {
    params.append("page", String(query.page));
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson<NotificationsResponse>(`/api/notifications${suffix}`);
};

export const fetchClusterDetail = (clusterLabel?: string): Promise<ClusterDetailPayload> => {
  const suffix = clusterLabel ? `?cluster_label=${encodeURIComponent(clusterLabel)}` : "";
  return fetchJson<ClusterDetailPayload>(`/api/cluster-detail${suffix}`);
};

// =============================================================================
// Next-check execution APIs
// =============================================================================

import type {
  NextCheckExecutionRequest,
  NextCheckExecutionResponse,
  NextCheckApprovalRequest,
  NextCheckApprovalResponse,
  DeterministicNextCheckPromotionRequest,
  DeterministicNextCheckPromotionResponse,
  UsefulnessFeedbackRequest,
  UsefulnessFeedbackResponse,
} from "./types";

type NextCheckExecutionError = Error & { blockingReason?: string | null };

export const executeNextCheckCandidate = async (
  request: NextCheckExecutionRequest
): Promise<NextCheckExecutionResponse> => {
  const response = await fetch("/api/next-check-execution", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    cache: "no-store",
  });
  if (!response.ok) {
    let message = response.statusText;
    let blockingReason: string | null | undefined;
    try {
      const payload = await response.json();
      if (payload && typeof payload === "object") {
        if ("error" in payload) {
          message = String((payload as Record<string, unknown>).error);
        }
        if ("blockingReason" in payload) {
          blockingReason = (payload as Record<string, unknown>).blockingReason as string | null;
        }
      }
    } catch {
      // ignore
    }
    const error = new Error(
      message || "Failed to execute next-check candidate"
    ) as NextCheckExecutionError;
    error.blockingReason = blockingReason ?? null;
    throw error;
  }
  const data = await response.json();
  return data as NextCheckExecutionResponse;
};

export const approveNextCheckCandidate = async (
  request: NextCheckApprovalRequest
): Promise<NextCheckApprovalResponse> => {
  const response = await fetch("/api/next-check-approval", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    cache: "no-store",
  });
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
    throw new Error(message || "Failed to approve next-check candidate");
  }
  const data = await response.json();
  return data as NextCheckApprovalResponse;
};

export const promoteDeterministicNextCheck = async (
  request: DeterministicNextCheckPromotionRequest
): Promise<DeterministicNextCheckPromotionResponse> => {
  const response = await fetch("/api/deterministic-next-check/promote", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    cache: "no-store",
  });
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
    throw new Error(message || "Failed to promote deterministic next check");
  }
  return (await response.json()) as DeterministicNextCheckPromotionResponse;
};

export const submitUsefulnessFeedback = async (
  request: UsefulnessFeedbackRequest
): Promise<UsefulnessFeedbackResponse> => {
  const response = await fetch("/api/next-check-execution-usefulness", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    cache: "no-store",
  });
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
    throw new Error(message || "Failed to submit usefulness feedback");
  }
  return (await response.json()) as UsefulnessFeedbackResponse;
};

// =============================================================================
// Runs list API
// =============================================================================

export type RunsListPayload = import("./types").RunsListPayload;

export const fetchRunsList = (): Promise<RunsListPayload> =>
  // OPTIMIZED: Use include_batch_eligibility=true instead of include_status=true.
  // This computes only batch eligibility (batchExecutable) without triggering execution count
  // derivation via the super-fast path, making the initial load much faster.
  fetchJson<RunsListPayload>("/api/runs?include_batch_eligibility=true");

// =============================================================================
// Batch execution API
// =============================================================================

export type BatchExecutionRequest = import("./types").BatchExecutionRequest;
export type BatchExecutionResponse = import("./types").BatchExecutionResponse;

export const runBatchExecution = async (
  request: BatchExecutionRequest
): Promise<BatchExecutionResponse> => {
  const response = await fetch("/api/run-batch-next-check-execution", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to run batch execution");
  }

  return (await response.json()) as BatchExecutionResponse;
};

// =============================================================================
// Alertmanager relevance feedback types (re-exported)
// =============================================================================

export type AlertmanagerRelevanceFeedbackRequest = import("./types").AlertmanagerRelevanceFeedbackRequest;
export type AlertmanagerRelevanceFeedbackResponse = import("./types").AlertmanagerRelevanceFeedbackResponse;

// =============================================================================
// Incident Diagnosis Loop API Types
// Re-exported from incidentDiagnosisLoop.ts for consumer convenience
// =============================================================================

export type {
  DiagnosisInvestigation,
  DiagnosisSection,
  DiagnosisReport,
  DiagnosisLoopOnePassRequest,
  DiagnosisArtifactRef,
  DiagnosisArtifacts,
  DiagnosisSafetyMetadata,
  DiagnosisLoopOnePassResponse,
} from "./api/incidentDiagnosisLoop";
