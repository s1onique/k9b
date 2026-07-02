/**
 * runs.ts — API client for run, fleet, proposals, and cluster-detail operations.
 *
 * Covers: fetchRun, fetchFleet, fetchProposals, fetchClusterDetail, fetchRunsList, runBatchExecution.
 *
 * GET operations use the generated OpenAPI client (IncidentsApi) with initOverrides
 * for signal and custom headers.
 * POST operations with request bodies use raw fetch since API schema
 * doesn't define request bodies for these endpoints.
 *
 * Auth/session behavior: Uses generated client configuration with credentials: "include"
 * to preserve existing browser auth (cookies, session headers).
 */

import { IncidentsApi } from "../generated/k9b-api";
import { createK9bApiConfiguration, normalizeGeneratedApiError } from "./generatedClient";
import { extractErrorMessage } from "./client";

import type {
  RunPayload,
  FleetPayload,
  ProposalsPayload,
  ClusterDetailPayload,
  RunsListPayload,
  BatchExecutionRequest,
  BatchExecutionResponse,
} from "../types";

// =============================================================================
// HTML Detection Helper
// =============================================================================

/**
 * Check if a response body looks like HTML content (e.g., SPA fallback).
 * Detects common HTML patterns including DOCTYPE, <html>, <body> tags.
 */
function looksLikeHtml(body: string): boolean {
  const trimmed = body.trim();
  return (
    trimmed.startsWith("<!") ||
    trimmed.startsWith("<html") ||
    trimmed.startsWith("<body") ||
    /<(doctype|html|head|body)/i.test(trimmed)
  );
}

/**
 * Detect HTML fallback responses and throw descriptive errors.
 * This handles the case where nginx/SPA serves index.html for non-existent API routes.
 *
 * The generated client's JSON parsing throws a generic error for HTML content.
 * This function catches that generic error and produces a descriptive message.
 */
async function handleGeneratedClientError(error: unknown, url: string): Promise<never> {
  // Normalize via the standard handler first
  const normalizedError = await normalizeGeneratedApiError(error);

  // Check if the error message suggests JSON parsing failure on HTML content
  // The generated client throws generic JSON parsing errors like:
  // "The request failed and the interceptors did not return an alternative response"
  if (
    normalizedError.message.includes("request failed") ||
    normalizedError.message.includes("interceptors") ||
    normalizedError.message.includes("JSON")
  ) {
    // Try to get more context about what we received
    throw new Error(
      `Expected JSON from ${url} but received text/html. ` +
        "API route may be falling through to SPA index.html"
    );
  }

  throw normalizedError;
}

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

export type FetchRunOptions = {
  clientRequestId?: string;
  signal?: AbortSignal;
};

/**
 * Fetch details for a specific run.
 *
 * @param runId - Optional run ID (uses selected run if not provided)
 * @param options - Request options including clientRequestId and abort signal
 */
export const fetchRun = async (
  runId?: string,
  options?: FetchRunOptions
): Promise<RunPayload> => {
  try {
    const api = createIncidentsApi();

    // Build initOverrides for signal and custom headers
    const initOverrides: RequestInit = {};
    if (options?.signal) {
      initOverrides.signal = options.signal;
    }
    if (options?.clientRequestId) {
      initOverrides.headers = {
        "X-K9B-Client-Request-Id": options.clientRequestId,
      };
    }

    const result = await api.getRunDetail(
      { runId },
      Object.keys(initOverrides).length ? initOverrides : undefined
    );
    return result as RunPayload;
  } catch (error) {
    throw await normalizeGeneratedApiError(error);
  }
};

/**
 * Fetch fleet overview (all clusters).
 */
export const fetchFleet = async (): Promise<FleetPayload> => {
  const url = "/api/fleet";
  try {
    const api = createIncidentsApi();
    const result = await api.getFleet();
    return result as FleetPayload;
  } catch (error) {
    throw await handleGeneratedClientError(error, url);
  }
};

/**
 * Fetch diagnostic proposals for the current run.
 */
export const fetchProposals = async (): Promise<ProposalsPayload> => {
  const url = "/api/proposals";
  try {
    const api = createIncidentsApi();
    const result = await api.getProposals();
    return result as ProposalsPayload;
  } catch (error) {
    throw await handleGeneratedClientError(error, url);
  }
};

/**
 * Fetch detailed information for a specific cluster.
 *
 * @param clusterLabel - Optional cluster label (uses selected cluster if not provided)
 */
export const fetchClusterDetail = async (clusterLabel?: string): Promise<ClusterDetailPayload> => {
  try {
    const api = createIncidentsApi();
    const result = await api.getClusterDetail({ clusterLabel });
    return result as ClusterDetailPayload;
  } catch (error) {
    throw await normalizeGeneratedApiError(error);
  }
};

// =============================================================================
// Fetch Runs List (uses raw fetch to preserve include_batch_eligibility optimization)
// =============================================================================

/**
 * Fetch list of all diagnostic runs with pagination.
 *
 * Uses raw fetch to preserve include_batch_eligibility=true query param which is
 * used for fast Execute-button eligibility determination without the overhead
 * of include_status=true.
 *
 * @param options - Optional pagination options
 */
export const fetchRunsList = async (options?: {
  limit?: number;
  page?: number;
  clusterLabel?: string;
}): Promise<RunsListPayload> => {
  const params = new URLSearchParams();
  params.set("include_batch_eligibility", "true");

  if (options?.limit !== undefined) {
    params.set("limit", String(options.limit));
  }
  if (options?.page !== undefined) {
    params.set("page", String(options.page));
  }
  if (options?.clusterLabel) {
    params.set("cluster_label", options.clusterLabel);
  }

  const url = `/api/runs?${params.toString()}`;

  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      const message = await extractErrorMessage(response);
      throw new Error(message || `Failed to fetch runs: ${response.statusText}`);
    }
    return (await response.json()) as RunsListPayload;
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error(String(error));
  }
};

// =============================================================================
// POST Operations (use generated client)
// =============================================================================

/**
 * Execute multiple next-checks in batch.
 *
 * Uses the generated client with typed request body from API schema.
 */
export const runBatchExecution = async (
  request: BatchExecutionRequest
): Promise<BatchExecutionResponse> => {
  try {
    const api = createIncidentsApi();
    const result = await api.runBatchNextCheckExecution({
      runBatchNextCheckExecutionRequest: {
        runId: request.runId,
        dryRun: request.dryRun,
      },
    });
    return result as BatchExecutionResponse;
  } catch (error) {
    throw await normalizeGeneratedApiError(error);
  }
};
