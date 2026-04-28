import { render, screen, waitFor, act } from "@testing-library/react";
import dayjs from "dayjs";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App, { formatAgeDuration } from "../App";
import type { RunPayload, RunsListPayload } from "../types";
import { createStorageMock, createFetchMock, sampleFleet, sampleProposals, sampleNotifications, sampleClusterDetail } from "./fixtures";
import { SELECTED_RUN_STORAGE_KEY } from "../App";

const minsAgo = (minutes: number) => dayjs().subtract(minutes, "minute").toISOString();

let storageMock: ReturnType<typeof createStorageMock>;

beforeEach(() => {
  storageMock = createStorageMock();
  vi.stubGlobal("localStorage", storageMock);
});

afterEach(() => {
  vi.restoreAllMocks();
});

// Helper to create a runs list with controlled timestamps
const createRunsList = (runs: Array<{ runId: string; ageMinutes: number }>): RunsListPayload => ({
  runs: runs.map((r, idx) => ({
    runId: r.runId,
    runLabel: `Run ${idx + 1}`,
    timestamp: minsAgo(r.ageMinutes),
    clusterCount: 2,
    triaged: idx === 0,
    executionCount: 0,
    reviewedCount: 0,
    reviewStatus: "no-executions" as const,
  })),
  totalCount: runs.length,
});

// Helper to create a run payload with a specific timestamp
const createRun = (ageMinutes: number): RunPayload => ({
  ...sampleFleet,
  runId: "test-run",
  label: "Test run",
  timestamp: minsAgo(ageMinutes),
  collectorVersion: "collector:v1.0",
  clusterCount: 2,
  drilldownCount: 0,
  proposalCount: 0,
  externalAnalysisCount: 0,
  notificationCount: 0,
  artifacts: [],
  runStats: {
    lastRunDurationSeconds: 30,
    totalRuns: 1,
    p50RunDurationSeconds: 30,
    p95RunDurationSeconds: 30,
    p99RunDurationSeconds: 30,
  },
  llmStats: {
    totalCalls: 0,
    successfulCalls: 0,
    failedCalls: 0,
    lastCallTimestamp: null,
    p50LatencyMs: 0,
    p95LatencyMs: 0,
    p99LatencyMs: 0,
    providerBreakdown: [],
    scope: "current_run",
  },
  historicalLlmStats: null,
  llmActivity: null,
  llmPolicy: null,
  reviewEnrichment: null,
  reviewEnrichmentStatus: null,
  providerExecution: null,
  diagnosticPack: null,
  diagnosticPackReview: null,
  deterministicNextChecks: null,
  nextCheckPlan: null,
  nextCheckQueue: [],
  nextCheckQueueExplanation: null,
  nextCheckExecutionHistory: [],
  plannerAvailability: null,
});

// Helper to render app with proper act() wrapping
const renderApp = async (runsList: RunsListPayload, run: RunPayload) => {
  const payloads: Record<string, unknown> = {
    "/api/runs": runsList,
    "/api/run": run,
    "/api/fleet": sampleFleet,
    "/api/proposals": sampleProposals,
    "/api/notifications": sampleNotifications,
    "/api/cluster-detail": sampleClusterDetail,
  };
  vi.stubGlobal("fetch", createFetchMock(payloads));
  await act(async () => {
    render(<App />);
  });
};

describe("formatAgeDuration", () => {
  test.each([
    [5, "5 minutes"],
    [1, "1 minute"],
    [59, "59 minutes"],
    [60, "1 hour"],
    [61, "1 hour 1 minute"],
    [119, "1 hour 59 minutes"],
    [120, "2 hours"],
    [121, "2 hours 1 minute"],
    [1439, "23 hours 59 minutes"],
    [1440, "1 day"],
    [1441, "1 day 1 minute"],
    [1500, "1 day 1 hour"],
    [1501, "1 day 1 hour 1 minute"],
    [2880, "2 days"],
  ])("formats %d minutes as '%s'", (minutes, expected) => {
    expect(formatAgeDuration(minutes)).toBe(expected);
  });
});

