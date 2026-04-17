import { render, screen } from "@testing-library/react";
import dayjs from "dayjs";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App, { formatAgeDuration } from "../App";
import type { RunPayload, RunsListPayload } from "../types";
import { createStorageMock, sampleFleet, sampleProposals, sampleNotifications, sampleClusterDetail } from "./fixtures";
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
const createRunsList = (runs: Array<{ runId: string; ageMinutes: number; isLatest?: boolean }>): RunsListPayload => ({
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
  ...sampleFleet, // Use a minimal structure
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

// Mock fetch for controlled test responses
const createFetchMock = (
  runsList: RunsListPayload,
  run: RunPayload
) =>
  vi.fn((input: RequestInfo) => {
    const url = typeof input === "string" ? input : input.url;
    if (url.includes("/api/runs")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        json: () => Promise.resolve(runsList),
      });
    }
    if (url.includes("/api/run")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        json: () => Promise.resolve(run),
      });
    }
    if (url.includes("/api/fleet")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        json: () => Promise.resolve(sampleFleet),
      });
    }
    if (url.includes("/api/proposals")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        json: () => Promise.resolve(sampleProposals),
      });
    }
    if (url.includes("/api/notifications")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        json: () => Promise.resolve(sampleNotifications),
      });
    }
    if (url.includes("/api/cluster-detail")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        json: () => Promise.resolve(sampleClusterDetail),
      });
    }
    return Promise.reject(new Error(`Unexpected fetch: ${url}`));
  });

const renderApp = (runsList: RunsListPayload, run: RunPayload) => {
  vi.stubGlobal("fetch", createFetchMock(runsList, run));
  render(<App />);
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
  test("1. past run selected and fresh -> shows past-run notice", async () => {
    // A run that's 5 minutes old (fresh) but is NOT the latest
    const pastRunId = "run-1";
    const latestRunId = "run-2";
    const runsList = createRunsList([
      { runId: latestRunId, ageMinutes: 3 }, // Latest - fresh
      { runId: pastRunId, ageMinutes: 5 }, // Past - fresh
    ]);
    const run = createRun(5); // Selected run is 5 minutes old

    // Pre-select the past run so App knows to show past-run notice
    localStorage.setItem(SELECTED_RUN_STORAGE_KEY, pastRunId);

    renderApp(runsList, run);
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Should show past-run notice (amber/yellow)
    expect(screen.queryByText(/This is a past run collected/i)).toBeInTheDocument();
    // Should NOT show latest-run warning
    expect(screen.queryByText(/Latest run is.*minutes old/i)).not.toBeInTheDocument();
  });

  test("2. past run selected and stale -> shows past-run notice, not latest-run warning", async () => {
    // A run that's 60 minutes old (stale) and is NOT the latest
    const pastRunId = "run-1";
    const latestRunId = "run-2";
    const runsList = createRunsList([
      { runId: latestRunId, ageMinutes: 30 }, // Latest - stale
      { runId: pastRunId, ageMinutes: 60 }, // Past - stale
    ]);
    const run = createRun(60); // Selected run is 60 minutes old

    // Pre-select the past run so App knows to show past-run notice
    localStorage.setItem(SELECTED_RUN_STORAGE_KEY, pastRunId);

    renderApp(runsList, run);
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Should show past-run notice (amber/yellow)
    expect(screen.queryByText(/This is a past run collected/i)).toBeInTheDocument();
    // Should NOT show latest-run warning
    expect(screen.queryByText(/Latest run is.*minutes old/i)).not.toBeInTheDocument();
  });

  test("3. latest run selected and stale -> shows latest-run warning", async () => {
    // A run that's 60 minutes old (stale) and IS the latest
    const latestRunId = "run-1";
    const runsList = createRunsList([
      { runId: latestRunId, ageMinutes: 60 }, // Latest - stale
    ]);
    const run = createRun(60); // Selected run is 60 minutes old

    // Pre-select the latest run
    localStorage.setItem(SELECTED_RUN_STORAGE_KEY, latestRunId);

    renderApp(runsList, run);
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Should show latest-run warning (red)
    expect(screen.queryByText(/Latest run is.*minutes old/i)).toBeInTheDocument();
    // Should NOT show past-run notice
    expect(screen.queryByText(/This is a past run collected/i)).not.toBeInTheDocument();
  });

  test("4. latest run selected and fresh -> no notice", async () => {
    // A run that's 5 minutes old (fresh) and IS the latest
    const latestRunId = "run-1";
    const runsList = createRunsList([
      { runId: latestRunId, ageMinutes: 5 }, // Latest - fresh
    ]);
    const run = createRun(5); // Selected run is 5 minutes old

    // Pre-select the latest run
    localStorage.setItem(SELECTED_RUN_STORAGE_KEY, latestRunId);

    renderApp(runsList, run);
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Should NOT show any age notice
    expect(screen.queryByText(/This is a past run collected/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Latest run is.*minutes old/i)).not.toBeInTheDocument();
  });
});
