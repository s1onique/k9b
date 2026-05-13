/**
 * status-cue-regression.test.tsx
 *
 * Epic: Operator-first UI surface
 *
 * Regression tests for:
 * - Degraded incident with actionable worklist
 * - Healthy run with honest empty-state behavior
 * - Stale incident warning visibility
 * - Approval-needed item rendering
 * - Deterministic advisory item with null command
 * - Executed/reviewed item rendering
 */

import { render, screen, act, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import type { IncidentReportPayload, OperatorWorklistPayload } from "../types";
import { IncidentReportCard } from "../components/run-summary/IncidentReportCard";
import { OperatorWorklistCard } from "../components/run-summary/OperatorWorklistCard";

// ============================================================================
// Regression: Degraded incident with actionable worklist
// ============================================================================

describe("Regression: Degraded incident with actionable worklist", () => {
  const degradedWithActionableWorklist: IncidentReportPayload = {
    title: "Degraded health detected in 1 cluster(s)",
    status: "degraded",
    affectedScope: "cluster-a",
    impact: null,
    evidenceSummary: null,
    facts: [
      {
        claimType: "observed",
        statement: "Warning events observed: 8",
        sourceArtifactRefs: [{ label: "Drilldown", path: "/artifacts/drilldown-cluster-a.json" }],
        confidence: "high",
      },
      {
        claimType: "observed",
        statement: "Non-running pods observed: 3",
        sourceArtifactRefs: [{ label: "Drilldown", path: "/artifacts/drilldown-cluster-a.json" }],
        confidence: "high",
      },
    ],
    derived: [
      {
        claimType: "derived",
        statement: "Cluster cluster-a health rating is Degraded.",
        sourceFields: ["health_rating"],
        sourceArtifactRefs: [{ label: "Assessment", path: "/artifacts/assessment-cluster-a.json" }],
        confidence: "high",
      },
    ],
    inferences: [],
    recommendations: [
      {
        claimType: "recommendation",
        statement: "Inspect non-running pod status",
        safetyLevel: "low",
        sourceArtifactRefs: [{ label: "Assessment", path: "/artifacts/assessment-cluster-a.json" }],
      },
    ],
    unknowns: [],
    staleEvidenceWarnings: [],
    confidence: "high",
    freshness: { ageSeconds: 1200, expectedIntervalSeconds: 3600, status: "healthy" },
    recommendedActions: [],
    sourceArtifactRefs: [],
  };

  const actionableWorklist: OperatorWorklistPayload = {
    items: [
      {
        id: "queue-item-1",
        rank: 1,
        workstream: "incident",
        title: "Inspect non-running pod status",
        description: "kubectl describe pod",
        command: "kubectl describe pod --all-namespaces --field-selector=status.phase!=Running --context cluster-a",
        targetCluster: "cluster-a",
        targetContext: "prod",
        reason: "Immediate triage for degraded cluster",
        expectedEvidence: "pod status, events",
        safetyNote: "Urgency: high; primary triage: true",
        approvalState: "approved",
        executionState: "unexecuted",
        feedbackState: null,
        sourceArtifactRefs: [],
      },
    ],
    totalItems: 1,
    completedItems: 0,
    pendingItems: 1,
    blockedItems: 0,
  };

  test("Degraded incident status badge renders correctly", () => {
    render(<IncidentReportCard incidentReport={degradedWithActionableWorklist} />);

    const statusBadge = screen.getByTestId("incident-status");
    expect(statusBadge).toBeInTheDocument();
    expect(statusBadge).toHaveClass("incident-status-degraded");
    expect(statusBadge).toHaveTextContent("degraded");
  });

  test("Degraded incident shows facts section with evidence", () => {
    render(<IncidentReportCard incidentReport={degradedWithActionableWorklist} />);

    expect(screen.getByTestId("incident-facts")).toBeInTheDocument();
    expect(screen.getByText(/Warning events observed: 8/)).toBeInTheDocument();
    expect(screen.getByText(/Non-running pods observed: 3/)).toBeInTheDocument();
  });

  test("Degraded incident shows derived conclusions", () => {
    render(<IncidentReportCard incidentReport={degradedWithActionableWorklist} />);

    expect(screen.getByTestId("incident-derived")).toBeInTheDocument();
    expect(screen.getByText(/health rating is Degraded/)).toBeInTheDocument();
  });

  test("Actionable worklist item shows command and state badges", () => {
    render(<OperatorWorklistCard operatorWorklist={actionableWorklist} />);

    // Command should be visible
    expect(screen.getByTestId("command-text-worklist-command-1")).toBeInTheDocument();

    // State badges should be visible
    expect(screen.getByText("approved")).toBeInTheDocument();
    expect(screen.getByText("unexecuted")).toBeInTheDocument();
  });

  test("Actionable worklist item shows target cluster and reason", () => {
    render(<OperatorWorklistCard operatorWorklist={actionableWorklist} />);

    // Use getAllByText since cluster-a appears in command and target
    expect(screen.getAllByText(/cluster-a/).length).toBeGreaterThan(0);
    // Check for the target value span specifically
    expect(screen.getByText("cluster-a · prod")).toBeInTheDocument();
    expect(screen.getByText(/Immediate triage for degraded cluster/)).toBeInTheDocument();
  });
});

// ============================================================================
// Regression: Healthy run with honest empty-state behavior
// ============================================================================

describe("Regression: Healthy run with honest empty-state behavior", () => {
  const healthyEmptyIncidentReport: IncidentReportPayload = {
    title: "All clusters healthy",
    status: "healthy",
    affectedScope: null,
    impact: null,
    evidenceSummary: null,
    facts: [],
    derived: [],
    inferences: [],
    recommendations: [],
    unknowns: [],
    staleEvidenceWarnings: [],
    confidence: "high",
    freshness: { ageSeconds: 600, expectedIntervalSeconds: 3600, status: "healthy" },
    recommendedActions: [],
    sourceArtifactRefs: [],
  };

  const healthyEmptyWorklist: OperatorWorklistPayload = {
    items: [],
    totalItems: 0,
    completedItems: 0,
    pendingItems: 0,
    blockedItems: 0,
  };

  test("Healthy incident report renders empty state honestly", () => {
    render(<IncidentReportCard incidentReport={healthyEmptyIncidentReport} />);

    expect(screen.getByTestId("incident-report-card")).toBeInTheDocument();
    expect(screen.getByText("Incident report")).toBeInTheDocument();
    // Should show "No incident data available." when all sections are empty
    expect(screen.getByText("No incident data available.")).toBeInTheDocument();
  });

  test("Healthy incident report shows healthy status badge", () => {
    render(<IncidentReportCard incidentReport={healthyEmptyIncidentReport} />);

    const statusBadge = screen.getByTestId("incident-status");
    expect(statusBadge).toHaveClass("incident-status-healthy");
    expect(statusBadge).toHaveTextContent("healthy");
  });

  test("Healthy empty worklist renders empty state honestly", () => {
    render(<OperatorWorklistCard operatorWorklist={healthyEmptyWorklist} />);

    expect(screen.getByTestId("operator-worklist-card")).toBeInTheDocument();
    expect(screen.getByText("No operator worklist items are available for this run.")).toBeInTheDocument();
  });

  test("Healthy empty worklist shows empty state instead of summary", () => {
    render(<OperatorWorklistCard operatorWorklist={healthyEmptyWorklist} />);

    // Empty worklist shows the empty state message instead of a summary
    expect(screen.getByText("No operator worklist items are available for this run.")).toBeInTheDocument();
    // No summary should be rendered for empty worklist
    expect(screen.queryByTestId("worklist-summary")).not.toBeInTheDocument();
  });

  test("Dashboard renders both empty cards without errors", async () => {
    const { RunOverviewDashboard } = await import("../components/run-summary/RunOverviewDashboard");

    render(
      <RunOverviewDashboard
        runSummaryStats={[{ label: "Clusters", value: 2 }]}
        runStatsSummary="Last 45s"
        runLlmStatsLine={<span>Calls: 0</span>}
        providerBreakdown={null}
        runPlan={null}
        planStatusText={null}
        planCandidateCountLabel="0"
        discoveryVariantCounts={{ safe: 0, approval: 0, approved: 0, duplicate: 0, stale: 0 }}
        discoveryClusters={[]}
        onFocusClusterForNextChecks={vi.fn()}
        artifacts={[]}
        incidentReport={healthyEmptyIncidentReport}
        operatorWorklist={healthyEmptyWorklist}
        onTabChange={vi.fn()}
      />
    );

    // Both cards should render without errors
    expect(screen.getByTestId("incident-report-card")).toBeInTheDocument();
    expect(screen.getByTestId("operator-worklist-card")).toBeInTheDocument();
  });
});

// ============================================================================
// Regression: Stale incident warning visibility
// ============================================================================

describe("Regression: Stale incident warning visibility", () => {
  const staleIncidentReport: IncidentReportPayload = {
    title: "Degraded health detected in 1 cluster(s)",
    status: "degraded",
    affectedScope: "cluster-a",
    impact: null,
    evidenceSummary: null,
    facts: [
      {
        claimType: "observed",
        statement: "Warning events observed: 5",
        sourceArtifactRefs: [],
        confidence: "medium",
      },
    ],
    derived: [],
    inferences: [],
    recommendations: [],
    unknowns: [],
    staleEvidenceWarnings: [
      "Run freshness is stale; evidence may be outdated.",
      "Last run was 2 hours ago; cluster state may have changed.",
    ],
    confidence: "medium",
    freshness: { ageSeconds: 7200, expectedIntervalSeconds: 1800, status: "stale" },
    recommendedActions: [],
    sourceArtifactRefs: [],
  };

  test("Stale incident shows stale warnings prominently", () => {
    render(<IncidentReportCard incidentReport={staleIncidentReport} />);

    const staleWarnings = screen.getByTestId("incident-stale-warnings");
    expect(staleWarnings).toBeInTheDocument();
  });

  test("Stale incident shows all stale warning messages", () => {
    render(<IncidentReportCard incidentReport={staleIncidentReport} />);

    expect(screen.getByText(/Run freshness is stale; evidence may be outdated/)).toBeInTheDocument();
    expect(screen.getByText(/Last run was 2 hours ago; cluster state may have changed/)).toBeInTheDocument();
  });

  test("Stale incident shows multiple warning icons", () => {
    render(<IncidentReportCard incidentReport={staleIncidentReport} />);

    const warningIcons = document.querySelectorAll(".stale-warning-icon");
    expect(warningIcons.length).toBe(2);
  });

  test("Stale warnings have correct CSS class for visibility", () => {
    render(<IncidentReportCard incidentReport={staleIncidentReport} />);

    const staleWarnings = screen.getByTestId("incident-stale-warnings");
    expect(staleWarnings).toHaveClass("incident-stale-warnings");

    const warnings = document.querySelectorAll(".incident-stale-warning");
    expect(warnings.length).toBe(2);
  });
});

// ============================================================================
// Regression: Approval-needed item rendering
// ============================================================================

describe("Regression: Approval-needed item rendering", () => {
  const approvalNeededWorklist: OperatorWorklistPayload = {
    items: [
      {
        id: "approval-item-1",
        rank: 1,
        workstream: "evidence",
        title: "Collect kubelet logs from node-1",
        description: "kubectl logs command",
        command: "kubectl logs -n kube-system -l k8s-app=kubelet --all-containers --context cluster-a",
        targetCluster: "cluster-a",
        targetContext: "prod",
        reason: "Gather diagnostic evidence for investigation",
        expectedEvidence: "kubelet logs, system events",
        safetyNote: "Urgency: medium; requires approval",
        approvalState: "approval-required",
        executionState: null,
        feedbackState: null,
        sourceArtifactRefs: [],
      },
      {
        id: "approval-item-2",
        rank: 2,
        workstream: "incident",
        title: "Check control plane components",
        description: "kubectl get pods",
        command: "kubectl get pods -n kube-system --context cluster-a",
        targetCluster: "cluster-a",
        targetContext: "prod",
        reason: "Verify control plane health",
        expectedEvidence: "control plane pod status",
        safetyNote: "Urgency: high; primary triage",
        approvalState: "approved",
        executionState: "unexecuted",
        feedbackState: null,
        sourceArtifactRefs: [],
      },
    ],
    totalItems: 2,
    completedItems: 0,
    pendingItems: 2,
    blockedItems: 1,
  };

  test("Approval-needed item shows approval-required state badge", () => {
    render(<OperatorWorklistCard operatorWorklist={approvalNeededWorklist} />);

    expect(screen.getByText("approval-required")).toBeInTheDocument();
  });

  test("Approval-needed item has correct state badge CSS class", () => {
    render(<OperatorWorklistCard operatorWorklist={approvalNeededWorklist} />);

    const approvalBadge = document.querySelector(".worklist-state-approval-required");
    expect(approvalBadge).toBeInTheDocument();
    expect(approvalBadge).toHaveTextContent("approval-required");
  });

  test("Approval-needed item shows blocked count in summary", () => {
    render(<OperatorWorklistCard operatorWorklist={approvalNeededWorklist} />);

    const summary = screen.getByTestId("worklist-summary");
    expect(summary).toHaveTextContent("1 blocked");
  });

  test("Approved item shows approved state badge separately", async () => {
    render(<OperatorWorklistCard operatorWorklist={approvalNeededWorklist} />);

    // Navigate to page 2 to see the approved item
    const nextButton = screen.getByRole("button", { name: /worklist next page/i });
    await act(async () => {
      await userEvent.click(nextButton);
    });

    expect(screen.getByText("approved")).toBeInTheDocument();
  });

  test("Approval-needed item is visually distinct from executable items", () => {
    render(<OperatorWorklistCard operatorWorklist={approvalNeededWorklist} />);

    // Check that approval-required state badge has warning styling
    const approvalBadge = document.querySelector(".worklist-state-approval-required");
    expect(approvalBadge).not.toBeNull();
  });
});

// ============================================================================
// Regression: Deterministic advisory item with null command
// ============================================================================

describe("Regression: Deterministic advisory item with null command", () => {
  const deterministicAdvisoryWorklist: OperatorWorklistPayload = {
    items: [
      {
        id: "deterministic-1",
        rank: 1,
        workstream: "evidence",
        title: "Review pod events for web-frontend namespace",
        description: "Owner: platform; method: kubectl get events",
        command: null, // Deterministic advisory - no executable command
        targetCluster: "cluster-a",
        targetContext: "prod",
        reason: "Collect evidence for pending pods investigation",
        expectedEvidence: "pod events, recent failures",
        safetyNote: "Urgency: medium; primary triage: false",
        approvalState: null,
        executionState: null,
        feedbackState: null,
        sourceArtifactRefs: [
          { label: "Assessment", path: "/artifacts/assessment-cluster-a.json" },
        ],
      },
      {
        id: "deterministic-2",
        rank: 2,
        workstream: "drift",
        title: "Compare Helm release versions across clusters",
        description: "Owner: platform; method: kubectl diff",
        command: null, // Deterministic advisory - no executable command
        targetCluster: null,
        targetContext: null,
        reason: "Detect version drift between clusters",
        expectedEvidence: "Helm release status",
        safetyNote: "Urgency: low; primary triage: false",
        approvalState: null,
        executionState: null,
        feedbackState: null,
        sourceArtifactRefs: [],
      },
    ],
    totalItems: 2,
    completedItems: 0,
    pendingItems: 2,
    blockedItems: 0,
  };

  test("Deterministic advisory item shows 'No executable command yet' honestly", () => {
    render(<OperatorWorklistCard operatorWorklist={deterministicAdvisoryWorklist} />);

    expect(screen.getByTestId("worklist-no-command-1")).toBeInTheDocument();
    expect(screen.getByText("No executable command yet.")).toBeInTheDocument();
  });

  test("Deterministic advisory item does not render empty command block", () => {
    render(<OperatorWorklistCard operatorWorklist={deterministicAdvisoryWorklist} />);

    // Should NOT have command text rendered
    expect(screen.queryByTestId("command-text-worklist-command-1")).not.toBeInTheDocument();
  });

  test("Deterministic advisory item shows title and description", () => {
    render(<OperatorWorklistCard operatorWorklist={deterministicAdvisoryWorklist} />);

    expect(screen.getByText("Review pod events for web-frontend namespace")).toBeInTheDocument();
  });

  test("Deterministic advisory item shows workstream badge", () => {
    render(<OperatorWorklistCard operatorWorklist={deterministicAdvisoryWorklist} />);

    expect(screen.getByText("evidence")).toBeInTheDocument();
  });

  test("Multiple deterministic items with null commands render correctly", async () => {
    render(<OperatorWorklistCard operatorWorklist={deterministicAdvisoryWorklist} />);

    // First item (page 1)
    expect(screen.getByTestId("worklist-no-command-1")).toBeInTheDocument();

    // Navigate to second page
    const nextButton = screen.getByRole("button", { name: /worklist next page/i });
    await act(async () => {
      await userEvent.click(nextButton);
    });

    // Second item (page 2) should also have null command
    expect(screen.getByTestId("worklist-no-command-2")).toBeInTheDocument();
    expect(screen.getByText("No executable command yet.")).toBeInTheDocument();
  });

  test("Deterministic advisory item shows source artifact link when available", () => {
    render(<OperatorWorklistCard operatorWorklist={deterministicAdvisoryWorklist} />);

    const artifactLinks = document.querySelectorAll(".worklist-artifact-link");
    expect(artifactLinks.length).toBeGreaterThan(0);
    expect(screen.getByText("Assessment")).toBeInTheDocument();
  });
});

// ============================================================================
// Regression: Executed/reviewed item rendering
// ============================================================================

describe("Regression: Executed/reviewed item rendering", () => {
  const executedReviewedWorklist: OperatorWorklistPayload = {
    items: [
      {
        id: "executed-item-1",
        rank: 1,
        workstream: "incident",
        title: "Check kubelet status on node-1",
        description: "kubectl top node",
        command: "kubectl top node node-1 --context cluster-a",
        targetCluster: "cluster-a",
        targetContext: "prod",
        reason: "High CPU investigation",
        expectedEvidence: "node CPU/memory metrics",
        safetyNote: "Urgency: high; primary triage",
        approvalState: "not-required",
        executionState: "executed-success",
        feedbackState: "useful",
        sourceArtifactRefs: [
          { label: "Execution", path: "/artifacts/execution-1.json" },
        ],
      },
      {
        id: "executed-item-2",
        rank: 2,
        workstream: "evidence",
        title: "Review pod logs for web-frontend",
        description: "kubectl logs",
        command: "kubectl logs -l app=web-frontend -n default --context cluster-a",
        targetCluster: "cluster-a",
        targetContext: "prod",
        reason: "Error pattern investigation",
        expectedEvidence: "application logs",
        safetyNote: "Urgency: medium; primary triage: false",
        approvalState: "approved",
        executionState: "executed-failed",
        feedbackState: "noisy",
        sourceArtifactRefs: [
          { label: "Execution", path: "/artifacts/execution-2.json" },
        ],
      },
      {
        id: "reviewed-item-3",
        rank: 3,
        workstream: "drift",
        title: "Compare deployment replicas",
        description: "kubectl get deployments",
        command: "kubectl get deployments -A --context cluster-a",
        targetCluster: "cluster-a",
        targetContext: "prod",
        reason: "Replica count drift check",
        expectedEvidence: "replica counts",
        safetyNote: "Urgency: low",
        approvalState: "not-required",
        executionState: "executed-success",
        feedbackState: "partial",
        sourceArtifactRefs: [],
      },
    ],
    totalItems: 3,
    completedItems: 3,
    pendingItems: 0,
    blockedItems: 0,
  };

  test("Executed-success item shows correct execution and feedback states", () => {
    render(<OperatorWorklistCard operatorWorklist={executedReviewedWorklist} />);

    expect(screen.getByText("executed-success")).toBeInTheDocument();
    expect(screen.getByText("useful")).toBeInTheDocument();
  });

  test("Executed-failed item shows failure and feedback states", async () => {
    render(<OperatorWorklistCard operatorWorklist={executedReviewedWorklist} />);

    // Navigate to page 2
    const nextButton = screen.getByRole("button", { name: /worklist next page/i });
    await act(async () => {
      await userEvent.click(nextButton);
    });

    expect(screen.getByText("executed-failed")).toBeInTheDocument();
    expect(screen.getByText("noisy")).toBeInTheDocument();
  });

  test("Partial feedback item shows correct state", async () => {
    render(<OperatorWorklistCard operatorWorklist={executedReviewedWorklist} />);

    // Navigate to page 2 first
    let nextButton = screen.getByRole("button", { name: /worklist next page/i });
    await act(async () => {
      await userEvent.click(nextButton);
    });

    // Now navigate to page 3
    nextButton = screen.getByRole("button", { name: /worklist next page/i });
    await act(async () => {
      await userEvent.click(nextButton);
    });

    // After navigating twice, we should be on page 3
    // Check that item 3 is visible and has the partial feedback state
    expect(screen.getByTestId("worklist-item-3")).toBeInTheDocument();
    expect(screen.getByText("executed-success")).toBeInTheDocument();
    expect(screen.getByText("partial")).toBeInTheDocument();
  });

  test("Executed/reviewed items have correct CSS classes for visual distinction", () => {
    render(<OperatorWorklistCard operatorWorklist={executedReviewedWorklist} />);

    const successBadge = document.querySelector(".worklist-state-executed-success");
    expect(successBadge).toBeInTheDocument();

    const usefulBadge = document.querySelector(".worklist-state-useful");
    expect(usefulBadge).toBeInTheDocument();
  });

  test("Completed summary shows correct count", () => {
    render(<OperatorWorklistCard operatorWorklist={executedReviewedWorklist} />);

    const summary = screen.getByTestId("worklist-summary");
    expect(summary).toHaveTextContent("3 total");
    expect(summary).toHaveTextContent("3 done");
  });

  test("Executed item shows execution artifact link", () => {
    render(<OperatorWorklistCard operatorWorklist={executedReviewedWorklist} />);

    const artifactLinks = document.querySelectorAll(".worklist-artifact-link");
    expect(artifactLinks.length).toBeGreaterThan(0);
  });
});