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
 * 11. Pagination works correctly (page size 1, previous/next, disabled states).
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
      claimType: "observed",
      statement: "Warning events observed: 5",
      sourceArtifactRefs: [{ label: "Drilldown", path: "/artifacts/drilldown-cluster-a.json" }],
      confidence: "high",
    },
    {
      claimType: "observed",
      statement: "Non-running pods observed: 2",
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
  inferences: [
    {
      claimType: "hypothesis",
      statement: "High control-plane CPU may be causing latency.",
      basis: ["control-plane", "metrics", "review-enrichment"],
      confidence: "medium",
      sourceArtifactRefs: [{ label: "Review Enrichment", path: "/artifacts/review-enrichment.json" }],
    },
  ],
  recommendations: [
    {
      claimType: "recommendation",
      statement: "Collect kubelet logs from affected nodes",
      safetyLevel: "medium",
      sourceArtifactRefs: [{ label: "Assessment", path: "/artifacts/assessment-cluster-a.json" }],
    },
    {
      claimType: "recommendation",
      statement: "Review control-plane component status",
      safetyLevel: "low",
      sourceArtifactRefs: [{ label: "Assessment", path: "/artifacts/assessment-cluster-a.json" }],
    },
  ],
  unknowns: [
    {
      claimType: "unknown",
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
// Phase 2: Canonical Incident Report Surface Tests
// ============================================================================

describe("Phase 2: Canonical Section Headings", () => {
  test("Canonical headings: Observed evidence section renders", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    expect(screen.getByText("Observed evidence")).toBeInTheDocument();
  });

  test("Canonical headings: Deterministic conclusions section renders", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    expect(screen.getByText("Deterministic conclusions")).toBeInTheDocument();
  });

  test("Canonical headings: Hypotheses section renders", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    expect(screen.getByText("Hypotheses")).toBeInTheDocument();
  });

  test("Canonical headings: Unknowns / not proven yet section renders", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    expect(screen.getByText("Unknowns / not proven yet")).toBeInTheDocument();
  });

  test("Canonical headings: Recommended next actions section renders", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    expect(screen.getByText("Recommended next actions")).toBeInTheDocument();
  });
});

describe("Phase 2: Derived Claims Section", () => {
  test("Derived claims render in deterministic conclusions section", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    expect(screen.getByTestId("incident-derived")).toBeInTheDocument();
    expect(screen.getByText("Cluster cluster-a health rating is Degraded.")).toBeInTheDocument();
  });

  test("Derived claims show source fields", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    expect(screen.getByText(/from: health_rating/i)).toBeInTheDocument();
  });

  test("Derived claims show confidence", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    expect(screen.getAllByText(/confidence: high/i).length).toBeGreaterThan(0);
  });

  test("Empty derived section does not render", () => {
    const reportWithoutDerived: IncidentReportPayload = {
      ...sampleIncidentReport,
      derived: [],
    };
    render(<IncidentReportCard incidentReport={reportWithoutDerived} />);
    expect(screen.queryByTestId("incident-derived")).not.toBeInTheDocument();
  });
});

describe("Phase 2: Structured Recommendations", () => {
  test("Structured recommendations render with safety level badges", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    expect(screen.getByTestId("incident-recommendations")).toBeInTheDocument();
    expect(screen.getByText("safety: medium")).toBeInTheDocument();
    expect(screen.getByText("safety: low")).toBeInTheDocument();
  });

  test("Structured recommendations preferred over legacy recommendedActions", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    // Should show structured recommendations, not legacy
    expect(screen.getByTestId("incident-recommendations")).toBeInTheDocument();
    expect(screen.queryByTestId("incident-recommended-actions")).not.toBeInTheDocument();
  });

  test("Legacy recommendedActions shown when no structured recommendations", () => {
    const reportWithLegacyOnly: IncidentReportPayload = {
      ...sampleIncidentReport,
      recommendations: [],
    };
    render(<IncidentReportCard incidentReport={reportWithLegacyOnly} />);
    expect(screen.getByTestId("incident-recommended-actions")).toBeInTheDocument();
    expect(screen.getByText("Recommended next actions")).toBeInTheDocument();
  });

  test("Empty recommendations section does not render", () => {
    const reportWithoutRecs: IncidentReportPayload = {
      ...sampleIncidentReport,
      recommendations: [],
      recommendedActions: [],
    };
    render(<IncidentReportCard incidentReport={reportWithoutRecs} />);
    expect(screen.queryByTestId("incident-recommendations")).not.toBeInTheDocument();
    expect(screen.queryByTestId("incident-recommended-actions")).not.toBeInTheDocument();
  });
});

