/**
 * Regression test for React hook-order violation (#310).
 *
 * This test verifies that App component renders correctly when critical data
 * (fleet/proposals) transitions from unavailable to available, without
 * triggering React hook-order errors.
 *
 * Previously, hooks were called AFTER an early return guard, causing:
 * - First render: data unavailable → early return → hooks NOT called
 * - Later render: data loaded → hooks ARE called → React #310 crash
 *
 * The fix moves ALL hooks before the loading guard and uses conditional
 * rendering in JSX instead of early return.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, test, vi, beforeEach, afterEach, expect } from "vitest";
import App from "../App";
import type { FleetPayload, ProposalsPayload, RunsListPayload } from "../types";
import { createStorageMock, createFetchMock } from "./fixtures";

describe("Hook Order Regression (React #310)", () => {
  const minimalFleet: FleetPayload = {
    clusters: [],
    topProblem: { rating: "healthy", detail: "All systems operational" },
    fleetStatus: { ratingCounts: [] },
    proposalSummary: { pending: 0, total: 0 },
  };

  const minimalProposals: ProposalsPayload = {
    proposals: [],
    totalCount: 0,
  };

  const minimalRunsList: RunsListPayload = {
    runs: [],
    totalCount: 0,
  };

  // Track console errors to detect React #310
  const consoleErrors: string[] = [];
  const originalError = console.error;

  beforeEach(() => {
    const storage = createStorageMock();
    vi.stubGlobal("localStorage", storage);
    // Capture console.error to detect hook-order violations
    console.error = vi.fn((...args: unknown[]) => {
      const msg = args[0]?.toString() ?? "";
      consoleErrors.push(msg);
      originalError.apply(console, args);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    console.error = originalError;
  });

  test("1. app renders with loading state when fleet/proposals unavailable", async () => {
    // Mock fetch that returns null data initially
    const fetchMock = createFetchMock({});
    vi.stubGlobal("fetch", fetchMock);

    consoleErrors.length = 0;
    render(<App />);

    // Loading state should appear
    await waitFor(() => {
      expect(screen.queryByText(/Loading operator data/i)).toBeInTheDocument();
    });

    // No hook-order errors should occur
    const hookOrderErrors = consoleErrors.filter(
      (e) =>
        e.includes("#310") ||
        e.includes("hook") ||
        e.includes("Rendered fewer hooks") ||
        e.includes("Rendered more hooks"),
    );
    expect(hookOrderErrors).toHaveLength(0);
  });

  test("2. app renders main content when fleet/proposals become available", async () => {
    // Mock fetch that returns data
    const fetchMock = createFetchMock({
      "/api/fleet": minimalFleet,
      "/api/proposals": minimalProposals,
      "/api/runs": minimalRunsList,
    });
    vi.stubGlobal("fetch", fetchMock);

    consoleErrors.length = 0;
    render(<App />);

    // Shell should render without blank page
    await waitFor(() => {
      expect(screen.queryByText(/Loading operator data/i)).not.toBeInTheDocument();
    });

    // Fleet overview should be visible
    expect(screen.getByRole("heading", { name: /Fleet overview/i })).toBeInTheDocument();

    // No hook-order errors should occur
    const hookOrderErrors = consoleErrors.filter(
      (e) =>
        e.includes("#310") ||
        e.includes("hook") ||
        e.includes("Rendered fewer hooks") ||
        e.includes("Rendered more hooks"),
    );
    expect(hookOrderErrors).toHaveLength(0);
  });

  test("3. app renders in StrictMode without hook-order errors", async () => {
    // Test with React StrictMode enabled to catch any hook-order issues
    const fetchMock = createFetchMock({
      "/api/fleet": minimalFleet,
      "/api/proposals": minimalProposals,
      "/api/runs": minimalRunsList,
    });
    vi.stubGlobal("fetch", fetchMock);

    consoleErrors.length = 0;
    render(
      <React.StrictMode>
        <App />
      </React.StrictMode>,
    );

    // Shell should render
    await waitFor(
      () => {
        expect(screen.queryByRole("heading", { name: /Fleet overview/i })).toBeInTheDocument();
      },
      { timeout: 5000 },
    );

    // No hook-order errors should occur (StrictMode double-renders to catch violations)
    const hookOrderErrors = consoleErrors.filter(
      (e) =>
        e.includes("#310") ||
        e.includes("Rendered fewer hooks") ||
        e.includes("Rendered more hooks"),
    );
    expect(hookOrderErrors).toHaveLength(0);
  });
});
