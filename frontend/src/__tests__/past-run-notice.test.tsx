import { render, screen, waitFor } from "@testing-library/react";
import dayjs from "dayjs";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App, { formatAgeDuration } from "../App";
import type { RunPayload, RunsListPayload } from "../types";
import { createStorageMock, sampleFleet, sampleProposals, sampleNotifications, sampleClusterDetail, makeRunWithOverrides } from "./fixtures";
import { SELECTED_RUN_STORAGE_KEY } from "../App";

const minsAgo = (minutes: number) => dayjs().subtract(minutes, "minute").toISOString();

let storageMock: ReturnType<typeof createStorageMock>;

beforeEach(() => {
  storageMock = createStorageMock();
  vi.stubGlobal("localStorage", storageMock);
  vi.stubGlobal("setInterval", vi.fn(() => 123));
  vi.stubGlobal("clearInterval", vi.fn());
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
const createRun = (runId: string, ageMinutes: number): RunPayload => {
  const run = makeRunWithOverrides({});
  return {
    ...run,
    runId,
    label: runId,
    timestamp: minsAgo(ageMinutes),
  };
};

/**
 * Run-aware fetch mock that parses /api/run?run_id=<id> and returns the correct payload.
 * This is critical for the past-run notice tests because the RunControl flow
 * requests /api/run?run_id=<selectedRunId> after reading localStorage.
 */
const createRunAwareFetchMock = (runsList: RunsListPayload) => {
  return vi.fn((input: RequestInfo | URL) => {
    const rawUrl = typeof input === "string" ? input : input.toString();
    const url = new URL(rawUrl, "http://localhost");
    const path = url.pathname;

    // Handle /api/run with query params
    if (path === "/api/run") {
      const runId = url.searchParams.get("run_id") ?? runsList.runs[0]?.runId;
      const runEntry = runsList.runs.find((r) => r.runId === runId);
      
      if (!runEntry || !runId) {
        return Promise.resolve({
          ok: false,
          status: 404,
          statusText: "Not Found",
          json: () => Promise.resolve({ error: "run not found" }),
        });
      }

      const ageMinutes = Math.max(
        0,
        Math.floor(dayjs().diff(dayjs(runEntry.timestamp), "minute"))
      );

      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        json: () => Promise.resolve(createRun(runId, ageMinutes)),
      });
    }

    // Handle other endpoints by pathname
    const payloads: Record<string, unknown> = {
      "/api/runs": runsList,
      "/api/fleet": sampleFleet,
      "/api/proposals": sampleProposals,
      "/api/notifications": sampleNotifications,
      "/api/notifications?limit=50&page=1": sampleNotifications,
      "/api/cluster-detail": sampleClusterDetail,
    };

    const payload = payloads[path];
    if (payload !== undefined) {
      return makeFetchResponse(payload);
    }

    // Also check full URL for exact matches
    const exactPayload = payloads[rawUrl];
    if (exactPayload !== undefined) {
      return makeFetchResponse(exactPayload);
    }

    return Promise.reject(new Error(`Unexpected fetch ${rawUrl}`));
  });
};

// Helper to render app with run-aware mock
const renderApp = async (runsList: RunsListPayload, selectedRunId: string) => {
  const fetchMock = createRunAwareFetchMock(runsList);
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  return fetchMock; // Return for assertion if needed
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

// Phase 3: RunControl integration tests for past-run notice UI.
// Tests verify the historical-vs-latest semantic boundary at the App level.
describe("Past-run notice UI", () => {
  // Suite-local timeout: 15s for async run-data loading

  test("1. past selected + fresh -> shows past-run notice, not latest warning", async () => {
    // Past run (run-1) is selected, latest is run-2
    const pastRunId = "run-1";
    const latestRunId = "run-2";
    const runsList = createRunsList([
      { runId: latestRunId, ageMinutes: 3 }, // Latest
      { runId: pastRunId, ageMinutes: 5 }, // Past
    ]);

    localStorage.setItem(SELECTED_RUN_STORAGE_KEY, pastRunId);
    const fetchMock = await renderApp(runsList, pastRunId);
    
    // Wait for shell to render (Fleet overview heading)
    await screen.findByRole("heading", { name: /Fleet overview/i });
    
    // Wait for run detail to load and show past-run notice
    // The notice should appear when the historical run is selected
    await waitFor(() => {
      const pastRunNotice = screen.queryByText(/past run/i);
      expect(pastRunNotice).toBeInTheDocument();
    }, { timeout: 10000 });
    
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

    localStorage.setItem(SELECTED_RUN_STORAGE_KEY, pastRunId);
    await renderApp(runsList, pastRunId);
    
    // Wait for shell to render
    await screen.findByRole("heading", { name: /Fleet overview/i });
    
    // Wait for run detail to load
    await waitFor(() => {
      const pastRunNotice = screen.queryByText(/past run/i);
      expect(pastRunNotice).toBeInTheDocument();
    }, { timeout: 10000 });
    
    // Assert latest warning is NOT visible (historical run takes precedence)
    expect(screen.queryByText(/Latest run is.*old/i)).not.toBeInTheDocument();
  });

  test("3. latest selected + stale -> shows latest warning, not past notice", async () => {
    // Only one run, it's the latest, and it's 60 min old (stale)
    const latestRunId = "run-1";
    const runsList = createRunsList([
      { runId: latestRunId, ageMinutes: 60 }, // Latest - stale
    ]);

    localStorage.setItem(SELECTED_RUN_STORAGE_KEY, latestRunId);
    await renderApp(runsList, latestRunId);
    
    // Wait for shell to render
    await screen.findByRole("heading", { name: /Fleet overview/i });
    
    // Wait for run detail to load and show latest warning
    await waitFor(() => {
      const staleWarning = screen.queryByText(/stale/i);
      expect(staleWarning).toBeInTheDocument();
    }, { timeout: 10000 });
    
    // Assert past-run notice is NOT visible (it's the latest)
    expect(screen.queryByText(/past run/i)).not.toBeInTheDocument();
  });

  test("4. latest selected + fresh -> shows neither notice", async () => {
    // Only one run, it's the latest, and it's 5 min old (fresh)
    const latestRunId = "run-1";
    const runsList = createRunsList([
      { runId: latestRunId, ageMinutes: 5 }, // Latest - fresh
    ]);

    localStorage.setItem(SELECTED_RUN_STORAGE_KEY, latestRunId);
    await renderApp(runsList, latestRunId);
    
    // Wait for shell to render
    await screen.findByRole("heading", { name: /Fleet overview/i });
    
    // Give time for async operations to settle
    await waitFor(() => {
      // Assert neither notice is visible
      // Since latest is fresh (5 min old), no stale warning should appear
      // Since selected IS latest, no past-run notice should appear
      const pastRunNotice = screen.queryByText(/past run/i);
      const staleWarning = screen.queryByText(/Latest run is.*old/i);
      expect(pastRunNotice).not.toBeInTheDocument();
      expect(staleWarning).not.toBeInTheDocument();
    }, { timeout: 10000 });
  });
}, 15000);
