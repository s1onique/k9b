/**
 * api.test.ts
 *
 * Targeted tests for frontend/src/api.ts.
 * Exercises real behavioral branches: success paths, error paths, parsing,
 * URL building, query param handling, and defensive fallback behavior.
 *
 * Baseline coverage: 51.9% stmts, 73.91% branches
 * Goal: meaningfully increase coverage for error handling, URL construction,
 * and contract edge cases.
 */

import { afterEach, describe, expect, test, vi } from "vitest";
import {
  approveNextCheckCandidate,
  executeNextCheckCandidate,
  fetchClusterDetail,
  fetchFleet,
  fetchNotifications,
  fetchProposals,
  fetchRun,
  fetchRunsList,
  performAlertmanagerSourceAction,
  promoteAlertmanagerSource,
  promoteDeterministicNextCheck,
  runBatchExecution,
  stopTrackingAlertmanagerSource,
  submitUsefulnessFeedback,
  type NotificationsQuery,
} from "../api";
import type {
  AlertmanagerSourceActionRequest,
  BatchExecutionRequest,
  DeterministicNextCheckPromotionRequest,
  NextCheckApprovalRequest,
  NextCheckExecutionRequest,
  UsefulnessFeedbackRequest,
} from "../types";

// ---------------------------------------------------------------------------
// Fetch mock helper - returns responses based on URL pattern matching
// ---------------------------------------------------------------------------

/**
 * Creates a mock fetch that matches URLs with query param normalization.
 * Supports exact matches and base-path matches (without query params).
 * Fail loudly if URL is not configured - no silent fallbacks.
 */
const createFetchMock = (responses: Record<string, Response>) =>
  vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === "string" || input instanceof URL ? input.toString() : input.url;
    // Try exact match first, then base path (without query params)
    const response = responses[url] ?? responses[url.split("?")[0]];
    if (!response) {
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    }
    return Promise.resolve(response);
  });

/**
 * Build a mock Response object with the given status and body.
 */
const mockResponse = (
  body: unknown,
  status: number,
  statusText?: string
): Response => {
  if (status >= 400 || body === null || body === undefined) {
    // For error responses with no valid JSON body, use text
    return new Response(
      typeof body === "string" ? body : body !== null && body !== undefined ? JSON.stringify(body) : "",
      {
        status,
        statusText: statusText ?? String(status),
        headers: { "Content-Type": "application/json" },
      }
    );
  }
  return new Response(JSON.stringify(body), {
    status,
    statusText: statusText ?? "OK",
    headers: { "Content-Type": "application/json" },
  });
};

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SUCCESS_PAYLOADS = {
  "/api/run": { runId: "run-123", label: "test-run" },
  "/api/run?run_id=run-456": { runId: "run-456", label: "other-run" },
  "/api/fleet": { runId: "run-123", clusters: [] },
  "/api/proposals": { proposals: [] },
  "/api/runs": { runs: [] },
  "/api/notifications": { notifications: [], total: 0, page: 1, limit: 50, total_pages: 0 },
  "/api/cluster-detail": { selectedClusterLabel: "cluster-a" },
  "/api/next-check-execution": { status: "success", artifactPath: "/artifacts/test.json" },
  "/api/next-check-approval": { status: "success", artifactPath: "/artifacts/approval.json" },
  "/api/deterministic-next-check/promote": { status: "success", candidateId: "promo-1" },
  "/api/next-check-execution-usefulness": { status: "success" },
  "/api/run-batch-next-check-execution": { status: "success", runId: "run-123" },
};

// ---------------------------------------------------------------------------
// Test setup/teardown
// ---------------------------------------------------------------------------

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// fetchJson helper (internal) - tested indirectly via exported functions
// ---------------------------------------------------------------------------

describe("fetchJson (via fetchRun)", () => {
  test("returns parsed JSON on success", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({ "/api/run": mockResponse(SUCCESS_PAYLOADS["/api/run"]) })
    );
    const result = await fetchRun();
    expect(result).toEqual({ runId: "run-123", label: "test-run" });
  });

  test("throws on non-OK response", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/run": new Response(null, { status: 404, statusText: "Not Found" }),
      })
    );
    await expect(fetchRun()).rejects.toThrow("Failed to fetch /api/run: Not Found");
  });

  test("throws on network error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("Network error")))
    );
    await expect(fetchRun()).rejects.toThrow("Network error");
  });
});

// ---------------------------------------------------------------------------
// fetchRun
// ---------------------------------------------------------------------------

