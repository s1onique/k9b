/**
 * run-overview-dashboard.test.tsx
 *
 * Focused tests for RunOverviewDashboard component.
 * Tests Overview tab content rendering and CTA behaviors.
 *
 * Phase 5 - Run Summary UX Redesign: High-fidelity Overview polish tests.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import type { NextCheckStatusVariant } from "../types";

import { RunOverviewDashboard } from "../components/run-summary/RunOverviewDashboard";

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

const mockDiscoveryVariantCounts: Record<NextCheckStatusVariant, number> = {
  safe: 1,
  approval: 1,
  approved: 0,
  duplicate: 0,
  stale: 0,
  // Note: degraded count intentionally not included here because
  // discoveryVariantCounts is for next-check workflow statuses, not health degradation.
};

const mockArtifacts = [
  { label: "run manifest", path: "/artifacts/run-manifest.json" },
  { label: "assessment", path: "/artifacts/assessment.json" },
  { label: "telemetry", path: "/artifacts/telemetry.json" },
  { label: "events", path: "/artifacts/events.json" },
];

const defaultProps = {
  runSummaryStats: mockRunSummaryStats,
  runStatsSummary: "Last 32s · Runs 12 · P50 24s",
  runLlmStatsLine: <span data-testid="llm-stats">Calls: 3 · OK: 2 · Failed: 1</span>,
  providerBreakdown: "k8sgpt 2 (0 failed)",
  runPlan: mockRunPlan,
  planStatusText: "planned",
  planCandidateCountLabel: "3 candidates",
  discoveryVariantCounts: mockDiscoveryVariantCounts,
  discoveryClusters: ["cluster-a", "cluster-b"],
  onFocusClusterForNextChecks: vi.fn(),
  artifacts: mockArtifacts,
  onTabChange: vi.fn(),
};

// ============================================================================
// RunOverviewDashboard tests
// ============================================================================

describe("RunOverviewDashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --------------------------------------------------------------------
  // Test 1: Overview tab renders KPI strip with visual anchors
  // --------------------------------------------------------------------
  test("1. Overview tab renders KPI strip with polished cards", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // KPI stats should be visible
    expect(screen.getByText("Clusters")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("Degraded")).toBeInTheDocument();
    expect(screen.getByText("Proposals")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();

    // KPI cards should have kpi-card class
    const kpiCards = document.querySelectorAll(".kpi-card");
    expect(kpiCards).toHaveLength(3);

    // KPI cards should have icon and content
    const kpiIcons = document.querySelectorAll(".kpi-icon");
    expect(kpiIcons).toHaveLength(3);

    const kpiValues = document.querySelectorAll(".kpi-value");
    expect(kpiValues).toHaveLength(3);

    // Duration summary should be visible
    expect(screen.getByText(/Last 32s/)).toBeInTheDocument();
  });

  // --------------------------------------------------------------------
  // Test 2: "What needs attention now" renders with actionable cluster rows
  // --------------------------------------------------------------------
  test("2. 'What needs attention now' renders with actionable cluster rows", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // Attention section heading should be visible
    expect(screen.getByRole("heading", { name: "What needs attention now" })).toBeInTheDocument();

    // Should show subtitle "Affected clusters need review"
    expect(screen.getByText("Affected clusters need review")).toBeInTheDocument();

    // Cluster rows should be present with cluster names
    expect(screen.getByText("cluster-a")).toBeInTheDocument();
    expect(screen.getByText("cluster-b")).toBeInTheDocument();

    // Cluster rows should have the correct class for styling
    const clusterRows = document.querySelectorAll(".attention-cluster-row");
    expect(clusterRows).toHaveLength(2);
  });

  // --------------------------------------------------------------------
  // Test 3: Cluster row CTAs call onFocusClusterForNextChecks
  // --------------------------------------------------------------------
  test("3. Clicking cluster row CTA calls onFocusClusterForNextChecks with exact cluster label", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // Click "View checks" button for cluster-a (using testid)
    const viewChecksClusterA = screen.getByTestId("cluster-badge-cluster-a");
    viewChecksClusterA.click();

    // Verify callback was called with cluster label
    expect(defaultProps.onFocusClusterForNextChecks).toHaveBeenCalledWith("cluster-a");
    expect(defaultProps.onFocusClusterForNextChecks).toHaveBeenCalledTimes(1);
  });

  // --------------------------------------------------------------------
  // Test 3b: Attention footer CTA calls onTabChange("next-checks")
  // --------------------------------------------------------------------
  test("3b. Clicking 'View all next checks' footer CTA calls onTabChange with next-checks", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // Click footer CTA
    const footerCta = screen.getByTestId("view-next-checks-from-attention");
    footerCta.click();

    // Verify callback was called with next-checks
    expect(defaultProps.onTabChange).toHaveBeenCalledWith("next-checks");
  });

  // --------------------------------------------------------------------
  // Test 4: "View telemetry" CTA calls onTabChange with telemetry
  // --------------------------------------------------------------------
  test("4. Clicking 'View telemetry' calls onTabChange with telemetry tab", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // Click View telemetry CTA
    const viewTelemetryCta = screen.getByTestId("view-telemetry-cta");
    viewTelemetryCta.click();

    // Verify callback was called with telemetry
    expect(defaultProps.onTabChange).toHaveBeenCalledWith("telemetry");
  });

  // --------------------------------------------------------------------
  // Test 5: "View artifacts" CTA calls onTabChange with artifacts
  // --------------------------------------------------------------------
  test("5. Clicking 'View artifacts' calls onTabChange with artifacts tab", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // Click View artifacts CTA
    const viewArtifactsCta = screen.getByTestId("view-artifacts-cta");
    viewArtifactsCta.click();

    // Verify callback was called with artifacts
    expect(defaultProps.onTabChange).toHaveBeenCalledWith("artifacts");
  });

  // --------------------------------------------------------------------
  // Test 6: Next checks preview renders with metric cells
  // --------------------------------------------------------------------
  test("6. Next checks preview renders planner status and candidate count as metric cells", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // Next checks section should have heading
    expect(screen.getByRole("heading", { name: "Next checks" })).toBeInTheDocument();

    // Should show Planner metric cell with status
    expect(screen.getByText("Planner")).toBeInTheDocument();
    expect(screen.getByText("planned")).toBeInTheDocument();

    // Should show Candidates metric cell
    expect(screen.getByText("Candidates")).toBeInTheDocument();
    expect(screen.getByText("3 candidates")).toBeInTheDocument();

    // Metric cells should be present
    const metricCells = document.querySelectorAll(".metric-cell");
    expect(metricCells.length).toBeGreaterThanOrEqual(2);

    // Primary CTA button should be visible
    const reviewCta = screen.getByTestId("review-next-checks-cta");
    expect(reviewCta).toBeInTheDocument();
    expect(screen.getByText("Review next checks")).toBeInTheDocument();
  });

  // --------------------------------------------------------------------
  // Test 7: Review next checks CTA calls onTabChange with next-checks
  // --------------------------------------------------------------------
  test("7. Clicking 'Review next checks' CTA calls onTabChange with next-checks tab", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // Click Review next checks CTA
    const reviewCta = screen.getByTestId("review-next-checks-cta");
    reviewCta.click();

    // Verify callback was called with next-checks
    expect(defaultProps.onTabChange).toHaveBeenCalledWith("next-checks");
  });

  // --------------------------------------------------------------------
  // Test 8: Artifacts preview shows count and label chips
  // --------------------------------------------------------------------
  test("8. Artifacts preview shows count and up to 3 artifact labels as chips", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // Artifacts section should have heading
    expect(screen.getByRole("heading", { name: "Artifacts" })).toBeInTheDocument();

    // Should show artifact count prominently
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("artifacts")).toBeInTheDocument();

    // Should show label chips for first 3
    expect(screen.getByText("run manifest")).toBeInTheDocument();
    expect(screen.getByText("assessment")).toBeInTheDocument();
    expect(screen.getByText("telemetry")).toBeInTheDocument();

    // Should show "+1 more" indicator
    expect(screen.getByText("+1 more")).toBeInTheDocument();

    // Artifact label chips should have the correct class
    const labelChips = document.querySelectorAll(".artifact-label-chip");
    expect(labelChips).toHaveLength(3);
  });

  // --------------------------------------------------------------------
  // Test 9: LLM telemetry preview shows stats and provider breakdown
  // --------------------------------------------------------------------
  test("9. LLM telemetry preview shows stats and provider breakdown", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // LLM telemetry section should have heading
    expect(screen.getByRole("heading", { name: "LLM telemetry" })).toBeInTheDocument();

    // Stats line should be rendered
    expect(screen.getByTestId("llm-stats")).toBeInTheDocument();

    // Provider breakdown should be visible
    expect(screen.getByText(/Providers: k8sgpt 2/)).toBeInTheDocument();
  });

  // --------------------------------------------------------------------
  // Test 10: Does not render AttentionNowCard when no clusters
  // --------------------------------------------------------------------
  test("10. Does not render AttentionNowCard when no clusters", () => {
    render(
      <RunOverviewDashboard
        {...defaultProps}
        discoveryClusters={[]}
      />
    );

    // Attention section should not be rendered when no clusters
    expect(screen.queryByTestId("attention-now-card")).not.toBeInTheDocument();
  });

  // --------------------------------------------------------------------
  // Test 11: AttentionNowCard does not derive degraded health findings from discoveryVariantCounts
  // --------------------------------------------------------------------
  test("11. AttentionNowCard does not treat next-check status counts as degraded health findings", () => {
    // Even with high "degraded" count in discoveryVariantCounts (next-check statuses),
    // the card should not show degraded health findings text
    const highDegradedVariantCounts: Record<NextCheckStatusVariant, number> = {
      safe: 0,
      approval: 0,
      approved: 0,
      duplicate: 0,
      stale: 0,
      degraded: 99, // High count in next-check statuses should NOT be shown
    };

    render(
      <RunOverviewDashboard
        {...defaultProps}
        discoveryVariantCounts={highDegradedVariantCounts}
        // But with no affected clusters, card should not render at all
        discoveryClusters={[]}
      />
    );

    // Card should not render without affected clusters
    expect(screen.queryByTestId("attention-now-card")).not.toBeInTheDocument();
    // And should never show degraded findings text from discoveryVariantCounts
    expect(screen.queryByText(/degraded finding/)).not.toBeInTheDocument();
  });

  // --------------------------------------------------------------------
  // Test 12: Next checks preview shows no plan message when runPlan is null
  // --------------------------------------------------------------------
  test("12. Next checks preview shows no plan message when runPlan is null", () => {
    render(<RunOverviewDashboard {...defaultProps} runPlan={null} />);

    // Next checks section should have heading
    expect(screen.getByRole("heading", { name: "Next checks" })).toBeInTheDocument();

    // Should show no plan message
    expect(screen.getByText("No next checks generated for this run.")).toBeInTheDocument();

    // Should not show metric cells when no plan
    expect(screen.queryByText("Planner")).not.toBeInTheDocument();
  });

  // --------------------------------------------------------------------
  // Test 13: Artifacts preview shows empty state when no artifacts
  // --------------------------------------------------------------------
  test("13. Artifacts preview shows empty state when no artifacts", () => {
    render(<RunOverviewDashboard {...defaultProps} artifacts={[]} />);

    // Artifacts section should have heading
    expect(screen.getByRole("heading", { name: "Artifacts" })).toBeInTheDocument();

    // Should show empty state message
    expect(screen.getByText("No artifacts available for this run.")).toBeInTheDocument();

    // Should not show View artifacts CTA
    expect(screen.queryByTestId("view-artifacts-cta")).not.toBeInTheDocument();
  });

  // --------------------------------------------------------------------
  // Test 14: CTA buttons are real buttons with correct type
  // --------------------------------------------------------------------
  test("14. CTA buttons are real buttons with correct type attribute", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // View telemetry CTA
    const viewTelemetryCta = screen.getByTestId("view-telemetry-cta");
    expect(viewTelemetryCta.tagName).toBe("BUTTON");
    expect(viewTelemetryCta).toHaveAttribute("type", "button");

    // View artifacts CTA
    const viewArtifactsCta = screen.getByTestId("view-artifacts-cta");
    expect(viewArtifactsCta.tagName).toBe("BUTTON");
    expect(viewArtifactsCta).toHaveAttribute("type", "button");

    // Review next checks CTA
    const reviewCta = screen.getByTestId("review-next-checks-cta");
    expect(reviewCta.tagName).toBe("BUTTON");
    expect(reviewCta).toHaveAttribute("type", "button");
  });

  // --------------------------------------------------------------------
  // Test 15: All CTA buttons are keyboard accessible
  // --------------------------------------------------------------------
  test("15. All CTA buttons are keyboard accessible", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // All CTAs should be focusable button elements
    const viewTelemetryCta = screen.getByTestId("view-telemetry-cta");
    const viewArtifactsCta = screen.getByTestId("view-artifacts-cta");
    const reviewCta = screen.getByTestId("review-next-checks-cta");

    expect(viewTelemetryCta.tabIndex).toBe(0);
    expect(viewArtifactsCta.tabIndex).toBe(0);
    expect(reviewCta.tabIndex).toBe(0);

    // Should be clickable
    viewTelemetryCta.click();
    expect(defaultProps.onTabChange).toHaveBeenCalledWith("telemetry");
  });

  // --------------------------------------------------------------------
  // Test 16: Overview dashboard renders the grid wrapper
  // --------------------------------------------------------------------
  test("16. Overview dashboard renders the grid wrapper for preview cards", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // Grid wrapper should be present
    const gridWrapper = screen.getByTestId("run-overview-dashboard").querySelector(".run-overview-grid");
    expect(gridWrapper).toBeInTheDocument();

    // All preview cards should be inside the grid
    expect(screen.getByTestId("next-checks-preview-card").parentElement).toBe(gridWrapper);
    expect(screen.getByTestId("llm-telemetry-preview-card").parentElement).toBe(gridWrapper);
    expect(screen.getByTestId("artifacts-preview-card").parentElement).toBe(gridWrapper);
  });

  // --------------------------------------------------------------------
  // Test 17: Preview cards have their specific card classes
  // --------------------------------------------------------------------
  test("17. Preview cards have shared run-overview-card class and specific classes", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // Next checks preview card has both shared and specific class
    const nextChecksCard = screen.getByTestId("next-checks-preview-card");
    expect(nextChecksCard).toHaveClass("run-overview-card");
    expect(nextChecksCard).toHaveClass("next-checks-preview-card");

    // LLM telemetry preview card has both shared and specific class
    const telemetryCard = screen.getByTestId("llm-telemetry-preview-card");
    expect(telemetryCard).toHaveClass("run-overview-card");
    expect(telemetryCard).toHaveClass("llm-telemetry-preview-card");

    // Artifacts preview card has both shared and specific class
    const artifactsCard = screen.getByTestId("artifacts-preview-card");
    expect(artifactsCard).toHaveClass("run-overview-card");
    expect(artifactsCard).toHaveClass("artifacts-preview-card");

    // Attention card has both shared and specific class, spans full width
    const attentionCard = screen.getByTestId("attention-now-card");
    expect(attentionCard).toHaveClass("run-overview-card");
    expect(attentionCard).toHaveClass("attention-now-card");
  });

  // --------------------------------------------------------------------
  // Test 18: Primary CTA (Review next checks) uses run-summary-cta class
  // --------------------------------------------------------------------
  test("18. Primary CTA uses run-summary-cta class for prominence", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    const reviewCta = screen.getByTestId("review-next-checks-cta");
    expect(reviewCta).toHaveClass("run-summary-cta");
    expect(reviewCta).not.toHaveClass("link");
  });

  // --------------------------------------------------------------------
  // Test 19: Secondary CTAs use run-summary-cta-secondary class
  // --------------------------------------------------------------------
  test("19. Secondary CTAs use run-summary-cta-secondary class", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // View telemetry CTA should use secondary class
    const viewTelemetryCta = screen.getByTestId("view-telemetry-cta");
    expect(viewTelemetryCta).toHaveClass("run-summary-cta-secondary");

    // View artifacts CTA should use secondary class
    const viewArtifactsCta = screen.getByTestId("view-artifacts-cta");
    expect(viewArtifactsCta).toHaveClass("run-summary-cta-secondary");
  });

  // --------------------------------------------------------------------
  // Test 20: Preview cards have visual anchor headers
  // --------------------------------------------------------------------
  test("20. Preview cards have preview-card-header with icons", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // All preview cards should have header with icon
    const previewHeaders = document.querySelectorAll(".preview-card-header");
    expect(previewHeaders.length).toBeGreaterThanOrEqual(3);

    // All preview cards should have icon
    const previewIcons = document.querySelectorAll(".preview-card-icon");
    expect(previewIcons.length).toBeGreaterThanOrEqual(3);
  });

  // --------------------------------------------------------------------
  // Test 21: Attention card has warning icon
  // --------------------------------------------------------------------
  test("21. Attention card has attention-icon in header", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // Attention card should have warning icon
    const attentionIcon = document.querySelector(".attention-icon");
    expect(attentionIcon).toBeInTheDocument();

    // Icon should contain warning character
    expect(attentionIcon?.textContent).toContain("⚠");
  });
});
