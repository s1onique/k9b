/**
 * Demo Shell Finding Selection Integration Tests
 *
 * Tests for finding selection integration with the DemoShell component.
 * Verifies the deterministic finding selection priority:
 * live critical → live warning → historical real → clean fallback.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import "@testing-library/jest-dom";
import { DemoShell } from "../components/DemoShell";

// Helper to render the demo shell with cleanup
const renderDemoShell = (props = {}) => {
  return render(<DemoShell {...props} />);
};

describe("DemoShell finding selection integration", () => {
  beforeEach(() => {
    cleanup();
  });

  it("renders dashboard with live critical finding from selection input", () => {
    const findingSelectionInput = {
      incidentReport: {
        status: "critical",
        resource: "default/nginx-pod",
        findingType: "CrashLoopBackOff",
      },
    };

    renderDemoShell({
      initialStep: "dashboard",
      findingSelectionInput,
    });

    // Should show the finding with critical severity badge
    expect(screen.getByText("Critical: CrashLoopBackOff")).toBeInTheDocument();
    expect(screen.getByText("default/nginx-pod")).toBeInTheDocument();
  });

  it("renders dashboard with live warning finding from selection input", () => {
    const findingSelectionInput = {
      incidentReport: {
        status: "warning",
        resource: "monitoring/prometheus-pod",
      },
    };

    renderDemoShell({
      initialStep: "dashboard",
      findingSelectionInput,
    });

    // Should show the finding with warning severity (title is "Warning finding detected")
    expect(screen.getByText(/Warning finding detected/i)).toBeInTheDocument();
    expect(screen.getByText("monitoring/prometheus-pod")).toBeInTheDocument();
  });

  it("renders historical real findings when no live findings available", () => {
    const historicalFindings = [
      {
        id: "hist-1",
        title: "Critical: FailedScheduling",
        severity: "critical" as const,
        affectedResource: "app/job-pod",
        evidenceSource: "live" as const,
        probableCause: "Insufficient resources",
        diagnosticEvidence: "Node capacity exceeded",
        recommendedAction: "Review resource requests",
        safetyMode: "preview-only" as const,
      },
    ];

    renderDemoShell({
      initialStep: "dashboard",
      findingSelectionInput: {},
      historicalFindings,
    });

    // Should show historical finding with Historical Real Run badge
    expect(screen.getByText("Critical: FailedScheduling")).toBeInTheDocument();
    expect(screen.getByText("Historical Real Run")).toBeInTheDocument();
  });

  it("shows clean cluster fallback when no findings available", () => {
    renderDemoShell({
      initialStep: "dashboard",
      findingSelectionInput: {},
    });

    // Should show clean cluster message
    expect(screen.getByText(/No critical issues found/i)).toBeInTheDocument();
    expect(screen.getByText(/No fake incidents were injected/i)).toBeInTheDocument();
  });

  it("shows stale badge for stale findings", () => {
    const findingSelectionInput = {
      incidentReport: {
        status: "warning",
        resource: "default/pod",
      },
      freshness: {
        isStale: true,
      },
    };

    renderDemoShell({
      initialStep: "dashboard",
      findingSelectionInput,
    });

    // Should show stale badge
    expect(screen.getByText("Stale")).toBeInTheDocument();
  });

  it("renders finding detail with evidence source", () => {
    const findingSelectionInput = {
      incidentReport: {
        status: "critical",
        resource: "default/nginx-pod",
        findingType: "CrashLoopBackOff",
      },
    };

    renderDemoShell({
      initialStep: "finding-detail",
      findingSelectionInput,
    });

    // Should show evidence source badge
    expect(screen.getByText("Live")).toBeInTheDocument();
    expect(screen.getByText("Critical: CrashLoopBackOff")).toBeInTheDocument();
  });

  it("renders finding detail with recommended action section", () => {
    const findingSelectionInput = {
      incidentReport: {
        status: "critical",
        resource: "default/nginx-pod",
        findingType: "CrashLoopBackOff",
      },
    };

    renderDemoShell({
      initialStep: "finding-detail",
      findingSelectionInput,
    });

    // Should show recommended action section header (h3 element)
    const sectionHeaders = document.querySelectorAll("h3.demo-section-label");
    const hasRecommendedActionSection = Array.from(sectionHeaders).some(
      (el) => el.textContent === "Recommended action"
    );
    expect(hasRecommendedActionSection).toBe(true);
  });

  it("renders action panel with preview-only safety mode", () => {
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

    // Should show preview-only safety mode badge
    const badgeElement = document.querySelector(".demo-badge--safety-previewonly");
    expect(badgeElement).toBeInTheDocument();
    expect(badgeElement).toHaveTextContent("Preview only");
  });

  it("does not contain forbidden phrases in finding selection", () => {
    const findingSelectionInput = {
      incidentReport: {
        status: "critical",
        resource: "default/nginx-pod",
        findingType: "CrashLoopBackOff",
      },
    };

    renderDemoShell({
      initialStep: "finding-detail",
      findingSelectionInput,
    });

    const container = document.querySelector(".demo-shell-overlay");
    expect(container?.textContent).not.toMatch(/\bself-healing\b/i);
    expect(container?.textContent).not.toMatch(/\bguaranteed root cause\b/i);
    expect(container?.textContent).not.toMatch(/\bautomatic production fix\b/i);
    expect(container?.textContent).not.toMatch(/\bfixes any Kubernetes issue\b/i);
    expect(container?.textContent).not.toMatch(/\bfully autonomous\b/i);
  });

  it("shows evidence source Live badge for fresh findings", () => {
    const findingSelectionInput = {
      incidentReport: {
        status: "critical",
        resource: "default/pod",
        findingType: "OOMKilled",
      },
      freshness: {
        age: 60, // Fresh
      },
    };

    renderDemoShell({
      initialStep: "dashboard",
      findingSelectionInput,
    });

    // Check for Live badge on the finding card (more specific selector)
    const liveBadges = document.querySelectorAll(".demo-badge--live");
    expect(liveBadges.length).toBeGreaterThan(0);
  });

  it("maps CrashLoopBackOff to critical severity in UI", () => {
    const findingSelectionInput = {
      incidentReport: {
        findingType: "CrashLoopBackOff",
        resource: "production/api-pod",
      },
    };

    renderDemoShell({
      initialStep: "dashboard",
      findingSelectionInput,
    });

    // Should show critical severity badge with finding title
    expect(screen.getByText("Critical: CrashLoopBackOff")).toBeInTheDocument();
    expect(screen.getByText("production/api-pod")).toBeInTheDocument();
  });

  it("maps ImagePullBackOff to critical severity in UI", () => {
    const findingSelectionInput = {
      incidentReport: {
        findingType: "ImagePullBackOff",
        resource: "staging/web-pod",
      },
    };

    renderDemoShell({
      initialStep: "dashboard",
      findingSelectionInput,
    });

    expect(screen.getByText("Critical: ImagePullBackOff")).toBeInTheDocument();
    expect(screen.getByText("staging/web-pod")).toBeInTheDocument();
  });

  it("displays 'Historical Real Run' label for historical evidence", () => {
    const historicalFindings = [
      {
        id: "hist-1",
        title: "Warning: Pending",
        severity: "warning" as const,
        affectedResource: "default/pod",
        evidenceSource: "live" as const,
        probableCause: "Pod pending scheduling",
        diagnosticEvidence: "Insufficient cluster resources",
        recommendedAction: "Check resource quotas",
        safetyMode: "preview-only" as const,
      },
    ];

    renderDemoShell({
      initialStep: "dashboard",
      findingSelectionInput: {},
      historicalFindings,
    });

    expect(screen.getByText("Historical Real Run")).toBeInTheDocument();
  });
});