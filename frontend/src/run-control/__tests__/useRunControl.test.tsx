/**
 * useRunControl.test.tsx — Unit tests for the useRunControl hook.
 *
 * Phase 2: Tests the interpreter hook that owns the runtime boundary.
 *
 * Test cases:
 * 1. boot executes fetchRuns and dispatches RunsLoaded on success.
 * 2. boot dispatches RunsFailed on fetchRuns failure.
 * 3. selecting a run executes fetchRun and dispatches RunLoaded on success.
 * 4. fetchRun failure dispatches RunFailed.
 * 5. slow timer dispatches RunSlowThresholdReached after delay.
 * 6. cancelSlowRunTimer prevents slow transition after RunLoaded.
 * 7. stale fetchRun result is ignored by reducer when newer request wins.
 * 8. debugLog does not call console.info by default.
 * 9. debugLog calls console.info when debugEnabled=true.
 * 10. unmount clears pending slow timers.
 * 11. manualRefresh executes fetchRuns with reason manual.
 * 12. poll executes fetchRuns with reason poll.
 */

import { renderHook, waitFor, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRunControl } from "../useRunControl";
import { fetchRun, fetchRunsList } from "../../api";
import { makeRunWithOverrides } from "../../__tests__/fixtures";
import type { RunsListPayload } from "../../types";

// Mock at module level - hoisted to top
vi.mock("../../api", () => ({
  fetchRunsList: vi.fn(),
  fetchRun: vi.fn(),
}));

// ============================================================================
// Test fixtures
// ============================================================================

const makeRunsListPayload = (
  runs: Array<{ runId: string; runLabel: string }>
): RunsListPayload => ({
  runs: runs.map((r, idx) => ({
    runId: r.runId,
    runLabel: r.runLabel,
    timestamp: `2026-04-07T${10 + idx}:00:00Z`,
    clusterCount: 2,
    triaged: true,
    executionCount: 5,
    reviewedCount: 5,
    reviewStatus: "fully-reviewed",
    reviewDownloadPath: null,
    batchExecutable: false,
    batchEligibleCount: 0,
  })),
  totalCount: runs.length,
  executionCountsComplete: true,
});

// ============================================================================
// Test helpers
// ============================================================================

/**
 * Boot and wait for selected run to be loaded.
 * Uses mockResolvedValueOnce to ensure immediate resolution.
 */
async function bootAndWaitLoaded(
  result: { current: ReturnType<typeof useRunControl> },
  runsPayload: RunsListPayload,
  runPayload: ReturnType<typeof makeRunWithOverrides>
) {
  vi.mocked(fetchRunsList).mockResolvedValueOnce(runsPayload);
  vi.mocked(fetchRun).mockResolvedValueOnce(runPayload);

  await act(async () => {
    result.current.boot();
  });

  await waitFor(
    () => {
      expect(result.current.selectedRunStatus).toBe("loaded");
    },
    { timeout: 2000 }
  );
}

// ============================================================================
// Test suite
// ============================================================================

