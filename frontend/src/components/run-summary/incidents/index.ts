/**
 * incidents/index.ts
 *
 * Barrel export for the canonical Incidents Elmish island.
 * Provides the main component and all supporting types/functions.
 */

// Main component
export { IncidentsOverviewSection } from "./IncidentsOverviewSection";
export type { IncidentsOverviewSectionProps } from "./IncidentsOverviewSection";

// Types
export type {
  IncidentsModel,
  IncidentsMsg,
  IncidentsLoadState,
  IncidentStatusFilter,
  IncidentStatusCounts,
  IncidentSummaryPayload,
} from "./incidentsTypes";

export {
  DEFAULT_INCIDENTS_PAGE_SIZE,
  INCIDENTS_PAGE_SIZE_OPTIONS,
  INCIDENT_STATUS_FILTER_OPTIONS,
} from "./incidentsTypes";

// Model
export { createInitialIncidentsModel } from "./incidentsModel";

// Update
export { incidentsUpdate, isValidStatusFilter } from "./incidentsUpdate";

// Selectors
export {
  selectFilteredIncidents,
  selectIncidentStatusCounts,
  selectSortedIncidents,
  selectPageCount,
  selectVisibleIncidents,
  selectPageRangeLabel,
  selectIsIncidentExpanded,
  selectHasExpandedIncidents,
  selectTotalStatusCounts,
  selectFilteredStatusCounts,
} from "./incidentsSelectors";

// View components (for advanced composition if needed)
export {
  DiagnosisStatusBadge,
  ReviewPacketIndicator,
  StatusSummaryBar,
  IncidentExpandedDetails,
  IncidentRow,
  IncidentsTable,
  FilterControls,
  IncidentsLoadingState,
  IncidentsErrorState,
  IncidentsEmptyState,
  IncidentsContent,
} from "./incidentsView";
