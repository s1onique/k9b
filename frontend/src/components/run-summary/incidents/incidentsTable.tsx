/**
 * incidentsTable.tsx — Table components for incidents.
 *
 * Pure view components for the incidents table and its sub-components.
 * All state is passed in as props; no local state or effects.
 */

import React from "react";
import type {
  IncidentsModel,
  IncidentsMsg,
  IncidentSummaryPayload,
  IncidentStatusCounts,
} from "./incidentsTypes";
import {
  incidentDisplayTitle,
  incidentStatusLabel,
  incidentSeverityClass,
  incidentStatusClass,
  formatIncidentTimestamp,
} from "../../incident-view-model";
import { DiagnosisStatusBadge } from "./incidentsBadges";
import { ReviewPacketIndicator } from "./incidentsBadges";

// ============================================================================
// Status summary bar
// ============================================================================

/**
 * Compact status summary showing counts for each active status.
 */
export const StatusSummaryBar: React.FC<{ counts: IncidentStatusCounts }> = ({
  counts,
}) => {
  const items = [
    { label: "Open", count: counts.open, key: "open" },
    {
      label: "Collecting",
      count: counts.collecting_evidence,
      key: "collecting_evidence",
    },
    {
      label: "Ready",
      count: counts.ready_for_review,
      key: "ready_for_review",
    },
    { label: "Investigating", count: counts.investigating, key: "investigating" },
    { label: "Resolved", count: counts.resolved, key: "resolved" },
  ].filter((item) => item.count > 0);

  if (items.length === 0) {
    return null;
  }

  return (
    <div
      className="incidents-status-summary"
      data-testid="incidents-status-summary"
    >
      {items.map((item, index) => (
        <span key={item.key} className="incidents-status-chip">
          {item.label}: <strong>{item.count}</strong>
          {index < items.length - 1 && (
            <span className="incidents-status-separator">|</span>
          )}
        </span>
      ))}
    </div>
  );
};

// ============================================================================
// Expanded incident details row
// ============================================================================

interface IncidentExpandedDetailsProps {
  incident: IncidentSummaryPayload;
}

/**
 * Renders expanded details for an incident.
 * Shown as an adjacent table row with a single cell spanning all columns.
 */
export const IncidentExpandedDetails: React.FC<IncidentExpandedDetailsProps> = ({
  incident,
}) => {
  return (
    <div className="incident-expanded-details">
      <dl className="incident-details-grid">
        <div className="incident-detail-item">
          <dt>Incident ID</dt>
          <dd>{incident.incident_id}</dd>
        </div>
        <div className="incident-detail-item">
          <dt>Source Candidate ID</dt>
          <dd>{incident.candidate_class}</dd>
        </div>
        <div className="incident-detail-item">
          <dt>Latest Snapshot Bundle ID</dt>
          <dd>{incident.latest_snapshot_bundle_id ?? "None"}</dd>
        </div>
        <div className="incident-detail-item">
          <dt>Raw Object Kind</dt>
          <dd>{incident.raw_object_kind ?? incident.object_kind}</dd>
        </div>
        <div className="incident-detail-item">
          <dt>Signal Count</dt>
          <dd>{incident.signal_count}</dd>
        </div>
        <div className="incident-detail-item">
          <dt>Evidence Count</dt>
          <dd>{incident.evidence_count}</dd>
        </div>
        <div className="incident-detail-item">
          <dt>First Observed</dt>
          <dd>{formatIncidentTimestamp(incident.first_observed_at)}</dd>
        </div>
        <div className="incident-detail-item">
          <dt>Last Observed</dt>
          <dd>{formatIncidentTimestamp(incident.last_observed_at)}</dd>
        </div>
        {incident.suppressed_reason && (
          <div className="incident-detail-item">
            <dt>Suppressed Reason</dt>
            <dd>{incident.suppressed_reason}</dd>
          </div>
        )}
        {incident.duplicate_of && (
          <div className="incident-detail-item">
            <dt>Duplicate Of</dt>
            <dd>{incident.duplicate_of}</dd>
          </div>
        )}
        {incident.resolved_at && (
          <div className="incident-detail-item">
            <dt>Resolved At</dt>
            <dd>{formatIncidentTimestamp(incident.resolved_at)}</dd>
          </div>
        )}
      </dl>
    </div>
  );
};

// ============================================================================
// Single incident row (expandable)
// ============================================================================

interface IncidentRowProps {
  incident: IncidentSummaryPayload;
  isExpanded: boolean;
  dispatch: React.Dispatch<IncidentsMsg>;
}

