/**
 * TimelineSection Component
 *
 * Timeline section for incident detail view.
 * Shows incident lifecycle events.
 */

import type { IncidentDetailPayload } from "../api";
import { formatIncidentTimestamp } from "./incident-view-model";

export interface TimelineSectionProps {
  events: IncidentDetailPayload["events"];
}

/**
 * Known event types with their category labels.
 * Unknown event types are rendered safely without category.
 */
const EVENT_TYPE_CATEGORIES: Record<string, string> = {
  opened: "Lifecycle",
  signal_merged: "Signals",
  severity_changed: "Status",
  evidence_collection_started: "Evidence",
  snapshot_bundle_attached: "Evidence",
  evidence_artifact_attached: "Evidence",
  review_packet_generated: "Review",
  review_packet_failed: "Review",
  status_changed: "Status",
  suppressed: "Status",
  marked_duplicate: "Status",
  closed: "Lifecycle",
  // Diagnosis loop events
  diagnosis_loop_started: "Diagnosis",
  diagnosis_loop_completed: "Diagnosis",
  diagnosis_loop_failed: "Diagnosis",
};

/**
 * Returns category label for an event type.
 * Returns undefined for unknown/future event types.
 */
const getEventCategory = (eventType: string): string | undefined => {
  return EVENT_TYPE_CATEGORIES[eventType.toLowerCase()];
};

/**
 * Timeline section - shows incident lifecycle events.
 */
export const TimelineSection: React.FC<TimelineSectionProps> = ({ events }) => {
  if (events.length === 0) {
    return (
      <div className="incident-section">
        <div className="incident-section-header">
          <h4 className="incident-section-title">Timeline</h4>
        </div>
        <div className="incident-section-content">
          <div className="incident-empty-state">
            <p className="muted small">No timeline events yet.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="incident-section">
      <div className="incident-section-header">
        <h4 className="incident-section-title">Timeline</h4>
      </div>
      <div className="incident-section-content">
        <ul className="incident-timeline-list">
          {events.map((event) => {
            const category = getEventCategory(event.event_type);
            return (
              <li key={event.event_id} className="timeline-event-item">
                <div className="timeline-event-header">
                  {category && (
                    <>
                      <span className={`timeline-event-category category-${category.toLowerCase()}`}>
                        {category}
                      </span>
                      <span className="muted small">·</span>
                    </>
                  )}
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
                  {formatIncidentTimestamp(event.occurred_at)}
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
};
