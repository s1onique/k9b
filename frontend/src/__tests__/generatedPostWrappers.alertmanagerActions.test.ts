/**
 * generatedPostWrappers.alertmanagerActions.test.ts
 *
 * Tests for performAlertmanagerSourceAction wrapper.
 *
 * Uses direct fetch() instead of the generated IncidentsApi client,
 * so tests assert at the fetch boundary rather than the IncidentsApi mock.
 *
 * IMPORTANT: Regression guard - sourceId must be in POST body, NOT URL path.
 * This protects the slash-containing sourceId regression (e.g., "crd:monitoring.coreos.com/v1/Alertmanager/main").
 */

import { describe, expect, test, vi, beforeEach, afterEach } from "vitest";
import { performAlertmanagerSourceAction } from "../api/alertmanager";

// ---------------------------------------------------------------------------
// Global fetch stub for direct fetch() calls
// Vitest/Node cannot resolve relative URLs like "/api/..." without a document base.
// Stubbing fetch prevents "TypeError: Invalid URL" when constructing requests.
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
  vi.clearAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// performAlertmanagerSourceAction
// ---------------------------------------------------------------------------

describe("performAlertmanagerSourceAction wrapper mapping", () => {
  test("POSTs to correct endpoint with sourceId in body (not URL path)", async () => {
    // This test uses direct fetch() (not the generated IncidentsApi mock),
    // so we assert at the fetch boundary instead.
    const result = await performAlertmanagerSourceAction(
      {
        sourceId: "crd:monitoring.coreos.com/v1/Alertmanager/main",
        clusterLabel: "cluster-a",
        action: "promote",
        reason: "Confirmed alert",
      },
      "run-456"
    );

    expect(result.ok).toBe(true);

    // Regression guard: sourceId must be in POST body, not URL path
    expect(fetch).toHaveBeenCalledWith(
      "/api/runs/run-456/alertmanager-sources/action",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({
          sourceId: "crd:monitoring.coreos.com/v1/Alertmanager/main",
          action: "promote",
          clusterLabel: "cluster-a",
          reason: "Confirmed alert",
        }),
      }),
    );

    // Verify sourceId is NOT in URL path (was the old buggy behavior)
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).not.toContain("crd:monitoring.coreos.com");
    expect(url).not.toContain("sourceId");
  });

  test("handles simple alphanumeric sourceId", async () => {
    const result = await performAlertmanagerSourceAction(
      {
        sourceId: "src-123",
        clusterLabel: "cluster-a",
        action: "disable",
      },
      "run-789"
    );

    expect(result.ok).toBe(true);
    expect(fetch).toHaveBeenCalledWith(
      "/api/runs/run-789/alertmanager-sources/action",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"sourceId":"src-123"'),
      }),
    );
  });
});
