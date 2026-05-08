/**
 * stale-while-refresh.test.tsx
 *
 * Regression tests for stale-while-refresh behavior in RecentRunsPanel.
 *
 * Goal:
 * - First load with no rows: show "Loading runs..."
 * - Second and subsequent loads: keep existing table visible while refresh happens in background
 * - When new data arrives: update rows atomically
 * - Do not clear existing runs state at refresh start
 * - Preserve Execute buttons and pagination
 * - Optional: show a subtle "Refreshing…" indicator near the Recent Runs title
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecentRunsPanel } from "../components/RunsPanel";
import type { RunsListEntry } from "../types";

// Helper to create a minimal runs list entry
const createRunEntry = (overrides: Partial<RunsListEntry> = {}): RunsListEntry => ({
  runId: "run-001",
  runLabel: "001",
  label: "001",
  timestamp: "2026-01-01T00:00:00Z",
  reviewStatus: "unreviewed",
  reviewDownloadPath: null,
  batchExecutable: false,
  ...overrides,
});

const defaultRuns: RunsListEntry[] = [
  createRunEntry({ runId: "run-001", runLabel: "001", reviewStatus: "unreviewed", batchExecutable: true }),
  createRunEntry({ runId: "run-002", runLabel: "002", reviewStatus: "fully-reviewed", batchExecutable: false }),
  createRunEntry({ runId: "run-003", runLabel: "003", reviewStatus: "partially-reviewed", batchExecutable: false }),
];

const defaultProps = {
  runsList: defaultRuns,
  executionCountsComplete: true,
  selectedRunId: null as string | null,
  runsFilter: "all" as const,
  runsFilterCounts: { all: 3, "no-executions": 0, "awaiting-review": 1, "partially-reviewed": 1, "fully-reviewed": 1, "needs-attention": 2 },
  paginatedRunsList: defaultRuns,
  filteredRunsList: defaultRuns,
  runsListLoading: false,
  runsListError: null as string | null,
  runsPage: 1,
  totalRunsPages: 1,
  runsPageSize: 10,
  isRunsListFollowingSelection: true,
  isSelectedRunVisibleOnCurrentRunsPage: true,
  executingBatchRunId: null as string | null,
  batchExecutionError: {} as Record<string, string>,
  onRunsFilterChange: vi.fn(),
  onRunsPageChange: vi.fn(),
  onRunsPageSizeChange: vi.fn(),
  onRunSelection: vi.fn(),
  onBatchExecution: vi.fn(),
  onShowSelectedRun: vi.fn(),
  onFocusClusterForNextChecks: vi.fn(),
};

describe("stale-while-refresh behavior for Recent Runs panel", () => {
  describe("initial loading state", () => {
    it("shows 'Loading runs...' when loading and no rows exist", () => {
      render(
        <RecentRunsPanel
          {...defaultProps}
          runsList={[]}
          paginatedRunsList={[]}
          filteredRunsList={[]}
          runsListLoading={true}
          runsListRefreshing={false}
        />
      );

      expect(screen.getByText("Loading runs...")).toBeInTheDocument();
    });

    it("does NOT show table when loading with no rows", () => {
      render(
        <RecentRunsPanel
          {...defaultProps}
          runsList={[]}
          paginatedRunsList={[]}
          filteredRunsList={[]}
          runsListLoading={true}
          runsListRefreshing={false}
        />
      );

      expect(screen.queryByRole("table")).not.toBeInTheDocument();
    });
  });

  describe("stale-while-refresh on subsequent loads", () => {
    it("keeps existing table visible during refresh with existing rows", () => {
      render(
        <RecentRunsPanel
          {...defaultProps}
          runsListLoading={true}
          runsListRefreshing={true}
        />
      );

      // Table should still be visible
      expect(screen.getByRole("table")).toBeInTheDocument();
    });

    it("does NOT show 'Loading runs...' when refreshing with existing rows", () => {
      render(
        <RecentRunsPanel
          {...defaultProps}
          runsListLoading={true}
          runsListRefreshing={true}
        />
      );

      expect(screen.queryByText("Loading runs...")).not.toBeInTheDocument();
    });

    it("shows subtle 'Refreshing…' indicator during background refresh", () => {
      render(
        <RecentRunsPanel
          {...defaultProps}
          runsListLoading={true}
          runsListRefreshing={true}
        />
      );

      expect(screen.getByText("Refreshing…")).toBeInTheDocument();
    });

    it("does NOT show 'Refreshing…' indicator when not refreshing", () => {
      render(
        <RecentRunsPanel
          {...defaultProps}
          runsListLoading={false}
          runsListRefreshing={false}
        />
      );

      expect(screen.queryByText("Refreshing…")).not.toBeInTheDocument();
    });

    it("does NOT show 'Refreshing…' indicator on initial load with no rows", () => {
      render(
        <RecentRunsPanel
          {...defaultProps}
          runsList={[]}
          paginatedRunsList={[]}
          filteredRunsList={[]}
          runsListLoading={true}
          runsListRefreshing={false}
        />
      );

      expect(screen.queryByText("Refreshing…")).not.toBeInTheDocument();
    });
  });

  describe("Execute buttons preserved during refresh", () => {
    it("preserves Execute buttons during background refresh", () => {
      render(
        <RecentRunsPanel
          {...defaultProps}
          runsListLoading={true}
          runsListRefreshing={true}
        />
      );

      // Find the Execute button on run-001 which has batchExecutable: true
      const executeButtons = screen.getAllByRole("button", { name: /execute/i });
      expect(executeButtons.length).toBeGreaterThan(0);
    });

    it("Execute button remains enabled during background refresh", () => {
      render(
        <RecentRunsPanel
          {...defaultProps}
          runsListLoading={true}
          runsListRefreshing={true}
        />
      );

      const executeButton = screen.getByRole("button", { name: /execute/i });
      expect(executeButton).not.toBeDisabled();
    });
  });

  describe("error and empty states", () => {
    it("shows error message when runsListError is present", () => {
      render(
        <RecentRunsPanel
          {...defaultProps}
          runsListError="Failed to load runs"
        />
      );

      expect(screen.getByText("Failed to load runs")).toBeInTheDocument();
    });

    it("shows 'No runs match the current filter' when filter returns empty and not refreshing", () => {
      render(
        <RecentRunsPanel
          {...defaultProps}
          runsFilter="no-executions"
          filteredRunsList={[]}
        />
      );

      expect(screen.getByText("No runs match the current filter.")).toBeInTheDocument();
    });

    it("shows table when filter returns empty but we are refreshing existing rows", () => {
      render(
        <RecentRunsPanel
          {...defaultProps}
          runsFilter="no-executions"
          filteredRunsList={[]}
          runsListLoading={true}
          runsListRefreshing={true}
        />
      );

      // Table is still visible because we have rows in runsList
      expect(screen.getByRole("table")).toBeInTheDocument();
    });
  });

  describe("refresh completion behavior", () => {
    it("updates rows atomically when new data arrives", () => {
      const { rerender } = render(
        <RecentRunsPanel
          {...defaultProps}
          runsListLoading={true}
          runsListRefreshing={true}
        />
      );

      // Verify table is showing - check for run data-testid attribute (first row)
      const initialEntries = screen.getAllByTestId("run-entry");
      expect(initialEntries.length).toBe(3);
      expect(initialEntries[0].getAttribute("data-run-id")).toBe("run-001");

      // Simulate refresh completion with updated data
      const newRuns: RunsListEntry[] = [
        createRunEntry({ runId: "run-004", runLabel: "004", reviewStatus: "unreviewed", batchExecutable: true }),
        createRunEntry({ runId: "run-003", runLabel: "003", reviewStatus: "partially-reviewed" }),
      ];

      rerender(
        <RecentRunsPanel
          {...defaultProps}
          runsList={newRuns}
          paginatedRunsList={newRuns}
          filteredRunsList={newRuns}
          runsListLoading={false}
          runsListRefreshing={false}
        />
      );

      // Verify table now shows new data
      const updatedEntries = screen.getAllByTestId("run-entry");
      expect(updatedEntries.length).toBe(2);
      expect(updatedEntries[0].getAttribute("data-run-id")).toBe("run-004");
    });

    it("clears 'Refreshing…' indicator when refresh completes", () => {
      const { rerender } = render(
        <RecentRunsPanel
          {...defaultProps}
          runsListLoading={true}
          runsListRefreshing={true}
        />
      );

      expect(screen.getByText("Refreshing…")).toBeInTheDocument();

      rerender(
        <RecentRunsPanel
          {...defaultProps}
          runsListLoading={false}
          runsListRefreshing={false}
        />
      );

      expect(screen.queryByText("Refreshing…")).not.toBeInTheDocument();
    });
  });

  describe("pagination preserved during refresh", () => {
    it("renders Pagination component during background refresh", () => {
      render(
        <RecentRunsPanel
          {...defaultProps}
          runsListLoading={true}
          runsListRefreshing={true}
        />
      );

      // Look for the pagination component - check for navigation with Runs label
      expect(screen.getByRole("navigation", { name: /runs/i })).toBeInTheDocument();
    });
  });

  describe("runsListRefreshing prop behavior", () => {
    it("defaults to falsy when not provided (backward compatibility)", () => {
      render(
        <RecentRunsPanel
          {...defaultProps}
          runsListLoading={true}
          // runsListRefreshing not provided
        />
      );

      // Should show loading since we have no rows in filteredRunsList
      expect(screen.queryByText("Loading runs...")).not.toBeInTheDocument();
      // Actually in this case with defaultProps, filteredRunsList has 3 items
      // so this is actually "refreshing with existing rows" scenario
      expect(screen.getByRole("table")).toBeInTheDocument();
    });

    it("when runsListRefreshing is true but no existing rows, shows loading", () => {
      render(
        <RecentRunsPanel
          {...defaultProps}
          runsList={[]}
          paginatedRunsList={[]}
          filteredRunsList={[]}
          runsListLoading={true}
          runsListRefreshing={true}
        />
      );

      // Even though runsListRefreshing is true, no existing rows means show loading
      expect(screen.getByText("Loading runs...")).toBeInTheDocument();
    });
  });
});
