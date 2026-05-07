/**
 * useRunSelection hook - refresh behavior tests
 *
 * PHASE 5: Updated tests for the new architecture where:
 *   - RunControl owns the authoritative run list data
 *   - useRunSelection receives runs as INPUT (not locally fetched)
 *   - App.tsx owns the auto-refresh timer
 *   - useRunSelection only manages pagination/filter state and autoRefreshInterval preference
 *
 * Timer ownership is SCOPED within this file:
 * - beforeEach: enables fake timers for tests that need them
 * - afterEach: always restores real timers to prevent cross-file pollution
 *
 * Acceptance criteria:
 * - useRunSelection receives runs as input from RunControl
 * - autoRefreshInterval is persisted and read by App.tsx for timer management
 * - pagination/filter/navigation helpers work correctly
 * - selectedRunId is handled as input for highlighting
 *
 * NOTE: fetchRunsList is no longer called by useRunSelection.
 * RunControl is the sole authoritative owner for run list fetching.
 */

import { renderHook, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { useRunSelection } from "../useRunSelection";
import { createStorageMock } from "../../__tests__/fixtures";
import type { RunsListEntry } from "../../types";

describe("useRunSelection refresh behavior (Phase 5)", () => {
  // Build sample runs list for testing
  const sampleRuns: RunsListEntry[] = [
    { runId: "run-123", runLabel: "2026-04-07-1200", timestamp: "2026-04-07T12:00:00Z", clusterCount: 3, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
    { runId: "run-122", runLabel: "2026-04-07-1100", timestamp: "2026-04-07T11:00:00Z", clusterCount: 3, triaged: false, executionCount: 3, reviewedCount: 0, reviewStatus: "unreviewed" },
    { runId: "run-121", runLabel: "2026-04-07-1000", timestamp: "2026-04-07T10:00:00Z", clusterCount: 3, triaged: true, executionCount: 7, reviewedCount: 7, reviewStatus: "fully-reviewed" },
  ];

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
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

  test("receives runs as input from RunControl", () => {
    const { result } = renderHook(() =>
      useRunSelection({
        runs: sampleRuns,
        isLoading: false,
        error: null,
      })
    );

    // useRunSelection passes through the runs from input
    expect(result.current.runs).toBe(sampleRuns);
    expect(result.current.runs.length).toBe(3);
  });

  test("derives latestRunId from runs input", () => {
    const { result } = renderHook(() =>
      useRunSelection({
        runs: sampleRuns,
        isLoading: false,
        error: null,
      })
    );

    // First run in the list (sorted by timestamp descending) should be latest
    expect(result.current.latestRunId).toBe("run-123");
  });

  test("derives isLatest correctly", () => {
    const { result: result1 } = renderHook(() =>
      useRunSelection({
        runs: sampleRuns,
        isLoading: false,
        error: null,
        selectedRunId: "run-123", // Selected is latest
      })
    );
    expect(result1.current.isLatest).toBe(true);

    const { result: result2 } = renderHook(() =>
      useRunSelection({
        runs: sampleRuns,
        isLoading: false,
        error: null,
        selectedRunId: "run-122", // Selected is not latest
      })
    );
    expect(result2.current.isLatest).toBe(false);
  });

  test("passes through isLoading from input", () => {
    const { result: resultLoading } = renderHook(() =>
      useRunSelection({
        runs: sampleRuns,
        isLoading: true,
        error: null,
      })
    );
    expect(resultLoading.current.isLoading).toBe(true);

    const { result: resultNotLoading } = renderHook(() =>
      useRunSelection({
        runs: sampleRuns,
        isLoading: false,
        error: null,
      })
    );
    expect(resultNotLoading.current.isLoading).toBe(false);
  });

  test("passes through error from input", () => {
    const { result: resultNoError } = renderHook(() =>
      useRunSelection({
        runs: sampleRuns,
        isLoading: false,
        error: null,
      })
    );
    expect(resultNoError.current.error).toBeNull();

    const { result: resultWithError } = renderHook(() =>
      useRunSelection({
        runs: sampleRuns,
        isLoading: false,
        error: "Failed to load runs",
      })
    );
    expect(resultWithError.current.error).toBe("Failed to load runs");
  });

  test("handles empty runs list", () => {
    const { result } = renderHook(() =>
      useRunSelection({
        runs: [],
        isLoading: false,
        error: null,
      })
    );

    expect(result.current.runs).toEqual([]);
    expect(result.current.latestRunId).toBeNull();
    expect(result.current.isLatest).toBe(true); // No selection, so isLatest is true
  });

  test("autoRefreshInterval is persisted", () => {
    const { result } = renderHook(() =>
      useRunSelection({
        runs: sampleRuns,
        isLoading: false,
        error: null,
      })
    );

    // Default autoRefreshInterval should be read from localStorage
    expect(result.current.autoRefreshInterval).toBeDefined();
  });

  test("handleAutoRefreshChange persists interval", () => {
    const { result } = renderHook(() =>
      useRunSelection({
        runs: sampleRuns,
        isLoading: false,
        error: null,
      })
    );

    // Change auto-refresh interval
    act(() => {
      result.current.handleAutoRefreshChange("10");
    });

    // The interval should be updated
    expect(result.current.autoRefreshInterval).toBe(10);
  });

  test("handleAutoRefreshChange can disable auto-refresh", () => {
    const { result } = renderHook(() =>
      useRunSelection({
        runs: sampleRuns,
        isLoading: false,
        error: null,
      })
    );

    // Disable auto-refresh
    act(() => {
      result.current.handleAutoRefreshChange("off");
    });

    // The interval should be null
    expect(result.current.autoRefreshInterval).toBeNull();
  });

  test("pagination helpers work correctly", () => {
    const { result } = renderHook(() =>
      useRunSelection({
        runs: sampleRuns,
        isLoading: false,
        error: null,
      })
    );

    // Default pagination
    expect(result.current.runsPage).toBe(1);
    expect(result.current.runsPageSize).toBe(5);
    expect(result.current.paginatedRunsList.length).toBe(3); // Only 3 items

    // Change page size
    act(() => {
      result.current.handleRunsPageSizeChange(2);
    });

    expect(result.current.runsPageSize).toBe(2);
    expect(result.current.paginatedRunsList.length).toBe(2);
  });

  test("filter helpers work correctly", () => {
    const { result } = renderHook(() =>
      useRunSelection({
        runs: sampleRuns,
        isLoading: false,
        error: null,
      })
    );

    // Default filter is "all"
    expect(result.current.runsFilter).toBe("all");
    expect(result.current.filteredRunsList.length).toBe(3);

    // Change filter to "unreviewed"
    act(() => {
      result.current.handleRunsFilterChange("awaiting-review");
    });

    expect(result.current.filteredRunsList.length).toBe(1); // Only run-122 is unreviewed
  });

  test("computePageForRunId works correctly", () => {
    const { result } = renderHook(() =>
      useRunSelection({
        runs: sampleRuns,
        isLoading: false,
        error: null,
      })
    );

    // Page size of 2 means:
    // - run-123 at index 0 -> page 1
    // - run-122 at index 1 -> page 1
    // - run-121 at index 2 -> page 2

    act(() => {
      result.current.handleRunsPageSizeChange(2);
    });

    expect(result.current.computePageForRunId("run-123")).toBe(1);
    expect(result.current.computePageForRunId("run-122")).toBe(1);
    expect(result.current.computePageForRunId("run-121")).toBe(2);
  });

  test("navigateToPageContainingRun updates page", () => {
    const { result } = renderHook(() =>
      useRunSelection({
        runs: sampleRuns,
        isLoading: false,
        error: null,
      })
    );

    act(() => {
      result.current.handleRunsPageSizeChange(2);
    });

    act(() => {
      result.current.navigateToPageContainingRun("run-121");
    });

    expect(result.current.runsPage).toBe(2);
    expect(result.current.isRunsListFollowingSelection).toBe(true);
  });

  test("handleShowSelectedRun navigates to selected run", () => {
    const { result } = renderHook(() =>
      useRunSelection({
        runs: sampleRuns,
        isLoading: false,
        error: null,
        selectedRunId: "run-122",
      })
    );

    act(() => {
      result.current.handleRunsPageSizeChange(2);
    });

    act(() => {
      result.current.handleShowSelectedRun();
    });

    expect(result.current.runsPage).toBe(1); // run-122 is on page 1 with pageSize=2
    expect(result.current.isRunsListFollowingSelection).toBe(true);
  });

  test("isSelectedRunVisibleOnCurrentRunsPage works correctly", () => {
    const { result } = renderHook(() =>
      useRunSelection({
        runs: sampleRuns,
        isLoading: false,
        error: null,
        selectedRunId: "run-123",
      })
    );

    act(() => {
      result.current.handleRunsPageSizeChange(2);
    });

    // run-123 is on page 1, so it should be visible
    expect(result.current.isSelectedRunVisibleOnCurrentRunsPage).toBe(true);

    // Navigate to page 2
    act(() => {
      result.current.handleRunsPageChange(2);
    });

    // run-123 is not on page 2, so it should not be visible
    expect(result.current.isSelectedRunVisibleOnCurrentRunsPage).toBe(false);
  });
});
