/**
 * generatedClient.test.ts
 *
 * Tests for the generatedClient.ts module.
 * Verifies HTML fallback guard behavior and error normalization.
 */

import { afterEach, describe, expect, test, vi } from "vitest";
import { createK9bApiConfiguration, normalizeGeneratedApiError } from "../api/generatedClient";
import { IncidentsApi } from "../generated/k9b-api";
import { ResponseError } from "../generated/k9b-api/runtime";

// ---------------------------------------------------------------------------
// Test setup/teardown
// ---------------------------------------------------------------------------

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// HTML Fallback Guard - tests that verify the guard catches SPA HTML responses
// ---------------------------------------------------------------------------

describe("HTML Fallback Guard", () => {
  test("generated GET wrappers preserve SPA HTML fallback guard - fetchFleet", async () => {
    // Don't mock IncidentsApi - use the real generated client with mocked global fetch
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response("<!doctype html><div id='root'></div>", {
          status: 200,
          headers: { "Content-Type": "text/html" },
        })
      )
    );

    const { fetchFleet } = await import("../api/runs");

    // The generated client's JSON parsing fails on HTML, then normalizeGeneratedApiError
    // detects HTML content in the response body and produces the descriptive message
    await expect(fetchFleet()).rejects.toThrow("Expected JSON");
    await expect(fetchFleet()).rejects.toThrow("SPA index.html");
  });

  test("generated GET wrappers preserve SPA HTML fallback guard - fetchProposals", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response("<html><body>SPA Fallback</body></html>", {
          status: 200,
          headers: { "Content-Type": "text/html; charset=utf-8" },
        })
      )
    );

    const { fetchProposals } = await import("../api/runs");

    // The generated client's JSON parsing fails on HTML, then normalizeGeneratedApiError
    // detects HTML content in the response body and produces the descriptive message
    await expect(fetchProposals()).rejects.toThrow("Expected JSON");
    await expect(fetchProposals()).rejects.toThrow("SPA index.html");
  });

  test("HTML guard allows normal JSON responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ runId: "run-123", clusters: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      )
    );

    const { fetchFleet } = await import("../api/runs");
    const result = await fetchFleet();
    expect(result).toEqual({ runId: "run-123", clusters: [] });
  });

  test("HTML guard does not block non-200 responses with text/html", async () => {
    // For non-OK responses, the generated client throws ResponseError
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response("<html><body>Error page</body></html>", {
          status: 404,
          statusText: "Not Found",
          headers: { "Content-Type": "text/html" },
        })
      )
    );

    const { fetchFleet } = await import("../api/runs");
    await expect(fetchFleet()).rejects.toThrow();
  });
});

// ---------------------------------------------------------------------------
// createK9bApiConfiguration
// ---------------------------------------------------------------------------

describe("createK9bApiConfiguration", () => {
  test("creates configuration with correct basePath and credentials", () => {
    const config = createK9bApiConfiguration();
    
    expect(config.basePath).toBe("");
    expect(config.credentials).toBe("include");
  });
});

// ---------------------------------------------------------------------------
// normalizeGeneratedApiError
// ---------------------------------------------------------------------------

describe("normalizeGeneratedApiError", () => {
  test("extracts error message from ResponseError with JSON body", async () => {
    const mockResponse = new Response(JSON.stringify({ error: "Test error message" }), {
      status: 400,
      statusText: "Bad Request",
      headers: { "Content-Type": "application/json" },
    });
    const responseError = new ResponseError(mockResponse);

    const result = await normalizeGeneratedApiError(responseError);
    
    expect(result.message).toBe("Test error message");
  });

  test("returns status text when ResponseError has no JSON body", async () => {
    const mockResponse = new Response("Not Found", {
      status: 404,
      statusText: "Not Found",
      headers: { "Content-Type": "text/plain" },
    });
    const responseError = new ResponseError(mockResponse);

    const result = await normalizeGeneratedApiError(responseError);
    
    expect(result.message).toBe("Not Found");
  });

  test("returns generic message when ResponseError has empty body", async () => {
    const mockResponse = new Response(null, {
      status: 500,
      statusText: "Internal Server Error",
    });
    const responseError = new ResponseError(mockResponse);

    const result = await normalizeGeneratedApiError(responseError);
    
    expect(result.message).toContain("500");
  });

  test("passes through non-ResponseError errors", async () => {
    const originalError = new Error("Original error");

    const result = await normalizeGeneratedApiError(originalError);
    
    expect(result).toBe(originalError);
  });

  test("converts non-Error values to Error", async () => {
    const result = await normalizeGeneratedApiError("string error");
    
    expect(result).toBeInstanceOf(Error);
    expect(result.message).toBe("string error");
  });
});
