/**
 * incidentsSelectors.ts — Pure selectors for the canonical Incidents Elmish island.
 *
 * All derived state lives here. Selectors are pure functions that do not mutate input.
 * They are computed on every render from the model, not stored in state.
 */

import type {
  IncidentsModel,
  IncidentSummaryPayload,
  IncidentStatusCounts,
} from "./incidentsTypes";

/**
 * Filters incidents based on the current status filter.
 * Returns a new array without mutating the input.
 *
 * @param model - The incidents model
 * @returns Filtered incidents (never empty array if filter matches nothing)
 */
export function selectFilteredIncidents(
  model: IncidentsModel
): ReadonlyArray<IncidentSummaryPayload> {
  if (model.statusFilter === "all") {
    return model.incidents;
  }
  return model.incidents.filter(
    (incident) => incident.status === model.statusFilter
  );
}

/**
 * Counts incidents by status for the status summary bar.
 * Includes all incidents (ignores current filter) to show total counts.
 *
 * @param incidents - Array of incidents to count
 * @returns Status counts object
 */
export function selectIncidentStatusCounts(
  incidents: ReadonlyArray<IncidentSummaryPayload>
): IncidentStatusCounts {
  const counts: IncidentStatusCounts = {
    open: 0,
    collecting_evidence: 0,
    ready_for_review: 0,
    investigating: 0,
    suppressed: 0,
    duplicate: 0,
    resolved: 0,
    total: incidents.length,
  };

  for (const incident of incidents) {
    switch (incident.status) {
      case "open":
        counts.open++;
        break;
      case "collecting_evidence":
        counts.collecting_evidence++;
        break;
      case "ready_for_review":
        counts.ready_for_review++;
        break;
      case "investigating":
        counts.investigating++;
        break;
      case "suppressed":
        counts.suppressed++;
        break;
      case "duplicate":
        counts.duplicate++;
        break;
      case "resolved":
        counts.resolved++;
        break;
      // Unknown statuses are ignored in counts
    }
  }

  return counts;
}

/**
 * Sorts incidents for display.
 * Primary sort: severity descending (error > warning > info)
 * Secondary sort: last_observed_at descending (newest first)
 * Tertiary sort: stable incident_id for tiebreaker
 *
 * @param incidents - Array of incidents to sort
 * @returns Sorted copy of incidents
 */
export function selectSortedIncidents(
  incidents: ReadonlyArray<IncidentSummaryPayload>
): ReadonlyArray<IncidentSummaryPayload> {
  const severityRank: Record<string, number> = {
    error: 3,
    warning: 2,
    info: 1,
  };

  return [...incidents].sort((a, b) => {
    // Primary: severity descending
    const rankA = severityRank[a.severity.toLowerCase()] ?? 0;
    const rankB = severityRank[b.severity.toLowerCase()] ?? 0;
    if (rankB !== rankA) {
      return rankB - rankA;
    }

    // Secondary: last_observed_at descending (newest first)
    const timeA = new Date(a.last_observed_at).getTime();
    const timeB = new Date(b.last_observed_at).getTime();
    if (timeB !== timeA) {
      return timeB - timeA;
    }

    // Tertiary: stable incident_id tiebreaker
    return a.incident_id.localeCompare(b.incident_id);
  });
}

/**
 * Calculates the total number of pages based on filtered incidents count and page size.
 *
 * @param filteredCount - Number of filtered incidents
 * @param pageSize - Items per page
 * @returns Total page count (minimum 1)
 */
export function selectPageCount(
  filteredCount: number,
  pageSize: number
): number {
  if (filteredCount === 0) {
    return 1;
  }
  return Math.ceil(filteredCount / pageSize);
}

/**
 * Returns the incidents visible on the current page.
 * Applies sorting and pagination to filtered incidents.
 *
 * @param model - The incidents model
 * @returns Paginated incidents for current page
 */
export function selectVisibleIncidents(
  model: IncidentsModel
): ReadonlyArray<IncidentSummaryPayload> {
  const filtered = selectFilteredIncidents(model);
  const sorted = selectSortedIncidents(filtered);
  const pageCount = selectPageCount(sorted.length, model.pageSize);

  // Handle edge case: if current page is beyond page count, show last page
  const safePage = Math.min(model.page, pageCount);
  const startIndex = (safePage - 1) * model.pageSize;
  const endIndex = startIndex + model.pageSize;

  return sorted.slice(startIndex, endIndex);
}

/**
 * Generates the page range label for pagination display.
 *
 * @param model - The incidents model
 * @returns Human-readable range label
 */
export function selectPageRangeLabel(model: IncidentsModel): string {
  const filtered = selectFilteredIncidents(model);

  if (filtered.length === 0) {
    return "No incidents";
  }

  const total = filtered.length;
  const pageCount = selectPageCount(total, model.pageSize);
  const safePage = Math.min(model.page, pageCount);

  const startItem = (safePage - 1) * model.pageSize + 1;
  const endItem = Math.min(safePage * model.pageSize, total);

  // Handle edge cases for small datasets
  if (total <= model.pageSize) {
    return `Showing ${total} of ${total}`;
  }

  return `Showing ${startItem}–${endItem} of ${total}`;
}

/**
 * Checks if an incident is expanded.
 *
 * @param model - The incidents model
 * @param incidentId - The incident ID to check
 * @returns True if the incident is expanded
 */
export function selectIsIncidentExpanded(
  model: IncidentsModel,
  incidentId: string
): boolean {
  return model.expandedIncidentIds.has(incidentId);
}

/**
 * Checks if there are any expanded incidents.
 *
 * @param model - The incidents model
 * @returns True if any incident is expanded
 */
export function selectHasExpandedIncidents(model: IncidentsModel): boolean {
  return model.expandedIncidentIds.size > 0;
}

/**
 * Returns filtered incidents counts by status for the summary bar.
 * Uses all incidents (ignores current filter) to show total counts.
 *
 * @param model - The incidents model
 * @returns Status counts for all incidents
 */
export function selectTotalStatusCounts(
  model: IncidentsModel
): IncidentStatusCounts {
  return selectIncidentStatusCounts(model.incidents);
}

/**
 * Returns filtered incidents counts by status.
 * Uses filtered incidents when a status filter is active.
 *
 * @param model - The incidents model
 * @returns Status counts for filtered incidents
 */
export function selectFilteredStatusCounts(
  model: IncidentsModel
): IncidentStatusCounts {
  const filtered = selectFilteredIncidents(model);
  return selectIncidentStatusCounts(filtered);
}
