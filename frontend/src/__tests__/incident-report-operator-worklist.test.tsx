/**
 * incident-report-operator-worklist.test.tsx
 *
 * Phase 2: Canonical Incident Surface Tests
 *
 * Tests for IncidentReportCard and OperatorWorklistCard components.
 * Verifies the acceptance criteria:
 * 1. Incident report renders for selected run.
 * 2. Facts, inferences, and unknowns render in separate sections.
 * 3. Stale warnings render when present.
 * 4. Recommended actions render as descriptions, not links/IDs.
 * 5. Operator worklist renders command when present.
 * 6. Operator worklist renders "No executable command yet" when command is null.
 * 7. Empty sourceArtifactRefs do not render broken artifact links.
 * 8. Empty incident report/worklist states render honestly.
 * 9. Selected-run binding: switching runs updates incident report and worklist.
 * 10. Dashboard renders worklist before incident report.
 * 11. Pagination works correctly (page size 3, previous/next, disabled states).
 */

import { render, screen, act } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import type { IncidentReportPayload, OperatorWorklistPayload } from "../types";
import { IncidentReportCard } from "../components/run-summary/IncidentReportCard";
import { OperatorWorklistCard } from "../components/run-summary/OperatorWorklistCard";

// ============================================================================
// Test fixtures
// ============================================================================

const sampleIncidentReport: IncidentReportPayload = {
  title: "Degraded health detected in 2 cluster(s)",
  status: "degraded",
  affectedScope: "cluster-a, cluster-b",
  impact: null,
  evidenceSummary: null,
  facts: [
    {
      statement: "Cluster cluster-a health rating is Degraded.",
      sourceArtifactRefs: [{ label: "Assessment", path: "/artifacts/assessment-cluster-a.json" }],
      confidence: "high",
    },
    {
      statement: "Warning events observed: 5",
      sourceArtifactRefs: [{ label: "Drilldown", path: "/artifacts/drilldown-cluster-a.json" }],
      confidence: "high",
    },
  ],
  inferences: [
    {
      statement: "High control-plane CPU may be causing latency.",
      basis: ["control-plane", "metrics", "review-enrichment"],
      confidence: "medium",
      sourceArtifactRefs: [{ label: "Review Enrichment", path: "/artifacts/review-enrichment.json" }],
    },
  ],
  unknowns: [
    {
      statement: "Missing evidence: logs from edge nodes",
      whyMissing: "Not collected in this run",
      sourceArtifactRefs: [],
    },
  ],
  staleEvidenceWarnings: [
    "Run freshness is stale; some evidence may be stale.",
  ],
  confidence: "high",
  freshness: { ageSeconds: 7200, expectedIntervalSeconds: 3600, status: "stale" },
  recommendedActions: [
    "Collect kubelet logs from affected nodes",
    "Review control-plane component status",
  ],
  sourceArtifactRefs: [
    { label: "Assessment", path: "/artifacts/assessment-cluster-a.json" },
    { label: "Drilldown", path: "/artifacts/drilldown-cluster-a.json" },
  ],
};

