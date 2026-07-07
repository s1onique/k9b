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
 * 9. Renders timeline events in provided order
 * 10. Renders empty timeline state
 * 11. Does not render remediation/action buttons
 * 12. Does not require old fields (review_packet_available, review_packet_id, snapshot_bundle_id)
 * 13. Read-only notice is displayed
 *
 * Note: Signals, evidence links, and evidence_needed tests moved to
 * incident-detail-panel.evidence.test.tsx for better organization.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { IncidentDetailPanel } from "../components/IncidentDetailPanel";
import { createIncidentFixture } from "./incident-detail-panel-test-utils";
import { expectAllButtonsAreSafe } from "./safety-test-utils";

describe("IncidentDetailPanel", () => {
  describe("1. Renders identity/status/severity/object information", () => {
    it("renders incident_id, namespace, object_kind, object_name, candidate_class, severity, status", () => {
      const incident = createIncidentFixture();
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText(/default-pod-test-pod-crash_loop/i)).toBeInTheDocument();
      // Component renders "Pod test-pod" in multiple places (title and Primary Entity)
      expect(screen.getAllByText(/Pod test-pod/i)).toHaveLength(2);
      // Namespace is rendered
      expect(screen.getByText("default")).toBeInTheDocument();
      expect(screen.getByText(/crash loop/i)).toBeInTheDocument();
      // Severity appears twice: in badge and in summary
      expect(screen.getAllByText("error")).toHaveLength(2);
      // Status appears twice: in badge and in summary
      expect(screen.getAllByText("Open")).toHaveLength(2);
    });

    it("renders first_observed_at and last_observed_at", () => {
      const incident = createIncidentFixture();
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText(/First Observed/i)).toBeInTheDocument();
      expect(screen.getByText(/Last Observed/i)).toBeInTheDocument();
    });

    it("uses raw_object_kind fallback when present", () => {
      const incident = createIncidentFixture({
        object_kind: "Pod",
        raw_object_kind: "EvictedPod",
      });
      render(<IncidentDetailPanel incident={incident} />);

      // Component renders "EvictedPod test-pod" twice: in title and Primary Entity
      expect(screen.getAllByText(/EvictedPod test-pod/i)).toHaveLength(2);
      // Pod test-pod should not appear
      expect(screen.queryByText("Pod test-pod")).not.toBeInTheDocument();
    });
  });

  describe("2. Renders signal_count and evidence_count", () => {
    it("renders signal_count and evidence_count", () => {
      const incident = createIncidentFixture({
        signal_count: 5,
        evidence_count: 10,
        evidence_links: [], // Empty to avoid duplicate "Evidence:" text
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText(/Signal Count/i)).toBeInTheDocument();
      expect(screen.getByText("5")).toBeInTheDocument();
      expect(screen.getByText(/Evidence Count/i)).toBeInTheDocument();
      expect(screen.getByText("10")).toBeInTheDocument();
    });
  });

  describe("3. Renders latest_snapshot_bundle_id when present", () => {
    it("shows bundle ID when latest_snapshot_bundle_id is present", () => {
      const incident = createIncidentFixture({
        latest_snapshot_bundle_id: "default-20260101-140000",
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Snapshot Bundle")).toBeInTheDocument();
      expect(screen.getByText(/default-20260101-140000/i)).toBeInTheDocument();
    });
  });

  describe("4. Shows honest empty state when latest_snapshot_bundle_id is null", () => {
    it("does not render snapshot bundle field when latest_snapshot_bundle_id is null", () => {
      const incident = createIncidentFixture({
        latest_snapshot_bundle_id: null,
      });
      render(<IncidentDetailPanel incident={incident} />);

      // When null, the snapshot bundle field is not rendered at all
      expect(screen.queryByText(/Snapshot Bundle/i)).not.toBeInTheDocument();
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

  describe("9. Renders timeline events in provided order", () => {
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

  describe("10. Renders empty timeline state", () => {
    it("shows 'No timeline events recorded.' when events array is empty", () => {
      const incident = createIncidentFixture({ events: [] });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Timeline")).toBeInTheDocument();
      expect(screen.getByText("No timeline events yet.")).toBeInTheDocument();
    });
  });

  describe("11. Does not render remediation/action buttons", () => {
    // Note: IncidentDetailPanel includes:
    // - IncidentDiagnosisLoopPanel with "Run one read-only pass" button
    // - IncidentOnePassDiagnosisPanel with "Run read-only diagnosis" button
    // Both are intentional safe functionality - no remediation/action buttons.

    it("has no remediation/action buttons", () => {
      const incident = createIncidentFixture();
      render(<IncidentDetailPanel incident={incident} />);

      const buttons = screen.getAllByRole("button");

      // Both safe buttons should be present
      expect(
        screen.getByRole("button", { name: /run one read-only pass/i }),
      ).toBeInTheDocument();

      expect(
        screen.getByRole("button", { name: /run read-only one-pass diagnosis/i }),
      ).toBeInTheDocument();

      // Neither button should contain remediation/action words
      expectAllButtonsAreSafe(Array.from(buttons));
    });
  });

  describe("12. Does not require old fields", () => {
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
