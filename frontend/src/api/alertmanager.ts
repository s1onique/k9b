/**
 * alertmanager.ts — API client for Alertmanager source operations.
 *
 * Covers: performAlertmanagerSourceAction, promoteAlertmanagerSource,
 *         stopTrackingAlertmanagerSource, submitAlertmanagerRelevanceFeedback,
 *         getAlertmanagerSourcesReviewPacket,
 *         getAlertmanagerSourceDebugPacket,
 *         getAlertmanagerSourcePromotionReview,
 *         probeAlertmanagerSource.
 *
 * All AlertManager-source operations are exposed through the generated
 * ``AlertmanagerApi`` client. The contract guarantees that ``sourceId`` is
 * transported as follows:
 *
 *   - ``performAlertmanagerSourceAction``: sourceId in the JSON request body.
 *   - ``probeAlertmanagerSource``:          sourceId in the JSON request body.
 *   - ``getAlertmanagerSourceDebugPacket``: sourceId as a required query param.
 *   - ``getAlertmanagerSourcePromotionReview``: sourceId as a required query param.
 *
 * None of these operations place ``sourceId`` in the URL path, so opaque
 * identifiers such as ``crd:monitoring/alertmanager-main`` round-trip
 * end-to-end without URL encoding or manual unquote handling.
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

// Generated client imports. AlertmanagerApi owns all AlertManager-source
// operations; recordAlertmanagerRelevanceFeedback remains under IncidentsApi
// since it is a feedback endpoint, not a source operation.
import { AlertmanagerApi, IncidentsApi } from "../generated/k9b-api";
import { RecordAlertmanagerRelevanceFeedbackRequest } from "../generated/k9b-api";
import { createK9bApiConfiguration, normalizeGeneratedApiError } from "./generatedClient";

// =============================================================================
// API Factories
// =============================================================================

function createAlertmanagerApi(): AlertmanagerApi {
  return new AlertmanagerApi(createK9bApiConfiguration());
}

function createIncidentsApi(): IncidentsApi {
  return new IncidentsApi(createK9bApiConfiguration());
}

// =============================================================================
// AlertManager source action (sourceId in JSON body)
// =============================================================================

/**
 * Perform an action on an Alertmanager source.
 *
 * The generated client exposes this operation on ``AlertmanagerApi``. The
 * ``sourceId`` is sent in the JSON request body so opaque identifiers that
 * contain ``/`` round-trip without URL encoding.
 *
 * @param request - The action request with sourceId, action, and optional clusterLabel/reason
 * @param runId - The run ID for the run-scoped route
 */
export const performAlertmanagerSourceAction = async (
  request: AlertmanagerSourceActionRequest,
  runId: string
): Promise<AlertmanagerSourceActionResponse> => {
  try {
    const api = createAlertmanagerApi();
    const result = await api.performAlertmanagerSourceAction({
      runId,
      performAlertmanagerSourceActionRequest: {
        sourceId: request.sourceId,
        action: request.action,
        clusterLabel: request.clusterLabel,
        reason: request.reason,
      },
    });
    return result as AlertmanagerSourceActionResponse;
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
// AlertManager source debug packet (sourceId in required query param)
// =============================================================================

/**
 * Fetch the debug packet for a single Alertmanager source.
 *
 * The ``sourceId`` is supplied as a required query parameter; the URL path
 * does not include the source identifier, so slash-containing identifiers
 * are accepted without any client-side URL encoding.
 */
export const getAlertmanagerSourceDebugPacket = async (
  runId: string,
  sourceId: string
): Promise<unknown> => {
  try {
    const api = createAlertmanagerApi();
    return await api.getAlertmanagerSourceDebugPacket({
      runId,
      sourceId,
    });
  } catch (error) {
    throw await normalizeGeneratedApiError(error);
  }
};

/**
 * Live-probe an Alertmanager source and return the updated debug packet.
 *
 * The ``sourceId`` is sent in the JSON request body so the POST path stays
 * stable regardless of the identifier content.
 */
export const probeAlertmanagerSource = async (
  runId: string,
  sourceId: string
): Promise<unknown> => {
  try {
    const api = createAlertmanagerApi();
    return await api.probeAlertmanagerSource({
      runId,
      probeAlertmanagerSourceRequest: { sourceId },
    });
  } catch (error) {
    throw await normalizeGeneratedApiError(error);
  }
};

// =============================================================================
// AlertManager sources review and promotion-review packets
// =============================================================================

/**
 * Fetch the multi-source review packet explaining why multiple Alertmanager
 * sources were discovered for a run.
 */
export const getAlertmanagerSourcesReviewPacket = async (
  runId: string
): Promise<unknown> => {
  try {
    const api = createAlertmanagerApi();
    return await api.getAlertmanagerSourcesReviewPacket({ runId });
  } catch (error) {
    throw await normalizeGeneratedApiError(error);
  }
};

/**
 * Fetch the pre-promotion review for a specific Alertmanager source.
 *
 * The ``sourceId`` is supplied as a required query parameter; the URL path
 * does not include the source identifier.
 */
export const getAlertmanagerSourcePromotionReview = async (
  runId: string,
  sourceId: string
): Promise<unknown> => {
  try {
    const api = createAlertmanagerApi();
    return await api.getAlertmanagerSourcePromotionReview({
      runId,
      sourceId,
    });
  } catch (error) {
    throw await normalizeGeneratedApiError(error);
  }
};

// =============================================================================
// AlertManager relevance feedback (non-source feedback endpoint)
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