describe("fetchRun", () => {
  test("calls /api/run without runId", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({ "/api/run": mockResponse(SUCCESS_PAYLOADS["/api/run"]) })
    );
    await fetchRun();
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/run",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  test("appends run_id query param when runId is provided", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/run?run_id=run-456": mockResponse(SUCCESS_PAYLOADS["/api/run?run_id=run-456"]),
      })
    );
    await fetchRun("run-456");
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/run?run_id=run-456",
      expect.any(Object)
    );
  });

  test("encodes special characters in runId", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/run?run_id=run%2F456": mockResponse({ runId: "run/456" }),
      })
    );
    await fetchRun("run/456");
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/run?run_id=run%2F456",
      expect.any(Object)
    );
  });
});

// ---------------------------------------------------------------------------
// fetchFleet
// ---------------------------------------------------------------------------

describe("fetchFleet", () => {
  test("calls /api/fleet and returns payload", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({ "/api/fleet": mockResponse(SUCCESS_PAYLOADS["/api/fleet"]) })
    );
    const result = await fetchFleet();
    expect(result).toEqual({ runId: "run-123", clusters: [] });
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/fleet",
      expect.objectContaining({ cache: "no-store" })
    );
  });
});

// ---------------------------------------------------------------------------
// fetchProposals
// ---------------------------------------------------------------------------

describe("fetchProposals", () => {
  test("calls /api/proposals and returns payload", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/proposals": mockResponse(SUCCESS_PAYLOADS["/api/proposals"]),
      })
    );
    const result = await fetchProposals();
    expect(result).toEqual({ proposals: [] });
  });
});

// ---------------------------------------------------------------------------
// fetchRunsList
// ---------------------------------------------------------------------------

describe("fetchRunsList", () => {
  test("calls /api/runs and returns payload", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({ "/api/runs": mockResponse(SUCCESS_PAYLOADS["/api/runs"]) })
    );
    const result = await fetchRunsList();
    expect(result).toEqual({ runs: [] });
  });
});

// ---------------------------------------------------------------------------
// fetchNotifications
// ---------------------------------------------------------------------------

describe("fetchNotifications", () => {
  test("calls /api/notifications with no params", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/notifications": mockResponse(SUCCESS_PAYLOADS["/api/notifications"]),
      })
    );
    await fetchNotifications();
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/notifications",
      expect.any(Object)
    );
  });

  test("builds single query param - kind", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/notifications?kind=Warning": mockResponse(SUCCESS_PAYLOADS["/api/notifications"]),
      })
    );
    await fetchNotifications({ kind: "Warning" });
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/notifications?kind=Warning",
      expect.any(Object)
    );
  });

  test("builds single query param - cluster_label", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/notifications?cluster_label=cluster-a": mockResponse(
          SUCCESS_PAYLOADS["/api/notifications"]
        ),
      })
    );
    await fetchNotifications({ cluster_label: "cluster-a" });
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/notifications?cluster_label=cluster-a",
      expect.any(Object)
    );
  });

  test("builds single query param - search", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/notifications?search=pod": mockResponse(SUCCESS_PAYLOADS["/api/notifications"]),
      })
    );
    await fetchNotifications({ search: "pod" });
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/notifications?search=pod",
      expect.any(Object)
    );
  });

  test("builds numeric params - limit and page", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/notifications?limit=20&page=2": mockResponse(SUCCESS_PAYLOADS["/api/notifications"]),
      })
    );
    await fetchNotifications({ limit: 20, page: 2 });
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/notifications?limit=20&page=2",
      expect.any(Object)
    );
  });

  test("builds all query params together", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/notifications?kind=Warning&cluster_label=cluster-a&search=error&limit=10&page=3":
          mockResponse(SUCCESS_PAYLOADS["/api/notifications"]),
      })
    );
    const query: NotificationsQuery = {
      kind: "Warning",
      cluster_label: "cluster-a",
      search: "error",
      limit: 10,
      page: 3,
    };
    await fetchNotifications(query);
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/notifications?kind=Warning&cluster_label=cluster-a&search=error&limit=10&page=3",
      expect.any(Object)
    );
  });

  test("omits limit and page params when 0 is passed (falsy check)", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/notifications?kind=Warning": mockResponse(SUCCESS_PAYLOADS["/api/notifications"]),
      })
    );
    // Pass limit: 0 to verify falsy check (should not append)
    await fetchNotifications({ kind: "Warning", limit: 0, page: 0 });
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/notifications?kind=Warning",
      expect.any(Object)
    );
  });

  test("handles missing optional fields in response", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/notifications": mockResponse({ notifications: [] }),
      })
    );
    const result = await fetchNotifications();
    // Should parse without throwing even if total/page/limit/total_pages missing
    expect(result.notifications).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// fetchClusterDetail
