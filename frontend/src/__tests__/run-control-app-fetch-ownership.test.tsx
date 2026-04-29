/**
 * run-control-app-fetch-ownership.test.tsx
 *
 * Phase 4: Verifies App-level selected-run fetch ownership guard.
 *
 * Test intent:
 * - Render App with a run-aware fetch mock.
 * - Persist selectedRunId in localStorage before render.
 * - Assert App correctly displays the selected run state.
 * - Assert selected run detail fetch happens exactly once on boot.
 *
 * Expected invariant:
 * - During initial App boot with a persisted selectedRunId, selected-run
 *   detail fetch for that persisted run happens exactly once.
 * - This test should FAIL if a persisted selected run never fetches
 *   its detail payload (Phase 3/4 gap).
 * - This test should FAIL if a second selected-run /api/run path is
 *   reintroduced (duplicate fetch regression).
 *
 * The existing useRunControl.test.tsx already verifies that:
 * - RunControl fetches /api/run exactly once for selectRun() calls
 * - No duplicate fetches occur for the same run
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";
import App, { SELECTED_RUN_STORAGE_KEY } from "../App";
import { makeRunWithOverrides } from "./fixtures";

// Mock API module - hoisted to top
const mockFetchRun = vi.fn();
const mockFetchRunsList = vi.fn();
const mockFetchFleet = vi.fn();
const mockFetchProposals = vi.fn();
const mockFetchNotifications = vi.fn();
const mockFetchClusterDetail = vi.fn();
const mockSubmitUsefulnessFeedback = vi.fn();
const mockExecuteNextCheckCandidate = vi.fn();
const mockApproveNextCheckCandidate = vi.fn();
const mockRunBatchExecution = vi.fn();
const mockSubmitAlertmanagerRelevanceFeedback = vi.fn();

vi.mock("../api", () => ({
  fetchRun: (...args: unknown[]) => mockFetchRun(...args),
  fetchRunsList: (...args: unknown[]) => mockFetchRunsList(...args),
  fetchFleet: (...args: unknown[]) => mockFetchFleet(...args),
  fetchProposals: (...args: unknown[]) => mockFetchProposals(...args),
  fetchNotifications: (...args: unknown[]) => mockFetchNotifications(...args),
  fetchClusterDetail: (...args: unknown[]) => mockFetchClusterDetail(...args),
  submitUsefulnessFeedback: (...args: unknown[]) => mockSubmitUsefulnessFeedback(...args),
  executeNextCheckCandidate: (...args: unknown[]) => mockExecuteNextCheckCandidate(...args),
  approveNextCheckCandidate: (...args: unknown[]) => mockApproveNextCheckCandidate(...args),
  runBatchExecution: (...args: unknown[]) => mockRunBatchExecution(...args),
  submitAlertmanagerRelevanceFeedback: (...args: unknown[]) => mockSubmitAlertmanagerRelevanceFeedback(...args),
}));

describe("run-control-app-fetch-ownership", () => {
  const PERSISTED_RUN_ID = "run-past-123";

  // Storage mock helper
  const createStorageMock = () => {
    const store: Record<string, string> = {};
    return {
      getItem: (key: string) => (key in store ? store[key] : null),
      setItem: (key: string, value: string) => {
        store[key] = value;
      },
      removeItem: (key: string) => {
        delete store[key];
      },
      clear: () => {
        Object.keys(store).forEach((k) => delete store[k]);
      },
    };
  };

  beforeEach(() => {
    vi.clearAllMocks();

    // Set up mock implementations
    mockFetchRun.mockResolvedValue(
      makeRunWithOverrides({ runId: PERSISTED_RUN_ID })
    );

    // Note: runs are sorted by timestamp descending, so "Latest" (11:00) comes first
    mockFetchRunsList.mockResolvedValue({
      runs: [
        { runId: "run-latest", runLabel: "Latest", timestamp: "2026-04-07T11:00:00Z", clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" as const, reviewDownloadPath: null, batchExecutable: false, batchEligibleCount: 0 },
        { runId: PERSISTED_RUN_ID, runLabel: "Past Run", timestamp: "2026-04-07T10:00:00Z", clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" as const, reviewDownloadPath: null, batchExecutable: false, batchEligibleCount: 0 },
      ],
      totalCount: 2,
      executionCountsComplete: true,
    });

    mockFetchFleet.mockResolvedValue({
      topProblem: { title: "Test", detail: "Test cluster issue" },
      proposalSummary: { total: 5, pending: 3 },
      fleetStatus: { ratingCounts: [{ rating: "Healthy", count: 2 }, { rating: "Degraded", count: 1 }] },
      clusters: [
        { label: "cluster-a", context: "prod", clusterClass: "standard", clusterRole: "worker", healthRating: "Degraded", latestRunTimestamp: "2026-04-07T10:00:00Z", topTriggerReason: "Memory pressure", drilldownAvailable: true, drilldownTimestamp: "2026-04-07T10:00:00Z" },
        { label: "cluster-b", context: "prod", clusterClass: "standard", clusterRole: "worker", healthRating: "Healthy", latestRunTimestamp: "2026-04-07T10:00:00Z", topTriggerReason: null, drilldownAvailable: true, drilldownTimestamp: "2026-04-07T10:00:00Z" },
      ],
    });

    mockFetchProposals.mockResolvedValue({
      proposals: [],
      total: 0,
      page: 1,
      limit: 50,
      total_pages: 1,
    });

    mockFetchNotifications.mockResolvedValue({ notifications: [], total: 0, page: 1, limit: 50, total_pages: 1 });
    mockFetchClusterDetail.mockResolvedValue({
      selectedClusterLabel: "cluster-a",
      selectedClusterContext: "prod",
      assessment: { healthRating: "Degraded", missingEvidence: [], probableLayer: "control-plane", overallConfidence: "High", artifactPath: "/test", snapshotPath: "/test" },
      findings: [],
      hypotheses: [],
      nextChecks: [],
      recommendedAction: { actionType: "change", description: "Test", references: [], safetyLevel: "safe" },
      drilldownAvailability: { totalClusters: 1, available: 1, missing: 0, missingClusters: [] },
      drilldownCoverage: [],
      relatedProposals: [],
      relatedNotifications: [],
      artifacts: [],
      nextCheckPlan: [],
      topProblem: { title: "Test", detail: "Test" },
    });
    mockSubmitUsefulnessFeedback.mockResolvedValue(undefined);
    mockExecuteNextCheckCandidate.mockResolvedValue({ status: "success", summary: "OK" });
    mockApproveNextCheckCandidate.mockResolvedValue({ status: "success", summary: "OK" });
    mockRunBatchExecution.mockResolvedValue({ status: "success", summary: "OK" });
    mockSubmitAlertmanagerRelevanceFeedback.mockResolvedValue(undefined);

    // Set up localStorage with persisted selected run
    const storageMock = createStorageMock();
    storageMock.setItem(SELECTED_RUN_STORAGE_KEY, PERSISTED_RUN_ID);
    vi.stubGlobal("localStorage", storageMock);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // --------------------------------------------------------------------------
  // Test: App renders persisted selected run correctly in header
  // --------------------------------------------------------------------------
  it("App renders persisted selected run correctly in the header", async () => {
    render(<App />);

    // Wait for the app shell to render (proves the critical path loaded)
    await waitFor(() => {
      const appShell = document.querySelector(".app-shell");
      expect(appShell).toBeTruthy();
    });

    // Wait for the hero section with run info to render
    await waitFor(() => {
      const heroRun = document.querySelector(".hero-run");
      expect(heroRun).toBeTruthy();
    });

    // Verify the selected run ID is shown (proves RunControl populated the selection)
    const heroRunId = document.querySelector(".hero-run-id");
    expect(heroRunId).toBeTruthy();
    expect(heroRunId?.textContent).toContain(PERSISTED_RUN_ID);

    // Verify the run label is shown
    const heroTitle = document.querySelector(".hero-run-title");
    expect(heroTitle?.textContent).toContain("Past Run");

    // Guard test: selected-run detail fetch happens exactly once during boot
    // This assertion will FAIL if the bug exists (persisted selection not fetched)
    await waitFor(() => {
      expect(mockFetchRun).toHaveBeenCalledWith(PERSISTED_RUN_ID);
    });

    // Verify exactly one fetch for the persisted run (no duplicates)
    expect(
      mockFetchRun.mock.calls.filter(([runId]) => runId === PERSISTED_RUN_ID)
    ).toHaveLength(1);
  });

  // --------------------------------------------------------------------------
  // Test: RunControl receives the persisted selected run ID and displays "Past run" badge
  // --------------------------------------------------------------------------
  it("RunControl displays the selected run with Past run badge", async () => {
    render(<App />);

    // Wait for app to fully settle
    await waitFor(() => {
      const appShell = document.querySelector(".app-shell");
      expect(appShell).toBeTruthy();
    });

    // Verify the selected run ID is shown
    const heroRunId = document.querySelector(".hero-run-id");
    expect(heroRunId?.textContent).toContain(PERSISTED_RUN_ID);

    // Verify the "Past run" badge is shown (proves the run is not the latest)
    // The selected run is NOT the latest (run-latest comes first in the sorted list)
    const pastRunBadge = document.querySelector(".run-badge--past");
    expect(pastRunBadge).toBeTruthy();
    expect(pastRunBadge?.textContent).toContain("Past run");

    // Guard test: selected-run detail fetch happens exactly once during boot
    // This assertion will FAIL if the bug exists (persisted selection not fetched)
    await waitFor(() => {
      expect(mockFetchRun).toHaveBeenCalledWith(PERSISTED_RUN_ID);
    });

    // Verify exactly one fetch for the persisted run (no duplicates)
    expect(
      mockFetchRun.mock.calls.filter(([runId]) => runId === PERSISTED_RUN_ID)
    ).toHaveLength(1);
  });
});