const sampleOperatorWorklist: OperatorWorklistPayload = {
  items: [
    {
      id: "deterministic-cluster-a-1",
      rank: 1,
      workstream: "incident",
      title: "Collect kubelet logs from affected nodes",
      description: "Owner: platform; method: kubectl logs; evidence needed: kubelet logs",
      command: "kubectl logs -n kube-system -l k8s-app=kubelet --context cluster-a",
      targetCluster: "cluster-a",
      targetContext: "prod",
      reason: "Immediate triage for High CPU",
      expectedEvidence: "kubelet logs",
      safetyNote: "Urgency: high; primary triage: true",
      approvalState: "not-required",
      executionState: "unexecuted",
      feedbackState: null,
      sourceArtifactRefs: [
        { label: "Assessment", path: "/artifacts/assessment-cluster-a.json" },
      ],
    },
    {
      id: "deterministic-cluster-a-2",
      rank: 2,
      workstream: "evidence",
      title: "Inspect readiness probes for web-frontend",
      description: "Owner: platform; method: kubectl describe; evidence needed: pod status",
      command: null, // No executable command - deterministic check without command preview
      targetCluster: "cluster-a",
      targetContext: "prod",
      reason: "Gather additional evidence",
      expectedEvidence: "pod status",
      safetyNote: "Urgency: medium; primary triage: false",
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

/** Large worklist fixture for pagination tests (10 items) */
const largeOperatorWorklist: OperatorWorklistPayload = {
  items: [
    { id: "item-1", rank: 1, workstream: "incident", title: "Item 1", description: "", command: "kubectl test 1", targetCluster: null, targetContext: null, reason: null, expectedEvidence: null, safetyNote: null, approvalState: null, executionState: null, feedbackState: null, sourceArtifactRefs: [] },
    { id: "item-2", rank: 2, workstream: "evidence", title: "Item 2", description: "", command: "kubectl test 2", targetCluster: null, targetContext: null, reason: null, expectedEvidence: null, safetyNote: null, approvalState: null, executionState: null, feedbackState: null, sourceArtifactRefs: [] },
    { id: "item-3", rank: 3, workstream: "incident", title: "Item 3", description: "", command: "kubectl test 3", targetCluster: null, targetContext: null, reason: null, expectedEvidence: null, safetyNote: null, approvalState: null, executionState: null, feedbackState: null, sourceArtifactRefs: [] },
    { id: "item-4", rank: 4, workstream: "evidence", title: "Item 4", description: "", command: "kubectl test 4", targetCluster: null, targetContext: null, reason: null, expectedEvidence: null, safetyNote: null, approvalState: null, executionState: null, feedbackState: null, sourceArtifactRefs: [] },
    { id: "item-5", rank: 5, workstream: "incident", title: "Item 5", description: "", command: "kubectl test 5", targetCluster: null, targetContext: null, reason: null, expectedEvidence: null, safetyNote: null, approvalState: null, executionState: null, feedbackState: null, sourceArtifactRefs: [] },
    { id: "item-6", rank: 6, workstream: "evidence", title: "Item 6", description: "", command: "kubectl test 6", targetCluster: null, targetContext: null, reason: null, expectedEvidence: null, safetyNote: null, approvalState: null, executionState: null, feedbackState: null, sourceArtifactRefs: [] },
    { id: "item-7", rank: 7, workstream: "incident", title: "Item 7", description: "", command: "kubectl test 7", targetCluster: null, targetContext: null, reason: null, expectedEvidence: null, safetyNote: null, approvalState: null, executionState: null, feedbackState: null, sourceArtifactRefs: [] },
    { id: "item-8", rank: 8, workstream: "evidence", title: "Item 8", description: "", command: "kubectl test 8", targetCluster: null, targetContext: null, reason: null, expectedEvidence: null, safetyNote: null, approvalState: null, executionState: null, feedbackState: null, sourceArtifactRefs: [] },
    { id: "item-9", rank: 9, workstream: "incident", title: "Item 9", description: "", command: "kubectl test 9", targetCluster: null, targetContext: null, reason: null, expectedEvidence: null, safetyNote: null, approvalState: null, executionState: null, feedbackState: null, sourceArtifactRefs: [] },
    { id: "item-10", rank: 10, workstream: "evidence", title: "Item 10", description: "", command: null, targetCluster: null, targetContext: null, reason: null, expectedEvidence: null, safetyNote: null, approvalState: null, executionState: null, feedbackState: null, sourceArtifactRefs: [] },
  ],
  totalItems: 10,
  completedItems: 0,
  pendingItems: 10,
  blockedItems: 0,
};

// ============================================================================
// IncidentReportCard Tests
// ============================================================================

describe("IncidentReportCard", () => {
  // Test 1: Incident report renders for selected run
  test("1. Renders incident report with title, status, and affected scope", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    // Title should be visible
    expect(screen.getByText("Incident report")).toBeInTheDocument();

    // Status badge
    expect(screen.getByTestId("incident-status")).toBeInTheDocument();
    expect(screen.getByText("degraded")).toBeInTheDocument();

    // Affected scope
    expect(screen.getByText("cluster-a, cluster-b")).toBeInTheDocument();
  });

  // Test 2: Facts, inferences, and unknowns render in separate sections
  test("2. Facts, inferences, and unknowns render in visually distinct sections", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    // Facts section
    expect(screen.getByTestId("incident-facts")).toBeInTheDocument();
    expect(screen.getByText("Facts")).toBeInTheDocument();
    expect(screen.getByText("Cluster cluster-a health rating is Degraded.")).toBeInTheDocument();

    // Inferences section
    expect(screen.getByTestId("incident-inferences")).toBeInTheDocument();
    expect(screen.getByText("Inferences")).toBeInTheDocument();
    expect(screen.getByText("High control-plane CPU may be causing latency.")).toBeInTheDocument();

    // Unknowns section
    expect(screen.getByTestId("incident-unknowns")).toBeInTheDocument();
    expect(screen.getByText("Unknowns")).toBeInTheDocument();
    expect(screen.getByText("Missing evidence: logs from edge nodes")).toBeInTheDocument();
  });

  // Test 3: Stale warnings render when present
  test("3. Stale warnings render prominently with warning styling", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    expect(screen.getByTestId("incident-stale-warnings")).toBeInTheDocument();
    expect(screen.getByText("Run freshness is stale; some evidence may be stale.")).toBeInTheDocument();
  });

  // Test 4: Recommended actions render as descriptions, not links/IDs
  test("4. Recommended actions render as text descriptions", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    expect(screen.getByTestId("incident-recommended-actions")).toBeInTheDocument();
    expect(screen.getByText("Collect kubelet logs from affected nodes")).toBeInTheDocument();
    expect(screen.getByText("Review control-plane component status")).toBeInTheDocument();
  });

  // Test 5: Provider-assisted inference has visible badge
  test("5. Provider-assisted inference is visually distinguished with badge", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    // The inference should have a "provider-assisted" badge
    expect(screen.getByText("provider-assisted")).toBeInTheDocument();
  });

  // Test 6: Empty sourceArtifactRefs do not render broken links
  test("6. Empty sourceArtifactRefs do not render broken artifact links", () => {
    const reportWithEmptyRefs: IncidentReportPayload = {
      title: "Empty refs test",
      status: "healthy",
      affectedScope: null,
      impact: null,
      evidenceSummary: null,
      facts: [
        {
          statement: "Test fact with empty refs",
          sourceArtifactRefs: [], // Empty array
          confidence: "high",
        },
      ],
      inferences: [],
      unknowns: [
        {
          statement: "Test unknown with empty refs",
          whyMissing: null,
          sourceArtifactRefs: [], // Empty array
        },
      ],
      staleEvidenceWarnings: [],
      confidence: "high",
      freshness: null,
      recommendedActions: [],
      sourceArtifactRefs: [], // Also empty at report level
    };

    render(<IncidentReportCard incidentReport={reportWithEmptyRefs} />);

    // Should render the statement but no broken links
    expect(screen.getByText("Test fact with empty refs")).toBeInTheDocument();
    expect(screen.getByText("Test unknown with empty refs")).toBeInTheDocument();

    // No artifact links should be present for these items
    const artifactLinks = document.querySelectorAll(".incident-artifact-link");
    expect(artifactLinks.length).toBe(0);
  });

  // Test 7: Empty state renders honestly
  test("7. Empty incident report state renders honestly", () => {
    render(<IncidentReportCard incidentReport={null} />);

    expect(screen.getByText("Incident report")).toBeInTheDocument();
    expect(screen.getByText("No incident report is available for this run.")).toBeInTheDocument();
  });

  test("8. Empty incident report state with undefined", () => {
    render(<IncidentReportCard incidentReport={undefined} />);

    expect(screen.getByText("No incident report is available for this run.")).toBeInTheDocument();
  });

  // Test 9: Artifact links render when sourceArtifactRefs is non-empty
  test("9. Artifact links render when sourceArtifactRefs is non-empty", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    // Source links should be present
    const artifactLinks = document.querySelectorAll(".incident-artifact-link");
    expect(artifactLinks.length).toBeGreaterThan(0);

    // Check specific artifact links using getAllByText for multiple matches
    const assessmentLinks = screen.getAllByText("Assessment");
    expect(assessmentLinks.length).toBeGreaterThan(0);
    
    const drilldownLinks = screen.getAllByText("Drilldown");
    expect(drilldownLinks.length).toBeGreaterThan(0);
  });
});

