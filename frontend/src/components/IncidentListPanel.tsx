/**
 * IncidentListPanel Component
 *
 * Read-only UI for displaying promoted incidents from snapshot captures.
 * 
 * Hard constraints enforced:
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 * - NO external tool invocation
 * - NO persistence (in-memory only)
 * - NO write actions
 */

import { useState, useEffect, useCallback, useRef } from "react";
import type { IncidentSummaryPayload, IncidentDetailPayload } from "../api";
import { listIncidents, getIncident } from "../api";
import { IncidentDetailPanel } from "./IncidentDetailPanel";

// Status values from IncidentStatus enum
const INCIDENT_STATUSES = [
  { value: "", label: "All" },
  { value: "open", label: "Open" },
  { value: "collecting_evidence", label: "Collecting Evidence" },
  { value: "ready_for_review", label: "Ready for Review" },
  { value: "investigating", label: "Investigating" },
  { value: "suppressed", label: "Suppressed" },
  { value: "duplicate", label: "Duplicate" },
  { value: "resolved", label: "Resolved" },
] as const;

/**
 * Maps backend status to display label.
 */
const getStatusLabel = (status: string): string => {
  const found = INCIDENT_STATUSES.find(s => s.value === status);
  return found?.label ?? status;
};

/**
 * Returns CSS class for severity badge.
 */
const getSeverityClass = (severity: string): string => {
  switch (severity.toLowerCase()) {
    case "error":
      return "severity-error";
    case "warning":
      return "severity-warning";
    default:
      return "severity-info";
  }
};

/**
 * Returns CSS class for status badge.
 */
const getStatusClass = (status: string): string => {
  switch (status.toLowerCase()) {
    case "open":
      return "status-open";
    case "collecting_evidence":
      return "status-collecting";
    case "ready_for_review":
      return "status-review";
    case "investigating":
      return "status-investigating";
    case "suppressed":
      return "status-suppressed";
    case "duplicate":
      return "status-duplicate";
    case "resolved":
      return "status-resolved";
    default:
      return "status-unknown";
  }
};

/**
 * Formats a timestamp for display.
 */
const formatTimestamp = (timestamp: string): string => {
  try {
    const date = new Date(timestamp);
    return date.toLocaleString();
  } catch {
    return timestamp;
  }
};

interface IncidentRowProps {
  incident: IncidentSummaryPayload;
  isExpanded: boolean;
  isLoading: boolean;
  hasError: boolean;
  onToggle: () => void;
}

/**
 * Renders a single incident row with read-only evidence and review packet info.
 * Uses latest_snapshot_bundle_id and review_packet state object.
 */
