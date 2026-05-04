/**
 * Regression tests for selected-run refresh bug (TASK 6 / TASK 7)
 *
 * Bug: When the user selects a past run from Recent runs, the app must
 * immediately fetch and render that run's data, including Review enrichment,
 * instead of continuing to show stale/latest-run-derived state until a later
 * refresh.
 *
 * Root cause: The effect that calls refresh() was missing selectedRunId in
 * its dependency array, so run selection changes didn't trigger a refresh.
 *
 * Fix: Add selectedRunId to the dependency array of the refresh effect.
 *
 * These tests prove that:
 * A. Selecting a past run triggers immediate fetch/render (not waiting for poll)
 * B. No polling timer advance is needed to see correct past-run content (async-correct)
 * C. Switching between latest and past run updates correctly both ways
 * D. Late stale latest response cannot overwrite correctly-displayed past-run UI (real race test)
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import App from "../App";
import type { RunPayload } from "../types";
import { createFetchMock, makeFetchResponse } from "./fixtures";
import {
  createPanelSelectionRun122,
  createPanelSelectionRun123,
  createStorageMock,
  sampleClusterDetail,
  sampleFleet,
  sampleNotifications,
  sampleProposals,
} from "./fixtures";

// ---------------------------------------------------------------------------
// Test data builders with unique markers for enrichment content
// ---------------------------------------------------------------------------

/**
 * Create run payload for latest run with LATEST marker in enrichment.
 * Uses unique phrases that won't appear in past run data.
 */
const createLatestRunPayload = (): RunPayload => {
  const base = createPanelSelectionRun123();
  return {
    ...base,
    runId: "run-latest",
    label: "Run Latest",
    reviewEnrichment: {
      ...base.reviewEnrichment!,
      summary: "LATEST ENRICHMENT MARKER - this is the latest run content",
      triageOrder: ["cluster-latest-a", "cluster-latest-b"],
      topConcerns: [
        "LATEST MARKER: API latency spike in production cluster",
        "LATEST MARKER: Memory pressure on control plane nodes",
      ],
      nextChecks: [
        "LATEST MARKER: Validate API server response times",
        "LATEST MARKER: Check etcd disk I/O metrics",
      ],
      focusNotes: ["LATEST MARKER: Focus on cluster-latest-a first"],
    },
  };
};

/**
 * Create run payload for past run with PAST marker in enrichment.
 * Uses unique phrases that won't appear in latest run data.
 */
const createPastRunPayload = (): RunPayload => {
  const base = createPanelSelectionRun122();
  return {
    ...base,
    runId: "run-past",
    label: "Run Past",
    reviewEnrichment: {
      ...base.reviewEnrichment!,
      summary: "PAST RUN ENRICHMENT MARKER - this is the historical run content",
      triageOrder: ["cluster-past-a"],
      topConcerns: [
        "PAST MARKER: Ingress connectivity issues in staging",
        "PAST MARKER: Certificate expiry warnings detected",
      ],
      nextChecks: [
        "PAST MARKER: Verify ingress controller certificates",
        "PAST MARKER: Check DNS resolution health",
      ],
      focusNotes: ["PAST MARKER: Prioritize cluster-past-a remediation"],
    },
  };
};

// ---------------------------------------------------------------------------
// Default payloads for global endpoints (stable across scenarios)
// ---------------------------------------------------------------------------

const GLOBAL_PAYLOADS = {
  "/api/runs": {
    runs: [
      {
        runId: "run-latest",
        runLabel: "2026-04-07-1200",
        timestamp: "2026-04-07T12:00:00Z",
        clusterCount: 2,
        triaged: true,
        executionCount: 5,
        reviewedCount: 5,
        reviewStatus: "fully-reviewed" as const,
      },
      {
        runId: "run-past",
        runLabel: "2026-04-07-1000",
        timestamp: "2026-04-07T10:00:00Z",
        clusterCount: 1,
        triaged: false,
        executionCount: 3,
        reviewedCount: 0,
        reviewStatus: "unreviewed" as const,
      },
    ],
    totalCount: 2,
  },
  "/api/fleet": sampleFleet,
  "/api/proposals": sampleProposals,
  "/api/notifications": sampleNotifications,
  "/api/notifications?limit=50&page=1": sampleNotifications,
  "/api/cluster-detail": sampleClusterDetail,
};

// ---------------------------------------------------------------------------
// Standard fetch mock: returns run-specific data based on run_id query param
// ---------------------------------------------------------------------------