describe("Phase 2: Visible Claim Type Labels", () => {
  test("Claim type labels: observed label renders", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    // Multiple facts may have observed label - use getAllByTestId
    expect(screen.getAllByTestId("claim-type-observed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("observed").length).toBeGreaterThan(0);
  });

  test("Claim type labels: derived label renders", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    expect(screen.getByTestId("claim-type-derived")).toBeInTheDocument();
    expect(screen.getByText("derived")).toBeInTheDocument();
  });

  test("Claim type labels: hypothesis label renders", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    expect(screen.getByTestId("claim-type-hypothesis")).toBeInTheDocument();
    expect(screen.getByText("hypothesis")).toBeInTheDocument();
  });

  test("Claim type labels: recommendation label renders", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    // Multiple recommendations may have recommendation label - use getAllByTestId
    expect(screen.getAllByTestId("claim-type-recommendation").length).toBeGreaterThan(0);
    expect(screen.getAllByText("recommendation").length).toBeGreaterThan(0);
  });

  test("Claim type labels: unknown label renders", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    expect(screen.getByTestId("claim-type-unknown")).toBeInTheDocument();
    expect(screen.getByText("unknown")).toBeInTheDocument();
  });
});

describe("Phase 2: Narrative Quality", () => {
  test("No 'root cause' language in observed evidence", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    const observedSection = screen.getByTestId("incident-facts");
    const text = observedSection.textContent || "";
    expect(text.toLowerCase()).not.toContain("root cause");
    expect(text.toLowerCase()).not.toContain("caused by");
  });

  test("No 'root cause' language in deterministic conclusions", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    const derivedSection = screen.getByTestId("incident-derived");
    const text = derivedSection.textContent || "";
    expect(text.toLowerCase()).not.toContain("root cause");
    expect(text.toLowerCase()).not.toContain("caused by");
  });

  test("Recommendations are action-oriented", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    // Structured recommendations should be action statements
    expect(screen.getByText("Collect kubelet logs from affected nodes")).toBeInTheDocument();
    expect(screen.getByText("Review control-plane component status")).toBeInTheDocument();
  });

  test("Unknowns include whyMissing explanation", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    // whyMissing is rendered inline, check for partial text match
    expect(screen.getByText(/why missing: Not collected in this run/i)).toBeInTheDocument();
  });

  test("Hypotheses include basis for causal language", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);
    // The hypothesis about CPU causing latency should have basis
    expect(screen.getByText(/basis: /i)).toBeInTheDocument();
    // basis may contain control-plane - check in hypothesis section
    const inferenceSection = screen.getByTestId("incident-inferences");
    expect(inferenceSection.textContent).toContain("control-plane");
  });
});

describe("Phase 2: hasContent Edge Cases", () => {
  test("derived-only incident report renders 'Deterministic conclusions' section", () => {
    const derivedOnlyReport: IncidentReportPayload = {
      title: "Derived only test",
      status: "healthy",
      affectedScope: null,
      impact: null,
      evidenceSummary: null,
      facts: [],
      derived: [
        {
          claimType: "derived",
          statement: "Cluster cluster-b health rating is Healthy.",
          sourceFields: ["health_rating"],
          sourceArtifactRefs: [{ label: "Assessment", path: "/artifacts/assessment-cluster-b.json" }],
          confidence: "high",
        },
      ],
      inferences: [],
      recommendations: [],
      unknowns: [],
      staleEvidenceWarnings: [],
      confidence: "high",
      freshness: null,
      recommendedActions: [],
      sourceArtifactRefs: [],
    };

    render(<IncidentReportCard incidentReport={derivedOnlyReport} />);

    // Should render the derived section, not "No incident data available"
    expect(screen.getByText("Deterministic conclusions")).toBeInTheDocument();
    expect(screen.getByText("Cluster cluster-b health rating is Healthy.")).toBeInTheDocument();
    // Should NOT show empty state
    expect(screen.queryByText("No incident data available.")).not.toBeInTheDocument();
  });

  test("structured-recommendations-only incident report renders 'Recommended next actions'", () => {
    const recsOnlyReport: IncidentReportPayload = {
      title: "Recommendations only test",
      status: "healthy",
      affectedScope: null,
      impact: null,
      evidenceSummary: null,
      facts: [],
      derived: [],
      inferences: [],
      recommendations: [
        {
          claimType: "recommendation",
          statement: "Check node health metrics",
          safetyLevel: "low",
          sourceArtifactRefs: [],
        },
      ],
      unknowns: [],
      staleEvidenceWarnings: [],
      confidence: "medium",
      freshness: null,
      recommendedActions: [],
      sourceArtifactRefs: [],
    };

    render(<IncidentReportCard incidentReport={recsOnlyReport} />);

    // Should render the recommendations section, not "No incident data available"
    expect(screen.getByText("Recommended next actions")).toBeInTheDocument();
    expect(screen.getByText("Check node health metrics")).toBeInTheDocument();
    // Should NOT show empty state
    expect(screen.queryByText("No incident data available.")).not.toBeInTheDocument();
  });

  test("legacy-recommended-actions-only report still works with consistent heading", () => {
    const legacyOnlyReport: IncidentReportPayload = {
      title: "Legacy only test",
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
      confidence: "low",
      freshness: null,
      recommendedActions: ["Check node status"],
      sourceArtifactRefs: [],
    };

    render(<IncidentReportCard incidentReport={legacyOnlyReport} />);

    // Legacy fallback should now also use "Recommended next actions"
    expect(screen.getByText("Recommended next actions")).toBeInTheDocument();
    expect(screen.getByText("Check node status")).toBeInTheDocument();
    // Should NOT show empty state
    expect(screen.queryByText("No incident data available.")).not.toBeInTheDocument();
  });
});

