/**
 * IncidentListPanel Component
 *
 * Read-only UI for displaying promoted incidents from snapshot captures.
 * Redesigned to make Incidents the primary operational object.
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
import {
  incidentDisplayTitle,
  incidentPrimaryEntity,
  incidentStatusLabel,
  incidentSeverityClass,
  incidentStatusClass,
  incidentClassLabel,
  incidentSourceBadges,
  incidentSignalCountLabel,
  incidentEvidenceCountLabel,
  incidentDiagnosisSummary,
  incidentDiagnosisLoopClass,
  incidentDiagnosisLoopLabel,
  formatIncidentTimestamp,
  getSignalSourceLabel,
  getSignalSourceClass,
  type SignalSource,
} from "./incident-view-model";

// Incident status filter type - union of valid status values
type IncidentStatusFilter = "" | "open" | "collecting_evidence" | "ready_for_review" | "investigating" | "suppressed" | "duplicate" | "resolved";

// Status values from backend enum
const INCIDENT_STATUSES: readonly { value: IncidentStatusFilter; label: string }[] = [
  { value: "", label: "All" },
  { value: "open", label: "Open" },
  { value: "collecting_evidence", label: "Collecting Evidence" },
  { value: "ready_for_review", label: "Ready for Review" },
  { value: "investigating", label: "Investigating" },
  { value: "suppressed", label: "Suppressed" },
  { value: "duplicate", label: "Duplicate" },
  { value: "resolved", label: "Resolved" },
];

/**
 * Type guard to validate incident status filter values.
 */
const isIncidentStatusFilter = (value: string): value is IncidentStatusFilter =>
  INCIDENT_STATUSES.some((status) => status.value === value);

/**
 * Renders source badges for an incident.
 */
const SourceBadges: React.FC<{ sources: SignalSource[] }> = ({ sources }) => (
  <div className="incident-card-badges">
    {sources.map((source) => (
      <span key={source} className={getSignalSourceClass(source)}>
        {getSignalSourceLabel(source)}
      </span>
    ))}
  </div>
);

/**
 * Renders a compact diagnosis status indicator.
 */
const DiagnosisStatus: React.FC<{ status: "not_run" | "running_or_started" | "completed" | "failed_or_unavailable" }> = ({ status }) => (
  <span className={incidentDiagnosisLoopClass(status)}>
    {incidentDiagnosisLoopLabel(status)}
  </span>
);

interface IncidentCardProps {
  incident: IncidentSummaryPayload;
  isExpanded: boolean;
  isLoading: boolean;
  hasError: boolean;
  onToggle: () => void;
  onRetry: () => void;
  detailId: string;
}

/**
 * Renders a single incident card with incident-first design.
 * Shows: title, entity, status, severity, class, counts, diagnosis state, source badges.
 */