// ---------------------------------------------------------------------------

describe("fetchClusterDetail", () => {
  test("calls /api/cluster-detail without clusterLabel", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/cluster-detail": mockResponse(SUCCESS_PAYLOADS["/api/cluster-detail"]),
      })
    );
    await fetchClusterDetail();
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/cluster-detail",
      expect.any(Object)
    );
  });

  test("appends cluster_label query param when provided", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/cluster-detail?cluster_label=cluster-b": mockResponse({
          selectedClusterLabel: "cluster-b",
        }),
      })
    );
    await fetchClusterDetail("cluster-b");
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/cluster-detail?cluster_label=cluster-b",
      expect.any(Object)
    );
  });

  test("encodes special characters in clusterLabel", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/cluster-detail?cluster_label=cluster%2Fb": mockResponse({
          selectedClusterLabel: "cluster/b",
        }),
      })
    );
    await fetchClusterDetail("cluster/b");
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/cluster-detail?cluster_label=cluster%2Fb",
      expect.any(Object)
    );
  });
});

// ---------------------------------------------------------------------------
// executeNextCheckCandidate
// ---------------------------------------------------------------------------

describe("executeNextCheckCandidate", () => {
  const request: NextCheckExecutionRequest = {
    candidateId: "candidate-1",
    clusterLabel: "cluster-a",
    planArtifactPath: "/artifacts/plan.json",
  };

  test("sends POST request with JSON body on success", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/next-check-execution": mockResponse(SUCCESS_PAYLOADS["/api/next-check-execution"]),
      })
    );
    const result = await executeNextCheckCandidate(request);
    expect(result.status).toBe("success");
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/next-check-execution",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      })
    );
  });

  test("extracts error message from error field in JSON response", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/next-check-execution": mockResponse({ error: "Execution failed" }, 400),
      })
    );
    await expect(executeNextCheckCandidate(request)).rejects.toThrow("Execution failed");
  });

  test("extracts blockingReason from error response", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/next-check-execution": mockResponse(
          { error: "Execution failed", blockingReason: "unknown-command" },
          400
        ),
      })
    );
    try {
      await executeNextCheckCandidate(request);
    } catch (e) {
      expect((e as { blockingReason?: string }).blockingReason).toBe("unknown-command");
    }
  });

  test("sets blockingReason to null when field is null in response", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/next-check-execution": mockResponse(
          { error: "Execution failed", blockingReason: null },
          400
        ),
      })
    );
    try {
      await executeNextCheckCandidate(request);
    } catch (e) {
      expect((e as { blockingReason?: string | null }).blockingReason).toBeNull();
    }
  });

  test("falls back to statusText when JSON parse fails", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/next-check-execution": new Response("Bad Gateway", {
          status: 502,
          statusText: "Bad Gateway",
        }),
      })
    );
    await expect(executeNextCheckCandidate(request)).rejects.toThrow("Bad Gateway");
  });

  test("uses statusText when response has no body and no JSON", async () => {
    // Real behavior: when body is null, response.json() throws,
    // and message stays as statusText instead of falling back to default
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/next-check-execution": new Response(null, {
          status: 500,
          statusText: "Internal Server Error",
        }),
      })
    );
    await expect(executeNextCheckCandidate(request)).rejects.toThrow(
      "Internal Server Error"
    );
  });

  test("ignores non-object JSON responses during error parsing", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/next-check-execution": new Response(JSON.stringify("string error"), {
          status: 400,
          statusText: "Bad Request",
          headers: { "Content-Type": "application/json" },
        }),
      })
    );
    // Should fall back to statusText since parsed JSON is not an object
    await expect(executeNextCheckCandidate(request)).rejects.toThrow("Bad Request");
  });

  test("handles malformed JSON in error response gracefully", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/next-check-execution": new Response("not valid json {", {
          status: 400,
          statusText: "Bad Request",
          headers: { "Content-Type": "application/json" },
        }),
      })
    );
    // Should fall back to statusText
    await expect(executeNextCheckCandidate(request)).rejects.toThrow("Bad Request");
  });

  test("uses statusText when error response body is empty", async () => {
    // Real behavior: when body is null, message stays as statusText
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/next-check-execution": new Response(null, {
          status: 503,
          statusText: "Service Unavailable",
        }),
      })
    );
    await expect(executeNextCheckCandidate(request)).rejects.toThrow("Service Unavailable");
  });
});