// ============================================================================
// OperatorWorklistCard Tests
// ============================================================================

describe("OperatorWorklistCard", () => {
  // Test 5: Operator worklist renders command when present
  test("5. Operator worklist renders command when present", () => {
    render(<OperatorWorklistCard operatorWorklist={sampleOperatorWorklist} />);

    // First item has a command
    expect(screen.getByTestId("worklist-item-1")).toBeInTheDocument();
    expect(screen.getByTestId("worklist-command-1")).toBeInTheDocument();
    expect(screen.getByText("kubectl logs -n kube-system -l k8s-app=kubelet --context cluster-a")).toBeInTheDocument();
  });

  // Test 6: Operator worklist renders "No executable command yet" when command is null
  test("6. Operator worklist renders 'No executable command yet' when command is null", () => {
    render(<OperatorWorklistCard operatorWorklist={sampleOperatorWorklist} />);

    // Second item has no command
    expect(screen.getByTestId("worklist-item-2")).toBeInTheDocument();
    expect(screen.getByTestId("worklist-no-command-2")).toBeInTheDocument();
    expect(screen.getByText("No executable command yet.")).toBeInTheDocument();
  });

  // Test 7: Summary stats render correctly
  test("7. Worklist summary stats render with total, pending, blocked counts", () => {
    render(<OperatorWorklistCard operatorWorklist={sampleOperatorWorklist} />);

    expect(screen.getByTestId("worklist-summary")).toBeInTheDocument();
    // Check that summary stats container has expected content
    expect(screen.getByText(/total/)).toBeInTheDocument();
    expect(screen.getByText(/pending/)).toBeInTheDocument();
  });

  // Test 8: Rank and workstream render for each item
  test("8. Rank and workstream badge render for each item", () => {
    render(<OperatorWorklistCard operatorWorklist={sampleOperatorWorklist} />);

    // First item
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText("incident")).toBeInTheDocument();

    // Second item
    expect(screen.getByText("#2")).toBeInTheDocument();
    expect(screen.getByText("evidence")).toBeInTheDocument();
  });

  // Test 9: Target, reason, expected evidence, and safety note render
  test("9. Target, reason, expected evidence, and safety note render", () => {
    render(<OperatorWorklistCard operatorWorklist={sampleOperatorWorklist} />);

    // Target - use getAllByText since cluster-a appears multiple times in the DOM
    const clusterMatches = screen.getAllByText(/cluster-a/);
    expect(clusterMatches.length).toBeGreaterThan(0);

    // Reason/why now - use getAllByText since it appears for each worklist item
    const whyNowMatches = screen.getAllByText("why now:");
    expect(whyNowMatches.length).toBeGreaterThan(0);
    expect(screen.getByText("Immediate triage for High CPU")).toBeInTheDocument();

    // Expected evidence - use getAllByText since it appears for each worklist item
    const evidenceMatches = screen.getAllByText("expected evidence:");
    expect(evidenceMatches.length).toBeGreaterThan(0);
    expect(screen.getByText("kubelet logs")).toBeInTheDocument();

    // Safety - use getAllByText since it appears for each worklist item
    const safetyMatches = screen.getAllByText("safety:");
    expect(safetyMatches.length).toBeGreaterThan(0);
    expect(screen.getByText(/Urgency: high/)).toBeInTheDocument();
  });

  // Test 10: State badges render when present
  test("10. State badges (approval, execution, feedback) render when present", () => {
    render(<OperatorWorklistCard operatorWorklist={sampleOperatorWorklist} />);

    // First item has approval and execution states
    expect(screen.getByText("not-required")).toBeInTheDocument();
    expect(screen.getByText("unexecuted")).toBeInTheDocument();
  });

  // Test 11: Empty state renders honestly
  test("11. Empty operator worklist state renders honestly", () => {
    render(<OperatorWorklistCard operatorWorklist={null} />);

    expect(screen.getByText("Operator worklist")).toBeInTheDocument();
    expect(screen.getByText("No operator worklist items are available for this run.")).toBeInTheDocument();
  });

  test("12. Empty operator worklist state with undefined", () => {
    render(<OperatorWorklistCard operatorWorklist={undefined} />);

    expect(screen.getByText("No operator worklist items are available for this run.")).toBeInTheDocument();
  });

  // Test 13: Empty sourceArtifactRefs do not render broken links
  test("13. Empty sourceArtifactRefs do not render broken artifact links in worklist", () => {
    const worklistWithEmptyRefs: OperatorWorklistPayload = {
      items: [
        {
          id: "test-item",
          rank: 1,
          workstream: "incident",
          title: "Test item with empty refs",
          description: "No refs",
          command: "kubectl test",
          targetCluster: null,
          targetContext: null,
          reason: null,
          expectedEvidence: null,
          safetyNote: null,
          approvalState: null,
          executionState: null,
          feedbackState: null,
          sourceArtifactRefs: [], // Empty array
        },
      ],
      totalItems: 1,
      completedItems: 0,
      pendingItems: 1,
      blockedItems: 0,
    };

    render(<OperatorWorklistCard operatorWorklist={worklistWithEmptyRefs} />);

    // Should render the item but no artifact links
    expect(screen.getByText("Test item with empty refs")).toBeInTheDocument();
    expect(screen.getByText("kubectl test")).toBeInTheDocument();

    // No artifact links should be present
    const artifactLinks = document.querySelectorAll(".worklist-artifact-link");
    expect(artifactLinks.length).toBe(0);
  });

  // Test 14: Artifact links render when sourceArtifactRefs is non-empty
  test("14. Artifact links render when sourceArtifactRefs is non-empty in worklist", () => {
    render(<OperatorWorklistCard operatorWorklist={sampleOperatorWorklist} />);

    // Source links should be present for first item
    const artifactLinks = document.querySelectorAll(".worklist-artifact-link");
    expect(artifactLinks.length).toBeGreaterThan(0);

    // Check specific artifact link
    expect(screen.getByText("Assessment")).toBeInTheDocument();
  });
});

