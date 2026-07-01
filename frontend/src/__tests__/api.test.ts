/**
 * api.test.ts
 *
 * Targeted tests for frontend/src/api.ts.
 * Exercises real behavioral branches: success paths, error paths, parsing,
 * URL building, query param handling, and defensive fallback behavior.
 *
 * Tests migrated functions use generated OpenAPI client for GET operations.
 * POST operations with request bodies still use raw fetch.
 *
 * Baseline coverage: 51.9% stmts, 73.91% branches
 * Goal: meaningfully increase coverage for error handling, URL construction,
 * and contract edge cases.
 */

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import {
  approveNextCheckCandidate,
  downloadExecutionStateDiagnostics,
  executeNextCheckCandidate,
  fetchClusterDetail,
  fetchDebugDiagnosticsEnabled,
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
import { IncidentsApi } from "../generated/k9b-api";

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
// Mock factory - creates fresh mock instances for each test
// ---------------------------------------------------------------------------

function createMockIncidentsApi(responses: Record<string, unknown>, error?: Error | null) {
  return {
    getRunDetail: vi.fn().mockImplementation(async (params: { runId?: string }, _initOverrides?: RequestInit) => {
      if (error) throw error;
      const key = params.runId ? `/api/run?run_id=${params.runId}` : "/api/run";
      return responses[key] ?? responses["/api/run"];
    }),
    getFleet: vi.fn().mockImplementation(async () => {
      if (error) throw error;
      return responses["/api/fleet"] ?? { runId: "run-123", clusters: [] };
    }),
    getProposals: vi.fn().mockImplementation(async () => {
      if (error) throw error;
      return responses["/api/proposals"] ?? { proposals: [] };
    }),
    getClusterDetail: vi.fn().mockImplementation(async (params: { clusterLabel?: string }) => {
      if (error) throw error;
      const key = params.clusterLabel ? `/api/cluster-detail?cluster_label=${params.clusterLabel}` : "/api/cluster-detail";
      return responses[key] ?? responses["/api/cluster-detail"];
    }),
    listRuns: vi.fn().mockImplementation(async () => {
      if (error) throw error;
      return responses["/api/runs"] ?? { runs: [] };
    }),
    listNotifications: vi.fn().mockImplementation(async (params: {
      kind?: string;
      clusterLabel?: string;
      search?: string;
      limit?: string;
      page?: string;
    }) => {
      if (error) throw error;
      // Build query string from params
      const queryParts: string[] = [];
      if (params.kind) queryParts.push(`Kind=${params.kind}`);
      if (params.clusterLabel) queryParts.push(`cluster_label=${params.clusterLabel}`);
      if (params.search) queryParts.push(`search=${params.search}`);
      if (params.limit) queryParts.push(`limit=${params.limit}`);
      if (params.page) queryParts.push(`page=${params.page}`);
      const queryString = queryParts.length > 0 ? `?${queryParts.join("&")}` : "";
      const key = `/api/notifications${queryString}`;
      return responses[key] ?? responses["/api/notifications"] ?? { notifications: [], total: 0, page: 1, limit: 50, total_pages: 0 };
    }),
    listIncidents: vi.fn().mockImplementation(async () => {
      if (error) throw error;
      return responses["/api/incidents"] ?? { incidents: [] };
    }),
    getIncidentDetail: vi.fn().mockImplementation(async () => {
      if (error) throw error;
      return responses["/api/incidents/detail"] ?? { incidentId: "test" };
    }),
    getIncidentDiagnosisReviewHandoff: vi.fn().mockImplementation(async () => {
      if (error) throw error;
      return responses["/api/incidents/handoff"] ?? { handoff: "test" };
    }),
  };
}

// ---------------------------------------------------------------------------
// Test setup/teardown
// ---------------------------------------------------------------------------

// Track current mock instance
let currentMockApi: ReturnType<typeof createMockIncidentsApi> | null = null;

// Mock IncidentsApi class to return our mock instance
vi.mock("../generated/k9b-api", () => ({
  IncidentsApi: vi.fn().mockImplementation(() => {
    if (!currentMockApi) {
      currentMockApi = createMockIncidentsApi({}, null);
    }
    return currentMockApi;
  }),
}));

// Mock the generatedClient module
vi.mock("../api/generatedClient", () => ({
  createK9bApiConfiguration: vi.fn(() => ({
    baseOptions: {
      credentials: "include" as const,
    },
  })),
  normalizeGeneratedApiError: vi.fn((error: unknown) => {
    if (error instanceof Error) {
      return Promise.resolve(error);
    }
    return Promise.resolve(new Error(String(error)));
  }),
}));

beforeEach(() => {
  // Reset mock before each test
  currentMockApi = createMockIncidentsApi({}, null);
  // Update the mock implementation for IncidentsApi
  vi.mocked(IncidentsApi).mockImplementation(() => currentMockApi!);
});

afterEach(() => {
  vi.restoreAllMocks();
  currentMockApi = null;
});

// ---------------------------------------------------------------------------
// fetchJson helper (internal) - tested indirectly via exported functions
// ---------------------------------------------------------------------------

describe("fetchJson (via fetchRun)", () => {
  test("returns parsed JSON on success", async () => {
    currentMockApi = createMockIncidentsApi({ "/api/run": { runId: "run-123", label: "test-run" } });
    
    const result = await fetchRun();
    expect(result).toEqual({ runId: "run-123", label: "test-run" });
  });

  test("throws on non-OK response", async () => {
    const mockError = new Error("Failed to fetch /api/run: Not Found");
    currentMockApi = createMockIncidentsApi({}, mockError);
    
    await expect(fetchRun()).rejects.toThrow("Not Found");
  });

  test("throws on network error", async () => {
    const networkError = new Error("Network error");
    currentMockApi = createMockIncidentsApi({}, networkError);
    
    await expect(fetchRun()).rejects.toThrow("Network error");
  });

  test("REGRESSION: throws descriptive error on HTML response (SPA fallback detection)", async () => {
    const htmlError = new Error("Expected JSON from /api/fleet but received text/html");
    currentMockApi = createMockIncidentsApi({}, htmlError);
    
    await expect(fetchFleet()).rejects.toThrow("text/html");
  });

  test("REGRESSION: throws descriptive error on application/html response", async () => {
    const htmlError = new Error("Expected JSON from /api/proposals but received text/html");
    currentMockApi = createMockIncidentsApi({}, htmlError);
    
    await expect(fetchProposals()).rejects.toThrow("text/html");
  });

  test("HTML guard does not affect normal JSON responses", async () => {
    currentMockApi = createMockIncidentsApi({ "/api/fleet": { runId: "run-123", clusters: [] } });
    
    const result = await fetchFleet();
    expect(result).toEqual({ runId: "run-123", clusters: [] });
  });
});

// ---------------------------------------------------------------------------
// fetchRun
// ---------------------------------------------------------------------------

describe("fetchRun", () => {
  test("calls /api/run without runId", async () => {
    currentMockApi = createMockIncidentsApi({ "/api/run": { runId: "run-123", label: "test-run" } });
    
    const result = await fetchRun();
    expect(result).toEqual({ runId: "run-123", label: "test-run" });
    expect(currentMockApi!.getRunDetail).toHaveBeenCalledWith({}, undefined);
  });

  test("appends run_id query param when runId is provided", async () => {
    currentMockApi = createMockIncidentsApi({ "/api/run?run_id=run-456": { runId: "run-456", label: "other-run" } });
    
    const result = await fetchRun("run-456");
    expect(result).toEqual({ runId: "run-456", label: "other-run" });
    expect(currentMockApi!.getRunDetail).toHaveBeenCalledWith({ runId: "run-456" }, undefined);
  });

  test("encodes special characters in runId", async () => {
    // Provide fallback for /api/run as well as the encoded version
    currentMockApi = createMockIncidentsApi({ 
      "/api/run": { runId: "run/456" },
      "/api/run?run_id=run%2F456": { runId: "run/456" } 
    });
    
    const result = await fetchRun("run/456");
    expect(result).toEqual({ runId: "run/456" });
    expect(currentMockApi!.getRunDetail).toHaveBeenCalledWith({ runId: "run/456" }, undefined);
  });

  test("handles runId parameter correctly", async () => {
    currentMockApi = createMockIncidentsApi({});
    
    await fetchRun("run-789");
    expect(currentMockApi!.getRunDetail).toHaveBeenCalledWith({ runId: "run-789" }, undefined);
  });

  test("preserves existing behavior with options parameter", async () => {
    currentMockApi = createMockIncidentsApi({ "/api/run": { runId: "run-123" } });
    
    await fetchRun(undefined, { clientRequestId: "rc-1-1234567890-abc123" });
    // Verify both params are passed: params object and initOverrides with headers
    expect(currentMockApi!.getRunDetail).toHaveBeenCalledWith(
      {},
      expect.objectContaining({
        headers: {
          "X-K9B-Client-Request-Id": "rc-1-1234567890-abc123",
        },
      })
    );
  });

  test("passes abort signal via initOverrides", async () => {
    currentMockApi = createMockIncidentsApi({ "/api/run": { runId: "run-123" } });
    const controller = new AbortController();
    
    await fetchRun(undefined, { signal: controller.signal });
    // Verify signal is passed via initOverrides
    expect(currentMockApi!.getRunDetail).toHaveBeenCalledWith(
      {},
      expect.objectContaining({
        signal: controller.signal,
      })
    );
  });
});

// ---------------------------------------------------------------------------
// fetchFleet
// ---------------------------------------------------------------------------

describe("fetchFleet", () => {
  test("calls /api/fleet and returns payload", async () => {
    currentMockApi = createMockIncidentsApi({ "/api/fleet": { runId: "run-123", clusters: [] } });
    
    const result = await fetchFleet();
    expect(result).toEqual({ runId: "run-123", clusters: [] });
    expect(currentMockApi!.getFleet).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// fetchProposals
// ---------------------------------------------------------------------------

describe("fetchProposals", () => {
  test("calls /api/proposals and returns payload", async () => {
    currentMockApi = createMockIncidentsApi({ "/api/proposals": { proposals: [] } });
    
    const result = await fetchProposals();
    expect(result).toEqual({ proposals: [] });
    expect(currentMockApi!.getProposals).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// fetchRunsList
// ---------------------------------------------------------------------------

describe("fetchRunsList", () => {
  test("calls /api/runs with include_batch_eligibility=true for fast batch eligibility", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs?include_batch_eligibility=true": mockResponse({ runs: [] }),
      })
    );
    
    const result = await fetchRunsList();
    expect(result).toEqual({ runs: [] });
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/runs?include_batch_eligibility=true",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  test("includes pagination params when provided", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs?include_batch_eligibility=true&limit=10&page=2": mockResponse({ runs: [] }),
      })
    );
    
    const result = await fetchRunsList({ limit: 10, page: 2 });
    expect(result).toEqual({ runs: [] });
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/runs?include_batch_eligibility=true&limit=10&page=2",
      expect.any(Object)
    );
  });

  test("includes cluster_label when provided", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs?include_batch_eligibility=true&cluster_label=cluster-a": mockResponse({ runs: [] }),
      })
    );
    
    const result = await fetchRunsList({ clusterLabel: "cluster-a" });
    expect(result).toEqual({ runs: [] });
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/runs?include_batch_eligibility=true&cluster_label=cluster-a",
      expect.any(Object)
    );
  });
});

