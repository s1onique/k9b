/**
 * incidentOnePassDiagnosis.test.ts
 *
 * Targeted tests for API client in incidentOnePassDiagnosis.ts.
 * Tests the request building and API call behavior.
 */

import { afterEach, describe, expect, test, vi } from "vitest";
import {
  buildOnePassDiagnosisRequest,
  generateOnePassRunId,
  runIncidentOnePassDiagnosis,
} from "./incidentOnePassDiagnosis";

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

/**
 * Capture an error from a rejected promise.
 * Fails the test if the function does not throw.
 */
async function captureError(fn: () => Promise<unknown>): Promise<Error> {
  try {
    await fn();
  } catch (e) {
    expect(e).toBeInstanceOf(Error);
    return e as Error;
  }
  throw new Error("expected function to reject");
}

// ---------------------------------------------------------------------------
// Mock fetch
// ---------------------------------------------------------------------------

const mockFetch = vi.fn();

global.fetch = mockFetch;

afterEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SUCCESS_RESPONSE = {
  schema_version: "1.0",
  incident_id: "test-incident-123",
  run_id: "one-pass-20260619-120000",
  category: "readiness_probe_failure",
  root_cause: "Pod readiness probe failure",
  confidence: "high",
  description: "The pod is not ready",
  evidence_refs: ["evidence-1", "evidence-2"],
  read_only: true,
  allowed_actions: [],
  forbidden_actions_observed: [],
  mutation_proposals_observed: [],
  decision: "run_allowed_read_only_checks",
  checks_run: 2,
  next_checks: [
    { check_id: "check-1", title: "Check pod events", read_only: true, source: "system" },
  ],
  artifact_written: true,
  artifact_name: "test-incident-diagnosis.json",
  error: null,
};

const ERROR_RESPONSE = {
  error: "Incident not found",
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("generateOnePassRunId", () => {
  test("returns a string", () => {
    const id = generateOnePassRunId();
    expect(typeof id).toBe("string");
  });

  test("starts with one-pass-", () => {
    const id = generateOnePassRunId();
    expect(id.startsWith("one-pass-")).toBe(true);
  });

  test("contains a timestamp-like segment", () => {
    const id = generateOnePassRunId();
    // Format: one-pass-YYYY-MM-DDTHH-MM-SS
    expect(id).toMatch(/^one-pass-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}$/);
  });
});

describe("buildOnePassDiagnosisRequest", () => {
  test("returns empty object when no options provided", () => {
    const body = buildOnePassDiagnosisRequest();
    expect(body).toEqual({});
  });

  test("returns empty object when runId not provided", () => {
    const body = buildOnePassDiagnosisRequest({});
    expect(body).toEqual({});
  });

  test("includes run_id when runId is provided", () => {
    const body = buildOnePassDiagnosisRequest({ runId: "my-run-123" });
    expect(body).toEqual({ run_id: "my-run-123" });
  });

  test("does not include provider in request", () => {
    const body = buildOnePassDiagnosisRequest({ runId: "test" });
    expect(body).not.toHaveProperty("provider");
    expect(body).not.toHaveProperty("provider_name");
  });

  test("does not include policy fields in request", () => {
    const body = buildOnePassDiagnosisRequest({ runId: "test" });
    expect(body).not.toHaveProperty("llm_policy");
    expect(body).not.toHaveProperty("policy");
  });

  test("does not include mutation fields in request", () => {
    const body = buildOnePassDiagnosisRequest({ runId: "test" });
    expect(body).not.toHaveProperty("allowed_actions");
    expect(body).not.toHaveProperty("mutation_proposals");
    expect(body).not.toHaveProperty("remediate");
    expect(body).not.toHaveProperty("apply_manifest");
  });

  test("does not include path fields in request", () => {
    const body = buildOnePassDiagnosisRequest({ runId: "test" });
    expect(body).not.toHaveProperty("path");
    expect(body).not.toHaveProperty("fs_path");
    expect(body).not.toHaveProperty("artifact_root");
  });
});

