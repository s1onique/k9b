/**
 * Tests for auto-refresh polling behavior.
 * Uses vi.useFakeTimers() at module level so the component mounts
 * with fake timers already active — this is the ONLY correct way
 * to test setInterval behavior created during React mount.
 *
 * IMPORTANT: Do not merge back into app.test.tsx. The timer isolation
 * strategy is incompatible with that file's real-timer default.
 */

import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, afterEach, beforeEach, describe, test, vi } from "vitest";
import App, { AUTOREFRESH_STORAGE_KEY } from "../App";
import {
  createFetchMock,
  createStorageMock,
  sampleClusterDetail,
  sampleFleet,
  sampleNotifications,
  sampleProposals,
  sampleRun,
  sampleRunsList,
} from "./fixtures";
import type { RunsListPayload } from "../types";

// Enable fake timers for all tests in this file
// Using shouldAdvanceTime to automatically advance when waiting for promises
vi.useFakeTimers({ shouldAdvanceTime: true });

const defaultPayloads = {
  "/api/run": sampleRun,
  "/api/runs": sampleRunsList,
  "/api/fleet": sampleFleet,
  "/api/proposals": sampleProposals,
  "/api/notifications": sampleNotifications,
  "/api/notifications?limit=50&page=1": sampleNotifications,
  "/api/cluster-detail": sampleClusterDetail,
};

