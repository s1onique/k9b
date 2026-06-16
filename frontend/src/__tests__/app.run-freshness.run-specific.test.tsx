/**
 * Run selection with run-specific data tests.
 *
 * Tests that selecting a run fetches the correct run_id and displays
 * run-specific Execution History and Work list content.
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

    await user.click(run122Row!);

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

    await user.click(run122Row!);

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

    await user.click(olderRunRow!);

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
    await user.click(refreshButton);

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

    await user.click(run122Row!);

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

    await user.click(run122Row!);

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