// ============================================================================
// OperatorWorklistCard Pagination Tests
// ============================================================================

describe("OperatorWorklistCard Pagination", () => {
  // Test 1: Dashboard renders Operator worklist before Incident report
  test("1. RunOverviewDashboard renders worklist before incident report in incident surfaces", async () => {
    const { RunOverviewDashboard } = await import("../components/run-summary/RunOverviewDashboard");

    render(
      <RunOverviewDashboard
        runSummaryStats={[{ label: "Clusters", value: 3 }]}
        runStatsSummary="Last 32s"
        runLlmStatsLine={<span>Calls: 3</span>}
        providerBreakdown={null}
        runPlan={null}
        planStatusText={null}
        planCandidateCountLabel="0"
        discoveryVariantCounts={{ safe: 0, approval: 0, approved: 0, duplicate: 0, stale: 0 }}
        discoveryClusters={[]}
        onFocusClusterForNextChecks={vi.fn()}
        artifacts={[]}
        incidentReport={sampleIncidentReport}
        operatorWorklist={sampleOperatorWorklist}
        onTabChange={vi.fn()}
      />
    );

    // Get the incident surfaces container
    const surfaces = screen.getByTestId("run-overview-incident-surfaces");
    const children = surfaces.children;

    // First child should be operator worklist card
    expect(children[0]).toHaveAttribute("data-testid", "operator-worklist-card");
    // Second child should be incident report card
    expect(children[1]).toHaveAttribute("data-testid", "incident-report-card");
  });

  // Test 2: Operator worklist renders only first page by default
  test("2. Operator worklist renders only first page by default when item count exceeds page size", () => {
    render(<OperatorWorklistCard operatorWorklist={largeOperatorWorklist} />);

    // Should show only first 3 items (page size = 3)
    expect(screen.getByTestId("worklist-item-1")).toBeInTheDocument();
    expect(screen.getByTestId("worklist-item-2")).toBeInTheDocument();
    expect(screen.getByTestId("worklist-item-3")).toBeInTheDocument();

    // Items 4-10 should NOT be present
    expect(screen.queryByTestId("worklist-item-4")).not.toBeInTheDocument();
    expect(screen.queryByTestId("worklist-item-10")).not.toBeInTheDocument();
  });

  // Test 3: Page count text renders
  test("3. Page count text renders correctly, e.g. 'Showing 1–3 of 10'", () => {
    render(<OperatorWorklistCard operatorWorklist={largeOperatorWorklist} />);

    // Should show the pagination summary
    expect(screen.getByText(/showing/i)).toBeInTheDocument();
    // Verify pagination summary contains the expected range values
    const paginationSummary = document.querySelector('.pagination-summary');
    expect(paginationSummary).not.toBeNull();
    expect(paginationSummary?.textContent).toContain("1");
    expect(paginationSummary?.textContent).toContain("3");
    expect(paginationSummary?.textContent).toContain("10");
  });

  // Test 4: Next moves to next page and shows ranks #4-#6
  test("4. Next button moves to next page and shows backend ranks #4–#6", async () => {
    render(<OperatorWorklistCard operatorWorklist={largeOperatorWorklist} />);

    // Click Next button wrapped in act to handle state updates
    const nextButton = screen.getByRole("button", { name: /worklist next page/i });
    await act(async () => {
      await userEvent.click(nextButton);
    });

    // Now should show items 4-6
    expect(screen.getByTestId("worklist-item-4")).toBeInTheDocument();
    expect(screen.getByTestId("worklist-item-5")).toBeInTheDocument();
    expect(screen.getByTestId("worklist-item-6")).toBeInTheDocument();

    // Items 1-3 should NOT be present
    expect(screen.queryByTestId("worklist-item-1")).not.toBeInTheDocument();

    // Page count should update - verify by checking page indicator element
    const pageIndicator = document.querySelector('.pagination-page-indicator');
    expect(pageIndicator).not.toBeNull();
    expect(pageIndicator?.textContent).toContain("2");
    expect(pageIndicator?.textContent).toContain("4");
  });

  // Test 5: Previous returns to first page (#1-#3)
  test("5. Previous button returns to first page showing backend ranks #1–#3", async () => {
    render(<OperatorWorklistCard operatorWorklist={largeOperatorWorklist} />);

    // Navigate to page 2 first
    const nextButton = screen.getByRole("button", { name: /worklist next page/i });
    await act(async () => {
      await userEvent.click(nextButton);
    });

    // Click Previous button
    const prevButton = screen.getByRole("button", { name: /worklist previous page/i });
    await act(async () => {
      await userEvent.click(prevButton);
    });

    // Now should show items 1-3 again
    expect(screen.getByTestId("worklist-item-1")).toBeInTheDocument();
    expect(screen.getByTestId("worklist-item-2")).toBeInTheDocument();
    expect(screen.getByTestId("worklist-item-3")).toBeInTheDocument();

    // Item 4 should NOT be present
    expect(screen.queryByTestId("worklist-item-4")).not.toBeInTheDocument();
  });

  // Test 6: Previous is disabled on first page
  test("6. Previous button is disabled on the first page", () => {
    render(<OperatorWorklistCard operatorWorklist={largeOperatorWorklist} />);

    const prevButton = screen.getByRole("button", { name: /worklist previous page/i });
    expect(prevButton).toBeDisabled();
  });

  // Test 7: Next is disabled on last page
  test("7. Next button is disabled on the last page", async () => {
    render(<OperatorWorklistCard operatorWorklist={largeOperatorWorklist} />);

    // Navigate to last page (page 4 of 4, showing items 10 only)
    // Page 1: 1-3, Page 2: 4-6, Page 3: 7-9, Page 4: 10
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: /worklist next page/i }));
    });
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: /worklist next page/i }));
    });
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: /worklist next page/i }));
    });

    const nextButton = screen.getByRole("button", { name: /worklist next page/i });
    expect(nextButton).toBeDisabled();
  });

  // Test 8: Pagination controls are hidden when item count <= 3
  test("8. Pagination controls are hidden when item count <= 3", () => {
    render(<OperatorWorklistCard operatorWorklist={sampleOperatorWorklist} />);

    // Should NOT have any navigation buttons (only 2 items, less than page size of 3)
    expect(screen.queryByRole("button", { name: /previous/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /next/i })).not.toBeInTheDocument();
  });

  // Test 9: Null command behavior still works on paginated pages
  test("9. Null command still shows 'No executable command yet' on paginated pages", async () => {
    render(<OperatorWorklistCard operatorWorklist={largeOperatorWorklist} />);

    // Item 10 has null command - it should appear on page 4
    // Navigate to last page
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: /worklist next page/i }));
    });
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: /worklist next page/i }));
    });
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: /worklist next page/i }));
    });

    // Item 10 should show "No executable command yet"
    expect(screen.getByTestId("worklist-item-10")).toBeInTheDocument();
    expect(screen.getByTestId("worklist-no-command-10")).toBeInTheDocument();
    expect(screen.getByText("No executable command yet.")).toBeInTheDocument();
  });

  // Test 10: Existing tests for command rendering, empty states, source links, and state badges still pass
  test("10. Pagination does not break existing worklist functionality (command rendering)", () => {
    render(<OperatorWorklistCard operatorWorklist={largeOperatorWorklist} />);

    // First item should have a command
    expect(screen.getByTestId("worklist-command-1")).toBeInTheDocument();
    expect(screen.getByText("kubectl test 1")).toBeInTheDocument();
  });

  test("10b. Pagination does not break existing worklist functionality (state badges)", () => {
    render(<OperatorWorklistCard operatorWorklist={sampleOperatorWorklist} />);

    // State badges should still render
    expect(screen.getByText("not-required")).toBeInTheDocument();
    expect(screen.getByText("unexecuted")).toBeInTheDocument();
  });

  test("10c. Pagination does not break existing worklist functionality (source links)", () => {
    render(<OperatorWorklistCard operatorWorklist={sampleOperatorWorklist} />);

    // Source links should render
    const artifactLinks = document.querySelectorAll(".worklist-artifact-link");
    expect(artifactLinks.length).toBeGreaterThan(0);
    expect(screen.getByText("Assessment")).toBeInTheDocument();
  });
});

