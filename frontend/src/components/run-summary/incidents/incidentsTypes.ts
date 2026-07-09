/**
 * incidentsTypes.ts — Type definitions for the canonical Incidents Elmish island.
 *
 * Defines the Model and Msg types for the IncidentsOverviewSection component.
 * Derived from existing IncidentSummaryPayload from the API layer.
 *
 * Hard constraints enforced:
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 * - NO external tool invocation
 * - NO persistence
 * - NO write actions
 */

import type { IncidentSummaryPayload } from "../../../api/incidents-types";

/**
 * Valid status filter values for incidents.
 */
export type IncidentStatusFilter =
  | "all"
  | "open"
  | "collecting_evidence"
  | "ready_for_review"
  | "investigating"
  | "suppressed"
  | "duplicate"
  | "resolved";

/**
 * All valid status filter values as a readonly array.
 */
export const INCIDENT_STATUS_FILTER_OPTIONS: readonly {
  value: IncidentStatusFilter;
  label: string;
}[] = [
  { value: "all", label: "All" },
  { value: "open", label: "Open" },
  { value: "collecting_evidence", label: "Collecting Evidence" },
  { value: "ready_for_review", label: "Ready for Review" },
  { value: "investigating", label: "Investigating" },
  { value: "suppressed", label: "Suppressed" },
  { value: "duplicate", label: "Duplicate" },
  { value: "resolved", label: "Resolved" },
] as const;

/**
 * Load state for the incidents data.
 */
export type IncidentsLoadState =
  | "idle"
  | "loading"
  | "loaded"
  | "failed";

/**
 * Canonical Incidents Model for the Elmish island.
 *
 * Design principles:
 * - Store only user choices and authoritative data
 * - Derived data lives in selectors, not the model
 * - Page/pageSize are user choices, not derived state
 */
export type IncidentsModel = {
  /** The run ID to filter incidents by. Null when no run is selected. */
  readonly runId: string | null;
  /** Current load state */
  readonly loadState: IncidentsLoadState;
  /** Error message when loadState is "failed" */
  readonly errorMessage: string | null;
  /** All incidents loaded from the API (unfiltered) */
  readonly incidents: ReadonlyArray<IncidentSummaryPayload>;
  /** User-selected status filter */
  readonly statusFilter: IncidentStatusFilter;
  /** Current page number (1-based) */
  readonly page: number;
  /** Number of incidents per page */
  readonly pageSize: number;
  /** Set of expanded incident IDs */
  readonly expandedIncidentIds: ReadonlySet<string>;
  /** Token that increments on refresh to trigger re-fetch */
  readonly refreshToken: number;
};

/**
 * Default page size for incidents pagination.
 */
export const DEFAULT_INCIDENTS_PAGE_SIZE = 10;

/**
 * Available page size options for incidents pagination.
 */
export const INCIDENTS_PAGE_SIZE_OPTIONS = [10, 25, 50] as const;

/**
 * Incidents Msg — all actions that can update the model.
 */
export type IncidentsMsg =
  | {
      readonly type: "runChanged";
      readonly runId: string | null;
    }
  | { readonly type: "loadStarted" }
  | {
      readonly type: "loadSucceeded";
      readonly incidents: ReadonlyArray<IncidentSummaryPayload>;
    }
  | { readonly type: "loadFailed"; readonly message: string }
  | {
      readonly type: "statusFilterChanged";
      readonly statusFilter: IncidentStatusFilter;
    }
  | { readonly type: "refreshRequested" }
  | { readonly type: "pageChanged"; readonly page: number }
  | { readonly type: "pageSizeChanged"; readonly pageSize: number }
  | {
      readonly type: "incidentExpansionToggled";
      readonly incidentId: string;
    }
  | { readonly type: "allExpansionsCollapsed" };

/**
 * Incident status counts for the summary bar.
 */
export interface IncidentStatusCounts {
  readonly open: number;
  readonly collecting_evidence: number;
  readonly ready_for_review: number;
  readonly investigating: number;
  readonly suppressed: number;
  readonly duplicate: number;
  readonly resolved: number;
  readonly total: number;
}

/**
 * Re-export IncidentSummaryPayload for consumers.
 */
export type { IncidentSummaryPayload };
