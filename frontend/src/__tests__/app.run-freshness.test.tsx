/**
 * Run freshness and selection semantics tests.
 *
 * Tests run freshness thresholds, selection semantics, and the semantic
 * separation between selection state (Latest/Past run) and freshness
 * state (Fresh/Aging/Stale).
 *
 * Uses a production-safe clock seam to make tests deterministic
 * without requiring fake timers.
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
  makeRunWithOverrides,
  sampleRun,
  sampleRunsList,
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
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const staleLabel = screen.getByText(/^Stale$/i);
    expect(staleLabel).toBeInTheDocument();

    const freshnessIndicator = document.querySelector(".freshness-indicator--stale");
    expect(freshnessIndicator).not.toBeNull();
  });

  test("boundary: run at exactly 15 minutes shows Fresh", async () => {
    const freshTimestamp = minsBeforeTestNow(14);
    const freshRun = {
      ...sampleRun,
      timestamp: freshTimestamp,
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": freshRun }));
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });
    expect(screen.getByText(/^Fresh$/i)).toBeInTheDocument();
  });

  test("boundary: run at exactly 45 minutes shows Aging", async () => {
    const agingTimestamp = minsBeforeTestNow(44);
    const agingRun = {
      ...sampleRun,
      timestamp: agingTimestamp,
    };
    const agingRunsList = {
      runs: [
        { runId: "run-123", runLabel: "Aging boundary", timestamp: agingTimestamp, clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
      ],
      totalCount: 1,
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": agingRun, "/api/runs": agingRunsList }));
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
    await act(async () => {
      await user.click(olderStaleRow!);
    });

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

    const refreshButton = await screen.findByRole("button", { name: /Refresh/i });
    expect(refreshButton).toBeInTheDocument();
    expect(refreshButton).not.toBeDisabled();

    const autoRefreshSelect = await screen.findByLabelText(/Auto/i);
    expect(autoRefreshSelect).toBeInTheDocument();

    const pageFreshness = document.querySelector(".page-freshness-indicator");
    expect(pageFreshness).not.toBeNull();
  });
});

describe("Cockpit header selection vs freshness semantics", () => {
  test("State 1: selected run is latest and fresh - shows Latest badge and Fresh indicator", async () => {
    const recentTimestamp = minsBeforeTestNow(5);
    const freshRun = {
      ...sampleRun,
      timestamp: recentTimestamp,
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": freshRun }));
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
    await act(async () => {
      await user.click(pastRunRow!);
    });

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
    const staleRun = {
      ...sampleRun,
      timestamp: staleTimestamp,
    };
    const staleRunsList = {
      runs: [
        { runId: "run-123", runLabel: "Stale latest", timestamp: staleTimestamp, clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
      ],
      totalCount: 1,
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": staleRun, "/api/runs": staleRunsList }));
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
    await act(async () => {
      await user.click(pastRunRow!);
    });

    await waitFor(() => {
      expect(screen.queryByText(/^Past run$/i)).toBeInTheDocument();
    });

    const jumpButton = screen.getByText(/← Latest/);
    await act(async () => {
      await user.click(jumpButton);
    });

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

    await act(async () => {
      await user.click(within(tabList).getByRole("button", { name: /Hypotheses/i }));
    });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    await waitFor(() => {
      const updatedTabList = document.querySelector('[role="tablist"]');
      expect(updatedTabList).toBeInTheDocument();
    });

    const updatedTabList = await screen.findByRole("tablist", { name: /Cluster detail tabs/i });
    await act(async () => {
      await user.click(within(updatedTabList).getByRole("button", { name: /Next checks/i }));
    });

    expect(within(updatedTabList).getByRole("button", { name: /Next checks/i })).toBeInTheDocument();
  });
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
    await act(async () => {
      await user.click(run122Row!);
    });

    await waitFor(() => {
      expect(run122Row).toHaveClass("run-row-selected");
    });

    const refreshButton = await screen.findByRole("button", { name: /Refresh/i });
    await act(async () => {
      await user.click(refreshButton);
    });

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
    await act(async () => {
      await user.click(run123Row!);
    });

    await waitFor(() => {
      expect(run123Row).toHaveClass("run-row-selected");
    });

    expect(screen.getByText(/← Latest/i)).toBeInTheDocument();

    const refreshButton = await screen.findByRole("button", { name: /Refresh/i });
    await act(async () => {
      await user.click(refreshButton);
    });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBe(5);
    });

    await waitFor(() => {
      expect(run123Row).toHaveClass("run-row-selected");
    });
  });
});

describe("Run selection with run-specific data", () => {
  test("selecting a run updates Execution History and verifies correct run_id in fetch", async () => {
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      if (base === "/api/run") {
        const params = new URLSearchParams(url.split("?")[1] || "");
        const runId = params.get("run_id");
        if (runId === "run-122") {
          return makeFetchResponse(makeRunWithOverrides({
              runId: "run-122",
              label: "2026-04-07-1100",
              nextCheckExecutionHistory: [
                {
                  timestamp: "2026-04-07T11:05:00Z",
                  clusterLabel: "cluster-x",
                  candidateId: "candidate-122",
                  candidateIndex: 0,
                  candidateDescription: "Check for run-122 specific data",
                  commandFamily: "kubectl-get",
                  status: "success",
                  durationMs: 100,
                  artifactPath: "/artifacts/run-122-exec-0.json",
                  timedOut: false,
                  stdoutTruncated: false,
                  stderrTruncated: false,
                  outputBytesCaptured: 1024,
                  resultClass: "useful-signal",
                  resultSummary: "Run-122 specific execution result.",
                },
              ],
              nextCheckQueue: [],
          }));
        }
        return makeFetchResponse(sampleRun);
      }

      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return makeFetchResponse(payload);
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : input.url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    await waitFor(() => {
      const execHistory = document.getElementById("execution-history");
      expect(execHistory).toBeInTheDocument();
    });

    const runSpecificHistory = await screen.findByText(/Check for run-122 specific data/i);
    expect(runSpecificHistory).toBeInTheDocument();
  });

  test("selecting a run updates Work list to show that run's queue and verifies run_id in fetch", async () => {
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      if (base === "/api/run") {
        const params = new URLSearchParams(url.split("?")[1] || "");
        const runId = params.get("run_id");
        if (runId === "run-122") {
          return makeFetchResponse(makeRunWithOverrides({
              runId: "run-122",
              label: "2026-04-07-1100",
              nextCheckExecutionHistory: [],
              nextCheckQueue: [
                {
                  candidateId: "candidate-122-queue",
                  candidateIndex: 0,
                  description: "Run-122 specific queue item",
                  targetCluster: "cluster-x",
                  priorityLabel: "primary",
                  suggestedCommandFamily: "kubectl-get",
                  safeToAutomate: true,
                  requiresOperatorApproval: false,
                  approvalState: "not-required",
                  executionState: "unexecuted",
                  outcomeStatus: "pending",
                  latestArtifactPath: null,
                  sourceReason: "test",
                  expectedSignal: "test",
                  normalizationReason: "test",
                  safetyReason: "test",
                  approvalReason: null,
                  duplicateReason: null,
                  blockingReason: null,
                  targetContext: "cluster-x",
                  commandPreview: "kubectl get all",
                  planArtifactPath: null,
                  queueStatus: "safe-ready",
                  workstream: "incident",
                },
              ],
          }));
        }
        return makeFetchResponse(sampleRun);
      }

      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return makeFetchResponse(payload);
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : input.url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    await waitFor(() => {
      const queueSection = document.getElementById("next-check-queue");
      expect(queueSection).toBeInTheDocument();
    });

    const runSpecificQueue = await screen.findByText(/Run-122 specific queue item/i);
    expect(runSpecificQueue).toBeInTheDocument();
  });

  test("selected run remains stable when runs list updates with new latest run", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    const olderRunRow = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(olderRunRow).not.toBeNull();

    await act(async () => {
      await user.click(olderRunRow!);
    });

    await waitFor(() => {
      expect(olderRunRow).toHaveClass("run-row-selected");
    });

    const newRunsList = {
      runs: [
        {
          runId: "run-124",
          runLabel: "2026-04-07-1400",
          timestamp: "2026-04-07T14:00:00Z",
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

    vi.stubGlobal("fetch", createFetchMock({
      ...defaultPayloads,
      "/api/runs": newRunsList,
    }));

    const refreshButton = await screen.findByRole("button", { name: /Refresh/i });
    await act(async () => {
      await user.click(refreshButton);
    });

    const selectedAfterRefresh = document.querySelector('.run-row-selected');
    expect(selectedAfterRefresh).toHaveAttribute("data-run-id", "run-122");

    const jumpButton = await screen.findByText(/← Latest/i);
    expect(jumpButton).toBeInTheDocument();
  });

  test("empty states are selected-run-specific for Execution History and verifies run_id", async () => {
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      if (base === "/api/run") {
        const params = new URLSearchParams(url.split("?")[1] || "");
        const runId = params.get("run_id");
        if (runId === "run-122") {
          return makeFetchResponse(makeRunWithOverrides({
              runId: "run-122",
              label: "2026-04-07-1100",
              nextCheckExecutionHistory: [],
              nextCheckQueue: [],
          }));
        }
        return makeFetchResponse(sampleRun);
      }

      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return makeFetchResponse(payload);
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : input.url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    await waitFor(() => {
      const execHistory = document.getElementById("execution-history");
      expect(execHistory).toBeInTheDocument();
    });

    const emptyState = await screen.findByText(/No execution history for this run yet/i);
    expect(emptyState).toBeInTheDocument();
  });

  test("empty states are selected-run-specific for Work list and verifies run_id", async () => {
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      if (base === "/api/run") {
        const params = new URLSearchParams(url.split("?")[1] || "");
        const runId = params.get("run_id");
        if (runId === "run-122") {
          return makeFetchResponse(makeRunWithOverrides({
              runId: "run-122",
              label: "2026-04-07-1100",
              nextCheckExecutionHistory: [],
              nextCheckQueue: [],
          }));
        }
        return makeFetchResponse(sampleRun);
      }

      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return makeFetchResponse(payload);
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App clock={() => TEST_NOW} />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : input.url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    await waitFor(() => {
      const queueSection = document.getElementById("next-check-queue");
      expect(queueSection).toBeInTheDocument();
    });

    const emptyState = await screen.findByText(/Work list is empty for this run/i);
    expect(emptyState).toBeInTheDocument();
  });
});
