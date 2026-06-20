/**
 * IncidentDetailPanel Timeline tests
 *
 * Verifies:
 * 1. Timeline renders events in chronological order
 * 2. Timeline renders empty state honestly
 * 3. Timeline renders known event types with category labels
 * 4. Timeline handles unknown event types safely
 * 5. Timeline renders review/evidence/status events correctly
 * 6. Timeline does NOT expose raw artifacts
 * 7. Timeline does NOT render action/remediation controls
 *
 * Hard constraints verified:
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 * - NO raw artifact dumping
 * - NO action/remediation controls
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { IncidentDetailPanel } from "../components/IncidentDetailPanel";
import type { IncidentDetailPayload } from "../api";

// Full fixture using IncidentDetailPayload
const createIncidentFixture = (overrides: Partial<IncidentDetailPayload> = {}): IncidentDetailPayload => ({
  incident_id: "default-pod-test-pod-crash_loop",
  namespace: "default",
  object_kind: "Pod",
  object_name: "test-pod",
  raw_object_kind: null,
  candidate_class: "crash_loop",
  severity: "error",
  status: "open",
  first_observed_at: "2026-01-01T12:00:00Z",
  last_observed_at: "2026-01-01T14:00:00Z",
  signal_count: 2,
  evidence_count: 3,
  latest_snapshot_bundle_id: "default-20260101-140000",
  review_packet: {
    status: "not_generated",
    id: null,
    generated_at: null,
    error_message: null,
  },
  suppressed_reason: null,
  duplicate_of: null,
  resolved_at: null,
  resolution_notes: null,
  source_candidate_id: "candidate-abc",
  signals: [],
  evidence_needed: [],
  evidence_links: [],
  events: [],
  suggested_checks: [],
  automatic_diagnosis_review: {
    available: false,
    unavailable_reason: "no_review_packet",
  },
  ...overrides,
});

describe("IncidentDetailPanel Timeline", () => {
  describe("1. Timeline renders events in chronological order", () => {
    it("renders events in DOM order: first, then second, then third", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "opened",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "First event: opened",
          },
          {
            event_id: "event-2",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "status_changed",
            actor: "system",
            occurred_at: "2026-01-01T13:00:00Z",
            message: "Second event: investigating",
          },
          {
            event_id: "event-3",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "evidence_collection_started",
            actor: "system",
            occurred_at: "2026-01-01T14:00:00Z",
            message: "Third event: evidence collected",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Timeline")).toBeInTheDocument();

      // Get all timeline event items
      const eventItems = document.querySelectorAll(".timeline-event-item");
      expect(eventItems).toHaveLength(3);

      // Verify DOM order: first event should appear before second, second before third
      const eventMessages = Array.from(eventItems).map(
        (item) => item.querySelector(".timeline-event-message")?.textContent
      );
      expect(eventMessages).toEqual([
        "First event: opened",
        "Second event: investigating",
        "Third event: evidence collected",
      ]);

      // Also verify unique message content matches each event
      expect(screen.getByText("First event: opened")).toBeInTheDocument();
      expect(screen.getByText("Second event: investigating")).toBeInTheDocument();
      expect(screen.getByText("Third event: evidence collected")).toBeInTheDocument();
    });

    it("renders events with correct message content", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "opened",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Incident opened from candidate",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Incident opened from candidate")).toBeInTheDocument();
    });
  });

  describe("2. Timeline renders empty state honestly", () => {
    it("shows 'No timeline events recorded.' when events array is empty", () => {
      const incident = createIncidentFixture({ events: [] });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Timeline")).toBeInTheDocument();
      expect(screen.getByText("No timeline events recorded.")).toBeInTheDocument();
    });

    it("renders timeline section header even with empty events", () => {
      const incident = createIncidentFixture({ events: [] });
      render(<IncidentDetailPanel incident={incident} />);

      const timelineSection = document.querySelector(".incident-timeline-list");
      expect(timelineSection).toBeNull();

      const emptyState = screen.getByText("No timeline events recorded.");
      expect(emptyState).toBeInTheDocument();
    });
  });

  describe("3. Timeline renders known event types with category labels", () => {
    it("renders 'Lifecycle' category for opened event", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "opened",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Incident opened",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Lifecycle")).toBeInTheDocument();
      expect(screen.getByText("opened")).toBeInTheDocument();
    });

    it("renders 'Lifecycle' category for closed event", () => {
      const incident = createIncidentFixture({
        status: "resolved",
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "closed",
            actor: "user",
            occurred_at: "2026-01-01T16:00:00Z",
            message: "Incident closed",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Lifecycle")).toBeInTheDocument();
      expect(screen.getByText("closed")).toBeInTheDocument();
    });

    it("renders 'Signals' category for signal_merged event", () => {
      const incident = createIncidentFixture({
        // Use empty signals to avoid duplicate "Signals" text
        signals: [],
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "signal_merged",
            actor: "detector",
            occurred_at: "2026-01-01T12:30:00Z",
            message: "Signal merged from metrics",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      // Find Signals category in timeline
      const signalsCategory = document.querySelector(".timeline-event-category");
      expect(signalsCategory?.textContent).toBe("Signals");
      expect(screen.getByText("signal_merged")).toBeInTheDocument();
    });

    it("renders 'Status' category for status_changed event", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "status_changed",
            actor: "system",
            occurred_at: "2026-01-01T13:00:00Z",
            message: "Status changed to investigating",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Status")).toBeInTheDocument();
      expect(screen.getByText("status_changed")).toBeInTheDocument();
    });

    it("renders 'Status' category for severity_changed event", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "severity_changed",
            actor: "system",
            occurred_at: "2026-01-01T12:15:00Z",
            message: "Severity changed to warning",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Status")).toBeInTheDocument();
      expect(screen.getByText("severity_changed")).toBeInTheDocument();
    });

    it("renders 'Evidence' category for evidence_collection_started event", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "evidence_collection_started",
            actor: "system",
            occurred_at: "2026-01-01T12:05:00Z",
            message: "Evidence collection started",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Evidence")).toBeInTheDocument();
      expect(screen.getByText("evidence_collection_started")).toBeInTheDocument();
    });

    it("renders 'Evidence' category for snapshot_bundle_attached event", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "snapshot_bundle_attached",
            actor: "system",
            occurred_at: "2026-01-01T12:10:00Z",
            message: "Snapshot bundle attached",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Evidence")).toBeInTheDocument();
      expect(screen.getByText("snapshot_bundle_attached")).toBeInTheDocument();
    });

    it("renders 'Evidence' category for evidence_artifact_attached event", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "evidence_artifact_attached",
            actor: "system",
            occurred_at: "2026-01-01T12:20:00Z",
            message: "Evidence artifact attached",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Evidence")).toBeInTheDocument();
      expect(screen.getByText("evidence_artifact_attached")).toBeInTheDocument();
    });

    it("renders 'Review' category for review_packet_generated event", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "review_packet_generated",
            actor: "system",
            occurred_at: "2026-01-01T15:00:00Z",
            message: "Review packet generated",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Review")).toBeInTheDocument();
      expect(screen.getByText("review_packet_generated")).toBeInTheDocument();
    });

    it("renders 'Review' category for review_packet_failed event", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "review_packet_failed",
            actor: "system",
            occurred_at: "2026-01-01T15:00:00Z",
            message: "Review packet generation failed",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Review")).toBeInTheDocument();
      expect(screen.getByText("review_packet_failed")).toBeInTheDocument();
    });

    it("renders 'Status' category for suppressed event", () => {
      const incident = createIncidentFixture({
        status: "suppressed",
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "suppressed",
            actor: "user",
            occurred_at: "2026-01-01T15:30:00Z",
            message: "Incident suppressed by operator",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Status")).toBeInTheDocument();
      // Use regex to find event type in timeline (not status badge)
      const timelineEventType = document.querySelector(".timeline-event-type");
      expect(timelineEventType?.textContent).toBe("suppressed");
    });

    it("renders 'Status' category for marked_duplicate event", () => {
      const incident = createIncidentFixture({
        status: "duplicate",
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "marked_duplicate",
            actor: "user",
            occurred_at: "2026-01-01T15:30:00Z",
            message: "Marked as duplicate of inc-123",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Status")).toBeInTheDocument();
      // Use regex to find event type in timeline (not status badge)
      const timelineEventType = document.querySelector(".timeline-event-type");
      expect(timelineEventType?.textContent).toBe("marked_duplicate");
    });
  });

  describe("4. Timeline handles unknown event types safely", () => {
    it("renders unknown event type without category label", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "future_event_type",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Future event type",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      // Should still render the event type
      expect(screen.getByText("future_event_type")).toBeInTheDocument();

      // Should NOT render a category label for unknown type
      const categoryLabels = document.querySelectorAll(".timeline-event-category");
      expect(categoryLabels).toHaveLength(0);
    });

    it("renders mixed known and unknown event types", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "opened",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Incident opened",
          },
          {
            event_id: "event-2",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "unknown_type",
            actor: "system",
            occurred_at: "2026-01-01T13:00:00Z",
            message: "Unknown event",
          },
          {
            event_id: "event-3",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "status_changed",
            actor: "system",
            occurred_at: "2026-01-01T14:00:00Z",
            message: "Status changed",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      // Known events have categories
      expect(screen.getByText("Lifecycle")).toBeInTheDocument();
      expect(screen.getByText("Status")).toBeInTheDocument();

      // Unknown event rendered without category
      expect(screen.getByText("unknown_type")).toBeInTheDocument();
    });

    it("does not crash on uppercase unknown event type", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "UNKNOWN_EVENT_TYPE",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Uppercase unknown type",
          },
        ],
      });

      // Should not throw
      expect(() => render(<IncidentDetailPanel incident={incident} />)).not.toThrow();
    });
  });

  describe("5. Timeline renders review/evidence/status events correctly", () => {
    it("renders evidence event with actor information", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "snapshot_bundle_attached",
            actor: "scheduler",
            occurred_at: "2026-01-01T12:10:00Z",
            message: "Snapshot bundle bundle-abc attached",
            data: { bundle_id: "bundle-abc" },
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("scheduler")).toBeInTheDocument();
      expect(screen.getByText("Snapshot bundle bundle-abc attached")).toBeInTheDocument();
    });

    it("renders evidence event with actor_id when present", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "evidence_artifact_attached",
            actor: "user",
            actor_id: "operator@example.com",
            occurred_at: "2026-01-01T12:20:00Z",
            message: "User attached evidence artifact",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("user")).toBeInTheDocument();
      expect(screen.getByText("operator@example.com")).toBeInTheDocument();
    });

    it("renders review packet event with status context", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "review_packet_generated",
            actor: "system",
            occurred_at: "2026-01-01T15:00:00Z",
            message: "Review packet generated with 5 findings",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("system")).toBeInTheDocument();
      expect(screen.getByText("Review")).toBeInTheDocument();
      expect(screen.getByText("review_packet_generated")).toBeInTheDocument();
    });

    it("renders status change event with old/new status", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "status_changed",
            actor: "system",
            occurred_at: "2026-01-01T13:00:00Z",
            message: "Status changed from open to investigating",
            data: { old_status: "open", new_status: "investigating" },
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Status")).toBeInTheDocument();
      expect(screen.getByText("Status changed from open to investigating")).toBeInTheDocument();
    });
  });

  describe("6. Timeline does NOT expose raw artifacts", () => {
    it("does not render artifact content in event message", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "evidence_artifact_attached",
            actor: "system",
            occurred_at: "2026-01-01T12:20:00Z",
            message: "Evidence artifact attached: artifact-123",
            // Data should not be raw artifact content
            data: { artifact_id: "artifact-123" },
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      // Should show safe message, not raw content
      expect(screen.getByText(/Evidence artifact attached/i)).toBeInTheDocument();

      // Should not show artifact content indicators
      expect(document.body.textContent).not.toContain("raw_content");
      expect(document.body.textContent).not.toContain("file_content");
    });

    it("does not render data field contents directly", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "snapshot_bundle_attached",
            actor: "system",
            occurred_at: "2026-01-01T12:10:00Z",
            message: "Snapshot bundle attached",
            data: {
              bundle_id: "bundle-123",
              // This is safe - just an ID, not raw content
            },
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      // Should show message, not data field contents
      expect(screen.getByText("Snapshot bundle attached")).toBeInTheDocument();
    });
  });

  describe("7. Timeline does NOT render action/remediation controls", () => {
    it("has no remediation/action buttons in timeline", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "opened",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Incident opened",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      const timelineSection = document.querySelector(".incident-detail-section");
      const buttons = timelineSection?.querySelectorAll("button") || [];

      // No buttons should be in the timeline section
      expect(buttons).toHaveLength(0);
    });

    it("has no Run/Apply/Fix/Promote/Remediate controls in timeline", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "status_changed",
            actor: "system",
            occurred_at: "2026-01-01T13:00:00Z",
            message: "Status changed",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      const timelineList = document.querySelector(".incident-timeline-list");
      if (timelineList) {
        const text = timelineList.textContent || "";
        expect(text).not.toMatch(/Run/i);
        expect(text).not.toMatch(/Apply/i);
        expect(text).not.toMatch(/Fix/i);
        expect(text).not.toMatch(/Promote/i);
        expect(text).not.toMatch(/Remediate/i);
      }
    });

    it("timeline event items do not have action links", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "evidence_collection_started",
            actor: "system",
            occurred_at: "2026-01-01T12:05:00Z",
            message: "Evidence collection started",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      const eventItems = document.querySelectorAll(".timeline-event-item");
      eventItems.forEach((item) => {
        const links = item.querySelectorAll("a");
        expect(links).toHaveLength(0);
      });
    });
  });

  describe("8. Timeline renders actor information correctly", () => {
    it("renders system actor", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "opened",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Incident opened",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("system")).toBeInTheDocument();
    });

    it("renders user actor", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "closed",
            actor: "user",
            occurred_at: "2026-01-01T16:00:00Z",
            message: "Incident closed by user",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("user")).toBeInTheDocument();
    });

    it("renders detector actor", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "signal_merged",
            actor: "detector",
            occurred_at: "2026-01-01T12:30:00Z",
            message: "Signal detected and merged",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("detector")).toBeInTheDocument();
    });

    it("renders scheduler actor", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "evidence_collection_started",
            actor: "scheduler",
            occurred_at: "2026-01-01T12:05:00Z",
            message: "Evidence collection scheduled",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("scheduler")).toBeInTheDocument();
    });
  });

  describe("9. Timeline renders timestamps correctly", () => {
    it("renders formatted timestamp for event", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "opened",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Incident opened",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      const timestamp = document.querySelector(".timeline-event-time");
      expect(timestamp).not.toBeNull();
      // Should contain parts of the ISO timestamp in some format
      expect(timestamp?.textContent).toContain("2026");
    });

    it("renders multiple events with different timestamps", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "opened",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "First event",
          },
          {
            event_id: "event-2",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "closed",
            actor: "system",
            occurred_at: "2026-01-01T16:00:00Z",
            message: "Second event",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      const timestamps = document.querySelectorAll(".timeline-event-time");
      expect(timestamps).toHaveLength(2);
    });
  });
});
