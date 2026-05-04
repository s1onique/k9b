/**
 * Detached Notice Visibility Tests
 *
 * Tests the UX refinement: the "Browsing page X of Y" detached notice should only
 * appear when the operator is in detached mode AND the selected run is NOT visible
 * on the current page.
 *
 * Coverage:
 * 1. detached + selected run visible on current page → notice NOT shown
 * 2. clicking "Show selected run" → notice hidden, follow mode re-engaged
 * 3. notice only appears when detached AND selected run is off-page
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import App from "../App";
import type { RunsListPayload } from "../types";
import { createStorageMock, makeRunWithOverrides } from "./fixtures";

// =============================================================================
// Helper: creates a multi-page runs list for pagination tests
// 8 runs with page size 5 = 2 pages.
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
// Helper: shared fetch mock setup
// =============================================================================
const setupFetchMock = (fetchMock: ReturnType<typeof vi.fn>, payloads: Record<string, unknown>) => {
  fetchMock.mockImplementation((input: RequestInfo) => {
    const url = typeof input === "string" ? input : input.url;
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
// TEST SUITE: Detached Notice Visibility
// =============================================================================
describe("Detached notice visibility", () => {
  /**
   * TEST 1: detached + selected run visible → notice NOT shown
   *
   * Scenario:
   * - Operator navigates to page 2 (detached mode)
   * - Selects run-95 which IS on page 2
   * - The notice should NOT appear because run-95 is visible
   */
  test("detached + selected run visible on current page → notice NOT shown", async () => {
    const runsPayload = createMultiPageRunsList();
    const latestRun = runsPayload.runs[0];
    // run-95 is on page 2 (index 5, page = floor(5/5)+1 = 2)
    const selectedRun = runsPayload.runs[5];

    const payloads = {
      "/api/runs": runsPayload,
      "/api/run": createRunPayload(selectedRun.runId, selectedRun.runLabel, selectedRun.timestamp),
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

    // Navigate to page 2 (this transitions to detached mode)
    const nextButton = await screen.findByRole("button", { name: /runs next page/i });
    await act(async () => {
      await user.click(nextButton);
    });

    await waitFor(() => {
      const pageIndicator = document.querySelector(".pagination-page-indicator");
      expect(pageIndicator?.textContent).toContain("2");
    });

    // Select run-95 (which is on page 2 - so it's visible)
    await act(async () => {
      const selectedRow = document.querySelector('.run-row[data-run-id="run-95"]');
      expect(selectedRow).toBeInTheDocument();
      await user.click(selectedRow!);
    });

    // ASSERTION: The detached notice should NOT be shown because run-95 IS visible on page 2
    // Query for the detached notice container specifically
    const detachedNotice = document.querySelector(".runs-detached-notice");
    expect(detachedNotice).not.toBeInTheDocument();

    // The selected run should still be visible and selected
    const selectedRow = document.querySelector('.run-row[data-run-id="run-95"].run-row-selected');
    expect(selectedRow).toBeInTheDocument();
  });

  /**
   * TEST 2: clicking "Show selected run" from page 2 with latest selected
   *
   * Scenario:
   * - Start on page 1 with latest run-100 selected (follow mode)
   * - Manually navigate to page 2 (detached mode)
   * - Notice appears because run-100 is NOT on page 2
   * - Click "Show selected run" → navigates to page 1, notice disappears
   */
  test("clicking 'Show selected run' hides notice and navigates to selected run", async () => {
    const runsPayload = createMultiPageRunsList();
    const latestRun = runsPayload.runs[0];
    // run-100 is on page 1, run-95 is on page 2

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

    // Verify we're on page 1 with latest run selected (follow mode)
    await waitFor(() => {
      const pageIndicator = document.querySelector(".pagination-page-indicator");
      expect(pageIndicator?.textContent).toContain("1");
    });

    // Latest run should be selected
    const latestRow = document.querySelector('.run-row[data-run-id="run-100"].run-row-selected');
    expect(latestRow).toBeInTheDocument();

    // No notice should be shown on page 1
    expect(document.querySelector(".runs-detached-notice")).not.toBeInTheDocument();

    // Manually navigate to page 2 (detached mode)
    const nextButton = await screen.findByRole("button", { name: /runs next page/i });
    await act(async () => {
      await user.click(nextButton);
    });

    await waitFor(() => {
      const pageIndicator = document.querySelector(".pagination-page-indicator");
      expect(pageIndicator?.textContent).toContain("2");
    });

    // Verify run-100 is NOT visible on page 2
    expect(document.querySelector('.run-row[data-run-id="run-100"]')).not.toBeInTheDocument();

    // ASSERTION: The detached notice SHOULD be shown because run-100 is NOT on page 2
    const detachedNotice = await screen.findByText(/Browsing page 2/);
    expect(detachedNotice).toBeInTheDocument();

    // Check the parent container has the correct class
    const detachedNoticeContainer = detachedNotice.closest(".runs-detached-notice");
    expect(detachedNoticeContainer).toBeInTheDocument();

    // The notice should contain the "Show selected run" button
    expect(screen.getByRole("button", { name: /Show selected run/i })).toBeInTheDocument();

    // Click "Show selected run"
    const showSelectedButton = screen.getByRole("button", { name: /Show selected run/i });
    await act(async () => {
      await user.click(showSelectedButton);
    });

    // ASSERTION: Notice should be hidden
    await waitFor(() => {
      const notice = document.querySelector(".runs-detached-notice");
      expect(notice).not.toBeInTheDocument();
    });

    // ASSERTION: Should navigate to page 1 where run-100 is visible
    await waitFor(() => {
      const pageIndicator = document.querySelector(".pagination-page-indicator");
      expect(pageIndicator?.textContent).toContain("1");
    });

    // ASSERTION: run-100 should be visible and selected
    const selectedRow = document.querySelector('.run-row[data-run-id="run-100"].run-row-selected');
    expect(selectedRow).toBeInTheDocument();
  });

  /**
   * TEST 3: notice only appears when detached AND selected run is off-page
   *
   * This test verifies the core UX refinement:
   * - Simply being in detached mode is NOT enough
   * - The selected run must also be off the current page for the notice to appear
   */
  test("notice only shows when detached AND selected run is off current page", async () => {
    const runsPayload = createMultiPageRunsList();
    const latestRun = runsPayload.runs[0];
    // run-95 is on page 2

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

    // Navigate to page 2 (detached mode)
    const nextButton = await screen.findByRole("button", { name: /runs next page/i });
    await act(async () => {
      await user.click(nextButton);
    });

    await waitFor(() => {
      const pageIndicator = document.querySelector(".pagination-page-indicator");
      expect(pageIndicator?.textContent).toContain("2");
    });

    // Select run-95 (which IS on page 2)
    await act(async () => {
      const run95Row = document.querySelector('.run-row[data-run-id="run-95"]');
      expect(run95Row).toBeInTheDocument();
      await user.click(run95Row!);
    });

    // Update mock for run-95
    payloads["/api/run"] = createRunPayload(
      runsPayload.runs[5].runId,
      runsPayload.runs[5].runLabel,
      runsPayload.runs[5].timestamp
    );

    // Wait for state to settle
    await waitFor(() => {
      const selectedRow = document.querySelector('.run-row[data-run-id="run-95"].run-row-selected');
      expect(selectedRow).toBeInTheDocument();
    });

    // ASSERTION: Notice should NOT be shown because run-95 IS on page 2 (visible)
    expect(document.querySelector(".runs-detached-notice")).not.toBeInTheDocument();

    // Now navigate to page 1 (detached mode continues, but selected run is now off-page)
    const prevButton = await screen.findByRole("button", { name: /runs previous page/i });
    await act(async () => {
      await user.click(prevButton);
    });

    await waitFor(() => {
      const pageIndicator = document.querySelector(".pagination-page-indicator");
      expect(pageIndicator?.textContent).toContain("1");
    });

    // Verify run-95 is NOT on page 1
    expect(document.querySelector('.run-row[data-run-id="run-95"]')).not.toBeInTheDocument();

    // ASSERTION: Now the notice SHOULD be shown because:
    // - isRunsListFollowingSelection is false (we manually navigated)
    // - selectedRunId is run-95
    // - isSelectedRunVisibleOnCurrentRunsPage is false (run-95 is not on page 1)
    const detachedNotice = await screen.findByText(/Browsing page 1/);
    expect(detachedNotice).toBeInTheDocument();

    // Check the parent container has the correct class
    const detachedNoticeContainer = detachedNotice.closest(".runs-detached-notice");
    expect(detachedNoticeContainer).toBeInTheDocument();
  });
});