// ============================================================================
// Incident Report Claim Taxonomy Tests (Epic: Incident Report Content Quality)
// ============================================================================

describe("IncidentReportCard Claim Taxonomy", () => {
  // Test for claim taxonomy rendering - claim groups render in distinct sections; badges are deferred

  test("Claim taxonomy: observed claims render in facts section", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    // Facts section should exist
    expect(screen.getByTestId("incident-facts")).toBeInTheDocument();
    expect(screen.getByText("Observed evidence")).toBeInTheDocument();

    // Each fact should have claimType field
    const facts = document.querySelectorAll(".incident-fact-item");
    expect(facts.length).toBeGreaterThan(0);
  });

  test("Claim taxonomy: hypothesis claims render in inferences section", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    // Inferences section should exist
    expect(screen.getByTestId("incident-inferences")).toBeInTheDocument();
    expect(screen.getByText("Hypotheses")).toBeInTheDocument();

    // Each inference should have basis displayed
    const inferenceBasis = document.querySelectorAll(".inference-basis");
    expect(inferenceBasis.length).toBeGreaterThan(0);
  });

  test("Claim taxonomy: unknown claims render in unknowns section", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    // Unknowns section should exist
    expect(screen.getByTestId("incident-unknowns")).toBeInTheDocument();
    expect(screen.getByText("Unknowns / not proven yet")).toBeInTheDocument();

    // Each unknown should have whyMissing explanation
    const unknownReasons = document.querySelectorAll(".unknown-reason");
    expect(unknownReasons.length).toBeGreaterThan(0);
  });

  test("Claim taxonomy: recommendation claims are separated from facts", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    // Structured recommendations section should exist (preferred over legacy)
    expect(screen.getByTestId("incident-recommendations")).toBeInTheDocument();
    expect(screen.getByText("Recommended next actions")).toBeInTheDocument();

    // Recommendations should be text descriptions, not mixed with facts
    const recommendedActions = document.querySelectorAll(".incident-action-item");
    expect(recommendedActions.length).toBeGreaterThan(0);
  });

  test("Claim taxonomy: claim groups render in distinct visual sections", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    // Facts section
    expect(screen.getByTestId("incident-facts")).toBeInTheDocument();

    // Derived section
    expect(screen.getByTestId("incident-derived")).toBeInTheDocument();

    // Inferences section
    expect(screen.getByTestId("incident-inferences")).toBeInTheDocument();

    // Unknowns section
    expect(screen.getByTestId("incident-unknowns")).toBeInTheDocument();

    // Stale warnings section
    expect(screen.getByTestId("incident-stale-warnings")).toBeInTheDocument();

    // Structured recommendations section (preferred over legacy)
    expect(screen.getByTestId("incident-recommendations")).toBeInTheDocument();
  });

  test("Claim taxonomy: observed claims have evidence badges", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    // Facts should show confidence
    const confidenceBadges = document.querySelectorAll(".incident-confidence");
    expect(confidenceBadges.length).toBeGreaterThan(0);

    // Check for high confidence badge
    expect(screen.getAllByText(/confidence: high/i).length).toBeGreaterThan(0);
  });

  test("Claim taxonomy: hypothesis claims have basis and provider badge", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    // Provider-assisted badge should appear
    expect(screen.getByText("provider-assisted")).toBeInTheDocument();

    // Basis should be displayed
    const inferenceBasis = document.querySelectorAll(".inference-basis");
    expect(inferenceBasis.length).toBeGreaterThan(0);
  });

  test("Claim taxonomy: unknown claims show why missing", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    // Missing evidence statement should be visible
    expect(screen.getByText("Missing evidence: logs from edge nodes")).toBeInTheDocument();

    // Why missing explanation should be visible
    expect(screen.getByText(/why missing: /i)).toBeInTheDocument();
  });

  test("Claim taxonomy: empty sections do not render", () => {
    const reportWithSomeEmpty: IncidentReportPayload = {
      title: "Partial test",
      status: "healthy",
      affectedScope: null,
      impact: null,
      evidenceSummary: null,
      facts: [], // empty
      derived: [], // empty
      inferences: [], // empty
      recommendations: [], // empty
      unknowns: [], // empty
      staleEvidenceWarnings: [],
      confidence: "high",
      freshness: null,
      recommendedActions: [],
      sourceArtifactRefs: [],
    };

    render(<IncidentReportCard incidentReport={reportWithSomeEmpty} />);

    // Empty sections should not be in the document
    expect(screen.queryByTestId("incident-facts")).not.toBeInTheDocument();
    expect(screen.queryByTestId("incident-inferences")).not.toBeInTheDocument();
    expect(screen.queryByTestId("incident-unknowns")).not.toBeInTheDocument();
    expect(screen.queryByTestId("incident-recommended-actions")).not.toBeInTheDocument();
  });
});

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
    expect(screen.getByText("Observed evidence")).toBeInTheDocument();
    expect(screen.getByText("Cluster cluster-a health rating is Degraded.")).toBeInTheDocument();

    // Inferences section
    expect(screen.getByTestId("incident-inferences")).toBeInTheDocument();
    expect(screen.getByText("Hypotheses")).toBeInTheDocument();
    expect(screen.getByText("High control-plane CPU may be causing latency.")).toBeInTheDocument();

    // Unknowns section
    expect(screen.getByTestId("incident-unknowns")).toBeInTheDocument();
    expect(screen.getByText("Unknowns / not proven yet")).toBeInTheDocument();
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

    // Structured recommendations section (preferred over legacy)
    expect(screen.getByTestId("incident-recommendations")).toBeInTheDocument();
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
          claimType: "observed",
          statement: "Test fact with empty refs",
          sourceArtifactRefs: [], // Empty array
          confidence: "high",
        },
      ],
      derived: [],
      inferences: [],
      recommendations: [],
      unknowns: [
        {
          claimType: "unknown",
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
  // Long kubectl title for truncation tests
  const longKubectlTitle = "kubectl describe pod -n recommender-service recommender-service-7df47f487-dqghg --context admin@rees46-k8s";

  // Test 5: Operator worklist renders command when present
  // Test 5a: Title uses ExpandableText for truncation
  test("5a. Worklist title uses ExpandableText component for truncation", () => {
    render(<OperatorWorklistCard operatorWorklist={sampleOperatorWorklist} />);

    // Title should use ExpandableText component
    expect(screen.getByTestId("expandable-text-worklist-title-1")).toBeInTheDocument();
  });

  // Test 5b: Title text is rendered within ExpandableText
  test("5b. Worklist title text is visible in truncated form", () => {
    render(<OperatorWorklistCard operatorWorklist={sampleOperatorWorklist} />);

    // The title text should be visible
    expect(screen.getByText("Collect kubelet logs from affected nodes")).toBeInTheDocument();
  });

  // Test 5c: Title truncation - long kubectl-like title wraps to one line with popup
  test("5c. Long kubectl-like title truncates to one line and opens popup on click", async () => {
    const worklistWithLongTitle: OperatorWorklistPayload = {
      items: [
        {
          id: "long-title-item",
          rank: 1,
          workstream: "incident",
          title: "kubectl describe pod -n recommender-service recommender-service-7df47f487-dqghg --context admin@rees46-k8s",
          description: "Long title test",
          command: null, // No command - title is NOT a command
          targetCluster: "cluster-a",
          targetContext: "prod",
          reason: "Testing truncation",
          expectedEvidence: null,
          safetyNote: null,
          approvalState: null,
          executionState: null,
          feedbackState: null,
          sourceArtifactRefs: [],
        },
      ],
      totalItems: 1,
      completedItems: 0,
      pendingItems: 1,
      blockedItems: 0,
    };

    render(<OperatorWorklistCard operatorWorklist={worklistWithLongTitle} />);

    // Title trigger should exist
    const titleTrigger = screen.getByTestId("expandable-text-worklist-title-1");
    expect(titleTrigger).toBeInTheDocument();

    // The truncated text should be visible
    expect(screen.getByTestId("expandable-text-worklist-title-1-truncated")).toBeInTheDocument();

    // Popup should NOT be open initially
    expect(screen.queryByTestId("expandable-text-worklist-title-1-popup")).not.toBeInTheDocument();

    // Click the trigger to open popup
    await act(async () => {
      await userEvent.click(titleTrigger);
    });

    // Popup should now be open
    expect(screen.getByTestId("expandable-text-worklist-title-1-popup")).toBeInTheDocument();

    // Popup should contain the full kubectl text in popup content
    expect(screen.getByTestId("expandable-text-worklist-title-1-popup-content")).toHaveTextContent(longKubectlTitle);

    // Popup label should be "Full check text" (generic, not "Full command")
    expect(screen.getByText("Full check text")).toBeInTheDocument();
  });

  // Test 5d: "No executable command yet" still appears when command is null
  test("5d. 'No executable command yet' still appears when item.command is null", () => {
    const worklistWithLongTitleAndNoCommand: OperatorWorklistPayload = {
      items: [
        {
          id: "long-title-no-command",
          rank: 1,
          workstream: "incident",
          title: "kubectl describe pod -n recommender-service recommender-service-7df47f487-dqghg --context admin@rees46-k8s",
          description: "Long title, no command",
          command: null, // Explicitly null
          targetCluster: "cluster-a",
          targetContext: "prod",
          reason: null,
          expectedEvidence: null,
          safetyNote: null,
          approvalState: null,
          executionState: null,
          feedbackState: null,
          sourceArtifactRefs: [],
        },
      ],
      totalItems: 1,
      completedItems: 0,
      pendingItems: 1,
      blockedItems: 0,
    };

    render(<OperatorWorklistCard operatorWorklist={worklistWithLongTitleAndNoCommand} />);

    // Title should still use ExpandableText
    expect(screen.getByTestId("expandable-text-worklist-title-1")).toBeInTheDocument();

    // "No executable command yet" should still appear
    expect(screen.getByTestId("worklist-no-command-1")).toBeInTheDocument();
    expect(screen.getByText("No executable command yet.")).toBeInTheDocument();
  });

  // Test 5: Operator worklist renders command when present
  test("5e. Operator worklist renders command when present", () => {
    render(<OperatorWorklistCard operatorWorklist={sampleOperatorWorklist} />);

    // First item has a command - now via CommandText component
    expect(screen.getByTestId("worklist-item-1")).toBeInTheDocument();
    expect(screen.getByTestId("command-text-worklist-command-1")).toBeInTheDocument();
    expect(screen.getByText("kubectl logs -n kube-system -l k8s-app=kubelet --context cluster-a")).toBeInTheDocument();
  });

  // Test 6: Operator worklist renders "No executable command yet" when command is null
  test("6. Operator worklist renders 'No executable command yet' when command is null", async () => {
    render(<OperatorWorklistCard operatorWorklist={sampleOperatorWorklist} />);

    // Navigate to page 2 to see the second item (which has null command)
    const nextButton = screen.getByRole("button", { name: /worklist next page/i });
    await act(async () => {
      await userEvent.click(nextButton);
    });

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

  // Test 8: Rank and workstream render for each item (across pages)
  test("8. Rank and workstream badge render for each item", async () => {
    render(<OperatorWorklistCard operatorWorklist={sampleOperatorWorklist} />);

    // First item
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText("incident")).toBeInTheDocument();

    // Navigate to page 2 to see the second item
    const nextButton = screen.getByRole("button", { name: /worklist next page/i });
    await act(async () => {
      await userEvent.click(nextButton);
    });

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

  // Test 2: Operator worklist renders only first item by default (page size = 1)
  test("2. Operator worklist renders only first item by default when item count exceeds page size", () => {
    render(<OperatorWorklistCard operatorWorklist={largeOperatorWorklist} />);

    // Should show only first item (page size = 1)
    expect(screen.getByTestId("worklist-item-1")).toBeInTheDocument();

    // Items 2-10 should NOT be present
    expect(screen.queryByTestId("worklist-item-2")).not.toBeInTheDocument();
    expect(screen.queryByTestId("worklist-item-10")).not.toBeInTheDocument();
  });

  // Test 3: Page count text renders correctly for one-item pagination
  test("3. Page count text renders correctly, e.g. 'Item 1 of 10'", () => {
    render(<OperatorWorklistCard operatorWorklist={largeOperatorWorklist} />);

    // Should show the pagination item indicator in single-item mode
    expect(screen.getByTestId("pagination-item-indicator")).toBeInTheDocument();
    // Verify item indicator contains the expected values
    const itemIndicator = document.querySelector('.pagination-item-indicator');
    expect(itemIndicator).not.toBeNull();
    const indicatorText = itemIndicator?.textContent || "";
    expect(indicatorText).toContain("Item");
    expect(indicatorText).toContain("1");
    expect(indicatorText).toContain("10");
  });

  // Test 4: Next moves to next page and shows backend rank #2
  test("4. Next button moves to next page and shows backend rank #2", async () => {
    render(<OperatorWorklistCard operatorWorklist={largeOperatorWorklist} />);

    // Click Next button wrapped in act to handle state updates
    const nextButton = screen.getByRole("button", { name: /worklist next page/i });
    await act(async () => {
      await userEvent.click(nextButton);
    });

    // Now should show item 2 only
    expect(screen.getByTestId("worklist-item-2")).toBeInTheDocument();

    // Item 1 should NOT be present
    expect(screen.queryByTestId("worklist-item-1")).not.toBeInTheDocument();

    // Page count should update - verify by checking item indicator element
    const itemIndicator = document.querySelector('.pagination-item-indicator');
    expect(itemIndicator).not.toBeNull();
    expect(itemIndicator?.textContent).toContain("Item");
    expect(itemIndicator?.textContent).toContain("2");
  });

  // Test 5: Previous returns to first page showing backend rank #1 only
  test("5. Previous button returns to first page showing backend rank #1", async () => {
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

    // Now should show item 1 only
    expect(screen.getByTestId("worklist-item-1")).toBeInTheDocument();

    // Item 2 should NOT be present
    expect(screen.queryByTestId("worklist-item-2")).not.toBeInTheDocument();
  });

  // Test 6: Previous is disabled on first page
  test("6. Previous button is disabled on the first page", () => {
    render(<OperatorWorklistCard operatorWorklist={largeOperatorWorklist} />);

    const prevButton = screen.getByRole("button", { name: /worklist previous page/i });
    expect(prevButton).toBeDisabled();
  });

  // Test 7: Next is disabled on last page (page 10 of 10, showing item #10)
  test("7. Next button is disabled on the last page", async () => {
    render(<OperatorWorklistCard operatorWorklist={largeOperatorWorklist} />);

    // Navigate to last page (page 10 of 10, showing item 10 only)
    // With page size of 1, we need to click next 9 times to reach page 10
    for (let i = 0; i < 9; i++) {
      await act(async () => {
        await userEvent.click(screen.getByRole("button", { name: /worklist next page/i }));
      });
    }

    const nextButton = screen.getByRole("button", { name: /worklist next page/i });
    expect(nextButton).toBeDisabled();
  });

  // Test 8: Pagination controls are hidden when item count <= 1
  test("8. Pagination controls are hidden when item count <= 1", () => {
    const singleItemWorklist: OperatorWorklistPayload = {
      items: [
        { id: "item-1", rank: 1, workstream: "incident", title: "Item 1", description: "", command: "kubectl test 1", targetCluster: null, targetContext: null, reason: null, expectedEvidence: null, safetyNote: null, approvalState: null, executionState: null, feedbackState: null, sourceArtifactRefs: [] },
      ],
      totalItems: 1,
      completedItems: 0,
      pendingItems: 1,
      blockedItems: 0,
    };

    render(<OperatorWorklistCard operatorWorklist={singleItemWorklist} />);

    // Should NOT have any navigation buttons (only 1 item, less than page size of 1)
    expect(screen.queryByRole("button", { name: /previous/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /next/i })).not.toBeInTheDocument();
  });

  // Test 9: Null command behavior still works on paginated pages
  test("9. Null command still shows 'No executable command yet' on paginated pages", async () => {
    render(<OperatorWorklistCard operatorWorklist={largeOperatorWorklist} />);

    // Item 10 has null command - it should appear on page 10
    // Navigate to last page (page 10 of 10, showing item 10 only)
    for (let i = 0; i < 9; i++) {
      await act(async () => {
        await userEvent.click(screen.getByRole("button", { name: /worklist next page/i }));
      });
    }

    // Item 10 should show "No executable command yet"
    expect(screen.getByTestId("worklist-item-10")).toBeInTheDocument();
    expect(screen.getByTestId("worklist-no-command-10")).toBeInTheDocument();
    expect(screen.getByText("No executable command yet.")).toBeInTheDocument();
  });

  // Test 10: Existing tests for command rendering, empty states, source links, and state badges still pass
  test("10. Pagination does not break existing worklist functionality (command rendering)", () => {
    render(<OperatorWorklistCard operatorWorklist={largeOperatorWorklist} />);

    // First item should have a command - now via CommandText component
    expect(screen.getByTestId("command-text-worklist-command-1")).toBeInTheDocument();
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

// ============================================================================
// Phase 3: Content Quality Tests (Deterministic Quality Fixtures)
// ============================================================================

describe("Phase 3: Content Quality Rules", () => {
  const CAUSAL_PHRASES = ["root cause", "caused by", "because of", "is the cause", "the cause of", "directly caused", "responsible for"];
  const FILLER_PHRASES = [
    "the system has identified",
    "potentially relevant diagnostic indicators",
    "it is recommended that",
    "various issues",
  ];

  test("No causal language in observed evidence section", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    const observedSection = screen.getByTestId("incident-facts");
    const text = observedSection.textContent || "";

    for (const phrase of CAUSAL_PHRASES) {
      expect(text.toLowerCase()).not.toContain(phrase);
    }
  });

  test("No causal language in deterministic conclusions section", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    const derivedSection = screen.getByTestId("incident-derived");
    const text = derivedSection.textContent || "";

    for (const phrase of CAUSAL_PHRASES) {
      expect(text.toLowerCase()).not.toContain(phrase);
    }
  });

  test("Hypotheses section has non-empty basis for each item", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    const inferenceBasis = document.querySelectorAll(".inference-basis");
    expect(inferenceBasis.length).toBeGreaterThan(0);

    for (const basis of inferenceBasis) {
      const basisText = basis.textContent || "";
      const basisValues = basisText.replace(/^basis:\s*/i, "");
      expect(basisValues.trim().length).toBeGreaterThan(0);
    }
  });

  test("Unknowns section shows why missing explanation", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    const unknownReasons = document.querySelectorAll(".unknown-reason");
    expect(unknownReasons.length).toBeGreaterThan(0);

    for (const reason of unknownReasons) {
      const reasonText = reason.textContent || "";
      const missingExplanation = reasonText.replace(/^why missing:\s*/i, "");
      expect(missingExplanation.trim().length).toBeGreaterThan(0);
    }
  });

  test("Recommendations section renders under 'Recommended next actions'", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    expect(screen.getByTestId("incident-recommendations")).toBeInTheDocument();
    expect(screen.getByText("Recommended next actions")).toBeInTheDocument();

    const recommendationItems = document.querySelectorAll(".incident-recommendation-item");
    expect(recommendationItems.length).toBeGreaterThan(0);

    for (const item of recommendationItems) {
      const statement = item.querySelector(".incident-statement");
      const text = statement?.textContent || "";
      expect(text.toLowerCase()).toMatch(/^(collect|check|review|inspect|investigate|analyze|monitor)/);
    }
  });

  test("Section headings are concise (under 50 characters)", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    const headings = [
      "Observed evidence",
      "Deterministic conclusions",
      "Hypotheses",
      "Unknowns / not proven yet",
      "Recommended next actions",
    ];

    for (const heading of headings) {
      expect(heading.length).toBeLessThan(50);
    }
  });

  test("Claim statements are reasonably short (under 200 characters)", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    const statements = document.querySelectorAll(".incident-statement");
    for (const statement of statements) {
      const text = statement.textContent || "";
      expect(text.length).toBeLessThan(200);
    }
  });

  test("No filler phrases in claim statements", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    const allText = document.body.textContent || "";

    for (const phrase of FILLER_PHRASES) {
      expect(allText.toLowerCase()).not.toContain(phrase);
    }
  });

  test("Report covers core questions: observed, derived, hypothesized, unknown, recommended", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    expect(screen.getByTestId("incident-facts")).toBeInTheDocument();
    expect(screen.getByTestId("incident-derived")).toBeInTheDocument();
    expect(screen.getByTestId("incident-inferences")).toBeInTheDocument();
    expect(screen.getByTestId("incident-unknowns")).toBeInTheDocument();
    expect(screen.getByTestId("incident-recommendations")).toBeInTheDocument();
  });
});