describe("Past-run notice UI", () => {
  // Suite-local timeout: 15s for async run-data loading

  beforeEach(() => {
    vi.stubGlobal("setInterval", vi.fn(() => 123));
    vi.stubGlobal("clearInterval", vi.fn());
  });

  test("1. past selected + fresh -> shows past-run notice, not latest warning", async () => {
    // Past run (run-1) is selected, latest is run-2
    const pastRunId = "run-1";
    const runsList = createRunsList([
      { runId: "run-2", ageMinutes: 3 }, // Latest
      { runId: pastRunId, ageMinutes: 5 }, // Past
    ]);
    const run = createRun(5);

    localStorage.setItem(SELECTED_RUN_STORAGE_KEY, pastRunId);
    await renderApp(runsList, run);
    
    // Wait for shell to render
    await screen.findByRole("heading", { name: /Fleet overview/i });
    
    // Wait for run detail to load and show past-run notice
    await waitFor(() => {
      expect(screen.queryByText(/This is a past run/)).toBeInTheDocument();
    }, { timeout: 10000 });
    
    // Assert past-run notice is visible
    expect(screen.getByText(/This is a past run/)).toBeInTheDocument();
    // Assert latest warning is NOT visible
    expect(screen.queryByText(/Latest run is.*old/i)).not.toBeInTheDocument();
  });

  test("2. past selected + stale -> shows past-run notice, not latest warning", async () => {
    // Past run (run-1) is selected, it's 60 min old (stale)
    const pastRunId = "run-1";
    const runsList = createRunsList([
      { runId: "run-2", ageMinutes: 30 }, // Latest - stale
      { runId: pastRunId, ageMinutes: 60 }, // Past - stale
    ]);
    const run = createRun(60);

    localStorage.setItem(SELECTED_RUN_STORAGE_KEY, pastRunId);
    await renderApp(runsList, run);
    
    // Wait for shell to render
    await screen.findByRole("heading", { name: /Fleet overview/i });
    
    // Wait for run detail to load
    await waitFor(() => {
      expect(screen.queryByText(/This is a past run/)).toBeInTheDocument();
    }, { timeout: 10000 });
    
    // Assert past-run notice is visible
    expect(screen.getByText(/This is a past run/)).toBeInTheDocument();
    // Assert latest warning is NOT visible
    expect(screen.queryByText(/Latest run is.*old/i)).not.toBeInTheDocument();
  });

  test("3. latest selected + stale -> shows latest warning, not past notice", async () => {
    // Only one run, it's the latest, and it's 60 min old (stale)
    const latestRunId = "run-1";
    const runsList = createRunsList([
      { runId: latestRunId, ageMinutes: 60 }, // Latest - stale
    ]);
    const run = createRun(60);

    localStorage.setItem(SELECTED_RUN_STORAGE_KEY, latestRunId);
    await renderApp(runsList, run);
    
    // Wait for shell to render
    await screen.findByRole("heading", { name: /Fleet overview/i });
    
    // Wait for run detail to load and show latest warning
    await waitFor(() => {
      expect(screen.queryByText(/Latest run is.*old/i)).toBeInTheDocument();
    }, { timeout: 10000 });
    
    // Assert latest warning is visible
    expect(screen.getByText(/Latest run is.*old/i)).toBeInTheDocument();
    // Assert past-run notice is NOT visible
    expect(screen.queryByText(/This is a past run/)).not.toBeInTheDocument();
  });

  test("4. latest selected + fresh -> shows neither notice", async () => {
    // Only one run, it's the latest, and it's 5 min old (fresh)
    const latestRunId = "run-1";
    const runsList = createRunsList([
      { runId: latestRunId, ageMinutes: 5 }, // Latest - fresh
    ]);
    const run = createRun(5);

    localStorage.setItem(SELECTED_RUN_STORAGE_KEY, latestRunId);
    await renderApp(runsList, run);
    
    // Wait for shell to render
    await screen.findByRole("heading", { name: /Fleet overview/i });
    
    // Wait for run data to load - use the shared helper approach
    await waitFor(() => {
      // When run data loads, the "Loading selected run" placeholder should be gone
      expect(screen.queryByText(/Loading selected run/i)).not.toBeInTheDocument();
    }, { timeout: 15000 });
    
    // Assert neither notice is visible
    expect(screen.queryByText(/This is a past run/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Latest run is.*old/i)).not.toBeInTheDocument();
  });
}, 15000);
