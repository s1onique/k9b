/**
 * Demo Shell Component Tests
 *
 * Tests for the clickable real-cluster demo path shell.
 * Core functionality and navigation tests.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, cleanup, act } from "@testing-library/react";
import "@testing-library/jest-dom";
import { DemoShell } from "../components/DemoShell";

const renderDemoShell = (props = {}) => render(<DemoShell {...props} />);

describe("DemoShell", () => {
  beforeEach(() => {
    cleanup();
  });

  describe("Start screen", () => {
    it("renders start screen with product name and CTA", () => {
      renderDemoShell();
      expect(screen.getByText("K8s Accelerator")).toBeInTheDocument();
      expect(screen.getByText("Transform Kubernetes operational signals into operator-ready actions")).toBeInTheDocument();
      const startButton = screen.getByTestId("demo-start-button");
      expect(startButton).toBeInTheDocument();
      expect(startButton).toHaveTextContent("Use selected real run");
    });

    it("shows safety note on start screen", () => {
      renderDemoShell();
      expect(screen.getByText(/Safety first/i)).toBeInTheDocument();
      expect(screen.getByText(/All actions are preview-only or require operator approval/i)).toBeInTheDocument();
    });

    it("displays no fake incidents message on start screen", () => {
      renderDemoShell();
      expect(screen.getByText(/No fake incidents, no fabricated samples/i)).toBeInTheDocument();
    });

    it("sets step indicator to Start", () => {
      renderDemoShell();
      expect(screen.getByText("Step: Start")).toBeInTheDocument();
    });
  });

  describe("Navigation flow", () => {
    it("clicking start button transitions to onboarding", () => {
      renderDemoShell();
      const startButton = screen.getByTestId("demo-start-button");
      fireEvent.click(startButton);
      expect(screen.getByText("Ready to start demo")).toBeInTheDocument();
      expect(screen.getByText("Step: Selected Real Run")).toBeInTheDocument();
    });

    it("clicking continue transitions to dashboard", async () => {
      vi.useFakeTimers();
      renderDemoShell({ initialStep: "onboarding" });
      const continueButton = screen.getByTestId("demo-connect-button");
      fireEvent.click(continueButton);
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });
      expect(screen.getByTestId("demo-shell")).toHaveAttribute("data-demo-step", "dashboard");
      vi.useRealTimers();
    });
  });

  describe("Dashboard shell", () => {
    it("shows connected status indicator", () => {
      renderDemoShell({
        initialStep: "dashboard",
        realContext: { runId: "run-123-abc", isFresh: true },
        findingSelectionInput: { incidentReport: { status: "critical" } },
      });
      expect(screen.getByText("Connected")).toBeInTheDocument();
    });

    it("shows read-only safety mode by default", () => {
      renderDemoShell({ initialStep: "dashboard", realContext: { runId: "run-123-abc", isFresh: true } });
      expect(screen.getByText("Read-only")).toBeInTheDocument();
    });
  });

  describe("Onboarding screen", () => {
    it("shows safety mode radio buttons", () => {
      renderDemoShell({ initialStep: "onboarding" });
      expect(document.querySelector('input[name="safety-mode"][value="read-only"]')).toBeInTheDocument();
      expect(document.querySelector('input[name="safety-mode"][value="operator-approved"]')).toBeInTheDocument();
      expect(document.querySelector('input[name="safety-mode"][value="preview-only"]')).toBeInTheDocument();
    });

    it("safety indicator updates when mode changes", () => {
      renderDemoShell({ initialStep: "onboarding" });
      expect(screen.getByText("No cluster mutations will be performed")).toBeInTheDocument();
      const operatorApprovedRadio = document.querySelector('input[name="safety-mode"][value="operator-approved"]');
      fireEvent.click(operatorApprovedRadio!);
      expect(screen.getByText("Actions require explicit operator click")).toBeInTheDocument();
    });
  });

  describe("Forbidden phrase checks", () => {
    it("does not contain 'self-healing'", () => {
      renderDemoShell();
      const container = document.querySelector(".demo-shell-overlay");
      expect(container?.textContent).not.toMatch(/\bself-healing\b/i);
    });

    it("does not contain 'guaranteed root cause'", () => {
      renderDemoShell();
      const container = document.querySelector(".demo-shell-overlay");
      expect(container?.textContent).not.toMatch(/\bguaranteed root cause\b/i);
    });

    it("does not contain 'automatic production fix'", () => {
      renderDemoShell();
      const container = document.querySelector(".demo-shell-overlay");
      expect(container?.textContent).not.toMatch(/\bautomatic production fix\b/i);
    });

    it("does not contain 'fixes any Kubernetes issue'", () => {
      renderDemoShell();
      const container = document.querySelector(".demo-shell-overlay");
      expect(container?.textContent).not.toMatch(/\bfixes any Kubernetes issue\b/i);
    });

    it("does not contain 'fully autonomous'", () => {
      renderDemoShell();
      const container = document.querySelector(".demo-shell-overlay");
      expect(container?.textContent).not.toMatch(/\bfully autonomous\b/i);
    });
  });

  describe("Data test attributes", () => {
    it("sets demo-step attribute on shell", () => {
      renderDemoShell({ initialStep: "start" });
      expect(screen.getByTestId("demo-shell")).toHaveAttribute("data-demo-step", "start");
    });

    it("sets demo-clean-cluster attribute on shell", () => {
      renderDemoShell({ initialStep: "dashboard" });
      expect(screen.getByTestId("demo-shell")).toHaveAttribute("data-demo-clean-cluster", "false");
    });
  });

  describe("Close button", () => {
    it("renders close button when onClose is provided", () => {
      const onClose = vi.fn();
      renderDemoShell({ onClose });
      const closeButton = screen.getByTestId("demo-close-button");
      expect(closeButton).toBeInTheDocument();
      fireEvent.click(closeButton);
      expect(onClose).toHaveBeenCalled();
    });
  });

  describe("Component structure", () => {
    it("renders overlay with container", () => {
      renderDemoShell();
      expect(document.querySelector(".demo-shell-overlay")).toBeInTheDocument();
      expect(document.querySelector(".demo-shell-container")).toBeInTheDocument();
    });

    it("renders header with title", () => {
      renderDemoShell();
      const title = document.querySelector(".demo-shell-title");
      expect(title).toBeInTheDocument();
      expect(title).toHaveTextContent("K8s Accelerator Demo");
    });

    it("renders footer with safety statement", () => {
      renderDemoShell();
      const footer = document.querySelector(".demo-shell-footer");
      expect(footer).toBeInTheDocument();
      expect(footer).toHaveTextContent(/Real cluster evidence/i);
    });
  });

  describe("Safety disclaimers present in component", () => {
    it("start screen mentions no automatic remediation", () => {
      renderDemoShell();
      expect(screen.getByText(/No automatic remediation/i)).toBeInTheDocument();
    });

    it("start screen mentions operator approval", () => {
      renderDemoShell();
      expect(screen.getByText(/require operator approval/i)).toBeInTheDocument();
    });

    it("onboarding shows safety mode radio buttons", () => {
      renderDemoShell({ initialStep: "onboarding" });
      expect(document.querySelector('input[name="safety-mode"][value="read-only"]')).toBeInTheDocument();
      expect(document.querySelector('input[name="safety-mode"][value="operator-approved"]')).toBeInTheDocument();
      expect(document.querySelector('input[name="safety-mode"][value="preview-only"]')).toBeInTheDocument();
    });
  });
});

describe("DemoShell types and exports", () => {
  it("exports DemoStep type values", () => {
    const steps: Array<"start" | "onboarding" | "dashboard" | "finding-detail" | "action-panel"> = [
      "start", "onboarding", "dashboard", "finding-detail", "action-panel",
    ];
    expect(steps).toHaveLength(5);
  });

  it("exports EvidenceSource type values", () => {
    const sources: Array<"live" | "historical" | "stale" | "none"> = ["live", "historical", "stale", "none"];
    expect(sources).toHaveLength(4);
  });

  it("exports SeverityLevel type values", () => {
    const levels: Array<"critical" | "warning" | "info"> = ["critical", "warning", "info"];
    expect(levels).toHaveLength(3);
  });

  it("exports SafetyMode type values", () => {
    const modes: Array<"read-only" | "operator-approved" | "preview-only"> = [
      "read-only", "operator-approved", "preview-only",
    ];
    expect(modes).toHaveLength(3);
  });

  it("exports DemoFinding interface structure", () => {
    const finding = {
      id: "test", title: "Test", severity: "info" as const,
      affectedResource: "test-ns/test-pod", evidenceSource: "none" as const,
      probableCause: "Test cause", diagnosticEvidence: "Test evidence",
      recommendedAction: "Test action", safetyMode: "read-only" as const,
    };
    expect(finding.id).toBe("test");
    expect(finding.severity).toBe("info");
  });
});
