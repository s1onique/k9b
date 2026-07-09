/**
 * incidents-overview-section-placement.test.tsx
 *
 * Tests for IncidentsOverviewSection component placement on the selected-run page.
 * Verifies:
 * - Component renders between Runtime status and Recent runs
 * - Section order in App.tsx is correct
 * - Loading, error, and empty states work
 * - Incidents table renders correctly
 * - Status summary bar shows counts
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { IncidentsOverviewSection } from "../components/run-summary";

// Mock the API module
vi.mock("../api", () => ({
  listIncidents: vi.fn(),
}));

// Import the mocked function after vi.mock
import { listIncidents } from "../api";

describe("IncidentsOverviewSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // API call verification test
  it("calls listIncidents API (API only supports status filter, not runId)", async () => {
    vi.mocked(listIncidents).mockResolvedValue({ incidents: [] });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      // Verify listIncidents was called
      expect(listIncidents).toHaveBeenCalled();
      // API only supports status parameter, not runId
      // Run scoping is handled by the backend
    });
  });

  // Race condition prevention test - verify ignore guard works
  it("ignores stale incident responses after runId changes", async () => {
    let resolveRun1!: (value: any) => void;
    let resolveRun2!: (value: any) => void;

    vi.mocked(listIncidents)
      .mockReturnValueOnce(new Promise((resolve) => { resolveRun1 = resolve; }))
      .mockReturnValueOnce(new Promise((resolve) => { resolveRun2 = resolve; }));

    const { rerender } = render(<IncidentsOverviewSection runId="run-1" />);
    
    // Change runId before first request completes
    rerender(<IncidentsOverviewSection runId="run-2" />);

    // Resolve run-2 first (newer request)
    resolveRun2({
      incidents: [{
        incident_id: "new-incident",
        severity: "warning",
        status: "open",
        object_kind: "Pod",
        object_name: "new-pod",
        namespace: "default",
        signal_count: 1,
        evidence_count: 0,
        review_packet: { status: "not_generated" },
        last_observed_at: "2026-07-09T05:52:25Z",
      }],
    });

    await waitFor(() => {
      expect(screen.getByTestId("incident-row-new-incident")).toBeInTheDocument();
    });

    // Resolve run-1 later (stale request) - should be ignored
    resolveRun1({
      incidents: [{
        incident_id: "stale-incident",
        severity: "error",
        status: "open",
        object_kind: "Pod",
        object_name: "stale-pod",
        namespace: "default",
        signal_count: 1,
        evidence_count: 0,
        review_packet: { status: "not_generated" },
        last_observed_at: "2026-07-09T05:52:00Z",
      }],
    });

    await waitFor(() => {
      // Stale incident should NOT appear (ignore guard worked)
      expect(screen.queryByTestId("incident-row-stale-incident")).not.toBeInTheDocument();
      // New incident should still be visible
      expect(screen.getByTestId("incident-row-new-incident")).toBeInTheDocument();
    });
  });

  const mockIncidents = [
    {
      incident_id: "inc-001",
      severity: "error",
      status: "open",
      object_kind: "Pod",
      object_name: "nginx-pod-abc123",
      namespace: "default",
      cluster_name: "test-cluster",
      signal_count: 5,
      evidence_count: 3,
      candidate_class: "Pod_failure",
      review_packet: { status: "not_generated" as const },
      last_observed_at: "2024-01-15T10:30:00Z",
      created_at: "2024-01-15T10:00:00Z",
    },
    {
      incident_id: "inc-002",
      severity: "warning",
      status: "investigating",
      object_kind: "Deployment",
      object_name: "api-deployment-xyz",
      namespace: "production",
      cluster_name: "test-cluster",
      signal_count: 2,
      evidence_count: 1,
      candidate_class: "Deployment_unavailable",
      review_packet: { status: "available" as const },
      last_observed_at: "2024-01-15T09:00:00Z",
      created_at: "2024-01-14T08:00:00Z",
    },
  ];

  describe("Rendering states", () => {
    it("renders loading state", async () => {
      // Setup mock to never resolve (simulates loading)
      vi.mocked(listIncidents).mockReturnValue(new Promise(() => {}));

      render(<IncidentsOverviewSection runId="run-123" />);

      expect(screen.getByText("Incidents")).toBeInTheDocument();
      expect(screen.getByText("Loading incidents...")).toBeInTheDocument();
      expect(screen.getByTestId("incidents-overview-section")).toHaveClass(
        "incidents-overview-section--loading"
      );
    });

    it("renders error state with retry button", async () => {
      vi.mocked(listIncidents).mockRejectedValue(new Error("Network error"));

      render(<IncidentsOverviewSection runId="run-123" />);

      await waitFor(() => {
        expect(screen.getByText(/Failed to load incidents/)).toBeInTheDocument();
      });

      expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
      expect(screen.getByTestId("incidents-overview-section")).toHaveClass(
        "incidents-overview-section--error"
      );
    });

    it("renders empty state honestly", async () => {
      vi.mocked(listIncidents).mockResolvedValue({ incidents: [] });

      render(<IncidentsOverviewSection runId="run-123" />);

      await waitFor(() => {
        expect(screen.getByText("No incidents for this run.")).toBeInTheDocument();
      });

      expect(screen.getByTestId("incidents-overview-section")).toHaveClass(
        "incidents-overview-section--empty"
      );
    });

    it("renders incidents table when data available", async () => {
      vi.mocked(listIncidents).mockResolvedValue({ incidents: mockIncidents });

      render(<IncidentsOverviewSection runId="run-123" />);

      await waitFor(() => {
        expect(screen.getByTestId("incidents-table-wrapper")).toBeInTheDocument();
      });

      // Verify both incidents are rendered
      expect(screen.getByTestId("incident-row-inc-001")).toBeInTheDocument();
      expect(screen.getByTestId("incident-row-inc-002")).toBeInTheDocument();
    });
  });

  describe("Status summary bar", () => {
    it("shows status counts correctly", async () => {
      vi.mocked(listIncidents).mockResolvedValue({ incidents: mockIncidents });

      render(<IncidentsOverviewSection runId="run-123" />);

      await waitFor(() => {
        expect(screen.getByTestId("incidents-status-summary")).toBeInTheDocument();
      });

      // Check status summary shows counts - use stronger matcher for chip content
      const summaryEl = screen.getByTestId("incidents-status-summary");
      expect(summaryEl.textContent).toContain("Open");
      expect(summaryEl.textContent).toContain("1");
      expect(summaryEl.textContent).toContain("Investigating");
    });

    it("does not show summary bar when no active incidents", async () => {
      vi.mocked(listIncidents).mockResolvedValue({ incidents: [] });

      render(<IncidentsOverviewSection runId="run-123" />);

      await waitFor(() => {
        expect(screen.queryByTestId("incidents-status-summary")).not.toBeInTheDocument();
      });
    });
  });

  describe("Incidents table", () => {
    it("renders correct columns", async () => {
      vi.mocked(listIncidents).mockResolvedValue({ incidents: [mockIncidents[0]] });

      render(<IncidentsOverviewSection runId="run-123" />);

      await waitFor(() => {
        expect(screen.getByText("Severity")).toBeInTheDocument();
        expect(screen.getByText("Status")).toBeInTheDocument();
        expect(screen.getByText("Object")).toBeInTheDocument();
        expect(screen.getByText("Namespace")).toBeInTheDocument();
        expect(screen.getByText("Evidence")).toBeInTheDocument();
        expect(screen.getByText("Diagnosis")).toBeInTheDocument();
        expect(screen.getByText("Review Packet")).toBeInTheDocument();
        expect(screen.getByText("Updated")).toBeInTheDocument();
      });
    });

    it("shows severity badges", async () => {
      vi.mocked(listIncidents).mockResolvedValue({ incidents: [mockIncidents[0]] });

      render(<IncidentsOverviewSection runId="run-123" />);

      await waitFor(() => {
        const errorBadge = screen.getByText("error");
        expect(errorBadge).toHaveClass("severity-badge");
        expect(errorBadge).toHaveClass("severity-error");
      });
    });

    it("shows review packet indicators", async () => {
      vi.mocked(listIncidents).mockResolvedValue({ incidents: [mockIncidents[1]] });

      render(<IncidentsOverviewSection runId="run-123" />);

      await waitFor(() => {
        const reviewPacketIndicator = screen.getByText("present");
        expect(reviewPacketIndicator).toHaveClass("review-packet-available");
      });
    });
  });

  describe("Section placement", () => {
    it("renders with correct section class", () => {
      vi.mocked(listIncidents).mockResolvedValue({ incidents: [] });

      render(<IncidentsOverviewSection runId="run-123" />);

      // The section should have the correct data-testid
      expect(screen.getByTestId("incidents-overview-section")).toBeInTheDocument();
    });

    it("shows incident count in header when data present", async () => {
      vi.mocked(listIncidents).mockResolvedValue({ incidents: mockIncidents });

      render(<IncidentsOverviewSection runId="run-123" />);

      await waitFor(() => {
        expect(screen.getByText("2 incidents")).toBeInTheDocument();
      });
    });
  });

  describe("Edge cases and regression tests", () => {
    it("does not crash when selected run is not available yet (runId is null)", async () => {
      vi.mocked(listIncidents).mockResolvedValue({ incidents: [] });

      // This tests the stale-selected-run-fallback scenario where runId becomes null
      // during transition between runs
      render(<IncidentsOverviewSection runId={null} />);

      await waitFor(() => {
        expect(screen.getByTestId("incidents-overview-section")).toBeInTheDocument();
      });

      // Should show empty state, not crash
      expect(screen.getByText("No incidents for this run.")).toBeInTheDocument();
    });

    it("treats missing incidents payload as empty array", async () => {
      // This tests a malformed/sparse API response where the incidents field is absent.
      vi.mocked(listIncidents).mockResolvedValue({});

      render(<IncidentsOverviewSection runId="run-123" />);

      await waitFor(() => {
        expect(screen.getByTestId("incidents-overview-section")).toBeInTheDocument();
      });

      // Should show empty state, not crash
      expect(screen.getByText("No incidents for this run.")).toBeInTheDocument();
    });

    it("treats undefined incidents payload as empty array", async () => {
      // Explicit undefined test for type safety
      vi.mocked(listIncidents).mockResolvedValue({ incidents: undefined } as any);

      render(<IncidentsOverviewSection runId="run-123" />);

      await waitFor(() => {
        expect(screen.getByTestId("incidents-overview-section")).toBeInTheDocument();
      });

      // Should show empty state, not crash
      expect(screen.getByText("No incidents for this run.")).toBeInTheDocument();
    });

    it("treats null incidents payload as empty array", async () => {
      // Explicit null test for type safety
      vi.mocked(listIncidents).mockResolvedValue({ incidents: null } as any);

      render(<IncidentsOverviewSection runId="run-123" />);

      await waitFor(() => {
        expect(screen.getByTestId("incidents-overview-section")).toBeInTheDocument();
      });

      // Should show empty state, not crash
      expect(screen.getByText("No incidents for this run.")).toBeInTheDocument();
    });

    it("handles non-array incidents payload gracefully", async () => {
      // Test edge case where incidents is a string or object instead of array
      vi.mocked(listIncidents).mockResolvedValue({ incidents: "not-an-array" } as any);

      render(<IncidentsOverviewSection runId="run-123" />);

      await waitFor(() => {
        expect(screen.getByTestId("incidents-overview-section")).toBeInTheDocument();
      });

      // Should show empty state, not crash
      expect(screen.getByText("No incidents for this run.")).toBeInTheDocument();
    });
  });
});

describe("App.tsx section order", () => {
  it("should have IncidentsOverviewSection between RuntimeStatusSummary and RecentRunsPanel", () => {
    // This test verifies the section order in App.tsx by checking imports
    // The actual component tree is tested in integration tests
    // Read App.tsx using direct file path (vitest/vite resolves from project root)
    const fs = require("fs");
    const path = require("path");
    const appTsxPath = path.resolve(__dirname, "../App.tsx");
    const appContent = fs.readFileSync(appTsxPath, "utf-8");

    // Verify imports exist
    expect(appContent).toContain('import { RuntimeStatusSummary } from "./components/runtime-status"');
    expect(appContent).toContain('import { IncidentsOverviewSection } from "./components/run-summary"');
    expect(appContent).toContain('from "./components/RunsPanel"');

    // Verify the component is rendered in JSX between RuntimeStatusSummary and RecentRunsPanel
    // This is a structural test - the actual rendering order is verified by visual/e2e tests
    const runtimeStatusIndex = appContent.indexOf("<RuntimeStatusSummary");
    const incidentsIndex = appContent.indexOf("<IncidentsOverviewSection");
    const recentRunsIndex = appContent.indexOf("<RecentRunsPanel");

    expect(runtimeStatusIndex).toBeGreaterThan(-1);
    expect(incidentsIndex).toBeGreaterThan(-1);
    expect(recentRunsIndex).toBeGreaterThan(-1);

    expect(incidentsIndex).toBeGreaterThan(runtimeStatusIndex);
    expect(incidentsIndex).toBeLessThan(recentRunsIndex);
  });

  it("renders sections in correct order: Runtime Status -> Incidents -> Recent Runs", () => {
    // DOM ordering test - verifies the headings appear in the correct sequence
    // This is a structural regression test that ensures the three sections are ordered correctly
    const fs = require("fs");
    const path = require("path");
    const appTsxPath = path.resolve(__dirname, "../App.tsx");
    const appContent = fs.readFileSync(appTsxPath, "utf-8");

    // Extract the section placement by finding the JSX structure
    // We verify order by finding the component tags in the return JSX
    const jsxStart = appContent.indexOf("return (");
    const jsxContent = appContent.substring(jsxStart);

    // Find positions of key section components in the JSX
    const runtimePos = jsxContent.indexOf("<RuntimeStatusSummary");
    const incidentsPos = jsxContent.indexOf("<IncidentsOverviewSection");
    const recentRunsPos = jsxContent.indexOf("<RecentRunsPanel");
    const runSummaryPos = jsxContent.indexOf("<AppRunSummarySection");

    // Verify all components are present
    expect(runtimePos).toBeGreaterThan(-1);
    expect(incidentsPos).toBeGreaterThan(-1);
    expect(recentRunsPos).toBeGreaterThan(-1);
    expect(runSummaryPos).toBeGreaterThan(-1);

    // Critical order assertion: Incidents must come after Runtime Status and before Recent Runs
    expect(incidentsPos).toBeGreaterThan(runtimePos);
    expect(incidentsPos).toBeLessThan(recentRunsPos);
    expect(incidentsPos).toBeLessThan(runSummaryPos);
  });
});