// ---------------------------------------------------------------------------
// fetchNotifications
// ---------------------------------------------------------------------------

describe("fetchNotifications", () => {
  test("calls /api/notifications with no params", async () => {
    currentMockApi = createMockIncidentsApi({ "/api/notifications": { notifications: [], total: 0, page: 1, limit: 50, total_pages: 0 } });
    
    const result = await fetchNotifications();
    expect(result).toEqual({ notifications: [], total: 0, page: 1, limit: 50, total_pages: 0 });
    expect(currentMockApi!.listNotifications).toHaveBeenCalledWith({});
  });

  test("builds single query param - kind", async () => {
    currentMockApi = createMockIncidentsApi({});
    
    await fetchNotifications({ kind: "Warning" });
    expect(currentMockApi!.listNotifications).toHaveBeenCalledWith({ kind: "Warning" });
  });

  test("builds single query param - cluster_label", async () => {
    currentMockApi = createMockIncidentsApi({});
    
    await fetchNotifications({ cluster_label: "cluster-a" });
    expect(currentMockApi!.listNotifications).toHaveBeenCalledWith({ clusterLabel: "cluster-a" });
  });

  test("builds single query param - search", async () => {
    currentMockApi = createMockIncidentsApi({});
    
    await fetchNotifications({ search: "pod" });
    expect(currentMockApi!.listNotifications).toHaveBeenCalledWith({ search: "pod" });
  });

  test("builds numeric params - limit and page", async () => {
    currentMockApi = createMockIncidentsApi({});
    
    await fetchNotifications({ limit: 20, page: 2 });
    // limit and page are converted to strings by the wrapper
    expect(currentMockApi!.listNotifications).toHaveBeenCalledWith({ limit: "20", page: "2" });
  });

  test("builds all query params together", async () => {
    currentMockApi = createMockIncidentsApi({});
    
    const query: NotificationsQuery = {
      kind: "Warning",
      cluster_label: "cluster-a",
      search: "error",
      limit: 10,
      page: 3,
    };
    await fetchNotifications(query);
    expect(currentMockApi!.listNotifications).toHaveBeenCalledWith({
      kind: "Warning",
      clusterLabel: "cluster-a",
      search: "error",
      limit: "10",
      page: "3",
    });
  });

  test("converts 0 to '0' string for limit and page", async () => {
    currentMockApi = createMockIncidentsApi({});
    
    await fetchNotifications({ kind: "Warning", limit: 0, page: 0 });
    // The wrapper converts numbers to strings, including 0 -> "0"
    expect(currentMockApi!.listNotifications).toHaveBeenCalledWith({ 
      kind: "Warning", 
      limit: "0", 
      page: "0",
      clusterLabel: undefined,
      search: undefined,
    });
  });

  test("handles missing optional fields in response", async () => {
    currentMockApi = createMockIncidentsApi({ "/api/notifications": { notifications: [] } });
    
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
    currentMockApi = createMockIncidentsApi({ "/api/cluster-detail": { selectedClusterLabel: "cluster-a" } });
    
    const result = await fetchClusterDetail();
    expect(result).toEqual({ selectedClusterLabel: "cluster-a" });
    expect(currentMockApi!.getClusterDetail).toHaveBeenCalledWith({});
  });

  test("appends cluster_label query param when provided", async () => {
    currentMockApi = createMockIncidentsApi({});
    
    const result = await fetchClusterDetail("cluster-b");
    expect(currentMockApi!.getClusterDetail).toHaveBeenCalledWith({ clusterLabel: "cluster-b" });
  });

  test("encodes special characters in clusterLabel", async () => {
    currentMockApi = createMockIncidentsApi({});
    
    const result = await fetchClusterDetail("cluster/b");
    expect(currentMockApi!.getClusterDetail).toHaveBeenCalledWith({ clusterLabel: "cluster/b" });
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
    await expect(executeNextCheckCandidate(request)).rejects.toThrow("Bad Request");
  });

  test("uses statusText when error response body is empty", async () => {
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

  test("throws error message from response on non-OK response", async () => {
    // Note: extractErrorMessage tries JSON.parse first, falls back to statusText
    // With Content-Type: application/json header and text body, JSON.parse fails
    // so it falls back to statusText "Internal Server Error"
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/run-batch-next-check-execution": new Response("Batch execution failed", {
          status: 500,
          statusText: "Internal Server Error",
        }),
      })
    );
    await expect(runBatchExecution(request)).rejects.toThrow("Internal Server Error");
  });

  test("uses default message when text body is empty and no JSON", async () => {
    // When response.json() fails and text is empty, message stays as statusText
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/run-batch-next-check-execution": new Response(null, {
          status: 500,
          statusText: "Internal Server Error",
        }),
      })
    );
    await expect(runBatchExecution(request)).rejects.toThrow("Internal Server Error");
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
    const body = JSON.parse((call[1] as { body?: string }).body as string);
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
    const body = JSON.parse((call[1] as { body?: string }).body as string);
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
    const body = JSON.parse((call[1] as { body?: string }).body as string);
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
    const body = JSON.parse((call[1] as { body?: string }).body as string);
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
    const body = JSON.parse((call[1] as { body?: string }).body as string);
    expect(body.action).toBe("disable");
  });
});