describe("Auto-refresh polling behavior", () => {
  let storageMock: ReturnType<typeof createStorageMock>;

  beforeEach(() => {
    storageMock = createStorageMock();
    vi.stubGlobal("localStorage", storageMock);
    // Default: auto-refresh off. Tests that need it will seed a value.
    storageMock.setItem(AUTOREFRESH_STORAGE_KEY, "off");
    vi.clearAllTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.clearAllTimers();
  });

  test("enabling auto-refresh fetches new data and updates UI with run-124 as latest", async () => {
    // Build initial runs list with run-123 as latest
    const initialRunsList: RunsListPayload = {
      runs: [
        {
          runId: "run-123",
          runLabel: "2026-04-07-1200",
          timestamp: "2026-04-07T12:00:00Z",
          clusterCount: 3,
          triaged: true,
          executionCount: 5,
          reviewedCount: 5,
          reviewStatus: "fully-reviewed",
        },
        {
          runId: "run-122",
          runLabel: "2026-04-07-1100",
          timestamp: "2026-04-07T11:00:00Z",
          clusterCount: 3,
          triaged: false,
          executionCount: 3,
          reviewedCount: 0,
          reviewStatus: "unreviewed",
        },
      ],
      totalCount: 2,
    };

    // Build updated runs list with run-124 as latest
    const updatedRunsList: RunsListPayload = {
      runs: [
        {
          runId: "run-124",
          runLabel: "2026-04-07-1300",
          timestamp: "2026-04-07T13:00:00Z",
          clusterCount: 3,
          triaged: false,
          executionCount: 0,
          reviewedCount: 0,
          reviewStatus: "no-executions",
        },
        {
          runId: "run-123",
          runLabel: "2026-04-07-1200",
          timestamp: "2026-04-07T12:00:00Z",
          clusterCount: 3,
          triaged: true,
          executionCount: 5,
          reviewedCount: 5,
          reviewStatus: "fully-reviewed",
        },
        {
          runId: "run-122",
          runLabel: "2026-04-07-1100",
          timestamp: "2026-04-07T11:00:00Z",
          clusterCount: 3,
          triaged: false,
          executionCount: 3,
          reviewedCount: 0,
          reviewStatus: "unreviewed",
        },
      ],
      totalCount: 3,
    };

    // Mutable reference for the runs list response
    let currentRunsList = initialRunsList;

    // Create mutable fetch mock
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: () => Promise.resolve({ ...currentRunsList }),
        });
      }

      const payload = (defaultPayloads as Record<string, unknown>)[url] ?? (defaultPayloads as Record<string, unknown>)[base];
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

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    render(<App />);

    // Wait for initial render - should advance automatically with shouldAdvanceTime
    await act(async () => {});
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Wait for run rows to appear
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const runRows = document.querySelectorAll(".run-row");
    expect(runRows.length).toBeGreaterThan(0);

    // Verify initial state: run-123 is selected
    const run123Row = document.querySelector('.run-row[data-run-id="run-123"]');
    expect(run123Row).not.toBeNull();
    expect(run123Row).toHaveClass("run-row-selected");

    // Enable auto-refresh with 10 second interval
    const autoRefreshSelect = screen.getByLabelText(/Auto/i) as HTMLSelectElement;
    await act(async () => {
      await user.selectOptions(autoRefreshSelect, "10");
    });

    // Update the mock to return run-124 as latest
    currentRunsList = updatedRunsList;

    // The core issue: React state updates from the interval callback need to be flushed
    // by act(). The advanceTimersByTimeAsync triggers the callback but React hasn't flushed yet.
    // Solution: flush in the same act() call that triggers the timer
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
      // After the async timer advance completes, React hasn't flushed yet
      // So we need another act to flush React
    });

    // Flush React state updates one more time
    await act(async () => {
      vi.runAllTicks();
    });
    await act(async () => {});

    // Assert synchronously - product behavior proof
    const run124Row = document.querySelector('.run-row[data-run-id="run-124"]');
    expect(run124Row).not.toBeNull();

    // Verify the total count shows 3 runs
    const showingText = screen.getByText(/Showing \d+ of 3/i);
    expect(showingText).toBeInTheDocument();

    // The "← Latest" jump button should be visible since a newer run exists
    const jumpButton = screen.queryByText(/← Latest/i);
    expect(jumpButton).not.toBeNull();
  });

  test("disabling auto-refresh prevents UI update even when data changes", async () => {
    // Initial runs with run-123 as latest
    const initialRunsList: RunsListPayload = {
      runs: [
        {
          runId: "run-123",
          runLabel: "2026-04-07-1200",
          timestamp: "2026-04-07T12:00:00Z",
          clusterCount: 3,
          triaged: true,
          executionCount: 5,
          reviewedCount: 5,
          reviewStatus: "fully-reviewed",
        },
      ],
      totalCount: 1,
    };

    // Updated runs with run-124 as latest
    const updatedRunsList: RunsListPayload = {
      runs: [
        {
          runId: "run-124",
          runLabel: "2026-04-07-1300",
          timestamp: "2026-04-07T13:00:00Z",
          clusterCount: 3,
          triaged: false,
          executionCount: 0,
          reviewedCount: 0,
          reviewStatus: "no-executions",
        },
        {
          runId: "run-123",
          runLabel: "2026-04-07-1200",
          timestamp: "2026-04-07T12:00:00Z",
          clusterCount: 3,
          triaged: true,
          executionCount: 5,
          reviewedCount: 5,
          reviewStatus: "fully-reviewed",
        },
      ],
      totalCount: 2,
    };

    let currentRunsList = initialRunsList;

    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: () => Promise.resolve({ ...currentRunsList }),
        });
      }

      const payload = (defaultPayloads as Record<string, unknown>)[url] ?? (defaultPayloads as Record<string, unknown>)[base];
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

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    render(<App />);

    // Wait for initial render
    await act(async () => {});
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Verify initial state - run-123 exists
    expect(document.querySelector('.run-row[data-run-id="run-123"]')).not.toBeNull();

    // Enable auto-refresh
    const autoRefreshSelect = screen.getByLabelText(/Auto/i) as HTMLSelectElement;
    await act(async () => {
      await user.selectOptions(autoRefreshSelect, "10");
    });

    // Disable auto-refresh
    await act(async () => {
      await user.selectOptions(autoRefreshSelect, "off");
    });

    // Re-query after interactions to get fresh DOM reference
    const run123After = document.querySelector('.run-row[data-run-id="run-123"]');
    expect(run123After).not.toBeNull();

    // Update the mock data - run-124 now available
    currentRunsList = updatedRunsList;

    // Advance time - no update should happen since disabled
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20000);
    });

    // Assert - run-124 should NOT appear (polling disabled)
    const run124Row = document.querySelector('.run-row[data-run-id="run-124"]');
    expect(run124Row).toBeNull();

    // Verify only 1 run exists in the list (no new data fetched)
    const runRows = document.querySelectorAll(".run-row");
    expect(runRows.length).toBe(1);
  });

  test("changing auto-refresh interval updates polling schedule", async () => {
    // Initial runs with run-123 as latest
    const initialRunsList: RunsListPayload = {
      runs: [
        {
          runId: "run-123",
          runLabel: "2026-04-07-1200",
          timestamp: "2026-04-07T12:00:00Z",
          clusterCount: 3,
          triaged: true,
          executionCount: 5,
          reviewedCount: 5,
          reviewStatus: "fully-reviewed",
        },
      ],
      totalCount: 1,
    };

    // Data after 15 seconds
    const runsAt15s: RunsListPayload = {
      runs: [
        {
          runId: "run-124",
          runLabel: "2026-04-07-1300",
          timestamp: "2026-04-07T13:00:00Z",
          clusterCount: 3,
          triaged: false,
          executionCount: 0,
          reviewedCount: 0,
          reviewStatus: "no-executions",
        },
        {
          runId: "run-123",
          runLabel: "2026-04-07-1200",
          timestamp: "2026-04-07T12:00:00Z",
          clusterCount: 3,
          triaged: true,
          executionCount: 5,
          reviewedCount: 5,
          reviewStatus: "fully-reviewed",
        },
      ],
      totalCount: 2,
    };

    // Data after 25 seconds (when 30s interval would have triggered but we changed it)
    const runsAt25s: RunsListPayload = {
      runs: [
        {
          runId: "run-125",
          runLabel: "2026-04-07-1400",
          timestamp: "2026-04-07T14:00:00Z",
          clusterCount: 3,
          triaged: false,
          executionCount: 0,
          reviewedCount: 0,
          reviewStatus: "no-executions",
        },
        {
          runId: "run-124",
          runLabel: "2026-04-07-1300",
          timestamp: "2026-04-07T13:00:00Z",
          clusterCount: 3,
          triaged: false,
          executionCount: 0,
          reviewedCount: 0,
          reviewStatus: "no-executions",
        },
        {
          runId: "run-123",
          runLabel: "2026-04-07-1200",
          timestamp: "2026-04-07T12:00:00Z",
          clusterCount: 3,
          triaged: true,
          executionCount: 5,
          reviewedCount: 5,
          reviewStatus: "fully-reviewed",
        },
      ],
      totalCount: 3,
    };

    let currentRunsList = initialRunsList;

    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: () => Promise.resolve({ ...currentRunsList }),
        });
      }

      const payload = (defaultPayloads as Record<string, unknown>)[url] ?? (defaultPayloads as Record<string, unknown>)[base];
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

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    render(<App />);

    // Wait for initial render
    await act(async () => {});
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Verify run-123 is selected
    const run123Row = document.querySelector('.run-row[data-run-id="run-123"]');
    expect(run123Row).toHaveClass("run-row-selected");

    // Enable 30 second interval
    const autoRefreshSelect = screen.getByLabelText(/Auto/i) as HTMLSelectElement;
    await act(async () => {
      await user.selectOptions(autoRefreshSelect, "30");
    });

    // Advance 15 seconds - no update should happen (30s interval not reached)
    currentRunsList = runsAt15s;
    await act(async () => {
      vi.advanceTimersByTime(15000);
    });

    // Re-query run-123 (DOM may have updated) - should still be selected
    const run123Row15s = document.querySelector('.run-row[data-run-id="run-123"]');
    expect(run123Row15s).toHaveClass("run-row-selected");
    // run-124 should NOT exist yet (30s interval not reached)
    expect(document.querySelector('.run-row[data-run-id="run-124"]')).toBeNull();

    // Change to 10 second interval
    await act(async () => {
      await user.selectOptions(autoRefreshSelect, "10");
    });

    // Advance 10 seconds - update should happen
    currentRunsList = runsAt25s;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    // Flush React state updates
    await act(async () => {
      vi.runAllTicks();
    });
    await act(async () => {});

    // Verify run-124 is now in the list
    const run124Row = document.querySelector('.run-row[data-run-id="run-124"]');
    expect(run124Row).not.toBeNull();
  });

  test("auto-refresh dropdown persists selection to localStorage", async () => {
    // This test uses real timers only - no fake timers needed
    localStorage.removeItem(AUTOREFRESH_STORAGE_KEY);
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<App />);

    // Find heading
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Select 10 second auto-refresh
    const autoRefreshSelect = screen.getByLabelText(/Auto/i) as HTMLSelectElement;
    await act(async () => {
      await user.selectOptions(autoRefreshSelect, "10");
    });

    // Verify localStorage was updated (immediate sync)
    expect(localStorage.getItem(AUTOREFRESH_STORAGE_KEY)).toBe("10");

    // Change to 30 second
    await act(async () => {
      await user.selectOptions(autoRefreshSelect, "30");
    });

    // Verify localStorage was updated to new value (immediate sync)
    expect(localStorage.getItem(AUTOREFRESH_STORAGE_KEY)).toBe("30");
  });
});

// Restore real timers after all tests in this file complete
afterAll(() => {
  vi.useRealTimers();
});
