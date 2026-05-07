/**
 * provider-alias-deanonymization-regression.test.tsx
 *
 * Regression test for provider alias de-anonymization in UI components.
 *
 * This test verifies that provider aliases (e.g., cluster-a, cluster-b, namespace-f)
 * do NOT appear in operator-facing UI components after backend/API de-anonymization.
 *
 * Covered components:
 * - IncidentReportCard: verifies real cluster names render, aliases don't
 * - OperatorWorklistCard: verifies real cluster contexts in commands, aliases don't
 *
 * Backend de-anonymization coverage (separate tests in test_server_read_support_deanonymization.py):
 * - _find_review_enrichment() de-anonymization
 * - _find_next_check_plan() de-anonymization
 * - provider_alias_mapping metadata preserved for audit
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { IncidentReportCard } from "../components/run-summary/IncidentReportCard";
import { OperatorWorklistCard } from "../components/run-summary/OperatorWorklistCard";

// ============================================================================
// De-anonymized incident report - all cluster references use real names
// ============================================================================

const createDeonymizedIncidentReport = () => ({
  title: "Degraded health detected in cluster1 and cluster2",
  status: "degraded",
  affectedScope: "cluster1, cluster2",
  impact: null,
  evidenceSummary: null,
  facts: [
    {
      claimType: "observed" as const,
      statement: "Warning events observed: 5 in cluster1",
      sourceArtifactRefs: [{ label: "Drilldown", path: "/artifacts/drilldown-cluster1.json" }],
      confidence: "high",
    },
    {
      claimType: "observed" as const,
      statement: "Non-running pods observed: 2 in cluster2",
      sourceArtifactRefs: [{ label: "Drilldown", path: "/artifacts/drilldown-cluster2.json" }],
      confidence: "high",
    },
  ],
  derived: [
    {
      claimType: "derived" as const,
      statement: "Cluster cluster1 health rating is Degraded.",
      sourceFields: ["health_rating"],
      sourceArtifactRefs: [{ label: "Assessment", path: "/artifacts/assessment-cluster1.json" }],
      confidence: "high",
    },
  ],
  inferences: [
    {
      claimType: "hypothesis" as const,
      statement: "High control-plane CPU may be causing latency in cluster1.",
      basis: ["control-plane", "metrics", "review-enrichment"],
      confidence: "medium",
      sourceArtifactRefs: [{ label: "Review Enrichment", path: "/artifacts/review-enrichment.json" }],
    },
  ],
  recommendations: [
    {
      claimType: "recommendation" as const,
      statement: "Collect kubelet logs from cluster1 nodes in namespace kube-system",
      safetyLevel: "medium",
      sourceArtifactRefs: [{ label: "Assessment", path: "/artifacts/assessment-cluster1.json" }],
    },
  ],
  unknowns: [
    {
      claimType: "unknown" as const,
      statement: "Missing evidence: logs from edge nodes in cluster2",
      whyMissing: "Not collected in this run",
      sourceArtifactRefs: [],
    },
  ],
  staleEvidenceWarnings: [],
  confidence: "high",
  freshness: null,
  recommendedActions: ["Collect kubelet logs from cluster1 nodes in namespace kube-system"],
  sourceArtifactRefs: [{ label: "Assessment", path: "/artifacts/assessment-cluster1.json" }],
});

// ============================================================================
// De-anonymized operator worklist - all contexts use real names
// ============================================================================

const createDeonymizedOperatorWorklist = () => ({
  items: [
    {
      id: "deanon-item-1",
      rank: 1,
      workstream: "incident",
      title: "Collect kubelet logs from cluster1 control-plane pods",
      description: "Owner: platform; method: kubectl logs; evidence needed: kubelet logs",
      command: "kubectl logs -n kube-system -l k8s-app=kubelet --context cluster1",
      targetCluster: "cluster1",
      targetContext: "prod",
      reason: "Immediate triage for High CPU in cluster1",
      expectedEvidence: "kubelet logs from cluster1",
      safetyNote: "Urgency: high; primary triage: true",
      approvalState: "not-required",
      executionState: "unexecuted",
      feedbackState: null,
      sourceArtifactRefs: [{ label: "Assessment", path: "/artifacts/assessment-cluster1.json" }],
    },
    {
      id: "deanon-item-2",
      rank: 2,
      workstream: "evidence",
      title: "Inspect readiness probes for web-frontend in cluster2",
      description: "Owner: platform; method: kubectl describe; evidence needed: pod status",
      command: "kubectl describe pod -n kube-system -l app=web-frontend --context cluster2",
      targetCluster: "cluster2",
      targetContext: "stage",
      reason: "Gather additional evidence from cluster2",
      expectedEvidence: "pod status from cluster2",
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
});

// ============================================================================
// Component-level regression tests
// ============================================================================

describe("Provider Alias De-anonymization Regression", () => {
  describe("IncidentReportCard - No Alias Leakage", () => {
    it("renders real cluster names, not aliases", () => {
      const incidentReport = createDeonymizedIncidentReport();
      render(<IncidentReportCard incidentReport={incidentReport} />);

      // Verify real names appear - use getAllByText since cluster names appear multiple times
      expect(screen.getAllByText(/cluster1/).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/cluster2/).length).toBeGreaterThan(0);
    });

    it("does NOT render provider aliases in incident report", () => {
      const incidentReport = createDeonymizedIncidentReport();
      render(<IncidentReportCard incidentReport={incidentReport} />);

      // Scope to the incident report component
      const incidentSection = screen.getByTestId("incident-report-card");
      const sectionQueries = within(incidentSection);

      // Verify aliases do NOT appear
      expect(sectionQueries.queryByText("cluster-a")).not.toBeInTheDocument();
      expect(sectionQueries.queryByText("cluster-b")).not.toBeInTheDocument();
      expect(sectionQueries.queryByText("namespace-f")).not.toBeInTheDocument();
    });

    it("renders real cluster names in statements", () => {
      const incidentReport = createDeonymizedIncidentReport();
      render(<IncidentReportCard incidentReport={incidentReport} />);

      // Verify real cluster names appear in evidence statements
      expect(screen.getByText(/Warning events observed: 5 in cluster1/)).toBeInTheDocument();
      expect(screen.getByText(/Non-running pods observed: 2 in cluster2/)).toBeInTheDocument();
    });
  });

  describe("OperatorWorklistCard - No Alias Leakage", () => {
    it("renders real cluster context in commands", () => {
      const worklist = createDeonymizedOperatorWorklist();
      render(<OperatorWorklistCard operatorWorklist={worklist} />);

      // Verify real cluster context appears
      expect(
        screen.getByText("kubectl logs -n kube-system -l k8s-app=kubelet --context cluster1")
      ).toBeInTheDocument();
    });

    it("does NOT render aliases in worklist commands", () => {
      const worklist = createDeonymizedOperatorWorklist();
      render(<OperatorWorklistCard operatorWorklist={worklist} />);

      // Scope to the worklist component
      const worklistSection = screen.getByTestId("operator-worklist-card");
      const sectionQueries = within(worklistSection);

      // Verify aliases do NOT appear in commands
      expect(sectionQueries.queryByText(/--context cluster-a/)).not.toBeInTheDocument();
      expect(sectionQueries.queryByText(/--context cluster-b/)).not.toBeInTheDocument();
      expect(sectionQueries.queryByText(/-n namespace-f/)).not.toBeInTheDocument();
    });

    it("renders real cluster names in worklist item 1", () => {
      const worklist = createDeonymizedOperatorWorklist();
      render(<OperatorWorklistCard operatorWorklist={worklist} />);

      // Verify cluster1 appears in first worklist item (page 1)
      expect(screen.getAllByText(/cluster1/).length).toBeGreaterThan(0);
    });
  });
});
