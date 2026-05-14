/**
 * Pure unit tests for getRunsDisplayStatus and related functions.
 * Tests executionSummary-based display status derivation.
 */
import { describe, expect, test } from "vitest";
import { 
  getRunsDisplayStatus, 
  deriveExecutionDisplayStatusFromSummary,
  computeRunsFilterCounts,
} from "../useRunSelection";
import type { BatchExecutionSummary } from "../../types";

describe("deriveExecutionDisplayStatusFromSummary", () => {
  const createSummary = (overrides: Partial<BatchExecutionSummary>): BatchExecutionSummary => ({
    totalCandidates: 10,
    executableCandidates: 5,
    executedCandidates: 0,
    failedCandidates: 0,
    pendingExecutableCandidates: 5,
    batchExecutionState: "not-started",
    ...overrides,
  });

  test("returns null when executionSummary is null", () => {
    expect(deriveExecutionDisplayStatusFromSummary(null)).toBeNull();
  });

  test("returns no-executable-work for no-candidates state", () => {
    const summary = createSummary({ batchExecutionState: "no-candidates", executableCandidates: 0 });
    expect(deriveExecutionDisplayStatusFromSummary(summary)).toBe("no-executable-work");
  });

  test("returns no-executions-yet for not-started with pending work", () => {
    const summary = createSummary({ 
      batchExecutionState: "not-started", 
      pendingExecutableCandidates: 5 
    });
    expect(deriveExecutionDisplayStatusFromSummary(summary)).toBe("no-executions-yet");
  });

  test("returns fully-executed for not-started with no pending work", () => {
    const summary = createSummary({ 
      batchExecutionState: "not-started", 
      pendingExecutableCandidates: 0 
    });
    expect(deriveExecutionDisplayStatusFromSummary(summary)).toBe("fully-executed");
  });

  test("returns partially-executed for partially-executed state", () => {
    const summary = createSummary({ 
      batchExecutionState: "partially-executed",
      executedCandidates: 3,
      pendingExecutableCandidates: 2,
    });
    expect(deriveExecutionDisplayStatusFromSummary(summary)).toBe("partially-executed");
  });

  test("returns fully-executed for fully-executed without failures", () => {
    const summary = createSummary({ 
      batchExecutionState: "fully-executed",
      executedCandidates: 5,
      failedCandidates: 0,
    });
    expect(deriveExecutionDisplayStatusFromSummary(summary)).toBe("fully-executed");
  });

  test("returns needs-attention for fully-executed with failures", () => {
    const summary = createSummary({ 
      batchExecutionState: "fully-executed",
      executedCandidates: 5,
      failedCandidates: 2,
    });
    expect(deriveExecutionDisplayStatusFromSummary(summary)).toBe("needs-attention");
  });
});

describe("getRunsDisplayStatus", () => {
  // Helper to create a run entry
  const createRun = (overrides: {
    executionSummary?: BatchExecutionSummary | null;
    reviewStatus?: string;
  } = {}) => ({
    runId: "run-1",
    runLabel: "2026-04-07-1200",
    timestamp: "2026-04-07T12:00:00Z",
    clusterCount: 3,
    triaged: false,
    executionCount: 0,
    reviewedCount: 0,
    reviewStatus: "no-executions",
    reviewDownloadPath: null,
    batchExecutable: false,
    batchEligibleCount: 0,
    ...overrides,
  });

  test("uses executionSummary when available", () => {
    const run = createRun({
      executionSummary: {
        totalCandidates: 10,
        executableCandidates: 5,
        executedCandidates: 5,
        failedCandidates: 0,
        pendingExecutableCandidates: 0,
        batchExecutionState: "fully-executed",
      },
    });
    expect(getRunsDisplayStatus(run, true)).toBe("fully-executed");
  });

  test("returns needs-attention for fully-executed with failures", () => {
    const run = createRun({
      executionSummary: {
        totalCandidates: 10,
        executableCandidates: 5,
        executedCandidates: 5,
        failedCandidates: 2,
        pendingExecutableCandidates: 0,
        batchExecutionState: "fully-executed",
      },
    });
    expect(getRunsDisplayStatus(run, true)).toBe("needs-attention");
  });

  test("returns partially-executed for partially-executed state", () => {
    const run = createRun({
      executionSummary: {
        totalCandidates: 10,
        executableCandidates: 5,
        executedCandidates: 3,
        failedCandidates: 0,
        pendingExecutableCandidates: 2,
        batchExecutionState: "partially-executed",
      },
    });
    expect(getRunsDisplayStatus(run, true)).toBe("partially-executed");
  });

  test("returns no-executable-work for no-candidates state", () => {
    const run = createRun({
      executionSummary: {
        totalCandidates: 10,
        executableCandidates: 0,
        executedCandidates: 0,
        failedCandidates: 0,
        pendingExecutableCandidates: 0,
        batchExecutionState: "no-candidates",
      },
    });
    expect(getRunsDisplayStatus(run, true)).toBe("no-executable-work");
  });

  test("falls back to reviewStatus when executionSummary is null", () => {
    const run = createRun({ executionSummary: null, reviewStatus: "fully-reviewed" });
    expect(getRunsDisplayStatus(run, true)).toBe("fully-executed");
  });

  test("falls back to reviewStatus for no-executions", () => {
    const run = createRun({ executionSummary: null, reviewStatus: "no-executions" });
    expect(getRunsDisplayStatus(run, true)).toBe("no-executions-yet");
  });

  test("falls back to needs-attention for unreviewed", () => {
    const run = createRun({ executionSummary: null, reviewStatus: "unreviewed" });
    expect(getRunsDisplayStatus(run, true)).toBe("needs-attention");
  });

  test("returns unknown when executionSummary is null and counts incomplete", () => {
    const run = createRun({ executionSummary: null, reviewStatus: "no-executions" });
    expect(getRunsDisplayStatus(run, false)).toBe("unknown");
  });
});

