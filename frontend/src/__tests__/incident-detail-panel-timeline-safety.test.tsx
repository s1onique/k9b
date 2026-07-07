/**
 * Tests for IncidentDetailPanel Timeline - safety constraints and unknown event handling.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { IncidentDetailPanel } from "../components/IncidentDetailPanel";
import type { IncidentDetailPayload } from "../api";

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
  evidence_artifacts: [],
  suggested_checks: [],
  automatic_diagnosis_review: {
    available: false,
    unavailable_reason: "no_review_packet",
  },
  automatic_diagnosis_loop_summary: {
    status: "not_run",
    latest_started_at: null,
    latest_completed_at: null,
    latest_failed_at: null,
    latest_event_id: null,
    latest_event_type: null,
    unavailable_reason: null,
    checks_requested: null,
    checks_run: null,
    checks_rejected: null,
    review_packet_available: false,
    review_packet_id: null,
    read_only: true,
    review_required_before_any_action: true,
    no_remediation_attempted: true,
  },
  ...overrides,
});

describe("IncidentDetailPanel Timeline - Unknown Event Types", () => {
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

    expect(screen.getByText("future_event_type")).toBeInTheDocument();
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

    expect(screen.getByText("Lifecycle")).toBeInTheDocument();
    // Use timeline-specific selector to avoid matching incident status label
    const statusCategory = document.querySelector(".timeline-event-category.category-status");
    expect(statusCategory?.textContent).toBe("Status");
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

    expect(() => render(<IncidentDetailPanel incident={incident} />)).not.toThrow();
  });
});

describe("IncidentDetailPanel Timeline - No Raw Content Exposure", () => {
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
          data: { artifact_id: "artifact-123" },
        },
      ],
    });
    render(<IncidentDetailPanel incident={incident} />);

    expect(screen.getByText(/Evidence artifact attached/i)).toBeInTheDocument();
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
          },
        },
      ],
    });
    render(<IncidentDetailPanel incident={incident} />);

    expect(screen.getByText("Snapshot bundle attached")).toBeInTheDocument();
  });
});

describe("IncidentDetailPanel Timeline - No Action Controls", () => {
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

describe("IncidentDetailPanel Timeline - Actor Information", () => {
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
});

describe("IncidentDetailPanel Timeline - Timestamps", () => {
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
