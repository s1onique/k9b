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

  // Guard: detect HTML response (likely SPA index.html fallback) instead of JSON.
  // This catches routing misconfiguration where API requests fall through to the SPA.
  // Reuse contentType already captured above for logging.
  const htmlContentType = contentType || response.headers.get("Content-Type") || "";
  const isHtmlResponse = htmlContentType.startsWith("text/html") || htmlContentType.startsWith("application/html");
  if (isHtmlResponse) {
    // Read a preview of the body for debugging, capped at 200 chars to avoid noisy logs
    let bodyPreview = "<not captured>";
    try {
      const text = await response.text();
      bodyPreview = text.slice(0, 200).replace(/\n/g, " ");
      if (text.length > 200) bodyPreview += "...";
    } catch {
      // ignore
    }
    throw new Error(
      `Expected JSON from ${path} but received text/html. ` +
      `API route may be falling through to SPA index.html. ` +
      `Content-Type: ${contentType}, body preview: ${bodyPreview}`
    );
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
  // OPTIMIZED: Use include_batch_eligibility=true instead of include_status=true.
  // This computes only batch eligibility (batchExecutable) without triggering execution count
  // derivation via the super-fast path, making the initial load much faster.
  // The distinction:
  // - include_status=true: triggers execution_count_derivation_ms (~360s on large dirs)
  // - include_batch_eligibility=true: computes batchExecutable via batch eligibility scan only
  fetchJson<RunsListPayload>("/api/runs?include_batch_eligibility=true");

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

// Runtime status types
export type RuntimeStatusPayload = import("./components/runtime-status/runtimeStatusTypes").RuntimeStatusPayload;

// Fetch runtime status (log windows + PVC usage)
export const fetchRuntimeStatus = (): Promise<RuntimeStatusPayload> =>
  fetchJson<RuntimeStatusPayload>("/api/runtime-status");

// Debug diagnostics types
export type DebugDiagnosticsEnabledResponse = {
  debugExecutionDiagnosticsEnabled: boolean;
};

// Check if debug diagnostics are enabled on the backend
export const fetchDebugDiagnosticsEnabled = async (): Promise<DebugDiagnosticsEnabledResponse> => {
  const response = await fetch("/api/debug/diagnostics-enabled", {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch debug diagnostics status: ${response.statusText}`);
  }
  return (await response.json()) as DebugDiagnosticsEnabledResponse;
};

// Download execution state diagnostics bundle for a specific run
export const downloadExecutionStateDiagnostics = async (runId: string): Promise<Blob> => {
  const response = await fetch(`/api/debug/runs/${encodeURIComponent(runId)}/execution-state-bundle`, {
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
    throw new Error(message || "Failed to download diagnostics bundle");
  }

  return response.blob();
};

// ============================================================================
// Incident Snapshot API
// ============================================================================

export type IncidentSnapshotRequest = {
  namespace: string;
  since_hours?: number;
};

// ============================================================================
// Incident Candidate shape for frontend display
// ============================================================================

export type IncidentCandidateSignal = {
  source: string;
  reason: string;
  message: string;
};

export type IncidentCandidate = {
  candidate_id: string;
  namespace: string;
  object_kind: string;
  object_name: string;
  class: string;
  severity: string;
  signals: IncidentCandidateSignal[];
  evidence_needed: string[];
  raw_object_kind?: string | null;
};

export type IncidentSnapshotSummary = {
  total_pods: number;
  failing_pods_count: number;
  total_deployments: number;
  total_events: number;
  symptoms_count: number;
  candidates_count: number;
  incidents_promoted_count: number;
};

export type IncidentSnapshotBundle = {
  metadata: {
    bundle_id: string;
    captured_at: string;
    namespace: string;
    since_hours: number;
    context: string | null;
    total_pods: number;
    total_events: number;
    total_deployments: number;
    failing_pods_count: number;
    symptoms_count: number;
    candidates_count: number;
  };
  pods: Array<{
    name: string;
    namespace: string;
    phase: string;
    health_status: string;
    restart_count: number;
    node: string | null;
    image_refs: string[];
    reason: string | null;
    message: string | null;
    is_failing: boolean;
  }>;
  events: Array<{
    namespace: string;
    name: string;
    type: string;
    reason: string;
    message: string;
    involved_object_kind: string | null;
    involved_object_name: string | null;
    count: number;
    last_timestamp: string | null;
  }>;
  deployments: Array<{
    name: string;
    namespace: string;
    replicas: number;
    available_replicas: number;
    ready_replicas: number;
    updated_replicas: number;
    available: boolean;
  }>;
  symptoms: Array<{
    symptom_type: string;
    pod_name: string | null;
    message: string;
    severity: string;
  }>;
  collection_errors: string[];
  candidates: IncidentCandidate[];
};

export type IncidentSnapshotResponse = {
  bundle_id: string;
  captured_at: string;
  namespace: string;
  summary: IncidentSnapshotSummary;
  bundle?: IncidentSnapshotBundle;
  error?: string | null;
};

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
    let message = response.statusText;
    try {
      const payload = await response.json();
      if (payload && typeof payload === "object" && "error" in payload) {
        message = String((payload as Record<string, unknown>).error);
      }
    } catch {
      // ignore
    }
    throw new Error(message || "Failed to capture incident snapshot");
  }

  return (await response.json()) as IncidentSnapshotResponse;
};

// ============================================================================
// Incident Review Packet API
// ============================================================================

export type IncidentReviewPacketRequest = {
  bundle: Record<string, unknown>;
  format?: "markdown";
};

export type IncidentReviewPacketResponse = {
  bundle_id: string;
  packet: string;
  format: string;
  error?: string | null;
};

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
    let message = response.statusText;
    try {
      const payload = await response.json();
      if (payload && typeof payload === "object" && "error" in payload) {
        message = String((payload as Record<string, unknown>).error);
      }
    } catch {
      // ignore
    }
    throw new Error(message || "Failed to generate incident review packet");
  }

  return (await response.json()) as IncidentReviewPacketResponse;
};

// ============================================================================
// Incident List API (read-only)
// Incident aggregate root: owns case lifecycle truth
// ============================================================================

/**
 * Signal that contributed to an incident.
 * Read-only; provenance for diagnostic context.
 */
export type IncidentSignal = {
  source: string;
  reason: string;
  message: string;
  captured_at: string;
  run_id?: string | null;
  detector_id?: string | null;
  finding_id?: string | null;
  fingerprint?: string | null;
};

/**
 * Evidence artifact attached to an incident.
 * Read-only; links incident to artifact store.
 */
export type IncidentEvidenceLink = {
  incident_id: string;
  artifact_id: string;
  role: string;
  attached_at: string;
};

/**
 * Review packet state for an incident.
 * Replaces old review_packet_available + review_packet_id pattern.
 */
export type IncidentReviewPacketPayload = {
  status: string;
  id?: string | null;
  generated_at?: string | null;
  error_message?: string | null;
};

/**
 * Timeline event in an incident's lifecycle.
 * Read-only; append-only record of state transitions.
 */
export type IncidentEvent = {
  event_id: string;
  incident_id: string;
  event_type: string;
  actor: string;
  occurred_at: string;
  message: string;
  actor_id?: string | null;
  data?: Record<string, unknown> | null;
};

/**
 * Read-only suggested-check compatibility projection for incident detail views.
 * This is NOT a fully implemented persistence object.
 *
 * The status field indicates the mapping reliability:
 * - "suggested": Next-check artifact successfully mapped to incident
 * - "compatibility": Legacy artifact without reliable incident mapping
 * - "unknown": No mapping attempted or mapping failed
 *
 * Hard constraints:
 * - NO check execution
 * - NO manual promotion
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 */
export type IncidentSuggestedCheck = {
  check_id: string;
  title: string;
  rationale: string;
  source: string;
  risk_level: string | null;
  status: "suggested" | "compatibility" | "unknown";
  artifact_id: string | null;
  run_id: string | null;
};

/**
 * Incident summary payload - lightweight list view.
 * Uses latest_snapshot_bundle_id (not snapshot_bundle_id).
 * Uses review_packet object (not review_packet_available + review_packet_id).
 */
export type IncidentSummaryPayload = {
  incident_id: string;
  namespace: string;
  object_kind: string;
  object_name: string;
  raw_object_kind: string | null;
  candidate_class: string;
  severity: string;
  status: string;
  first_observed_at: string;
  last_observed_at: string;
  signal_count: number;
  evidence_count: number;
  latest_snapshot_bundle_id: string | null;
  review_packet: IncidentReviewPacketPayload;
  suppressed_reason: string | null;
  duplicate_of: string | null;
  resolved_at: string | null;
  resolution_notes: string | null;
};

/**
 * Incident detail payload - full case view.
 * Includes signals, evidence links, timeline, and suggested checks.
 * Run artifacts remain evidence provenance, not the primary case object.
 *
 * Note: suggested_checks is a read-only compatibility projection.
 * Currently returns empty list when no next-check-to-incident mapping exists.
 */
export type IncidentDetailPayload = IncidentSummaryPayload & {
  source_candidate_id: string;
  signals: IncidentSignal[];
  evidence_needed: string[];
  evidence_links: IncidentEvidenceLink[];
  events: IncidentEvent[];
  suggested_checks: IncidentSuggestedCheck[];
};

export type IncidentsListResponse = {
  incidents: IncidentSummaryPayload[];
  total: number;
};

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
    let message = response.statusText;
    try {
      const payload = await response.json();
      if (payload && typeof payload === "object" && "error" in payload) {
        message = String((payload as Record<string, unknown>).error);
      }
    } catch {
      // ignore
    }
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
    try {
      const payload = await response.json();
      if (payload && typeof payload === "object" && "error" in payload) {
        message = String((payload as Record<string, unknown>).error);
      }
    } catch {
      // ignore
    }
    throw new Error(message || "Failed to get incident");
  }

  return (await response.json()) as IncidentDetailPayload;
};