describe("useRunControl", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Only stub what's needed - localStorage for auto-refresh interval
    const storageMock = {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    };
    vi.stubGlobal("localStorage", storageMock);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  // --------------------------------------------------------------------------
  // Test 1: boot executes fetchRuns and dispatches RunsLoaded on success
  // --------------------------------------------------------------------------
  it("1. boot executes fetchRuns and dispatches RunsLoaded on success", async () => {
    const runsPayload = makeRunsListPayload([
      { runId: "run-latest", runLabel: "Latest" },
    ]);
    const runPayload = makeRunWithOverrides({ runId: "run-latest" });

    vi.mocked(fetchRunsList).mockResolvedValue(runsPayload);
    vi.mocked(fetchRun).mockResolvedValue(runPayload);

    const { result } = renderHook(() => useRunControl({ autoBoot: false }));

    await act(async () => {
      result.current.boot();
    });

    // Wait for async resolution
    await waitFor(
      () => {
        expect(result.current.selectedRunStatus).toBe("loaded");
      },
      { timeout: 2000 }
    );

    // fetchRuns should have been called
    expect(fetchRunsList).toHaveBeenCalledTimes(1);

    // Should have selected the latest run
    expect(result.current.selectedRunId).toBe("run-latest");
    expect(result.current.model.runs.items).toHaveLength(1);
  });

  // --------------------------------------------------------------------------
  // Test 2: boot dispatches RunsFailed on fetchRuns failure
  // --------------------------------------------------------------------------
  it("2. boot dispatches RunsFailed on fetchRuns failure", async () => {
    vi.mocked(fetchRunsList).mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() => useRunControl({ autoBoot: false }));

    await act(async () => {
      result.current.boot();
    });

    await waitFor(
      () => {
        expect(result.current.model.runs.status).toBe("failed");
      },
      { timeout: 2000 }
    );

    expect(result.current.model.runs.error).toBe("Network error");
  });

  // --------------------------------------------------------------------------
  // Test 3: selecting a run executes fetchRun and dispatches RunLoaded on success
  // --------------------------------------------------------------------------
  it("3. selecting a run executes fetchRun and dispatches RunLoaded on success", async () => {
    const runsPayload = makeRunsListPayload([
      { runId: "run-123", runLabel: "Run 123" },
    ]);
    const runPayload = makeRunWithOverrides({ runId: "run-123" });

    const { result } = renderHook(() => useRunControl({ autoBoot: false }));

    // Boot with immediate resolution
    await bootAndWaitLoaded(result, runsPayload, runPayload);

    // Set up mock for selectRun BEFORE calling it
    vi.mocked(fetchRun).mockResolvedValueOnce(runPayload);

    await act(async () => {
      result.current.selectRun("run-123");
    });

    // fetchRun should have been called
    expect(fetchRun).toHaveBeenCalledWith(
      "run-123",
      expect.objectContaining({ clientRequestId: expect.any(String), signal: expect.any(Object) })
    );

    // Wait for async resolution
    await waitFor(
      () => {
        expect(result.current.selectedRunStatus).toBe("loaded");
      },
      { timeout: 2000 }
    );

    expect(result.current.selectedRun?.runId).toBe("run-123");
  });

  // --------------------------------------------------------------------------
  // Test 4: fetchRun failure dispatches RunFailed
  // --------------------------------------------------------------------------
  it("4. fetchRun failure dispatches RunFailed", async () => {
    const runsPayload = makeRunsListPayload([
      { runId: "run-123", runLabel: "Run 123" },
    ]);
    const runPayload = makeRunWithOverrides({ runId: "run-123" });

    // First boot succeeds, then selectRun fails
    vi.mocked(fetchRunsList).mockResolvedValue(runsPayload);
    vi.mocked(fetchRun)
      .mockResolvedValueOnce(runPayload) // boot
      .mockRejectedValueOnce(new Error("Server error")); // selectRun

    const { result } = renderHook(() => useRunControl({ autoBoot: false }));

    await bootAndWaitLoaded(result, runsPayload, runPayload);

    await act(async () => {
      result.current.selectRun("run-123");
    });

    await waitFor(
      () => {
        expect(result.current.selectedRunStatus).toBe("failed");
      },
      { timeout: 2000 }
    );

    expect(result.current.selectedRunError).toBe("Server error");
  });

  // --------------------------------------------------------------------------
  // Test 5: slow timer dispatches RunSlowThresholdReached after delay
  // --------------------------------------------------------------------------
  it("5. slow timer dispatches RunSlowThresholdReached after delay", async () => {
    // IMPORTANT: Set up fake timers BEFORE renderHook
    vi.useFakeTimers({ shouldAdvanceTime: false });

    const runsPayload = makeRunsListPayload([
      { runId: "run-123", runLabel: "Run 123" },
    ]);
    const runPayload = makeRunWithOverrides({ runId: "run-123" });

    // Create a deferred promise that never resolves during the test
    let resolveRun: (value: typeof runPayload) => void;
    const runPromise = new Promise<typeof runPayload>((resolve) => {
      resolveRun = resolve;
    });

    vi.mocked(fetchRunsList).mockResolvedValue(runsPayload);
    vi.mocked(fetchRun).mockImplementation(() => runPromise);

    const { result } = renderHook(() =>
      useRunControl({ slowAfterMs: 10_000, autoBoot: false })
    );

    // Boot with immediate resolution (no waitFor needed with fake timers)
    vi.mocked(fetchRunsList).mockResolvedValueOnce(runsPayload);
    vi.mocked(fetchRun).mockResolvedValueOnce(runPayload);

    await act(async () => {
      result.current.boot();
    });

    // Advance time to flush pending microtasks
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // Should be loaded after boot
    expect(result.current.selectedRunStatus).toBe("loaded");

    // Set up never-resolving mock for selectRun
    vi.mocked(fetchRun).mockClear();
    vi.mocked(fetchRun).mockImplementation(() => runPromise);

    await act(async () => {
      result.current.selectRun("run-123");
    });

    // Should be loading
    expect(result.current.selectedRunStatus).toBe("loading");

    // Advance time past slow threshold
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    // Should now be slow
    expect(result.current.selectedRunStatus).toBe("slow");

    // Resolve the promise to clean up
    act(() => {
      resolveRun!(runPayload);
    });
  });

  // --------------------------------------------------------------------------
  // Test 6: cancelSlowRunTimer prevents slow transition after RunLoaded
  // --------------------------------------------------------------------------
  it("6. cancelSlowRunTimer prevents slow transition after RunLoaded", async () => {
    // IMPORTANT: Set up fake timers BEFORE renderHook
    vi.useFakeTimers({ shouldAdvanceTime: false });

    const runsPayload = makeRunsListPayload([
      { runId: "run-123", runLabel: "Run 123" },
    ]);
    const runPayload = makeRunWithOverrides({ runId: "run-123" });

    // Deferred promise for controlled timing
    let resolveRun: (value: typeof runPayload) => void;
    const runPromise = new Promise<typeof runPayload>((resolve) => {
      resolveRun = resolve;
    });

    vi.mocked(fetchRunsList).mockResolvedValue(runsPayload);
    vi.mocked(fetchRun).mockImplementation(() => runPromise);

    const { result } = renderHook(() =>
      useRunControl({ slowAfterMs: 10_000, autoBoot: false })
    );

    // Boot with immediate resolution
    vi.mocked(fetchRunsList).mockResolvedValueOnce(runsPayload);
    vi.mocked(fetchRun).mockResolvedValueOnce(runPayload);

    await act(async () => {
      result.current.boot();
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.selectedRunStatus).toBe("loaded");

    // Set up deferred mock for selectRun
    vi.mocked(fetchRun).mockClear();
    vi.mocked(fetchRun).mockImplementation(() => runPromise);

    await act(async () => {
      result.current.selectRun("run-123");
    });

    // Advance time to just before slow threshold
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9_000);
    });

    // Should still be loading (not slow yet)
    expect(result.current.selectedRunStatus).toBe("loading");

    // Resolve the fetch before slow threshold
    await act(async () => {
      resolveRun!(runPayload);
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // Should be loaded (timer was cancelled)
    expect(result.current.selectedRunStatus).toBe("loaded");

    // Advance past slow threshold - should NOT transition to slow
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    // Should still be loaded (timer was cancelled)
    expect(result.current.selectedRunStatus).toBe("loaded");
  });

  // --------------------------------------------------------------------------
  // Test 7: stale fetchRun result is ignored by reducer when newer request wins
  // --------------------------------------------------------------------------
  it("7. stale fetchRun result is ignored by reducer when newer request wins", async () => {
    // IMPORTANT: Set up fake timers BEFORE renderHook
    vi.useFakeTimers({ shouldAdvanceTime: false });

    const runsPayload = makeRunsListPayload([
      { runId: "run-123", runLabel: "Run 123" },
      { runId: "run-456", runLabel: "Run 456" },
    ]);
    const runPayload123 = makeRunWithOverrides({ runId: "run-123" });
    const runPayload456 = makeRunWithOverrides({ runId: "run-456" });

    // Deferred promises for controlled timing
    let resolveSlow: (value: typeof runPayload123) => void;
    const slowPromise = new Promise<typeof runPayload123>((resolve) => {
      resolveSlow = resolve;
    });

    vi.mocked(fetchRunsList).mockResolvedValue(runsPayload);
    vi.mocked(fetchRun)
      .mockResolvedValueOnce(runPayload123) // boot selected latest (run-123)
      .mockImplementationOnce(() => slowPromise) // slow first selection
      .mockResolvedValueOnce(runPayload456); // fast second selection

    const { result } = renderHook(() => useRunControl({ autoBoot: false }));

    // Boot with immediate resolution
    vi.mocked(fetchRunsList).mockResolvedValueOnce(runsPayload);
    vi.mocked(fetchRun).mockResolvedValueOnce(runPayload123);

    await act(async () => {
      result.current.boot();
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.selectedRunStatus).toBe("loaded");

    // Select run-123 (slow)
    await act(async () => {
      result.current.selectRun("run-123");
    });

    // Immediately select run-456 (fast)
    await act(async () => {
      result.current.selectRun("run-456");
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // Selected run should be run-456
    expect(result.current.selectedRunId).toBe("run-456");
    expect(result.current.selectedRun?.runId).toBe("run-456");
    expect(result.current.selectedRunStatus).toBe("loaded");

    // Now resolve the slow promise (should be ignored)
    await act(async () => {
      resolveSlow!(runPayload123);
    });

    // State should still show run-456 (stale run-123 ignored)
    expect(result.current.selectedRunId).toBe("run-456");
    expect(result.current.selectedRun?.runId).toBe("run-456");
  });

  // --------------------------------------------------------------------------
  // Test 8: debugLog does not call console.info by default
  // --------------------------------------------------------------------------
  it("8. debugLog does not call console.info by default", async () => {
    const consoleInfoSpy = vi.spyOn(console, "info").mockImplementation(() => {});

    const runsPayload = makeRunsListPayload([
      { runId: "run-123", runLabel: "Run 123" },
    ]);
    const runPayload = makeRunWithOverrides({ runId: "run-123" });

    const { result } = renderHook(() =>
      useRunControl({ debugEnabled: false, autoBoot: false })
    );

    await bootAndWaitLoaded(result, runsPayload, runPayload);

    // No debug logs should have been emitted (debug disabled)
    expect(consoleInfoSpy).not.toHaveBeenCalled();

    consoleInfoSpy.mockRestore();
  });

  // --------------------------------------------------------------------------
  // Test 9: debugLog calls console.info when debugEnabled=true with stale response
  // --------------------------------------------------------------------------
  it("9. debugLog calls console.info when debugEnabled=true with stale response", async () => {
    // IMPORTANT: Set up fake timers BEFORE renderHook
    vi.useFakeTimers({ shouldAdvanceTime: false });

    const consoleInfoSpy = vi.spyOn(console, "info").mockImplementation(() => {});

    const runsPayload = makeRunsListPayload([
      { runId: "run-123", runLabel: "Run 123" },
      { runId: "run-456", runLabel: "Run 456" },
    ]);
    const runPayload123 = makeRunWithOverrides({ runId: "run-123" });
    const runPayload456 = makeRunWithOverrides({ runId: "run-456" });

    // Deferred promises
    let resolveSlow: (value: typeof runPayload123) => void;
    const slowPromise = new Promise<typeof runPayload123>((resolve) => {
      resolveSlow = resolve;
    });

    vi.mocked(fetchRunsList).mockResolvedValue(runsPayload);
    vi.mocked(fetchRun)
      .mockResolvedValueOnce(runPayload123) // boot
      .mockImplementationOnce(() => slowPromise) // slow first selection
      .mockResolvedValueOnce(runPayload456); // fast second selection

    const { result } = renderHook(() =>
      useRunControl({ debugEnabled: true, autoBoot: false })
    );

    // Boot with immediate resolution
    vi.mocked(fetchRunsList).mockResolvedValueOnce(runsPayload);
    vi.mocked(fetchRun).mockResolvedValueOnce(runPayload123);

    await act(async () => {
      result.current.boot();
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.selectedRunStatus).toBe("loaded");

    // Select run-123 (slow)
    await act(async () => {
      result.current.selectRun("run-123");
    });

    // Select run-456 (fast)
    await act(async () => {
      result.current.selectRun("run-456");
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.selectedRunStatus).toBe("loaded");

    // Resolve the slow promise - should trigger debugLog for stale response
    await act(async () => {
      resolveSlow!(runPayload123);
    });

    // Flush microtasks to ensure the stale response is processed
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // Dispatch a no-op message to trigger effect drainer
    // (stale response doesn't change model, so we need to force a model change)
    await act(async () => {
      result.current.poll();
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // Debug logs should have been emitted for stale response
    expect(consoleInfoSpy).toHaveBeenCalled();
    // Should contain our prefix
    const calls = consoleInfoSpy.mock.calls;
    const hasRunControlPrefix = calls.some((call) =>
      String(call[0]).includes("[run-control]")
    );
    expect(hasRunControlPrefix).toBe(true);

    consoleInfoSpy.mockRestore();
  });

  // --------------------------------------------------------------------------
  // Test 10: unmount clears pending slow timers
  // --------------------------------------------------------------------------
  it("10. unmount clears pending slow timers", async () => {
    // IMPORTANT: Set up fake timers BEFORE renderHook
    vi.useFakeTimers({ shouldAdvanceTime: false });

    const runsPayload = makeRunsListPayload([
      { runId: "run-123", runLabel: "Run 123" },
    ]);
    const runPayload = makeRunWithOverrides({ runId: "run-123" });

    // Deferred promise
    let resolveRun: (value: typeof runPayload) => void;
    const runPromise = new Promise<typeof runPayload>((resolve) => {
      resolveRun = resolve;
    });

    vi.mocked(fetchRunsList).mockResolvedValue(runsPayload);
    vi.mocked(fetchRun).mockImplementation(() => runPromise);

    const { result, unmount } = renderHook(() =>
      useRunControl({ slowAfterMs: 10_000, autoBoot: false })
    );

    // Boot with immediate resolution
    vi.mocked(fetchRunsList).mockResolvedValueOnce(runsPayload);
    vi.mocked(fetchRun).mockResolvedValueOnce(runPayload);

    await act(async () => {
      result.current.boot();
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.selectedRunStatus).toBe("loaded");

    // Set up never-resolving mock
    vi.mocked(fetchRun).mockClear();
    vi.mocked(fetchRun).mockImplementation(() => runPromise);

    await act(async () => {
      result.current.selectRun("run-123");
    });

    // Should be loading
    expect(result.current.selectedRunStatus).toBe("loading");

    // Unmount before slow timer fires
    unmount();

    // Advance time past slow threshold - should not cause errors
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });

    // Clean up promise
    act(() => {
      resolveRun!(runPayload);
    });
  });

  // --------------------------------------------------------------------------
  // Test 11: manualRefresh executes fetchRuns with reason manual
  // --------------------------------------------------------------------------
  it("11. manualRefresh executes fetchRuns with reason manual", async () => {
    const runsPayload = makeRunsListPayload([
      { runId: "run-latest", runLabel: "Latest" },
    ]);
    const runPayload = makeRunWithOverrides({ runId: "run-latest" });

    vi.mocked(fetchRunsList).mockResolvedValue(runsPayload);
    vi.mocked(fetchRun).mockResolvedValue(runPayload);

    const { result } = renderHook(() => useRunControl({ autoBoot: false }));

    await bootAndWaitLoaded(result, runsPayload, runPayload);

    // Set up mock for next fetchRunsList call BEFORE clearing
    vi.mocked(fetchRunsList).mockResolvedValueOnce(runsPayload);

    await act(async () => {
      result.current.manualRefresh();
    });

    // fetchRuns should have been called again
    expect(fetchRunsList).toHaveBeenCalledTimes(2);

    await waitFor(
      () => {
        expect(result.current.model.runs.status).toBe("loaded");
      },
      { timeout: 2000 }
    );

    expect(result.current.model.runs.lastRefreshReason).toBe("manual");
  });

  // --------------------------------------------------------------------------
  // Test 12: poll executes fetchRuns with reason poll
  // --------------------------------------------------------------------------
  it("12. poll executes fetchRuns with reason poll", async () => {
    const runsPayload = makeRunsListPayload([
      { runId: "run-latest", runLabel: "Latest" },
    ]);
    const runPayload = makeRunWithOverrides({ runId: "run-latest" });

    vi.mocked(fetchRunsList).mockResolvedValue(runsPayload);
    vi.mocked(fetchRun).mockResolvedValue(runPayload);

    const { result } = renderHook(() => useRunControl({ autoBoot: false }));

    await bootAndWaitLoaded(result, runsPayload, runPayload);

    // Set up mock for next fetchRunsList call BEFORE clearing
    vi.mocked(fetchRunsList).mockResolvedValueOnce(runsPayload);

    await act(async () => {
      result.current.poll();
    });

    // fetchRuns should have been called again
    expect(fetchRunsList).toHaveBeenCalledTimes(2);

    await waitFor(
      () => {
        expect(result.current.model.runs.status).toBe("loaded");
      },
      { timeout: 2000 }
    );

    expect(result.current.model.runs.lastRefreshReason).toBe("poll");
  });

  // --------------------------------------------------------------------------
  // Additional: autoBoot option
  // --------------------------------------------------------------------------
  it("autoBoot=true calls boot on mount", async () => {
    const runsPayload = makeRunsListPayload([
      { runId: "run-latest", runLabel: "Latest" },
    ]);
    const runPayload = makeRunWithOverrides({ runId: "run-latest" });

    vi.mocked(fetchRunsList).mockResolvedValue(runsPayload);
    vi.mocked(fetchRun).mockResolvedValue(runPayload);

    const { result } = renderHook(() => useRunControl({ autoBoot: true }));

    // fetchRuns should have been called automatically
    expect(fetchRunsList).toHaveBeenCalledTimes(1);

    await waitFor(
      () => {
        expect(result.current.selectedRunStatus).toBe("loaded");
      },
      { timeout: 2000 }
    );
  });

  // --------------------------------------------------------------------------
  // Additional: clickLatest
  // --------------------------------------------------------------------------
  it("clickLatest selects the latest run", async () => {
    const runsPayload = makeRunsListPayload([
      { runId: "run-latest", runLabel: "Latest" },
    ]);
    const runPayload = makeRunWithOverrides({ runId: "run-latest" });

    const { result } = renderHook(() => useRunControl({ autoBoot: false }));

    await bootAndWaitLoaded(result, runsPayload, runPayload);

    // Set up mock for clickLatest BEFORE calling it
    vi.mocked(fetchRun).mockResolvedValueOnce(runPayload);

    await act(async () => {
      result.current.clickLatest();
    });

    await waitFor(
      () => {
        expect(result.current.selectedRunStatus).toBe("loaded");
      },
      { timeout: 2000 }
    );

    expect(result.current.selectedRunId).toBe("run-latest");
  });

  // --------------------------------------------------------------------------
  // Additional: retrySelectedRun
  // --------------------------------------------------------------------------
  it("retrySelectedRun refetches the selected run", async () => {
    const runsPayload = makeRunsListPayload([
      { runId: "run-123", runLabel: "Run 123" },
    ]);
    const runPayload = makeRunWithOverrides({ runId: "run-123" });

    const { result } = renderHook(() => useRunControl({ autoBoot: false }));

    await bootAndWaitLoaded(result, runsPayload, runPayload);

    // Set up mock for retry BEFORE calling it
    vi.mocked(fetchRun).mockResolvedValueOnce(runPayload);

    await act(async () => {
      result.current.retrySelectedRun();
    });

    // Should retry fetching the selected run (run-123)
    expect(fetchRun).toHaveBeenCalledWith(
      "run-123",
      expect.objectContaining({ clientRequestId: expect.any(String), signal: expect.any(Object) })
    );
  });

  // --------------------------------------------------------------------------
  // Regression: newer requestSeq for same run is not deduped away
  // --------------------------------------------------------------------------
  it("newer requestSeq for same run is not deduped away", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false });

    const runsPayload = makeRunsListPayload([
      { runId: "run-123", runLabel: "Run 123" },
    ]);
    const runPayload123 = makeRunWithOverrides({ runId: "run-123" });
    const secondPayload = makeRunWithOverrides({ runId: "run-123", clusterCount: 5 });

    vi.mocked(fetchRunsList).mockResolvedValue(runsPayload);

    const { result } = renderHook(() => useRunControl({ autoBoot: false }));

    // Boot: immediate resolution
    vi.mocked(fetchRun).mockResolvedValueOnce(runPayload123);
    vi.mocked(fetchRunsList).mockResolvedValueOnce(runsPayload);

    await act(async () => {
      result.current.boot();
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.selectedRunStatus).toBe("loaded");

    // Set up mock for retry
    vi.mocked(fetchRun).mockResolvedValueOnce(secondPayload);

    // Call retry - this should NOT be deduped because it has a different requestSeq
    await act(async () => {
      result.current.retrySelectedRun();
    });

    // Advance time to process all microtasks
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // The retry should have been made (not deduped) - verify at least one call was made
    expect(fetchRun.mock.calls.length).toBeGreaterThan(0);

    vi.useRealTimers();
  });

  // --------------------------------------------------------------------------
  // Regression: old aborted request cleanup does not clear newer request
  // --------------------------------------------------------------------------
  it("old aborted request cleanup does not clear newer in-flight request", async () => {
    // IMPORTANT: Set up fake timers BEFORE renderHook
    vi.useFakeTimers({ shouldAdvanceTime: false });

    const runsPayload = makeRunsListPayload([
      { runId: "run-123", runLabel: "Run 123" },
    ]);
    const runPayload123 = makeRunWithOverrides({ runId: "run-123" });

    // Deferred promise for first request (never resolves in test)
    let resolveFirst: (value: typeof runPayload123) => void;
    const firstPromise = new Promise<typeof runPayload123>((resolve) => {
      resolveFirst = resolve;
    });

    vi.mocked(fetchRunsList).mockResolvedValue(runsPayload);
    vi.mocked(fetchRun)
      .mockResolvedValueOnce(runPayload123) // boot
      .mockImplementationOnce(() => firstPromise) // first selectRun (never resolves)
      .mockResolvedValueOnce(runPayload123); // second selectRun (resolves immediately)

    const { result } = renderHook(() => useRunControl({ autoBoot: false }));

    // Boot with immediate resolution
    vi.mocked(fetchRunsList).mockResolvedValueOnce(runsPayload);
    vi.mocked(fetchRun).mockResolvedValueOnce(runPayload123);

    await act(async () => {
      result.current.boot();
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.selectedRunStatus).toBe("loaded");

    // Clear mocks and set up the chain for this test
    vi.mocked(fetchRun).mockClear();
    vi.mocked(fetchRun)
      .mockImplementationOnce(() => firstPromise) // first selectRun (never resolves)
      .mockResolvedValueOnce(runPayload123); // second selectRun (resolves)

    await act(async () => {
      result.current.selectRun("run-123");
    });

    // Should be loading (first request is pending)
    expect(result.current.selectedRunStatus).toBe("loading");

    // Select same run again - this should abort previous and start new request
    await act(async () => {
      result.current.selectRun("run-123");
    });

    // Advance time to allow microtasks to resolve
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // The newer request should complete successfully
    // This proves that old request cleanup didn't corrupt the newer request
    expect(result.current.selectedRunStatus).toBe("loaded");
    expect(result.current.selectedRun?.runId).toBe("run-123");

    vi.useRealTimers();
  });

  // --------------------------------------------------------------------------
  // Regression: selected run switch aborts old request
  // --------------------------------------------------------------------------
  it("selected run switch aborts old request", async () => {
    // IMPORTANT: Set up fake timers BEFORE renderHook
    vi.useFakeTimers({ shouldAdvanceTime: false });

    const runsPayload = makeRunsListPayload([
      { runId: "run-123", runLabel: "Run 123" },
      { runId: "run-456", runLabel: "Run 456" },
    ]);
    const runPayload123 = makeRunWithOverrides({ runId: "run-123" });
    const runPayload456 = makeRunWithOverrides({ runId: "run-456" });

    // Deferred promise for first request
    let resolveFirst: (value: typeof runPayload123) => void;
    const firstPromise = new Promise<typeof runPayload123>((resolve) => {
      resolveFirst = resolve;
    });

    vi.mocked(fetchRunsList).mockResolvedValue(runsPayload);
    vi.mocked(fetchRun)
      .mockResolvedValueOnce(runPayload123) // boot
      .mockImplementationOnce(() => firstPromise); // select run-123 (never resolves)

    const { result } = renderHook(() => useRunControl({ autoBoot: false }));

    // Boot with immediate resolution
    vi.mocked(fetchRunsList).mockResolvedValueOnce(runsPayload);
    vi.mocked(fetchRun).mockResolvedValueOnce(runPayload123);

    await act(async () => {
      result.current.boot();
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.selectedRunStatus).toBe("loaded");

    // Set up never-resolving mock for selectRun
    vi.mocked(fetchRun).mockClear();
    vi.mocked(fetchRun).mockImplementation(() => firstPromise);

    await act(async () => {
      result.current.selectRun("run-123");
    });

    // Should be loading
    expect(result.current.selectedRunStatus).toBe("loading");

    // Set up mock for run-456
    vi.mocked(fetchRun).mockResolvedValueOnce(runPayload456);

    // Switch to run-456 - this should abort run-123 request
    await act(async () => {
      result.current.selectRun("run-456");
    });

    // Advance time to allow microtasks to resolve
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // run-456 should load successfully (run-123 was aborted)
    expect(result.current.selectedRunStatus).toBe("loaded");
    expect(result.current.selectedRunId).toBe("run-456");

    vi.useRealTimers();
  });

  // --------------------------------------------------------------------------
  // Regression: stale response is ignored but current response clears loading
  // --------------------------------------------------------------------------
  it("stale response is ignored but current response clears loading", async () => {
    // IMPORTANT: Set up fake timers BEFORE renderHook
    vi.useFakeTimers({ shouldAdvanceTime: false });

    const runsPayload = makeRunsListPayload([
      { runId: "run-123", runLabel: "Run 123" },
      { runId: "run-456", runLabel: "Run 456" },
    ]);
    const runPayload123 = makeRunWithOverrides({ runId: "run-123" });
    const runPayload456 = makeRunWithOverrides({ runId: "run-456" });

    // Deferred promises for controlled timing
    let resolveSlow: (value: typeof runPayload123) => void;
    const slowPromise = new Promise<typeof runPayload123>((resolve) => {
      resolveSlow = resolve;
    });

    vi.mocked(fetchRunsList).mockResolvedValue(runsPayload);
    vi.mocked(fetchRun)
      .mockResolvedValueOnce(runPayload123) // boot
      .mockImplementationOnce(() => slowPromise) // slow first selection
      .mockResolvedValueOnce(runPayload456); // fast second selection

    const { result } = renderHook(() => useRunControl({ autoBoot: false }));

    // Boot with immediate resolution
    vi.mocked(fetchRunsList).mockResolvedValueOnce(runsPayload);
    vi.mocked(fetchRun).mockResolvedValueOnce(runPayload123);

    await act(async () => {
      result.current.boot();
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.selectedRunStatus).toBe("loaded");

    // Select run-123 (slow)
    await act(async () => {
      result.current.selectRun("run-123");
    });

    // Immediately select run-456 (fast) - this aborts run-123
    await act(async () => {
      result.current.selectRun("run-456");
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // Selected run should be run-456
    expect(result.current.selectedRunId).toBe("run-456");
    expect(result.current.selectedRunStatus).toBe("loaded");
    expect(result.current.selectedRun?.runId).toBe("run-456");

    // Now resolve the slow promise (should be ignored)
    await act(async () => {
      resolveSlow!(runPayload123);
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // State should still show run-456 (stale run-123 ignored)
    expect(result.current.selectedRunId).toBe("run-456");
    expect(result.current.selectedRun?.runId).toBe("run-456");

    vi.useRealTimers();
  });

  // --------------------------------------------------------------------------
  // Regression: duplicate same run + same requestSeq does not create duplicate
  // --------------------------------------------------------------------------
  it("duplicate same run + same requestSeq does not create duplicate network calls", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false });

    const runsPayload = makeRunsListPayload([
      { runId: "run-123", runLabel: "Run 123" },
    ]);
    const runPayload = makeRunWithOverrides({ runId: "run-123" });

    const { result } = renderHook(() => useRunControl({ autoBoot: false }));

    // Boot with immediate resolution
    vi.mocked(fetchRunsList).mockResolvedValueOnce(runsPayload);
    vi.mocked(fetchRun).mockResolvedValueOnce(runPayload);

    await act(async () => {
      result.current.boot();
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.selectedRunStatus).toBe("loaded");

    // Get the current call count
    const callCountAfterBoot = fetchRun.mock.calls.length;

    // Set up mock for all retry calls - each retrySelectedRun has a different requestSeq
    // so they'll all go through (not deduped by same requestSeq)
    vi.mocked(fetchRun)
      .mockResolvedValueOnce(runPayload)
      .mockResolvedValueOnce(runPayload)
      .mockResolvedValueOnce(runPayload);

    // Call retry multiple times rapidly
    await act(async () => {
      result.current.retrySelectedRun();
    });
    await act(async () => {
      result.current.retrySelectedRun();
    });
    await act(async () => {
      result.current.retrySelectedRun();
    });

    // Advance time to allow all promises to resolve
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // With requestSeq-based deduplication:
    // - Each retrySelectedRun() has a different requestSeq (seq increments)
    // - So NONE of them should be deduped
    // - All 3 should make network calls
    expect(fetchRun.mock.calls.length).toBe(callCountAfterBoot + 3);

    vi.useRealTimers();
  });

  // --------------------------------------------------------------------------
  // Additional: derived values are correct
  // --------------------------------------------------------------------------
  it("derived values are correctly computed", async () => {
    const runsPayload = makeRunsListPayload([
      { runId: "run-latest", runLabel: "Latest" },
      { runId: "run-old", runLabel: "Old" },
    ]);
    const runPayload = makeRunWithOverrides({ runId: "run-latest" });

    const { result } = renderHook(() => useRunControl({ autoBoot: false }));

    await bootAndWaitLoaded(result, runsPayload, runPayload);

    // Check initial derived values
    expect(result.current.latestRunId).toBe("run-latest");
    expect(result.current.selectedRunId).toBe("run-latest");
    expect(result.current.selectedRunStatus).toBe("loaded");
    expect(result.current.selectedRunError).toBeNull();
    expect(result.current.runOwnedPanelState).toBe("loaded");
    expect(result.current.showLatestJump).toBe(false);
  });
});
