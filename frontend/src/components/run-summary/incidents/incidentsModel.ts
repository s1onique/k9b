/**
 * incidentsModel.ts — Model factory for the canonical Incidents Elmish island.
 *
 * Pure function to create the initial model state.
 * All state transitions live in incidentsUpdate.ts.
 */

import type { IncidentsModel } from "./incidentsTypes";
import { DEFAULT_INCIDENTS_PAGE_SIZE } from "./incidentsTypes";

/**
 * Creates the initial IncidentsModel.
 *
 * @param runId - Optional initial run ID (null means no run selected)
 * @returns Initial model state
 */
export function createInitialIncidentsModel(
  runId: string | null = null
): IncidentsModel {
  return Object.freeze({
    runId,
    loadState: "idle",
    errorMessage: null,
    incidents: [],
    statusFilter: "all",
    page: 1,
    pageSize: DEFAULT_INCIDENTS_PAGE_SIZE,
    expandedIncidentIds: new Set(),
    refreshToken: 0,
  });
}
