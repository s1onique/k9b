/**
 * useRunSelection hook tests
 *
 * Tests for getRunsDisplayStatus and computeRunsFilterCounts functions
 * that handle executionCountsComplete flag for truthful UI rendering.
 * 
 * Note: getRunsDisplayStatus now takes a full RunsListEntry object to access
 * executionSummary, and returns new execution-based display statuses.
 */

import { describe, expect, it } from "vitest";
import {
  computeRunsFilterCounts,
  getRunsDisplayStatus,
  type RunsDisplayStatus,
  type RunsReviewFilter,
} from "../useRunSelection";
import type { RunsListEntry } from "../../types";

// Helper to create a runs list entry for testing
const createRunEntry = (overrides: Partial<RunsListEntry> = {}): RunsListEntry => ({
  runId: "run-test-001",
  runLabel: "2026-04-07-1200",
  timestamp: "2026-04-07T12:00:00Z",
  clusterCount: 3,
  triaged: true,
  executionCount: 5,
  reviewedCount: 5,
  reviewStatus: "fully-reviewed",
  reviewDownloadPath: null,
  batchExecutable: false,
  batchEligibleCount: 0,
  executionSummary: null,
  ...overrides,
});

describe("getRunsDisplayStatus", () => {
  describe("with executionSummary (preferred path)", () => {
    it("returns fully-executed for fully-executed state without failures", () => {
      const run = createRunEntry({
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 5,
          failedCandidates: 0,
          pendingExecutableCandidates: 0,
          batchExecutionState: "fully-executed",
        },
      });
      const result = getRunsDisplayStatus(run, true);
      expect(result).toBe("fully-executed");
    });

    it("returns needs-attention for fully-executed with failures", () => {
      const run = createRunEntry({
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 5,
          failedCandidates: 2,
          pendingExecutableCandidates: 0,
          batchExecutionState: "fully-executed",
        },
      });
      const result = getRunsDisplayStatus(run, true);
      expect(result).toBe("needs-attention");
    });

    it("returns no-executions-yet for not-started with pending work", () => {
      const run = createRunEntry({
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 0,
          failedCandidates: 0,
          pendingExecutableCandidates: 5,
          batchExecutionState: "not-started",
        },
      });
      const result = getRunsDisplayStatus(run, true);
      expect(result).toBe("no-executions-yet");
    });

    it("returns partially-executed for partially-executed state", () => {
      const run = createRunEntry({
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 3,
          failedCandidates: 0,
          pendingExecutableCandidates: 2,
          batchExecutionState: "partially-executed",
        },
      });
      const result = getRunsDisplayStatus(run, true);
      expect(result).toBe("partially-executed");
    });

    it("returns no-executable-work for no-candidates state", () => {
      const run = createRunEntry({
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 0,
          executedCandidates: 0,
          failedCandidates: 0,
          pendingExecutableCandidates: 0,
          batchExecutionState: "no-candidates",
        },
      });
      const result = getRunsDisplayStatus(run, true);
      expect(result).toBe("no-executable-work");
    });
  });

  describe("without executionSummary (backward compatibility)", () => {
    it("returns no-executions-yet for no-executions status", () => {
      const run = createRunEntry({ 
        executionSummary: null, 
        reviewStatus: "no-executions" 
      });
      const result = getRunsDisplayStatus(run, true);
      expect(result).toBe("no-executions-yet");
    });

    it("returns fully-executed for fully-reviewed status", () => {
      const run = createRunEntry({ 
        executionSummary: null, 
        reviewStatus: "fully-reviewed" 
      });
      const result = getRunsDisplayStatus(run, true);
      expect(result).toBe("fully-executed");
    });

    it("returns needs-attention for unreviewed status", () => {
      const run = createRunEntry({ 
        executionSummary: null, 
        reviewStatus: "unreviewed" 
      });
      const result = getRunsDisplayStatus(run, true);
      expect(result).toBe("needs-attention");
    });

    it("returns needs-attention for partially-reviewed status", () => {
      const run = createRunEntry({ 
        executionSummary: null, 
        reviewStatus: "partially-reviewed" 
      });
      const result = getRunsDisplayStatus(run, true);
      expect(result).toBe("needs-attention");
    });

    it("returns unknown for no-executions when counts are incomplete", () => {
      const run = createRunEntry({ 
        executionSummary: null, 
        reviewStatus: "no-executions" 
      });
      const result = getRunsDisplayStatus(run, false);
      expect(result).toBe("unknown");
    });

    it("preserves fully-executed status when counts are incomplete", () => {
      const run = createRunEntry({ 
        executionSummary: null, 
        reviewStatus: "fully-reviewed" 
      });
      const result = getRunsDisplayStatus(run, false);
      expect(result).toBe("fully-executed");
    });
  });
});