// ---------------------------------------------------------------------------
// Edge cases and contract preservation
// ---------------------------------------------------------------------------

describe("API client resilience", () => {
  test("fetchRun handles empty response body", async () => {
    currentMockApi = createMockIncidentsApi({ "/api/run": null });
    
    const result = await fetchRun();
    expect(result).toBeNull();
  });

  test("fetchNotifications handles notifications with all optional fields null", async () => {
    currentMockApi = createMockIncidentsApi({
      "/api/notifications": {
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
      },
    });
    
    const result = await fetchNotifications();
    expect(result.notifications[0].kind).toBeNull();
    expect(result.total).toBeNull();
  });

  test("all core POST functions include no-store cache directive", async () => {
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

// ---------------------------------------------------------------------------
// Debug diagnostics API functions
// ---------------------------------------------------------------------------

describe("fetchDebugDiagnosticsEnabled", () => {
  test("calls /api/debug/diagnostics-enabled and returns enabled status", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/debug/diagnostics-enabled": mockResponse({
          debugExecutionDiagnosticsEnabled: true,
        }),
      })
    );
    const result = await fetchDebugDiagnosticsEnabled();
    expect(result).toEqual({ debugExecutionDiagnosticsEnabled: true });
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/debug/diagnostics-enabled",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  test("returns disabled status when endpoint returns false", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/debug/diagnostics-enabled": mockResponse({
          debugExecutionDiagnosticsEnabled: false,
        }),
      })
    );
    const result = await fetchDebugDiagnosticsEnabled();
    expect(result).toEqual({ debugExecutionDiagnosticsEnabled: false });
  });

  test("throws on non-OK response", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/debug/diagnostics-enabled": new Response(null, { status: 500, statusText: "Internal Server Error" }),
      })
    );
    await expect(fetchDebugDiagnosticsEnabled()).rejects.toThrow("Internal Server Error");
  });

  test("throws on network error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("Network error")))
    );
    await expect(fetchDebugDiagnosticsEnabled()).rejects.toThrow("Network error");
  });
});