// ---------------------------------------------------------------------------
// approveNextCheckCandidate
// ---------------------------------------------------------------------------

describe("approveNextCheckCandidate", () => {
  const request: NextCheckApprovalRequest = {
    candidateId: "candidate-1",
    clusterLabel: "cluster-a",
  };

  test("sends POST request on success", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/next-check-approval": mockResponse(SUCCESS_PAYLOADS["/api/next-check-approval"]),
      })
    );
    const result = await approveNextCheckCandidate(request);
    expect(result.status).toBe("success");
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/next-check-approval",
      expect.objectContaining({ method: "POST" })
    );
  });

  test("extracts error from error field in JSON", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/next-check-approval": mockResponse({ error: "Approval rejected" }, 400),
      })
    );
    await expect(approveNextCheckCandidate(request)).rejects.toThrow("Approval rejected");
  });

  test("uses statusText when body has no error field", async () => {
    // Real behavior: when body exists but has no error field, response.json() succeeds
    // but message stays as statusText since error extraction fails.
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/next-check-approval": mockResponse(
          { message: "Some other field" },
          400,
          "Bad Request"
        ),
      })
    );
    await expect(approveNextCheckCandidate(request)).rejects.toThrow("Bad Request");
  });

  test("ignores JSON parse errors during error extraction", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/next-check-approval": new Response("invalid json", {
          status: 400,
          statusText: "Bad Request",
        }),
      })
    );
    await expect(approveNextCheckCandidate(request)).rejects.toThrow("Bad Request");
  });
});

// ---------------------------------------------------------------------------
// promoteDeterministicNextCheck
// ---------------------------------------------------------------------------

describe("promoteDeterministicNextCheck", () => {
  const request: DeterministicNextCheckPromotionRequest = {
    clusterLabel: "cluster-a",
    description: "Collect kubelet metrics",
  };

  test("sends POST request on success", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/deterministic-next-check/promote": mockResponse(
          SUCCESS_PAYLOADS["/api/deterministic-next-check/promote"]
        ),
      })
    );
    const result = await promoteDeterministicNextCheck(request);
    expect(result.status).toBe("success");
  });

  test("extracts error from response", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/deterministic-next-check/promote": mockResponse(
          { error: "Promotion failed" },
          400
        ),
      })
    );
    await expect(promoteDeterministicNextCheck(request)).rejects.toThrow(
      "Promotion failed"
    );
  });

  test("uses statusText when body is null", async () => {
    // Real behavior: when body is null, response.json() throws,
    // and message stays as statusText instead of default
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/deterministic-next-check/promote": new Response(null, {
          status: 500,
          statusText: "Internal Server Error",
        }),
      })
    );
    await expect(promoteDeterministicNextCheck(request)).rejects.toThrow("Internal Server Error");
  });
});

// ---------------------------------------------------------------------------
// submitUsefulnessFeedback
// ---------------------------------------------------------------------------

describe("submitUsefulnessFeedback", () => {
  const request: UsefulnessFeedbackRequest = {
    artifactPath: "/artifacts/exec-1.json",
    usefulnessClass: "useful",
    usefulnessSummary: "Good signal",
  };

  test("sends POST request on success", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/next-check-execution-usefulness": mockResponse(
          SUCCESS_PAYLOADS["/api/next-check-execution-usefulness"]
        ),
      })
    );
    const result = await submitUsefulnessFeedback(request);
    expect(result.status).toBe("success");
  });

  test("extracts error from response", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/next-check-execution-usefulness": mockResponse(
          { error: "Feedback rejected" },
          400
        ),
      })
    );
    await expect(submitUsefulnessFeedback(request)).rejects.toThrow("Feedback rejected");
  });

  test("uses statusText when body is null and no error field", async () => {
    // Real behavior: when body is null, response.json() throws,
    // and message stays as statusText instead of default
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/next-check-execution-usefulness": new Response(null, {
          status: 503,
          statusText: "Service Unavailable",
        }),
      })
    );
    await expect(submitUsefulnessFeedback(request)).rejects.toThrow("Service Unavailable");
  });
});

// ---------------------------------------------------------------------------
// runBatchExecution
// ---------------------------------------------------------------------------

