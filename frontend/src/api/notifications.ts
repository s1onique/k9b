/**
 * notifications.ts — API client for notification operations.
 *
 * Covers: fetchNotifications (listNotifications).
 *
 * This module uses the generated OpenAPI client (IncidentsApi) for HTTP operations
 * while maintaining stable handwritten wrapper functions for React components.
 *
 * Auth/session behavior: Uses generated client configuration with credentials: "include"
 * to preserve existing browser auth (cookies, session headers).
 */

import type { NotificationsPayload } from "../types";
import { IncidentsApi } from "../generated/k9b-api";
import { createK9bApiConfiguration, normalizeGeneratedApiError } from "./generatedClient";

// =============================================================================
// Types
// =============================================================================

export type NotificationsQuery = {
  kind?: string;
  cluster_label?: string;
  search?: string;
  limit?: number;
  page?: number;
};

export type NotificationsResponse = NotificationsPayload;

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
// API Calls
// =============================================================================

/**
 * Fetch notifications with optional filtering.
 *
 * @param query - Optional query parameters for filtering
 */
export const fetchNotifications = async (query?: NotificationsQuery): Promise<NotificationsResponse> => {
  try {
    const api = createIncidentsApi();
    // limit and page are strings in generated client; convert numbers to strings
    const result = await api.listNotifications({
      kind: query?.kind,
      clusterLabel: query?.cluster_label,
      search: query?.search,
      limit: query?.limit !== undefined ? String(query.limit) : undefined,
      page: query?.page !== undefined ? String(query.page) : undefined,
    });
    return result as NotificationsResponse;
  } catch (error) {
    throw await normalizeGeneratedApiError(error);
  }
};
