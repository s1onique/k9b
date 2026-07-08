/**
 * alertmanager.ts — API client for Alertmanager source operations.
 *
 * Covers: performAlertmanagerSourceAction, promoteAlertmanagerSource,
 *         stopTrackingAlertmanagerSource, submitAlertmanagerRelevanceFeedback.
 *
 * All operations use the generated OpenAPI client (IncidentsApi).
 * Request body types are generated from the backend API_ROUTES registry.
 *
 * Auth/session behavior: Uses generated client configuration with credentials: "include"
 * to preserve existing browser auth (cookies, session headers).
 */

import type {
  AlertmanagerSourceActionRequest,
  AlertmanagerSourceActionResponse,
  AlertmanagerRelevanceFeedbackRequest,
  AlertmanagerRelevanceFeedbackResponse,
} from "../types";

// Generated client imports
import { IncidentsApi } from "../generated/k9b-api";
import {
  PerformAlertmanagerSourceActionRequest,
  RecordAlertmanagerRelevanceFeedbackRequest,
} from "../generated/k9b-api";
import { createK9bApiConfiguration, normalizeGeneratedApiError } from "./generatedClient";

// Body-based source_id endpoint (sourceId in request body to support slashes)
const ALERTMANAGER_SOURCE_ACTION_ENDPOINT = "/api/runs/{runId}/alertmanager-sources/action";

// =============================================================================
// API Factory
// =============================================================================

function createIncidentsApi(): IncidentsApi {
  return new IncidentsApi(createK9bApiConfiguration());
}

// =============================================================================
// AlertManager source action
// =============================================================================

/**
 * Perform an action on an Alertmanager source.
 *
 * Uses direct fetch to POST to the body-based endpoint. sourceId is now in the
 * request body (not the URL path) to support slashes in identifiers like
 * 'crd:monitoring/kube-prometheus-stack-alertmanager'.
 *
 * @param request - The action request with sourceId, action, and optional clusterLabel/reason
 * @param runId - The run ID for the run-scoped route
 */
export const performAlertmanagerSourceAction = async (
  request: AlertmanagerSourceActionRequest,
  runId: string
): Promise<AlertmanagerSourceActionResponse> => {
  try {
    const config = createK9bApiConfiguration();
    const endpoint = ALERTMANAGER_SOURCE_ACTION_ENDPOINT.replace("{runId}", runId);

    const response = await fetch(`${config.basePath}${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(config.username ? {
          Authorization: `Basic ${btoa(`${config.username}:${config.password}`)}`
        } : {}),
      },
      credentials: "include", // Preserve cookies/session
      body: JSON.stringify({
        sourceId: request.sourceId,
        action: request.action,
        clusterLabel: request.clusterLabel,
        reason: request.reason,
      }),
    });

    if (!response.ok) {
      const errorBody = await response.text();
      throw new Error(`HTTP ${response.status}: ${errorBody}`);
    }

    return await response.json() as AlertmanagerSourceActionResponse;
  } catch (error) {
    throw await normalizeGeneratedApiError(error);
  }
};

/**
 * Convenience wrapper to promote an Alertmanager source.
 *
 * @param request - The source action request (without action)
 * @param runId - The run ID for the run-scoped route
 */
export const promoteAlertmanagerSource = async (
  request: AlertmanagerSourceActionRequest,
  runId: string
): Promise<AlertmanagerSourceActionResponse> => {
  return performAlertmanagerSourceAction({ ...request, action: "promote" }, runId);
};

/**
 * Convenience wrapper to stop tracking an Alertmanager source (disable).
 *
 * @param request - The source action request (without action)
 * @param runId - The run ID for the run-scoped route
 */
export const stopTrackingAlertmanagerSource = async (
  request: AlertmanagerSourceActionRequest,
  runId: string
): Promise<AlertmanagerSourceActionResponse> => {
  return performAlertmanagerSourceAction({ ...request, action: "disable" }, runId);
};

// =============================================================================
// AlertManager relevance feedback
// =============================================================================

/**
 * Submit relevance feedback for an Alertmanager source.
 *
 * Uses the generated client with typed request body from API schema.
 *
 * @param request - The relevance feedback request
 */
export const submitAlertmanagerRelevanceFeedback = async (
  request: AlertmanagerRelevanceFeedbackRequest
): Promise<AlertmanagerRelevanceFeedbackResponse> => {
  try {
    const api = createIncidentsApi();
    const generatedRequest: RecordAlertmanagerRelevanceFeedbackRequest = {
      artifactPath: request.artifactPath,
      alertmanagerRelevance: request.alertmanagerRelevance,
      alertmanagerRelevanceSummary: request.alertmanagerRelevanceSummary,
    };
    const result = await api.recordAlertmanagerRelevanceFeedback({
      recordAlertmanagerRelevanceFeedbackRequest: generatedRequest,
    });
    return result as AlertmanagerRelevanceFeedbackResponse;
  } catch (error) {
    throw await normalizeGeneratedApiError(error);
  }
};
