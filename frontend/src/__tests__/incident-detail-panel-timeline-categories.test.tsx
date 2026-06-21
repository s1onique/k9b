/**
 * Tests for IncidentDetailPanel Timeline event categories.
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

describe("IncidentDetailPanel Timeline - Event Categories", () => {
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

  it("renders 'Status' category for suppressed event", () => {
    const incident = createIncidentFixture({
      events: [
        {
          event_id: "event-1",
          incident_id: "default-pod-test-pod-crash_loop",
          event_type: "suppressed",
          actor: "user",
          occurred_at: "2026-01-01T16:00:00Z",
          message: "Incident suppressed",
        },
      ],
    });
    render(<IncidentDetailPanel incident={incident} />);

    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("suppressed")).toBeInTheDocument();
  });

  it("renders 'Status' category for marked_duplicate event", () => {
    const incident = createIncidentFixture({
      events: [
        {
          event_id: "event-1",
          incident_id: "default-pod-test-pod-crash_loop",
          event_type: "marked_duplicate",
          actor: "user",
          occurred_at: "2026-01-01T16:00:00Z",
          message: "Marked as duplicate",
        },
      ],
    });
    render(<IncidentDetailPanel incident={incident} />);

    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("marked_duplicate")).toBeInTheDocument();
  });
});