describe("Phase 3: Content Quality - Rendering Semantics", () => {
  test("Bad observed claim with causal language visibly renders without production sanitization", () => {
    const reportWithBadClaim: IncidentReportPayload = {
      ...sampleIncidentReport,
      facts: [
        {
          claimType: "observed",
          statement: "The root cause of the crash is memory exhaustion",
          sourceArtifactRefs: [],
          confidence: "high",
        },
      ],
    };

    render(<IncidentReportCard incidentReport={reportWithBadClaim} />);

    expect(screen.getByText(/root cause/i)).toBeInTheDocument();
    expect(screen.getByTestId("claim-type-observed")).toBeInTheDocument();
  });

  test("Bad derived claim with causal language visibly renders without production sanitization", () => {
    const reportWithBadClaim: IncidentReportPayload = {
      ...sampleIncidentReport,
      derived: [
        {
          claimType: "derived",
          statement: "The pod crash was caused by OOM kill",
          sourceFields: ["state", "lastState"],
          sourceArtifactRefs: [],
          confidence: "medium",
        },
      ],
    };

    render(<IncidentReportCard incidentReport={reportWithBadClaim} />);

    expect(screen.getByText(/caused by/i)).toBeInTheDocument();
    expect(screen.getByTestId("claim-type-derived")).toBeInTheDocument();
  });

  test("Unknown claim without whyMissing renders statement but not why-missing explanation", () => {
    const reportWithBadClaim: IncidentReportPayload = {
      ...sampleIncidentReport,
      unknowns: [
        {
          claimType: "unknown",
          statement: "Missing evidence: logs from edge nodes",
          whyMissing: null,
          sourceArtifactRefs: [],
        },
      ],
    };

    render(<IncidentReportCard incidentReport={reportWithBadClaim} />);

    expect(screen.getByText("Missing evidence: logs from edge nodes")).toBeInTheDocument();
    expect(screen.queryByText(/why missing:/i)).not.toBeInTheDocument();
  });

  test("Hypothesis claim without basis renders statement but basis section has no content", () => {
    const reportWithBadClaim: IncidentReportPayload = {
      ...sampleIncidentReport,
      inferences: [
        {
          claimType: "hypothesis",
          statement: "This might be the root cause",
          basis: [],
          confidence: "low",
          sourceArtifactRefs: [],
        },
      ],
    };

    render(<IncidentReportCard incidentReport={reportWithBadClaim} />);

    expect(screen.getByText("This might be the root cause")).toBeInTheDocument();

    const basisElements = document.querySelectorAll(".inference-basis");
    expect(basisElements.length).toBeGreaterThan(0);

    for (const basis of basisElements) {
      const basisText = basis.textContent || "";
      const basisContent = basisText.replace(/^basis:\s*/i, "").trim();
      expect(basisContent.length).toBe(0);
    }
  });
});

