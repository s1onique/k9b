/**
 * Cockpit header selection vs freshness semantics tests.
 *
 * Tests the semantic separation between selection state (Latest/Past run)
 * and freshness state (Fresh/Aging/Stale).
 *
 * Part of app.run-freshness.test.tsx split for LLM-friendly file sizes.
 */

import { act, render, screen, waitFor, within } from "@testing-library/react";
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

describe("Cockpit header selection vs freshness semantics", () => {
  test("State 1: selected run is latest and fresh - shows Latest badge and Fresh indicator", async () => {
    const recentTimestamp = minsBeforeTestNow(5);
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": { ...sampleRun, timestamp: recentTimestamp } }));
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    expect(screen.getByText(/^Latest$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Fresh$/i)).toBeInTheDocument();
    expect(screen.getByText(/Captured .* ago/i)).toBeInTheDocument();
  });

  test("State 2: past run selected but latest is fresh - shows Past run badge, NO Stale indicator", async () => {
    const pastRunTimestamp = minsBeforeTestNow(60);
    const latestRunTimestamp = minsBeforeTestNow(5);

    const runsWithPastAndFreshLatest = {
      runs: [
        { runId: "run-fresh", runLabel: "Latest run", timestamp: latestRunTimestamp, clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
        { runId: "run-past", runLabel: "Past run", timestamp: pastRunTimestamp, clusterCount: 2, triaged: true, executionCount: 3, reviewedCount: 3, reviewStatus: "fully-reviewed" },
      ],
      totalCount: 2,
    };

    const pastRun = { ...sampleRun, runId: "run-past", timestamp: pastRunTimestamp };
    const latestRun = { ...sampleRun, runId: "run-fresh", timestamp: latestRunTimestamp };

    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        return Promise.resolve(makeFetchResponse(runsWithPastAndFreshLatest));
      }
      if (base === "/api/run") {
        const params = new URLSearchParams(url.split("?")[1] || "");
        const runId = params.get("run_id");
        if (runId === "run-past") {
          return Promise.resolve(makeFetchResponse(pastRun));
        }
        return Promise.resolve(makeFetchResponse(latestRun));
      }

      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) return Promise.reject(new Error(`Unexpected fetch ${url}`));
      return Promise.resolve(makeFetchResponse(payload));
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    expect(screen.getByText(/^Latest$/i)).toBeInTheDocument();

    const pastRunRow = document.querySelector('.run-row[data-run-id="run-past"]');
    await user.click(pastRunRow!);

    await waitFor(() => {
      expect(screen.queryByText(/^Past run$/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/^Past run$/i)).toBeInTheDocument();
    expect(screen.getByText(/Latest run available:/i)).toBeInTheDocument();
    expect(screen.getByText(/Captured .* ago/i)).toBeInTheDocument();

    expect(screen.queryByText(/^Stale$/i)).not.toBeInTheDocument();

    const freshnessIndicator = document.querySelector(".freshness-indicator");
    expect(freshnessIndicator).toBeNull();

    const jumpButton = screen.getByText(/← Latest/);
    expect(jumpButton).toBeInTheDocument();

    const pastRunFetchCalls = fetchMock.mock.calls.filter(([input]) => {
      const url = typeof input === "string" ? input : input.url;
      return url.includes("run_id=run-past");
    });
    expect(pastRunFetchCalls.length).toBeGreaterThan(0);
  });

  test("State 3: latest run itself is stale - shows Stale indicator for latest run", async () => {
    const staleTimestamp = minsBeforeTestNow(60);
    const staleRunsList = {
      runs: [
        { runId: "run-123", runLabel: "Stale latest", timestamp: staleTimestamp, clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
      ],
      totalCount: 1,
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": { ...sampleRun, timestamp: staleTimestamp }, "/api/runs": staleRunsList }));
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    expect(screen.getByText(/^Latest$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Stale$/i)).toBeInTheDocument();

    const staleIndicator = document.querySelector(".freshness-indicator--stale");
    expect(staleIndicator).not.toBeNull();
  });

  test("jump to latest button returns to latest run and restores Fresh indicator", async () => {
    const pastRunTimestamp = minsBeforeTestNow(60);
    const latestRunTimestamp = minsBeforeTestNow(5);

    const runsWithPastAndFreshLatest = {
      runs: [
        { runId: "run-fresh", runLabel: "Latest run", timestamp: latestRunTimestamp, clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
        { runId: "run-past", runLabel: "Past run", timestamp: pastRunTimestamp, clusterCount: 2, triaged: true, executionCount: 3, reviewedCount: 3, reviewStatus: "fully-reviewed" },
      ],
      totalCount: 2,
    };

    const pastRun = { ...sampleRun, runId: "run-past", timestamp: pastRunTimestamp };
    const latestRun = { ...sampleRun, runId: "run-fresh", timestamp: latestRunTimestamp };

    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        return Promise.resolve(makeFetchResponse(runsWithPastAndFreshLatest));
      }
      if (base === "/api/run") {
        const params = new URLSearchParams(url.split("?")[1] || "");
        const runId = params.get("run_id");
        if (runId === "run-past") {
          return Promise.resolve(makeFetchResponse(pastRun));
        }
        return Promise.resolve(makeFetchResponse(latestRun));
      }

      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) return Promise.reject(new Error(`Unexpected fetch ${url}`));
      return Promise.resolve(makeFetchResponse(payload));
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const pastRunRow = document.querySelector('.run-row[data-run-id="run-past"]');
    await user.click(pastRunRow!);

    await waitFor(() => {
      expect(screen.queryByText(/^Past run$/i)).toBeInTheDocument();
    });

    const jumpButton = screen.getByText(/← Latest/);
    await user.click(jumpButton);

    await waitFor(() => {
      expect(screen.queryByText(/^Latest$/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/^Fresh$/i)).toBeInTheDocument();
    expect(screen.queryByText(/Latest run available:/i)).not.toBeInTheDocument();

    const freshIndicator = document.querySelector(".freshness-indicator--fresh");
    expect(freshIndicator).not.toBeNull();
  });

  test("panel switching behavior still works after run selection", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const clusterSection = await screen.findByRole("heading", { name: /Cluster detail/i });
    expect(clusterSection).toBeInTheDocument();

    const tabList = await screen.findByRole("tablist", { name: /Cluster detail tabs/i });
    expect(tabList).toBeInTheDocument();

    await user.click(within(tabList).getByRole("button", { name: /Hypotheses/i }));

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await user.click(run122Row!);

    await waitFor(() => {
      const updatedTabList = document.querySelector('[role="tablist"]');
      expect(updatedTabList).toBeInTheDocument();
    });

    const updatedTabList = await screen.findByRole("tablist", { name: /Cluster detail tabs/i });
    await user.click(within(updatedTabList).getByRole("button", { name: /Next checks/i }));

    expect(within(updatedTabList).getByRole("button", { name: /Next checks/i })).toBeInTheDocument();
  });
});
