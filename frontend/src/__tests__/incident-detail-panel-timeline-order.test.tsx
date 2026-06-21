/**
 * Tests for IncidentDetailPanel Timeline - chronological order and rendering.
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

describe("IncidentDetailPanel Timeline - Chronological Order", () => {
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

    const eventItems = document.querySelectorAll(".timeline-event-item");
    expect(eventItems).toHaveLength(3);

    const eventMessages = Array.from(eventItems).map(
      (item) => item.querySelector(".timeline-event-message")?.textContent
    );
    expect(eventMessages).toEqual([
      "First event: opened",
      "Second event: investigating",
      "Third event: evidence collected",
    ]);

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

describe("IncidentDetailPanel Timeline - Review Events", () => {
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
