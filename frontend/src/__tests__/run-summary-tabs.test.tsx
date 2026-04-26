/**
 * run-summary-tabs.test.tsx
 *
 * Focused tests for RunSummaryTabs component.
 * Tests tab behavior, ARIA accessibility, and content rendering per tab.
 *
 * Phase 2 - Run Summary UX Redesign: Tab interface for RunSummaryPanel.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import type { NextCheckPlanCandidate, NextCheckStatusVariant } from "../types";

import { RunSummaryTabs } from "../components/run-summary/RunSummaryTabs";

// ============================================================================
// Test fixtures
// ============================================================================

const mockRunSummaryStats = [
  { label: "Clusters", value: 5 },
  { label: "Degraded", value: 2 },
  { label: "Proposals", value: 10 },
];

const mockRunPlan = {
  summary: "Planner generated multiple advisory checks.",
  artifactPath: "/artifacts/next-check-plan.json",
  status: "planned",
  candidateCount: 3,
};

const mockRunPlanCandidates: NextCheckPlanCandidate[] = [
  {
    description: "Check 1",
    targetCluster: "cluster-a",
    sourceReason: null,
    expectedSignal: null,
    suggestedCommandFamily: "kubectl-logs",
    safeToAutomate: true,
    requiresOperatorApproval: false,
    riskLevel: "low",
    estimatedCost: "low",
    confidence: "high",
    priorityLabel: null,
    gatingReason: null,
    duplicateOfExistingEvidence: false,
    duplicateEvidenceDescription: null,
    candidateIndex: 0,
  },
  {
    description: "Check 2",
    targetCluster: "cluster-b",
    sourceReason: null,
    expectedSignal: null,
    suggestedCommandFamily: "kubectl-get",
    safeToAutomate: true,
    requiresOperatorApproval: true,
    riskLevel: "medium",
    estimatedCost: "medium",
    confidence: "medium",
    priorityLabel: null,
    gatingReason: null,
    duplicateOfExistingEvidence: false,
    duplicateEvidenceDescription: null,
    candidateIndex: 1,
  },
];

const mockDiscoveryVariantOrder: NextCheckStatusVariant[] = ["safe", "approval", "approved", "duplicate", "stale"];
const mockDiscoveryVariantCounts: Record<NextCheckStatusVariant, number> = {
  safe: 1,
  approval: 1,
  approved: 0,
  duplicate: 0,
  stale: 0,
};

const mockArtifacts = [
  { label: "run manifest", path: "/artifacts/run-manifest.json" },
  { label: "assessment", path: "/artifacts/assessment.json" },
];

// ============================================================================
// Test setup helper
// ============================================================================

const defaultProps = {
  activeTab: "overview" as const,
  onTabChange: vi.fn(),
  runSummaryStats: mockRunSummaryStats,
  runStatsSummary: "Last 32s · Runs 12 · P50 24s",
  runLlmStatsLine: <span data-testid="llm-stats">Calls: 3 · OK: 2 · Failed: 1</span>,
  historicalLlmStatsLine: <span data-testid="historical-stats">Historical: 18 calls</span>,
  providerBreakdown: "k8sgpt 2 (0 failed)",
  runPlan: mockRunPlan,
  runPlanCandidates: mockRunPlanCandidates,
  planSummaryText: "Planner generated multiple advisory checks.",
  planStatusText: "planned",
  plannerReasonText: "Planner data unavailable",
  plannerHint: null,
  plannerNextActionHint: "Check the planner artifact",
  plannerArtifactUrl: "http://localhost/artifacts/next-check-plan.json",
  planCandidateCountLabel: "3 candidates",
  discoveryVariantOrder: mockDiscoveryVariantOrder,
  discoveryVariantCounts: mockDiscoveryVariantCounts,
  discoveryClusters: ["cluster-a", "cluster-b"],
  onReviewNextChecks: vi.fn(),
  onFocusClusterForNextChecks: vi.fn(),
  artifacts: mockArtifacts,
};

// ============================================================================
// RunSummaryTabs tests
// ============================================================================

describe("RunSummaryTabs", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --------------------------------------------------------------------
  // Test 1: Overview tab is selected by default
  // --------------------------------------------------------------------
  test("1. Overview tab is selected by default", () => {
    render(<RunSummaryTabs {...defaultProps} />);

    // Overview tab should be active and have aria-selected="true"
    const overviewTab = screen.getByRole("tab", { name: "Overview" });
    expect(overviewTab).toHaveAttribute("aria-selected", "true");
    expect(overviewTab).toHaveClass("active");

    // Other tabs should not be active
    const nextChecksTab = screen.getByRole("tab", { name: "Next checks" });
    expect(nextChecksTab).toHaveAttribute("aria-selected", "false");
    expect(nextChecksTab).not.toHaveClass("active");

    const telemetryTab = screen.getByRole("tab", { name: "Telemetry" });
    expect(telemetryTab).toHaveAttribute("aria-selected", "false");
    expect(telemetryTab).not.toHaveClass("active");

    const artifactsTab = screen.getByRole("tab", { name: "Artifacts" });
    expect(artifactsTab).toHaveAttribute("aria-selected", "false");
    expect(artifactsTab).not.toHaveClass("active");
  });

  // --------------------------------------------------------------------
  // Test 2: Clicking Next checks shows next-check content
  // --------------------------------------------------------------------
  test("2. Clicking Next checks shows next-check content", () => {
    const { rerender } = render(<RunSummaryTabs {...defaultProps} />);

    // Click "Next checks" tab
    const nextChecksTab = screen.getByRole("tab", { name: "Next checks" });
    nextChecksTab.click();

    // Verify callback was called with correct tab id
    expect(defaultProps.onTabChange).toHaveBeenCalledWith("next-checks");

    // Re-render with Next checks active
    rerender(<RunSummaryTabs {...defaultProps} activeTab="next-checks" />);

    // Verify next-check content is visible (use heading for specificity)
    expect(screen.getByRole("heading", { name: "Planner candidates" })).toBeInTheDocument();
    expect(screen.getByText("3 candidates")).toBeInTheDocument();
    expect(screen.getByText("cluster-a")).toBeInTheDocument();
    expect(screen.getByText("cluster-b")).toBeInTheDocument();
  });

  // --------------------------------------------------------------------
  // Test 3: Clicking Telemetry shows LLM telemetry content
  // --------------------------------------------------------------------
  test("3. Clicking Telemetry shows LLM telemetry content", () => {
    const { rerender } = render(<RunSummaryTabs {...defaultProps} />);

    // Click "Telemetry" tab
    const telemetryTab = screen.getByRole("tab", { name: "Telemetry" });
    telemetryTab.click();

    // Verify callback was called with correct tab id
    expect(defaultProps.onTabChange).toHaveBeenCalledWith("telemetry");

    // Re-render with Telemetry active
    rerender(<RunSummaryTabs {...defaultProps} activeTab="telemetry" />);

    // Verify telemetry content is visible
    expect(screen.getByText("LLM telemetry")).toBeInTheDocument();
    expect(screen.getByTestId("llm-stats")).toBeInTheDocument();
    expect(screen.getByText(/Providers: k8sgpt 2/)).toBeInTheDocument();
  });

  // --------------------------------------------------------------------
  // Test 4: Clicking Artifacts shows artifact links
  // --------------------------------------------------------------------
  test("4. Clicking Artifacts shows artifact links", () => {
    const { rerender } = render(<RunSummaryTabs {...defaultProps} />);

    // Click "Artifacts" tab
    const artifactsTab = screen.getByRole("tab", { name: "Artifacts" });
    artifactsTab.click();

    // Verify callback was called with correct tab id
    expect(defaultProps.onTabChange).toHaveBeenCalledWith("artifacts");

    // Re-render with Artifacts active
    rerender(<RunSummaryTabs {...defaultProps} activeTab="artifacts" />);

    // Verify artifact links are visible
    expect(screen.getByText("run manifest")).toBeInTheDocument();
    expect(screen.getByText("assessment")).toBeInTheDocument();
  });

  // --------------------------------------------------------------------
  // Test 5: Tab buttons expose correct ARIA roles and selected state
  // --------------------------------------------------------------------
  test("5. Tab buttons expose correct ARIA roles and selected state", () => {
    render(<RunSummaryTabs {...defaultProps} activeTab="telemetry" />);

    // Container should have role="tablist"
    const tablist = screen.getByRole("tablist");
    expect(tablist).toBeInTheDocument();
    expect(tablist).toHaveAttribute("aria-label", "Run summary sections");

    // All tabs should have role="tab"
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(4);

    // Telemetry should be active with aria-selected="true"
    const telemetryTab = screen.getByRole("tab", { name: "Telemetry" });
    expect(telemetryTab).toHaveAttribute("aria-selected", "true");
    expect(telemetryTab).toHaveClass("active");

    // Other tabs should not be active
    const overviewTab = screen.getByRole("tab", { name: "Overview" });
    expect(overviewTab).toHaveAttribute("aria-selected", "false");

    const nextChecksTab = screen.getByRole("tab", { name: "Next checks" });
    expect(nextChecksTab).toHaveAttribute("aria-selected", "false");

    const artifactsTab = screen.getByRole("tab", { name: "Artifacts" });
    expect(artifactsTab).toHaveAttribute("aria-selected", "false");

    // Active tab panel should have role="tabpanel"
    const activePanel = screen.getByRole("tabpanel");
    expect(activePanel).toBeInTheDocument();
    expect(activePanel).toHaveAttribute("id", "panel-telemetry");
  });

  // --------------------------------------------------------------------
  // Test 6: PastRunNotice still renders independently of active tab
  //         (This is tested via integration - PastRunNotice is rendered
  //          outside the tabs in RunSummaryPanel)
  // --------------------------------------------------------------------
  test("6. Tab content is conditionally rendered based on active tab", () => {
    const { rerender } = render(<RunSummaryTabs {...defaultProps} activeTab="overview" />);

    // Overview panel should be visible (not hidden)
    expect(screen.getByTestId("panel-overview")).not.toHaveAttribute("hidden");
    // Other panels should be hidden
    expect(screen.getByTestId("panel-next-checks")).toHaveAttribute("hidden");

    // Switch to Next checks
    rerender(<RunSummaryTabs {...defaultProps} activeTab="next-checks" />);

    // Next checks panel should be visible, overview hidden
    expect(screen.getByTestId("panel-overview")).toHaveAttribute("hidden");
    expect(screen.getByTestId("panel-next-checks")).not.toHaveAttribute("hidden");

    // Switch to Telemetry
    rerender(<RunSummaryTabs {...defaultProps} activeTab="telemetry" />);

    // Telemetry panel should be visible
    expect(screen.getByTestId("panel-telemetry")).not.toHaveAttribute("hidden");
    expect(screen.getByTestId("panel-next-checks")).toHaveAttribute("hidden");

    // Switch to Artifacts
    rerender(<RunSummaryTabs {...defaultProps} activeTab="artifacts" />);

    // Artifacts panel should be visible
    expect(screen.getByTestId("panel-artifacts")).not.toHaveAttribute("hidden");
    expect(screen.getByTestId("panel-telemetry")).toHaveAttribute("hidden");
  });

  // --------------------------------------------------------------------
  // Additional tests
  // --------------------------------------------------------------------

  test("shows empty state when no artifacts", () => {
    render(<RunSummaryTabs {...defaultProps} activeTab="artifacts" artifacts={[]} />);

    expect(screen.getByText("No artifacts available for this run.")).toBeInTheDocument();
  });

  test("shows overview content with KPI stats", () => {
    render(<RunSummaryTabs {...defaultProps} activeTab="overview" />);

    // KPI stats should be visible in Overview tab
    expect(screen.getByText("Clusters")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("Degraded")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("Proposals")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();

    // Duration summary should be visible
    expect(screen.getByText(/Last 32s/)).toBeInTheDocument();
  });

  test("calls onFocusClusterForNextChecks when cluster badge clicked", () => {
    render(<RunSummaryTabs {...defaultProps} activeTab="next-checks" />);

    // Click cluster badge
    const clusterABadge = screen.getByRole("button", { name: "cluster-a" });
    clusterABadge.click();

    // Verify callback was called with cluster label
    expect(defaultProps.onFocusClusterForNextChecks).toHaveBeenCalledWith("cluster-a");
  });

  test("calls onReviewNextChecks when button clicked", () => {
    render(<RunSummaryTabs {...defaultProps} activeTab="next-checks" />);

    // Click Review next checks button
    const reviewButton = screen.getByRole("button", { name: /Review next checks/i });
    reviewButton.click();

    // Verify callback was called
    expect(defaultProps.onReviewNextChecks).toHaveBeenCalledTimes(1);
  });

  test("tab buttons are keyboard accessible and respond to clicks", () => {
    render(<RunSummaryTabs {...defaultProps} />);

    // Tab buttons are buttons with click handlers - they are keyboard accessible
    const overviewTab = screen.getByRole("tab", { name: "Overview" });

    // Verify tab is a button element
    expect(overviewTab.tagName).toBe("BUTTON");

    // Verify onClick is wired (clicking triggers tab change)
    overviewTab.click();
    expect(defaultProps.onTabChange).toHaveBeenCalled();
  });

  test("all four tabs render with correct labels", () => {
    render(<RunSummaryTabs {...defaultProps} />);

    expect(screen.getByRole("tab", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Next checks" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Telemetry" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Artifacts" })).toBeInTheDocument();
  });

  // --------------------------------------------------------------------
  // Accessibility tests: ARIA wiring
  // --------------------------------------------------------------------
  test("each tab button has stable id matching its panel", () => {
    render(<RunSummaryTabs {...defaultProps} activeTab="overview" />);

    // Overview tab
    const overviewTab = screen.getByTestId("tab-overview");
    expect(overviewTab).toHaveAttribute("id", "tab-overview");
    expect(overviewTab).toHaveAttribute("aria-controls", "panel-overview");

    // Next checks tab
    const nextChecksTab = screen.getByTestId("tab-next-checks");
    expect(nextChecksTab).toHaveAttribute("id", "tab-next-checks");
    expect(nextChecksTab).toHaveAttribute("aria-controls", "panel-next-checks");

    // Telemetry tab
    const telemetryTab = screen.getByTestId("tab-telemetry");
    expect(telemetryTab).toHaveAttribute("id", "tab-telemetry");
    expect(telemetryTab).toHaveAttribute("aria-controls", "panel-telemetry");

    // Artifacts tab
    const artifactsTab = screen.getByTestId("tab-artifacts");
    expect(artifactsTab).toHaveAttribute("id", "tab-artifacts");
    expect(artifactsTab).toHaveAttribute("aria-controls", "panel-artifacts");
  });

  test("each panel has stable id and aria-labelledby pointing to its tab", () => {
    render(<RunSummaryTabs {...defaultProps} activeTab="overview" />);

    // All panels should have stable IDs
    expect(screen.getByTestId("panel-overview")).toHaveAttribute("id", "panel-overview");
    expect(screen.getByTestId("panel-next-checks")).toHaveAttribute("id", "panel-next-checks");
    expect(screen.getByTestId("panel-telemetry")).toHaveAttribute("id", "panel-telemetry");
    expect(screen.getByTestId("panel-artifacts")).toHaveAttribute("id", "panel-artifacts");

    // All panels should have aria-labelledby pointing to their tab
    expect(screen.getByTestId("panel-overview")).toHaveAttribute("aria-labelledby", "tab-overview");
    expect(screen.getByTestId("panel-next-checks")).toHaveAttribute("aria-labelledby", "tab-next-checks");
    expect(screen.getByTestId("panel-telemetry")).toHaveAttribute("aria-labelledby", "tab-telemetry");
    expect(screen.getByTestId("panel-artifacts")).toHaveAttribute("aria-labelledby", "tab-artifacts");
  });

  test("active tab has aria-controls pointing to active panel", () => {
    const { rerender } = render(<RunSummaryTabs {...defaultProps} activeTab="overview" />);

    // Overview tab active
    const overviewTab = screen.getByTestId("tab-overview");
    expect(overviewTab).toHaveAttribute("aria-controls", "panel-overview");
    expect(overviewTab).toHaveAttribute("aria-selected", "true");

    // Switch to Telemetry
    rerender(<RunSummaryTabs {...defaultProps} activeTab="telemetry" />);

    const telemetryTab = screen.getByTestId("tab-telemetry");
    expect(telemetryTab).toHaveAttribute("aria-controls", "panel-telemetry");
    expect(telemetryTab).toHaveAttribute("aria-selected", "true");

    // Overview tab is now inactive
    expect(screen.getByTestId("tab-overview")).toHaveAttribute("aria-selected", "false");
  });

  test("active panel has aria-labelledby pointing to active tab", () => {
    const { rerender } = render(<RunSummaryTabs {...defaultProps} activeTab="overview" />);

    // Overview panel active
    const overviewPanel = screen.getByTestId("panel-overview");
    expect(overviewPanel).toHaveAttribute("aria-labelledby", "tab-overview");
    expect(overviewPanel).not.toHaveAttribute("hidden");

    // Switch to Next checks
    rerender(<RunSummaryTabs {...defaultProps} activeTab="next-checks" />);

    const nextChecksPanel = screen.getByTestId("panel-next-checks");
    expect(nextChecksPanel).toHaveAttribute("aria-labelledby", "tab-next-checks");
    expect(nextChecksPanel).not.toHaveAttribute("hidden");

    // Overview panel is now hidden
    expect(screen.getByTestId("panel-overview")).toHaveAttribute("hidden");
  });

  test("no duplicate or empty panel IDs are rendered", () => {
    render(<RunSummaryTabs {...defaultProps} activeTab="telemetry" />);

    // Get all panels with role="tabpanel"
    const panels = screen.getAllByRole("tabpanel");

    // All panels should have IDs
    panels.forEach((panel) => {
      expect(panel).toHaveAttribute("id");
      const id = panel.getAttribute("id");
      expect(id).not.toBe("");
      // ID should match pattern panel-{name}
      expect(id).toMatch(/^panel-(overview|next-checks|telemetry|artifacts)$/);
    });

    // All panels should have unique IDs
    const ids = panels.map((p) => p.getAttribute("id"));
    const uniqueIds = new Set(ids);
    expect(uniqueIds.size).toBe(panels.length);
  });

  test("active tab and panel have bidirectional ARIA wiring", () => {
    const { rerender } = render(<RunSummaryTabs {...defaultProps} activeTab="artifacts" />);

    // Active tab (artifacts) points to active panel
    const artifactsTab = screen.getByTestId("tab-artifacts");
    expect(artifactsTab).toHaveAttribute("aria-controls", "panel-artifacts");
    expect(artifactsTab).toHaveAttribute("aria-selected", "true");

    // Active panel (artifacts) points back to active tab
    const artifactsPanel = screen.getByTestId("panel-artifacts");
    expect(artifactsPanel).toHaveAttribute("aria-labelledby", "tab-artifacts");
    expect(artifactsPanel).not.toHaveAttribute("hidden");

    // Switch to Overview tab
    rerender(<RunSummaryTabs {...defaultProps} activeTab="overview" />);

    // Now overview should be active with full wiring
    const overviewTab = screen.getByTestId("tab-overview");
    expect(overviewTab).toHaveAttribute("aria-controls", "panel-overview");
    expect(overviewTab).toHaveAttribute("aria-selected", "true");

    const overviewPanel = screen.getByTestId("panel-overview");
    expect(overviewPanel).toHaveAttribute("aria-labelledby", "tab-overview");
    expect(overviewPanel).not.toHaveAttribute("hidden");
  });
});
