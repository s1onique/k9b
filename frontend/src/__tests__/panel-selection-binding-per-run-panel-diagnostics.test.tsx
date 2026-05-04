// Panel selection binding tests — Per-run panels (diagnostics)

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App from "../App";
import type { RunPayload } from "../types";
import {
  createPanelSelectionRun123,
  createPanelSelectionRun122,
  createStorageMock,
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

describe("Panel selection binding - Per-run panels", () => {
  test("Run Diagnostic Pack Panel shows run-specific pack data", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    const fetchMock = createRunAwareFetchMock(run123, run122);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Find the Diagnostic Pack Download Panel
    const packPanel = document.getElementById("diagnostic-pack-download");
    expect(packPanel).toBeInTheDocument();

    // Wait for panel heading to appear
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Run diagnostic package/i })).toBeInTheDocument();
    });

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Verify fetch was called with run-122
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : (input as Request).url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    // Panel should still be visible with heading
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Run diagnostic package/i })).toBeInTheDocument();
    });
  });

  test("Diagnostic Pack Review Panel shows run-specific review data", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    const fetchMock = createRunAwareFetchMock(run123, run122);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Find the Diagnostic Pack Review Panel
    const reviewPanel = document.getElementById("diagnostic-pack-review");
    expect(reviewPanel).toBeInTheDocument();

    // Wait for data to load FIRST before using within()
    await waitFor(() => {
      expect(screen.getByText(/Run 123 disagreement 1/i)).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(within(reviewPanel!).getByText(/Run 123 disagreement 1/i)).toBeInTheDocument();
    });

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Verify fetch was called with run-122
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : (input as Request).url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    // Should now show run-122 disagreement - re-query panel since DOM may have changed
    await waitFor(() => {
      expect(screen.getByText(/Run 122 disagreement 1/i)).toBeInTheDocument();
    });
    // Re-query the panel element after state change (stale element reference issue)
    const updatedReviewPanel = document.getElementById("diagnostic-pack-review");
    await waitFor(() => {
      expect(within(updatedReviewPanel!).getByText(/Run 122 disagreement 1/i)).toBeInTheDocument();
    });
  });

  test("Run Summary shows run-specific data", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    const fetchMock = createRunAwareFetchMock(run123, run122);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Find the Run Summary Panel (re-query after state changes)
    const summaryPanel = document.getElementById("run-detail");
    expect(summaryPanel).toBeInTheDocument();

    // Wait for data to load FIRST before using within()
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Run 123/i })).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(within(summaryPanel!).getByRole("heading", { name: /Run 123/i })).toBeInTheDocument();
    });

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Verify fetch was called with run-122
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : (input as Request).url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    // Should now show run-122 label - re-query panel since DOM may have changed
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Run 122/i })).toBeInTheDocument();
    });
    // Re-query the panel element after state change (stale element reference issue)
    const updatedSummaryPanel = document.getElementById("run-detail");
    await waitFor(() => {
      expect(within(updatedSummaryPanel!).getByRole("heading", { name: /Run 122/i })).toBeInTheDocument();
    });
  });
});
