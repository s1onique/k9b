/**
 * api.test.ts
 *
 * Targeted tests for frontend/src/api.ts.
 * Tests cover: success paths, error paths, parsing, URL building, query param handling.
 *
 * Note: Some tests that require complex IncidentsApi mocking are deferred.
 */

import { describe, expect, test, vi } from "vitest";
import {
  fetchClusterDetail,
  fetchDebugDiagnosticsEnabled,
  fetchFleet,
  fetchNotifications,
  fetchProposals,
  fetchRun,
  fetchRunsList,
  fetchJson,
  downloadExecutionStateDiagnostics,
  performAlertmanagerSourceAction,
  promoteAlertmanagerSource,
  stopTrackingAlertmanagerSource,
} from "../api";

// ---------------------------------------------------------------------------
// Fetch mock helper
// ---------------------------------------------------------------------------

const createFetchMock = (responses: Record<string, Response>) =>
  vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === "string" || input instanceof URL ? input.toString() : input.url;
    const response = responses[url] ?? responses[url.split("?")[0]];
    if (!response) {
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    }
    return Promise.resolve(response);
  });

const mockResponse = (body: unknown, status: number, statusText?: string): Response => {
  return new Response(
    typeof body === "string" ? body : body !== null && body !== undefined ? JSON.stringify(body) : "",
    {
      status,
      statusText: statusText ?? String(status),
      headers: { "Content-Type": "application/json" },
    }
  );
};

// ---------------------------------------------------------------------------
// fetchJson
// ---------------------------------------------------------------------------

describe("fetchJson", () => {
  test("returns parsed JSON on success", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/run": mockResponse({ runId: "run-123", label: "test-run" }, 200),
      })
    );
    const result = await fetchJson("/api/run");
    expect(result).toEqual({ runId: "run-123", label: "test-run" });
  });

  test("throws on non-OK response", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/run": mockResponse({ error: "Not Found" }, 404),
      })
    );
    await expect(fetchJson("/api/run")).rejects.toThrow("Failed to fetch /api/run: 404");
  });

  test("throws descriptive error on HTML response (SPA fallback detection)", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/fleet": new Response("<html>Not Found</html>", {
          status: 404,
          statusText: "Not Found",
          headers: { "Content-Type": "text/html" },
        }),
      })
    );
    await expect(fetchJson("/api/fleet")).rejects.toThrow("Failed to fetch /api/fleet: Not Found");
  });

  test("HTML guard does not affect normal JSON responses", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/fleet": mockResponse({ runId: "run-123", clusters: [] }, 200),
      })
    );
    const result = await fetchJson("/api/fleet");
    expect(result).toEqual({ runId: "run-123", clusters: [] });
  });
});

// ---------------------------------------------------------------------------
// fetchRun
// ---------------------------------------------------------------------------

describe("fetchRun", () => {
  test("calls /api/run without runId", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/run": mockResponse({ runId: "run-123", label: "test-run" }, 200),
      })
    );
    const result = await fetchRun();
    expect(result).toEqual({ runId: "run-123", label: "test-run" });
  });

  test("appends run_id query param when runId is provided", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/run?run_id=run-456": mockResponse({ runId: "run-456", label: "other-run" }, 200),
      })
    );
    const result = await fetchRun("run-456");
    expect(result).toEqual({ runId: "run-456", label: "other-run" });
  });

  test("encodes special characters in runId", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/run?run_id=run%2F456": mockResponse({ runId: "run/456" }, 200),
      })
    );
    const result = await fetchRun("run/456");
    expect(result).toEqual({ runId: "run/456" });
  });

  test("handles runId parameter correctly", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/run?run_id=run-789": mockResponse({ runId: "run-789" }, 200),
      })
    );
    const result = await fetchRun("run-789");
    expect(result).toEqual({ runId: "run-789" });
  });
});

// ---------------------------------------------------------------------------
// fetchFleet
// ---------------------------------------------------------------------------

describe("fetchFleet", () => {
  test("calls /api/fleet and returns payload", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/fleet": mockResponse({ runId: "run-123", clusters: [] }, 200),
      })
    );
    const result = await fetchFleet();
    expect(result).toEqual({ runId: "run-123", clusters: [] });
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
        "/api/proposals": mockResponse({ proposals: [] }, 200),
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
  test("calls /api/runs with include_batch_eligibility=true", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs?include_batch_eligibility=true": mockResponse({ runs: [] }, 200),
      })
    );
    const result = await fetchRunsList();
    expect(result).toEqual({ runs: [] });
  });

  test("includes pagination params when provided", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs?include_batch_eligibility=true&limit=10&page=2": mockResponse({ runs: [] }, 200),
      })
    );
    const result = await fetchRunsList({ limit: 10, page: 2 });
    expect(result).toEqual({ runs: [] });
  });

  test("includes cluster_label when provided", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs?include_batch_eligibility=true&cluster_label=cluster-a": mockResponse({ runs: [] }, 200),
      })
    );
    const result = await fetchRunsList({ clusterLabel: "cluster-a" });
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
        "/api/notifications": mockResponse(
          { notifications: [], total: 0 },
          200
        ),
      })
    );
    const result = await fetchNotifications();
    expect(result.notifications).toEqual([]);
    expect(result.total).toBe(0);
  });

  test("handles missing optional fields in response", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/notifications": mockResponse({ notifications: [] }, 200),
      })
    );
    const result = await fetchNotifications();
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
        "/api/cluster-detail": mockResponse({ selectedClusterLabel: "cluster-a" }, 200),
      })
    );
    const result = await fetchClusterDetail();
    expect(result).toEqual({ selectedClusterLabel: "cluster-a" });
  });

  test("appends cluster_label query param when provided", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/cluster-detail?cluster_label=cluster-b": mockResponse({ selectedClusterLabel: "cluster-b" }, 200),
      })
    );
    const result = await fetchClusterDetail("cluster-b");
    expect(result).toEqual({ selectedClusterLabel: "cluster-b" });
  });

  test("encodes special characters in clusterLabel", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/cluster-detail?cluster_label=cluster%2Fb": mockResponse({ selectedClusterLabel: "cluster/b" }, 200),
      })
    );
    const result = await fetchClusterDetail("cluster/b");
    expect(result).toEqual({ selectedClusterLabel: "cluster/b" });
  });
});