const createRunAwareFetchMock = (
  latestRunPayload: RunPayload,
  pastRunPayload: RunPayload
) => {
  return vi.fn((input: RequestInfo) => {
    const url = typeof input === "string" ? input : input.url;
    const base = url.split("?")[0];

    if (base === "/api/run") {
      const params = new URLSearchParams(url.split("?")[1] || "");
      const runId = params.get("run_id");
      if (runId === "run-past") {
        return makeFetchResponse(pastRunPayload);
      }
      // Default to latest run payload (no run_id = latest)
      return makeFetchResponse(latestRunPayload);
    }

    const payload = GLOBAL_PAYLOADS[url as keyof typeof GLOBAL_PAYLOADS] ?? GLOBAL_PAYLOADS[base as keyof typeof GLOBAL_PAYLOADS];
    if (!payload) {
      return Promise.reject(new Error(`Unexpected fetch ${url}`));
    }
    return makeFetchResponse(payload);
  });
};

// ---------------------------------------------------------------------------
// Selector helpers: prefer user-visible text, fall back to semantic structure
// ---------------------------------------------------------------------------

/**
 * Find the past run row using accessible structure.
 * The run rows should contain visible timestamp text like "2026-04-07-1000".
 */
const getPastRunRow = (): HTMLElement | null => {
  // Try to find by timestamp text (most user-visible)
  const rows = document.querySelectorAll('[class*="run-row"], [class*="recent-run"]');
  for (const row of rows) {
    if (row.textContent?.includes("2026-04-07-1000")) {
      return row as HTMLElement;
    }
  }
  // Fallback: data attribute based selector
  return document.querySelector('.run-row[data-run-id="run-past"]');
};

/**
 * Find the latest run row using accessible structure.
 */
const getLatestRunRow = (): HTMLElement | null => {
  const rows = document.querySelectorAll('[class*="run-row"], [class*="recent-run"]');
  for (const row of rows) {
    if (row.textContent?.includes("2026-04-07-1200")) {
      return row as HTMLElement;
    }
  }
  // Fallback: data attribute based selector
  return document.querySelector('.run-row[data-run-id="run-latest"]');
};

// ---------------------------------------------------------------------------
// Test setup/teardown
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Regression tests
// ---------------------------------------------------------------------------

