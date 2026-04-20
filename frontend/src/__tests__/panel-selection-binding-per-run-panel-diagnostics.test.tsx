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

    // Should show the panel heading
    await waitFor(() => {
      expect(within(packPanel!).getByRole("heading", { name: /Run diagnostic package archive/i })).toBeInTheDocument();
    });

    // --- STRENGTHENED: Assert run-123 specific content BEFORE switching ---
    // Run-123 diagnosticPack: timestamp 2026-04-07T12:00:00Z (Apr 7, 2026 12:00 UTC)
    await waitFor(() => {
      // Verify run-123 timestamp is rendered
      expect(within(packPanel!).getByText(/Apr 7, 2026 12:00 UTC/i)).toBeInTheDocument();
    });

    // Verify Download link exists with run-123 path (URL-encoded)
    const run123Link = within(packPanel!).getByText(/Download diagnostic pack/i);
    expect(run123Link).toBeInTheDocument();
    // The href is URL-encoded: /artifact?path=%2Fartifacts%2Frun-123-diagnostic-pack.zip
    const run123Href = run123Link.getAttribute("href") || "";
    expect(decodeURIComponent(run123Href)).toContain("/artifacts/run-123-diagnostic-pack.zip");

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

    // --- STRENGTHENED: Assert run-122 specific content AFTER switching ---
    // Run-122 diagnosticPack: timestamp 2026-04-07T11:00:00Z (Apr 7, 2026 11:00 UTC)
    await waitFor(() => {
      // Verify timestamp changed to run-122
      expect(within(packPanel!).getByText(/Apr 7, 2026 11:00 UTC/i)).toBeInTheDocument();
    });

    // Verify download link changed to run-122 path (URL-encoded)
    const run122Link = within(packPanel!).getByText(/Download diagnostic pack/i);
    expect(run122Link).toBeInTheDocument();
    const run122Href = run122Link.getAttribute("href") || "";
    expect(decodeURIComponent(run122Href)).toContain("/artifacts/run-122-diagnostic-pack.zip");

    // Panel should still be visible
    await waitFor(() => {
      expect(within(packPanel!).getByRole("heading", { name: /Run diagnostic package archive/i })).toBeInTheDocument();
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

    // Should show run-123 disagreement
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

    // Should now show run-122 disagreement
    await waitFor(() => {
      expect(within(reviewPanel!).getByText(/Run 122 disagreement 1/i)).toBeInTheDocument();
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

    // Find the Run Summary Panel
    const summaryPanel = document.getElementById("run-detail");
    expect(summaryPanel).toBeInTheDocument();

    // Should show run-123 label
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

    // Should now show run-122 label
    await waitFor(() => {
      expect(within(summaryPanel!).getByRole("heading", { name: /Run 122/i })).toBeInTheDocument();
    });
  });
});