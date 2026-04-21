/**
 * Tests for useAppData hook - handleAlertmanagerRelevanceFeedback
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
        lastRefresh: {
          toISOString: () => "2026-04-06T12:00:00Z",
        } as any,
        refreshRuns: vi.fn(),
        refreshRunData: vi.fn(),
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

  test("calls submitAlertmanagerRelevanceFeedback without summary when not provided", async () => {
    const { result } = renderHook(() =>
      useAppData({
        selectedRunId: "run-123",
        lastRefresh: {
          toISOString: () => "2026-04-06T12:00:00Z",
        } as any,
        refreshRuns: vi.fn(),
        refreshRunData: vi.fn(),
      })
    );

    await waitFor(() => {
      expect(fetchFleet).toHaveBeenCalled();
    });

    await result.current.handleAlertmanagerRelevanceFeedback(
      "/artifacts/execution-1.json",
      "not_relevant",
      undefined
    );

    expect(submitAlertmanagerRelevanceFeedback).toHaveBeenCalledWith({
      artifactPath: "/artifacts/execution-1.json",
      alertmanagerRelevance: "not_relevant",
      alertmanagerRelevanceSummary: undefined,
    });
  });

  test("accepts all valid relevance values", async () => {
    const { result } = renderHook(() =>
      useAppData({
        selectedRunId: "run-123",
        lastRefresh: {
          toISOString: () => "2026-04-06T12:00:00Z",
        } as any,
        refreshRuns: vi.fn(),
        refreshRunData: vi.fn(),
      })
    );

    await waitFor(() => {
      expect(fetchFleet).toHaveBeenCalled();
    });

    // Test "noisy"
    await result.current.handleAlertmanagerRelevanceFeedback(
      "/artifacts/1.json",
      "noisy",
      "Too many false positives"
    );
    expect(submitAlertmanagerRelevanceFeedback).toHaveBeenLastCalledWith({
      artifactPath: "/artifacts/1.json",
      alertmanagerRelevance: "noisy",
      alertmanagerRelevanceSummary: "Too many false positives",
    });

    // Test "unsure"
    await result.current.handleAlertmanagerRelevanceFeedback(
      "/artifacts/2.json",
      "unsure",
      undefined
    );
    expect(submitAlertmanagerRelevanceFeedback).toHaveBeenLastCalledWith({
      artifactPath: "/artifacts/2.json",
      alertmanagerRelevance: "unsure",
      alertmanagerRelevanceSummary: undefined,
    });
  });

  test("refreshes app data after successful submission", async () => {
    const mockRefreshRuns = vi.fn();
    const mockRefreshRunData = vi.fn();

    vi.mocked(submitAlertmanagerRelevanceFeedback).mockResolvedValue(undefined);

    const { result } = renderHook(() =>
      useAppData({
        selectedRunId: "run-123",
        lastRefresh: {
          toISOString: () => "2026-04-06T12:00:00Z",
        } as any,
        refreshRuns: mockRefreshRuns,
        refreshRunData: mockRefreshRunData,
      })
    );

    await waitFor(() => {
      expect(fetchFleet).toHaveBeenCalled();
    });

    await result.current.handleAlertmanagerRelevanceFeedback(
      "/artifacts/execution-1.json",
      "relevant",
      undefined
    );

    // Wait for the async refresh to be called
    await waitFor(() => {
      expect(mockRefreshRuns).toHaveBeenCalled();
    });
  });

  test("re-throws error from API on submission failure", async () => {
    vi.mocked(submitAlertmanagerRelevanceFeedback).mockRejectedValue(
      new Error("API Error: Invalid request")
    );

    const { result } = renderHook(() =>
      useAppData({
        selectedRunId: "run-123",
        lastRefresh: {
          toISOString: () => "2026-04-06T12:00:00Z",
        } as any,
        refreshRuns: vi.fn(),
        refreshRunData: vi.fn(),
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
