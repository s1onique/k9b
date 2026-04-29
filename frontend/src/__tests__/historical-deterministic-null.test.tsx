/**
 * Regression test: Historical runs with null deterministicNextChecks but valid queue
 * 
 * Tests that:
 * 1. Latest runs show deterministic checks when available
 * 2. Historical runs with deterministicNextChecks=null still show the Work list
 * 3. The empty state message doesn't contradict Work list visibility
 * 4. Queue panel is visible even when deterministic checks are null
 */

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App from "../App";
import type { RunPayload } from "../types";
import {
  createFetchMock,
  createStorageMock,
  makeRunWithOverrides,
  sampleClusterDetail,
  sampleFleet,
  sampleNotifications,
  sampleProposals,
} from "./fixtures";

// Helper to get the queue panel from the screen
const getQueuePanel = async () => {
  const heading = await screen.findByRole("heading", { name: /Work list/i });
  const queuePanel = heading.closest(".next-check-queue-panel");
  if (!queuePanel) {
    throw new Error("Queue panel is not rendered");
  }
  return within(queuePanel);
};

// Helper to get the deterministic panel
const getDeterministicPanel = async () => {
  const panel = document.getElementById("deterministic-next-checks");
  if (!panel) {
    throw new Error("Deterministic panel not rendered");
  }
  return within(panel);
};

// Create a historical run payload with null deterministicNextChecks but valid queue
const createHistoricalRunPayload = (runId: string, queueItems: RunPayload["nextCheckQueue"]): RunPayload => {
  const baseRun = makeRunWithOverrides({});
  return {
    ...baseRun,
    runId,
    label: `Historical run ${runId}`,
    timestamp: "2026-04-01T12:00:00Z",
    deterministicNextChecks: null,  // Explicitly null for historical runs
    nextCheckQueue: queueItems,
    nextCheckQueueExplanation: {
      status: "ok",
      clusterState: {
        degradedClusterCount: 1,
        degradedClusterLabels: ["cluster-a"],
        deterministicNextCheckCount: 0,
        deterministicClusterCount: 0,
        drilldownReadyCount: 0,
      },
      candidateAccounting: {
        generated: queueItems.length,
        safe: 1,
        approvalNeeded: queueItems.length - 1,
        duplicate: 0,
        completed: 0,
        staleOrphaned: 0,
        orphanedApprovals: 0,
      },
      deterministicNextChecksAvailable: false,
      recommendedNextActions: [],
    },
  };
};

// Create a latest run payload with valid deterministicNextChecks
const createLatestRunPayload = (queueItems: RunPayload["nextCheckQueue"]): RunPayload => {
  const baseRun = makeRunWithOverrides({});
  return {
    ...baseRun,
    runId: "latest-run",
    label: "Latest run",
    timestamp: new Date().toISOString(),
    deterministicNextChecks: {
      clusterCount: 1,
      totalNextCheckCount: 3,
      clusters: [
        {
          label: "cluster-a",
          context: "prod",
          topProblem: "High CPU",
          deterministicNextCheckCount: 3,
          deterministicNextCheckSummaries: [
            {
              description: "Collect kubelet logs",
              owner: "platform",
              method: "kubectl logs",
              evidenceNeeded: ["logs output"],
              priorityScore: 90,
              workstream: "incident" as const,
              urgency: "high" as const,
              isPrimaryTriage: true,
              whyNow: "Immediate triage for High CPU",
            },
            {
              description: "Review node conditions",
              owner: "platform",
              method: "kubectl get nodes",
              evidenceNeeded: ["node status"],
              priorityScore: 70,
              workstream: "evidence" as const,
              urgency: "medium" as const,
              isPrimaryTriage: false,
              whyNow: "Gather additional evidence",
            },
            {
              description: "Compare baseline parity",
              owner: "platform engineer",
              method: "kubectl get helmrelease",
              evidenceNeeded: ["helm release list"],
              priorityScore: 30,
              workstream: "drift" as const,
              urgency: "low" as const,
              isPrimaryTriage: false,
              whyNow: "Baseline drift follow-up",
            },
          ],
          drilldownAvailable: true,
          assessmentArtifactPath: "/artifacts/assessment.json",
          drilldownArtifactPath: "/artifacts/drilldown.json",
        },
      ],
    },
    nextCheckQueue: queueItems,
  };
};

