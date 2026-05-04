/**
 * Sentinel progressive-loading test.
 * 
 * PROVES the new render contract:
 * - App shell renders with fleet + proposals immediately
 * - /api/run remains pending (not mocked)
 * - Run-dependent panels show loading placeholders
 * - No runtime crash
 * 
 * This test validates the progressive loading architecture is correct
 * BEFORE updating other tests that may need to mock run data.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { describe, test, vi } from "vitest";
import App from "../App";
import type { FleetPayload, ProposalsPayload, RunsListPayload } from "../types";
import { createStorageMock, createFetchMock } from "./fixtures";

describe("Progressive Loading Contract", () => {
  // Minimal valid payloads for shell rendering
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

  beforeEach(() => {
    const storage = createStorageMock();
    vi.stubGlobal("localStorage", storage);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("1. app shell renders with fleet+proposals while run is pending", async () => {
    // Mock only /api/fleet and /api/proposals
    // Do NOT mock /api/run - this simulates the pending state
    const fetchMock = createFetchMock({
      "/api/fleet": minimalFleet,
      "/api/proposals": minimalProposals,
      "/api/runs": minimalRunsList,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    // Shell must render immediately (no "Loading operator data…" spinner)
    await waitFor(() => {
      expect(screen.queryByText(/Loading operator data/i)).not.toBeInTheDocument();
    });

    // Fleet overview must be visible
    expect(screen.getByRole("heading", { name: /Fleet overview/i })).toBeInTheDocument();

    // Recent runs panel must be visible - there may be multiple matches (nav link + heading)
    expect(screen.getAllByText(/Recent runs/i).length).toBeGreaterThan(0);

    // Proposals section must be visible
    expect(screen.getByRole("heading", { name: /Action proposals/i })).toBeInTheDocument();

    // Run-dependent panels must show loading placeholders
    await waitFor(() => {
      expect(screen.getAllByText(/Loading selected run/i).length).toBeGreaterThan(0);
    });

    // Verify key run-dependent panel headings are present (may appear multiple times)
    expect(screen.getAllByText(/Execution review/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Work list/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Provider advisory/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/LLM policy/i).length).toBeGreaterThan(0);
  });

  test("2. no runtime crash when run data fails to load", async () => {
    // Mock fleet/proposals to succeed with complete Response objects
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];
      
      if (base === "/api/fleet") {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          headers: {
            get: (name: string) => {
              if (name === "Content-Type") return "application/json";
              return null;
            },
          },
          text: () => Promise.resolve(JSON.stringify(minimalFleet)),
          json: () => Promise.resolve(minimalFleet),
        });
      }
      if (base === "/api/proposals") {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          headers: {
            get: (name: string) => {
              if (name === "Content-Type") return "application/json";
              return null;
            },
          },
          text: () => Promise.resolve(JSON.stringify(minimalProposals)),
          json: () => Promise.resolve(minimalProposals),
        });
      }
      if (base === "/api/runs") {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          headers: {
            get: (name: string) => {
              if (name === "Content-Type") return "application/json";
              return null;
            },
          },
          text: () => Promise.resolve(JSON.stringify(minimalRunsList)),
          json: () => Promise.resolve(minimalRunsList),
        });
      }
      // /api/run not mocked - simulates failure or pending
      
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    // Should not throw
    expect(() => render(<App />)).not.toThrow();

    // Shell should still render
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: /Fleet overview/i })).toBeInTheDocument();
    });
  });
});
