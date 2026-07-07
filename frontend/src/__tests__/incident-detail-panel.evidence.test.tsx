/**
 * IncidentDetailPanel tests - Signals and Evidence
 *
 * Verifies:
 * 1. Renders signals with provenance fields
 * 2. Renders empty signals state
 * 3. Renders evidence links with artifact_id and role
 * 4. Renders empty evidence links state
 * 5. Renders evidence_needed list
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { IncidentDetailPanel } from "../components/IncidentDetailPanel";
import { createIncidentFixture } from "./incident-detail-panel-test-utils";

describe("IncidentDetailPanel - Evidence", () => {
  describe("Signals", () => {
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

    it("shows empty state when signals array is empty", () => {
      const incident = createIncidentFixture({ signals: [] });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Signals")).toBeInTheDocument();
      expect(screen.getByText("No signals are attached to this incident yet.")).toBeInTheDocument();
    });
  });

  describe("Evidence Links", () => {
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

      expect(screen.getByText("Evidence Links")).toBeInTheDocument();
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

    it("shows empty state when evidence_links array is empty", () => {
      const incident = createIncidentFixture({ evidence_links: [] });
      render(<IncidentDetailPanel incident={incident} />);

      // When empty, component shows "Evidence" (not "Evidence Links") with empty state
      expect(screen.getByText("Evidence")).toBeInTheDocument();
      expect(screen.getByText("No evidence artifacts are attached to this incident yet.")).toBeInTheDocument();
    });
  });

  describe("Evidence Needed", () => {
    it("renders evidence_needed list when non-empty", () => {
      const incident = createIncidentFixture({
        evidence_needed: [
          "kubectl logs for test-pod",
          "describe output for test-deployment",
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      // Section header is "Evidence Needed"
      expect(screen.getByText("Evidence Needed")).toBeInTheDocument();
      expect(screen.getByText("kubectl logs for test-pod")).toBeInTheDocument();
      expect(screen.getByText("describe output for test-deployment")).toBeInTheDocument();
    });
  });
});
