/**
 * run-summary-components.test.tsx
 *
 * Focused tests for run-summary extracted components.
 * Tests: RunHeader, RunKpiStrip, LlmTelemetryCard,
 *        NextChecksSummaryCard, PastRunNotice.
 *
 * E1-3b-step15: Behavior-preserving extraction verification.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import dayjs from "dayjs";

// Import components under test
import {
  RunHeader,
  RunKpiStrip,
  LlmTelemetryCard,
  NextChecksSummaryCard,
  PastRunNotice,
} from "../components/run-summary";
import type { NextCheckPlanCandidate, NextCheckStatusVariant } from "../types";

// ============================================================================
// Helper to mock localStorage for tests
// ============================================================================

const createStorageMock = () => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
  };
};

// ============================================================================
// RunHeader tests
// ============================================================================

describe("RunHeader", () => {
  test("1. run id renders in header", () => {
    render(
      <RunHeader
        label="Test Run"
        collectorVersion="collector:v1.2.0"
        timestamp="2026-04-06T12:00:00Z"
      />
    );

    // Run label should be visible
    expect(screen.getByRole("heading", { name: "Test Run" })).toBeInTheDocument();

    // Collector version should be displayed (text is split across elements)
    expect(screen.getByText(/Collector/)).toBeInTheDocument();
    expect(screen.getByText(/collector:v1\.2\.0/)).toBeInTheDocument();
  });

  test("displays timestamp formatted", () => {
    render(
      <RunHeader
        label="Run Label"
        collectorVersion="v1.0"
        timestamp="2026-04-06T12:00:00Z"
      />
    );

    // Should show "Run summary" kicker
    expect(screen.getByText("Run summary")).toBeInTheDocument();
  });

  test("timestamp renders as formatted date", () => {
    render(
      <RunHeader
        label="Test"
        collectorVersion="v1.0"
        timestamp="2026-04-06T12:00:00Z"
      />
    );

    // The timestamp should be formatted as "Apr 6, 2026 12:00 UTC"
    // We can verify the formatted output by checking for the expected format
    expect(screen.getByText(/Apr 6, 2026/)).toBeInTheDocument();
    expect(screen.getByText(/12:00 UTC/)).toBeInTheDocument();
  });

  test("renders as two-row compact header with correct semantic structure", () => {
    render(
      <RunHeader
        label="health-run-20260427T145704Z"
        collectorVersion="0.0.0"
        timestamp="2026-04-27T14:59:00Z"
      />
    );

    // Find the h2 by role and assert its closest header has the correct class
    const title = screen.getByRole("heading", {
      level: 2,
      name: "health-run-20260427T145704Z",
    });
    const header = title.closest("header");
    expect(header).toHaveClass("run-summary-header");

    // Should contain the run summary header row
    const headerRow = header?.querySelector(".run-summary-header-row");
    expect(headerRow).toBeInTheDocument();

    // Should contain the run summary meta group
    const metaGroup = header?.querySelector(".run-summary-meta");
    expect(metaGroup).toBeInTheDocument();

    // Kicker should be in the header row
    expect(screen.getByText("Run summary")).toBeInTheDocument();

    // Collector and timestamp should be in the meta group
    expect(screen.getByText("Collector 0.0.0")).toBeInTheDocument();
    const timeElement = header?.querySelector("time");
    expect(timeElement).toBeInTheDocument();
  });

  test("uses <time> element for timestamp accessibility", () => {
    render(
      <RunHeader
        label="Test Run"
        collectorVersion="v1.0"
        timestamp="2026-04-06T12:00:00Z"
      />
    );

    // Should use <time> element for the timestamp
    const container = document.querySelector(".run-summary-header");
    const timeElement = container?.querySelector("time");
    expect(timeElement).toBeInTheDocument();
    expect(timeElement).toHaveAttribute("dateTime", "2026-04-06T12:00:00Z");
    expect(timeElement).toHaveClass("run-summary-time");
  });

  test("long run ids truncate with ellipsis", () => {
    render(
      <RunHeader
        label="health-run-with-very-long-name-that-should-truncate-gracefully-20260427T145704Z"
        collectorVersion="v1.0"
        timestamp="2026-04-06T12:00:00Z"
      />
    );

    // The title element should have overflow styling for truncation
    const titleElement = screen.getByText("health-run-with-very-long-name-that-should-truncate-gracefully-20260427T145704Z");
    expect(titleElement.tagName).toBe("H2");
    expect(titleElement).toHaveClass("run-summary-title");

    // Verify the title element has the truncation class applied
    // Note: overflow/ellipsis styles are defined in CSS (fleet-summary.css)
    // and cannot be tested via toHaveStyle in jsdom (only inline styles work)
  });

  test("collector and timestamp remain readable on compact layout", () => {
    render(
      <RunHeader
        label="Test Run"
        collectorVersion="collector:v1.2.0"
        timestamp="2026-04-06T12:00:00Z"
      />
    );

    // Collector should have compact styling
    const collector = screen.getByText(/Collector/);
    expect(collector).toHaveClass("run-summary-collector");

    // Timestamp should have compact styling - use DOM query since jsdom doesn't assign "timer" role
    const container = document.querySelector(".run-summary-header");
    const timestamp = container?.querySelector("time");
    expect(timestamp).toBeInTheDocument();
    expect(timestamp).toHaveClass("run-summary-time");
  });
});

// ============================================================================
// RunKpiStrip tests
// ============================================================================

describe("RunKpiStrip", () => {
  test("2. KPI counts render correctly", () => {
    const stats = [
      { label: "Clusters", value: 5 },
      { label: "Degraded", value: 2 },
      { label: "Proposals", value: 10 },
      { label: "Notifications", value: 15 },
      { label: "Drilldowns", value: 3 },
    ];

    render(
      <RunKpiStrip
        stats={stats}
        durationSummary="Last 32s · Runs 12 · P50 24s"
      />
    );

    // All KPI values should render
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("15")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();

    // All KPI labels should render
    expect(screen.getByText("Clusters")).toBeInTheDocument();
    expect(screen.getByText("Degraded")).toBeInTheDocument();
    expect(screen.getByText("Proposals")).toBeInTheDocument();
    expect(screen.getByText("Notifications")).toBeInTheDocument();
    expect(screen.getByText("Drilldowns")).toBeInTheDocument();

    // Duration summary should render
    expect(screen.getByText(/Last 32s/)).toBeInTheDocument();
  });

  test("renders empty stats gracefully", () => {
    render(
      <RunKpiStrip
        stats={[]}
        durationSummary="No stats available"
      />
    );

    // Should render duration summary even with empty stats
    expect(screen.getByText("No stats available")).toBeInTheDocument();
  });
});

// ============================================================================
// LlmTelemetryCard tests
// ============================================================================

describe("LlmTelemetryCard", () => {
  test("3. LLM telemetry values render", () => {
    // Create a simple stats line element
    const statsLine = (
      <span data-testid="llm-stats-line">
        Calls: 3 · OK: 2 · Failed: 1
      </span>
    );

    render(
      <LlmTelemetryCard
        llmStatsLine={statsLine}
        historicalLlmStatsLine={null}
        providerBreakdown="k8sgpt 2 (0 failed)"
      />
    );

    // LLM telemetry section should be visible
    expect(screen.getByText("LLM telemetry")).toBeInTheDocument();

    // Stats line should render
    expect(screen.getByTestId("llm-stats-line")).toBeInTheDocument();
    expect(screen.getByText(/Calls: 3/)).toBeInTheDocument();

    // Provider breakdown should render
    expect(screen.getByText(/Providers: k8sgpt 2 \(0 failed\)/)).toBeInTheDocument();

    // Subtitle should render
    expect(screen.getByText(/Provider call metrics from artifacts/)).toBeInTheDocument();
  });

  test("shows historical stats when provided", () => {
    const currentStatsLine = <span>Current: 3 calls</span>;
    const historicalStatsLine = <span>Historical: 18 calls</span>;

    render(
      <LlmTelemetryCard
        llmStatsLine={currentStatsLine}
        historicalLlmStatsLine={historicalStatsLine}
        providerBreakdown={null}
      />
    );

    // Historical stats should be in a collapsible details element
    expect(screen.getByText("Retained history stats")).toBeInTheDocument();
    expect(screen.getByText(/Historical: 18 calls/)).toBeInTheDocument();
  });

  test("hides historical section when null", () => {
    const statsLine = <span>3 calls</span>;

    render(
      <LlmTelemetryCard
        llmStatsLine={statsLine}
        historicalLlmStatsLine={null}
        providerBreakdown={null}
      />
    );

    // Should NOT show "Retained history stats"
    expect(screen.queryByText(/Retained history stats/i)).not.toBeInTheDocument();
  });
});

// ============================================================================
// NextChecksSummaryCard tests
// ============================================================================

describe("NextChecksSummaryCard", () => {
  const mockOnReviewNextChecks = vi.fn();
  const mockOnFocusClusterForNextChecks = vi.fn();

  beforeEach(() => {
    mockOnReviewNextChecks.mockClear();
    mockOnFocusClusterForNextChecks.mockClear();
  });

  test("4. next checks summary renders planner status and candidate count", () => {
    const plan = {
      summary: "Planner generated multiple advisory checks.",
      artifactPath: "/artifacts/next-check-plan.json",
      status: "planned",
      candidateCount: 3,
    };

    const candidates: NextCheckPlanCandidate[] = [
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

    const variantOrder: NextCheckStatusVariant[] = ["safe", "approval", "approved", "duplicate", "stale"];
    const variantCounts: Record<NextCheckStatusVariant, number> = {
      safe: 1,
      approval: 1,
      approved: 0,
      duplicate: 0,
      stale: 0,
    };

    render(
      <NextChecksSummaryCard
        runPlan={plan}
        runPlanCandidates={candidates}
        planSummaryText="Planner generated multiple advisory checks."
        planStatusText="planned"
        plannerReasonText="Planner data unavailable"
        plannerHint={null}
        plannerNextActionHint="Check the planner artifact"
        plannerArtifactUrl="http://localhost/artifacts/next-check-plan.json"
        planCandidateCountLabel="3 candidates"
        discoveryVariantOrder={variantOrder}
        discoveryVariantCounts={variantCounts}
        discoveryClusters={["cluster-a", "cluster-b"]}
        onReviewNextChecks={mockOnReviewNextChecks}
        onFocusClusterForNextChecks={mockOnFocusClusterForNextChecks}
      />
    );

    // Should show "Next checks" eyebrow
    expect(screen.getByText("Next checks")).toBeInTheDocument();

    // Should show "Planner candidates" heading
    expect(screen.getByRole("heading", { name: "Planner candidates" })).toBeInTheDocument();

    // Should show plan summary
    expect(screen.getByText(/Planner generated multiple advisory checks\./)).toBeInTheDocument();

    // Should show planner status
    expect(screen.getByText(/Planner status: planned/)).toBeInTheDocument();

    // Should show candidate count
    expect(screen.getByText("3 candidates")).toBeInTheDocument();

    // Should show next action hint
    expect(screen.getByText(/Check the planner artifact/)).toBeInTheDocument();

    // Should show artifact link
    expect(screen.getByRole("link", { name: /View planner artifact/i })).toBeInTheDocument();

    // Should show status pills
    expect(screen.getByText("Safe candidate")).toBeInTheDocument();
    expect(screen.getByText("Approval needed")).toBeInTheDocument();

    // Should show cluster badges
    expect(screen.getByText("cluster-a")).toBeInTheDocument();
    expect(screen.getByText("cluster-b")).toBeInTheDocument();

    // Should have "Review next checks" button
    expect(screen.getByRole("button", { name: /Review next checks/i })).toBeInTheDocument();
  });

  test("shows no plan message when plan is null", () => {
    render(
      <NextChecksSummaryCard
        runPlan={null}
        runPlanCandidates={[]}
        planSummaryText=""
        planStatusText={null}
        plannerReasonText="Planner data is not available for this run."
        plannerHint="Enable the planner to generate next checks."
        plannerNextActionHint={null}
        plannerArtifactUrl={null}
        planCandidateCountLabel=""
        discoveryVariantOrder={["safe", "approval", "approved", "duplicate", "stale"]}
        discoveryVariantCounts={{ safe: 0, approval: 0, approved: 0, duplicate: 0, stale: 0 }}
        discoveryClusters={[]}
        onReviewNextChecks={mockOnReviewNextChecks}
        onFocusClusterForNextChecks={mockOnFocusClusterForNextChecks}
      />
    );

    // Should show reason text
    expect(screen.getByText(/Planner data is not available for this run\./)).toBeInTheDocument();

    // Should show hint
    expect(screen.getByText(/Enable the planner to generate next checks\./)).toBeInTheDocument();

    // Should show "no next checks generated" message
    expect(screen.getByText(/No next checks generated for this run\./)).toBeInTheDocument();
  });

  test("calls onReviewNextChecks when button clicked", () => {
    const plan = {
      summary: "Test plan",
      artifactPath: null,
      status: "test",
      candidateCount: 1,
    };

    const candidates: NextCheckPlanCandidate[] = [
      {
        description: "Test candidate",
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
    ];

    render(
      <NextChecksSummaryCard
        runPlan={plan}
        runPlanCandidates={candidates}
        planSummaryText="Test"
        planStatusText={null}
        plannerReasonText=""
        plannerHint={null}
        plannerNextActionHint={null}
        plannerArtifactUrl={null}
        planCandidateCountLabel="1 candidate"
        discoveryVariantOrder={["safe", "approval", "approved", "duplicate", "stale"]}
        discoveryVariantCounts={{ safe: 1, approval: 0, approved: 0, duplicate: 0, stale: 0 }}
        discoveryClusters={["cluster-a"]}
        onReviewNextChecks={mockOnReviewNextChecks}
        onFocusClusterForNextChecks={mockOnFocusClusterForNextChecks}
      />
    );

    // Click the "Review next checks" button
    screen.getByRole("button", { name: /Review next checks/i }).click();

    // Handler should be called
    expect(mockOnReviewNextChecks).toHaveBeenCalledTimes(1);
  });

  test("calls onFocusClusterForNextChecks with exact cluster label when cluster badge clicked", () => {
    const plan = {
      summary: "Test plan",
      artifactPath: null,
      status: "test",
      candidateCount: 2,
    };

    const candidates: NextCheckPlanCandidate[] = [
      {
        description: "Check for cluster-a",
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
        description: "Check for cluster-b",
        targetCluster: "cluster-b",
        sourceReason: null,
        expectedSignal: null,
        suggestedCommandFamily: "kubectl-get",
        safeToAutomate: true,
        requiresOperatorApproval: false,
        riskLevel: "low",
        estimatedCost: "low",
        confidence: "high",
        priorityLabel: null,
        gatingReason: null,
        duplicateOfExistingEvidence: false,
        duplicateEvidenceDescription: null,
        candidateIndex: 1,
      },
    ];

    render(
      <NextChecksSummaryCard
        runPlan={plan}
        runPlanCandidates={candidates}
        planSummaryText="Test"
        planStatusText={null}
        plannerReasonText=""
        plannerHint={null}
        plannerNextActionHint={null}
        plannerArtifactUrl={null}
        planCandidateCountLabel="2 candidates"
        discoveryVariantOrder={["safe", "approval", "approved", "duplicate", "stale"]}
        discoveryVariantCounts={{ safe: 2, approval: 0, approved: 0, duplicate: 0, stale: 0 }}
        discoveryClusters={["cluster-a", "cluster-b"]}
        onReviewNextChecks={mockOnReviewNextChecks}
        onFocusClusterForNextChecks={mockOnFocusClusterForNextChecks}
      />
    );

    // Find and click the cluster-a badge
    const clusterABadge = screen.getByRole("button", { name: "cluster-a" });
    clusterABadge.click();

    // Handler should be called with the exact cluster label
    expect(mockOnFocusClusterForNextChecks).toHaveBeenCalledTimes(1);
    expect(mockOnFocusClusterForNextChecks).toHaveBeenCalledWith("cluster-a");

    // Verify the other cluster badge is also clickable
    mockOnFocusClusterForNextChecks.mockClear();
    const clusterBBadge = screen.getByRole("button", { name: "cluster-b" });
    clusterBBadge.click();

    expect(mockOnFocusClusterForNextChecks).toHaveBeenCalledTimes(1);
    expect(mockOnFocusClusterForNextChecks).toHaveBeenCalledWith("cluster-b");
  });
});

// ============================================================================
// PastRunNotice tests
// ============================================================================

describe("PastRunNotice", () => {
  let storageMock: ReturnType<typeof createStorageMock>;

  beforeEach(() => {
    storageMock = createStorageMock();
    vi.stubGlobal("localStorage", storageMock);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("5. past-run notice renders when selected run is not latest", () => {
    const timestamp = dayjs().subtract(30, "minute").toISOString();

    render(
      <PastRunNotice
        isSelectedRunLatest={false}
        runFresh={true}
        runTimestamp={timestamp}
      />
    );

    // Should show past-run notice
    expect(screen.getByText(/This is a past run collected/)).toBeInTheDocument();
    expect(screen.getByText(/ago\./)).toBeInTheDocument();
  });

  test("shows freshness warning when latest run is stale", () => {
    const timestamp = dayjs().subtract(60, "minute").toISOString();

    render(
      <PastRunNotice
        isSelectedRunLatest={true}
        runFresh={false}
        runTimestamp={timestamp}
      />
    );

    // Should show freshness warning
    expect(screen.getByText(/Latest run is.*minutes old/)).toBeInTheDocument();
    expect(screen.getByText(/ensure the scheduler is running/)).toBeInTheDocument();
  });

  test("renders nothing when latest run is fresh", () => {
    const timestamp = dayjs().subtract(5, "minute").toISOString();

    const { container } = render(
      <PastRunNotice
        isSelectedRunLatest={true}
        runFresh={true}
        runTimestamp={timestamp}
      />
    );

    // Should render nothing (null)
    expect(container.firstChild).toBeNull();
  });

  test("formats age duration correctly", () => {
    // Test with 60 minutes (1 hour)
    const timestamp = dayjs().subtract(60, "minute").toISOString();

    render(
      <PastRunNotice
        isSelectedRunLatest={false}
        runFresh={true}
        runTimestamp={timestamp}
      />
    );

    // Should show "1h" format
    expect(screen.getByText(/1h ago/)).toBeInTheDocument();
  });

  test("handles days format", () => {
    // Test with 2 days
    const timestamp = dayjs().subtract(2, "day").toISOString();

    render(
      <PastRunNotice
        isSelectedRunLatest={false}
        runFresh={true}
        runTimestamp={timestamp}
      />
    );

    // Should show "2d" format
    expect(screen.getByText(/2d ago/)).toBeInTheDocument();
  });
});