describe("runBatchExecution", () => {
  const request: BatchExecutionRequest = {
    runId: "run-123",
    dryRun: false,
  };

  test("sends POST request on success", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/run-batch-next-check-execution": mockResponse(
          SUCCESS_PAYLOADS["/api/run-batch-next-check-execution"]
        ),
      })
    );
    const result = await runBatchExecution(request);
    expect(result.status).toBe("success");
  });

  test("throws text body on non-OK response", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/run-batch-next-check-execution": new Response("Batch execution failed", {
          status: 500,
          statusText: "Internal Server Error",
        }),
      })
    );
    await expect(runBatchExecution(request)).rejects.toThrow("Batch execution failed");
  });

  test("uses default message when text body is empty", async () => {
    // runBatchExecution uses response.text() not response.json(),
    // so empty body triggers the default message fallback
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/run-batch-next-check-execution": new Response(null, {
          status: 500,
          statusText: "Internal Server Error",
        }),
      })
    );
    await expect(runBatchExecution(request)).rejects.toThrow(
      "Failed to run batch execution"
    );
  });
});

// ---------------------------------------------------------------------------
// performAlertmanagerSourceAction
// ---------------------------------------------------------------------------

describe("performAlertmanagerSourceAction", () => {
  const baseRequest: AlertmanagerSourceActionRequest = {
    sourceId: "src-123",
    clusterLabel: "cluster-a",
    action: "promote",
  };

  test("builds correct run-scoped URL for promote action", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs/run-456/alertmanager-sources/src-123/action": mockResponse({
          status: "success",
          sourceId: "src-123",
          action: "promote",
        }),
      })
    );
    const result = await performAlertmanagerSourceAction(baseRequest, "run-456");
    expect(result.sourceId).toBe("src-123");
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/runs/run-456/alertmanager-sources/src-123/action",
      expect.objectContaining({ method: "POST" })
    );
  });

  test("builds correct run-scoped URL for disable action", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs/run-789/alertmanager-sources/src-456/action": mockResponse({
          status: "success",
          sourceId: "src-456",
          action: "disable",
        }),
      })
    );
    const disableRequest: AlertmanagerSourceActionRequest = {
      sourceId: "src-456",
      clusterLabel: "cluster-b",
      action: "disable",
    };
    await performAlertmanagerSourceAction(disableRequest, "run-789");
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/runs/run-789/alertmanager-sources/src-456/action",
      expect.any(Object)
    );
  });

  test("omits reason field from body when not provided", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs/run-456/alertmanager-sources/src-123/action": mockResponse({
          status: "success",
        }),
      })
    );
    await performAlertmanagerSourceAction(baseRequest, "run-456");
    const call = vi.mocked(globalThis.fetch).mock.calls[0];
    const body = JSON.parse(call[1].body as string);
    // reason should not be present in the body (omitted by spread operator)
    expect(Object.keys(body)).not.toContain("reason");
  });

  test("includes reason field in body when provided", async () => {
    const requestWithReason: AlertmanagerSourceActionRequest = {
      ...baseRequest,
      reason: "Testing promotion",
    };
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs/run-456/alertmanager-sources/src-123/action": mockResponse({
          status: "success",
        }),
      })
    );
    await performAlertmanagerSourceAction(requestWithReason, "run-456");
    const call = vi.mocked(globalThis.fetch).mock.calls[0];
    const body = JSON.parse(call[1].body as string);
    expect(body.reason).toBe("Testing promotion");
  });

  test("includes clusterLabel in body", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs/run-456/alertmanager-sources/src-123/action": mockResponse({
          status: "success",
        }),
      })
    );
    await performAlertmanagerSourceAction(baseRequest, "run-456");
    const call = vi.mocked(globalThis.fetch).mock.calls[0];
    const body = JSON.parse(call[1].body as string);
    expect(body.clusterLabel).toBe("cluster-a");
  });

  test("extracts error from response", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs/run-456/alertmanager-sources/src-123/action": mockResponse(
          { error: "Action not allowed" },
          403
        ),
      })
    );
    await expect(
      performAlertmanagerSourceAction(baseRequest, "run-456")
    ).rejects.toThrow("Action not allowed");
  });

  test("uses statusText when body is null and no error field", async () => {
    // Real behavior: when body is null, response.json() throws,
    // and message stays as statusText instead of default
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs/run-456/alertmanager-sources/src-123/action": new Response(null, {
          status: 500,
          statusText: "Internal Server Error",
        }),
      })
    );
    await expect(
      performAlertmanagerSourceAction(baseRequest, "run-456")
    ).rejects.toThrow("Internal Server Error");
  });

  test("encodes sourceId with special characters", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs/run-456/alertmanager-sources/src%2F123/action": mockResponse({
          status: "success",
        }),
      })
    );
    const requestWithSpecialId: AlertmanagerSourceActionRequest = {
      ...baseRequest,
      sourceId: "src/123",
    };
    await performAlertmanagerSourceAction(requestWithSpecialId, "run-456");
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/runs/run-456/alertmanager-sources/src%2F123/action",
      expect.any(Object)
    );
  });
});