const IncidentCard: React.FC<IncidentCardProps> = ({
  incident,
  isExpanded,
  isLoading,
  hasError,
  onToggle,
  onRetry,
  detailId,
}) => {
  const sources = incidentSourceBadges(incident);
  const title = incidentDisplayTitle(incident);
  const entity = incidentPrimaryEntity(incident);

  return (
    <div className="incident-card">
      <div className="incident-card-header">
        <div className="incident-card-badges">
          <span className={incidentSeverityClass(incident.severity)}>
            {incident.severity}
          </span>
          <span className={incidentStatusClass(incident.status)}>
            {incidentStatusLabel(incident)}
          </span>
          <SourceBadges sources={sources} />
        </div>
        <span className="incident-card-id">{incident.incident_id}</span>
      </div>

      <h3 className="incident-card-title">{title}</h3>

      <div className="incident-card-entity">
        <span className="object-kind">{incident.raw_object_kind || incident.object_kind}</span>
        <span className="object-name">{incident.object_name}</span>
        <span>in</span>
        <span className="namespace">{incident.namespace}</span>
      </div>

      <div className="incident-card-meta">
        <span className="muted small">Class: {incidentClassLabel(incident)}</span>
        <span className="muted small">Last observed: {formatIncidentTimestamp(incident.last_observed_at)}</span>
      </div>

      <div className="incident-card-counts">
        <div className="incident-card-count">
          <span className="incident-card-count-label">Signals:</span>
          <span>{incident.signal_count}</span>
        </div>
        <div className="incident-card-count">
          <span className="incident-card-count-label">Evidence:</span>
          <span>{incident.evidence_count}</span>
        </div>
      </div>

      <div className="incident-card-diagnosis">
        <span className="muted small">Diagnosis:</span>
        <DiagnosisStatus status="not_run" />
      </div>

      <div className="incident-card-actions">
        {isLoading ? (
          <span className="muted small">Loading incident details...</span>
        ) : hasError ? (
          <>
            <span className="muted small">Unable to load incident details.</span>
            <button
              type="button"
              className="btn btn-ghost btn-small"
              onClick={onRetry}
              aria-label="Retry details"
            >
              Retry details
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-small"
              onClick={onToggle}
              aria-expanded={isExpanded}
              aria-controls={detailId}
            >
              Hide details
            </button>
          </>
        ) : (
          <button
            type="button"
            className="btn btn-ghost btn-small"
            onClick={onToggle}
            aria-expanded={isExpanded}
            aria-controls={detailId}
          >
            {isExpanded ? "Hide details" : "View details"}
          </button>
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
 * Redesigned to prioritize incidents as the primary operational object.
 */
export const IncidentListPanel: React.FC<IncidentListPanelProps> = () => {
  const [incidents, setIncidents] = useState<IncidentSummaryPayload[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<IncidentStatusFilter>("");

  // Detail expansion state
  const [expandedIncidentId, setExpandedIncidentId] = useState<string | null>(null);
  const [detail, setDetail] = useState<IncidentDetailPayload | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Ref for stale-response protection
  const activeRequestRef = useRef<string | null>(null);

  const loadIncidents = useCallback(async (status: IncidentStatusFilter) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await listIncidents(status || undefined);
      setIncidents(response.incidents);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load incidents";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Load incident details with stale-response protection
  const loadIncidentDetails = useCallback(async (incidentId: string) => {
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
  }, []);

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

    // Expand new incident - clear previous state and load details
    setExpandedIncidentId(incidentId);
    await loadIncidentDetails(incidentId);
  }, [expandedIncidentId, loadIncidentDetails]);

  // Retry loading incident details
  const retryIncidentDetails = useCallback(async (incidentId: string) => {
    await loadIncidentDetails(incidentId);
  }, [loadIncidentDetails]);

  useEffect(() => {
    void loadIncidents(statusFilter);
  }, [loadIncidents, statusFilter]);

  return (
    <section className="panel incident-panel" id="incident-list">
      <div className="incident-panel-header">
        <h2 className="incident-panel-title">
          <span>Incidents</span>
        </h2>
        <p className="incident-panel-subtitle">
          Read-only view of incidents promoted from operational signals
        </p>
      </div>

      {/* Status filter */}
      <div className="incident-filter">
        <label>
          Filter by status:
          <select
            value={statusFilter}
            onChange={(e) => {
              const value = e.target.value;
              if (isIncidentStatusFilter(value)) {
                setStatusFilter(value);
              }
            }}
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
          onClick={() => void loadIncidents(statusFilter)}
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

      {/* Empty state - incident-first messaging */}
      {!isLoading && !error && (!incidents || incidents.length === 0) && (
        <div className="incident-empty-state">
          <div className="incident-empty-state-icon">📋</div>
          <h3 className="incident-empty-state-title">No incidents yet.</h3>
          <p className="incident-empty-state-description">
            K9B opens incidents from detected operational signals. Today this includes
            Kubernetes candidates; future integrations can add Alertmanager and vmalert signals.
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
                <IncidentCard
                  incident={incident}
                  isExpanded={expandedIncidentId === incident.incident_id}
                  isLoading={expandedIncidentId === incident.incident_id && detailLoading}
                  hasError={expandedIncidentId === incident.incident_id && detailError !== null}
                  onToggle={() => toggleIncidentDetails(incident.incident_id)}
                  onRetry={() => retryIncidentDetails(incident.incident_id)}
                  detailId={`incident-detail-${incident.incident_id}`}
                />
                {/* Expanded detail panel */}
                {expandedIncidentId === incident.incident_id && detail && (
                  <div
                    id={`incident-detail-${incident.incident_id}`}
                    className="incident-detail-wrapper"
                    data-testid="incident-detail-panel"
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