describe("computeRunsFilterCounts", () => {
  it("counts runs into correct filter buckets with executionSummary", () => {
    const runs: RunsListEntry[] = [
      // fully-executed
      createRunEntry({
        runId: "run-1",
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 5,
          failedCandidates: 0,
          pendingExecutableCandidates: 0,
          batchExecutionState: "fully-executed",
        },
      }),
      // needs-attention (with failures)
      createRunEntry({
        runId: "run-2",
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 5,
          failedCandidates: 2,
          pendingExecutableCandidates: 0,
          batchExecutionState: "fully-executed",
        },
      }),
      // no-executions-yet
      createRunEntry({
        runId: "run-3",
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 0,
          failedCandidates: 0,
          pendingExecutableCandidates: 5,
          batchExecutionState: "not-started",
        },
      }),
      // partially-executed
      createRunEntry({
        runId: "run-4",
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 3,
          failedCandidates: 0,
          pendingExecutableCandidates: 2,
          batchExecutionState: "partially-executed",
        },
      }),
      // no-executable-work
      createRunEntry({
        runId: "run-5",
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 0,
          executedCandidates: 0,
          failedCandidates: 0,
          pendingExecutableCandidates: 0,
          batchExecutionState: "no-candidates",
        },
      }),
    ];

    const counts = computeRunsFilterCounts(runs, true);

    expect(counts.all).toBe(5);
    expect(counts["no-executable-work"]).toBe(1);
    expect(counts["no-executions-yet"]).toBe(1);
    expect(counts["partially-executed"]).toBe(1);
    expect(counts["fully-executed"]).toBe(1);
    expect(counts["needs-attention"]).toBe(1);
  });

  it("falls back to reviewStatus for runs without executionSummary", () => {
    const runs: RunsListEntry[] = [
      createRunEntry({ runId: "run-1", executionSummary: null, reviewStatus: "fully-reviewed" }),
      createRunEntry({ runId: "run-2", executionSummary: null, reviewStatus: "unreviewed" }),
      createRunEntry({ runId: "run-3", executionSummary: null, reviewStatus: "no-executions" }),
    ];

    const counts = computeRunsFilterCounts(runs, true);

    expect(counts.all).toBe(3);
    expect(counts["fully-executed"]).toBe(1);
    expect(counts["needs-attention"]).toBe(1);
    expect(counts["no-executions-yet"]).toBe(1);
  });

  it("excludes no-executions-yet when counts are incomplete", () => {
    const runs: RunsListEntry[] = [
      createRunEntry({ runId: "run-1", executionSummary: null, reviewStatus: "no-executions" }),
      createRunEntry({ runId: "run-2", executionSummary: null, reviewStatus: "fully-reviewed" }),
    ];

    const counts = computeRunsFilterCounts(runs, false);

    expect(counts.all).toBe(2);
    expect(counts["no-executions-yet"]).toBe(0);
    expect(counts["fully-executed"]).toBe(1);
  });

  it("handles empty runs list", () => {
    const counts = computeRunsFilterCounts([], true);

    expect(counts.all).toBe(0);
    expect(counts["no-executable-work"]).toBe(0);
    expect(counts["no-executions-yet"]).toBe(0);
    expect(counts["partially-executed"]).toBe(0);
    expect(counts["fully-executed"]).toBe(0);
    expect(counts["needs-attention"]).toBe(0);
  });

  it("defaults executionCountsComplete to true", () => {
    const countsWithDefault = computeRunsFilterCounts([
      createRunEntry({ executionSummary: null, reviewStatus: "no-executions" }),
    ]);
    const countsExplicit = computeRunsFilterCounts(
      [createRunEntry({ executionSummary: null, reviewStatus: "no-executions" })],
      true
    );

    expect(countsWithDefault["no-executions-yet"]).toBe(1);
    expect(countsExplicit["no-executions-yet"]).toBe(1);
  });
});