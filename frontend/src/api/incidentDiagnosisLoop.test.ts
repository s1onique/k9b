/**
 * incidentDiagnosisLoop.test.ts
 *
 * Targeted tests for frontend/src/api/incidentDiagnosisLoop.ts.
 *
 * Verifies:
 * 1. POSTs to /api/incidents/{incident_id}/diagnosis-loop/one-pass
 * 2. Uses method POST
 * 3. Sends Content-Type: application/json
 * 4. Sends run_id
 * 5. Sends bounded diagnosis_report
 * 6. Does not send external_analysis_dir
 * 7. Does not send action-control fields
 * 8. Handles success response
 * 9. Handles backend error response
 * 10. Handles network/fetch failure safely
 * 11. generateManualRunId produces safe format
 * 12. createMinimalDiagnosisReport produces safe shape
 */

import { describe, expect, test, vi } from "vitest";
import {
  runIncidentDiagnosisLoopOnePass,
  generateManualRunId,
  createMinimalDiagnosisReport,
  type DiagnosisLoopOnePassRequest,
} from "./incidentDiagnosisLoop";

// ---------------------------------------------------------------------------
// Fetch mock helper
// ---------------------------------------------------------------------------

/**
 * Creates a mock fetch that returns configured responses by URL.
 */
const createFetchMock = (responses: Record<string, Response>) =>
  vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === "string" || input instanceof URL ? input.toString() : input.url;
    const response = responses[url];
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

const SUCCESS_RESPONSE = {
  schema_version: "1.0",
  incident_id: "test-incident-123",
  run_id: "manual-loop-20260619-120000",
  read_only: true,
  allowed_actions: [],
  decision: "continue",
  checks_requested: 0,
  checks_run: 0,
  checks_skipped: 0,
  checks_rejected: 0,
  artifacts: {
    read_only_check_results: { written: false, name: null },
    diagnosis_loop_pass: { written: true, name: "manual-loop-20260619-120000-diagnosis-loop-pass.json" },
  },
  case_file_linked_artifact: false,
  safety_metadata: {
    read_only: true,
    allowed_actions: [],
    no_kubernetes_client: true,
    no_shell: true,
    no_subprocess: true,
    no_kubectl: true,
    no_mutation: true,
    fake_runner: true,
    one_pass_only: true,
  },
};

const ERROR_RESPONSE = { error: "Incident not found" };

// ---------------------------------------------------------------------------
// Tests: generateManualRunId
// ---------------------------------------------------------------------------

describe("generateManualRunId", () => {
  test("produces run_id starting with manual-loop-", () => {
    const runId = generateManualRunId();
    expect(runId).toMatch(/^manual-loop-/);
  });

  test("produces run_id with ISO-like timestamp", () => {
    const runId = generateManualRunId();
    // Format: manual-loop-YYYY-MM-DDTHH-MM-SS
    expect(runId).toMatch(/^manual-loop-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}$/);
  });

  test("produces safe characters only (no special chars)", () => {
    const runId = generateManualRunId();
    // Should only contain alphanumeric, hyphen, underscore, T
    expect(runId).toMatch(/^[a-zA-Z0-9-_T]+$/);
  });
});

// ---------------------------------------------------------------------------
// Tests: createMinimalDiagnosisReport
// ---------------------------------------------------------------------------

describe("createMinimalDiagnosisReport", () => {
  test("produces valid diagnosis report shape", () => {
    const report = createMinimalDiagnosisReport();
    expect(report).toHaveProperty("diagnosis");
    expect(report).toHaveProperty("diagnosis.recommended_investigations");
  });

  test("produces empty recommended_investigations", () => {
    const report = createMinimalDiagnosisReport();
    expect(report.diagnosis.recommended_investigations).toEqual([]);
  });

  test("does not include forbidden fields", () => {
    const report = createMinimalDiagnosisReport();
    const reportJson = JSON.stringify(report);
    expect(reportJson).not.toContain("external_analysis_dir");
    expect(reportJson).not.toContain("artifact_root");
    expect(reportJson).not.toContain("path");
    expect(reportJson).not.toContain("mutate");
    expect(reportJson).not.toContain("remediate");
  });
});

// ---------------------------------------------------------------------------
// Tests: runIncidentDiagnosisLoopOnePass
// ---------------------------------------------------------------------------