const IncidentRow: React.FC<IncidentRowProps> = ({
  incident,
  isExpanded,
  isLoading,
  hasError,
  onToggle,
}) => {
  const displayKind = incident.raw_object_kind || incident.object_kind;

  return (
    <div className="incident-row">
      <div className="incident-header">
        <div className="incident-badges">
          <span className={`severity-badge ${getSeverityClass(incident.severity)}`}>
            {incident.severity}
          </span>
          <span className={`status-badge ${getStatusClass(incident.status)}`}>
            {getStatusLabel(incident.status)}
          </span>
        </div>
        <span className="incident-id muted small">{incident.incident_id}</span>
      </div>
      <div className="incident-body">
        <div className="incident-object">
          <span className="object-kind">{displayKind}</span>
          <span className="object-name">{incident.object_name}</span>
          <span className="muted">in</span>
          <span className="namespace">{incident.namespace}</span>
        </div>
        <div className="incident-class">
          <span className="muted small">Class:</span>
          <span>{incident.candidate_class.replace(/_/g, " ")}</span>
        </div>
        <div className="incident-timestamp">
          <span className="muted small">Last observed:</span>
          <span>{formatTimestamp(incident.last_observed_at)}</span>
        </div>
        {/* Signal and evidence counts */}
        <div className="incident-counts">
          <span className="muted small">Signals:</span>
          <span>{incident.signal_count}</span>
          <span className="muted small">Evidence:</span>
          <span>{incident.evidence_count}</span>
        </div>
        {incident.latest_snapshot_bundle_id && (
          <div className="incident-bundle-id">
            <span className="muted small">Bundle:</span>
            <code>{incident.latest_snapshot_bundle_id}</code>
          </div>
        )}
        {/* Review packet state section - uses review_packet object */}
        <div className="incident-review-section">
          {incident.review_packet.status === "available" ? (
            <div className="review-packet-info">
              <span className="muted small">Review Packet:</span>
              <span className="review-packet-badge">Available</span>
              {incident.review_packet.id && (
                <code className="review-packet-id">{incident.review_packet.id}</code>
              )}
            </div>
          ) : incident.review_packet.status === "generating" ? (
            <div className="review-packet-pending">
              <span className="muted small">Review Packet:</span>
              <span className="review-packet-generating-text">Generating...</span>
            </div>
          ) : incident.review_packet.status === "failed" ? (
            <div className="review-packet-pending">
              <span className="muted small">Review Packet:</span>
              <span className="review-packet-error-text">Failed: {incident.review_packet.error_message || "Unknown error"}</span>
            </div>
          ) : (
            <div className="review-packet-pending">
              <span className="muted small">Review Packet:</span>
              <span className="review-packet-pending-text">Not generated yet</span>
            </div>
          )}
        </div>
        {/* View/Hide details control */}
        <div className="incident-detail-control">
          {isLoading ? (
            <span className="incident-detail-loading muted small">Loading incident details...</span>
          ) : hasError ? (
            <span className="incident-detail-error muted small">Unable to load incident details.</span>
          ) : (
            <button
              type="button"
              className="btn btn-ghost btn-small"
              onClick={onToggle}
              aria-expanded={isExpanded}
              aria-controls={`incident-detail-${incident.incident_id}`}
            >
              {isExpanded ? "Hide details" : "View details"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export interface IncidentListPanelProps {
  /** No props required - reads from backend API */
}

/**
 * Read-only incident list panel.
 * Displays incidents promoted from snapshot captures.
 */
export const IncidentListPanel: React.FC<IncidentListPanelProps> = () => {
  const [incidents, setIncidents] = useState<IncidentSummaryPayload[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");

  // Detail expansion state
  const [expandedIncidentId, setExpandedIncidentId] = useState<string | null>(null);
  const [detail, setDetail] = useState<IncidentDetailPayload | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Ref for stale-response protection
  const activeRequestRef = useRef<string | null>(null);

  const loadIncidents = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await listIncidents(statusFilter || undefined);
      setIncidents(response.incidents);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load incidents";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter]);

  // Toggle incident details with stale-response protection
  const toggleIncidentDetails = useCallback(async (incidentId: string) => {
    // If already expanded, collapse it
    if (expandedIncidentId === incidentId) {
      setExpandedIncidentId(null);
      setDetail(null);
      setDetailError(null);
      activeRequestRef.current = null;
      return;
    }

    // Expand new incident - clear previous state
    setExpandedIncidentId(incidentId);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    activeRequestRef.current = incidentId;

    try {
      const payload = await getIncident(incidentId);
      // Stale-response guard: only apply if this is still the active request
      if (activeRequestRef.current === incidentId) {
        setDetail(payload);
        setDetailError(null);
      }
    } catch {
      // Only apply error if this is still the active request
      if (activeRequestRef.current === incidentId) {
        setDetailError("Unable to load incident details.");
      }
    } finally {
      // Only clear loading if this is still the active request
      if (activeRequestRef.current === incidentId) {
        setDetailLoading(false);
      }
    }
  }, [expandedIncidentId]);

  useEffect(() => {
    loadIncidents();
  }, [loadIncidents]);

  return (
    <section className="panel" id="incident-list">
      <div className="section-head">
        <h2>Incidents</h2>
        <p className="muted small">
          Read-only view of incidents promoted from snapshot captures
        </p>
      </div>

      {/* Status filter */}
      <div className="incident-filter">
        <label>
          Filter by status:
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            disabled={isLoading}
          >
            {INCIDENT_STATUSES.map(status => (
              <option key={status.value} value={status.value}>
                {status.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={loadIncidents}
          disabled={isLoading}
          aria-label="Refresh incidents"
        >
          {isLoading ? "Loading..." : "Refresh incidents"}
        </button>
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="incident-loading">
          <p>Loading incidents...</p>
        </div>
      )}

      {/* Error state */}
      {error && !isLoading && (
        <div className="incident-error">
          <p className="error-message">Failed to load incidents: {error}</p>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !error && (!incidents || incidents.length === 0) && (
        <div className="incident-empty">
          <p className="muted small">
            {statusFilter
              ? `No incidents with status "${getStatusLabel(statusFilter)}"`
              : "No incidents recorded"}
          </p>
        </div>
      )}

      {/* Incident list */}
      {!isLoading && !error && (incidents?.length ?? 0) > 0 && (
        <div className="incident-list">
          <p className="muted small incident-count">
            {incidents!.length} incident{incidents!.length !== 1 ? "s" : ""}
          </p>
          <div className="incident-items">
            {incidents!.map((incident) => (
              <div key={incident.incident_id}>
                <IncidentRow
                  incident={incident}
                  isExpanded={expandedIncidentId === incident.incident_id}
                  isLoading={expandedIncidentId === incident.incident_id && detailLoading}
                  hasError={expandedIncidentId === incident.incident_id && detailError !== null}
                  onToggle={() => toggleIncidentDetails(incident.incident_id)}
                />
                {/* Expanded detail panel */}
                {expandedIncidentId === incident.incident_id && detail && (
                  <div
                    id={`incident-detail-${incident.incident_id}`}
                    className="incident-detail-wrapper"
                  >
                    <IncidentDetailPanel incident={detail} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Read-only notice */}
      <div className="incident-notice">
        <p className="muted small">
          Read-only view. No remediation, mutation, or LLM actions available.
        </p>
      </div>
    </section>
  );
};

export default IncidentListPanel;
