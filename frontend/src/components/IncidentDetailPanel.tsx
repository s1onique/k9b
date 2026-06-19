/**
 * IncidentDetailPanel Component
 *
 * Read-only UI for displaying full incident detail from IncidentDetailPayload.
 * Renders signals, evidence links, timeline events, and review packet state.
 *
 * Hard constraints enforced:
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 * - NO external tool invocation
 * - NO persistence
 * - NO write actions
 *
 * Uses:
 * - latest_snapshot_bundle_id (not snapshot_bundle_id)
 * - review_packet object (not review_packet_available + review_packet_id)
 */

import type { IncidentDetailPayload } from "../api";
import { IncidentDiagnosisLoopPanel } from "./IncidentDiagnosisLoopPanel";

export interface IncidentDetailPanelProps {
  incident: IncidentDetailPayload;
}

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
 * Renders review packet state section.
 */
const ReviewPacketSection: React.FC<{ reviewPacket: IncidentDetailPayload["review_packet"] }> = ({ reviewPacket }) => {
  return (
    <div className="incident-detail-section">
      <h4>Review packet</h4>
      <div className="review-packet-state">
        {reviewPacket.status === "not_generated" && (
          <span className="review-packet-pending-text">Not generated yet</span>
        )}
        {reviewPacket.status === "generating" && (
          <span className="review-packet-generating-text">Generating…</span>
        )}
        {reviewPacket.status === "available" && (
          <div className="review-packet-info">
            <span className="review-packet-badge">Available</span>
            {reviewPacket.id && (
              <code className="review-packet-id">{reviewPacket.id}</code>
            )}
          </div>
        )}
        {reviewPacket.status === "failed" && (
          <div className="review-packet-error">
            <span className="review-packet-error-text">
              Failed: {reviewPacket.error_message || "Unknown error"}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * Renders signals section.
 */
const SignalsSection: React.FC<{ signals: IncidentDetailPayload["signals"] }> = ({ signals }) => {
  if (signals.length === 0) {
    return (
      <div className="incident-detail-section">
        <h4>Signals</h4>
        <p className="muted small">No signals recorded.</p>
      </div>
    );
  }

  return (
    <div className="incident-detail-section">
      <h4>Signals</h4>
      <ul className="incident-signals-list">
        {signals.map((signal, index) => (
          <li key={index} className="signal-item">
            <div className="signal-header">
              <span className="signal-source">{signal.source}</span>
              <span className="muted small">·</span>
              <span className="signal-reason">{signal.reason}</span>
            </div>
            <div className="signal-message">{signal.message}</div>
            <div className="signal-meta muted small">
              <span>Captured: {formatTimestamp(signal.captured_at)}</span>
              {signal.run_id && (
                <>
                  <span>·</span>
                  <span>Run: {signal.run_id}</span>
                </>
              )}
              {signal.detector_id && (
                <>
                  <span>·</span>
                  <span>Detector: {signal.detector_id}</span>
                </>
              )}
              {signal.finding_id && (
                <>
                  <span>·</span>
                  <span>Finding: {signal.finding_id}</span>
                </>
              )}
              {signal.fingerprint && (
                <>
                  <span>·</span>
                  <span>FP: {signal.fingerprint.slice(0, 8)}…</span>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
};

/**
 * Renders evidence links section.
 */
const EvidenceLinksSection: React.FC<{ evidenceLinks: IncidentDetailPayload["evidence_links"] }> = ({ evidenceLinks }) => {
  if (evidenceLinks.length === 0) {
    return (
      <div className="incident-detail-section">
        <h4>Evidence links</h4>
        <p className="muted small">No evidence links attached.</p>
      </div>
    );
  }

  return (
    <div className="incident-detail-section">
      <h4>Evidence links</h4>
      <ul className="incident-evidence-links-list">
        {evidenceLinks.map((link, index) => (
          <li key={index} className="evidence-link-item">
            <div className="evidence-link-header">
              <span className="evidence-artifact-id">{link.artifact_id}</span>
              <span className="muted small">·</span>
              <span className="evidence-role">{link.role}</span>
            </div>
            <div className="evidence-meta muted small">
              Attached: {formatTimestamp(link.attached_at)}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
};

/**
 * Renders timeline events section.
 */
const TimelineSection: React.FC<{ events: IncidentDetailPayload["events"] }> = ({ events }) => {
  if (events.length === 0) {
    return (
      <div className="incident-detail-section">
        <h4>Timeline</h4>
        <p className="muted small">No timeline events recorded.</p>
      </div>
    );
  }

  return (
    <div className="incident-detail-section">
      <h4>Timeline</h4>
      <ul className="incident-timeline-list">
        {events.map((event) => (
          <li key={event.event_id} className="timeline-event-item">
            <div className="timeline-event-header">
              <span className="timeline-event-type">{event.event_type}</span>
              <span className="muted small">·</span>
              <span className="timeline-actor">{event.actor}</span>
              {event.actor_id && (
                <>
                  <span className="muted small">·</span>
                  <span className="timeline-actor-id muted small">{event.actor_id}</span>
                </>
              )}
            </div>
            <div className="timeline-event-message">{event.message}</div>
            <div className="timeline-event-time muted small">
              {formatTimestamp(event.occurred_at)}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
};

/**
 * Renders evidence needed section.
 */
const EvidenceNeededSection: React.FC<{ evidenceNeeded: IncidentDetailPayload["evidence_needed"] }> = ({ evidenceNeeded }) => {
  if (evidenceNeeded.length === 0) {
    return (
      <div className="incident-detail-section">
        <h4>Evidence needed</h4>
        <p className="muted small">No additional evidence requested.</p>
      </div>
    );
  }

  return (
    <div className="incident-detail-section">
      <h4>Evidence needed</h4>
      <ul className="incident-evidence-needed-list">
        {evidenceNeeded.map((item, index) => (
          <li key={index} className="evidence-needed-item">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
};

/**
 * Renders suggested checks section.
 * Read-only compatibility projection - no execution, promotion, or remediation.
 */
const SuggestedChecksSection: React.FC<{ suggestedChecks?: IncidentDetailPayload["suggested_checks"] }> = ({ suggestedChecks }) => {
  // Defensive: treat undefined/empty as empty state
  const checks = suggestedChecks ?? [];
  if (checks.length === 0) {
    return (
      <div className="incident-detail-section">
        <h4>Suggested checks</h4>
        <p className="muted small">No suggested checks linked to this incident yet.</p>
      </div>
    );
  }

  return (
    <div className="incident-detail-section">
      <h4>Suggested checks</h4>
      <p className="muted small">Read-only view. No execution, promotion, or remediation available.</p>
      <ul className="incident-suggested-checks-list">
        {checks.map((check, index) => (
          <li key={index} className="suggested-check-item">
            <div className="suggested-check-header">
              <span className="suggested-check-title">{check.title}</span>
              {check.risk_level && (
                <span className={`risk-badge risk-${check.risk_level.toLowerCase()}`}>
                  {check.risk_level}
                </span>
              )}
              <span className={`status-badge status-${check.status}`}>
                {check.status}
              </span>
            </div>
            <div className="suggested-check-rationale">{check.rationale}</div>
            <div className="suggested-check-meta muted small">
              <span>Source: {check.source}</span>
              {check.artifact_id && (
                <>
                  <span>·</span>
                  <span>Artifact: {check.artifact_id}</span>
                </>
              )}
              {check.run_id && (
                <>
                  <span>·</span>
                  <span>Run: {check.run_id}</span>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
};

/**
 * Read-only incident detail panel.
 * Displays full incident information including signals, evidence links, and timeline.
 */
export const IncidentDetailPanel: React.FC<IncidentDetailPanelProps> = ({ incident }) => {
  const displayKind = incident.raw_object_kind || incident.object_kind;

  return (
    <section className="panel incident-detail-panel">
      {/* Header / Identity */}
      <div className="incident-detail-header">
        <div className="incident-badges">
          <span className={`severity-badge ${getSeverityClass(incident.severity)}`}>
            {incident.severity}
          </span>
          <span className={`status-badge ${getStatusClass(incident.status)}`}>
            {incident.status.replace(/_/g, " ")}
          </span>
        </div>
        <div className="incident-identity">
          <span className="incident-id muted small">{incident.incident_id}</span>
        </div>
      </div>

      {/* Object info */}
      <div className="incident-detail-section incident-object-info">
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
      </div>

      {/* Counts and latest snapshot */}
      <div className="incident-detail-section incident-counts-section">
        <div className="incident-counts">
          <div className="count-item">
            <span className="muted small">Signals:</span>
            <span>{incident.signal_count}</span>
          </div>
          <div className="count-item">
            <span className="muted small">Evidence:</span>
            <span>{incident.evidence_count}</span>
          </div>
          {incident.latest_snapshot_bundle_id && (
            <div className="count-item">
              <span className="muted small">Latest snapshot bundle:</span>
              <code>{incident.latest_snapshot_bundle_id}</code>
            </div>
          )}
          {!incident.latest_snapshot_bundle_id && (
            <div className="count-item muted small">
              No snapshot bundle captured yet
            </div>
          )}
        </div>
      </div>

      {/* Timestamps */}
      <div className="incident-detail-section incident-timestamps">
        <div className="timestamp-row">
          <span className="muted small">First observed:</span>
          <span>{formatTimestamp(incident.first_observed_at)}</span>
        </div>
        <div className="timestamp-row">
          <span className="muted small">Last observed:</span>
          <span>{formatTimestamp(incident.last_observed_at)}</span>
        </div>
      </div>

      {/* Review packet state */}
      <ReviewPacketSection reviewPacket={incident.review_packet} />

      {/* Signals */}
      <SignalsSection signals={incident.signals} />

      {/* Evidence links */}
      <EvidenceLinksSection evidenceLinks={incident.evidence_links} />

      {/* Timeline */}
      <TimelineSection events={incident.events} />

      {/* Evidence needed */}
      <EvidenceNeededSection evidenceNeeded={incident.evidence_needed} />

      {/* Suggested checks - read-only compatibility projection */}
      <SuggestedChecksSection suggestedChecks={incident.suggested_checks} />

      {/* Manual diagnosis loop - one-pass only */}
      <IncidentDiagnosisLoopPanel
        incidentId={incident.incident_id}
        suggestedChecks={incident.suggested_checks}
      />

      {/* Read-only notice */}
      <div className="incident-detail-notice">
        <p className="muted small">
          Read-only view. No remediation, mutation, or LLM actions available.
        </p>
      </div>
    </section>
  );
};

export default IncidentDetailPanel;
