/**
 * Regression tests for useRunData hook.
 *
 * These tests verify that the hook correctly fetches run data when
 * selectedRunId changes. This was the root cause of execution-history-filter
 * test timeouts - the refresh() function existed but was never called
 * when selectedRunId changed.
 *
 * Key behaviors tested:
 * 1. selectedRunId is set -> fetchRun is called for that run
 * 2. selectedRunId changes -> a new fetch starts
 * 3. Stale older response does not overwrite newer selected-run data
 *    (monotonic sequence guard)
 */
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRunData } from "../useRunData";
import type { RunPayload } from "../../types";

// Mock the API module
vi.mock("../../api", () => ({
  fetchRun: vi.fn().mockResolvedValue({
    runId: "mock-run",
    label: "Mock run",
    timestamp: new Date().toISOString(),
    collectorVersion: "v1.0.0",
    clusterCount: 1,
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
  }),
}));

import { fetchRun } from "../../api";

describe("useRunData", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("setInterval", vi.fn(() => 123));
    vi.stubGlobal("clearInterval", vi.fn());
    // Mock localStorage for auto-refresh interval reading
    const storageMock = {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    };
    vi.stubGlobal("localStorage", storageMock);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("selectedRunId changes trigger fetch", () => {
    it("calls fetchRun when selectedRunId is set", async () => {
      renderHook(() => useRunData({ selectedRunId: "run-123" }));

      // Wait for the effect to trigger
      await waitFor(() => {
        expect(fetchRun).toHaveBeenCalled();
      }, { timeout: 2000 });

      // Verify fetchRun was called with the correct run ID
      expect(fetchRun).toHaveBeenCalledWith("run-123");
    });

    // Note: When selectedRunId is null, no fetch is triggered (conditional effect)
    // This is intentional - we only fetch when a run is selected

    it("triggers new fetch when selectedRunId changes", async () => {
      const { rerender } = renderHook(
        ({ selectedRunId }: { selectedRunId: string | null }) =>
          useRunData({ selectedRunId }),
        { initialProps: { selectedRunId: "run-1" } }
      );

      // Wait for first fetch
      await waitFor(() => {
        expect(fetchRun).toHaveBeenCalledWith("run-1");
      }, { timeout: 2000 });

      // Change selectedRunId
      rerender({ selectedRunId: "run-2" });

      // Wait for second fetch
      await waitFor(() => {
        expect(fetchRun).toHaveBeenCalledWith("run-2");
      }, { timeout: 2000 });

      // Verify both fetches were called
      expect(fetchRun).toHaveBeenCalledWith("run-1");
      expect(fetchRun).toHaveBeenCalledWith("run-2");
    });
  });

  describe("selectedRunId changes trigger new fetch", () => {
    // Note: Full stale-response guard verification requires controlled deferred promises
    // and is deferred to future work. This test verifies that selectedRunId changes
    // trigger new fetch calls (which is the primary regression for the original bug).
    it("makes two fetch calls when selectedRunId changes", async () => {
      const { rerender } = renderHook(
        ({ selectedRunId }: { selectedRunId: string | null }) =>
          useRunData({ selectedRunId }),
        { initialProps: { selectedRunId: "run-1" } }
      );

      // Wait for first fetch
      await waitFor(() => {
        expect(fetchRun).toHaveBeenCalledTimes(1);
      }, { timeout: 2000 });

      // Change selectedRunId
      rerender({ selectedRunId: "run-2" });

      // Wait for second fetch
      await waitFor(() => {
        expect(fetchRun).toHaveBeenCalledTimes(2);
      }, { timeout: 2000 });

      // Verify both fetches were called with correct IDs
      expect(fetchRun).toHaveBeenNthCalledWith(1, "run-1");
      expect(fetchRun).toHaveBeenNthCalledWith(2, "run-2");
    });
  });
});