/**
 * Renders a single incident as an expandable table row.
 * Shows: [Expand] | Severity | Status | Object | Namespace | Evidence | Diagnosis | Review Packet | Updated
 */
export const IncidentRow: React.FC<IncidentRowProps> = ({
  incident,
  isExpanded,
  dispatch,
}) => {
  const displayTitle = incidentDisplayTitle(incident);
  const detailsId = `incident-details-${incident.incident_id}`;

  return (
    <React.Fragment>
      <tr
        className="incident-overview-row"
        data-testid={`incident-row-${incident.incident_id}`}
      >
        {/* Expand/Collapse button */}
        <td className="incident-overview-cell incident-expand-cell">
          <button
            type="button"
            className="incident-expand-btn"
            aria-expanded={isExpanded}
            aria-controls={detailsId}
            onClick={() =>
              dispatch({
                type: "incidentExpansionToggled",
                incidentId: incident.incident_id,
              })
            }
          >
            {isExpanded ? "Collapse" : "Expand"}
          </button>
        </td>

        {/* Severity */}
        <td className="incident-overview-cell">
          <span className={incidentSeverityClass(incident.severity)}>
            {incident.severity}
          </span>
        </td>

        {/* Status */}
        <td className="incident-overview-cell">
          <span className={incidentStatusClass(incident.status)}>
            {incidentStatusLabel(incident)}
          </span>
        </td>

        {/* Object */}
        <td className="incident-overview-cell incident-overview-object">
          <span className="incident-overview-title" title={displayTitle}>
            {displayTitle}
          </span>
        </td>

        {/* Namespace */}
        <td className="incident-overview-cell">
          <span className="namespace">{incident.namespace}</span>
        </td>

        {/* Evidence */}
        <td className="incident-overview-cell">
          <span
            className="incident-overview-evidence"
            title={`${incident.evidence_count} evidence items`}
          >
            {incident.evidence_count} artifact
            {incident.evidence_count !== 1 ? "s" : ""}
          </span>
          {incident.signal_count > 0 && (
            <span
              className="incident-overview-signals muted small"
              title={`${incident.signal_count} signals`}
            >
              / {incident.signal_count} link{incident.signal_count !== 1 ? "s" : ""}
            </span>
          )}
        </td>

        {/* Diagnosis */}
        <td className="incident-overview-cell">
          <DiagnosisStatusBadge status="not_run" />
        </td>

        {/* Review Packet */}
        <td className="incident-overview-cell">
          <ReviewPacketIndicator
            status={incident.review_packet.status}
            errorMessage={incident.review_packet.error_message}
          />
        </td>

        {/* Updated */}
        <td className="incident-overview-cell">
          <span className="muted small">
            {formatIncidentTimestamp(incident.last_observed_at)}
          </span>
        </td>
      </tr>

      {/* Expanded details row */}
      {isExpanded && (
        <tr
          id={detailsId}
          className="incident-expanded-row"
          data-testid={`incident-expanded-${incident.incident_id}`}
        >
          <td colSpan={9} className="incident-expanded-cell">
            <IncidentExpandedDetails incident={incident} />
          </td>
        </tr>
      )}
    </React.Fragment>
  );
};

// ============================================================================
// Incidents table
// ============================================================================

interface IncidentsTableProps {
  incidents: ReadonlyArray<IncidentSummaryPayload>;
  model: IncidentsModel;
  dispatch: React.Dispatch<IncidentsMsg>;
}

/**
 * Renders incidents as an expandable table.
 */
export const IncidentsTable: React.FC<IncidentsTableProps> = ({
  incidents,
  model,
  dispatch,
}) => {
  if (incidents.length === 0) {
    return null;
  }

  return (
    <div className="incidents-table-wrapper" data-testid="incidents-table-wrapper">
      <table className="incidents-overview-table">
        <thead>
          <tr className="incident-overview-header-row">
            <th className="incident-overview-header incident-expand-header">
              Expand
            </th>
            <th className="incident-overview-header">Severity</th>
            <th className="incident-overview-header">Status</th>
            <th className="incident-overview-header">Object</th>
            <th className="incident-overview-header">Namespace</th>
            <th className="incident-overview-header">Evidence</th>
            <th className="incident-overview-header">Diagnosis</th>
            <th className="incident-overview-header">Review Packet</th>
            <th className="incident-overview-header">Updated</th>
          </tr>
        </thead>
        <tbody>
          {incidents.map((incident) => (
            <IncidentRow
              key={incident.incident_id}
              incident={incident}
              isExpanded={model.expandedIncidentIds.has(incident.incident_id)}
              dispatch={dispatch}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
};
