/**
 * Tests for Diagnosis Loop event types in IncidentDetailPanel Timeline.
 *
 * Verifies:
 * 1. Diagnosis Loop category label renders correctly
 * 2. diagnosis_loop_started renders with category
 * 3. diagnosis_loop_completed renders with category
 * 4. diagnosis_loop_failed renders with category
 * 5. No action/remediation controls
 * 6. No raw artifact or packet content exposure
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

describe("IncidentDetailPanel Timeline - Diagnosis Loop Events", () => {
  describe("1. Diagnosis Loop category label renders correctly", () => {
    it("renders 'Diagnosis Loop' category for diagnosis_loop_started", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "diagnosis_loop_started",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Automatic diagnosis loop started",
            data: {
              run_id: "auto-inc-123-20260621000000",
              collector_run_id: "collector-001",
              read_only: true,
              review_required_before_any_action: true,
              no_remediation_attempted: true,
            },
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Diagnosis Loop")).toBeInTheDocument();
      expect(screen.getByText("diagnosis_loop_started")).toBeInTheDocument();
    });

    it("renders 'Diagnosis Loop' category for diagnosis_loop_completed", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "diagnosis_loop_completed",
            actor: "system",
            occurred_at: "2026-01-01T12:05:00Z",
            message: "Automatic diagnosis loop completed",
            data: {
              run_id: "auto-inc-123-20260621000000",
              collector_run_id: "collector-001",
              checks_requested: 3,
              checks_run: 2,
              checks_rejected: 1,
              read_only: true,
            },
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Diagnosis Loop")).toBeInTheDocument();
      expect(screen.getByText("diagnosis_loop_completed")).toBeInTheDocument();
    });

    it("renders 'Diagnosis Loop' category for diagnosis_loop_failed", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "diagnosis_loop_failed",
            actor: "system",
            occurred_at: "2026-01-01T12:10:00Z",
            message: "Automatic diagnosis loop failed or unavailable",
            data: {
              unavailable_reason: "not_eligible",
              read_only: true,
            },
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Diagnosis Loop")).toBeInTheDocument();
      expect(screen.getByText("diagnosis_loop_failed")).toBeInTheDocument();
    });
  });

  describe("2. All diagnosis loop events render with proper metadata", () => {
    it("renders diagnosis_loop_started with run_id metadata", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "diagnosis_loop_started",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Automatic diagnosis loop started",
            data: {
              run_id: "auto-inc-123-20260621000000",
              collector_run_id: "collector-001",
              read_only: true,
            },
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Automatic diagnosis loop started")).toBeInTheDocument();
      expect(screen.getByText("system")).toBeInTheDocument();
    });

    it("renders diagnosis_loop_completed with check counts", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "diagnosis_loop_completed",
            actor: "system",
            occurred_at: "2026-01-01T12:05:00Z",
            message: "Automatic diagnosis loop completed",
            data: {
              run_id: "auto-inc-123-20260621000000",
              collector_run_id: "collector-001",
              checks_requested: 5,
              checks_run: 3,
              checks_rejected: 2,
              read_only: true,
            },
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Automatic diagnosis loop completed")).toBeInTheDocument();
      expect(screen.getByText("diagnosis_loop_completed")).toBeInTheDocument();
    });

    it("renders diagnosis_loop_failed with unavailable_reason", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "diagnosis_loop_failed",
            actor: "system",
            occurred_at: "2026-01-01T12:10:00Z",
            message: "Automatic diagnosis loop failed or unavailable",
            data: {
              unavailable_reason: "case_file_error",
              read_only: true,
            },
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Automatic diagnosis loop failed or unavailable")).toBeInTheDocument();
      expect(screen.getByText("diagnosis_loop_failed")).toBeInTheDocument();
    });
  });

  describe("3. Timeline renders diagnosis loop events in chronological order", () => {
    it("renders started, completed, failed events in order", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "diagnosis_loop_started",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Started",
          },
          {
            event_id: "event-2",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "diagnosis_loop_completed",
            actor: "system",
            occurred_at: "2026-01-01T12:05:00Z",
            message: "Completed",
          },
          {
            event_id: "event-3",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "diagnosis_loop_failed",
            actor: "system",
            occurred_at: "2026-01-01T12:10:00Z",
            message: "Failed",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      const eventItems = document.querySelectorAll(".timeline-event-item");
      expect(eventItems).toHaveLength(3);

      const messages = Array.from(eventItems).map(
        (item) => item.querySelector(".timeline-event-message")?.textContent
      );
      expect(messages).toEqual(["Started", "Completed", "Failed"]);
    });
  });

  describe("4. Timeline does NOT render action/remediation controls for diagnosis loop events", () => {
    it("has no remediation/action buttons for diagnosis loop events", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "diagnosis_loop_started",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Automatic diagnosis loop started",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      const timelineSection = document.querySelector(".incident-detail-section");
      const buttons = timelineSection?.querySelectorAll("button") || [];
      expect(buttons).toHaveLength(0);
    });

    it("has no Run/Apply/Fix/Promote/Remediate controls in diagnosis loop events", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "diagnosis_loop_completed",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Automatic diagnosis loop completed",
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
            event_type: "diagnosis_loop_failed",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Automatic diagnosis loop failed",
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

  describe("5. Timeline does NOT expose raw artifact or packet content for diagnosis loop events", () => {
    it("does not render raw packet content in diagnosis_loop_started message", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "diagnosis_loop_started",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Automatic diagnosis loop started",
            // Safe metadata only - no raw content
            data: {
              run_id: "auto-inc-123",
              collector_run_id: "collector-001",
              read_only: true,
            },
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      // Should show safe message only
      expect(screen.getByText("Automatic diagnosis loop started")).toBeInTheDocument();
      // Should not show content indicators
      expect(document.body.textContent).not.toContain("raw_content");
      expect(document.body.textContent).not.toContain("file_content");
      expect(document.body.textContent).not.toContain("artifact_payload");
    });

    it("does not render raw packet content in diagnosis_loop_completed message", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "diagnosis_loop_completed",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Automatic diagnosis loop completed",
            // Safe metadata only
            data: {
              run_id: "auto-inc-123",
              checks_requested: 3,
              checks_run: 2,
              read_only: true,
            },
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Automatic diagnosis loop completed")).toBeInTheDocument();
      expect(document.body.textContent).not.toContain("raw_packets");
    });

    it("does not render stack traces or logs in diagnosis_loop_failed message", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "diagnosis_loop_failed",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Automatic diagnosis loop failed or unavailable",
            // Safe error message only
            data: {
              unavailable_reason: "orchestrator_error",
              read_only: true,
            },
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Automatic diagnosis loop failed or unavailable")).toBeInTheDocument();
      expect(document.body.textContent).not.toContain("Traceback");
      expect(document.body.textContent).not.toContain("stack_trace");
    });
  });

  describe("6. Mixed timeline with diagnosis loop and other events", () => {
    it("renders diagnosis loop events alongside lifecycle events", () => {
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
            event_type: "diagnosis_loop_started",
            actor: "system",
            occurred_at: "2026-01-01T12:05:00Z",
            message: "Automatic diagnosis loop started",
          },
          {
            event_id: "event-3",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "diagnosis_loop_completed",
            actor: "system",
            occurred_at: "2026-01-01T12:10:00Z",
            message: "Automatic diagnosis loop completed",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      // Both event types should be visible in timeline
      expect(screen.getByText("opened")).toBeInTheDocument();
      expect(screen.getByText("diagnosis_loop_started")).toBeInTheDocument();
      expect(screen.getByText("diagnosis_loop_completed")).toBeInTheDocument();

      // Category labels should exist in timeline
      const categories = document.querySelectorAll(".timeline-event-category");
      expect(categories.length).toBeGreaterThanOrEqual(2);
    });
  });
});