describe("runIncidentOnePassDiagnosis", () => {
  test("POSTs to correct endpoint", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      statusText: "OK",
      json: () => Promise.resolve(SUCCESS_RESPONSE),
    });

    await runIncidentOnePassDiagnosis("test-incident-123");

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toBe("/api/incidents/test-incident-123/one-pass-diagnosis");
    expect(options.method).toBe("POST");
  });

  test("uses correct HTTP method", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      statusText: "OK",
      json: () => Promise.resolve(SUCCESS_RESPONSE),
    });

    await runIncidentOnePassDiagnosis("test-incident");

    const [, options] = mockFetch.mock.calls[0];
    expect(options.method).toBe("POST");
  });

  test("includes Content-Type header", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      statusText: "OK",
      json: () => Promise.resolve(SUCCESS_RESPONSE),
    });

    await runIncidentOnePassDiagnosis("test-incident");

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers["Content-Type"]).toBe("application/json");
  });

  test("URL-encodes incident_id with special characters", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      statusText: "OK",
      json: () => Promise.resolve(SUCCESS_RESPONSE),
    });

    await runIncidentOnePassDiagnosis("test/incident:123");

    const [url] = mockFetch.mock.calls[0];
    expect(url).toBe("/api/incidents/test%2Fincident%3A123/one-pass-diagnosis");
  });

  test("sends empty body when no options", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      statusText: "OK",
      json: () => Promise.resolve(SUCCESS_RESPONSE),
    });

    await runIncidentOnePassDiagnosis("test-incident");

    const [, options] = mockFetch.mock.calls[0];
    expect(options.body).toBe("{}");
  });

  test("sends run_id in body when provided", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      statusText: "OK",
      json: () => Promise.resolve(SUCCESS_RESPONSE),
    });

    await runIncidentOnePassDiagnosis("test-incident", { runId: "my-run-123" });

    const [, options] = mockFetch.mock.calls[0];
    expect(options.body).toBe('{"run_id":"my-run-123"}');
  });

  test("does not send provider field", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      statusText: "OK",
      json: () => Promise.resolve(SUCCESS_RESPONSE),
    });

    await runIncidentOnePassDiagnosis("test-incident");

    const [, options] = mockFetch.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body).not.toHaveProperty("provider");
    expect(body).not.toHaveProperty("provider_name");
  });

  test("does not send policy fields", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      statusText: "OK",
      json: () => Promise.resolve(SUCCESS_RESPONSE),
    });

    await runIncidentOnePassDiagnosis("test-incident");

    const [, options] = mockFetch.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body).not.toHaveProperty("llm_policy");
    expect(body).not.toHaveProperty("policy");
  });

  test("does not send mutation fields", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      statusText: "OK",
      json: () => Promise.resolve(SUCCESS_RESPONSE),
    });

    await runIncidentOnePassDiagnosis("test-incident");

    const [, options] = mockFetch.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body).not.toHaveProperty("allowed_actions");
    expect(body).not.toHaveProperty("mutation_proposals");
    expect(body).not.toHaveProperty("remediate");
    expect(body).not.toHaveProperty("apply_manifest");
  });

  test("returns parsed response on success", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      statusText: "OK",
      json: () => Promise.resolve(SUCCESS_RESPONSE),
    });

    const result = await runIncidentOnePassDiagnosis("test-incident");

    expect(result).toEqual(SUCCESS_RESPONSE);
  });

  test("throws Error on HTTP error", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: () => Promise.resolve(ERROR_RESPONSE),
    });

    await expect(runIncidentOnePassDiagnosis("nonexistent")).rejects.toThrow("Incident not found");
  });

  test("throws Error with bounded message on HTTP error", async () => {
    const longMessage = "x".repeat(600);
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.resolve({ error: longMessage }),
    });

    // Single call - capture the error and verify it was bounded
    const error = await captureError(() => runIncidentOnePassDiagnosis("test"));
    expect(error.message).not.toBe("expected function to reject");
    expect(error.message.length).toBeLessThanOrEqual(503);
  });

  test("throws Error on network failure", async () => {
    mockFetch.mockRejectedValueOnce(new Error("Network error"));

    await expect(runIncidentOnePassDiagnosis("test")).rejects.toThrow("Network error");
  });

  test("throws Error on malformed JSON response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      statusText: "OK",
      json: () => Promise.reject(new SyntaxError("Unexpected token in JSON")),
    });

    await expect(runIncidentOnePassDiagnosis("test")).rejects.toThrow("Unexpected");
  });

  test("bounds long network error from rejected fetch", async () => {
    const longError = "x".repeat(600);
    mockFetch.mockRejectedValueOnce(new Error(longError));

    // Single call - capture the error and verify it was bounded
    const error = await captureError(() => runIncidentOnePassDiagnosis("test"));
    expect(error.message).not.toBe("expected function to reject");
    expect(error.message.length).toBeLessThanOrEqual(503);
  });

  test("bounds long malformed JSON error", async () => {
    const longError = "Unexpected token at position " + "x".repeat(580);
    mockFetch.mockResolvedValueOnce({
      ok: true,
      statusText: "OK",
      json: () => Promise.reject(new SyntaxError(longError)),
    });

    // Single call - capture the error and verify it was bounded
    const error = await captureError(() => runIncidentOnePassDiagnosis("test"));
    expect(error.message).not.toBe("expected function to reject");
    expect(error.message.length).toBeLessThanOrEqual(503);
  });
});
