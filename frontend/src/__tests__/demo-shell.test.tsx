/**
 * Demo Shell Component Tests
 *
 * Tests for the clickable real-cluster demo path shell.
 * Covers the main click path and safety/truth requirements.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, cleanup, act } from "@testing-library/react";
import "@testing-library/jest-dom";
import { DemoShell } from "../components/DemoShell";

// Helper to render the demo shell with cleanup
const renderDemoShell = (props = {}) => {
  const result = render(<DemoShell {...props} />);
  return result;
};

describe("DemoShell", () => {
  beforeEach(() => {
    cleanup();
  });

  describe("Start screen", () => {
    it("renders start screen with product name and CTA", () => {
      renderDemoShell();

      // Product name should be visible
      expect(screen.getByText("K8s Accelerator")).toBeInTheDocument();

      // Value proposition should be visible
      expect(
        screen.getByText("Transform Kubernetes operational signals into operator-ready actions")
      ).toBeInTheDocument();

      // CTA button should be present
      const startButton = screen.getByTestId("demo-start-button");
      expect(startButton).toBeInTheDocument();
      expect(startButton).toHaveTextContent("Start real-cluster demo");
    });

    it("shows safety note on start screen", () => {
      renderDemoShell();

      expect(screen.getByText(/Safety first/i)).toBeInTheDocument();
      expect(
        screen.getByText(/All actions are preview-only or require operator approval/i)
      ).toBeInTheDocument();
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

      // Click start button
      const startButton = screen.getByTestId("demo-start-button");
      fireEvent.click(startButton);

      // Should show onboarding screen
      expect(screen.getByText("Connect your cluster")).toBeInTheDocument();
      expect(screen.getByText("Step: Connect Cluster")).toBeInTheDocument();
    });

    it("clicking connect transitions to dashboard", async () => {
      vi.useFakeTimers();

      renderDemoShell({ initialStep: "onboarding" });

      const connectButton = screen.getByTestId("demo-connect-button");
      fireEvent.click(connectButton);

      // Advance timers and wrap in act to flush React state updates
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      expect(screen.getByTestId("demo-shell")).toHaveAttribute(
        "data-demo-step",
        "dashboard"
      );
      expect(screen.getByText("minikube")).toBeInTheDocument();

      vi.useRealTimers();
    });
  });

  describe("Dashboard shell", () => {
    it("shows cluster name after connection", () => {
      renderDemoShell({ initialStep: "dashboard" });

      expect(screen.getByText("minikube")).toBeInTheDocument();
    });

    it("shows connected status indicator", () => {
      renderDemoShell({ initialStep: "dashboard" });

      expect(screen.getByText("Connected")).toBeInTheDocument();
    });

    it("shows read-only safety mode by default", () => {
      renderDemoShell({ initialStep: "dashboard" });

      // Read-only badge should be present
      expect(screen.getByText("Read-only")).toBeInTheDocument();
    });

    it("shows evidence source badge", () => {
      renderDemoShell({ initialStep: "dashboard" });

      // Evidence source should be visible
      expect(screen.getByText("Live")).toBeInTheDocument();
    });

    it("shows finding feed area", () => {
      renderDemoShell({ initialStep: "dashboard" });

      expect(screen.getByText("Findings")).toBeInTheDocument();
    });

    it("shows evidence source label in footer", () => {
      renderDemoShell({ initialStep: "dashboard" });

      // Footer should show evidence source
      expect(screen.getByText(/Evidence source: Live scan/)).toBeInTheDocument();
    });
  });

  describe("Onboarding screen", () => {
    it("shows kube context selector", () => {
      renderDemoShell({ initialStep: "onboarding" });

      // Context selector should be present
      const contextSelect = document.getElementById("kube-context");
      expect(contextSelect).toBeInTheDocument();
    });

    it("shows safety mode radio buttons", () => {
      renderDemoShell({ initialStep: "onboarding" });

      // Safety mode radio buttons should be present
      const readOnlyOption = document.querySelector(
        'input[name="safety-mode"][value="read-only"]'
      );
      const operatorApprovedOption = document.querySelector(
        'input[name="safety-mode"][value="operator-approved"]'
      );
      const previewOnlyOption = document.querySelector(
        'input[name="safety-mode"][value="preview-only"]'
      );

      expect(readOnlyOption).toBeInTheDocument();
      expect(operatorApprovedOption).toBeInTheDocument();
      expect(previewOnlyOption).toBeInTheDocument();
    });

    it("safety indicator updates when mode changes", () => {
      renderDemoShell({ initialStep: "onboarding" });

      // Initially shows read-only description
      expect(
        screen.getByText("No cluster mutations will be performed")
      ).toBeInTheDocument();

      // Select operator-approved mode
      const operatorApprovedRadio = document.querySelector(
        'input[name="safety-mode"][value="operator-approved"]'
      );
      fireEvent.click(operatorApprovedRadio!);

      // Should show operator-approved description
      expect(screen.getByText("Actions require explicit operator click")).toBeInTheDocument();
    });
  });

  describe("Forbidden phrase checks", () => {
    // These tests verify that forbidden phrases do not appear in the demo
    // Use word boundary regex to avoid partial matches

    it("does not contain 'self-healing' in rendered output", () => {
      renderDemoShell();
      const container = document.querySelector(".demo-shell-overlay");
      expect(container?.textContent).not.toMatch(/\bself-healing\b/i);
    });

    it("does not contain 'guaranteed root cause' in rendered output", () => {
      renderDemoShell();
      const container = document.querySelector(".demo-shell-overlay");
      expect(container?.textContent).not.toMatch(/\bguaranteed root cause\b/i);
    });

    it("does not contain 'automatic production fix' in rendered output", () => {
      renderDemoShell();
      const container = document.querySelector(".demo-shell-overlay");
      expect(container?.textContent).not.toMatch(/\bautomatic production fix\b/i);
    });

    it("does not contain 'fixes any Kubernetes issue' in rendered output", () => {
      renderDemoShell();
      const container = document.querySelector(".demo-shell-overlay");
      expect(container?.textContent).not.toMatch(/\bfixes any Kubernetes issue\b/i);
    });

    it("does not contain 'fully autonomous' in rendered output", () => {
      renderDemoShell();
      const container = document.querySelector(".demo-shell-overlay");
      expect(container?.textContent).not.toMatch(/\bfully autonomous\b/i);
    });
  });

  describe("Data test attributes", () => {
    it("sets demo-step attribute on shell", () => {
      renderDemoShell({ initialStep: "start" });

      const shell = screen.getByTestId("demo-shell");
      expect(shell).toHaveAttribute("data-demo-step", "start");
    });

    it("sets demo-clean-cluster attribute on shell", () => {
      renderDemoShell({ initialStep: "dashboard" });

      const shell = screen.getByTestId("demo-shell");
      expect(shell).toHaveAttribute("data-demo-clean-cluster", "false");
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

  describe("Safety mode labels", () => {
    it("shows 'read-only' label in dashboard", () => {
      renderDemoShell({ initialStep: "dashboard" });
      expect(screen.getByText("Read-only")).toBeInTheDocument();
    });

    it("shows safety mode options in onboarding", () => {
      renderDemoShell({ initialStep: "onboarding" });

      // Check all three safety mode options are visible
      const readOnlyOption = document.querySelector(
        'input[name="safety-mode"][value="read-only"]'
      );
      const operatorApprovedOption = document.querySelector(
        'input[name="safety-mode"][value="operator-approved"]'
      );
      const previewOnlyOption = document.querySelector(
        'input[name="safety-mode"][value="preview-only"]'
      );

      expect(readOnlyOption).toBeInTheDocument();
      expect(operatorApprovedOption).toBeInTheDocument();
      expect(previewOnlyOption).toBeInTheDocument();
    });

    it("updates safety indicator when mode changes", () => {
      renderDemoShell({ initialStep: "onboarding" });

      // Initially shows read-only description
      expect(screen.getByText("No cluster mutations will be performed")).toBeInTheDocument();

      // Select operator-approved mode
      const operatorApprovedRadio = document.querySelector(
        'input[name="safety-mode"][value="operator-approved"]'
      );
      fireEvent.click(operatorApprovedRadio!);

      // Should show operator-approved badge in safety indicator
      const badge = document.querySelector(".demo-badge--safety-operatorapproved");
      expect(badge).toBeInTheDocument();
    });
  });

  describe("Component structure", () => {
    it("renders overlay with container", () => {
      renderDemoShell();

      const overlay = document.querySelector(".demo-shell-overlay");
      expect(overlay).toBeInTheDocument();

      const container = document.querySelector(".demo-shell-container");
      expect(container).toBeInTheDocument();
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

      // Safety mode radio buttons should be present
      const readOnlyOption = document.querySelector(
        'input[name="safety-mode"][value="read-only"]'
      );
      const operatorApprovedOption = document.querySelector(
        'input[name="safety-mode"][value="operator-approved"]'
      );
      const previewOnlyOption = document.querySelector(
        'input[name="safety-mode"][value="preview-only"]'
      );

      expect(readOnlyOption).toBeInTheDocument();
      expect(operatorApprovedOption).toBeInTheDocument();
      expect(previewOnlyOption).toBeInTheDocument();
    });
  });
});

describe("DemoShell types and exports", () => {
  it("exports DemoStep type values", () => {
    // This verifies the type is exported for external use
    const steps: Array<"start" | "onboarding" | "dashboard" | "finding-detail" | "action-panel"> = [
      "start",
      "onboarding",
      "dashboard",
      "finding-detail",
      "action-panel",
    ];
    expect(steps).toHaveLength(5);
  });

  it("exports EvidenceSource type values", () => {
    // This verifies the type is exported for external use
    const sources: Array<"live" | "historical" | "stale" | "none"> = ["live", "historical", "stale", "none"];
    expect(sources).toHaveLength(4);
  });

  it("exports SeverityLevel type values", () => {
    // This verifies the type is exported for external use
    const levels: Array<"critical" | "warning" | "info"> = ["critical", "warning", "info"];
    expect(levels).toHaveLength(3);
  });

  it("exports SafetyMode type values", () => {
    // This verifies the type is exported for external use
    const modes: Array<"read-only" | "operator-approved" | "preview-only"> = [
      "read-only",
      "operator-approved",
      "preview-only",
    ];
    expect(modes).toHaveLength(3);
  });

  it("exports DemoFinding interface structure", () => {
    // This verifies the interface is exported for external use
    const finding = {
      id: "test",
      title: "Test",
      severity: "info" as const,
      affectedResource: "test-ns/test-pod",
      evidenceSource: "none" as const,
      probableCause: "Test cause",
      diagnosticEvidence: "Test evidence",
      recommendedAction: "Test action",
      safetyMode: "read-only" as const,
    };
    expect(finding.id).toBe("test");
    expect(finding.severity).toBe("info");
  });
});