// ---------------------------------------------------------------------------
// promoteAlertmanagerSource (convenience wrapper)
// ---------------------------------------------------------------------------

describe("promoteAlertmanagerSource", () => {
  test("delegates to performAlertmanagerSourceAction with action=promote", async () => {
    const request: AlertmanagerSourceActionRequest = {
      sourceId: "src-123",
      clusterLabel: "cluster-a",
    };
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs/run-999/alertmanager-sources/src-123/action": mockResponse({
          status: "success",
          action: "promote",
        }),
      })
    );
    await promoteAlertmanagerSource(request, "run-999");
    const call = vi.mocked(globalThis.fetch).mock.calls[0];
    const body = JSON.parse(call[1].body as string);
    expect(body.action).toBe("promote");
  });
});

// ---------------------------------------------------------------------------
// stopTrackingAlertmanagerSource (convenience wrapper)
// ---------------------------------------------------------------------------

describe("stopTrackingAlertmanagerSource", () => {
  test("delegates to performAlertmanagerSourceAction with action=disable", async () => {
    const request: AlertmanagerSourceActionRequest = {
      sourceId: "src-789",
      clusterLabel: "cluster-b",
    };
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs/run-111/alertmanager-sources/src-789/action": mockResponse({
          status: "success",
          action: "disable",
        }),
      })
    );
    await stopTrackingAlertmanagerSource(request, "run-111");
    const call = vi.mocked(globalThis.fetch).mock.calls[0];
    const body = JSON.parse(call[1].body as string);
    expect(body.action).toBe("disable");
  });
});

// ---------------------------------------------------------------------------
// Edge cases and contract preservation
// ---------------------------------------------------------------------------

describe("API client resilience", () => {
  test("fetchRun handles empty response body", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/run": new Response("null", {
          status: 200,
          statusText: "OK",
          headers: { "Content-Type": "application/json" },
        }),
      })
    );
    // response.json() will parse "null" as null, which is valid
    const result = await fetchRun();
    expect(result).toBeNull();
  });

  test("fetchNotifications handles notifications with all optional fields null", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/notifications": mockResponse({
          notifications: [
            {
              kind: null,
              summary: "Test",
              timestamp: null,
              runId: null,
              clusterLabel: null,
              context: null,
              details: [],
              artifactPath: null,
            },
          ],
          total: null,
          page: null,
          limit: null,
          total_pages: null,
        }),
      })
    );
    const result = await fetchNotifications();
    expect(result.notifications[0].kind).toBeNull();
    expect(result.total).toBeNull();
  });

  test("all core POST functions include no-store cache directive", async () => {
    // Tests the primary mutation helpers that use fetchJson pattern.
    // Note: runBatchExecution and performAlertmanagerSourceAction are tested separately
    // for their specific behavior (text body vs JSON parsing differences).
    const postFunctions = [
      { fn: executeNextCheckCandidate, args: [{ candidateId: "c1", clusterLabel: "c-a" }] },
      { fn: approveNextCheckCandidate, args: [{ candidateId: "c1", clusterLabel: "c-a" }] },
      {
        fn: promoteDeterministicNextCheck,
        args: [{ clusterLabel: "c-a", description: "test" }],
      },
      {
        fn: submitUsefulnessFeedback,
        args: [{ artifactPath: "/a.json", usefulnessClass: "useful" }],
      },
    ];

    for (const { fn, args } of postFunctions) {
      vi.stubGlobal(
        "fetch",
        createFetchMock({
          "/api/next-check-execution": mockResponse({ status: "success" }),
          "/api/next-check-approval": mockResponse({ status: "success" }),
          "/api/deterministic-next-check/promote": mockResponse({ status: "success" }),
          "/api/next-check-execution-usefulness": mockResponse({ status: "success" }),
        })
      );
      await fn(...args);
      expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ cache: "no-store" })
      );
      vi.mocked(globalThis.fetch).mockClear();
    }
  });
});
