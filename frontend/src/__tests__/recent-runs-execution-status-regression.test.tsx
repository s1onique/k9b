/**
 * Regression test: Recent runs should not display "Execution Status Not Loaded"
 * for runs with missing/unknown execution status.
 *
 * Background: After the run-list ownership cleanup, Recent runs renders from
 * the fast/index-backed runs list. The run list may intentionally omit expensive
 * execution review/status derivation. When execution status is absent because
 * the fast path skipped it, the UI should display a neutral fallback like
 * "Not reviewed yet" - NOT "Execution Status Not Loaded".
 *
 * This test ensures that the internal placeholder text never leaks to users.
 *
 * Note: We intentionally do NOT mock getRunsDisplayStatus here. This test
 * exercises the real integration path so StatusBadge is tested with the
 * actual fallback behavior.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { RecentRunsPanel } from "../components/RunsPanel";
import type { RunsListEntry, RunsReviewFilter } from "../types";

// Create a run with "no-executions" status for testing the unknown state
const createRunWithUnknownStatus = (id: string): RunsListEntry => ({
  runId: id,
  runLabel: "2026-04-07-1200",
  timestamp: "2026-04-07T12:00:00Z",
  clusterCount: 3,
  triaged: false,
  executionCount: 0,
  reviewedCount: 0,
  reviewStatus: "no-executions", // This should map to "unknown" display status when executionCountsComplete is false
  reviewDownloadPath: null,
  batchEligibility: "unknown",
  batchExecutable: false,
  batchEligibleCount: 0,
});

const createRunWithRealStatus = (id: string, status: string): RunsListEntry => ({
  runId: id,
  runLabel: "2026-04-07-1200",
  timestamp: "2026-04-07T12:00:00Z",
  clusterCount: 3,
  triaged: status === "fully-reviewed",
  executionCount: status === "no-executions" ? 0 : 5,
  reviewedCount: status === "fully-reviewed" ? 5 : 0,
  reviewStatus: status,
  reviewDownloadPath: null,
  batchEligibility: "unknown",
  batchExecutable: false,
  batchEligibleCount: 0,
});

describe("Recent runs execution status regression", () => {
  test("should NOT display 'Execution status not loaded' for unknown status", () => {
    // Arrange: Create a runs list with incomplete execution counts
    const runsList: RunsListEntry[] = [
      createRunWithUnknownStatus("run-incomplete"),
    ];

    const emptyFilterCounts: Record<RunsReviewFilter, number> = {
      "all": 1,
      "no-executions": 0,
      "awaiting-review": 0,
      "partially-reviewed": 0,
      "fully-reviewed": 0,
      "needs-attention": 0,
    };

    // Act: Render with executionCountsComplete=false (the fast path scenario)
    render(
      <RecentRunsPanel
        runsList={runsList}
        executionCountsComplete={false} // Simulates fast path where counts weren't computed
        selectedRunId={null}
        runsFilter="all"
        runsFilterCounts={emptyFilterCounts}
        paginatedRunsList={runsList}
        filteredRunsList={runsList}
        runsListLoading={false}
        runsListError={null}
        runsPage={1}
        totalRunsPages={1}
        runsPageSize={5}
        isRunsListFollowingSelection={true}
        isSelectedRunVisibleOnCurrentRunsPage={true}
        executingBatchRunId={null}
        batchExecutionError={{}}
        onRunsFilterChange={() => {}}
        onRunsPageChange={() => {}}
        onRunsPageSizeChange={() => {}}
        onRunSelection={() => {}}
        onBatchExecution={() => {}}
        onShowSelectedRun={() => {}}
        onFocusClusterForNextChecks={() => {}}
      />
    );

    // Assert: The forbidden text should NOT appear anywhere
    expect(
      screen.queryByText(/Execution Status Not Loaded/i)
    ).not.toBeInTheDocument();

    // Assert: The neutral fallback "Not reviewed yet" should appear
    expect(
      screen.getByText("Not reviewed yet")
    ).toBeInTheDocument();
  });

  test("should display 'Not reviewed yet' when execution counts are incomplete", () => {
    // Arrange
    const runsList: RunsListEntry[] = [
      createRunWithUnknownStatus("run-fast-path"),
    ];

    const emptyFilterCounts: Record<RunsReviewFilter, number> = {
      "all": 1,
      "no-executions": 0,
      "awaiting-review": 0,
      "partially-reviewed": 0,
      "fully-reviewed": 0,
      "needs-attention": 0,
    };

    // Act
    render(
      <RecentRunsPanel
        runsList={runsList}
        executionCountsComplete={false}
        selectedRunId={null}
        runsFilter="all"
        runsFilterCounts={emptyFilterCounts}
        paginatedRunsList={runsList}
        filteredRunsList={runsList}
        runsListLoading={false}
        runsListError={null}
        runsPage={1}
        totalRunsPages={1}
        runsPageSize={5}
        isRunsListFollowingSelection={true}
        isSelectedRunVisibleOnCurrentRunsPage={true}
        executingBatchRunId={null}
        batchExecutionError={{}}
        onRunsFilterChange={() => {}}
        onRunsPageChange={() => {}}
        onRunsPageSizeChange={() => {}}
        onRunSelection={() => {}}
        onBatchExecution={() => {}}
        onShowSelectedRun={() => {}}
        onFocusClusterForNextChecks={() => {}}
      />
    );

    // Assert: Should display "Not reviewed yet"
    expect(screen.getByText("Not reviewed yet")).toBeInTheDocument();
  });

  test("should still display real statuses when execution counts are complete", () => {
    // Arrange: Runs with complete execution counts
    const runsList: RunsListEntry[] = [
      createRunWithRealStatus("run-reviewed", "fully-reviewed"),
      createRunWithRealStatus("run-unreviewed", "unreviewed"),
      createRunWithRealStatus("run-partial", "partially-reviewed"),
      createRunWithRealStatus("run-no-exec", "no-executions"),
    ];

    const filterCounts: Record<RunsReviewFilter, number> = {
      "all": 4,
      "no-executions": 1,
      "awaiting-review": 1,
      "partially-reviewed": 1,
      "fully-reviewed": 1,
      "needs-attention": 2,
    };

    // Act: Render with executionCountsComplete=true (full path)
    render(
      <RecentRunsPanel
        runsList={runsList}
        executionCountsComplete={true}
        selectedRunId={null}
        runsFilter="all"
        runsFilterCounts={filterCounts}
        paginatedRunsList={runsList}
        filteredRunsList={runsList}
        runsListLoading={false}
        runsListError={null}
        runsPage={1}
        totalRunsPages={1}
        runsPageSize={5}
        isRunsListFollowingSelection={true}
        isSelectedRunVisibleOnCurrentRunsPage={true}
        executingBatchRunId={null}
        batchExecutionError={{}}
        onRunsFilterChange={() => {}}
        onRunsPageChange={() => {}}
        onRunsPageSizeChange={() => {}}
        onRunSelection={() => {}}
        onBatchExecution={() => {}}
        onShowSelectedRun={() => {}}
        onFocusClusterForNextChecks={() => {}}
      />
    );

    // Assert: The forbidden text should NOT appear
    expect(
      screen.queryByText(/Execution Status Not Loaded/i)
    ).not.toBeInTheDocument();

    // Assert: Real statuses should still display correctly
    expect(screen.getAllByText("Fully reviewed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Awaiting review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Partially reviewed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("No executions").length).toBeGreaterThan(0);
  });
});
