/**
 * IncidentDiagnosisLoopPanel.suggested-checks.test.tsx
 *
 * Targeted tests for suggested-check selection in IncidentDiagnosisLoopPanel.
 * Tests synchronous rendering behavior and static element checks.
 */

import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { IncidentDiagnosisLoopPanel } from "./IncidentDiagnosisLoopPanel";
import type { IncidentSuggestedCheck } from "../api";

// Create suggested check fixture
const createSuggestedCheck = (overrides: Partial<IncidentSuggestedCheck> = {}): IncidentSuggestedCheck => ({
  check_id: "test-check-001",
  title: "Check pod logs",
  rationale: "Test rationale",
  source: "next-check-planning",
  risk_level: "LOW",
  status: "suggested",
  artifact_id: "artifact-abc",
  run_id: "run-123",
  ...overrides,
});

describe("IncidentDiagnosisLoopPanel suggested checks", () => {
  describe("1. Renders suggested-check selection when checks are present", () => {
    test("renders suggested checks section when checks are provided", () => {
      const suggestedChecks = [
        createSuggestedCheck({ check_id: "pod_logs", title: "Check pod logs" }),
        createSuggestedCheck({ check_id: "describe_pod", title: "Describe pod" }),
      ];

      render(
        <IncidentDiagnosisLoopPanel
          incidentId="test-incident"
          suggestedChecks={suggestedChecks}
        />
      );

      expect(screen.getByText("Optional read-only checks for this pass")).toBeInTheDocument();
      expect(screen.getByText("Check pod logs")).toBeInTheDocument();
      expect(screen.getByText("Describe pod")).toBeInTheDocument();
    });

    test("shows check_id in parentheses", () => {
      const suggestedChecks = [
        createSuggestedCheck({ check_id: "pod_logs", title: "Check pod logs" }),
      ];

      render(
        <IncidentDiagnosisLoopPanel
          incidentId="test-incident"
          suggestedChecks={suggestedChecks}
        />
      );

      expect(screen.getByText("(pod_logs)")).toBeInTheDocument();
    });

    test("shows helper text about backend policy", () => {
      const suggestedChecks = [
        createSuggestedCheck({ check_id: "pod_logs", title: "Check pod logs" }),
      ];

      render(
        <IncidentDiagnosisLoopPanel
          incidentId="test-incident"
          suggestedChecks={suggestedChecks}
        />
      );

      expect(screen.getByText(/Only existing suggested checks are shown/)).toBeInTheDocument();
    });

    test("renders checkboxes for each suggested check", () => {
      const suggestedChecks = [
        createSuggestedCheck({ check_id: "pod_logs", title: "Check pod logs" }),
        createSuggestedCheck({ check_id: "describe_pod", title: "Describe pod" }),
      ];

      render(
        <IncidentDiagnosisLoopPanel
          incidentId="test-incident"
          suggestedChecks={suggestedChecks}
        />
      );

      const checkboxes = screen.getAllByRole("checkbox");
      expect(checkboxes).toHaveLength(2);
    });

    test("checkboxes are unchecked by default", () => {
      const suggestedChecks = [
        createSuggestedCheck({ check_id: "pod_logs", title: "Check pod logs" }),
      ];

      render(
        <IncidentDiagnosisLoopPanel
          incidentId="test-incident"
          suggestedChecks={suggestedChecks}
        />
      );

      const checkbox = screen.getByRole("checkbox");
      expect(checkbox).not.toBeChecked();
    });
  });

  describe("2. Renders safe empty-state copy when no checks are present", () => {
    test("does not render suggested checks section when empty", () => {
      render(
        <IncidentDiagnosisLoopPanel incidentId="test-incident" suggestedChecks={[]} />
      );

      expect(screen.queryByText("Optional read-only checks for this pass")).not.toBeInTheDocument();
    });

    test("does not render suggested checks section when undefined", () => {
      render(<IncidentDiagnosisLoopPanel incidentId="test-incident" />);

      expect(screen.queryByText("Optional read-only checks for this pass")).not.toBeInTheDocument();
    });

    test("renders run button even when no checks available", () => {
      render(<IncidentDiagnosisLoopPanel incidentId="test-incident" />);

      expect(screen.getByRole("button", { name: /Run one read-only pass/i })).toBeInTheDocument();
    });
  });

  describe("3. No remediation/action buttons are rendered", () => {
    test("only has the safe Run one read-only pass button", () => {
      render(
        <IncidentDiagnosisLoopPanel
          incidentId="test-incident"
          suggestedChecks={[createSuggestedCheck()]}
        />
      );

      const buttons = screen.getAllByRole("button");
      expect(buttons).toHaveLength(1);
      expect(buttons[0]).toHaveTextContent("Run one read-only pass");
    });

    test("does not render Execute button", () => {
      render(
        <IncidentDiagnosisLoopPanel
          incidentId="test-incident"
          suggestedChecks={[createSuggestedCheck()]}
        />
      );

      expect(screen.queryByRole("button", { name: /Execute/i })).not.toBeInTheDocument();
    });

    test("does not render Apply button", () => {
      render(
        <IncidentDiagnosisLoopPanel
          incidentId="test-incident"
          suggestedChecks={[createSuggestedCheck()]}
        />
      );

      expect(screen.queryByRole("button", { name: /Apply/i })).not.toBeInTheDocument();
    });

    test("does not render Fix button", () => {
      render(
        <IncidentDiagnosisLoopPanel
          incidentId="test-incident"
          suggestedChecks={[createSuggestedCheck()]}
        />
      );

      expect(screen.queryByRole("button", { name: /Fix/i })).not.toBeInTheDocument();
    });

    test("does not render Delete button", () => {
      render(
        <IncidentDiagnosisLoopPanel
          incidentId="test-incident"
          suggestedChecks={[createSuggestedCheck()]}
        />
      );

      expect(screen.queryByRole("button", { name: /Delete/i })).not.toBeInTheDocument();
    });

    test("does not render Restart button", () => {
      render(
        <IncidentDiagnosisLoopPanel
          incidentId="test-incident"
          suggestedChecks={[createSuggestedCheck()]}
        />
      );

      expect(screen.queryByRole("button", { name: /Restart/i })).not.toBeInTheDocument();
    });

    test("does not render Remediate button", () => {
      render(
        <IncidentDiagnosisLoopPanel
          incidentId="test-incident"
          suggestedChecks={[createSuggestedCheck()]}
        />
      );

      expect(screen.queryByRole("button", { name: /Remediate/i })).not.toBeInTheDocument();
    });
  });

  describe("4. Panel structure and safety indicators", () => {
    test("displays panel header", () => {
      render(
        <IncidentDiagnosisLoopPanel
          incidentId="test-incident"
          suggestedChecks={[createSuggestedCheck()]}
        />
      );

      expect(screen.getByText("Manual diagnosis loop")).toBeInTheDocument();
    });

    test("displays safety footer notice", () => {
      render(
        <IncidentDiagnosisLoopPanel
          incidentId="test-incident"
          suggestedChecks={[createSuggestedCheck()]}
        />
      );

      expect(screen.getByText(/Fake runner/)).toBeInTheDocument();
      expect(screen.getByText(/Safe checks only/)).toBeInTheDocument();
      expect(screen.getByText(/No kubectl/)).toBeInTheDocument();
    });

    test("displays description text", () => {
      render(
        <IncidentDiagnosisLoopPanel
          incidentId="test-incident"
          suggestedChecks={[createSuggestedCheck()]}
        />
      );

      expect(screen.getByText(/Runs exactly one read-only diagnosis pass/)).toBeInTheDocument();
    });

    test("run button is enabled by default", () => {
      render(
        <IncidentDiagnosisLoopPanel
          incidentId="test-incident"
          suggestedChecks={[createSuggestedCheck()]}
        />
      );

      const runButton = screen.getByRole("button", { name: /Run one read-only pass/i });
      expect(runButton).toBeEnabled();
      expect(runButton).not.toBeDisabled();
    });
  });

  describe("5. Handles invalid/edge case checks", () => {
    test("filters out checks with empty check_id", () => {
      const suggestedChecks = [
        createSuggestedCheck({ check_id: "valid-check", title: "Valid check" }),
        createSuggestedCheck({ check_id: "", title: "Empty check_id" }),
      ];

      render(
        <IncidentDiagnosisLoopPanel
          incidentId="test-incident"
          suggestedChecks={suggestedChecks}
        />
      );

      // Only the valid check should be shown
      expect(screen.getByText("Valid check")).toBeInTheDocument();
      // The empty check should not be shown (no checkbox for it)
      const checkboxes = screen.getAllByRole("checkbox");
      expect(checkboxes).toHaveLength(1);
    });

    test("handles checks with null title gracefully", () => {
      const suggestedChecks = [
        createSuggestedCheck({ check_id: "check-1", title: "" as unknown as string }),
      ];

      // Should not throw
      expect(() => {
        render(
          <IncidentDiagnosisLoopPanel
            incidentId="test-incident"
            suggestedChecks={suggestedChecks}
          />
        );
      }).not.toThrow();
    });
  });
});
