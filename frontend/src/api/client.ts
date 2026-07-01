/**
 * client.ts — Shared fetch/request helpers for the K9b API client.
 *
 * Provides fetchJson with JSON parsing, error handling, and debug phase logging.
 * All HTTP-level concerns live here so API modules stay focused on business logic.
 */

import type { RuntimeStatusPayload } from "../components/runtime-status/runtimeStatusTypes";

// =============================================================================
// Types
// =============================================================================

interface FetchJsonOptions {
  headers?: Record<string, string>;
}

/**
 * Phase timing instrumentation for fetch operations.
 * Logs to console when ?debugUi is enabled.
 */
export interface FetchPhaseTiming {
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

// Extended RequestInit to carry runId and requestKind for debug logging
export interface FetchRunInit extends RequestInit {
  __runId?: string;
  __requestKind?: string;
}

// =============================================================================
// Debug Logging
// =============================================================================

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
 * Log a fetch phase timing event.
 * Only logs when ?debugUi query parameter is present.
 */
export const logFetchPhase = (timing: FetchPhaseTiming): void => {
  if (!DEBUG_UI_ENABLED()) return;
  const prefix = "[api:http]";
  const {
    path,
    method,
    runId,
    clientRequestId,
    requestKind,
    phase,
    elapsedMs,
    status,
    aborted,
    contentLength,
    contentType,
    bodyTextLength,
  } = timing;
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

// =============================================================================
// Core Fetch
// =============================================================================

/**
 * Fetch JSON from a path, with timing instrumentation and HTML guard.
 *
 * CRITICAL: __runId and __requestKind in extraInit are debug-only fields.
 * They are NOT valid RequestInit fields and must NOT be passed to fetch().
 */
export const fetchJson = async <T>(
  path: string,
  options?: FetchJsonOptions,
  extraInit?: FetchRunInit
): Promise<T> => {
  const headers = options?.headers || {};
  const clientRequestId = headers["X-K9B-Client-Request-Id"];

  // Extract debug-only fields BEFORE building RequestInit.
  const { __runId, __requestKind, ...cleanExtraInit } = extraInit || {};
  const runId = __runId;
  const requestKind = __requestKind;

  // Build init from cleanExtraInit only (debug fields removed)
  const init: RequestInit = { cache: "no-store", ...cleanExtraInit };
  if (options?.headers) {
    init.headers = { ...options.headers, ...cleanExtraInit?.headers as Record<string, string> };
  }

  const startTime = performance.now();
  logFetchPhase({ path, runId, clientRequestId, requestKind, phase: "start", elapsedMs: 0 });

  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (err) {
    const elapsed = performance.now() - startTime;
    logFetchPhase({ path, runId, clientRequestId, requestKind, phase: "failed", elapsedMs: elapsed });
    throw err;
  }

  const headersTime = performance.now();
  const contentLength = response.headers.get("Content-Length") || undefined;
  const contentType = response.headers.get("Content-Type") || undefined;
  logFetchPhase({
    path,
    runId,
    clientRequestId,
    requestKind,
    phase: "headers-received",
    elapsedMs: headersTime - startTime,
    status: response.status,
    aborted: false,
    contentLength,
    contentType,
  });

  if (!response.ok) {
    const elapsed = performance.now() - startTime;
    logFetchPhase({
      path,
      runId,
      clientRequestId,
      requestKind,
      phase: "non-ok-response",
      elapsedMs: elapsed,
      status: response.status,
      aborted: false,
    });
    throw new Error(`Failed to fetch ${path}: ${response.statusText}`);
  }

  // Guard: detect HTML response (likely SPA index.html fallback) instead of JSON.
  const htmlContentType = contentType || response.headers.get("Content-Type") || "";
  const isHtmlResponse =
    htmlContentType.startsWith("text/html") || htmlContentType.startsWith("application/html");
  if (isHtmlResponse) {
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
  const textStartTime = performance.now();
  logFetchPhase({
    path,
    runId,
    clientRequestId,
    requestKind,
    phase: "text-start",
    elapsedMs: textStartTime - startTime,
    status: response.status,
    aborted: false,
  });

  let text: string;
  try {
    text = await response.text();
  } catch (err) {
    const elapsed = performance.now() - startTime;
    logFetchPhase({
      path,
      runId,
      clientRequestId,
      requestKind,
      phase: "text-failed",
      elapsedMs: elapsed,
      status: response.status,
      aborted: false,
    });
    throw new Error(`Failed to read response body: ${err}`);
  }

  const textDoneTime = performance.now();
  const bodyTextLength = text.length;
  logFetchPhase({
    path,
    runId,
    clientRequestId,
    requestKind,
    phase: "text-done",
    elapsedMs: textDoneTime - startTime,
    status: response.status,
    aborted: false,
    bodyTextLength,
  });

  const jsonStartTime = performance.now();
  logFetchPhase({
    path,
    runId,
    clientRequestId,
    requestKind,
    phase: "json-parse-start",
    elapsedMs: jsonStartTime - startTime,
    status: response.status,
    aborted: false,
    bodyTextLength,
  });

  let data: T;
  try {
    data = JSON.parse(text) as T;
  } catch (err) {
    const elapsed = performance.now() - startTime;
    logFetchPhase({
      path,
      runId,
      clientRequestId,
      requestKind,
      phase: "json-parse-failed",
      elapsedMs: elapsed,
      status: response.status,
      aborted: false,
      bodyTextLength,
    });
    throw new Error(`Failed to parse JSON response: ${err}`);
  }

  const doneTime = performance.now();
  logFetchPhase({
    path,
    runId,
    clientRequestId,
    requestKind,
    phase: "done",
    elapsedMs: doneTime - startTime,
    status: response.status,
    aborted: false,
    bodyTextLength,
  });

  return data;
};

// =============================================================================
// Helper: Extract error message from response
// =============================================================================

/**
 * Extract error message from a non-ok response.
 * Tries JSON payload first, falls back to statusText.
 */
export const extractErrorMessage = async (response: Response): Promise<string> => {
  let message = response.statusText;
  try {
    const payload = await response.json();
    if (payload && typeof payload === "object" && "error" in payload) {
      message = String((payload as Record<string, unknown>).error);
    }
  } catch {
    // ignore - fall back to statusText
  }
  return message;
};

// =============================================================================
// Re-export RuntimeStatusPayload for convenience
// =============================================================================

export type { RuntimeStatusPayload };

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
  const response = await fetch(
    `/api/debug/runs/${encodeURIComponent(runId)}/execution-state-bundle`,
    {
      cache: "no-store",
    }
  );

  if (!response.ok) {
    const message = await extractErrorMessage(response);
    throw new Error(message || "Failed to download diagnostics bundle");
  }

  return response.blob();
};
