/**
 * Tests for useAppData hook - handleAlertmanagerRelevanceFeedback
 *
 * RunControl owns runs refresh. useAppData owns fleet/proposals refresh.
 * handleAlertmanagerRelevanceFeedback calls refreshAppData() after successful submission.
 */

import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { useAppData } from "../hooks/useAppData";
import * as apiModule from "../api";

// Mock the API module
vi.mock("../api", () => ({
  submitAlertmanagerRelevanceFeedback: vi.fn(),
  fetchFleet: vi.fn().mockResolvedValue({
    clusters: [],
    fleetStatus: { ratingCounts: [] },
    topProblem: { title: "", detail: "" },
    proposalSummary: { pending: 0, total: 0 },
  }),
  fetchProposals: vi.fn().mockResolvedValue({
    proposals: [],
    statusSummary: [],
  }),
  fetchNotifications: vi.fn().mockResolvedValue({
    notifications: [],
    totalCount: 0,
  }),
  promoteDeterministicNextCheck: vi.fn(),
  submitUsefulnessFeedback: vi.fn(),
}));

// Import after mocking
import {
  submitAlertmanagerRelevanceFeedback,
  fetchFleet,
  fetchProposals,
  fetchNotifications,
} from "../api";

describe("useAppData - handleAlertmanagerRelevanceFeedback", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("calls submitAlertmanagerRelevanceFeedback with correct payload", async () => {
    const { result } = renderHook(() =>
      useAppData({
        selectedRunId: "run-123",
        lastRefreshMs: Date.now(),
      })
    );

    // Wait for initial fetch to complete
    await waitFor(() => {
      expect(fetchFleet).toHaveBeenCalled();
    });

    // Call the handler
    await result.current.handleAlertmanagerRelevanceFeedback(
      "/artifacts/execution-1.json",
      "relevant",
      "This was helpful for debugging"
    );

    // Verify API was called with correct arguments
    expect(submitAlertmanagerRelevanceFeedback).toHaveBeenCalledWith({
      artifactPath: "/artifacts/execution-1.json",
      alertmanagerRelevance: "relevant",
      alertmanagerRelevanceSummary: "This was helpful for debugging",
    });
  });

  test("accepts all valid relevance values", async () => {
    const { result } = renderHook(() =>
      useAppData({
        selectedRunId: "run-123",
        lastRefreshMs: Date.now(),
      })
    );

    await waitFor(() => {
      expect(fetchFleet).toHaveBeenCalled();
    });

    // Test all valid relevance values
    const validValues: Array<"relevant" | "not_relevant" | "noisy" | "unsure"> = [
      "relevant",
      "not_relevant",
      "noisy",
      "unsure",
    ];

    for (const relevance of validValues) {
      vi.clearAllMocks();

      await result.current.handleAlertmanagerRelevanceFeedback(
        "/artifacts/execution-1.json",
        relevance,
        undefined
      );

      expect(submitAlertmanagerRelevanceFeedback).toHaveBeenCalledWith({
        artifactPath: "/artifacts/execution-1.json",
        alertmanagerRelevance: relevance,
        alertmanagerRelevanceSummary: undefined,
      });
    }
  });

  test("refreshes app data after successful submission", async () => {
    vi.mocked(submitAlertmanagerRelevanceFeedback).mockResolvedValue(undefined);

    const { result } = renderHook(() =>
      useAppData({
        selectedRunId: "run-123",
        lastRefreshMs: Date.now(),
      })
    );

    await waitFor(() => {
      expect(fetchFleet).toHaveBeenCalled();
    });

    // Count initial calls
    const initialFleetCalls = fetchFleet.mock.calls.length;
    const initialProposalsCalls = fetchProposals.mock.calls.length;

    // Call the handler
    await result.current.handleAlertmanagerRelevanceFeedback(
      "/artifacts/execution-1.json",
      "relevant",
      undefined
    );

    // Wait for refresh to complete
    await waitFor(
      () => {
        // refreshAppData() should be called which triggers fleet/proposals fetches
        expect(fetchFleet.mock.calls.length).toBeGreaterThan(initialFleetCalls);
        expect(fetchProposals.mock.calls.length).toBeGreaterThan(initialProposalsCalls);
      },
      { timeout: 2000 }
    );
  });

  test("re-throws error from API on submission failure", async () => {
    vi.mocked(submitAlertmanagerRelevanceFeedback).mockRejectedValue(
      new Error("API Error: Invalid request")
    );

    const { result } = renderHook(() =>
      useAppData({
        selectedRunId: "run-123",
        lastRefreshMs: Date.now(),
      })
    );

    await waitFor(() => {
      expect(fetchFleet).toHaveBeenCalled();
    });

    await expect(
      result.current.handleAlertmanagerRelevanceFeedback(
        "/artifacts/execution-1.json",
        "relevant",
        undefined
      )
    ).rejects.toThrow("API Error: Invalid request");
  });
});
