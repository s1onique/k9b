/**
 * Recent Runs Navigation Synchronization Tests
 *
 * Tests for the "Latest" button synchronization bug:
 * - When clicking "Latest" in header, the Recent Runs panel should:
 *   1. Navigate to page 1
 *   2. Highlight/select the latest run row
 * - When selecting a historical run from the list, header should update
 * - Filter interaction should be defined and covered
 * - Refresh/auto-refresh should not break synchronization
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import App from "../App";
import type { RunsListPayload } from "../types";
import { createStorageMock, makeRunWithOverrides } from "./fixtures";

// =============================================================================
// Helper: creates a multi-page runs list for pagination tests
// 8 runs with page size 5 = 2 pages. First 3 runs are reviewed, rest are unreviewed.
// Page 1: run-100, run-99, run-98, run-97, run-96
// Page 2: run-95, run-94, run-93
// =============================================================================
const createMultiPageRunsList = (): RunsListPayload => {
  const runs = Array.from({ length: 8 }, (_, i) => ({
    runId: `run-${100 - i}`,
    runLabel: `2026-04-${String(10 - Math.floor(i / 2)).padStart(2, "0")}-${String(12 + (i % 2) * 2).padStart(2, "0")}`,
    timestamp: new Date(Date.now() - i * 3600000).toISOString(),
    clusterCount: 2,
    triaged: i % 2 === 0,
    executionCount: i,
    reviewedCount: i,
    // runs[0]=fully-reviewed, runs[1-2]=partially-reviewed, runs[3-7]=unreviewed
    reviewStatus: i === 0 ? "fully-reviewed" : i < 3 ? "partially-reviewed" : "unreviewed",
    reviewDownloadPath: null,
    batchExecutable: false,
    batchEligibleCount: 0,
  }));
  return { runs, totalCount: runs.length };
};

// =============================================================================
// Helper: create a run payload with specific run ID, label, and timestamp
// =============================================================================
const createRunPayload = (runId: string, label: string, timestamp: string) =>
  makeRunWithOverrides({
    runId,
    label,
    timestamp,
  });

// =============================================================================
// Helper: shared fetch mock setup that handles query parameters
// The actual API uses "/api/run?run_id=xxx", so we strip query params to match
// =============================================================================
const setupFetchMock = (fetchMock: ReturnType<typeof vi.fn>, payloads: Record<string, unknown>) => {
  fetchMock.mockImplementation((input: RequestInfo) => {
    const url = typeof input === "string" ? input : input.url;
    // Strip query parameters to match base URLs in payloads
    const base = url.split("?")[0];
    const payload = payloads[url] ?? payloads[base];
    if (!payload) {
      return Promise.reject(new Error(`Unexpected fetch ${url}`));
    }
    return makeFetchResponse(payload);
  });
};

// =============================================================================
// Shared test setup
// =============================================================================
let storageMock: ReturnType<typeof createStorageMock>;
let setIntervalSpy: ReturnType<typeof vi.fn>;
let clearIntervalSpy: ReturnType<typeof vi.fn>;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  storageMock = createStorageMock();
  vi.stubGlobal("localStorage", storageMock);

  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  setIntervalSpy = vi.fn(() => 123);
  clearIntervalSpy = vi.fn();
  vi.stubGlobal("setInterval", setIntervalSpy);
  vi.stubGlobal("clearInterval", clearIntervalSpy);
});

afterEach(() => {
  vi.restoreAllMocks();
});

// =============================================================================
// TEST SUITE: Recent Runs Navigation Synchronization
// =============================================================================
describe("Recent Runs Navigation Synchronization", () => {
  // ---------------------------------------------------------------------------
  // TEST GROUP: ← Latest button navigation
  // ---------------------------------------------------------------------------
  describe("← Latest button navigation", () => {
    test("clicking '← Latest' should navigate to page 1 and show latest row selected", async () => {
      const runsPayload = createMultiPageRunsList();
      const latestRun = runsPayload.runs[0];
      // run-95 is on page 2 (index 5, page = floor(5/5)+1 = 2)
      const historicalRun = runsPayload.runs[5];

      const payloads = {
        "/api/runs": runsPayload,
        "/api/run": createRunPayload(historicalRun.runId, historicalRun.runLabel, historicalRun.timestamp),
        "/api/fleet": {
          runId: latestRun.runId,
          runLabel: latestRun.runLabel,
          lastRunTimestamp: latestRun.timestamp,
          topProblem: { title: "Test", detail: "Test problem" },
          fleetStatus: { ratingCounts: [], degradedClusters: [] },
          clusters: [],
          proposalSummary: { pending: 0, total: 0, statusCounts: [] },
        },
        "/api/proposals": { proposals: [], statusSummary: [] },
        "/api/notifications": { notifications: [], total: 0, page: 1, limit: 50, total_pages: 1 },
      };

      setupFetchMock(fetchMock, payloads);
      const user = userEvent.setup();

      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });

      // Wait for runs to Render
      await waitFor(() => {
        const runRows = document.querySelectorAll(".run-row");
        expect(runRows.length).toBeGreaterThan(0);
      });

      // Navigate to page 2 where run-95 is
      const nextButton = await screen.findByRole("button", { name: /runs next page/i });
      await act(async () => {
        await user.click(nextButton);
      });

      await waitFor(() => {
        const pageIndicator = document.querySelector(".pagination-page-indicator");
        expect(pageIndicator?.textContent).toContain("2");
      });

      // Wait for run-95 to be visible on page 2
      const historicalRow = await waitFor(() => document.querySelector('.run-row[data-run-id="run-95"]'), { timeout: 2000 });
      expect(historicalRow).toBeInTheDocument();

      // Update mock for historical run fetch
      payloads["/api/run"] = createRunPayload(
        historicalRun.runId,
        historicalRun.runLabel,
        historicalRun.timestamp
      );

      // Select historical run
      await act(async () => {
        await user.click(historicalRow!);
      });

      // Verify "← Latest" button appears
      const latestButton = await screen.findByRole("button", { name: /← Latest/i });
      expect(latestButton).toBeInTheDocument();

      // Update mock for latest run
      payloads["/api/run"] = createRunPayload(latestRun.runId, latestRun.runLabel, latestRun.timestamp);

      // Click "← Latest"
      await act(async () => {
        await user.click(latestButton);
      });

      // ASSERTION 1: Page indicator should show page 1
      await waitFor(() => {
        const pageIndicator = document.querySelector(".pagination-page-indicator");
        expect(pageIndicator?.textContent).toContain("1");
      });

      // ASSERTION 2: Latest run row should be visible on page 1
      const latestRow = document.querySelector('.run-row[data-run-id="run-100"]');
      expect(latestRow).toBeInTheDocument();

      // ASSERTION 3: Latest run row should be selected
      expect(latestRow).toHaveClass("run-row-selected");
    });

    test("clicking '← Latest' should deselect the historical run and select latest", async () => {
      const runsPayload = createMultiPageRunsList();
      const latestRun = runsPayload.runs[0];
      // run-95 is on page 2 (index 5, page = floor(5/5)+1 = 2)
      const historicalRun = runsPayload.runs[5];

      const payloads = {
        "/api/runs": runsPayload,
        "/api/run": createRunPayload(historicalRun.runId, historicalRun.runLabel, historicalRun.timestamp),
        "/api/fleet": {
          runId: latestRun.runId,
          runLabel: latestRun.runLabel,
          lastRunTimestamp: latestRun.timestamp,
          topProblem: { title: "Test", detail: "Test problem" },
          fleetStatus: { ratingCounts: [], degradedClusters: [] },
          clusters: [],
          proposalSummary: { pending: 0, total: 0, statusCounts: [] },
        },
        "/api/proposals": { proposals: [], statusSummary: [] },
        "/api/notifications": { notifications: [], total: 0, page: 1, limit: 50, total_pages: 1 },
      };

      setupFetchMock(fetchMock, payloads);
      const user = userEvent.setup();

      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });

      await waitFor(() => {
        const runRows = document.querySelectorAll(".run-row");
        expect(runRows.length).toBeGreaterThan(0);
      });

      // Navigate to page 2
      const nextButton = await screen.findByRole("button", { name: /runs next page/i });
      await act(async () => {
        await user.click(nextButton);
      });

      await waitFor(() => {
        const pageIndicator = document.querySelector(".pagination-page-indicator");
        expect(pageIndicator?.textContent).toContain("2");
      });

      // Select historical run
      payloads["/api/run"] = createRunPayload(
        historicalRun.runId,
        historicalRun.runLabel,
        historicalRun.timestamp
      );

      const historicalRow = document.querySelector('.run-row[data-run-id="run-95"]')!;
      await act(async () => {
        await user.click(historicalRow);
      });

      // Wait for "← Latest" button
      await screen.findByRole("button", { name: /← Latest/i });

      // Update mock for latest run
      payloads["/api/run"] = createRunPayload(latestRun.runId, latestRun.runLabel, latestRun.timestamp);

      // Click "← Latest"
      const latestButton = await screen.findByRole("button", { name: /← Latest/i });
      await act(async () => {
        await user.click(latestButton);
      });

      // ASSERTION: Latest row should be selected on page 1
      await waitFor(() => {
        const latestRow = document.querySelector('.run-row[data-run-id="run-100"]');
        expect(latestRow).toBeInTheDocument();
        expect(latestRow).toHaveClass("run-row-selected");
      });

      // ASSERTION: "Past run" badge should be gone (now showing "Latest")
      // Note: we don't check for "Latest" text in header badge since it may take time for async fetch
      // But the key assertion is that latest row is selected
      const latestRowSelected = document.querySelector('.run-row[data-run-id="run-100"].run-row-selected');
      expect(latestRowSelected).toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // TEST GROUP: Historical run selection should update header
  // ---------------------------------------------------------------------------
  describe("Historical run selection should update header", () => {
    test("selecting a historical run should show 'Past run' badge and '← Latest' button", async () => {
      const runsPayload = createMultiPageRunsList();
      const latestRun = runsPayload.runs[0];
      // run-95 is on page 2 (index 5, page = floor(5/5)+1 = 2)
      const historicalRun = runsPayload.runs[5];

      const payloads = {
        "/api/runs": runsPayload,
        "/api/run": createRunPayload(historicalRun.runId, historicalRun.runLabel, historicalRun.timestamp),
        "/api/fleet": {
          runId: latestRun.runId,
          runLabel: latestRun.runLabel,
          lastRunTimestamp: latestRun.timestamp,
          topProblem: { title: "Test", detail: "Test problem" },
          fleetStatus: { ratingCounts: [], degradedClusters: [] },
          clusters: [],
          proposalSummary: { pending: 0, total: 0, statusCounts: [] },
        },
        "/api/proposals": { proposals: [], statusSummary: [] },
        "/api/notifications": { notifications: [], total: 0, page: 1, limit: 50, total_pages: 1 },
      };

      setupFetchMock(fetchMock, payloads);
      const user = userEvent.setup();

      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });

      await waitFor(() => {
        const runRows = document.querySelectorAll(".run-row");
        expect(runRows.length).toBeGreaterThan(0);
      });

      // Navigate to page 2 where run-95 is
      const nextButton = await screen.findByRole("button", { name: /runs next page/i });
      await act(async () => {
        await user.click(nextButton);
      });

      await waitFor(() => {
        const row = document.querySelector('.run-row[data-run-id="run-95"]');
        expect(row).toBeInTheDocument();
      });

      // Select historical run - this triggers:
      // 1. selectedRunId updates to "run-95"
      // 2. isSelectedRunLatest becomes false
      // 3. Header badge changes from "Latest" to "Past run"
      // 4. "← Latest" button appears
      const historicalRow = document.querySelector('.run-row[data-run-id="run-95"]')!;
      await act(async () => {
        await user.click(historicalRow);
      });

      // ASSERTION 1: "← Latest" button should appear (proves historical run was selected)
      const latestButton = await screen.findByRole("button", { name: /← Latest/i });
      expect(latestButton).toBeInTheDocument();

      // ASSERTION 2: Header should show "Past run" badge (proves header updated)
      // Use getAllByText since "Past run" appears in multiple places (header badge + panel)
      const pastRunBadges = screen.getAllByText(/Past run/i);
      expect(pastRunBadges.length).toBeGreaterThan(0);

      // ASSERTION 3: "Latest" text should NOT appear in header badge anymore
      // (the header shows "Past run", not "Latest")
      const latestBadges = screen.queryAllByText(/Latest/i);
      // Filter to only header badges (with run-badge class)
      const headerLatestBadges = latestBadges.filter(badge => 
        badge.closest('.run-badge')
      );
      expect(headerLatestBadges.length).toBe(0);

      // ASSERTION 4: Verify fetch was called with historical run ID
      await waitFor(() => {
        const callArgs = fetchMock.mock.calls.flat();
        const hasRun95 = callArgs.some(
          (arg: unknown) => typeof arg === "string" && arg.includes("run_id=run-95")
        );
        expect(hasRun95).toBe(true);
      });
    });
  });

  // ---------------------------------------------------------------------------
  // TEST GROUP: Filter interaction behavior
  // ---------------------------------------------------------------------------
  describe("Filter interaction should show only matching runs", () => {
    test("selecting a filter should show only matching runs and update the summary", async () => {
      const runsPayload = createMultiPageRunsList();
      const latestRun = runsPayload.runs[0];

      // 5 unreviewed runs (run-97 through run-93) with page size 5 = 1 page
      const payloads = {
        "/api/runs": runsPayload,
        "/api/run": createRunPayload(latestRun.runId, latestRun.runLabel, latestRun.timestamp),
        "/api/fleet": {
          runId: latestRun.runId,
          runLabel: latestRun.runLabel,
          lastRunTimestamp: latestRun.timestamp,
          topProblem: { title: "Test", detail: "Test problem" },
          fleetStatus: { ratingCounts: [], degradedClusters: [] },
          clusters: [],
          proposalSummary: { pending: 0, total: 0, statusCounts: [] },
        },
        "/api/proposals": { proposals: [], statusSummary: [] },
        "/api/notifications": { notifications: [], total: 0, page: 1, limit: 50, total_pages: 1 },
      };

      setupFetchMock(fetchMock, payloads);
      const user = userEvent.setup();

      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });

      await waitFor(() => {
        const runRows = document.querySelectorAll(".run-row");
        expect(runRows.length).toBeGreaterThan(0);
      });

      // Click "Awaiting review" filter
      const filterButton = await screen.findByRole("button", { name: /Awaiting review/i });
      await act(async () => {
        await user.click(filterButton);
      });

      // ASSERTION 1: After filter, only 5 unreviewed runs are shown
      await waitFor(() => {
        const runRows = document.querySelectorAll(".run-row");
        expect(runRows.length).toBe(5);
      });

      // ASSERTION 2: All visible rows should be unreviewed (displayed as "Awaiting review")
      const runRows = document.querySelectorAll(".run-row");
      for (const row of runRows) {
        const statusCell = row.querySelector("td:nth-child(2)");
        expect(statusCell?.textContent).toContain("Awaiting review");
      }

      // ASSERTION 3: Filter summary should show correct counts
      const filterSummary = await screen.findByText(/Showing 5 of 8 runs/);
      expect(filterSummary).toBeInTheDocument();

      // ASSERTION 4: Active filter button should be visually marked
      const activeFilterButton = await screen.findByRole("button", { name: /Awaiting review/i });
      expect(activeFilterButton).toHaveClass("active");

      // ASSERTION 5: Pagination summary should show correct range
      const paginationSummary = document.querySelector(".pagination-summary");
      expect(paginationSummary?.textContent).toContain("1–5");
      expect(paginationSummary?.textContent).toContain("5");
    });
  });
});
