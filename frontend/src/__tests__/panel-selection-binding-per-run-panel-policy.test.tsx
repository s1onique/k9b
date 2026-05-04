// Panel selection binding tests — Per-run panels (policy & activity)

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

describe("Panel selection binding - Per-run panels", () => {
  test("Deterministic Next Checks Panel shows run-specific data", async () => {
    const run123 = createRun123Payload();
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

    // Find the Deterministic Next Checks Panel
    const deterministicPanel = document.getElementById("deterministic-next-checks");
    expect(deterministicPanel).toBeInTheDocument();

    // Should show run-123 deterministic check
    await waitFor(() => {
      expect(within(deterministicPanel!).getByText(/Run 123 deterministic check/i)).toBeInTheDocument();
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

    // Should show empty state for run-122 (no deterministic checks) - re-query panel
    const updatedDeterministicPanel = document.getElementById("deterministic-next-checks");
    await waitFor(() => {
      expect(within(updatedDeterministicPanel!).getByText(/No evidence-based checks are available for this run/i)).toBeInTheDocument();
    });
  });

  test("LLM Policy Panel shows run-specific policy data", async () => {
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

    // Find the LLM Policy Panel
    const llmPolicyPanel = document.getElementById("llm-policy");
    expect(llmPolicyPanel).toBeInTheDocument();

    // --- STRENGTHENED: Assert run-123 specific content BEFORE switching ---
    // Run-123 llmPolicy.autoDrilldown: enabled=true, provider=default, usedThisRun=1, success/failed/skipped=1/0/0
    await waitFor(() => {
      expect(within(llmPolicyPanel!).getByText(/used this run/i)).toBeInTheDocument();
    });

    // Check enabled status pill
    await waitFor(() => {
      expect(within(llmPolicyPanel!).getByText(/Auto drilldown enabled/i)).toBeInTheDocument();
    });

    // Check provider name (rendered as separate elements: "Provider" label + "default" value)
    await waitFor(() => {
      expect(within(llmPolicyPanel!).getByText(/^Provider$/i)).toBeInTheDocument();
      // The value is rendered as <strong>default</strong>
      expect(within(llmPolicyPanel!).getByText(/^default$/)).toBeInTheDocument();
    });

    // Check success count (run-123: 1 successful, 0 failed, 0 skipped)
    await waitFor(() => {
      expect(within(llmPolicyPanel!).getByText(/1 \/ 0 \/ 0/i)).toBeInTheDocument();
    });

    // Check budget status
    await waitFor(() => {
      expect(within(llmPolicyPanel!).getByText(/Within budget/i)).toBeInTheDocument();
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

    // --- STRENGTHENED: Assert run-122 specific content AFTER switching ---
    // Run-122 llmPolicy.autoDrilldown: enabled=false, provider=stub, usedThisRun=0, success/failed/skipped=0/0/0
    // Re-query panel since DOM may have changed
    const updatedLlmPolicyPanel = document.getElementById("llm-policy");

    // Check disabled status pill
    await waitFor(() => {
      expect(within(updatedLlmPolicyPanel!).getByText(/Auto drilldown disabled/i)).toBeInTheDocument();
    });

    // Check provider changed to stub (rendered as separate elements)
    await waitFor(() => {
      expect(within(updatedLlmPolicyPanel!).getByText(/^Provider$/i)).toBeInTheDocument();
      // The value is rendered as <strong>stub</strong>
      expect(within(updatedLlmPolicyPanel!).getByText(/^stub$/)).toBeInTheDocument();
    });

    // Check success/failed/skipped changed to 0/0/0
    await waitFor(() => {
      expect(within(updatedLlmPolicyPanel!).getByText(/0 \/ 0 \/ 0/i)).toBeInTheDocument();
    });

    // Panel should still be visible
    await waitFor(() => {
      expect(within(updatedLlmPolicyPanel!).getByText(/used this run/i)).toBeInTheDocument();
    });
  });

  test("LLM Activity Panel shows run-specific activity data", async () => {
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

    // Find the LLM Activity Panel
    const llmActivityPanel = document.getElementById("llm-activity");
    expect(llmActivityPanel).toBeInTheDocument();

    // Should show run-123 LLM activity entry - wait for data first
    await waitFor(() => {
      expect(screen.getByText(/Run 123 LLM activity/i)).toBeInTheDocument();
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

    // Should now show run-122 LLM activity entry - wait for data first
    await waitFor(() => {
      expect(screen.getByText(/Run 122 LLM activity/i)).toBeInTheDocument();
    });
  });
});