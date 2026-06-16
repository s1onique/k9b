/**
 * Run freshness thresholds and past-run selection tests.
 *
 * Tests the Fresh/Aging/Stale threshold behavior and the interaction
 * between selection state and freshness state.
 *
 * Part of app.run-selection.test.tsx split for LLM-friendly file sizes.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App from "../App";

import {
  createFetchMock,
  createStorageMock,
  defaultPayloads,
  makeFetchResponse,
  minsAgo,
  sampleRun,
} from "./app.test-fixtures";

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
  test("run shows Fresh status when timestamp is <= 15 minutes old", async () => {
    const freshRun = {
      ...sampleRun,
      timestamp: minsAgo(10),
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": freshRun }));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const freshLabel = screen.getByText(/^Fresh$/i);
    expect(freshLabel).toBeInTheDocument();

    const freshnessIndicator = document.querySelector(".freshness-indicator--fresh");
    expect(freshnessIndicator).not.toBeNull();
  });

  test("run shows Aging status when timestamp is > 15 and <= 45 minutes old", async () => {
    const agingTimestamp = minsAgo(30);
    const agingRun = {
      ...sampleRun,
      timestamp: agingTimestamp,
    };
    const agingRunsList = {
      runs: [
        { runId: "run-123", runLabel: "Aging run", timestamp: agingTimestamp, clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
      ],
      totalCount: 1,
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": agingRun, "/api/runs": agingRunsList }));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const agingLabel = screen.getByText(/^Aging$/i);
    expect(agingLabel).toBeInTheDocument();

    const freshnessIndicator = document.querySelector(".freshness-indicator--warning");
    expect(freshnessIndicator).not.toBeNull();
  });

  test("run shows Stale status when timestamp is > 45 minutes old", async () => {
    const staleTimestamp = minsAgo(60);
    const staleRun = {
      ...sampleRun,
      timestamp: staleTimestamp,
    };
    const staleRunsList = {
      runs: [
        { runId: "run-123", runLabel: "Stale run", timestamp: staleTimestamp, clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
      ],
      totalCount: 1,
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": staleRun, "/api/runs": staleRunsList }));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const staleLabel = screen.getByText(/^Stale$/i);
    expect(staleLabel).toBeInTheDocument();

    const freshnessIndicator = document.querySelector(".freshness-indicator--stale");
    expect(freshnessIndicator).not.toBeNull();
  });

  test("selecting a past run hides freshness indicator but shows Past run badge", async () => {
    const freshRunTimestamp = minsAgo(10);
    const staleRunTimestamp = minsAgo(120);

    const runsWithDifferentTimestamps = {
      runs: [
        { runId: "run-123", runLabel: "Fresh run", timestamp: freshRunTimestamp, clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
        { runId: "run-122", runLabel: "Stale run", timestamp: staleRunTimestamp, clusterCount: 2, triaged: true, executionCount: 3, reviewedCount: 3, reviewStatus: "fully-reviewed" },
      ],
      totalCount: 2,
    };

    const freshRun = { ...sampleRun, timestamp: freshRunTimestamp };
    const staleRun = { ...sampleRun, runId: "run-122", timestamp: staleRunTimestamp };

    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        return Promise.resolve(makeFetchResponse(runsWithDifferentTimestamps));
      }
      if (base === "/api/run") {
        const params = new URLSearchParams(url.split("?")[1] || "");
        const runId = params.get("run_id");
        if (runId === "run-122") {
          return Promise.resolve(makeFetchResponse(staleRun));
        }
        return Promise.resolve(makeFetchResponse(freshRun));
      }

      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) return Promise.reject(new Error(`Unexpected fetch ${url}`));
      return Promise.resolve(makeFetchResponse(payload));
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      expect(screen.queryByText(/^Fresh$/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/^Fresh$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Latest$/i)).toBeInTheDocument();

    const staleRunRow = document.querySelector('.run-row[data-run-id="run-122"]');
    await user.click(staleRunRow!);

    await waitFor(() => {
      expect(screen.queryByText(/^Past run$/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/^Past run$/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Stale$/i)).not.toBeInTheDocument();
    const staleIndicator = document.querySelector(".freshness-indicator");
    expect(staleIndicator).toBeNull();

    expect(screen.getByText(/← Latest/)).toBeInTheDocument();
    expect(screen.getByText(/Latest run available:/i)).toBeInTheDocument();
  });
});
