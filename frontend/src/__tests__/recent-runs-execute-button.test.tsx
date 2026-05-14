/**
 * Regression test: Recent runs Execute button visibility.
 *
 * Background: The Execute button should show for runs with executionSummary
 * indicating pending work. When executionSummary is present, button state
 * derives from:
 * - not-started + pending > 0 => Execute
 * - partially-executed + pending > 0 => Resume
 * - fully-executed / no pending => hide Execute
 *
 * This test ensures the Execute button correctly responds to executionSummary.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { RecentRunsPanel } from "../components/RunsPanel";
import type { RunsListEntry } from "../types";
import type { RunsReviewFilter } from "../hooks/useRunSelection";

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
  executionSummary: null,
  ...overrides,
});

// Common filter counts for single-run tests with new filter types
const singleFilterCounts: Record<RunsReviewFilter, number> = {
  all: 1,
  "no-executable-work": 0,
  "no-executions-yet": 1,
  "partially-executed": 0,
  "fully-executed": 0,
  "needs-attention": 0,
};

describe("Recent runs Execute button visibility", () => {
  test("shows Execute button when executionSummary indicates not-started with pending work", () => {
    // Arrange: Create a run with executionSummary=not-started and pending work
    const runsList: RunsListEntry[] = [
      createRunEntry("run-with-candidates", {
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 0,
          failedCandidates: 0,
          pendingExecutableCandidates: 5,
          batchExecutionState: "not-started",
        },
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

    // Assert: Execute button should be visible (filter for row-action context)
    const executeButtons = screen.getAllByRole("button", { name: /execute/i });
    const rowExecuteButton = executeButtons.find(btn => btn.closest(".row-action") !== null);
    expect(rowExecuteButton).toBeInTheDocument();

    // Clicking should call onBatchExecution
    rowExecuteButton!.click();
    expect(onBatchExecution).toHaveBeenCalledWith("run-with-candidates");
  });

  test("shows Resume button when executionSummary indicates partially-executed with pending work", () => {
    // Arrange: Create a run with partially-executed state
    const runsList: RunsListEntry[] = [
      createRunEntry("run-partial", {
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 3,
          failedCandidates: 0,
          pendingExecutableCandidates: 2,
          batchExecutionState: "partially-executed",
        },
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
        runsFilterCounts={{
          all: 1,
          "no-executable-work": 0,
          "no-executions-yet": 0,
          "partially-executed": 1,
          "fully-executed": 0,
          "needs-attention": 0,
        }}
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

    // Assert: Resume button should be visible
    expect(screen.getByRole("button", { name: /resume/i })).toBeInTheDocument();
  });

  test("shows dash (—) when run is fully-executed without pending work", () => {
    // Arrange: Create a fully-executed run
    const runsList: RunsListEntry[] = [
      createRunEntry("run-reviewed", {
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 5,
          failedCandidates: 0,
          pendingExecutableCandidates: 0,
          batchExecutionState: "fully-executed",
        },
      }),
    ];

    // Act
    render(
      <RecentRunsPanel
        runsList={runsList}
        executionCountsComplete={true}
        selectedRunId={null}
        runsFilter="all"
        runsFilterCounts={{
          all: 1,
          "no-executable-work": 0,
          "no-executions-yet": 0,
          "partially-executed": 0,
          "fully-executed": 1,
          "needs-attention": 0,
        }}
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

    // Assert: No Execute button in row-action context, dash should be shown in the Action column
    const executeButtons = screen.queryAllByRole("button", { name: /execute/i });
    const rowExecuteButtons = executeButtons.filter(btn => btn.closest(".row-action") !== null);
    expect(rowExecuteButtons.length).toBe(0);
    expect(screen.queryByRole("button", { name: /resume/i })).not.toBeInTheDocument();
    // Use getAllByText since both Review and Action columns may show "—" for runs without downloads
    const dashes = screen.getAllByText("—", { selector: '[aria-label="No action available"]' });
    // At least one dash should be in the Action column
    expect(dashes.length).toBeGreaterThan(0);
  });

  test("shows 'Running…' when batch execution is in progress for this run", () => {
    // Arrange
    const runsList: RunsListEntry[] = [
      createRunEntry("run-executing", {
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 0,
          failedCandidates: 0,
          pendingExecutableCandidates: 5,
          batchExecutionState: "not-started",
        },
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
    const runsList: RunsListEntry[] = [
      createRunEntry("run-1", {
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 2,
          executedCandidates: 0,
          failedCandidates: 0,
          pendingExecutableCandidates: 2,
          batchExecutionState: "not-started",
        },
      }),
      createRunEntry("run-2", {
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 5,
          failedCandidates: 0,
          pendingExecutableCandidates: 0,
          batchExecutionState: "fully-executed",
        },
      }),
      createRunEntry("run-3", {
        executionSummary: {
          totalCandidates: 10,
          executableCandidates: 7,
          executedCandidates: 0,
          failedCandidates: 0,
          pendingExecutableCandidates: 7,
          batchExecutionState: "not-started",
        },
      }),
    ];

    const multiFilterCounts: Record<RunsReviewFilter, number> = {
      all: 3,
      "no-executable-work": 0,
      "no-executions-yet": 2, // run-1 and run-3 have pending work
      "partially-executed": 0,
      "fully-executed": 1, // run-2 is fully-executed
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
    // run-1 and run-3 have executionSummary with pending work, run-2 doesn't
    const executeButtons = screen.getAllByRole("button", { name: /execute/i });
    // Filter to only row-action buttons (not filter bar buttons)
    const rowExecuteButtons = executeButtons.filter(btn => btn.closest(".row-action") !== null);
    expect(rowExecuteButtons.length).toBe(2);

    // Click run-3's button (it's the second one since run-1 is also executable)
    rowExecuteButtons[1].click();

    // Verify the correct runId was passed
    expect(onBatchExecution).toHaveBeenCalledWith("run-3");
  });

  test("backward compat: shows Execute for batchExecutable=true without executionSummary", () => {
    // Arrange: Legacy run without executionSummary but with batchExecutable=true
    const runsList: RunsListEntry[] = [
      createRunEntry("run-legacy", {
        executionSummary: null,
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
        runsFilterCounts={{
          all: 1,
          "no-executable-work": 0,
          "no-executions-yet": 1,
          "partially-executed": 0,
          "fully-executed": 0,
          "needs-attention": 0,
        }}
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

    // Assert: Execute button should be visible for backward compatibility (filter for row-action)
    const executeButtons = screen.getAllByRole("button", { name: /execute/i });
    const rowExecuteButton = executeButtons.find(btn => btn.closest(".row-action") !== null);
    expect(rowExecuteButton).toBeInTheDocument();
  });
});
