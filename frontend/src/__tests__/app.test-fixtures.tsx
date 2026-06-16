/**
 * Shared test fixtures and helpers for app.test.tsx split files.
 * 
 * This module extracts the shared setup, mocks, and helpers from app.test.tsx
 * so they can be reused across the split test files.
 * 
 * DO NOT add test cases here - only shared fixtures and helper functions.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import dayjs from "dayjs";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App, { AUTOREFRESH_STORAGE_KEY, QUEUE_VIEW_STORAGE_KEY } from "../App";
import type { NotificationEntry } from "../types";

import {
  createFetchMock,
  createFetchQueueMock,
  createStorageMock,
  makeDiagnosticPackReview,
  makeFetchResponse,
  makeRunWithOverrides,
  sampleClusterDetail,
  sampleFleet,
  sampleNextCheckCandidates,
  sampleNotifications,
  sampleProposals,
  sampleRun,
  sampleRuntimeStatus,
  sampleRunsList,
  UI_STRINGS,
} from "./fixtures";

// Re-export all fixtures for convenience in split files
export {
  createFetchMock,
  createFetchQueueMock,
  createStorageMock,
  makeDiagnosticPackReview,
  makeFetchResponse,
  makeRunWithOverrides,
  sampleClusterDetail,
  sampleFleet,
  sampleNextCheckCandidates,
  sampleNotifications,
  sampleProposals,
  sampleRun,
  sampleRuntimeStatus,
  sampleRunsList,
  UI_STRINGS,
};

// Re-export types
export type { NotificationEntry } from "../types";

/**
 * Timestamp helper - generates timestamps relative to test execution.
 */
export const minsAgo = (minutes: number) => dayjs().subtract(minutes, "minute").toISOString();

// ============================================================
// Default payloads for API mocks
// ============================================================

export const defaultPayloads = {
  "/api/run": sampleRun,
  "/api/runs": sampleRunsList,
  "/api/fleet": sampleFleet,
  "/api/proposals": sampleProposals,
  "/api/notifications": sampleNotifications,
  "/api/notifications?limit=50&page=1": sampleNotifications,
  "/api/cluster-detail": sampleClusterDetail,
  "/api/deterministic-next-check/promote": {
    status: "success",
    summary: "Deterministic next check promoted to the queue.",
    artifactPath: "/artifacts/promoted.json",
    candidateId: "promo-1",
  },
  "/api/runtime-status": sampleRuntimeStatus,
};

// ============================================================
// Shared queue panel helper
// ============================================================

/**
 * Gets the queue panel element and returns a within-scoped query function.
 * Waits for run data to fully load before returning.
 */
export const getQueuePanel = async () => {
  // Wait for run data to load first (queue panel shows "Loading selected run…" when loading)
  await waitFor(() => {
    expect(screen.queryByText(/Loading selected run/i)).not.toBeInTheDocument();
  });
  // Also wait for queue items to appear (approve buttons indicate queue content is ready)
  await waitFor(() => {
    expect(screen.getAllByRole("button", { name: /Approve/i }).length).toBeGreaterThan(0);
  }, { timeout: 5000 });
  const heading = await screen.findByRole("heading", { name: /Work list/i });
  const queuePanel = heading.closest(".next-check-queue-panel");
  if (!queuePanel) {
    throw new Error("Queue panel is not rendered");
  }
  return within(queuePanel);
};

// ============================================================
// Shared deterministic panel helper
// ============================================================

/**
 * Gets the deterministic checks panel element and returns it.
 * Waits for panel to be fully loaded with content.
 */
export const getLoadedDeterministicPanel = async (sentinel: RegExp = /candidate check.*to review and promote/i) => {
  // Wait for panel heading to appear (proves panel shell exists)
  await waitFor(() => {
    const panel = document.getElementById("deterministic-next-checks");
    expect(panel).toBeInTheDocument();
    expect(within(panel!).getByRole("heading", { name: /Deterministic checks/i })).toBeInTheDocument();
  }, { timeout: 5000 });

  // Then wait for loaded-content sentinel (proves run-owned panel, not placeholder)
  await waitFor(() => {
    const panel = document.getElementById("deterministic-next-checks")!;
    expect(within(panel).getByText(sentinel)).toBeInTheDocument();
  }, { timeout: 5000 });

  return document.getElementById("deterministic-next-checks")!;
};

// ============================================================
// Notification builder helpers
// ============================================================

const NOTIFICATION_BASE_TIME = Date.UTC(2026, 3, 7, 0, 0, 0);
export const PLANNER_HINT_TEXT =
  "Cluster Detail next checks may still reflect deterministic assessments or review content even when the planner artifact is absent.";

export const buildNotificationEntry = (
  index: number,
  overrides: Partial<NotificationEntry> = {}
): NotificationEntry => {
  const defaultTimestamp = new Date(NOTIFICATION_BASE_TIME - index * 60000).toISOString();
  return {
    kind: overrides.kind ?? (index % 2 ? "Warning" : "Info"),
    summary: overrides.summary ?? `Notification ${index + 1}`,
    timestamp: overrides.timestamp ?? defaultTimestamp,
    runId: overrides.runId ?? `run-${(index % 3) + 1}`,
    clusterLabel: overrides.clusterLabel ?? `cluster-${(index % 2) + 1}`,
    context: overrides.context ?? "test-context",
    details: overrides.details ?? [{ label: "Pod", value: `pod-${index}` }],
    artifactPath: overrides.artifactPath ?? (index % 4 === 0 ? null : `/artifacts/n-${index}.json`),
  };
};

export const buildNotificationList = (count: number) =>
  Array.from({ length: count }, (_, index) => buildNotificationEntry(index));

// ============================================================
// App render helpers
// ============================================================

/**
 * Renders App with a run that has specific overrides applied.
 */
export const renderAppWithRunOverride = async (overrides: Partial<typeof sampleRun>) => {
  const payloads = {
    ...defaultPayloads,
    "/api/run": makeRunWithOverrides(overrides),
  };
  vi.stubGlobal("fetch", createFetchMock(payloads));
  render(<App />);
  await screen.findByRole("heading", { name: /Fleet overview/i });
};

// ============================================================
// Global mock state for beforeEach/afterEach
// ============================================================

let setIntervalSpy: ReturnType<typeof vi.fn>;
let clearIntervalSpy: ReturnType<typeof vi.fn>;
let storageMock: ReturnType<typeof createStorageMock>;

/**
 * Sets up the global mocks needed for app tests.
 * Call in beforeEach.
 */
export const setupAppTestMocks = () => {
  setIntervalSpy = vi.fn(() => 123);
  clearIntervalSpy = vi.fn();
  vi.stubGlobal("setInterval", setIntervalSpy);
  vi.stubGlobal("clearInterval", clearIntervalSpy);
  storageMock = createStorageMock();
  vi.stubGlobal("localStorage", storageMock);
};

/**
 * Tears down global mocks.
 * Call in afterEach.
 */
export const teardownAppTestMocks = () => {
  vi.restoreAllMocks();
};

/**
 * Creates the standard beforeEach for app tests.
 */
export const createBeforeEach = () => {
  beforeEach(() => {
    setupAppTestMocks();
  });
};

/**
 * Creates the standard afterEach for app tests.
 */
export const createAfterEach = () => {
  afterEach(() => {
    teardownAppTestMocks();
  });
};

// ============================================================
// Export spies for external access (e.g., refresh tests)
// ============================================================

export const getSpies = () => ({ setIntervalSpy, clearIntervalSpy, storageMock });