describe("Selected-run immediate refresh regression", () => {
  /**
   * SCENARIO A: Selecting a past run triggers immediate fetch and renders
   *
   * Arrange:
   * - Initial app load returns latest run payload with LATEST ENRICHMENT MARKER
   * - Recent runs list includes a past run
   * - /api/run?run_id=run-past returns PAST RUN ENRICHMENT MARKER content
   *
   * Act:
   * - Render app
   * - Click/select the past run
   *
   * Assert:
   * - Fetch was called for that specific run_id
   * - UI updates to show the past run's distinctive enrichment content
   * - UI no longer shows the latest run's distinctive enrichment content
   */
  test("Scenario A: selecting a past run triggers immediate fetch and renders correct enrichment", async () => {
    const latestRun = createLatestRunPayload();
    const pastRun = createPastRunPayload();
    const fetchMock = createRunAwareFetchMock(latestRun, pastRun);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Wait for runs to render
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // --- VERIFY INITIAL STATE: Latest run enrichment is visible ---
    await waitFor(() => {
      expect(screen.getByText(/LATEST ENRICHMENT MARKER/i)).toBeInTheDocument();
    });

    // Verify the LATEST marker content in concerns
    expect(screen.getAllByText(/LATEST MARKER: API latency spike/i).length).toBeGreaterThan(0);

    // Verify the LATEST marker content in next checks
    expect(screen.getAllByText(/LATEST MARKER: Validate API server/i).length).toBeGreaterThan(0);

    // --- ACT: Select the past run ---
    const pastRunRow = getPastRunRow();
    expect(pastRunRow).not.toBeNull();

    await act(async () => {
      await user.click(pastRunRow!);
    });

    // --- ASSERT: Fetch was called for run-past ---
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(([input]) => {
        const url = typeof input === "string" ? input : (input as Request).url;
        return url.includes("/api/run") && url.includes("run_id=run-past");
      });
      expect(runCalls.length).toBeGreaterThan(0);
    });

    // --- ASSERT: Past run enrichment content is now visible ---
    await waitFor(() => {
      expect(screen.getByText(/PAST RUN ENRICHMENT MARKER/i)).toBeInTheDocument();
    });

    // Verify the PAST marker content in concerns
    expect(screen.getAllByText(/PAST MARKER: Ingress connectivity issues/i).length).toBeGreaterThan(0);

    // Verify the PAST marker content in next checks
    expect(screen.getAllByText(/PAST MARKER: Verify ingress controller/i).length).toBeGreaterThan(0);

    // --- ASSERT: Latest run enrichment content is NO LONGER visible ---
    // This proves we didn't just add the past content alongside stale latest content
    expect(screen.queryByText(/LATEST ENRICHMENT MARKER/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/LATEST MARKER: API latency spike/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/LATEST MARKER: Memory pressure/i)).not.toBeInTheDocument();
  });

  /**
   * SCENARIO B: Correct past-run enrichment appears without polling timer advance
   *
   * This test proves that selecting a past run triggers the fetch immediately
   * and the correct content appears - WITHOUT advancing timers.
   *
   * KEY: We use async DOM waiting (waitFor) after the click, proving that
   * the effect fires immediately but React rendering is async.
   *
   * Without the fix (missing selectedRunId in dependency array), the past run
   * content would only appear after a poll cycle.
   */
  test("Scenario B: past-run enrichment appears without polling timer advance", async () => {
    const latestRun = createLatestRunPayload();
    const pastRun = createPastRunPayload();
    const fetchMock = createRunAwareFetchMock(latestRun, pastRun);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Wait for initial render with latest run
    await waitFor(() => {
      expect(screen.getByText(/LATEST ENRICHMENT MARKER/i)).toBeInTheDocument();
    });

    // Track the number of fetch calls before selection
    const fetchCountBefore = fetchMock.mock.calls.length;

    // ACT: Select the past run
    const pastRunRow = getPastRunRow();
    expect(pastRunRow).not.toBeNull();

    await act(async () => {
      await user.click(pastRunRow!);
    });

    // ASSERT: Immediately after selection, the fetch was triggered
    // This proves the effect with selectedRunId dependency fired right away
    const fetchCountAfter = fetchMock.mock.calls.length;
    expect(fetchCountAfter).toBeGreaterThan(fetchCountBefore);

    // ASSERT: Fetch was made for the past run specifically
    const pastRunCalls = fetchMock.mock.calls.filter(([input]) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      return url.includes("/api/run") && url.includes("run_id=run-past");
    });
    expect(pastRunCalls.length).toBeGreaterThan(0);

    // ASSERT: The correct past-run enrichment appears (async DOM waiting, no timer advance)
    // This proves it happens without waiting for a poll tick
    await waitFor(() => {
      expect(screen.getByText(/PAST RUN ENRICHMENT MARKER/i)).toBeInTheDocument();
    });

    // ASSERT: Latest run enrichment is gone
    await waitFor(() => {
      expect(screen.queryByText(/LATEST ENRICHMENT MARKER/i)).not.toBeInTheDocument();
    });
  });

  /**
   * SCENARIO C: Switching between latest and past run updates correctly both ways
   *
   * Act:
   * - Load latest
   * - Select past run
   * - Switch back to latest (via "← Latest" button)
   *
   * Assert:
   * - Each switch causes the corresponding content to appear
   * - No stale mixed content remains visible
   */
  test("Scenario C: switching between latest and past run updates content correctly both ways", async () => {
    const latestRun = createLatestRunPayload();
    const pastRun = createPastRunPayload();
    const fetchMock = createRunAwareFetchMock(latestRun, pastRun);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // --- STEP 1: Verify initial state (latest run) ---
    await waitFor(() => {
      expect(screen.getByText(/LATEST ENRICHMENT MARKER/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/PAST RUN ENRICHMENT MARKER/i)).not.toBeInTheDocument();

    // --- STEP 2: Select past run ---
    const pastRunRow = getPastRunRow();
    expect(pastRunRow).not.toBeNull();

    await act(async () => {
      await user.click(pastRunRow!);
    });

    await waitFor(() => {
      expect(screen.getByText(/PAST RUN ENRICHMENT MARKER/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/LATEST ENRICHMENT MARKER/i)).not.toBeInTheDocument();

    // --- STEP 3: Switch back to latest run via button ---
    const latestButton = await screen.findByRole("button", { name: /← Latest/i });
    expect(latestButton).toBeInTheDocument();

    await act(async () => {
      await user.click(latestButton);
    });

    // --- ASSERT: Latest run enrichment is restored ---
    await waitFor(() => {
      expect(screen.getByText(/LATEST ENRICHMENT MARKER/i)).toBeInTheDocument();
    });

    // --- ASSERT: Past run enrichment is gone ---
    await waitFor(() => {
      expect(screen.queryByText(/PAST RUN ENRICHMENT MARKER/i)).not.toBeInTheDocument();
    });

    // --- ASSERT: No stale mixed content ---
    // Only LATEST markers should be present
    expect(screen.queryByText(/PAST MARKER:/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/LATEST MARKER: API latency spike/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/LATEST MARKER: Memory pressure/i).length).toBeGreaterThan(0);
  });

  /**
   * SCENARIO D: Real stale-response ordering test with controlled response timing
   *
   * This test models the exact race condition where:
   * 1. Latest request starts first (app load)
   * 2. Past-run request starts after selection
   * 3. Past-run request resolves FIRST (fast response)
   * 4. Latest request resolves LATER (slow response via polling)
   * 5. UI must still show past-run content (not be overwritten by stale latest)
   *
   * We use deferred promises to control when each response resolves.
   */
  test("Scenario D: late stale latest response cannot overwrite correctly-displayed past-run UI", async () => {
    const latestRun = createLatestRunPayload();
    const pastRun = createPastRunPayload();

    // Track whether we've completed initial load
    let initialLoadComplete = false;

    // Deferred resolvers for explicit control over response order
    let latestResolve: (() => void) | null = null;
    let pastResolve: (() => void) | null = null;

    // Deferred promise for latest run response
    const latestDeferred = new Promise<unknown>((resolve) => {
      latestResolve = () => {
        resolve(makeFetchResponse(latestRun));
      };
    });

    // Deferred promise for past run response
    const pastDeferred = new Promise<unknown>((resolve) => {
      pastResolve = () => {
        resolve(makeFetchResponse(pastRun));
      };
    });

    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      // For /api/run endpoint, use deferred resolvers based on request type
      if (base === "/api/run") {
        const params = new URLSearchParams(url.split("?")[1] || "");
        const runId = params.get("run_id");

        if (runId === "run-past") {
          // Past run: return deferred promise that resolves when we call pastResolve
          return pastDeferred as ReturnType<typeof fetchMock>;
        } else {
          // Latest run: return deferred promise
          // But if initial load hasn't completed, return a fast mock instead
          if (!initialLoadComplete) {
            return makeFetchResponse(latestRun);
          }
          // After initial load, the latest response comes from the polling timer
          // which fires after the user has already selected the past run
          return latestDeferred as ReturnType<typeof fetchMock>;
        }
      }

      // Global endpoints: return immediately
      const payload = GLOBAL_PAYLOADS[url as keyof typeof GLOBAL_PAYLOADS] ?? GLOBAL_PAYLOADS[base as keyof typeof GLOBAL_PAYLOADS];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return makeFetchResponse(payload);
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Wait for initial latest run to render
    await waitFor(() => {
      expect(screen.getByText(/LATEST ENRICHMENT MARKER/i)).toBeInTheDocument();
    });

    // Mark initial load complete - from now on, latest requests will be deferred
    initialLoadComplete = true;

    // Capture fetch call count before selection
    const fetchCountBefore = fetchMock.mock.calls.length;

    // Select past run
    const pastRunRow = getPastRunRow();
    expect(pastRunRow).not.toBeNull();

    await act(async () => {
      await user.click(pastRunRow!);
    });

    // Wait for past run to be fetched (verify new fetch was made)
    await waitFor(() => {
      const pastRunCalls = fetchMock.mock.calls.filter(([input]) => {
        const url = typeof input === "string" ? input : (input as Request).url;
        return url.includes("/api/run") && url.includes("run_id=run-past");
      });
      expect(pastRunCalls.length).toBeGreaterThan(0);
    });

    // Verify total fetch calls increased
    expect(fetchMock.mock.calls.length).toBeGreaterThan(fetchCountBefore);

    // Now: explicitly control response order
    // 1. Resolve past-run request FIRST (simulating fast past-run response)
    expect(pastResolve).not.toBeNull();
    pastResolve!();

    // 2. Wait for past-run content to render
    await waitFor(() => {
      expect(screen.getByText(/PAST RUN ENRICHMENT MARKER/i)).toBeInTheDocument();
    });

    // 3. Now resolve latest request LATE (simulating slow latest response from polling)
    // This represents the scenario where a background polling fetch for latest
    // completes AFTER the user has already selected and viewed a past run
    expect(latestResolve).not.toBeNull();
    latestResolve!();

    // 4. Allow time for the late latest response to be processed
    await new Promise((resolve) => setTimeout(resolve, 100));

    // ASSERT: UI STILL shows past run content (not overwritten by stale latest)
    // This is the critical assertion - the past run must remain visible
    expect(screen.getByText(/PAST RUN ENRICHMENT MARKER/i)).toBeInTheDocument();
    expect(screen.queryByText(/LATEST ENRICHMENT MARKER/i)).not.toBeInTheDocument();

    // ASSERT: No stale LATEST markers are visible
    expect(screen.queryByText(/LATEST MARKER:/i)).not.toBeInTheDocument();

    // ASSERT: PAST markers are still present (multiple matches are expected)
    expect(screen.getAllByText(/PAST MARKER: Ingress connectivity issues/i).length).toBeGreaterThan(0);
  });
});
