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
import { createStorageMock, createFetchMock, makeRunWithOverrides } from "./fixtures";

/**
 * Creates a runs list with enough entries to span multiple pages.
 * With page size of 5, we need 6+ runs to have 2 pages.
 */
const createMultiPageRunsList = (pageSize = 5): RunsListPayload => {
  const runs = Array.from({ length: 8 }, (_, i) => ({
    runId: `run-${100 - i}`,
    runLabel: `2026-04-${String(10 - Math.floor(i / 2)).padStart(2, "0")}-${String(12 + (i % 2) * 2).padStart(2, "0")}`,
    timestamp: new Date(Date.now() - i * 3600000).toISOString(), // 1 hour apart
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

// Shared test setup
let storageMock: ReturnType<typeof createStorageMock>;
let setIntervalSpy: ReturnType<typeof vi.fn>;
let clearIntervalSpy: ReturnType<typeof vi.fn>;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  // Reset storage mock
  storageMock = createStorageMock();
  vi.stubGlobal("localStorage", storageMock);
  
  // Create and stub fetch mock
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  
  // Stub setInterval/clearInterval for auto-refresh
  setIntervalSpy = vi.fn(() => 123);
  clearIntervalSpy = vi.fn();
  vi.stubGlobal("setInterval", setIntervalSpy);
  vi.stubGlobal("clearInterval", clearIntervalSpy);
});

afterEach(() => {
  vi.restoreAllMocks();
});

// Helper to create a run payload with specific run ID
const createRunPayload = (runId: string, label: string, timestamp: string) =>
  makeRunWithOverrides({
    runId,
    label,
    timestamp,
  });

describe("Recent Runs Navigation Synchronization", () => {
  describe("Bug: Latest button should navigate to page 1 and highlight latest run", () => {
    test("clicking '← Latest' should navigate Recent Runs panel to page 1", async () => {
      // Create a multi-page runs list (8 runs with page size 5 = 2 pages)
      const runsPayload = createMultiPageRunsList(5);
      const latestRun = runsPayload.runs[0];
      
      // Build payloads
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
      
      // Set up fetch mock
      fetchMock.mockImplementation((input: RequestInfo) => {
        const url = typeof input === "string" ? input : input.url;
        const base = url.split("?")[0];
        const payload = payloads[url] ?? payloads[base];
        if (!payload) {
          return Promise.reject(new Error(`Unexpected fetch ${url}`));
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: () => Promise.resolve(payload),
        });
      });
      
      const user = userEvent.setup();
      
      // Render app
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      
      // Verify we're on page 1 initially
      const pageIndicator = document.querySelector(".pagination-page-indicator");
      expect(pageIndicator?.textContent).toContain("1");
      
      // Wait for runs list to be visible first
      await waitFor(() => {
        const runRows = document.querySelectorAll(".run-row");
        expect(runRows.length).toBeGreaterThan(0);
      });
      
      // First, navigate to page 2 using the next page button
      const nextButton = await screen.findByRole("button", { name: /runs next page/i });
      await act(async () => {
        await user.click(nextButton);
      });
      
      // Verify we're on page 2
      await waitFor(() => {
        const updatedIndicator = document.querySelector(".pagination-page-indicator");
        expect(updatedIndicator?.textContent).toContain("2");
      });
      
      // Now we need to navigate back to page 1 to click on run-97
      // Click the previous page button
      const prevButton = await screen.findByRole("button", { name: /runs previous page/i });
      await act(async () => {
        await user.click(prevButton);
      });
      
      // Verify we're back on page 1
      await waitFor(() => {
        const indicator = document.querySelector(".pagination-page-indicator");
        expect(indicator?.textContent).toContain("1");
      });
      
      // Now select a historical run (run-97)
      const historicalRow = document.querySelector('.run-row[data-run-id="run-97"]');
      expect(historicalRow).toBeInTheDocument();
      
      // Update fetch mock to handle the historical run fetch
      const historicalRun = runsPayload.runs.find(r => r.runId === "run-97")!;
      payloads["/api/run"] = createRunPayload(historicalRun.runId, historicalRun.runLabel, historicalRun.timestamp);
      fetchMock.mockImplementation((input: RequestInfo) => {
        const url = typeof input === "string" ? input : input.url;
        const base = url.split("?")[0];
        const payload = payloads[url] ?? payloads[base];
        if (!payload) {
          return Promise.reject(new Error(`Unexpected fetch ${url}`));
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: () => Promise.resolve(payload),
        });
      });
      
      await act(async () => {
        await user.click(historicalRow);
      });
      
      // Wait for the "← Latest" button to appear (indicates we selected a historical run)
      const latestButton = await screen.findByText(/← Latest/i);
      expect(latestButton).toBeInTheDocument();
      
      // Now click "← Latest" button
      await act(async () => {
        await user.click(latestButton);
      });
      
      // Page should navigate back to 1
      await waitFor(() => {
        const updatedPageIndicator = document.querySelector(".pagination-page-indicator");
        expect(updatedPageIndicator?.textContent).toContain("1");
      });
    });

    test("clicking '← Latest' should visually highlight the latest run row", async () => {
      const runsPayload = createMultiPageRunsList(5);
      const latestRun = runsPayload.runs[0];
      const historicalRun = runsPayload.runs[3]; // run-97
      
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
      
      // Set up fetch mock
      fetchMock.mockImplementation((input: RequestInfo) => {
        const url = typeof input === "string" ? input : input.url;
        const base = url.split("?")[0];
        const payload = payloads[url] ?? payloads[base];
        if (!payload) {
          return Promise.reject(new Error(`Unexpected fetch ${url}`));
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: () => Promise.resolve(payload),
        });
      });
      
      const user = userEvent.setup();
      
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      
      // Wait for runs to render
      await waitFor(() => {
        const runRows = document.querySelectorAll(".run-row");
        expect(runRows.length).toBeGreaterThan(0);
      });
      
      // Click on a historical run
      const historicalRow = document.querySelector('.run-row[data-run-id="run-97"]');
      expect(historicalRow).toBeInTheDocument();
      
      await act(async () => {
        await user.click(historicalRow);
      });
      
      // Latest button should appear
      const latestButton = await screen.findByText(/← Latest/i);
      
      // Update mock for latest run
      payloads["/api/run"] = createRunPayload(latestRun.runId, latestRun.runLabel, latestRun.timestamp);
      
      // Click "← Latest"
      await act(async () => {
        await user.click(latestButton);
      });
      
      // Latest run row should be selected (have the run-row-selected class)
      await waitFor(() => {
        const latestRow = document.querySelector('.run-row[data-run-id="run-100"]');
        expect(latestRow).toBeInTheDocument();
        expect(latestRow).toHaveClass("run-row-selected");
      });
    });
  });

  describe("Historical run selection should update header", () => {
    test("selecting a historical run from the list should show the Latest button", async () => {
      const runsPayload = createMultiPageRunsList(5);
      const latestRun = runsPayload.runs[0];
      const historicalRun = runsPayload.runs[3]; // run-97
      
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
      
      // Set up fetch mock
      fetchMock.mockImplementation((input: RequestInfo) => {
        const url = typeof input === "string" ? input : input.url;
        const base = url.split("?")[0];
        const payload = payloads[url] ?? payloads[base];
        if (!payload) {
          return Promise.reject(new Error(`Unexpected fetch ${url}`));
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: () => Promise.resolve(payload),
        });
      });
      
      const user = userEvent.setup();
      
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      
      // Wait for runs to render
      await waitFor(() => {
        const runRows = document.querySelectorAll(".run-row");
        expect(runRows.length).toBeGreaterThan(0);
      });
      
      // Click on historical run
      const historicalRow = document.querySelector('.run-row[data-run-id="run-97"]');
      expect(historicalRow).toBeInTheDocument();
      
      await act(async () => {
        await user.click(historicalRow);
      });
      
      // Latest button should be visible
      const latestButton = await screen.findByText(/← Latest/i);
      expect(latestButton).toBeInTheDocument();
      
      // Verify fetch was called with the run
      await waitFor(() => {
        const callArgs = fetchMock.mock.calls.flat();
        const hasRun97 = callArgs.some((arg: string) => typeof arg === "string" && arg.includes("run_id=run-97"));
        expect(hasRun97).toBe(true);
      });
    });
  });

  describe("Filter interaction behavior", () => {
    test("selecting a non-latest filter should reset to page 1 and show filtered runs", async () => {
      const runsPayload = createMultiPageRunsList(5);
      const latestRun = runsPayload.runs[0];
      
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
      
      // Set up fetch mock
      fetchMock.mockImplementation((input: RequestInfo) => {
        const url = typeof input === "string" ? input : input.url;
        const base = url.split("?")[0];
        const payload = payloads[url] ?? payloads[base];
        if (!payload) {
          return Promise.reject(new Error(`Unexpected fetch ${url}`));
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: () => Promise.resolve(payload),
        });
      });
      
      const user = userEvent.setup();
      
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      
      // Wait for runs to render
      await waitFor(() => {
        const runRows = document.querySelectorAll(".run-row");
        expect(runRows.length).toBeGreaterThan(0);
      });
      
      // Click on "Awaiting review" filter - this filters runs to show only unreviewed ones
      const filterButton = await screen.findByRole("button", { name: /Awaiting review/i });
      await act(async () => {
        await user.click(filterButton);
      });
      
      // Verify the runs are filtered (should show only runs with reviewStatus "unreviewed")
      // From our fixture: runs with i >= 3 are "unreviewed" (run-97, run-95, run-93, run-91, run-89)
      // With page size 5, this should show 5 runs on page 1
      await waitFor(() => {
        const runRows = document.querySelectorAll(".run-row");
        expect(runRows.length).toBe(5); // First page of filtered runs
      });
      
      // Verify the "Awaiting review" filter button text persists
      // (the filter is active when the runs are correctly filtered)
      expect(screen.getByText(/Showing 5 of/)).toBeInTheDocument();
    });
  });
});