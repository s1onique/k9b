/**
 * api.ts — Backend API client for the K9b diagnostics frontend.
 *
 * Exports: fetchRun, fetchFleet, fetchProposals, fetchNotifications,
 *         fetchClusterDetail, fetchRunsList, executeNextCheckCandidate,
 *         approveNextCheckCandidate, promoteDeterministicNextCheck,
 *         submitUsefulnessFeedback, runBatchExecution,
 *         performAlertmanagerSourceAction, promoteAlertmanagerSource,
 *         stopTrackingAlertmanagerSource.
 * Used by: All frontend components that load or mutate backend state.
 */

import type {
  AlertmanagerSourceActionRequest,
  AlertmanagerSourceActionResponse,
  ClusterDetailPayload,
  DeterministicNextCheckPromotionRequest,
  DeterministicNextCheckPromotionResponse,
  FleetPayload,
  NextCheckApprovalRequest,
  NextCheckApprovalResponse,
  NextCheckExecutionRequest,
  NextCheckExecutionResponse,
  NotificationsPayload,
  ProposalsPayload,
  RunPayload,
  UsefulnessFeedbackRequest,
  UsefulnessFeedbackResponse,
} from "./types";

type NextCheckExecutionError = Error & { blockingReason?: string | null };

interface FetchJsonOptions {
  headers?: Record<string, string>;
}

const fetchJson = async <T>(
  path: string,
  options?: FetchJsonOptions,
  extraInit?: RequestInit
): Promise<T> => {
  const init: RequestInit = { cache: "no-store", ...extraInit };
  if (options?.headers) {
    init.headers = { ...options.headers, ...extraInit?.headers as Record<string, string> };
  }
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${path}: ${response.statusText}`);
  }
  return response.json();
};

export const fetchRun = (
  runId?: string,
  options?: { clientRequestId?: string; signal?: AbortSignal }
): Promise<RunPayload> => {
  const suffix = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  const headers: Record<string, string> = {};
  if (options?.clientRequestId) {
    headers["X-K9B-Client-Request-Id"] = options.clientRequestId;
  }
  const init: RequestInit = { cache: "no-store" };
  if (options?.signal) {
    init.signal = options.signal;
  }
  return fetchJson<RunPayload>(`/api/run${suffix}`, { headers }, init);
};
export const fetchFleet = (): Promise<FleetPayload> => fetchJson<FleetPayload>("/api/fleet");
export const fetchProposals = (): Promise<ProposalsPayload> => fetchJson<ProposalsPayload>("/api/proposals");

export type NotificationsQuery = {
  kind?: string;
  cluster_label?: string;
  search?: string;
  limit?: number;
  page?: number;
};

export type NotificationsResponse = NotificationsPayload;

export const fetchNotifications = (
  query?: NotificationsQuery
): Promise<NotificationsResponse> => {
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

export type RunsListPayload = import("./types").RunsListPayload;

export const fetchRunsList = (): Promise<RunsListPayload> =>
  fetchJson<RunsListPayload>("/api/runs");

// Batch execution API
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

// Alertmanager source action APIs
export const performAlertmanagerSourceAction = async (
  request: AlertmanagerSourceActionRequest,
  runId: string
): Promise<AlertmanagerSourceActionResponse> => {
  // Use the run-scoped route: POST /api/runs/{run_id}/alertmanager-sources/{source_id}/action
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/alertmanager-sources/${encodeURIComponent(request.sourceId)}/action`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      action: request.action,
      clusterLabel: request.clusterLabel,
      reason: request.reason || undefined,
    }),
    cache: 'no-store',
  });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const payload = await response.json();
      if (payload && typeof payload === 'object' && 'error' in payload) {
        message = String((payload as Record<string, unknown>).error);
      }
    } catch {
      // ignore
    }
    throw new Error(message || `Failed to ${request.action} Alertmanager source`);
  }
  return (await response.json()) as AlertmanagerSourceActionResponse;
};

// Convenience wrappers for promote/disable actions
export const promoteAlertmanagerSource = async (
  request: AlertmanagerSourceActionRequest,
  runId: string
): Promise<AlertmanagerSourceActionResponse> => {
  return performAlertmanagerSourceAction({ ...request, action: 'promote' }, runId);
};

export const stopTrackingAlertmanagerSource = async (
  request: AlertmanagerSourceActionRequest,
  runId: string
): Promise<AlertmanagerSourceActionResponse> => {
  return performAlertmanagerSourceAction({ ...request, action: 'disable' }, runId);
};

// Alertmanager relevance feedback API
export type AlertmanagerRelevanceFeedbackRequest = import("./types").AlertmanagerRelevanceFeedbackRequest;
export type AlertmanagerRelevanceFeedbackResponse = import("./types").AlertmanagerRelevanceFeedbackResponse;

export const submitAlertmanagerRelevanceFeedback = async (
  request: AlertmanagerRelevanceFeedbackRequest
): Promise<AlertmanagerRelevanceFeedbackResponse> => {
  const response = await fetch("/api/alertmanager-relevance-feedback", {
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
    throw new Error(message || "Failed to submit Alertmanager relevance feedback");
  }
  return (await response.json()) as AlertmanagerRelevanceFeedbackResponse;
};
