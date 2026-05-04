/**
 * useRunSelection hook - refresh behavior tests
 *
 * Tests that both manual refresh and auto-refresh polling invoke the same
 * refreshRuns() pipeline, which calls fetchRunsList() internally.
 *
 * IMPORTANT: Timer ownership is SCOPED within this file.
 * - beforeEach: enables fake timers for tests that need them
 * - afterEach: always restores real timers to prevent cross-file pollution
 *
 * Acceptance criteria:
 * - refreshRuns() is called on mount (initial fetch)
 * - manual invocation of refreshRuns() triggers /api/runs fetch
 * - auto-refresh polling (setInterval) triggers /api/runs fetch
 * - both paths invoke the same fetchRunsList() pipeline
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { useRunSelection } from "../useRunSelection";
import { createStorageMock, makeFetchResponse } from "../../__tests__/fixtures";
import type { RunsListPayload } from "../../types";

describe("useRunSelection refresh behavior", () => {
  // Build initial runs list (run-123 is latest)
  const initialRunsList: RunsListPayload = {
    runs: [
      { runId: "run-123", runLabel: "2026-04-07-1200", timestamp: "2026-04-07T12:00:00Z", clusterCount: 3, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
      { runId: "run-122", runLabel: "2026-04-07-1100", timestamp: "2026-04-07T11:00:00Z", clusterCount: 3, triaged: false, executionCount: 3, reviewedCount: 0, reviewStatus: "unreviewed" },
    ],
    totalCount: 2,
    executionCountsComplete: true,
  };

  // Build updated runs list (run-124 is latest - newer than run-123)
  const updatedRunsList: RunsListPayload = {
    runs: [
      { runId: "run-124", runLabel: "2026-04-07-1300", timestamp: "2026-04-07T13:00:00Z", clusterCount: 4, triaged: true, executionCount: 7, reviewedCount: 7, reviewStatus: "fully-reviewed" },
      { runId: "run-123", runLabel: "2026-04-07-1200", timestamp: "2026-04-07T12:00:00Z", clusterCount: 3, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
      { runId: "run-122", runLabel: "2026-04-07-1100", timestamp: "2026-04-07T11:00:00Z", clusterCount: 3, triaged: false, executionCount: 3, reviewedCount: 0, reviewStatus: "unreviewed" },
    ],
    totalCount: 3,
    executionCountsComplete: true,
  };

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.clearAllTimers();
    vi.clearAllMocks();
    const storageMock = createStorageMock();
    vi.stubGlobal("localStorage", storageMock);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.clearAllTimers();
    vi.unstubAllGlobals();
  });

  test("initial mount calls fetchRunsList() (initial fetch)", async () => {
    // Mutable reference for runs response
    let currentRunsList = { ...initialRunsList };
    let callCount = 0;

    const fetchMock = vi.fn(async (input: RequestInfo) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        callCount++;
        return makeFetchResponse({ ...currentRunsList });
      }

      // Default responses for other endpoints
      return makeFetchResponse({});
    });

    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useRunSelection());

    // Wait for initial render to complete
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // Verify /api/runs was called at least once (initial mount fetch)
    const runsCalls = fetchMock.mock.calls.filter(([input]) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      return url.includes("/api/runs");
    });
    expect(runsCalls.length).toBeGreaterThanOrEqual(1);

    // Verify runs state was populated
    expect(result.current.runs.length).toBe(2);
  });

  test("refreshRuns() manually triggers /api/runs fetch (newer latest run surfaced)", async () => {
    // Mutable reference - simulates server-side data change
    let currentRunsList = { ...initialRunsList };
    let runsCallCount = 0;

    const fetchMock = vi.fn(async (input: RequestInfo) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        runsCallCount++;
        // First call returns initialRunsList
        // Second call (after refreshRuns()) returns updatedRunsList with run-124
        const payload = runsCallCount === 1 ? currentRunsList : (() => {
          currentRunsList = { ...updatedRunsList };
          return updatedRunsList;
        })();
        return makeFetchResponse({ ...payload });
      }

      return makeFetchResponse({});
    });

    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useRunSelection());

    // Wait for initial mount fetch
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const initialCallCount = runsCallCount;

    // Verify initial state: run-123 is latest
    expect(result.current.latestRunId).toBe("run-123");
    expect(result.current.runs.length).toBe(2);

    // Trigger manual refresh
    await act(async () => {
      await result.current.refreshRuns();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // Verify refreshRuns() triggered an additional /api/runs fetch
    expect(runsCallCount).toBe(initialCallCount + 1);

    // Verify the updated runs list contains run-124 (newer latest)
    expect(result.current.runs.length).toBe(3); // run-124, run-123, run-122
    expect(result.current.runs[0].runId).toBe("run-124"); // Newest first

    // Verify latestRunId is now run-124
    expect(result.current.latestRunId).toBe("run-124");
  });

  test("auto-refresh polling calls /api/runs via setInterval (newer latest surfaced)", async () => {
    let currentRunsList = { ...initialRunsList };
    let runsCallCount = 0;

    const fetchMock = vi.fn(async (input: RequestInfo) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        runsCallCount++;
        // First call returns initialRunsList
        // Subsequent calls return updatedRunsList with run-124
        const payload = runsCallCount === 1 ? currentRunsList : (() => {
          currentRunsList = { ...updatedRunsList };
          return updatedRunsList;
        })();
        return makeFetchResponse({ ...payload });
      }

      return makeFetchResponse({});
    });

    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useRunSelection());

    // Wait for initial mount fetch
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const initialCallCount = runsCallCount;

    // Verify initial state: run-123 is latest
    expect(result.current.latestRunId).toBe("run-123");

    // Enable auto-refresh with 10-second interval
    await act(async () => {
      result.current.handleAutoRefreshChange("10");
    });

    // Advance time by 10 seconds to trigger the polling interval
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });

    // Flush React state updates
    await act(async () => {
      vi.runAllTicks();
    });
    await act(async () => {});

    // Verify polling triggered an additional /api/runs fetch
    expect(runsCallCount).toBe(initialCallCount + 1);

    // Verify the updated runs list is reflected in hook state
    expect(result.current.runs.length).toBe(3); // run-124, run-123, run-122
    expect(result.current.runs[0].runId).toBe("run-124");
    expect(result.current.latestRunId).toBe("run-124");
  });

  test("both manual refresh and polling invoke the same /api/runs pipeline", async () => {
    let currentRunsList = { ...initialRunsList };
    let runsCallCount = 0;

    const fetchMock = vi.fn(async (input: RequestInfo) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        runsCallCount++;
        return makeFetchResponse({ ...currentRunsList });
      }

      return makeFetchResponse({});
    });

    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useRunSelection());

    // Wait for initial mount
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const initialCalls = runsCallCount;

    // Manual refresh path
    await act(async () => {
      await result.current.refreshRuns();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // Auto-refresh polling path (enable first)
    await act(async () => {
      result.current.handleAutoRefreshChange("10");
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    await act(async () => {
      vi.runAllTicks();
    });
    await act(async () => {});

    // Both paths should have triggered /api/runs fetch
    // manual: +1 call, polling: +1 call = +2 total
    expect(runsCallCount).toBe(initialCalls + 2);

    // The key proof: both manual and polling result in the same observable state
    // (runs list updated, latestRunId set correctly)
    expect(result.current.runs.length).toBe(2);
    expect(result.current.latestRunId).toBe("run-123");
  });
});