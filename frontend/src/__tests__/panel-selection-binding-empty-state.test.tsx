// Panel selection binding tests — Empty state wording

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
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve(run122Payload),
        });
      }
      // Default to run-123 payload
      return Promise.resolve({
        ok: true, status: 200, statusText: "OK",
        json: () => Promise.resolve(run123Payload),
      });
    }

    const payload = defaultPayloads[url] ?? defaultPayloads[base];
    if (!payload) {
      return Promise.reject(new Error(`Unexpected fetch ${url}`));
    }
    return Promise.resolve({
      ok: true, status: 200, statusText: "OK",
      json: () => Promise.resolve(payload),
    });
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

describe("Panel selection binding - Empty state wording", () => {
  test("Review Enrichment empty state says 'for this run'", async () => {
    const run123 = createRun123Payload({ reviewEnrichment: undefined, reviewEnrichmentStatus: undefined });
    const run122 = createRun122Payload({ reviewEnrichment: undefined, reviewEnrichmentStatus: undefined });
    const fetchMock = createRunAwareFetchMock(run123, run122);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Should show empty state for run-123
    await waitFor(() => {
      expect(screen.getByText(/Provider-assisted review enrichment is not configured for this run/i)).toBeInTheDocument();
    });

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Should still show 'for this run' wording
    await waitFor(() => {
      expect(screen.getByText(/Provider-assisted review enrichment is not configured for this run/i)).toBeInTheDocument();
    });
  });

  test("Deterministic Next Checks empty state says 'for this run'", async () => {
    const run123 = createRun123Payload({ deterministicNextChecks: null });
    const run122 = createRun122Payload({ deterministicNextChecks: null });
    const fetchMock = createRunAwareFetchMock(run123, run122);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Find the deterministic panel
    const deterministicPanel = document.getElementById("deterministic-next-checks");
    expect(deterministicPanel).toBeInTheDocument();

    // Should show empty state for run-123
    await waitFor(() => {
      expect(within(deterministicPanel!).getByText(/No evidence-based checks are available for this run/i)).toBeInTheDocument();
    });

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Should still show 'for this run' wording
    await waitFor(() => {
      expect(within(deterministicPanel!).getByText(/No evidence-based checks are available for this run/i)).toBeInTheDocument();
    });
  });
});