describe("computeRunsFilterCounts", () => {
  test("counts runs into correct filter buckets based on executionSummary", () => {
    const runs = [
      // fully-executed
      {
        runId: "run-1",
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 5,
          failedCandidates: 0,
          pendingExecutableCandidates: 0,
          batchExecutionState: "fully-executed",
        },
        reviewStatus: "fully-reviewed",
      },
      // needs-attention (with failures)
      {
        runId: "run-2",
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 5,
          failedCandidates: 2,
          pendingExecutableCandidates: 0,
          batchExecutionState: "fully-executed",
        },
        reviewStatus: "fully-reviewed",
      },
      // partially-executed
      {
        runId: "run-3",
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 3,
          failedCandidates: 0,
          pendingExecutableCandidates: 2,
          batchExecutionState: "partially-executed",
        },
        reviewStatus: "fully-reviewed",
      },
      // no-executions-yet
      {
        runId: "run-4",
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 0,
          failedCandidates: 0,
          pendingExecutableCandidates: 5,
          batchExecutionState: "not-started",
        },
        reviewStatus: "no-executions",
      },
      // no-executable-work
      {
        runId: "run-5",
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 0,
          executedCandidates: 0,
          failedCandidates: 0,
          pendingExecutableCandidates: 0,
          batchExecutionState: "no-candidates",
        },
        reviewStatus: "no-executions",
      },
    ] as any[];

    const counts = computeRunsFilterCounts(runs, true);

    expect(counts.all).toBe(5);
    expect(counts['fully-executed']).toBe(1);
    expect(counts['needs-attention']).toBe(1); // The failure run
    expect(counts['partially-executed']).toBe(1);
    expect(counts['no-executions-yet']).toBe(1);
    expect(counts['no-executable-work']).toBe(1);
  });

  test("falls back to reviewStatus for runs without executionSummary", () => {
    const runs = [
      { runId: "run-1", executionSummary: null, reviewStatus: "fully-reviewed" },
      { runId: "run-2", executionSummary: null, reviewStatus: "unreviewed" },
      { runId: "run-3", executionSummary: null, reviewStatus: "no-executions" },
    ] as any[];

    const counts = computeRunsFilterCounts(runs, true);

    expect(counts.all).toBe(3);
    expect(counts['fully-executed']).toBe(1);
    expect(counts['needs-attention']).toBe(1); // unreviewed
    expect(counts['no-executions-yet']).toBe(1);
  });

  test("executionSummary takes precedence over stale reviewStatus - fully-executed vs no-executions", () => {
    // Regression test: when executionSummary says "fully-executed" but reviewStatus is "no-executions",
    // the run should match "fully-executed" filter, NOT "no-executions-yet"
    const runs = [
      {
        runId: "run-stale-1",
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 5,
          failedCandidates: 0,
          pendingExecutableCandidates: 0,
          batchExecutionState: "fully-executed",
        },
        reviewStatus: "no-executions", // stale legacy status
      },
    ] as any[];

    const counts = computeRunsFilterCounts(runs, true);

    // executionSummary takes precedence - should be counted as "fully-executed"
    expect(counts['fully-executed']).toBe(1);
    expect(counts['no-executions-yet']).toBe(0); // NOT counted via reviewStatus fallback
  });

  test("executionSummary takes precedence over stale reviewStatus - needs-attention vs fully-reviewed", () => {
    // Regression test: when executionSummary says "needs-attention" but reviewStatus is "fully-reviewed",
    // the run should match "needs-attention" filter, NOT "fully-executed"
    const runs = [
      {
        runId: "run-stale-2",
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 5,
          failedCandidates: 2,
          pendingExecutableCandidates: 0,
          batchExecutionState: "fully-executed",
        },
        reviewStatus: "fully-reviewed", // stale legacy status
      },
    ] as any[];

    const counts = computeRunsFilterCounts(runs, true);

    // executionSummary takes precedence - should be counted as "needs-attention"
    expect(counts['needs-attention']).toBe(1);
    expect(counts['fully-executed']).toBe(0); // NOT counted via reviewStatus fallback
  });
});