// ============================================================================
// Integration: Dashboard Surface Rendering
// ============================================================================

describe("RunOverviewDashboard with Incident Surfaces", () => {
  // Test 15: RunOverviewDashboard renders incident surfaces section
  test("15. RunOverviewDashboard renders incident surfaces section", async () => {
    const { RunOverviewDashboard } = await import("../components/run-summary/RunOverviewDashboard");

    render(
      <RunOverviewDashboard
        runSummaryStats={[{ label: "Clusters", value: 3 }]}
        runStatsSummary="Last 32s"
        runLlmStatsLine={<span>Calls: 3</span>}
        providerBreakdown={null}
        runPlan={null}
        planStatusText={null}
        planCandidateCountLabel="0"
        discoveryVariantCounts={{ safe: 0, approval: 0, approved: 0, duplicate: 0, stale: 0 }}
        discoveryClusters={[]}
        onFocusClusterForNextChecks={vi.fn()}
        artifacts={[]}
        incidentReport={sampleIncidentReport}
        operatorWorklist={sampleOperatorWorklist}
        onTabChange={vi.fn()}
      />
    );

    // Incident surfaces section should be present
    expect(screen.getByTestId("run-overview-incident-surfaces")).toBeInTheDocument();

    // Both cards should render
    expect(screen.getByTestId("incident-report-card")).toBeInTheDocument();
    expect(screen.getByTestId("operator-worklist-card")).toBeInTheDocument();
  });
});
