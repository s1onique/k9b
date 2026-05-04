// Panel selection binding tests — Global panels

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App from "../App";
import type { RunPayload } from "../types";
import {
  createPanelSelectionRun123,
  createPanelSelectionRun122,
  createStorageMock,
  makeFetchResponse,
  sampleClusterDetail,
  sampleFleet,
  sampleNotifications,
  sampleProposals,
} from "./fixtures";

// Helper to create a smart fetch mock that returns run-specific data
const createRunAwareFetchMock = (
  run123Payload: RunPayload,
  run122Payload: RunPayload,
  globalPayloads: Record<string, unknown> = {}
) => {
  const defaultPayloads = {
    "/api/run": run123Payload,
    "/api/runs": {
      runs: [
        { runId: "run-123", runLabel: "2026-04-07-1200", timestamp: "2026-04-07T12:00:00Z", clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
        { runId: "run-122", runLabel: "2026-04-07-1100", timestamp: "2026-04-07T11:00:00Z", clusterCount: 2, triaged: false, executionCount: 3, reviewedCount: 0, reviewStatus: "unreviewed" },
      ],
      totalCount: 2,
    },
    "/api/fleet": sampleFleet,
    "/api/proposals": sampleProposals,
    "/api/notifications": sampleNotifications,
    "/api/notifications?limit=50&page=1": sampleNotifications,
    "/api/cluster-detail": sampleClusterDetail,
    ...globalPayloads,
  };

  return vi.fn((input: RequestInfo) => {
    const url = typeof input === "string" ? input : input.url;
    const base = url.split("?")[0];

    if (base === "/api/run") {
      const params = new URLSearchParams(url.split("?")[1] || "");
      const runId = params.get("run_id");
      if (runId === "run-122") {
        return makeFetchResponse(run122Payload);
      }
      // Default to run-123 payload
      return makeFetchResponse(run123Payload);
    }

    const payload = defaultPayloads[url] ?? defaultPayloads[base];
    if (!payload) {
      return Promise.reject(new Error(`Unexpected fetch ${url}`));
    }
    return makeFetchResponse(payload);
  });
};

// Wrapper functions that delegate to shared builders in fixtures.ts
const createRun123Payload = (overrides: Partial<RunPayload> = {}): RunPayload =>
  createPanelSelectionRun123(overrides as Parameters<typeof createPanelSelectionRun123>[0]);

const createRun122Payload = (overrides: Partial<RunPayload> = {}): RunPayload =>
  createPanelSelectionRun122(overrides as Parameters<typeof createPanelSelectionRun122>[0]);

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

describe("Panel selection binding - Global panels", () => {
  test("Fleet Overview does not change when selecting different run", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    const stableFleet = JSON.parse(JSON.stringify(sampleFleet));
    stableFleet.topProblem = { title: "API pressure", detail: "Control plane latency is trending upward" };
    const fetchMock = createRunAwareFetchMock(run123, run122, { "/api/fleet": stableFleet });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });
    expect(screen.getByText(sampleFleet.topProblem.detail, { exact: false })).toBeInTheDocument();
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();
    await act(async () => { await user.click(run122Row!); });
    expect(screen.getByText(sampleFleet.topProblem.detail, { exact: false })).toBeInTheDocument();
  });

  test("Cluster Detail does not change when selecting different run", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    const stableClusterDetail = {
      ...sampleClusterDetail,
      selectedClusterLabel: "cluster-a",
      findings: [{ label: "Stable Finding", context: "stable", triggerReasons: [], warningEvents: 0, nonRunningPods: 0, summaryEntries: [], patternDetails: [], rolloutStatus: [], artifactPath: null }],
      hypotheses: [{ description: "Stable Hypothesis", confidence: "high", probableLayer: "control-plane", falsifier: "none" }],
      nextChecks: [],
    };
    const fetchMock = createRunAwareFetchMock(run123, run122, { "/api/cluster-detail": stableClusterDetail });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });
    const clusterSection = document.getElementById("cluster");
    expect(clusterSection).toBeInTheDocument();
    expect(within(clusterSection).getByText(/Stable Finding/i)).toBeInTheDocument();
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();
    await act(async () => { await user.click(run122Row!); });
    expect(within(clusterSection).getByText(/Stable Finding/i)).toBeInTheDocument();
  });

  test("Action Proposals does not change when selecting different run", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    const stableProposals = {
      proposals: [
        { proposalId: "stable-proposal-1", status: "pending", confidence: "high", target: "Stable Target 1", rationale: "Stable rationale", expectedBenefit: "Improve stability", sourceRunId: "run-123", latestNote: null, lifecycle: [{ status: "pending", timestamp: "2026-04-07T10:00:00Z", note: null }], artifacts: [{ label: "diagnostic", path: "/artifacts/stable-1.json" }] },
        { proposalId: "stable-proposal-2", status: "approved", confidence: "medium", target: "Stable Target 2", rationale: "Another stable rationale", expectedBenefit: "Reduce alerts", sourceRunId: "run-123", latestNote: null, lifecycle: [{ status: "approved", timestamp: "2026-04-07T11:00:00Z", note: null }], artifacts: [{ label: "diagnostic", path: "/artifacts/stable-2.json" }] },
      ],
      statusSummary: [{ status: "pending", count: 1 }, { status: "approved", count: 1 }],
    };
    const fetchMock = createRunAwareFetchMock(run123, run122, { "/api/proposals": stableProposals });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });
    const proposalsSection = document.getElementById("proposals");
    expect(proposalsSection).toBeInTheDocument();
    expect(within(proposalsSection).getByText(/Stable Target 1/i)).toBeInTheDocument();
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();
    await act(async () => { await user.click(run122Row!); });
    expect(within(proposalsSection).getByText(/Stable Target 1/i)).toBeInTheDocument();
  });

  test("Notification History does not change when selecting different run", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    const stableNotifications = {
      notifications: [
        { kind: "Info", summary: "Stable notification 1", timestamp: "2026-04-07T10:00:00Z", runId: "run-old", clusterLabel: "cluster-a", context: "stable", details: [] },
        { kind: "Warning", summary: "Stable notification 2", timestamp: "2026-04-07T11:00:00Z", runId: "run-old", clusterLabel: "cluster-b", context: "stable", details: [] },
      ],
      total: 2, page: 1, limit: 50, total_pages: 1,
    };
    const fetchMock = createRunAwareFetchMock(run123, run122, {
      "/api/notifications": stableNotifications,
      "/api/notifications?limit=50&page=1": stableNotifications,
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });
    const notificationSection = document.getElementById("notifications");
    expect(notificationSection).toBeInTheDocument();
    expect(within(notificationSection).getByText(/Stable notification 1/i)).toBeInTheDocument();
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();
    await act(async () => { await user.click(run122Row!); });
    expect(within(notificationSection).getByText(/Stable notification 1/i)).toBeInTheDocument();
  });
});
