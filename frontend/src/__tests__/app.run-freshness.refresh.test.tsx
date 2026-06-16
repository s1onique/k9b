/**
 * Cockpit refresh regression tests.
 *
 * Tests that run selection is preserved across refresh operations
 * and that interval polling behaves correctly.
 *
 * Part of app.run-freshness.test.tsx split for LLM-friendly file sizes.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import dayjs from "dayjs";
import App from "../App";

import {
  createFetchMock,
  createStorageMock,
  defaultPayloads,
  sampleRun,
  sampleRunsList,
} from "./app.test-fixtures";

/**
 * Clock seam for run freshness tests.
 * Uses a fixed reference time so tests are deterministic without fake timers.
 */
const TEST_NOW = dayjs("2026-04-07T12:00:00Z");

let setIntervalSpy: ReturnType<typeof vi.fn>;
let clearIntervalSpy: ReturnType<typeof vi.fn>;
let storageMock: ReturnType<typeof createStorageMock>;

beforeEach(() => {
  setIntervalSpy = vi.fn(() => 123);
  clearIntervalSpy = vi.fn();
  vi.stubGlobal("setInterval", setIntervalSpy);
  vi.stubGlobal("clearInterval", clearIntervalSpy);
  storageMock = createStorageMock();
  vi.stubGlobal("localStorage", storageMock);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Cockpit refresh regression", () => {
  test("selected run remains selected after manual refresh", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    await user.click(run122Row!);

    await waitFor(() => {
      expect(run122Row).toHaveClass("run-row-selected");
    });

    const refreshButton = await screen.findByRole("button", { name: /Refresh/i });
    await user.click(refreshButton);

    await waitFor(() => {
      expect(run122Row).toHaveClass("run-row-selected");
    });

    expect(screen.getByText(/← Latest/i)).toBeInTheDocument();
  });

  test("interval polling does not leak or duplicate timers", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    setIntervalSpy.mockClear();
    clearIntervalSpy.mockClear();

    const autoRefreshSelect = screen.getByLabelText(/Auto/i) as HTMLSelectElement;
    await act(async () => {
      autoRefreshSelect.value = "10";
      autoRefreshSelect.dispatchEvent(new Event("change", { bubbles: true }));
    });

    expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 10000);
    expect(clearIntervalSpy).toHaveBeenCalled();
  });

  test("manual refresh surfaces newer latest run in Recent Runs", async () => {
    const runsWithNewLatest = {
      runs: [
        {
          runId: "run-124",
          runLabel: "2026-04-07-1400",
          timestamp: TEST_NOW.toISOString(),
          clusterCount: 2,
          triaged: false,
          executionCount: 0,
          reviewedCount: 0,
          reviewStatus: "no-executions",
          batchExecutable: true,
          batchEligibleCount: 3,
        },
        ...sampleRunsList.runs,
      ],
      totalCount: 5,
    };

    const payloads = { ...defaultPayloads, "/api/runs": runsWithNewLatest };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    const user = userEvent.setup();
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const run124Row = document.querySelector('.run-row[data-run-id="run-124"]');
    expect(run124Row).toHaveClass("run-row-selected");

    const run123Row = document.querySelector('.run-row[data-run-id="run-123"]');
    await user.click(run123Row!);

    await waitFor(() => {
      expect(run123Row).toHaveClass("run-row-selected");
    });

    expect(screen.getByText(/← Latest/i)).toBeInTheDocument();

    const refreshButton = await screen.findByRole("button", { name: /Refresh/i });
    await user.click(refreshButton);

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBe(5);
    });

    await waitFor(() => {
      expect(run123Row).toHaveClass("run-row-selected");
    });
  });
});
