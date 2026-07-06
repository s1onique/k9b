/**
 * IncidentWarRoomHeader Component
 *
 * War room header section for incident detail view.
 * Shows: title, severity/status badges, source badges, summary grid.
 */

import type { IncidentDetailPayload } from "../api";
import {
  incidentDisplayTitle,
  incidentStatusLabel,
  incidentSeverityClass,
  incidentStatusClass,
  incidentClassLabel,
  incidentSourceBadges,
  incidentDiagnosisSummary,
  incidentDiagnosisLoopClass,
  incidentDiagnosisLoopLabel,
  formatIncidentTimestamp,
  getSignalSourceLabel,
  getSignalSourceClass,
} from "./incident-view-model";

export interface IncidentWarRoomHeaderProps {
  incident: IncidentDetailPayload;
}

/**
 * War Room Header - Top summary section with all key incident metadata.
 */
export const IncidentWarRoomHeader: React.FC<IncidentWarRoomHeaderProps> = ({ incident }) => {
  const sources = incidentSourceBadges(incident);
  const title = incidentDisplayTitle(incident);
  const diagnosisSummary = incidentDiagnosisSummary(incident);

  return (
    <div className="incident-war-room-header">
      <div className="incident-war-room-title">
        <span className={incidentSeverityClass(incident.severity)}>
          {incident.severity}
        </span>
        <span className={incidentStatusClass(incident.status)}>
          {incidentStatusLabel(incident)}
        </span>
        {sources.map((source) => (
          <span key={source} className={getSignalSourceClass(source)}>
            {getSignalSourceLabel(source)}
          </span>
        ))}
        <span className="incident-war-room-title-text">{title}</span>
      </div>

      <div className="incident-war-room-summary">
        <div className="incident-war-room-summary-item">
          <span className="incident-war-room-summary-label">Incident ID</span>
          <span className="incident-war-room-summary-value">{incident.incident_id}</span>
        </div>
        <div className="incident-war-room-summary-item">
          <span className="incident-war-room-summary-label">Status</span>
          <span className="incident-war-room-summary-value">{incidentStatusLabel(incident)}</span>
        </div>
        <div className="incident-war-room-summary-item">
          <span className="incident-war-room-summary-label">Severity</span>
          <span className="incident-war-room-summary-value">{incident.severity}</span>
        </div>
        <div className="incident-war-room-summary-item">
          <span className="incident-war-room-summary-label">Class</span>
          <span className="incident-war-room-summary-value">{incidentClassLabel(incident)}</span>
        </div>
        <div className="incident-war-room-summary-item">
          <span className="incident-war-room-summary-label">Primary Entity</span>
          <span className="incident-war-room-summary-value">
            {incident.raw_object_kind || incident.object_kind} {incident.object_name}
          </span>
        </div>
        <div className="incident-war-room-summary-item">
          <span className="incident-war-room-summary-label">Namespace</span>
          <span className="incident-war-room-summary-value">{incident.namespace}</span>
        </div>
        <div className="incident-war-room-summary-item">
          <span className="incident-war-room-summary-label">First Observed</span>
          <span className="incident-war-room-summary-value">
            {formatIncidentTimestamp(incident.first_observed_at)}
          </span>
        </div>
        <div className="incident-war-room-summary-item">
          <span className="incident-war-room-summary-label">Last Observed</span>
          <span className="incident-war-room-summary-value">
            {formatIncidentTimestamp(incident.last_observed_at)}
          </span>
        </div>
        <div className="incident-war-room-summary-item">
          <span className="incident-war-room-summary-label">Signal Count</span>
          <span className="incident-war-room-summary-value">{incident.signal_count}</span>
        </div>
        <div className="incident-war-room-summary-item">
          <span className="incident-war-room-summary-label">Evidence Count</span>
          <span className="incident-war-room-summary-value">{incident.evidence_count}</span>
        </div>
        <div className="incident-war-room-summary-item">
          <span className="incident-war-room-summary-label">Diagnosis State</span>
          <span className="incident-war-room-summary-value">
            <span className={incidentDiagnosisLoopClass(diagnosisSummary.status)}>
              {incidentDiagnosisLoopLabel(diagnosisSummary.status)}
            </span>
          </span>
        </div>
        {incident.latest_snapshot_bundle_id && (
          <div className="incident-war-room-summary-item">
            <span className="incident-war-room-summary-label">Snapshot Bundle</span>
            <span className="incident-war-room-summary-value">
              <code>{incident.latest_snapshot_bundle_id}</code>
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