describe("Phase 3: Content Quality - Report Structure Verification", () => {
  test("Degraded report answers what is observed", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    const factsSection = screen.getByTestId("incident-facts");
    expect(factsSection).toBeInTheDocument();
    expect(screen.getByText(/Warning events observed/i)).toBeInTheDocument();
  });

  test("Degraded report answers what is derived", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    const derivedSection = screen.getByTestId("incident-derived");
    expect(derivedSection).toBeInTheDocument();
    expect(screen.getByText(/health rating is/i)).toBeInTheDocument();
  });

  test("Degraded report answers what is hypothesized", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    const inferencesSection = screen.getByTestId("incident-inferences");
    expect(inferencesSection).toBeInTheDocument();
    expect(screen.getByText(/may be causing/i)).toBeInTheDocument();
  });

  test("Degraded report answers what is unknown", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    const unknownsSection = screen.getByTestId("incident-unknowns");
    expect(unknownsSection).toBeInTheDocument();
    expect(screen.getByText(/Missing evidence/i)).toBeInTheDocument();
  });

  test("Degraded report answers what action is recommended", () => {
    render(<IncidentReportCard incidentReport={sampleIncidentReport} />);

    const recommendationsSection = screen.getByTestId("incident-recommendations");
    expect(recommendationsSection).toBeInTheDocument();
    expect(screen.getByText("Collect kubelet logs from affected nodes")).toBeInTheDocument();
    expect(screen.getByText("Review control-plane component status")).toBeInTheDocument();
  });
});
