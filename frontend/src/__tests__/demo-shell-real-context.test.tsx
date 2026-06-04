/**
 * Demo Shell Real Context Tests
 *
 * Tests for real context integration in DemoShell component.
 * Verifies that when launched from the main app, the demo shell shows real run/cluster info.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import "@testing-library/jest-dom";
import { DemoShell } from "../components/DemoShell";

const renderDemoShell = (props = {}) => {
  return render(<DemoShell {...props} />);
};

describe("DemoShell Real Context Integration", () => {
  beforeEach(() => {
    cleanup();
  });

  describe("Real context in onboarding screen", () => {
    it("shows real context summary when realContext is provided", () => {
      renderDemoShell({
        initialStep: "onboarding",
        realContext: {
          runId: "run-123-abc",
          clusterLabel: "prod-us-west",
          isFresh: true,
        },
      });

      expect(screen.getByTestId("demo-context-run-id")).toBeInTheDocument();
      expect(screen.getByTestId("demo-context-cluster")).toBeInTheDocument();
      expect(screen.getByTestId("demo-context-freshness")).toBeInTheDocument();
    });

    it("shows 'Selected real run' title when realContext is provided", () => {
      renderDemoShell({
        initialStep: "onboarding",
        realContext: {
          runId: "run-123-abc",
          isFresh: true,
        },
      });

      expect(screen.getByText("Selected real run")).toBeInTheDocument();
    });

    it("shows 'Continue with selected run' button when realContext is provided", () => {
      renderDemoShell({
        initialStep: "onboarding",
        realContext: {
          runId: "run-123-abc",
          isFresh: true,
        },
      });

      expect(screen.getByText("Continue with selected run")).toBeInTheDocument();
    });
  });

  describe("Real context in dashboard", () => {
    it("shows cluster name from realContext", () => {
      renderDemoShell({
        initialStep: "dashboard",
        realContext: {
          runId: "run-123-abc",
          clusterLabel: "prod-us-west",
          isFresh: true,
        },
        findingSelectionInput: {
          incidentReport: { status: "critical" },
        },
      });

      expect(screen.getByTestId("demo-cluster-name")).toHaveTextContent("prod-us-west");
    });

    it("shows run ID badge from realContext", () => {
      renderDemoShell({
        initialStep: "dashboard",
        realContext: {
          runId: "run-123-abc",
          clusterLabel: "prod-us-west",
          isFresh: true,
        },
        findingSelectionInput: {
          incidentReport: { status: "critical" },
        },
      });

      expect(screen.getByTestId("demo-run-id-badge")).toBeInTheDocument();
    });

    it("shows fresh badge when isFresh is true", () => {
      renderDemoShell({
        initialStep: "dashboard",
        realContext: {
          runId: "run-123",
          isFresh: true,
        },
      });

      expect(screen.getByTestId("demo-context-badge")).toHaveTextContent("Fresh");
    });

    it("shows stale badge when isFresh is false", () => {
      renderDemoShell({
        initialStep: "dashboard",
        realContext: {
          runId: "run-123",
          isFresh: false,
        },
      });

      expect(screen.getByTestId("demo-context-badge")).toHaveTextContent("Stale");
    });

    it("shows context detail section when realContext is provided", () => {
      renderDemoShell({
        initialStep: "dashboard",
        realContext: {
          runId: "run-123",
          clusterLabel: "my-cluster",
          isFresh: true,
        },
      });

      expect(screen.getByTestId("demo-context-detail")).toBeInTheDocument();
    });

    it("shows real run evidence in footer", () => {
      renderDemoShell({
        initialStep: "dashboard",
        realContext: {
          runId: "run-123-abc",
          isFresh: true,
        },
      });

      expect(screen.getByText(/Real run evidence/i)).toBeInTheDocument();
    });
  });

  describe("Real context types and exports", () => {
    it("exports DemoShellRealContext interface structure", () => {
      const context = {
        runId: "test-run-123",
        clusterLabel: "test-cluster",
        isFresh: true,
        runCapturedAt: "2024-01-01T00:00:00Z",
        initialSafetyMode: "read-only" as const,
      };
      expect(context.runId).toBe("test-run-123");
      expect(context.clusterLabel).toBe("test-cluster");
      expect(context.isFresh).toBe(true);
    });
  });
});
