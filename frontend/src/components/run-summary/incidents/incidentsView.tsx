/**
 * incidentsView.tsx — Re-export barrel for view components.
 *
 * This file re-exports all view components from split files for backward compatibility.
 * The actual implementations are in:
 * - incidentsBadges.tsx - Badge and indicator components
 * - incidentsTable.tsx - Table and row components
 * - incidentsStates.tsx - State components (loading, error, empty, content)
 */

export {
  DiagnosisStatusBadge,
  ReviewPacketIndicator,
} from "./incidentsBadges";

export {
  StatusSummaryBar,
  IncidentExpandedDetails,
  IncidentRow,
  IncidentsTable,
} from "./incidentsTable";

export {
  FilterControls,
  IncidentsLoadingState,
  IncidentsErrorState,
  IncidentsEmptyState,
  IncidentsContent,
} from "./incidentsStates";
