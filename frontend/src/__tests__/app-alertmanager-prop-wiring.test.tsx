/**
 * Smoke test for App -> ExecutionHistoryPanel Alertmanager relevance prop wiring.
 * 
 * This test verifies that the onSubmitAlertmanagerRelevanceFeedback prop is correctly
 * passed from App.tsx to ExecutionHistoryPanel by testing the integration in App.tsx.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import App from "../App";
import { createFetchMock, createStorageMock } from "./fixtures";

const defaultPayloads = {
  "/api/run": {
    runId: "run-123",
    label: "123",
    timestamp: new Date().toISOString(),
    artifacts: [],
    clusterCount: 1,
    proposalCount: 0,
    notificationCount: 0,
    drilldownCount: 0,
    runStats: {
      totalRuns: 1,
      lastRunDurationSeconds: 60,
      p50RunDurationSeconds: 60,
      p95RunDurationSeconds: 60,
      p99RunDurationSeconds: 60,
    },
    nextCheckExecutionHistory: [
      {
        timestamp: new Date().toISOString(),
        clusterLabel: "test-cluster",
        candidateDescription: "Test check",
        commandFamily: "kubectl-logs",
        status: "success",
        durationMs: 100,
        artifactPath: "/artifacts/test.json",
        alertmanagerProvenance: {
          matchedDimensions: ["namespace"],
          matchedValues: { namespace: ["monitoring"] },
          appliedBonus: 5,
          baseBonus: 5,
        },
        // No alertmanagerRelevance - should show feedback control
      },
    ],
    llmStats: {
      scope: "run",
      totalCalls: 10,
      successfulCalls: 9,
      failedCalls: 1,
      p50LatencyMs: 100,
      p95LatencyMs: 200,
      p99LatencyMs: 500,
      lastCallTimestamp: new Date().toISOString(),
      providerBreakdown: [],
    },
    nextCheckQueue: [],
    nextCheckPlan: null,
    plannerAvailability: null,
    diagnosticPack: null,
    diagnosticPackReview: null,
    alertmanagerCompact: null,
    alertmanagerSources: null,
    reviewEnrichment: null,
    reviewEnrichmentStatus: null,
    providerExecution: null,
    deterministicNextChecks: null,
    historicalLlmStats: null,
    llmPolicy: null,
    llmActivity: null,
  },
  "/api/runs": {
    runs: [
      {
        runId: "run-123",
        runLabel: "123",
        timestamp: new Date().toISOString(),
        reviewStatus: "unreviewed",
      },
    ],
    totalCount: 1,
    page: 1,
    pageSize: 10,
  },
  "/api/fleet": {
    clusters: [
      {
        label: "test-cluster",
        context: "test-context",
        clusterClass: "production",
        clusterRole: " workload",
        baselineCohort: "default",
        healthRating: "healthy",
        latestRunTimestamp: new Date().toISOString(),
        topTriggerReason: "none",
        drilldownAvailable: false,
        drilldownTimestamp: null,
      },
    ],
    fleetStatus: { ratingCounts: [{ rating: "healthy", count: 1 }] },
    topProblem: { title: "No issues", detail: "All systems healthy" },
    proposalSummary: { pending: 0, total: 0 },
  },
  "/api/proposals": { proposals: [], statusSummary: [] },
  "/api/notifications": { notifications: [], totalCount: 0 },
  "/api/notifications?limit=50&page=1": { notifications: [], totalCount: 0 },
  "/api/cluster-detail": {
    selectedClusterLabel: "test-cluster",
    findings: [],
    hypotheses: [],
    nextChecks: [],
    artifacts: [],
    drilldownCoverage: [],
    drilldownAvailability: { available: 0, totalClusters: 1, missingClusters: [] },
    assessment: null,
    recommendedAction: null,
    nextCheckPlan: [],
    autoInterpretation: null,
    topProblem: null,
    relatedProposals: [],
    relatedNotifications: [],
  },
  "/api/deterministic-next-check/promote": {
    status: "success",
    summary: "Check promoted",
  },
};

describe("App - Alertmanager relevance prop wiring", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    const storageMock = createStorageMock();
    vi.stubGlobal("localStorage", storageMock);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("ExecutionHistoryPanel receives onSubmitAlertmanagerRelevanceFeedback prop", async () => {
    const mockSubmit = vi.fn().mockResolvedValue(undefined);
    
    // Mock the API to include the callback
    vi.stubGlobal("fetch", createFetchMock({
      ...defaultPayloads,
      "/api/alertmanager-relevance-feedback": mockSubmit,
    }));

    render(<App />);

    // Wait for app to load - look for fleet overview heading
    await waitFor(() => {
      expect(screen.queryByText(/Loading operator data/i)).not.toBeInTheDocument();
    }, { timeout: 5000 });

    // Find the execution history panel
    const execPanel = await screen.findByText(/Check execution review/i);
    expect(execPanel).toBeInTheDocument();

    // Verify that the feedback control link appears when provenance exists
    // This confirms the prop is being passed correctly
    expect(screen.getByText(/Rate Alertmanager relevance/i)).toBeInTheDocument();
  });

  test("feedback control appears when provenance exists and no saved relevance", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));

    render(<App />);

    await waitFor(() => {
      expect(screen.queryByText(/Loading operator data/i)).not.toBeInTheDocument();
    }, { timeout: 5000 });

    // Wait for execution history panel to render
    const execPanel = await screen.findByText(/Check execution review/i);
    expect(execPanel).toBeInTheDocument();

    // Should see the feedback control
    expect(screen.getByText(/Rate Alertmanager relevance/i)).toBeInTheDocument();
  });
});