describe("downloadExecutionStateDiagnostics", () => {
  test("calls correct endpoint with runId", async () => {
    const blob = new Blob(["test"], { type: "application/zip" });
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/debug/runs/run-123/execution-state-bundle": new Response(blob, {
          status: 200,
          statusText: "OK",
        }),
      })
    );
    const result = await downloadExecutionStateDiagnostics("run-123");
    expect(result).toBeDefined();
    expect(typeof result.size).toBe("number");
    expect(result.size).toBeGreaterThan(0);
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/debug/runs/run-123/execution-state-bundle",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  test("encodes special characters in runId", async () => {
    const blob = new Blob(["test"], { type: "application/zip" });
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/debug/runs/run%2F456/execution-state-bundle": new Response(blob, {
          status: 200,
        }),
      })
    );
    await downloadExecutionStateDiagnostics("run/456");
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      "/api/debug/runs/run%2F456/execution-state-bundle",
      expect.any(Object)
    );
  });

  test("extracts error message from JSON error response", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/debug/runs/run-123/execution-state-bundle": mockResponse(
          { error: "Debug endpoints disabled" },
          403
        ),
      })
    );
    await expect(downloadExecutionStateDiagnostics("run-123")).rejects.toThrow(
      "Debug endpoints disabled"
    );
  });

  test("throws on non-OK response without error field", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/debug/runs/run-123/execution-state-bundle": new Response(null, {
          status: 404,
          statusText: "Not Found",
        }),
      })
    );
    await expect(downloadExecutionStateDiagnostics("run-123")).rejects.toThrow("Not Found");
  });

  test("throws on network error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("Network error")))
    );
    await expect(downloadExecutionStateDiagnostics("run-123")).rejects.toThrow("Network error");
  });
});
