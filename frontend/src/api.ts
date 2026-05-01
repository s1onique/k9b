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

/**
 * Debug logging helper - gated by ?debugUi query parameter.
 * Safe to call in tests (handles window undefined).
 */
const DEBUG_UI_ENABLED = (): boolean => {
  if (typeof window === "undefined") return false;
  const params = new URLSearchParams(window.location.search);
  return params.has("debugUi");
};

/**
 * Phase timing instrumentation for fetch operations.
 * Logs to console when ?debugUi is enabled.
 * Applies to all API calls (not just fetchRun).
 */
interface FetchPhaseTiming {
  path: string;
  method?: string;
  runId?: string;
  clientRequestId?: string;
  requestKind?: string;
  phase: string;
  elapsedMs: number;
  status?: number;
  aborted?: boolean;
  contentLength?: string;
  contentType?: string;
  bodyTextLength?: number;
}

const logFetchPhase = (timing: FetchPhaseTiming): void => {
  if (!DEBUG_UI_ENABLED()) return;
  const prefix = "[api:http]";
  const { path, method, runId, clientRequestId, requestKind, phase, elapsedMs, status, aborted, contentLength, contentType, bodyTextLength } = timing;
  const parts: string[] = [];
  parts.push(path);
  if (method) parts.push(`method=${method}`);
  if (runId) parts.push(`runId=${runId}`);
  if (clientRequestId) parts.push(`clientRequestId=${clientRequestId}`);
  if (requestKind) parts.push(`kind=${requestKind}`);
  parts.push(phase);
  parts.push(`elapsedMs=${elapsedMs.toFixed(1)}`);
  if (status !== undefined) parts.push(`status=${status}`);
  if (aborted !== undefined) parts.push(`aborted=${aborted}`);
  if (contentLength) parts.push(`content-length=${contentLength}`);
  if (contentType) parts.push(`content-type=${contentType}`);
  if (bodyTextLength !== undefined) parts.push(`bodyTextLength=${bodyTextLength}`);
  console.info(prefix, parts.join(" "));
};

const fetchJson = async <T>(
  path: string,
  options?: FetchJsonOptions,
  extraInit?: RequestInit
): Promise<T> => {
  const headers = options?.headers || {};
  const clientRequestId = headers["X-K9B-Client-Request-Id"];
  
  // CRITICAL: Destructure debug-only fields FIRST before building RequestInit.
  // __runId and __requestKind are for debug logging only - they are not valid
  // RequestInit fields and must NOT be passed to the browser's fetch().
  const { __runId, __requestKind, ...cleanExtraInit } = extraInit || {};
  
  // Extract runId and requestKind for debug logging BEFORE building init
  const runId = __runId;
  const requestKind = __requestKind;
  
  // Build init from cleanExtraInit only (debug fields already removed)
  const init: RequestInit = { cache: "no-store", ...cleanExtraInit };
  if (options?.headers) {
    init.headers = { ...options.headers, ...cleanExtraInit?.headers as Record<string, string> };
  }
  // NOTE: We no longer set Connection: close here - that header is forbidden in fetch.
  // Instead, we rely on the backend to set Connection: close in responses via _send_json().
  
  const startTime = performance.now();
  logFetchPhase({ path, runId, clientRequestId, requestKind, phase: "start", elapsedMs: 0, status: undefined, aborted: undefined });
  
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (err) {
    const elapsed = performance.now() - startTime;
    logFetchPhase({ path, runId, clientRequestId, requestKind, phase: "failed", elapsedMs: elapsed });
    throw err;
  }
  
  const headersTime = performance.now();
  const elapsedHeaders = headersTime - startTime;
  const contentLength = response.headers.get("Content-Length") || undefined;
  const contentType = response.headers.get("Content-Type") || undefined;
  logFetchPhase({ path, runId, clientRequestId, requestKind, phase: "headers-received", elapsedMs: elapsedHeaders, status: response.status, aborted: false, contentLength, contentType });
  
  if (!response.ok) {
    const elapsed = performance.now() - startTime;
    logFetchPhase({ path, runId, clientRequestId, requestKind, phase: "non-ok-response", elapsedMs: elapsed, status: response.status, aborted: false });
    throw new Error(`Failed to fetch ${path}: ${response.statusText}`);
  }
  
  // Use response.text() + JSON.parse() to distinguish phases
  // This helps identify whether the delay is in body download or JSON parsing
  const textStartTime = performance.now();
  logFetchPhase({ path, runId, clientRequestId, requestKind, phase: "text-start", elapsedMs: textStartTime - startTime, status: response.status, aborted: false });
  
  let text: string;
  try {
    text = await response.text();
  } catch (err) {
    const elapsed = performance.now() - startTime;
    logFetchPhase({ path, runId, clientRequestId, requestKind, phase: "text-failed", elapsedMs: elapsed, status: response.status, aborted: false });
    throw new Error(`Failed to read response body: ${err}`);
  }
  
  const textDoneTime = performance.now();
  const bodyTextLength = text.length;
  logFetchPhase({ path, runId, clientRequestId, requestKind, phase: "text-done", elapsedMs: textDoneTime - startTime, status: response.status, aborted: false, bodyTextLength });
  
  const jsonStartTime = performance.now();
  logFetchPhase({ path, runId, clientRequestId, requestKind, phase: "json-parse-start", elapsedMs: jsonStartTime - startTime, status: response.status, aborted: false, bodyTextLength });
  
  let data: T;
  try {
    data = JSON.parse(text) as T;
  } catch (err) {
    const elapsed = performance.now() - startTime;
    logFetchPhase({ path, runId, clientRequestId, requestKind, phase: "json-parse-failed", elapsedMs: elapsed, status: response.status, aborted: false, bodyTextLength });
    throw new Error(`Failed to parse JSON response: ${err}`);
  }
  
  const doneTime = performance.now();
  logFetchPhase({ path, runId, clientRequestId, requestKind, phase: "done", elapsedMs: doneTime - startTime, status: response.status, aborted: false, bodyTextLength });
  
  return data;
};

// Extended RequestInit to carry runId and requestKind for debug logging
interface FetchRunInit extends RequestInit {
  __runId?: string;
  __requestKind?: string;
}

export const fetchRun = (
  runId?: string,
  options?: { clientRequestId?: string; signal?: AbortSignal }
): Promise<RunPayload> => {
  const suffix = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  const headers: Record<string, string> = {};
  if (options?.clientRequestId) {
    headers["X-K9B-Client-Request-Id"] = options.clientRequestId;
  }
  const init: FetchRunInit = { cache: "no-store" };
  if (options?.signal) {
    init.signal = options.signal;
  }
  // Pass runId and requestKind through for debug logging
  if (runId) {
    init.__runId = runId;
  }
  // Mark this as run-detail for phase logging
  init.__requestKind = "run-detail";
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