describe("runIncidentDiagnosisLoopOnePass", () => {
  const incidentId = "test-incident-123";
  let fetchSpy: ReturnType<typeof createFetchMock>;

  beforeEach(() => {
    fetchSpy = createFetchMock({});
    global.fetch = fetchSpy;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("1. POSTs to correct endpoint", async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse(SUCCESS_RESPONSE, 200));

    const request: DiagnosisLoopOnePassRequest = {
      run_id: generateManualRunId(),
      diagnosis_report: createMinimalDiagnosisReport(),
    };

    await runIncidentDiagnosisLoopOnePass(incidentId, request);

    const calls = fetchSpy.mock.calls;
    expect(calls.length).toBe(1);
    const [url] = calls[0];
    expect(url).toBe(`/api/incidents/${incidentId}/diagnosis-loop/one-pass`);
  });

  test("2. Uses POST method", async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse(SUCCESS_RESPONSE, 200));

    const request: DiagnosisLoopOnePassRequest = {
      run_id: generateManualRunId(),
      diagnosis_report: createMinimalDiagnosisReport(),
    };

    await runIncidentDiagnosisLoopOnePass(incidentId, request);

    const calls = fetchSpy.mock.calls;
    const [, init] = calls[0];
    expect((init as RequestInit).method).toBe("POST");
  });

  test("3. Sends Content-Type: application/json", async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse(SUCCESS_RESPONSE, 200));

    const request: DiagnosisLoopOnePassRequest = {
      run_id: generateManualRunId(),
      diagnosis_report: createMinimalDiagnosisReport(),
    };

    await runIncidentDiagnosisLoopOnePass(incidentId, request);

    const calls = fetchSpy.mock.calls;
    const [, init] = calls[0];
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers["Content-Type"]).toBe("application/json");
  });

  test("4. Sends run_id in request body", async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse(SUCCESS_RESPONSE, 200));

    const runId = generateManualRunId();
    const request: DiagnosisLoopOnePassRequest = {
      run_id: runId,
      diagnosis_report: createMinimalDiagnosisReport(),
    };

    await runIncidentDiagnosisLoopOnePass(incidentId, request);

    const calls = fetchSpy.mock.calls;
    const [, init] = calls[0];
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.run_id).toBe(runId);
  });

  test("5. Sends bounded diagnosis_report", async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse(SUCCESS_RESPONSE, 200));

    const request: DiagnosisLoopOnePassRequest = {
      run_id: generateManualRunId(),
      diagnosis_report: createMinimalDiagnosisReport(),
    };

    await runIncidentDiagnosisLoopOnePass(incidentId, request);

    const calls = fetchSpy.mock.calls;
    const [, init] = calls[0];
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body).toHaveProperty("diagnosis_report");
    expect(body.diagnosis_report).toHaveProperty("diagnosis");
    expect(body.diagnosis_report.diagnosis).toHaveProperty("recommended_investigations");
  });

  test("6. Does not send external_analysis_dir", async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse(SUCCESS_RESPONSE, 200));

    const request: DiagnosisLoopOnePassRequest = {
      run_id: generateManualRunId(),
      diagnosis_report: createMinimalDiagnosisReport(),
    };

    await runIncidentDiagnosisLoopOnePass(incidentId, request);

    const calls = fetchSpy.mock.calls;
    const [, init] = calls[0];
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body).not.toHaveProperty("external_analysis_dir");
    expect(body).not.toHaveProperty("external_analysis_path");
  });

  test("7. Does not send action-control fields", async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse(SUCCESS_RESPONSE, 200));

    const request: DiagnosisLoopOnePassRequest = {
      run_id: generateManualRunId(),
      diagnosis_report: createMinimalDiagnosisReport(),
    };

    await runIncidentDiagnosisLoopOnePass(incidentId, request);

    const calls = fetchSpy.mock.calls;
    const [, init] = calls[0];
    const body = JSON.parse((init as RequestInit).body as string);
    const forbidden = ["mutate", "delete", "scale", "restart", "rollout", "patch", "apply", "remediate"];
    for (const field of forbidden) {
      expect(body).not.toHaveProperty(field);
    }
  });

  test("8. Handles success response", async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse(SUCCESS_RESPONSE, 200));

    const request: DiagnosisLoopOnePassRequest = {
      run_id: generateManualRunId(),
      diagnosis_report: createMinimalDiagnosisReport(),
    };

    const result = await runIncidentDiagnosisLoopOnePass(incidentId, request);

    expect(result.schema_version).toBe("1.0");
    expect(result.incident_id).toBe(incidentId);
    expect(result.read_only).toBe(true);
    expect(result.decision).toBe("continue");
    expect(result.checks_requested).toBe(0);
    expect(result.artifacts.diagnosis_loop_pass.written).toBe(true);
  });

  test("9. Handles backend error response", async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse(ERROR_RESPONSE, 404));

    const request: DiagnosisLoopOnePassRequest = {
      run_id: generateManualRunId(),
      diagnosis_report: createMinimalDiagnosisReport(),
    };

    await expect(runIncidentDiagnosisLoopOnePass(incidentId, request)).rejects.toThrow("Incident not found");
  });

  test("10. Handles network/fetch failure safely", async () => {
    fetchSpy.mockRejectedValueOnce(new Error("Network error"));

    const request: DiagnosisLoopOnePassRequest = {
      run_id: generateManualRunId(),
      diagnosis_report: createMinimalDiagnosisReport(),
    };

    await expect(runIncidentDiagnosisLoopOnePass(incidentId, request)).rejects.toThrow("Network error");
  });

  test("handles error response with error field in body", async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse({ error: "Custom error message" }, 400));

    const request: DiagnosisLoopOnePassRequest = {
      run_id: generateManualRunId(),
      diagnosis_report: createMinimalDiagnosisReport(),
    };

    await expect(runIncidentDiagnosisLoopOnePass(incidentId, request)).rejects.toThrow("Custom error message");
  });

  test("URL-encodes incident ID for safety", async () => {
    fetchSpy.mockResolvedValueOnce(mockResponse(SUCCESS_RESPONSE, 200));

    const request: DiagnosisLoopOnePassRequest = {
      run_id: generateManualRunId(),
      diagnosis_report: createMinimalDiagnosisReport(),
    };

    await runIncidentDiagnosisLoopOnePass("incident/with/slashes", request);

    const calls = fetchSpy.mock.calls;
    const [url] = calls[0];
    expect(url).toBe("/api/incidents/incident%2Fwith%2Fslashes/diagnosis-loop/one-pass");
  });
});
