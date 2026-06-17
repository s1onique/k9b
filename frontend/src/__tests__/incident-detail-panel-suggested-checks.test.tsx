/**
 * IncidentDetailPanel suggested_checks tests
 *
 * Verifies:
 * 1. Renders suggested_checks empty state
 * 2. Renders suggested_checks list when non-empty
 * 3. Does not render action buttons for suggested checks
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
  ...overrides,
});

describe("IncidentDetailPanel suggested_checks", () => {
  describe("Renders suggested_checks empty state", () => {
    it("shows 'No suggested checks linked to this incident yet.' when empty", () => {
      const incident = createIncidentFixture({ suggested_checks: [] });
      render(<IncidentDetailPanel incident={incident} />);
      expect(screen.getByText("Suggested checks")).toBeInTheDocument();
      expect(screen.getByText("No suggested checks linked to this incident yet.")).toBeInTheDocument();
    });

    it("renders Suggested checks section by default (empty list)", () => {
      const incident = createIncidentFixture();
      render(<IncidentDetailPanel incident={incident} />);
      expect(screen.getByText("Suggested checks")).toBeInTheDocument();
    });
  });

  describe("Renders suggested_checks list when non-empty", () => {
    it("renders single suggested check with title, rationale, source, status, and provenance", () => {
      const incident = createIncidentFixture({
        suggested_checks: [
          {
            check_id: "check-001",
            title: "Inspect pod logs for test-pod",
            rationale: "CrashLoopBackOff typically leaves informative logs",
            source: "next-check-planning",
            risk_level: "LOW",
            status: "suggested" as const,
            artifact_id: "plan-artifact-abc",
            run_id: "run-123",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Suggested checks")).toBeInTheDocument();
      expect(screen.getByText("Inspect pod logs for test-pod")).toBeInTheDocument();
      expect(screen.getByText("CrashLoopBackOff typically leaves informative logs")).toBeInTheDocument();
      expect(screen.getByText("Source: next-check-planning")).toBeInTheDocument();
      expect(screen.getByText("suggested")).toBeInTheDocument();
      expect(screen.getByText("Artifact: plan-artifact-abc")).toBeInTheDocument();
      expect(screen.getByText("Run: run-123")).toBeInTheDocument();
    });

    it("renders multiple suggested checks", () => {
      const incident = createIncidentFixture({
        suggested_checks: [
          {
            check_id: "check-001",
            title: "Check pod logs",
            rationale: "First diagnostic step",
            source: "next-check-planning",
            risk_level: "LOW",
            status: "suggested" as const,
            artifact_id: null,
            run_id: null,
          },
          {
            check_id: "check-002",
            title: "Describe deployment",
            rationale: "Check replica status",
            source: "diagnostic-pack",
            risk_level: "MEDIUM",
            status: "compatibility" as const,
            artifact_id: "diag-pack-xyz",
            run_id: "run-456",
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Check pod logs")).toBeInTheDocument();
      expect(screen.getByText("Describe deployment")).toBeInTheDocument();
      expect(screen.getAllByText("suggested")).toHaveLength(1);
      expect(screen.getAllByText("compatibility")).toHaveLength(1);
    });

    it("shows read-only notice for suggested checks", () => {
      const incident = createIncidentFixture({
        suggested_checks: [
          {
            check_id: "check-001",
            title: "Check pod logs",
            rationale: "First diagnostic step",
            source: "next-check-planning",
            risk_level: "LOW",
            status: "suggested" as const,
            artifact_id: null,
            run_id: null,
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Read-only view. No execution, promotion, or remediation available.")).toBeInTheDocument();
    });

    it("does not render action buttons for suggested checks", () => {
      const incident = createIncidentFixture({
        suggested_checks: [
          {
            check_id: "check-001",
            title: "Check pod logs",
            rationale: "First diagnostic step",
            source: "next-check-planning",
            risk_level: "LOW",
            status: "suggested" as const,
            artifact_id: null,
            run_id: null,
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      // Should still have zero buttons (no Run, Execute, Promote, etc.)
      const buttons = document.querySelectorAll("button");
      expect(buttons.length).toBe(0);
    });

    it("renders risk level badge when present", () => {
      const incident = createIncidentFixture({
        suggested_checks: [
          {
            check_id: "check-001",
            title: "Check pod logs",
            rationale: "First diagnostic step",
            source: "next-check-planning",
            risk_level: "HIGH",
            status: "suggested" as const,
            artifact_id: null,
            run_id: null,
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("HIGH")).toBeInTheDocument();
    });

    it("renders unknown status", () => {
      const incident = createIncidentFixture({
        suggested_checks: [
          {
            check_id: "check-001",
            title: "Check pod logs",
            rationale: "First diagnostic step",
            source: "next-check-planning",
            risk_level: null,
            status: "unknown" as const,
            artifact_id: null,
            run_id: null,
          },
        ],
      });
      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("unknown")).toBeInTheDocument();
    });
  });
});
