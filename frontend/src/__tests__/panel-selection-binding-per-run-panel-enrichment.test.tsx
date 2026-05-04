// Panel selection binding tests — Per-run panels (enrichment & execution)

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App from "../App";
import type {
  DiagnosticPackReview,
  LLMActivity,
  LLMPolicy,
  ProviderExecution,
  RunPayload,
} from "../types";
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
  test("Review Enrichment Panel shows run-specific enrichment data", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    const fetchMock = createRunAwareFetchMock(run123, run122);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Wait for runs to render
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Initially run-123 should be selected - verify enrichment shows run-123 provider
    await waitFor(() => {
      expect(screen.getByText(/Provider k8sgpt/i)).toBeInTheDocument();
    });

    // Verify enrichment summary is from run-123
    expect(screen.getByText(/Run 123 enrichment summary/i)).toBeInTheDocument();

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

    // Verify enrichment now shows run-122 provider
    await waitFor(() => {
      expect(screen.getByText(/Provider llamacpp/i)).toBeInTheDocument();
    });

    // Verify enrichment summary is from run-122
    expect(screen.getByText(/Run 122 enrichment summary/i)).toBeInTheDocument();
  });

  test("Provider Execution Panel shows run-specific execution data", async () => {
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

    // Find the Provider Execution Panel section
    const providerPanel = document.getElementById("provider-execution");
    expect(providerPanel).toBeInTheDocument();

    // Verify the panel is visible with its heading
    await waitFor(() => {
      expect(within(providerPanel!).getByText(/Auto drilldown/i)).toBeInTheDocument();
    });

    // --- STRENGTHENED: Assert run-123 specific content BEFORE switching ---
    // Run-123 autoDrilldown: eligible=2, attempted=1, succeeded=1, failed=0, skipped=0, unattempted=1
    // Run-123 reviewEnrichment: eligible=1, attempted=1, succeeded=1, failed=0, skipped=0, unattempted=0
    // Unique differentiator: unattempted 1 (autoDrilldown) vs unattempted 0 (reviewEnrichment)
    await waitFor(() => {
      // Check both branches exist with expected titles
      expect(within(providerPanel!).getByText(/Auto drilldown/i)).toBeInTheDocument();
      expect(within(providerPanel!).getByText(/Review enrichment/i)).toBeInTheDocument();
      // Use unattempted 1 as unique marker for autoDrilldown in run-123
      expect(within(providerPanel!).getByText(/unattempted 1/i)).toBeInTheDocument();
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
      expect(runCalls.length).toBe(1);
    });

    // --- STRENGTHENED: Assert run-122 specific content AFTER switching ---
    // Run-122 autoDrilldown: eligible=1, attempted=0, succeeded=0, failed=0, skipped=1, unattempted=0
    // Run-122 reviewEnrichment: eligible=1, attempted=1, succeeded=0, failed=1, skipped=0
    // Unique differentiators for run-122: skipped 1 and failed 1
    // Re-query panel since DOM may have changed
    const updatedProviderPanel = document.getElementById("provider-execution");
    await waitFor(() => {
      // Check skipped=1 for autoDrilldown (unique to run-122 vs run-123 which has skipped 0)
      expect(within(updatedProviderPanel!).getByText(/skipped 1/i)).toBeInTheDocument();
      // Check failed=1 for reviewEnrichment (unique to run-122 vs run-123 which has failed 0)
      expect(within(updatedProviderPanel!).getByText(/failed 1/i)).toBeInTheDocument();
    });

    // Panel should still be visible
    await waitFor(() => {
      expect(within(updatedProviderPanel!).getByText(/Auto drilldown/i)).toBeInTheDocument();
    });
  });
});