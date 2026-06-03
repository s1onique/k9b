/**
 * Demo Shell Action Preview Integration Tests
 *
 * Tests for the enhanced action panel with safety mode labels and remediation preview.
 * Verifies that the action panel is safe for sales demos:
 * - No real mutation
 * - No kubectl execution
 * - No autonomous remediation claims
 * - Clear safety mode labeling
 * - Explicit approval/disabled states
 */

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import "@testing-library/jest-dom";
import { DemoShell } from "../components/DemoShell";

// Helper to render the demo shell with cleanup
const renderDemoShell = (props = {}) => {
  return render(<DemoShell {...props} />);
};

describe("DemoShell Action Panel - Safety Modes", () => {
  beforeEach(() => {
    cleanup();
  });

  describe("Action panel renders with safety mode", () => {
    const findingSelectionInput = {
      incidentReport: {
        status: "critical",
        resource: "default/nginx-pod",
        findingType: "CrashLoopBackOff",
      },
    };

    it("renders 'Recommended Action' title", () => {
      renderDemoShell({
        initialStep: "action-panel",
        findingSelectionInput,
      });

      expect(screen.getByTestId("action-title")).toHaveTextContent("Recommended Action");
    });

    it("renders safety mode badge", () => {
      renderDemoShell({
        initialStep: "action-panel",
        findingSelectionInput,
      });

      const badgeElement = document.querySelector(".demo-badge--safety-previewonly");
      expect(badgeElement).toBeInTheDocument();
    });

    it("renders safety mode panel with description", () => {
      renderDemoShell({
        initialStep: "action-panel",
        findingSelectionInput,
      });

      expect(screen.getByTestId("safety-mode-panel")).toBeInTheDocument();
    });
  });

  describe("Command preview display", () => {
    it("shows command preview section when available", () => {
      const findingSelectionInput = {
        incidentReport: {
          status: "critical",
          resource: "default/nginx-pod",
          findingType: "CrashLoopBackOff",
        },
      };

      renderDemoShell({
        initialStep: "action-panel",
        findingSelectionInput,
      });

      expect(screen.getByTestId("remediation-preview")).toBeInTheDocument();
    });
  });

  describe("Provenance section display", () => {
    it("shows evidence provenance section", () => {
      const findingSelectionInput = {
        incidentReport: {
          status: "critical",
          resource: "default/nginx-pod",
          findingType: "CrashLoopBackOff",
        },
      };

      renderDemoShell({
        initialStep: "action-panel",
        findingSelectionInput,
      });

      expect(screen.getByTestId("provenance-section")).toBeInTheDocument();
      expect(screen.getByText("Evidence provenance")).toBeInTheDocument();
    });

    it("shows severity in provenance", () => {
      const findingSelectionInput = {
        incidentReport: {
          status: "critical",
          resource: "default/nginx-pod",
          findingType: "CrashLoopBackOff",
        },
      };

      renderDemoShell({
        initialStep: "action-panel",
        findingSelectionInput,
      });

      expect(screen.getByText("Severity")).toBeInTheDocument();
    });

    it("shows evidence source in provenance", () => {
      const findingSelectionInput = {
        incidentReport: {
          status: "critical",
          resource: "default/nginx-pod",
          findingType: "CrashLoopBackOff",
        },
      };

      renderDemoShell({
        initialStep: "action-panel",
        findingSelectionInput,
      });

      expect(screen.getByText("Evidence source")).toBeInTheDocument();
    });

    it("shows affected resource in provenance", () => {
      const findingSelectionInput = {
        incidentReport: {
          status: "critical",
          resource: "default/nginx-pod",
          findingType: "CrashLoopBackOff",
        },
      };

      renderDemoShell({
        initialStep: "action-panel",
        findingSelectionInput,
      });

      expect(screen.getByText("Affected resource")).toBeInTheDocument();
      expect(screen.getByText("default/nginx-pod")).toBeInTheDocument();
    });
  });

  describe("Approval requirement callout", () => {
    it("shows operator approval required callout", () => {
      const findingSelectionInput = {
        incidentReport: {
          status: "critical",
          resource: "default/nginx-pod",
          findingType: "CrashLoopBackOff",
        },
      };

      renderDemoShell({
        initialStep: "action-panel",
        findingSelectionInput,
      });

      expect(screen.getByTestId("approval-callout")).toBeInTheDocument();
      expect(screen.getByText("Operator approval required")).toBeInTheDocument();
    });
  });

  describe("CTA behavior", () => {
    it("renders disabled CTA for non-preview modes", () => {
      const historicalFindings = [
        {
          id: "hist-1",
          title: "Critical: FailedScheduling",
          severity: "critical" as const,
          affectedResource: "app/job-pod",
          evidenceSource: "historical" as const,
          probableCause: "Insufficient resources",
          diagnosticEvidence: "Node capacity exceeded",
          recommendedAction: "Review resource requests",
          safetyMode: "read-only" as const,
        },
      ];

      renderDemoShell({
        initialStep: "action-panel",
        findingSelectionInput: {},
        historicalFindings,
      });

      const disabledButton = screen.getByTestId("disabled-cta-button");
      expect(disabledButton).toBeInTheDocument();
      expect(disabledButton).toBeDisabled();
    });

    it("renders copy button for preview-only mode", () => {
      const findingSelectionInput = {
        incidentReport: {
          status: "critical",
          resource: "default/nginx-pod",
          findingType: "CrashLoopBackOff",
        },
      };

      renderDemoShell({
        initialStep: "action-panel",
        findingSelectionInput,
      });

      const copyButton = screen.getByTestId("copy-recommendation-button");
      expect(copyButton).toBeInTheDocument();
    });
  });

  describe("Remediation preview section", () => {
    it("renders remediation preview section", () => {
      const findingSelectionInput = {
        incidentReport: {
          status: "critical",
          resource: "default/nginx-pod",
          findingType: "CrashLoopBackOff",
        },
      };

      renderDemoShell({
        initialStep: "action-panel",
        findingSelectionInput,
      });

      expect(screen.getByTestId("remediation-preview")).toBeInTheDocument();
      expect(screen.getByText("Remediation preview")).toBeInTheDocument();
    });

    it("shows recommended action text", () => {
      const findingSelectionInput = {
        incidentReport: {
          status: "critical",
          resource: "default/nginx-pod",
          findingType: "CrashLoopBackOff",
        },
      };

      renderDemoShell({
        initialStep: "action-panel",
        findingSelectionInput,
      });

      const actionText = screen.getByText(/Review diagnostic evidence/i);
      expect(actionText).toBeInTheDocument();
    });
  });

  describe("Workflow note", () => {
    it("shows evidence-preserving workflow note", () => {
      const findingSelectionInput = {
        incidentReport: {
          status: "critical",
          resource: "default/nginx-pod",
          findingType: "CrashLoopBackOff",
        },
      };

      renderDemoShell({
        initialStep: "action-panel",
        findingSelectionInput,
      });

      expect(screen.getByText(/Evidence-preserving workflow/i)).toBeInTheDocument();
    });
  });
});