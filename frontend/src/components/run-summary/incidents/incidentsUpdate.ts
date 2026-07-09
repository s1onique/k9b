/**
 * incidentsUpdate.ts — Pure reducer for the canonical Incidents Elmish island.
 *
 * All state transitions are pure functions of (model, msg) => model.
 * No side effects, no API calls, no React hooks.
 */

import type { IncidentsModel, IncidentsMsg, IncidentStatusFilter } from "./incidentsTypes";
import { INCIDENTS_PAGE_SIZE_OPTIONS } from "./incidentsTypes";

/**
 * Pure reducer for IncidentsModel.
 *
 * Update rules:
 * - runChanged: set runId, clear error, reset page to 1, collapse expansions
 * - loadStarted: set loadState = "loading", clear error
 * - loadSucceeded: store incidents, set loadState = "loaded", clamp page, remove stale expanded IDs
 * - loadFailed: set loadState = "failed", store error, keep old incidents
 * - statusFilterChanged: set filter, reset page to 1, collapse expansions
 * - refreshRequested: no model change (triggered by effect)
 * - pageChanged: clamp to [1, pageCount], collapse expansions
 * - pageSizeChanged: set page size, reset page to 1, collapse expansions
 * - incidentExpansionToggled: toggle ID in expandedIncidentIds
 * - allExpansionsCollapsed: clear expandedIncidentIds
 *
 * @param model - Current model state
 * @param msg - Action to process
 * @returns New model state (never mutates input)
 */
export function incidentsUpdate(
  model: IncidentsModel,
  msg: IncidentsMsg
): IncidentsModel {
  switch (msg.type) {
    case "runChanged": {
      // Run changed: reset to loading state for the new run
      return Object.freeze({
        ...model,
        runId: msg.runId,
        loadState: "loading" as const,
        errorMessage: null,
        // Keep incidents array during load transition to prevent flash
        // incidents: [],
        page: 1,
        expandedIncidentIds: new ReadonlySet(),
      });
    }

    case "loadStarted": {
      return Object.freeze({
        ...model,
        loadState: "loading" as const,
        errorMessage: null,
      });
    }

    case "loadSucceeded": {
      // Filter incidents to those matching the current status filter
      // The actual filtering is done in selectors, but we compute page count here
      const filteredCount = msg.incidents.filter(
        (incident) =>
          model.statusFilter === "all" || incident.status === model.statusFilter
      ).length;

      // Clamp page to valid range
      const pageCount = Math.max(1, Math.ceil(filteredCount / model.pageSize));
      const clampedPage = Math.min(model.page, pageCount);

      // Remove expanded IDs that no longer exist in the new incidents list
      const validIds = new Set(msg.incidents.map((i) => i.incident_id));
      const validExpandedIds = [...model.expandedIncidentIds].filter((id) =>
        validIds.has(id)
      );

      return Object.freeze({
        ...model,
        loadState: "loaded" as const,
        errorMessage: null,
        incidents: msg.incidents,
        page: clampedPage,
        expandedIncidentIds: new ReadonlySet(validExpandedIds),
      });
    }

    case "loadFailed": {
      // Keep old incidents on failure (defensive: don't clear useful data)
      return Object.freeze({
        ...model,
        loadState: "failed" as const,
        errorMessage: msg.message,
      });
    }

    case "statusFilterChanged": {
      return Object.freeze({
        ...model,
        statusFilter: msg.statusFilter,
        page: 1,
        expandedIncidentIds: new ReadonlySet(),
      });
    }

    case "refreshRequested": {
      // Increment refreshToken to trigger the fetch effect to re-run
      return Object.freeze({
        ...model,
        refreshToken: model.refreshToken + 1,
      });
    }

    case "pageChanged": {
      // Clamp page to valid range based on current filtered incidents
      const filteredCount = model.incidents.filter(
        (incident) =>
          model.statusFilter === "all" || incident.status === model.statusFilter
      ).length;

      const pageCount = Math.max(1, Math.ceil(filteredCount / model.pageSize));
      const clampedPage = Math.max(1, Math.min(msg.page, pageCount));

      return Object.freeze({
        ...model,
        page: clampedPage,
        expandedIncidentIds: new ReadonlySet(), // Collapse expansions on page change
      });
    }

    case "pageSizeChanged": {
      // Validate page size against allowed options
      const validSizes = [...INCIDENTS_PAGE_SIZE_OPTIONS];
      const newSize = validSizes.includes(msg.pageSize)
        ? msg.pageSize
        : model.pageSize;

      return Object.freeze({
        ...model,
        pageSize: newSize,
        page: 1,
        expandedIncidentIds: new ReadonlySet(),
      });
    }

    case "incidentExpansionToggled": {
      const newExpanded = new Set(model.expandedIncidentIds);
      if (newExpanded.has(msg.incidentId)) {
        newExpanded.delete(msg.incidentId);
      } else {
        newExpanded.add(msg.incidentId);
      }
      return Object.freeze({
        ...model,
        expandedIncidentIds: Object.freeze(newExpanded),
      });
    }

    case "allExpansionsCollapsed": {
      return Object.freeze({
        ...model,
        expandedIncidentIds: new ReadonlySet(),
      });
    }

    default: {
      // Exhaustive check: ensure all Msg variants are handled
      const _exhaustive: never = msg;
      return model;
    }
  }
}

/**
 * Checks if a status filter value is valid.
 */
export function isValidStatusFilter(value: string): value is IncidentStatusFilter {
  const validFilters: IncidentStatusFilter[] = [
    "all",
    "open",
    "collecting_evidence",
    "ready_for_review",
    "investigating",
    "suppressed",
    "duplicate",
    "resolved",
  ];
  return validFilters.includes(value as IncidentStatusFilter);
}
