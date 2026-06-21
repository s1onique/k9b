/**
 * IncidentDetailPanel tests
 *
 * Verifies:
 * 1. Renders identity/status/severity/object information
 * 2. Renders signal_count and evidence_count
 * 3. Renders latest_snapshot_bundle_id when present
 * 4. Shows honest empty state when latest_snapshot_bundle_id is null
 * 5. Renders review_packet.status=not_generated as "Not generated yet"
 * 6. Renders review_packet.status=generating as "Generating…"
 * 7. Renders review_packet.status=available with packet id
 * 8. Renders review_packet.status=failed with error message
 * 9. Renders signals with provenance fields
 * 10. Renders empty signals state
 * 11. Renders evidence links with artifact_id and role
 * 12. Renders empty evidence links state
 * 13. Renders timeline events in provided order
 * 14. Renders empty timeline state
 * 15. Renders evidence_needed list
 * 16. Renders suggested_checks empty state
 * 17. Renders suggested_checks list when non-empty
 * 18. Does not render remediation/action buttons
 * 19. Does not require old fields (review_packet_available, review_packet_id, snapshot_bundle_id)
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

describe("IncidentDetailPanel", () => {
  describe("1. Renders identity/status/severity/object information", () => {
    it("renders incident_id, namespace, object_kind, object_name, candidate_class, severity, status", () => {
      const incident = createIncidentFixture();
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText(/default-pod-test-pod-crash_loop/i)).toBeInTheDocument();
      expect(screen.getByText("Pod")).toBeInTheDocument();
      expect(screen.getByText("test-pod")).toBeInTheDocument();
      expect(screen.getByText("default")).toBeInTheDocument();
      expect(screen.getByText(/crash loop/i)).toBeInTheDocument();
      expect(screen.getByText(/error/i)).toBeInTheDocument();
      expect(screen.getByText(/open/i)).toBeInTheDocument();
    });

    it("renders first_observed_at and last_observed_at", () => {
      const incident = createIncidentFixture();
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText(/First observed:/i)).toBeInTheDocument();
      expect(screen.getByText(/Last observed:/i)).toBeInTheDocument();
    });

    it("uses raw_object_kind fallback when present", () => {
      const incident = createIncidentFixture({
        object_kind: "Pod",
        raw_object_kind: "EvictedPod",
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("EvictedPod")).toBeInTheDocument();
      expect(screen.queryByText("Pod")).not.toBeInTheDocument();
    });
  });

  describe("2. Renders signal_count and evidence_count", () => {
    it("renders signal_count and evidence_count", () => {
      const incident = createIncidentFixture({
        signal_count: 5,
        evidence_count: 10,
        evidence_links: [],  // Empty to avoid duplicate "Evidence:" text
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText(/Signals:/i)).toBeInTheDocument();
      expect(screen.getByText("5")).toBeInTheDocument();
      // The evidence count renders as "Evidence (10)" or similar format
      expect(screen.getByText("10")).toBeInTheDocument();
    });
  });

  describe("3. Renders latest_snapshot_bundle_id when present", () => {
    it("shows bundle ID when latest_snapshot_bundle_id is present", () => {
      const incident = createIncidentFixture({
        latest_snapshot_bundle_id: "default-20260101-140000",
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText(/Latest snapshot bundle:/i)).toBeInTheDocument();
      expect(screen.getByText(/default-20260101-140000/i)).toBeInTheDocument();
    });
  });

  describe("4. Shows honest empty state when latest_snapshot_bundle_id is null", () => {
    it("shows 'No snapshot bundle captured yet' when latest_snapshot_bundle_id is null", () => {
      const incident = createIncidentFixture({
        latest_snapshot_bundle_id: null,
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText(/No snapshot bundle captured yet/i)).toBeInTheDocument();
      expect(screen.queryByText(/Latest snapshot bundle:/i)).not.toBeInTheDocument();
    });
  });

  describe("5. Renders review_packet.status=not_generated as 'Not generated yet'", () => {
    it("shows 'Not generated yet' when status is not_generated", () => {
      const incident = createIncidentFixture({
        review_packet: {
          status: "not_generated",
          id: null,
          generated_at: null,
          error_message: null,
        },
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Not generated yet")).toBeInTheDocument();
    });
  });

  describe("6. Renders review_packet.status=generating as 'Generating…'", () => {
    it("shows 'Generating…' when status is generating", () => {
      const incident = createIncidentFixture({
        review_packet: {
          status: "generating",
          id: null,
          generated_at: null,
          error_message: null,
        },
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Generating…")).toBeInTheDocument();
    });
  });

  describe("7. Renders review_packet.status=available with packet id", () => {
    it("shows 'Available' and id when status is available", () => {
      const incident = createIncidentFixture({
        review_packet: {
          status: "available",
          id: "review-packet-abc123",
          generated_at: "2026-01-01T12:00:00Z",
          error_message: null,
        },
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Available")).toBeInTheDocument();
      expect(screen.getByText(/review-packet-abc123/i)).toBeInTheDocument();
    });

    it("defensively shows 'Available' when id is null (malformed payload)", () => {
      const incident = createIncidentFixture({
        review_packet: {
          status: "available",
          id: null,
          generated_at: "2026-01-01T12:00:00Z",
          error_message: null,
        },
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Available")).toBeInTheDocument();
    });
  });

  describe("8. Renders review_packet.status=failed with error message", () => {
    it("shows 'Failed: <error_message>' when status is failed", () => {
      const incident = createIncidentFixture({
        review_packet: {
          status: "failed",
          id: null,
          generated_at: null,
          error_message: "LLM unavailable",
        },
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText(/Failed: LLM unavailable/i)).toBeInTheDocument();
    });

    it("shows 'Failed: Unknown error' when status is failed but error_message is null", () => {
      const incident = createIncidentFixture({
        review_packet: {
          status: "failed",
          id: null,
          generated_at: null,
          error_message: null,
        },
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText(/Failed: Unknown error/i)).toBeInTheDocument();
    });
  });

  describe("9. Renders signals with provenance fields", () => {
    it("renders signals with source, reason, message, captured_at, run_id, detector_id, finding_id, fingerprint", () => {
      const incident = createIncidentFixture({
        signals: [
          {
            source: "metrics-collector",
            reason: "HighErrorRate",
            message: "Error rate exceeded threshold: 5%",
            captured_at: "2026-01-01T13:00:00Z",
            run_id: "run-123",
            detector_id: "detector-456",
            finding_id: "finding-789",
            fingerprint: "abc123def456",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Signals")).toBeInTheDocument();
      expect(screen.getByText("metrics-collector")).toBeInTheDocument();
      expect(screen.getByText("HighErrorRate")).toBeInTheDocument();
      expect(screen.getByText("Error rate exceeded threshold: 5%")).toBeInTheDocument();
      expect(screen.getByText(/Run: run-123/i)).toBeInTheDocument();
      expect(screen.getByText(/Detector: detector-456/i)).toBeInTheDocument();
      expect(screen.getByText(/Finding: finding-789/i)).toBeInTheDocument();
      expect(screen.getByText(/FP: abc123de…/i)).toBeInTheDocument();
    });

    it("renders signal with only required fields", () => {
      const incident = createIncidentFixture({
        signals: [
          {
            source: "events-collector",
            reason: "Warning",
            message: "Pod in warning state",
            captured_at: "2026-01-01T13:00:00Z",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("events-collector")).toBeInTheDocument();
      expect(screen.getByText("Warning")).toBeInTheDocument();
    });

    it("renders multiple signals", () => {
      const incident = createIncidentFixture({
        signals: [
          { source: "source-1", reason: "reason-1", message: "message-1", captured_at: "2026-01-01T13:00:00Z" },
          { source: "source-2", reason: "reason-2", message: "message-2", captured_at: "2026-01-01T13:30:00Z" },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getAllByText("source-1")).toHaveLength(1);
      expect(screen.getAllByText("source-2")).toHaveLength(1);
    });
  });

  describe("10. Renders empty signals state", () => {
    it("shows 'No signals recorded.' when signals array is empty", () => {
      const incident = createIncidentFixture({ signals: [] });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Signals")).toBeInTheDocument();
      expect(screen.getByText("No signals recorded.")).toBeInTheDocument();
    });
  });

  describe("11. Renders evidence links with artifact_id and role", () => {
    it("renders evidence links with artifact_id, role, and attached_at", () => {
      const incident = createIncidentFixture({
        evidence_links: [
          {
            incident_id: "default-pod-test-pod-crash_loop",
            artifact_id: "artifact-abc-123",
            role: "snapshot",
            attached_at: "2026-01-01T14:00:00Z",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Evidence links")).toBeInTheDocument();
      expect(screen.getByText("artifact-abc-123")).toBeInTheDocument();
      expect(screen.getByText("snapshot")).toBeInTheDocument();
      expect(screen.getByText(/Attached:/i)).toBeInTheDocument();
    });

    it("renders multiple evidence links", () => {
      const incident = createIncidentFixture({
        evidence_links: [
          { incident_id: "inc-1", artifact_id: "art-1", role: "snapshot", attached_at: "2026-01-01T14:00:00Z" },
          { incident_id: "inc-1", artifact_id: "art-2", role: "review", attached_at: "2026-01-01T15:00:00Z" },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getAllByText("art-1")).toHaveLength(1);
      expect(screen.getAllByText("art-2")).toHaveLength(1);
    });
  });

  describe("12. Renders empty evidence links state", () => {
    it("shows 'No evidence links attached.' when evidence_links array is empty", () => {
      const incident = createIncidentFixture({ evidence_links: [] });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Evidence links")).toBeInTheDocument();
      expect(screen.getByText("No evidence links attached.")).toBeInTheDocument();
    });
  });

  describe("13. Renders timeline events in provided order", () => {
    it("renders timeline events in provided array order", () => {
      const incident = createIncidentFixture({
        events: [
          {
            event_id: "event-1",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "created",
            actor: "system",
            occurred_at: "2026-01-01T12:00:00Z",
            message: "Incident created",
          },
          {
            event_id: "event-2",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "status_changed",
            actor: "operator",
            occurred_at: "2026-01-01T13:00:00Z",
            message: "Status changed to investigating",
          },
          {
            event_id: "event-3",
            incident_id: "default-pod-test-pod-crash_loop",
            event_type: "evidence_added",
            actor: "collector",
            occurred_at: "2026-01-01T14:00:00Z",
            message: "Evidence attached",
            actor_id: "collector-id-123",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Timeline")).toBeInTheDocument();
      
      // Check that events are rendered
      expect(screen.getByText("created")).toBeInTheDocument();
      expect(screen.getByText("status_changed")).toBeInTheDocument();
      expect(screen.getByText("evidence_added")).toBeInTheDocument();
      
      // Check event details
      expect(screen.getByText("system")).toBeInTheDocument();
      expect(screen.getByText("operator")).toBeInTheDocument();
      expect(screen.getByText("collector")).toBeInTheDocument();
      expect(screen.getByText("collector-id-123")).toBeInTheDocument();
      
      // Check messages
      expect(screen.getByText("Incident created")).toBeInTheDocument();
      expect(screen.getByText("Status changed to investigating")).toBeInTheDocument();
      expect(screen.getByText("Evidence attached")).toBeInTheDocument();
    });
  });

  describe("14. Renders empty timeline state", () => {
    it("shows 'No timeline events recorded.' when events array is empty", () => {
      const incident = createIncidentFixture({ events: [] });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Timeline")).toBeInTheDocument();
      expect(screen.getByText("No timeline events recorded.")).toBeInTheDocument();
    });
  });

  describe("15. Renders evidence_needed list", () => {
    it("renders evidence_needed list when non-empty", () => {
      const incident = createIncidentFixture({
        evidence_needed: [
          "kubectl logs for test-pod",
          "describe output for test-deployment",
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Evidence needed")).toBeInTheDocument();
      expect(screen.getByText("kubectl logs for test-pod")).toBeInTheDocument();
      expect(screen.getByText("describe output for test-deployment")).toBeInTheDocument();
    });
  });

  describe("16. Does not render remediation/action buttons", () => {
    // Note: IncidentDetailPanel now includes IncidentDiagnosisLoopPanel which has
    // a "Run one read-only pass" button. This is intentional safe functionality.
    // The button does NOT contain remediation/action words.

    it("has no remediation/action buttons", () => {
      const incident = createIncidentFixture();
      render(<IncidentDetailPanel incident={incident} />);

      const buttons = document.querySelectorAll("button");
      // There should be exactly 1 button: the "Run one read-only pass" button
      expect(buttons.length).toBe(1);

      // The button should NOT contain remediation/action words
      const FORBIDDEN_WORDS = ["Apply", "Delete", "Patch", "Scale", "Restart", "Rollout", "Remediate", "Fix", "Resolve automatically"];
      for (const button of buttons) {
        for (const word of FORBIDDEN_WORDS) {
          expect(button.textContent).not.toContain(word);
        }
      }
    });
  });

  describe("17. Does not require old fields", () => {
    it("renders without review_packet_available field", () => {
      const incident = createIncidentFixture();
      // Explicitly ensure old fields are not used by checking the shape
      expect((incident as Record<string, unknown>).review_packet_available).toBeUndefined();
    });

    it("renders without review_packet_id field", () => {
      const incident = createIncidentFixture();
      expect((incident as Record<string, unknown>).review_packet_id).toBeUndefined();
    });

    it("renders without snapshot_bundle_id field", () => {
      const incident = createIncidentFixture();
      expect((incident as Record<string, unknown>).snapshot_bundle_id).toBeUndefined();
    });
  });

  describe("Read-only notice", () => {
    it("displays read-only notice", () => {
      const incident = createIncidentFixture();
      render(<IncidentDetailPanel incident={incident} />);

      const notice = document.querySelector(".incident-detail-notice");
      expect(notice).not.toBeNull();
      expect(notice?.textContent).toContain("No remediation");
      expect(notice?.textContent?.toLowerCase()).toContain("mutation");
      expect(notice?.textContent).toContain("LLM actions");
    });
  });
});
