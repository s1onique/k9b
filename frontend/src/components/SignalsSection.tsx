/**
 * SignalsSection Component
 *
 * Signals section for incident detail view.
 * Shows all signals attached to the incident.
 */

import type { IncidentDetailPayload } from "../api";
import { formatIncidentTimestamp } from "./incident-view-model";

export interface SignalsSectionProps {
  signals: IncidentDetailPayload["signals"];
}

/**
 * Signals section - shows all signals attached to the incident.
 */
export const SignalsSection: React.FC<SignalsSectionProps> = ({ signals }) => {
  if (signals.length === 0) {
    return (
      <div className="incident-section">
        <div className="incident-section-header">
          <h4 className="incident-section-title">Signals</h4>
        </div>
        <div className="incident-section-content">
          <div className="incident-empty-state">
            <p className="muted small">No signals are attached to this incident yet.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="incident-section">
      <div className="incident-section-header">
        <h4 className="incident-section-title">Signals</h4>
      </div>
      <div className="incident-section-content">
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
                <span>Captured: {formatIncidentTimestamp(signal.captured_at)}</span>
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
    </div>
  );
};
