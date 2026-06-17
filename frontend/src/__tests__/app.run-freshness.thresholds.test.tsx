/**
 * Run freshness threshold tests.
 *
 * Tests the Fresh/Aging/Stale threshold behavior for run timestamps.
 * Uses a production-safe clock seam to make tests deterministic.
 *
 * Part of app.run-freshness.test.tsx split for LLM-friendly file sizes.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import dayjs from "dayjs";
import App from "../App";

import {
  createFetchMock,
  createStorageMock,
  defaultPayloads,
  makeFetchResponse,
  sampleRun,
} from "./app.test-fixtures";

/**
 * Clock seam for run freshness tests.
 * Uses a fixed reference time so tests are deterministic without fake timers.
 */
const TEST_NOW = dayjs("2026-04-07T12:00:00Z");

/**
 * Generate a timestamp N minutes before the test reference time.
 * This creates deterministic timestamps for freshness testing.
 */
const minsBeforeTestNow = (minutes: number) =>
  TEST_NOW.subtract(minutes, "minute").toISOString();

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

describe("Run freshness thresholds", () => {
  test("run shows Stale status when timestamp is > 45 minutes old", async () => {
    const staleTimestamp = minsBeforeTestNow(60);
    const staleRunsList = {
      runs: [
        { runId: "run-123", runLabel: "Stale run", timestamp: staleTimestamp, clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
      ],
      totalCount: 1,
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": { ...sampleRun, timestamp: staleTimestamp }, "/api/runs": staleRunsList }));
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const staleLabel = screen.getByText(/^Stale$/i);
    expect(staleLabel).toBeInTheDocument();

    const freshnessIndicator = document.querySelector(".freshness-indicator--stale");
    expect(freshnessIndicator).not.toBeNull();
  });

  test("boundary: run at exactly 15 minutes shows Fresh", async () => {
    const freshTimestamp = minsBeforeTestNow(14);
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": { ...sampleRun, timestamp: freshTimestamp } }));
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });
    expect(screen.getByText(/^Fresh$/i)).toBeInTheDocument();
  });

  test("boundary: run at exactly 45 minutes shows Aging", async () => {
    const agingTimestamp = minsBeforeTestNow(44);
    const agingRunsList = {
      runs: [
        { runId: "run-123", runLabel: "Aging boundary", timestamp: agingTimestamp, clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
      ],
      totalCount: 1,
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": { ...sampleRun, timestamp: agingTimestamp }, "/api/runs": agingRunsList }));
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });
    expect(screen.getByText(/^Aging$/i)).toBeInTheDocument();
  });

  test("selecting a stale latest run shows Stale indicator", async () => {
    const staleRunTimestamp = minsBeforeTestNow(60);
    const olderStaleTimestamp = minsBeforeTestNow(120);

    const runsWithStaleLatest = {
      runs: [
        { runId: "run-123", runLabel: "Stale run (latest)", timestamp: staleRunTimestamp, clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
        { runId: "run-122", runLabel: "Older stale run", timestamp: olderStaleTimestamp, clusterCount: 2, triaged: true, executionCount: 3, reviewedCount: 3, reviewStatus: "fully-reviewed" },
      ],
      totalCount: 2,
    };

    const staleRun = { ...sampleRun, timestamp: staleRunTimestamp };
    const olderStaleRun = { ...sampleRun, runId: "run-122", timestamp: olderStaleTimestamp };

    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        return Promise.resolve(makeFetchResponse(runsWithStaleLatest));
      }
      if (base === "/api/run") {
        const params = new URLSearchParams(url.split("?")[1] || "");
        const runId = params.get("run_id");
        if (runId === "run-122") {
          return Promise.resolve(makeFetchResponse(olderStaleRun));
        }
        return Promise.resolve(makeFetchResponse(staleRun));
      }

      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) return Promise.reject(new Error(`Unexpected fetch ${url}`));
      return Promise.resolve(makeFetchResponse(payload));
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      expect(screen.queryByText(/^Stale$/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/^Stale$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Latest$/i)).toBeInTheDocument();
    const staleIndicator = document.querySelector(".freshness-indicator--stale");
    expect(staleIndicator).not.toBeNull();

    const olderStaleRow = document.querySelector('.run-row[data-run-id="run-122"]');
    await user.click(olderStaleRow!);

    await waitFor(() => {
      expect(screen.queryByText(/^Past run$/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/^Past run$/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Stale$/i)).not.toBeInTheDocument();
    const hiddenStaleIndicator = document.querySelector(".freshness-indicator");
    expect(hiddenStaleIndicator).toBeNull();
  });

  test("refresh controls remain present and queryable in header", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Find header refresh button - use aria-label to get the specific one
    const headerRefreshButton = screen.getByRole("button", { name: /^Refresh$/i });
    expect(headerRefreshButton).toBeInTheDocument();
    expect(headerRefreshButton).not.toBeDisabled();

    const autoRefreshSelect = await screen.findByLabelText(/Auto/i);
    expect(autoRefreshSelect).toBeInTheDocument();

    const pageFreshness = document.querySelector(".page-freshness-indicator");
    expect(pageFreshness).not.toBeNull();
  });
});
