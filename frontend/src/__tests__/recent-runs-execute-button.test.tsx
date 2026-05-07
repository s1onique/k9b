/**
 * Regression test: Recent runs Execute button visibility.
 *
 * Background: The Execute button should show for runs with batchExecutable=true
 * (eligible candidates from batch eligibility scan), even if the reviewStatus
 * is not "no-executions".
 *
 * This test ensures the Execute button correctly responds to batchExecutable.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { RecentRunsPanel } from "../components/RunsPanel";
import type { RunsListEntry, RunsReviewFilter } from "../types";

// Helper to create a basic run entry with optional batchExecutable override
const createRunEntry = (
  id: string,
  overrides: Partial<RunsListEntry> = {}
): RunsListEntry => ({
  runId: id,
  runLabel: "2026-04-07-1200",
  timestamp: "2026-04-07T12:00:00Z",
  clusterCount: 3,
  triaged: false,
  executionCount: 0,
  reviewedCount: 0,
  reviewStatus: "no-executions",
  reviewDownloadPath: null,
  batchEligibility: "unknown",
  batchExecutable: false,
  batchEligibleCount: 0,
  ...overrides,
});

// Common filter counts for single-run tests
const singleFilterCounts: Record<RunsReviewFilter, number> = {
  "all": 1,
  "no-executions": 1,
  "awaiting-review": 0,
  "partially-reviewed": 0,
  "fully-reviewed": 0,
  "needs-attention": 0,
};

describe("Recent runs Execute button visibility", () => {
  test("shows Execute button when batchExecutable is true", () => {
    // Arrange: Create a run with batchExecutable=true (has eligible candidates)
    const runsList: RunsListEntry[] = [
      createRunEntry("run-with-candidates", {
        batchExecutable: true,
        batchEligibleCount: 5,
      }),
    ];

    const onBatchExecution = vi.fn();

    // Act
    render(
      <RecentRunsPanel
        runsList={runsList}
        executionCountsComplete={true}
        selectedRunId={null}
        runsFilter="all"
        runsFilterCounts={singleFilterCounts}
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
        onBatchExecution={onBatchExecution}
        onShowSelectedRun={() => {}}
        onFocusClusterForNextChecks={() => {}}
      />
    );

    // Assert: Execute button should be visible
    const executeButton = screen.getByRole("button", { name: /execute/i });
    expect(executeButton).toBeInTheDocument();

    // Clicking should call onBatchExecution
    executeButton.click();
    expect(onBatchExecution).toHaveBeenCalledWith("run-with-candidates");
  });

  test("shows Execute button when reviewStatus is 'no-executions'", () => {
    // Arrange: Create a run with no-executions status (hasn't run any checks yet)
    const runsList: RunsListEntry[] = [
      createRunEntry("run-no-executions", {
        reviewStatus: "no-executions",
        batchExecutable: false,
      }),
    ];

    const onBatchExecution = vi.fn();

    // Act
    render(
      <RecentRunsPanel
        runsList={runsList}
        executionCountsComplete={true}
        selectedRunId={null}
        runsFilter="all"
        runsFilterCounts={singleFilterCounts}
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
        onBatchExecution={onBatchExecution}
        onShowSelectedRun={() => {}}
        onFocusClusterForNextChecks={() => {}}
      />
    );

    // Assert: Execute button should be visible
    expect(screen.getByRole("button", { name: /execute/i })).toBeInTheDocument();
  });

  test("shows dash (—) when run is not executable and has executions", () => {
    // Arrange: Create a run that has been executed (reviewed) - no need to execute again
    const runsList: RunsListEntry[] = [
      createRunEntry("run-reviewed", {
        reviewStatus: "fully-reviewed",
        executionCount: 5,
        reviewedCount: 5,
        triaged: true,
        batchExecutable: false,
      }),
    ];

    const filterCountsReviewed: Record<RunsReviewFilter, number> = {
      "all": 1,
      "no-executions": 0,
      "awaiting-review": 0,
      "partially-reviewed": 0,
      "fully-reviewed": 1,
      "needs-attention": 0,
    };

    // Act
    render(
      <RecentRunsPanel
        runsList={runsList}
        executionCountsComplete={true}
        selectedRunId={null}
        runsFilter="all"
        runsFilterCounts={filterCountsReviewed}
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

    // Assert: No Execute button, dash should be shown in the Action column
    expect(screen.queryByRole("button", { name: /execute/i })).not.toBeInTheDocument();
    // Use getAllByText since both Review and Action columns may show "—" for runs without downloads
    const dashes = screen.getAllByText("—", { selector: '[aria-label="No action available"]' });
    // At least one dash should be in the Action column
    expect(dashes.length).toBeGreaterThan(0);
  });

  test("shows 'Running…' when batch execution is in progress for this run", () => {
    // Arrange
    const runsList: RunsListEntry[] = [
      createRunEntry("run-executing", {
        batchExecutable: true,
        batchEligibleCount: 3,
      }),
    ];

    // Act: Render with executingBatchRunId set to this run
    render(
      <RecentRunsPanel
        runsList={runsList}
        executionCountsComplete={true}
        selectedRunId={null}
        runsFilter="all"
        runsFilterCounts={singleFilterCounts}
        paginatedRunsList={runsList}
        filteredRunsList={runsList}
        runsListLoading={false}
        runsListError={null}
        runsPage={1}
        totalRunsPages={1}
        runsPageSize={5}
        isRunsListFollowingSelection={true}
        isSelectedRunVisibleOnCurrentRunsPage={true}
        executingBatchRunId="run-executing" // This run is being executed
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

    // Assert: Button should show "Running…" and be disabled
    const button = screen.getByRole("button", { name: /running/i });
    expect(button).toBeInTheDocument();
    expect(button).toBeDisabled();
  });

  test("Execute button calls onBatchExecution with correct runId", () => {
    // Arrange: Multiple runs with different states
    // run-1: batchExecutable=true -> shows Execute
    // run-2: batchExecutable=false, reviewStatus=fully-reviewed -> shows dash
    // run-3: batchExecutable=true -> shows Execute
    const runsList: RunsListEntry[] = [
      createRunEntry("run-1", { batchExecutable: true, batchEligibleCount: 2 }),
      createRunEntry("run-2", { 
        batchExecutable: false, 
        reviewStatus: "fully-reviewed",
        executionCount: 5,
        reviewedCount: 5,
        triaged: true,
      }),
      createRunEntry("run-3", { batchExecutable: true, batchEligibleCount: 7 }),
    ];

    const multiFilterCounts: Record<RunsReviewFilter, number> = {
      "all": 3,
      "no-executions": 1,
      "awaiting-review": 0,
      "partially-reviewed": 0,
      "fully-reviewed": 1,  // run-2 is fully-reviewed
      "needs-attention": 0,
    };

    const onBatchExecution = vi.fn();

    // Act
    render(
      <RecentRunsPanel
        runsList={runsList}
        executionCountsComplete={true}
        selectedRunId={null}
        runsFilter="all"
        runsFilterCounts={multiFilterCounts}
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
        onBatchExecution={onBatchExecution}
        onShowSelectedRun={() => {}}
        onFocusClusterForNextChecks={() => {}}
      />
    );

    // Find the Execute button for run-3 and click it
    // run-1 and run-3 have batchExecutable=true, run-2 doesn't
    const executeButtons = screen.getAllByRole("button", { name: /execute/i });
    expect(executeButtons.length).toBe(2);

    // Click run-3's button (it's the second one since run-1 is also executable)
    executeButtons[1].click();

    // Verify the correct runId was passed
    expect(onBatchExecution).toHaveBeenCalledWith("run-3");
  });
});
