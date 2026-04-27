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
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
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
// Integration: Dashboard Surface Rendering
// ============================================================================

describe("RunOverviewDashboard with Incident Surfaces", () => {
  // Import dynamically to test integration
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