// ---------------------------------------------------------------------------
// fetchDebugDiagnosticsEnabled
// ---------------------------------------------------------------------------

describe("fetchDebugDiagnosticsEnabled", () => {
  test("calls /api/debug/diagnostics-enabled and returns enabled status", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/debug/diagnostics-enabled": mockResponse(
          { debugExecutionDiagnosticsEnabled: true },
          200
        ),
      })
    );
    const result = await fetchDebugDiagnosticsEnabled();
    expect(result).toEqual({ debugExecutionDiagnosticsEnabled: true });
  });

  test("returns disabled status when endpoint returns false", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/debug/diagnostics-enabled": mockResponse(
          { debugExecutionDiagnosticsEnabled: false },
          200
        ),
      })
    );
    const result = await fetchDebugDiagnosticsEnabled();
    expect(result).toEqual({ debugExecutionDiagnosticsEnabled: false });
  });

  test("throws on non-OK response", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/debug/diagnostics-enabled": mockResponse(null, 500, "Internal Server Error"),
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

// ---------------------------------------------------------------------------
// downloadExecutionStateDiagnostics
// ---------------------------------------------------------------------------

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
        "/api/debug/runs/run-123/execution-state-bundle": mockResponse(null, 404, "Not Found"),
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

// ---------------------------------------------------------------------------
// performAlertmanagerSourceAction
// ---------------------------------------------------------------------------

describe("performAlertmanagerSourceAction", () => {
  test("builds correct run-scoped URL for promote action", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs/run-456/alertmanager-sources/src-123/action": mockResponse({
          status: "success",
          sourceId: "src-123",
          action: "promote",
        }, 200),
      })
    );
    const result = await performAlertmanagerSourceAction(
      { sourceId: "src-123", clusterLabel: "cluster-a", action: "promote" },
      "run-456"
    );
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
        }, 200),
      })
    );
    await performAlertmanagerSourceAction(
      { sourceId: "src-456", clusterLabel: "cluster-b", action: "disable" },
      "run-789"
    );
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
        }, 200),
      })
    );
    await performAlertmanagerSourceAction(
      { sourceId: "src-123", clusterLabel: "cluster-a", action: "promote" },
      "run-456"
    );
    const call = vi.mocked(globalThis.fetch).mock.calls[0];
    const body = JSON.parse((call[1] as { body?: string }).body as string);
    expect(Object.keys(body)).not.toContain("reason");
  });

  test("includes reason field in body when provided", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs/run-456/alertmanager-sources/src-123/action": mockResponse({
          status: "success",
        }, 200),
      })
    );
    await performAlertmanagerSourceAction(
      { sourceId: "src-123", clusterLabel: "cluster-a", action: "promote", reason: "Testing promotion" },
      "run-456"
    );
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
        }, 200),
      })
    );
    await performAlertmanagerSourceAction(
      { sourceId: "src-123", clusterLabel: "cluster-a", action: "promote" },
      "run-456"
    );
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
      performAlertmanagerSourceAction(
        { sourceId: "src-123", clusterLabel: "cluster-a", action: "promote" },
        "run-456"
      )
    ).rejects.toThrow("Action not allowed");
  });

  test("uses statusText when body is null and no error field", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs/run-456/alertmanager-sources/src-123/action": mockResponse(null, 500, "Internal Server Error"),
      })
    );
    await expect(
      performAlertmanagerSourceAction(
        { sourceId: "src-123", clusterLabel: "cluster-a", action: "promote" },
        "run-456"
      )
    ).rejects.toThrow("Request failed with status 500");
  });

  test("encodes sourceId with special characters", async () => {
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs/run-456/alertmanager-sources/src%2F123/action": mockResponse({
          status: "success",
        }, 200),
      })
    );
    await performAlertmanagerSourceAction(
      { sourceId: "src/123", clusterLabel: "cluster-a", action: "promote" },
      "run-456"
    );
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
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs/run-999/alertmanager-sources/src-123/action": mockResponse({
          status: "success",
          action: "promote",
        }, 200),
      })
    );
    await promoteAlertmanagerSource(
      { sourceId: "src-123", clusterLabel: "cluster-a" },
      "run-999"
    );
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
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        "/api/runs/run-111/alertmanager-sources/src-789/action": mockResponse({
          status: "success",
          action: "disable",
        }, 200),
      })
    );
    await stopTrackingAlertmanagerSource(
      { sourceId: "src-789", clusterLabel: "cluster-b" },
      "run-111"
    );
    const call = vi.mocked(globalThis.fetch).mock.calls[0];
    const body = JSON.parse((call[1] as { body?: string }).body as string);
    expect(body.action).toBe("disable");
  });
});
