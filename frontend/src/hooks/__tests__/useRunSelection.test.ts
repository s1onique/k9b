/**
 * useRunSelection hook tests
 *
 * Tests for getRunsDisplayStatus and computeRunsFilterCounts functions
 * that handle executionCountsComplete flag for truthful UI rendering.
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
  ...overrides,
});

describe("getRunsDisplayStatus", () => {
  describe("when executionCountsComplete is true", () => {
    it("returns the raw reviewStatus for fully-reviewed", () => {
      const result = getRunsDisplayStatus("fully-reviewed", true);
      expect(result).toBe("fully-reviewed");
    });

    it("returns the raw reviewStatus for partially-reviewed", () => {
      const result = getRunsDisplayStatus("partially-reviewed", true);
      expect(result).toBe("partially-reviewed");
    });

    it("returns the raw reviewStatus for unreviewed", () => {
      const result = getRunsDisplayStatus("unreviewed", true);
      expect(result).toBe("unreviewed");
    });

    it("returns 'no-executions' when executionCount is legitimately zero", () => {
      const result = getRunsDisplayStatus("no-executions", true);
      expect(result).toBe("no-executions");
    });
  });

  describe("when executionCountsComplete is false", () => {
    it("returns 'unknown' for no-executions (ambiguous - may be untracked)", () => {
      const result = getRunsDisplayStatus("no-executions", false);
      expect(result).toBe("unknown");
    });

    it("preserves 'fully-reviewed' status when counts are incomplete", () => {
      const result = getRunsDisplayStatus("fully-reviewed", false);
      expect(result).toBe("fully-reviewed");
    });

    it("preserves 'partially-reviewed' status when counts are incomplete", () => {
      const result = getRunsDisplayStatus("partially-reviewed", false);
      expect(result).toBe("partially-reviewed");
    });

    it("preserves 'unreviewed' status when counts are incomplete", () => {
      const result = getRunsDisplayStatus("unreviewed", false);
      expect(result).toBe("unreviewed");
    });
  });
});

describe("computeRunsFilterCounts", () => {
  const runsWithVariousStatuses: RunsListEntry[] = [
    createRunEntry({ runId: "run-1", reviewStatus: "fully-reviewed" }),
    createRunEntry({ runId: "run-2", reviewStatus: "partially-reviewed" }),
    createRunEntry({ runId: "run-3", reviewStatus: "unreviewed" }),
    createRunEntry({ runId: "run-4", reviewStatus: "no-executions" }),
    createRunEntry({ runId: "run-5", reviewStatus: "no-executions" }),
  ];

  it("counts all statuses correctly when counts are complete", () => {
    const counts = computeRunsFilterCounts(runsWithVariousStatuses, true);

    expect(counts.all).toBe(5);
    expect(counts["no-executions"]).toBe(2);
    expect(counts["awaiting-review"]).toBe(1);
    expect(counts["partially-reviewed"]).toBe(1);
    expect(counts["fully-reviewed"]).toBe(1);
    expect(counts["needs-attention"]).toBe(2); // unreviewed + partially-reviewed
  });

  it("excludes no-executions from filter count when counts are incomplete", () => {
    const counts = computeRunsFilterCounts(runsWithVariousStatuses, false);

    expect(counts.all).toBe(5); // All runs still visible
    expect(counts["no-executions"]).toBe(0); // Excluded - untrustworthy
    expect(counts["awaiting-review"]).toBe(1);
    expect(counts["partially-reviewed"]).toBe(1);
    expect(counts["fully-reviewed"]).toBe(1);
    expect(counts["needs-attention"]).toBe(2);
  });

  it("handles empty runs list", () => {
    const counts = computeRunsFilterCounts([], true);

    expect(counts.all).toBe(0);
    expect(counts["no-executions"]).toBe(0);
    expect(counts["awaiting-review"]).toBe(0);
    expect(counts["partially-reviewed"]).toBe(0);
    expect(counts["fully-reviewed"]).toBe(0);
    expect(counts["needs-attention"]).toBe(0);
  });

  it("defaults executionCountsComplete to true", () => {
    // When called without second argument, should behave as if counts are complete
    const countsWithDefault = computeRunsFilterCounts([
      createRunEntry({ reviewStatus: "no-executions" }),
    ]);
    const countsExplicit = computeRunsFilterCounts(
      [createRunEntry({ reviewStatus: "no-executions" })],
      true
    );

    expect(countsWithDefault["no-executions"]).toBe(1);
    expect(countsExplicit["no-executions"]).toBe(1);
  });
});
