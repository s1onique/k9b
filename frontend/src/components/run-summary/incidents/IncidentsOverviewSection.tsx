/**
 * IncidentsOverviewSection.tsx
 *
 * Canonical Incidents section for the selected-run overview page.
 * Implements the Elmish island pattern with explicit Model, Msg, update, selectors, and view.
 *
 * Design goals:
 * - State clarity: shows status, evidence, diagnosis, review-packet indicators
 * - Compact: at-a-glance view without full detail expansion
 * - Honest empty state: "No incidents for this run."
 * - Expandable: inline expansion for incident details
 * - Paginated: Recent Runs-style pagination
 *
 * Hard constraints enforced:
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 * - NO external tool invocation
 * - NO persistence
 * - NO write actions
 */

import { useReducer, useEffect, useCallback, useMemo } from "react";
import type { IncidentsListResponse } from "../../../api";
import { listIncidents } from "../../../api";
import Pagination from "../../Pagination";

import type { IncidentsModel, IncidentsMsg } from "./incidentsTypes";
import {
  DEFAULT_INCIDENTS_PAGE_SIZE,
  INCIDENTS_PAGE_SIZE_OPTIONS,
} from "./incidentsTypes";
import { createInitialIncidentsModel } from "./incidentsModel";
import { incidentsUpdate } from "./incidentsUpdate";
import {
  selectVisibleIncidents,
  selectFilteredIncidents,
  selectPageCount,
  selectPageRangeLabel,
  selectTotalStatusCounts,
  selectFilteredStatusCounts,
} from "./incidentsSelectors";

import {
  DiagnosisStatusBadge,
  ReviewPacketIndicator,
  StatusSummaryBar,
  IncidentRow,
  IncidentsTable,
  FilterControls,
  IncidentsLoadingState,
  IncidentsErrorState,
  IncidentsEmptyState,
} from "./incidentsView";

// ============================================================================
// Props
// ============================================================================

export interface IncidentsOverviewSectionProps {
  /** The run ID to filter incidents by */
  runId: string | null;
}

// ============================================================================
// Reducer setup
// ============================================================================

/**
 * Reducer for IncidentsModel.
 * Uses incidentsUpdate for pure state transitions.
 */
function incidentsReducer(model: IncidentsModel, msg: IncidentsMsg): IncidentsModel {
  return incidentsUpdate(model, msg);
}

// ============================================================================
// Main component
// ============================================================================

/**
 * Canonical Incidents section for the selected-run overview page.
 *
 * Shows:
 * - Status summary bar (Open / Collecting / Ready for review / Investigating / Resolved counts)
 * - Compact expandable table with: Expand | Severity | Status | Object | Namespace | Evidence | Diagnosis | Review Packet | Updated
 * - Status filter and pagination controls
 * - Empty state when no incidents
 * - Loading state while fetching
 * - Error state with retry option
 * - Read-only notice
 *
 * API: Backend owns run scoping; runId triggers refetch on changes.
 */
export const IncidentsOverviewSection: React.FC<IncidentsOverviewSectionProps> = ({
  runId,
}) => {
  // Initialize model with runId
  const [model, dispatch] = useReducer(
    incidentsReducer,
    runId,
    createInitialIncidentsModel
  );

  // Load incidents effect - runs on mount, when runId changes, or when refresh is requested
  useEffect(() => {
    // Ignore flag prevents race conditions when responses arrive out of order
    let ignore = false;

    // Dispatch loadStarted to set loading state
    dispatch({ type: "loadStarted" });

    async function load() {
      try {
        // API only supports status filter; run scoping is done by backend
        const response: IncidentsListResponse = await listIncidents();
        if (!ignore) {
          // Dispatch loadSucceeded with the incidents
          dispatch({
            type: "loadSucceeded",
            incidents: Array.isArray(response.incidents) ? response.incidents : [],
          });
        }
      } catch (err) {
        if (!ignore) {
          const message = err instanceof Error ? err.message : "Failed to load incidents";
          dispatch({ type: "loadFailed", message });
        }
      }
    }

    void load();

    return () => {
      ignore = true;
    };
  }, [runId, model.refreshToken]);

  // Handle runId changes from parent
  useEffect(() => {
    if (runId !== model.runId) {
      dispatch({ type: "runChanged", runId });
    }
  }, [runId, model.runId]);

  // Handle refresh request
  const handleRefresh = useCallback(() => {
    dispatch({ type: "refreshRequested" });
  }, []);

  // Handle retry
  const handleRetry = useCallback(() => {
    dispatch({ type: "refreshRequested" });
  }, []);

  // Handle page change
  const handlePageChange = useCallback((page: number) => {
    dispatch({ type: "pageChanged", page });
  }, []);

  // Handle page size change
  const handlePageSizeChange = useCallback((size: number) => {
    dispatch({ type: "pageSizeChanged", pageSize: size });
  }, []);

  // Compute derived state using selectors
  const visibleIncidents = useMemo(
    () => selectVisibleIncidents(model),
    [model]
  );

  const filteredIncidents = useMemo(
    () => selectFilteredIncidents(model),
    [model]
  );

  const totalCounts = useMemo(
    () => selectTotalStatusCounts(model),
    [model]
  );

  const filteredCounts = useMemo(
    () => selectFilteredStatusCounts(model),
    [model]
  );

  const totalPages = useMemo(
    () => selectPageCount(filteredIncidents.length, model.pageSize),
    [filteredIncidents.length, model.pageSize]
  );

  const pageRangeLabel = useMemo(
    () => selectPageRangeLabel(model),
    [model]
  );

  const hasFilter = model.statusFilter !== "all";
  const isLoading = model.loadState === "loading";

  // Loading state
  if (model.loadState === "idle" || isLoading) {
    return <IncidentsLoadingState />;
  }

  // Error state
  if (model.loadState === "failed" && model.errorMessage) {
    return (
      <IncidentsErrorState
        message={model.errorMessage}
        onRetry={handleRetry}
      />
    );
  }

  // Empty state - no incidents for this run
  if (filteredIncidents.length === 0) {
    return <IncidentsEmptyState hasFilter={hasFilter} />;
  }

  // Main content - incidents table with status summary, filter, and pagination
  return (
    <section
      className="panel incidents-overview-section"
      data-testid="incidents-overview-section"
    >
      {/* Header */}
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
      <StatusSummaryBar counts={hasFilter ? filteredCounts : totalCounts} />

      {/* Filter controls */}
      <FilterControls
        model={model}
        dispatch={dispatch}
        isLoading={isLoading}
      />

      {/* Incidents table */}
      <IncidentsTable
        incidents={visibleIncidents}
        model={model}
        dispatch={dispatch}
      />

      {/* Pagination */}
      <Pagination
        currentPage={model.page}
        totalPages={totalPages}
        totalItems={filteredIncidents.length}
        pageSize={model.pageSize}
        pageSizeOptions={INCIDENTS_PAGE_SIZE_OPTIONS}
        onPageChange={handlePageChange}
        onPageSizeChange={handlePageSizeChange}
        label="Incidents"
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

export default IncidentsOverviewSection;