// Sample queue items for testing
const sampleQueueItems: RunPayload["nextCheckQueue"] = [
  {
    candidateId: "candidate-1",
    candidateIndex: 0,
    description: "Collect kubelet logs for web deployment",
    targetCluster: "cluster-a",
    priorityLabel: "primary",
    suggestedCommandFamily: "kubectl-logs",
    safeToAutomate: true,
    requiresOperatorApproval: false,
    approvalState: "not-required",
    executionState: "unexecuted",
    outcomeStatus: "not-used",
    latestArtifactPath: null,
    sourceReason: "warning_event_threshold",
    expectedSignal: "logs",
    normalizationReason: "selection_label",
    safetyReason: "known_command",
    approvalReason: null,
    duplicateReason: null,
    blockingReason: null,
    targetContext: "cluster-a · web deployment",
    commandPreview: "kubectl logs deployment/web --context cluster-a",
    planArtifactPath: "/artifacts/plan.json",
    queueStatus: "safe-ready",
  },
  {
    candidateId: "candidate-2",
    candidateIndex: 1,
    description: "Describe diag CRD for control plane",
    targetCluster: null,
    priorityLabel: "secondary",
    suggestedCommandFamily: "kubectl-describe",
    safeToAutomate: false,
    requiresOperatorApproval: true,
    approvalState: "approval-required",
    executionState: "unexecuted",
    outcomeStatus: "approval-required",
    latestArtifactPath: null,
    sourceReason: "diag-availability",
    expectedSignal: "events",
    normalizationReason: "selection_default",
    safetyReason: "unknown_command",
    approvalReason: "unknown_command",
    duplicateReason: null,
    blockingReason: "unknown_command",
    targetContext: "cluster-b · diag CRD",
    commandPreview: "kubectl describe diag customresourcedefinition --context cluster-b",
    planArtifactPath: "/artifacts/plan.json",
    queueStatus: "approval-needed",
    priorityRationale: "Approval required before execution",
  },
];

let setIntervalSpy: ReturnType<typeof vi.fn>;
let clearIntervalSpy: ReturnType<typeof vi.fn>;
let storageMock: ReturnType<typeof createStorageMock>;

