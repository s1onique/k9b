/**
 * alertmanager.ts — API client for Alertmanager source operations.
 *
 * Covers: performAlertmanagerSourceAction, promoteAlertmanagerSource,
 *         stopTrackingAlertmanagerSource, submitAlertmanagerRelevanceFeedback.
 *
 * Auth/session behavior: Uses raw fetch which preserves existing browser auth
 * (cookies, session headers). This matches existing frontend API conventions.
 */

import type {
  AlertmanagerSourceActionRequest,
  AlertmanagerSourceActionResponse,
  AlertmanagerRelevanceFeedbackRequest,
  AlertmanagerRelevanceFeedbackResponse,
} from "../types";

// =============================================================================
// API Calls
// =============================================================================

/**
 * Perform an action on an Alertmanager source.
 *
 * @param request - The action request with sourceId, action, and optional clusterLabel/reason
 * @param runId - The run ID for the run-scoped route
 */
export const performAlertmanagerSourceAction = async (
  request: AlertmanagerSourceActionRequest,
  runId: string
): Promise<AlertmanagerSourceActionResponse> => {
  // Use the run-scoped route: POST /api/runs/{run_id}/alertmanager-sources/{source_id}/action
  const response = await fetch(
    `/api/runs/${encodeURIComponent(runId)}/alertmanager-sources/${encodeURIComponent(
      request.sourceId
    )}/action`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        action: request.action,
        clusterLabel: request.clusterLabel,
        reason: request.reason || undefined,
      }),
      cache: "no-store",
    }
  );
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
    throw new Error(message || `Failed to ${request.action} Alertmanager source`);
  }
  return (await response.json()) as AlertmanagerSourceActionResponse;
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

/**
 * Submit relevance feedback for an Alertmanager source.
 *
 * @param request - The relevance feedback request
 */
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
