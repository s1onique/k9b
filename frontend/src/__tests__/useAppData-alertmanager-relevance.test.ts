/**
 * Tests for useAppData hook - handleAlertmanagerRelevanceFeedback
 *
 * RunControl owns runs refresh. useAppData owns fleet/proposals refresh.
 * handleAlertmanagerRelevanceFeedback calls refreshAppData() after successful submission.
 */

const mockSubmitAlertmanagerRelevanceFeedback = vi.fn();
const mockFetchFleet = vi.fn();
const mockFetchProposals = vi.fn();
const mockFetchNotifications = vi.fn();
const mockPromoteDeterministicNextCheck = vi.fn();
const mockSubmitUsefulnessFeedback = vi.fn();
const mockFetchDebugDiagnosticsEnabled = vi.fn();
const mockDownloadExecutionStateDiagnostics = vi.fn();

vi.mock("../api", () => ({
  submitAlertmanagerRelevanceFeedback: (...args: unknown[]) => mockSubmitAlertmanagerRelevanceFeedback(...args),
  fetchFleet: (...args: unknown[]) => mockFetchFleet(...args),
  fetchProposals: (...args: unknown[]) => mockFetchProposals(...args),
  fetchNotifications: (...args: unknown[]) => mockFetchNotifications(...args),
  promoteDeterministicNextCheck: (...args: unknown[]) => mockPromoteDeterministicNextCheck(...args),
  submitUsefulnessFeedback: (...args: unknown[]) => mockSubmitUsefulnessFeedback(...args),
  fetchDebugDiagnosticsEnabled: (...args: unknown[]) => mockFetchDebugDiagnosticsEnabled(...args),
  downloadExecutionStateDiagnostics: (...args: unknown[]) => mockDownloadExecutionStateDiagnostics(...args),
}));

import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { useAppData } from "../hooks/useAppData";
import * as apiModule from "../api";

// NOTE: The imported API functions are now wrapper functions around the top-level mock variables.
// Use the top-level mock variables directly for mockResolvedValue/mockRejectedValue/assertions.
// The wrapper pattern is needed so vi.clearAllMocks() can restore default implementations.
import {
  submitAlertmanagerRelevanceFeedback,
  fetchFleet,
  fetchProposals,
  fetchNotifications,
} from "../api";

describe("useAppData - handleAlertmanagerRelevanceFeedback", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchFleet.mockResolvedValue({
      clusters: [],
      fleetStatus: { ratingCounts: [] },
      topProblem: { title: "", detail: "" },
      proposalSummary: { pending: 0, total: 0 },
    });
    mockFetchProposals.mockResolvedValue({
      proposals: [],
      statusSummary: [],
    });
    mockFetchNotifications.mockResolvedValue({
      notifications: [],
      totalCount: 0,
    });
    mockFetchDebugDiagnosticsEnabled.mockResolvedValue({
      debugExecutionDiagnosticsEnabled: false,
    });
    mockDownloadExecutionStateDiagnostics.mockResolvedValue(new Blob(["test"]));
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
      expect(mockFetchFleet).toHaveBeenCalled();
    });

    // Call the handler
    await result.current.handleAlertmanagerRelevanceFeedback(
      "/artifacts/execution-1.json",
      "relevant",
      "This was helpful for debugging"
    );

    // Verify API was called with correct arguments
    expect(mockSubmitAlertmanagerRelevanceFeedback).toHaveBeenCalledWith({
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
      expect(mockFetchFleet).toHaveBeenCalled();
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

      expect(mockSubmitAlertmanagerRelevanceFeedback).toHaveBeenCalledWith({
        artifactPath: "/artifacts/execution-1.json",
        alertmanagerRelevance: relevance,
        alertmanagerRelevanceSummary: undefined,
      });
    }
  });

  test("refreshes app data after successful submission", async () => {
    mockSubmitAlertmanagerRelevanceFeedback.mockResolvedValue(undefined);

    const { result } = renderHook(() =>
      useAppData({
        selectedRunId: "run-123",
        lastRefreshMs: Date.now(),
      })
    );

    await waitFor(() => {
      expect(mockFetchFleet).toHaveBeenCalled();
    });

    // Count initial calls
    const initialFleetCalls = mockFetchFleet.mock.calls.length;
    const initialProposalsCalls = mockFetchProposals.mock.calls.length;

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
        expect(mockFetchFleet.mock.calls.length).toBeGreaterThan(initialFleetCalls);
        expect(mockFetchProposals.mock.calls.length).toBeGreaterThan(initialProposalsCalls);
      },
      { timeout: 2000 }
    );
  });

  test("re-throws error from API on submission failure", async () => {
    mockSubmitAlertmanagerRelevanceFeedback.mockRejectedValue(
      new Error("API Error: Invalid request")
    );

    const { result } = renderHook(() =>
      useAppData({
        selectedRunId: "run-123",
        lastRefreshMs: Date.now(),
      })
    );

    await waitFor(() => {
      expect(mockFetchFleet).toHaveBeenCalled();
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