beforeEach(() => {
  setIntervalSpy = vi.fn(() => 123);
  clearIntervalSpy = vi.fn();
  vi.stubGlobal("setInterval", setIntervalSpy);
  vi.stubGlobal("clearInterval", clearIntervalSpy);
  storageMock = createStorageMock();
  vi.stubGlobal("localStorage", storageMock);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Historical runs with null deterministicNextChecks", () => {
  test("latest run shows deterministic checks when available", async () => {
    const latestPayload = createLatestRunPayload(sampleQueueItems);
    const payloads = {
      "/api/run": latestPayload,
      "/api/runs": {
        runs: [
          { runId: "latest-run", runLabel: "Latest run", timestamp: new Date().toISOString(), clusterCount: 1, triaged: true, executionCount: 0, reviewedCount: 0, reviewStatus: "no-executions" },
        ],
        totalCount: 1,
      },
      "/api/fleet": sampleFleet,
      "/api/proposals": sampleProposals,
      "/api/notifications": sampleNotifications,
      "/api/notifications?limit=50&page=1": sampleNotifications,
      "/api/cluster-detail": sampleClusterDetail,
    };
    
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);
    
    await screen.findByRole("heading", { name: /Fleet overview/i });
    
    // Wait for run data to load, then query panel content directly from screen
    // Use findAllByText since multiple elements may contain "Collect kubelet logs" (check title + queue item)
    const elements = await screen.findAllByText(/Collect kubelet logs/i);
    expect(elements.length).toBeGreaterThan(0);
    
    // Should NOT show empty state
    expect(screen.queryByText(/No evidence-based checks are available/i)).not.toBeInTheDocument();
  });

  test("historical run with null deterministic shows empty state but queue is visible", async () => {
    const historicalPayload = createHistoricalRunPayload("historical-run", sampleQueueItems);
    const payloads = {
      "/api/run": historicalPayload,
      "/api/runs": {
        runs: [
          { runId: "historical-run", runLabel: "Historical run", timestamp: "2026-04-01T12:00:00Z", clusterCount: 1, triaged: true, executionCount: 0, reviewedCount: 0, reviewStatus: "no-executions" },
        ],
        totalCount: 1,
      },
      "/api/fleet": sampleFleet,
      "/api/proposals": sampleProposals,
      "/api/notifications": sampleNotifications,
      "/api/notifications?limit=50&page=1": sampleNotifications,
      "/api/cluster-detail": sampleClusterDetail,
    };
    
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);
    
    await screen.findByRole("heading", { name: /Fleet overview/i });
    
    // Wait for data to load first
    await waitFor(() => {
      expect(document.getElementById("deterministic-next-checks")).toBeInTheDocument();
    });
    
    // Now get the within-scoped panel after data has loaded
    const deterministicPanel = await getDeterministicPanel();
    await waitFor(() => {
      expect(deterministicPanel.getByText(/No evidence-based checks are available for this run/i)).toBeInTheDocument();
      // Should point to Work list
      expect(deterministicPanel.getByText(/Use the Work list below for the full queue of planner candidates/i)).toBeInTheDocument();
    });
    
    // Queue panel should still be visible with items
    const queuePanel = await getQueuePanel();
    const queueItems = queuePanel.getAllByRole("article");
    expect(queueItems.length).toBe(2);  // Both queue items should be visible
  });

  test("historical run queue is visible when deterministic panel shows empty state", async () => {
    const historicalPayload = createHistoricalRunPayload("historical-run-2", sampleQueueItems);
    const payloads = {
      "/api/run": historicalPayload,
      "/api/runs": {
        runs: [
          { runId: "historical-run-2", runLabel: "Historical run 2", timestamp: "2026-03-15T12:00:00Z", clusterCount: 1, triaged: true, executionCount: 0, reviewedCount: 0, reviewStatus: "no-executions" },
        ],
        totalCount: 1,
      },
      "/api/fleet": sampleFleet,
      "/api/proposals": sampleProposals,
      "/api/notifications": sampleNotifications,
      "/api/notifications?limit=50&page=1": sampleNotifications,
      "/api/cluster-detail": sampleClusterDetail,
    };
    
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);
    
    await screen.findByRole("heading", { name: /Fleet overview/i });
    
    // Wait for queue items to load (use waitFor since they may appear after initial render)
    await waitFor(() => {
      const queueItems = document.querySelectorAll("article");
      expect(queueItems.length).toBeGreaterThanOrEqual(2);
    }, { timeout: 5000 });
    
    // Verify queue panel heading is visible
    const queuePanel = await getQueuePanel();
    
    // Verify first queue item is visible
    expect(queuePanel.getByText(/Collect kubelet logs for web deployment/i)).toBeInTheDocument();
    
    // Verify second queue item (approval needed) is visible
    expect(queuePanel.getByText(/Describe diag CRD for control plane/i)).toBeInTheDocument();
    
    // Verify deterministic panel shows empty state
    const deterministicPanel = await getDeterministicPanel();
    await waitFor(() => {
      expect(deterministicPanel.getByText(/No evidence-based checks are available for this run/i)).toBeInTheDocument();
    });
  });

  test("switching from latest to historical run preserves queue visibility", async () => {
    const latestPayload = createLatestRunPayload(sampleQueueItems);
    const historicalPayload = createHistoricalRunPayload("historical-run-3", sampleQueueItems);
    
    // Create a mock that returns different data based on run_id, using sample fixtures for others
    const smartMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];
      const params = new URLSearchParams(url.split("?")[1] || "");
      const runId = params.get("run_id");
      
      // Handle /api/runs
      if (base === "/api/runs") {
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve({
            runs: [
              { runId: "latest-run", runLabel: "Latest run", timestamp: new Date().toISOString(), clusterCount: 1, triaged: true, executionCount: 0, reviewedCount: 0, reviewStatus: "no-executions" },
              { runId: "historical-run-3", runLabel: "Historical run 3", timestamp: "2026-03-01T12:00:00Z", clusterCount: 1, triaged: true, executionCount: 0, reviewedCount: 0, reviewStatus: "no-executions" },
            ],
            totalCount: 2,
          }),
        });
      }
      
      // Handle /api/run
      if (base === "/api/run") {
        if (runId === "historical-run-3") {
          return Promise.resolve({
            ok: true, status: 200, statusText: "OK",
            json: () => Promise.resolve(historicalPayload),
          });
        }
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve(latestPayload),
        });
      }
      
      // Use sample fixtures for all other endpoints
      const samplePayloads = {
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
        "/api/notifications?limit=50&page=1": sampleNotifications,
        "/api/cluster-detail": sampleClusterDetail,
      };
      
      const payload = samplePayloads[base] ?? samplePayloads[url];
      if (payload) {
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve(payload),
        });
      }
      
      return Promise.resolve({
        ok: true, status: 200, statusText: "OK",
        json: () => Promise.resolve({}),
      });
    });
    
    vi.stubGlobal("fetch", smartMock);
    const user = userEvent.setup();
    render(<App />);
    
    await screen.findByRole("heading", { name: /Fleet overview/i });
    
    // Initially on latest run - wait for deterministic checks to appear
    // Use findAllByText since multiple elements may contain "Collect kubelet logs"
    await waitFor(() => {
      const elements = screen.getAllByText(/Collect kubelet logs/i);
      expect(elements.length).toBeGreaterThan(0);
    });
    
    // Queue panel should be visible
    const queuePanel = await getQueuePanel();
    expect(queuePanel.getAllByRole("article").length).toBe(2);
    
    // Switch to historical run
    const historicalRow = document.querySelector('.run-row[data-run-id="historical-run-3"]');
    expect(historicalRow).not.toBeNull();
    
    await act(async () => {
      await user.click(historicalRow!);
    });
    
    // Deterministic panel should now show empty state
    await waitFor(() => {
      expect(screen.getByText(/No evidence-based checks are available for this run/i)).toBeInTheDocument();
    });
    
    // Queue panel should STILL be visible with items
    const updatedQueuePanel = await getQueuePanel();
    expect(updatedQueuePanel.getAllByRole("article").length).toBe(2);
  });
});
