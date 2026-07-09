/**
 * incidentsStates.tsx — State components for incidents (loading, error, empty, content).
 *
 * Pure view components for loading, error, empty, and content states.
 * All state is passed in as props; no local state or effects.
 */

import React from "react";
import type {
  IncidentsModel,
  IncidentsMsg,
  IncidentStatusCounts,
} from "./incidentsTypes";
import { INCIDENT_STATUS_FILTER_OPTIONS } from "./incidentsTypes";
import { StatusSummaryBar } from "./incidentsTable";
import { IncidentsTable } from "./incidentsTable";

// ============================================================================
// Filter controls
// ============================================================================

interface FilterControlsProps {
  model: IncidentsModel;
  dispatch: React.Dispatch<IncidentsMsg>;
  isLoading: boolean;
}

/**
 * Renders filter dropdown and refresh button.
 */
export const FilterControls: React.FC<FilterControlsProps> = ({
  model,
  dispatch,
  isLoading,
}) => {
  return (
    <div className="incidents-filter-bar">
      <div className="incident-filter">
        <label>
          Filter by status:
          <select
            value={model.statusFilter}
            onChange={(e) => {
              const value = e.target.value;
              if (
                INCIDENT_STATUS_FILTER_OPTIONS.some(
                  (opt) => opt.value === value
                )
              ) {
                dispatch({
                  type: "statusFilterChanged",
                  statusFilter: value as typeof model.statusFilter,
                });
              }
            }}
            disabled={isLoading}
          >
            {INCIDENT_STATUS_FILTER_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => dispatch({ type: "refreshRequested" })}
          disabled={isLoading}
          aria-label="Refresh incidents"
        >
          {isLoading ? "Loading..." : "Refresh incidents"}
        </button>
      </div>
    </div>
  );
};

// ============================================================================
// Loading state
// ============================================================================

/**
 * Renders the loading state for incidents.
 */
export const IncidentsLoadingState: React.FC = () => (
  <section
    className="panel incidents-overview-section incidents-overview-section--loading"
    data-testid="incidents-overview-section"
  >
    <div className="incidents-overview-header">
      <span className="incidents-overview-icon" aria-hidden="true">
        🚨
      </span>
      <h3>Incidents</h3>
    </div>
    <div className="incidents-overview-loading">
      <span className="loading-text">Loading incidents...</span>
    </div>
  </section>
);

// ============================================================================
// Error state
// ============================================================================

interface IncidentsErrorStateProps {
  message: string;
  onRetry: () => void;
}

/**
 * Renders the error state for incidents.
 */
export const IncidentsErrorState: React.FC<IncidentsErrorStateProps> = ({
  message,
  onRetry,
}) => (
  <section
    className="panel incidents-overview-section incidents-overview-section--error"
    data-testid="incidents-overview-section"
  >
    <div className="incidents-overview-header">
      <span className="incidents-overview-icon" aria-hidden="true">
        🚨
      </span>
      <h3>Incidents</h3>
    </div>
    <div className="incidents-overview-error">
      <p className="error-message">Failed to load incidents: {message}</p>
      <button type="button" className="btn btn-ghost" onClick={onRetry}>
        Retry
      </button>
    </div>
  </section>
);

// ============================================================================
// Empty state
// ============================================================================

interface IncidentsEmptyStateProps {
  hasFilter: boolean;
}

/**
 * Renders the empty state for incidents.
 */
export const IncidentsEmptyState: React.FC<IncidentsEmptyStateProps> = ({
  hasFilter,
}) => (
  <section
    className="panel incidents-overview-section incidents-overview-section--empty"
    data-testid="incidents-overview-section"
  >
    <div className="incidents-overview-header">
      <span className="incidents-overview-icon" aria-hidden="true">
        🚨
      </span>
      <h3>Incidents</h3>
    </div>
    <div className="incidents-overview-empty">
      <p className="muted">
        {hasFilter
          ? "No incidents match the current filter."
          : "No incidents for this run."}
      </p>
    </div>
  </section>
);

// ============================================================================
// Main content state
// ============================================================================

interface IncidentsContentProps {
  model: IncidentsModel;
  dispatch: React.Dispatch<IncidentsMsg>;
  totalCounts: IncidentStatusCounts;
}

/**
 * Renders the main content state for incidents with data.
 * Note: This component is not currently used - IncidentsOverviewSection
 * handles the main content directly. Exported for potential future use.
 */
export const IncidentsContent: React.FC<IncidentsContentProps> = ({
  model,
  dispatch,
  totalCounts,
}) => {
  const hasFilter = model.statusFilter !== "all";

  return (
    <section
      className="panel incidents-overview-section"
      data-testid="incidents-overview-section"
    >
      <div className="incidents-overview-header">
        <span className="incidents-overview-icon" aria-hidden="true">
          🚨
        </span>
        <h3>Incidents</h3>
        <span className="incidents-overview-count muted small">
          {totalCounts.total} incident{totalCounts.total !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Status summary bar */}
      <StatusSummaryBar counts={totalCounts} />

      {/* Filter controls */}
      <FilterControls
        model={model}
        dispatch={dispatch}
        isLoading={model.loadState === "loading"}
      />

      {/* Compact incidents table - placeholder, parent should pass actual incidents */}
      <IncidentsTable
        incidents={[]}
        model={model}
        dispatch={dispatch}
      />

      {/* Read-only notice */}
      <div className="incidents-overview-notice">
        <p className="muted small">
          Read-only view. No remediation, mutation, or LLM actions available.
        </p>
      </div>
    </section>
  );
};
