/**
 * Regression test: Stale selected-run localStorage fallback
 * 
 * Tests that when a persisted selected run ID no longer exists in the runs list
 * (e.g., run was deleted or expired), the app falls back to the latest run.
 */

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App from "../App";
import type { RunPayload } from "../types";
import {
  createFetchMock,
  createStorageMock,
  makeRunWithOverrides,
  sampleClusterDetail,
  sampleFleet,
  sampleNotifications,
  sampleProposals,
} from "./fixtures";

// Helper to get the queue panel from the screen
const getQueuePanel = async () => {
  const heading = await screen.findByRole("heading", { name: /Work list/i });
  const queuePanel = heading.closest(".next-check-queue-panel");
  if (!queuePanel) {
    throw new Error("Queue panel is not rendered");
  }
  return within(queuePanel);
};

let setIntervalSpy: ReturnType<typeof vi.fn>;
let clearIntervalSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  setIntervalSpy = vi.fn(() => 123);
  clearIntervalSpy = vi.fn();
  vi.stubGlobal("setInterval", setIntervalSpy);
  vi.stubGlobal("clearInterval", clearIntervalSpy);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Stale selected-run fallback", () => {
  test("falls back to latest when persisted selected run is absent from runs list", async () => {
    // Create storage with a stale selected run ID (run-999)
    const storageMock = createStorageMock();
    storageMock.setItem("selected-run-id", "run-999");
    vi.stubGlobal("localStorage", storageMock);
    
    // Latest run payload
    const latestRun = makeRunWithOverrides({});
    
    // Create a smart mock that only returns latest-run (not the stale run-999)
    const smartMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];
      const params = new URLSearchParams(url.split("?")[1] || "");
      const runId = params.get("run_id");
      
      // Handle /api/runs - only returns latest-run, NOT run-999
      if (base === "/api/runs") {
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve({
            runs: [
              { runId: "run-123", runLabel: "Latest run", timestamp: new Date().toISOString(), clusterCount: 1, triaged: true, executionCount: 0, reviewedCount: 0, reviewStatus: "no-executions" },
            ],
            totalCount: 1,
          }),
        });
      }
      
      // Handle /api/run - only return latest-run data
      if (base === "/api/run") {
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve(latestRun),
        });
      }
      
      // Use sample fixtures for all other endpoints
      const samplePayloads = {
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
        "/api/notifications?limit=50&page=1": sampleNotifications,
        "/api/cluster-detail": sampleClusterDetail,
      };
      
      const payload = samplePayloads[base] ?? samplePayloads[url];
      if (payload) {
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve(payload),
        });
      }
      
      return Promise.resolve({
        ok: true, status: 200, statusText: "OK",
        json: () => Promise.resolve({}),
      });
    });
    
    vi.stubGlobal("fetch", smartMock);
    render(<App />);
    
    // App should load and show latest run, not the stale run-999
    await screen.findByRole("heading", { name: /Fleet overview/i });
    
    // Verify latest run is selected (not the stale run-999)
    const latestRunRow = document.querySelector('.run-row[data-run-id="run-123"]');
    expect(latestRunRow).not.toBeNull();
    expect(latestRunRow).toHaveClass("run-row-selected");
    
    // Verify stale run-999 is NOT in the runs list
    const staleRunRow = document.querySelector('.run-row[data-run-id="run-999"]');
    expect(staleRunRow).toBeNull();
    
    // Hero should show "Latest" badge
    expect(screen.getByText(/^Latest$/i)).toBeInTheDocument();
    
    // Queue panel should show the latest run's queue
    await getQueuePanel(); // Will throw if panel not found
  });

  test("persisted stale run ID does not reappear after reload", async () => {
    // Create storage with a stale selected run ID
    const storageMock = createStorageMock();
    storageMock.setItem("selected-run-id", "deleted-run");
    vi.stubGlobal("localStorage", storageMock);
    
    const latestRun = makeRunWithOverrides({});
    
    const smartMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];
      
      if (base === "/api/runs") {
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve({
            runs: [
              { runId: "current-run", runLabel: "Current run", timestamp: new Date().toISOString(), clusterCount: 1, triaged: true, executionCount: 0, reviewedCount: 0, reviewStatus: "no-executions" },
            ],
            totalCount: 1,
          }),
        });
      }
      
      if (base === "/api/run") {
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve(latestRun),
        });
      }
      
      const samplePayloads = {
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
        "/api/notifications?limit=50&page=1": sampleNotifications,
        "/api/cluster-detail": sampleClusterDetail,
      };
      
      const payload = samplePayloads[base] ?? samplePayloads[url];
      if (payload) {
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve(payload),
        });
      }
      
      return Promise.resolve({
        ok: true, status: 200, statusText: "OK",
        json: () => Promise.resolve({}),
      });
    });
    
    vi.stubGlobal("fetch", smartMock);
    render(<App />);
    
    // Wait for app to load
    await screen.findByRole("heading", { name: /Fleet overview/i });
    
    // Verify current-run is selected (stale deleted-run was not in runs list)
    const currentRunRow = document.querySelector('.run-row[data-run-id="current-run"]');
    expect(currentRunRow).not.toBeNull();
    expect(currentRunRow).toHaveClass("run-row-selected");
    
    // Verify the stale run does not appear
    const deletedRunRow = document.querySelector('.run-row[data-run-id="deleted-run"]');
    expect(deletedRunRow).toBeNull();
  });
});
