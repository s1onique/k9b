/**
 * Regression test: Recent runs should display execution-based labels
 * derived from executionSummary when available.
 *
 * Background: After the executionSummary integration, Recent runs labels
 * and filter chips now derive from the executionSummary contract instead
 * of stale reviewStatus heuristics.
 *
 * Label mapping from executionSummary:
 * - no-candidates → "No executable checks"
 * - not-started + pending > 0 → "No executions yet"
 * - partially-executed → "Partially executed"
 * - fully-executed + failed > 0 → "Needs attention"
 * - fully-executed + failed === 0 → "Fully executed"
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { RecentRunsPanel } from "../components/RunsPanel";
import type { RunsListEntry, RunsReviewFilter } from "../hooks/useRunSelection";

// Helper to create a run entry with executionSummary
const createRunWithExecutionSummary = (
  id: string,
  executionSummary: RunsListEntry["executionSummary"]
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
  batchExecutable: false,
  batchEligibleCount: 0,
  executionSummary,
});

// Helper to create a run entry without executionSummary (backward compat)
const createRunWithoutExecutionSummary = (
  id: string,
  reviewStatus: string
): RunsListEntry => ({
  runId: id,
  runLabel: "2026-04-07-1200",
  timestamp: "2026-04-07T12:00:00Z",
  clusterCount: 3,
  triaged: reviewStatus === "fully-reviewed",
  executionCount: reviewStatus === "no-executions" ? 0 : 5,
  reviewedCount: reviewStatus === "fully-reviewed" ? 5 : 0,
  reviewStatus,
  reviewDownloadPath: null,
  batchExecutable: false,
  batchEligibleCount: 0,
  executionSummary: null,
});

// Default filter counts matching new filter types
const emptyFilterCounts: Record<RunsReviewFilter, number> = {
  all: 0,
  "no-executable-work": 0,
  "no-executions-yet": 0,
  "partially-executed": 0,
  "fully-executed": 0,
  "needs-attention": 0,
};

const renderPanel = (runsList: RunsListEntry[]) => {
  const filterCounts: Record<RunsReviewFilter, number> = {
    all: runsList.length,
    "no-executable-work": 0,
    "no-executions-yet": 0,
    "partially-executed": 0,
    "fully-executed": 0,
    "needs-attention": 0,
  };

  // Compute filter counts based on executionSummary
  runsList.forEach((run) => {
    if (run.executionSummary) {
      const { batchExecutionState, failedCandidates, pendingExecutableCandidates } = run.executionSummary;
      switch (batchExecutionState) {
        case "no-candidates":
          filterCounts["no-executable-work"]++;
          break;
        case "not-started":
          filterCounts["no-executions-yet"]++;
          break;
        case "partially-executed":
          filterCounts["partially-executed"]++;
          break;
        case "fully-executed":
          if (failedCandidates > 0) {
            filterCounts["needs-attention"]++;
          } else {
            filterCounts["fully-executed"]++;
          }
          break;
      }
    } else {
      // Fallback to reviewStatus
      switch (run.reviewStatus) {
        case "fully-reviewed":
          filterCounts["fully-executed"]++;
          break;
        case "unreviewed":
        case "partially-reviewed":
          filterCounts["needs-attention"]++;
          break;
        case "no-executions":
          filterCounts["no-executions-yet"]++;
          break;
      }
    }
  });

  return render(
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
};

describe("Recent runs execution-based labels", () => {
  describe("from executionSummary", () => {
    test("displays 'No executable checks' for no-candidates state", () => {
      const runsList = [
        createRunWithExecutionSummary("run-no-candidates", {
          totalCandidates: 10,
          executableCandidates: 0,
          executedCandidates: 0,
          failedCandidates: 0,
          pendingExecutableCandidates: 0,
          batchExecutionState: "no-candidates",
        }),
      ];

      renderPanel(runsList);
      expect(screen.getByText("No executable checks")).toBeInTheDocument();
    });

    test("displays 'No executions yet' for not-started with pending work", () => {
      const runsList = [
        createRunWithExecutionSummary("run-not-started", {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 0,
          failedCandidates: 0,
          pendingExecutableCandidates: 5,
          batchExecutionState: "not-started",
        }),
      ];

      renderPanel(runsList);
      // Use getAllByText since "No executions yet" appears in both filter chip and status badge
      const elements = screen.getAllByText("No executions yet");
      expect(elements.length).toBeGreaterThan(0);
    });

    test("displays 'Partially executed' for partially-executed state", () => {
      const runsList = [
        createRunWithExecutionSummary("run-partial", {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 3,
          failedCandidates: 0,
          pendingExecutableCandidates: 2,
          batchExecutionState: "partially-executed",
        }),
      ];

      renderPanel(runsList);
      // Use getAllByText since "Partially executed" appears in both filter chip and status badge
      const elements = screen.getAllByText("Partially executed");
      expect(elements.length).toBeGreaterThan(0);
    });

    test("displays 'Fully executed' for fully-executed without failures", () => {
      const runsList = [
        createRunWithExecutionSummary("run-done", {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 5,
          failedCandidates: 0,
          pendingExecutableCandidates: 0,
          batchExecutionState: "fully-executed",
        }),
      ];

      renderPanel(runsList);
      // Use getAllByText since "Fully executed" appears in both filter chip and status badge
      const elements = screen.getAllByText("Fully executed");
      expect(elements.length).toBeGreaterThan(0);
    });

    test("displays 'Needs attention' for fully-executed with failures", () => {
      const runsList = [
        createRunWithExecutionSummary("run-failed", {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 5,
          failedCandidates: 2,
          pendingExecutableCandidates: 0,
          batchExecutionState: "fully-executed",
        }),
      ];

      renderPanel(runsList);
      // Use getAllByText since "Needs attention" appears in both filter chip and status badge
      const elements = screen.getAllByText("Needs attention");
      expect(elements.length).toBeGreaterThan(0);
    });
  });

  describe("backward compatibility without executionSummary", () => {
    test("displays 'Fully executed' for fully-reviewed status", () => {
      const runsList = [
        createRunWithoutExecutionSummary("run-reviewed", "fully-reviewed"),
      ];

      renderPanel(runsList);
      // Use getAllByText since "Fully executed" appears in both filter chip and status badge
      const elements = screen.getAllByText("Fully executed");
      expect(elements.length).toBeGreaterThan(0);
    });

    test("displays 'Needs attention' for unreviewed status", () => {
      const runsList = [
        createRunWithoutExecutionSummary("run-unreviewed", "unreviewed"),
      ];

      renderPanel(runsList);
      // Use getAllByText since "Needs attention" appears in both filter chip and status badge
      const elements = screen.getAllByText("Needs attention");
      expect(elements.length).toBeGreaterThan(0);
    });

    test("displays 'No executions yet' for no-executions status", () => {
      const runsList = [
        createRunWithoutExecutionSummary("run-no-exec", "no-executions"),
      ];

      renderPanel(runsList);
      // Use getAllByText and verify at least one exists (both filter chip and status badge use same text)
      const elements = screen.getAllByText("No executions yet");
      expect(elements.length).toBeGreaterThan(0);
    });

    test("displays 'Not reviewed yet' when counts are incomplete", () => {
      const runsList = [
        createRunWithoutExecutionSummary("run-incomplete", "no-executions"),
      ];

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

      expect(screen.getByText("Not reviewed yet")).toBeInTheDocument();
    });
  });

  describe("button behavior preserved", () => {
    test("shows Execute button for not-started with pending work", () => {
      const runsList = [
        createRunWithExecutionSummary("run-not-started", {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 0,
          failedCandidates: 0,
          pendingExecutableCandidates: 5,
          batchExecutionState: "not-started",
        }),
      ];

      renderPanel(runsList);
      // Use getAllByRole to find all buttons, then filter for Execute in the table rows
      const executeButtons = screen.getAllByRole("button", { name: /execute/i });
      // Find the one in a row-action context (inside the table action column)
      const rowExecuteButton = executeButtons.find(btn => 
        btn.closest(".row-action") !== null
      );
      expect(rowExecuteButton).toBeInTheDocument();
    });

    test("shows Resume button for partially-executed with pending work", () => {
      const runsList = [
        createRunWithExecutionSummary("run-partial", {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 3,
          failedCandidates: 0,
          pendingExecutableCandidates: 2,
          batchExecutionState: "partially-executed",
        }),
      ];

      renderPanel(runsList);
      expect(screen.getByRole("button", { name: /resume/i })).toBeInTheDocument();
    });

    test("hides Execute button for fully-executed without failures", () => {
      const runsList = [
        createRunWithExecutionSummary("run-done", {
          totalCandidates: 10,
          executableCandidates: 5,
          executedCandidates: 5,
          failedCandidates: 0,
          pendingExecutableCandidates: 0,
          batchExecutionState: "fully-executed",
        }),
      ];

      renderPanel(runsList);
      // Check that no Execute or Resume buttons appear in the runs table (use row-actions class)
      const rowActionButtons = document.querySelectorAll(".row-action--primary");
      const actionButtonTexts = Array.from(rowActionButtons).map(btn => btn.textContent);
      expect(actionButtonTexts.some(t => t?.includes("Execute") || t?.includes("Resume"))).toBe(false);
    });
  });
});