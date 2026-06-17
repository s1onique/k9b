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

import { useState, useEffect, useCallback } from "react";
import type { Incident } from "../api";
import { listIncidents } from "../api";

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
  incident: Incident;
}

const IncidentRow: React.FC<IncidentRowProps> = ({ incident }) => {
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
          <span>{incident.class.replace(/_/g, " ")}</span>
        </div>
        <div className="incident-timestamp">
          <span className="muted small">Last observed:</span>
          <span>{formatTimestamp(incident.last_observed_at)}</span>
        </div>
        {incident.snapshot_bundle_id && (
          <div className="incident-bundle-id">
            <span className="muted small">Bundle:</span>
            <code>{incident.snapshot_bundle_id}</code>
          </div>
        )}
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
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");

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
              <IncidentRow key={incident.incident_id} incident={incident} />
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
