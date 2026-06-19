/**
 * incident-detail-panel-diagnosis-loop-integration.test.tsx
 *
 * Integration tests for IncidentDetailPanel passing suggested_checks
 * to IncidentDiagnosisLoopPanel.
 * Tests synchronous rendering behavior.
 */

import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { IncidentDetailPanel } from "../components/IncidentDetailPanel";
import type { IncidentDetailPayload } from "../api";

// Full fixture using IncidentDetailPayload
const createIncidentFixture = (overrides: Partial<IncidentDetailPayload> = {}): IncidentDetailPayload => ({
  incident_id: "test-incident-123",
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

describe("IncidentDetailPanel diagnosis loop integration", () => {
  describe("1. IncidentDetailPanel passes suggested checks to IncidentDiagnosisLoopPanel", () => {
    test("passes suggested checks from incident to diagnosis panel", () => {
      const incident = createIncidentFixture({
        suggested_checks: [
          {
            check_id: "pod_logs",
            title: "Check pod logs",
            rationale: "Test rationale",
            source: "next-check-planning",
            risk_level: "LOW",
            status: "suggested" as const,
            artifact_id: "artifact-abc",
            run_id: "run-123",
          },
        ],
      });

      render(<IncidentDetailPanel incident={incident} />);

      // Diagnosis loop panel should show suggested checks from incident
      expect(screen.getByText("Optional read-only checks for this pass")).toBeInTheDocument();
      // Title appears twice: in SuggestedChecksSection and in diagnosis-loop selection
      expect(screen.getAllByText("Check pod logs")).toHaveLength(2);
    });

    test("passes multiple suggested checks", () => {
      const incident = createIncidentFixture({
        suggested_checks: [
          {
            check_id: "check_1",
            title: "First check",
            rationale: "First rationale",
            source: "next-check-planning",
            risk_level: "LOW",
            status: "suggested" as const,
            artifact_id: null,
            run_id: null,
          },
          {
            check_id: "check_2",
            title: "Second check",
            rationale: "Second rationale",
            source: "next-check-planning",
            risk_level: "MEDIUM",
            status: "suggested" as const,
            artifact_id: null,
            run_id: null,
          },
        ],
      });

      render(<IncidentDetailPanel incident={incident} />);

      // Each check appears twice: in SuggestedChecksSection and in diagnosis-loop selection
      expect(screen.getAllByText("First check")).toHaveLength(2);
      expect(screen.getAllByText("Second check")).toHaveLength(2);
    });

    test("does not pass suggested checks when incident has none", () => {
      const incident = createIncidentFixture({
        suggested_checks: [],
      });

      render(<IncidentDetailPanel incident={incident} />);

      // Diagnosis loop panel should not show suggested checks section
      expect(screen.queryByText("Optional read-only checks for this pass")).not.toBeInTheDocument();
    });

    test("passes incident_id to diagnosis panel", () => {
      const incident = createIncidentFixture({
        incident_id: "my-special-incident-id",
        suggested_checks: [
          {
            check_id: "check_1",
            title: "Check",
            rationale: "",
            source: "test",
            risk_level: null,
            status: "suggested" as const,
            artifact_id: null,
            run_id: null,
          },
        ],
      });

      render(<IncidentDetailPanel incident={incident} />);

      // Panel should render without errors (incidentId is passed correctly)
      expect(screen.getByText("Manual diagnosis loop")).toBeInTheDocument();
      expect(screen.getByText("Run one read-only pass")).toBeInTheDocument();
    });
  });

  describe("2. existing suggested-check section still renders", () => {
    test("renders Suggested checks section separately from diagnosis loop panel", () => {
      const incident = createIncidentFixture({
        suggested_checks: [
          {
            check_id: "pod_logs",
            title: "Check pod logs",
            rationale: "CrashLoopBackOff logs are useful",
            source: "next-check-planning",
            risk_level: "LOW",
            status: "suggested" as const,
            artifact_id: "artifact-abc",
            run_id: "run-123",
          },
        ],
      });

      render(<IncidentDetailPanel incident={incident} />);

      // The Suggested checks section in incident detail should still render
      expect(screen.getByText("Suggested checks")).toBeInTheDocument();
      expect(screen.getByText("Read-only view. No execution, promotion, or remediation available.")).toBeInTheDocument();
      expect(screen.getByText("CrashLoopBackOff logs are useful")).toBeInTheDocument();

      // The diagnosis loop panel selection should be separate
      expect(screen.getByText("Optional read-only checks for this pass")).toBeInTheDocument();
    });

    test("renders empty suggested checks state correctly", () => {
      const incident = createIncidentFixture({
        suggested_checks: [],
      });

      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Suggested checks")).toBeInTheDocument();
      expect(screen.getByText("No suggested checks linked to this incident yet.")).toBeInTheDocument();
    });
  });

  describe("3. existing no-remediation button tests still pass", () => {
    test("only safe Run one read-only pass button is present", () => {
      const incident = createIncidentFixture({
        suggested_checks: [
          {
            check_id: "check_1",
            title: "Check",
            rationale: "",
            source: "test",
            risk_level: null,
            status: "suggested" as const,
            artifact_id: null,
            run_id: null,
          },
        ],
      });

      render(<IncidentDetailPanel incident={incident} />);

      // Only one button in the diagnosis loop panel
      const buttons = screen.getAllByRole("button");
      expect(buttons).toHaveLength(1);
      expect(buttons[0]).toHaveTextContent("Run one read-only pass");
    });

    test("no Execute button exists", () => {
      const incident = createIncidentFixture({
        suggested_checks: [
          {
            check_id: "check_1",
            title: "Check",
            rationale: "",
            source: "test",
            risk_level: null,
            status: "suggested" as const,
            artifact_id: null,
            run_id: null,
          },
        ],
      });

      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.queryByRole("button", { name: /Execute/i })).not.toBeInTheDocument();
    });

    test("no Apply button exists", () => {
      const incident = createIncidentFixture({
        suggested_checks: [
          {
            check_id: "check_1",
            title: "Check",
            rationale: "",
            source: "test",
            risk_level: null,
            status: "suggested" as const,
            artifact_id: null,
            run_id: null,
          },
        ],
      });

      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.queryByRole("button", { name: /Apply/i })).not.toBeInTheDocument();
    });

    test("no Fix button exists", () => {
      const incident = createIncidentFixture({
        suggested_checks: [
          {
            check_id: "check_1",
            title: "Check",
            rationale: "",
            source: "test",
            risk_level: null,
            status: "suggested" as const,
            artifact_id: null,
            run_id: null,
          },
        ],
      });

      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.queryByRole("button", { name: /Fix/i })).not.toBeInTheDocument();
    });

    test("no Remediate button exists", () => {
      const incident = createIncidentFixture({
        suggested_checks: [
          {
            check_id: "check_1",
            title: "Check",
            rationale: "",
            source: "test",
            risk_level: null,
            status: "suggested" as const,
            artifact_id: null,
            run_id: null,
          },
        ],
      });

      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.queryByRole("button", { name: /Remediate/i })).not.toBeInTheDocument();
    });

    test("no Delete button exists", () => {
      const incident = createIncidentFixture({
        suggested_checks: [
          {
            check_id: "check_1",
            title: "Check",
            rationale: "",
            source: "test",
            risk_level: null,
            status: "suggested" as const,
            artifact_id: null,
            run_id: null,
          },
        ],
      });

      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.queryByRole("button", { name: /Delete/i })).not.toBeInTheDocument();
    });

    test("no Restart button exists", () => {
      const incident = createIncidentFixture({
        suggested_checks: [
          {
            check_id: "check_1",
            title: "Check",
            rationale: "",
            source: "test",
            risk_level: null,
            status: "suggested" as const,
            artifact_id: null,
            run_id: null,
          },
        ],
      });

      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.queryByRole("button", { name: /Restart/i })).not.toBeInTheDocument();
    });

    test("displays read-only notice", () => {
      const incident = createIncidentFixture();

      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Read-only view. No remediation, mutation, or LLM actions available.")).toBeInTheDocument();
    });

    test("displays safety badges in diagnosis loop panel", () => {
      const incident = createIncidentFixture({
        suggested_checks: [
          {
            check_id: "check_1",
            title: "Check",
            rationale: "",
            source: "test",
            risk_level: null,
            status: "suggested" as const,
            artifact_id: null,
            run_id: null,
          },
        ],
      });

      render(<IncidentDetailPanel incident={incident} />);

      // "Read-only" appears twice: once in panel header badge, once in each suggested check item
      expect(screen.getAllByText("Read-only")).toHaveLength(2);
      expect(screen.getByText("One pass only")).toBeInTheDocument();
    });
  });

  describe("5. existing incident detail tests do not regress", () => {
    test("renders incident identity correctly", () => {
      const incident = createIncidentFixture({
        incident_id: "my-incident",
        namespace: "production",
        object_kind: "Deployment",
        object_name: "api-server",
        severity: "warning",
        status: "investigating",
      });

      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("my-incident")).toBeInTheDocument();
      expect(screen.getByText("production")).toBeInTheDocument();
      expect(screen.getByText("Deployment")).toBeInTheDocument();
      expect(screen.getByText("api-server")).toBeInTheDocument();
      expect(screen.getByText("warning")).toBeInTheDocument();
      expect(screen.getByText("investigating")).toBeInTheDocument();
    });

    test("renders read-only notice", () => {
      const incident = createIncidentFixture();

      render(<IncidentDetailPanel incident={incident} />);

      expect(screen.getByText("Read-only view. No remediation, mutation, or LLM actions available.")).toBeInTheDocument();
    });
  });
});
