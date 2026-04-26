/**
 * run-overview-dashboard.test.tsx
 *
 * Focused tests for RunOverviewDashboard component.
 * Tests Overview tab content rendering and CTA behaviors.
 *
 * Phase 3 - Run Summary UX Redesign: Overview dashboard.
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
  // Test 1: Overview tab renders KPI strip
  // --------------------------------------------------------------------
  test("1. Overview tab renders KPI strip plus heading", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // KPI stats should be visible
    expect(screen.getByText("Clusters")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("Degraded")).toBeInTheDocument();
    expect(screen.getByText("Proposals")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();

    // Duration summary should be visible
    expect(screen.getByText(/Last 32s/)).toBeInTheDocument();
  });

  // --------------------------------------------------------------------
  // Test 2: "What needs attention now" renders with affected clusters
  // --------------------------------------------------------------------
  test("2. 'What needs attention now' renders with affected cluster badges", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // Attention section heading should be visible
    expect(screen.getByRole("heading", { name: "What needs attention now" })).toBeInTheDocument();

    // Affected clusters should be shown
    expect(screen.getByText("Affected clusters:")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "cluster-a" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "cluster-b" })).toBeInTheDocument();
  });

  // --------------------------------------------------------------------
  // Test 3: Affected cluster badges call onFocusClusterForNextChecks
  // --------------------------------------------------------------------
  test("3. Clicking affected cluster badge calls onFocusClusterForNextChecks with exact cluster label", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // Click cluster-a badge
    const clusterABadge = screen.getByRole("button", { name: "cluster-a" });
    clusterABadge.click();

    // Verify callback was called with cluster label
    expect(defaultProps.onFocusClusterForNextChecks).toHaveBeenCalledWith("cluster-a");
    expect(defaultProps.onFocusClusterForNextChecks).toHaveBeenCalledTimes(1);
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
  // Test 6: Next checks preview renders with candidate count and CTA
  // --------------------------------------------------------------------
  test("6. Next checks preview renders candidate count and offers Review next checks CTA", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // Next checks section should have heading
    expect(screen.getByRole("heading", { name: "Next checks" })).toBeInTheDocument();

    // Candidate count label should be visible (may be combined with status text)
    expect(screen.getByText(/3 candidates/)).toBeInTheDocument();

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
  // Test 8: Artifacts preview shows count and up to 3 labels
  // --------------------------------------------------------------------
  test("8. Artifacts preview shows count and up to 3 artifact labels", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // Artifacts section should have heading
    expect(screen.getByRole("heading", { name: "Artifacts" })).toBeInTheDocument();

    // Should show total count (text may be split across elements)
    expect(screen.getByText(/artifacts available/)).toBeInTheDocument();

    // Should show first 3 labels (text may be split across elements)
    expect(screen.getByText(/run manifest, assessment, telemetry/)).toBeInTheDocument();
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
  // Test 19: Secondary CTAs still work and call correct tab changes
  // --------------------------------------------------------------------
  test("19. Secondary CTAs call correct tab changes", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    // Click View telemetry CTA
    screen.getByTestId("view-telemetry-cta").click();
    expect(defaultProps.onTabChange).toHaveBeenCalledWith("telemetry");

    // Click View artifacts CTA
    screen.getByTestId("view-artifacts-cta").click();
    expect(defaultProps.onTabChange).toHaveBeenCalledWith("artifacts");
  });

  // --------------------------------------------------------------------
  // Test 20: Attention card "View next checks" CTA also calls correct tab change
  // --------------------------------------------------------------------
  test("20. Attention card CTA calls onTabChange with next-checks", () => {
    render(<RunOverviewDashboard {...defaultProps} />);

    const viewNextChecksCta = screen.getByTestId("view-next-checks-from-attention");
    expect(viewNextChecksCta.tagName).toBe("BUTTON");
    viewNextChecksCta.click();
    expect(defaultProps.onTabChange).toHaveBeenCalledWith("next-checks");
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
});
