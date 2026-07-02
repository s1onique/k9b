/**
 * generatedPostWrappers.test.ts
 *
 * Focused tests verifying wrapper-to-generated-client mappings for POST operations.
 * Tests that each wrapper passes the correct operation object, request-body property name,
 * and initOverrides to the generated IncidentsApi.
 *
 * Also tests blockingReason preservation via ResponseError.
 */

import { describe, expect, test, vi, beforeEach } from "vitest";
import { ResponseError } from "../generated/k9b-api/runtime";
import { IncidentsApi } from "../generated/k9b-api";

// Mock the IncidentsApi before importing wrapper modules
const mockIncidentsApiInstance = {
  captureIncidentSnapshot: vi.fn(),
  createIncidentReviewPacket: vi.fn(),
  executeNextCheck: vi.fn(),
  approveNextCheck: vi.fn(),
  promoteDeterministicNextCheck: vi.fn(),
  recordNextCheckUsefulness: vi.fn(),
  runBatchNextCheckExecution: vi.fn(),
  performAlertmanagerSourceAction: vi.fn(),
  recordAlertmanagerRelevanceFeedback: vi.fn(),
  getRunDetail: vi.fn(),
};

vi.mock("../generated/k9b-api", async () => {
  const actual = await vi.importActual("../generated/k9b-api");
  return {
    ...actual,
    IncidentsApi: vi.fn().mockImplementation(() => mockIncidentsApiInstance),
  };
});

// Import wrappers being tested AFTER the mock
import {
  captureIncidentSnapshot,
  generateIncidentReviewPacket,
} from "../api/incidents";
import {
  executeNextCheckCandidate,
  approveNextCheckCandidate,
  promoteDeterministicNextCheck,
  submitUsefulnessFeedback,
} from "../api/nextChecks";
import {
  performAlertmanagerSourceAction,
  submitAlertmanagerRelevanceFeedback,
} from "../api/alertmanager";
import { fetchRun, runBatchExecution } from "../api/runs";

// Reset mocks before each test
beforeEach(() => {
  vi.clearAllMocks();
});

// Helper to get the mock instance for assertions
const createMockIncidentsApi = () => mockIncidentsApiInstance;

// ---------------------------------------------------------------------------
// captureIncidentSnapshot
// ---------------------------------------------------------------------------

describe("captureIncidentSnapshot wrapper mapping", () => {
  test("calls api.captureIncidentSnapshot with correct request object", async () => {
    const mockApi = createMockIncidentsApi();
    mockApi.captureIncidentSnapshot.mockResolvedValue({
      artifactPath: "/snapshots/test.json",
    } as never);

    const result = await captureIncidentSnapshot({
      namespace: "default",
      sinceHours: 2,
    });

    expect(result.artifactPath).toBe("/snapshots/test.json");
    expect(mockApi.captureIncidentSnapshot).toHaveBeenCalledTimes(1);
    expect(mockApi.captureIncidentSnapshot).toHaveBeenCalledWith({
      captureIncidentSnapshotRequest: {
        namespace: "default",
        sinceHours: 2,
      },
    });
  });
});

// ---------------------------------------------------------------------------
// generateIncidentReviewPacket
// ---------------------------------------------------------------------------

describe("generateIncidentReviewPacket wrapper mapping", () => {
  test("calls api.createIncidentReviewPacket with correct request object", async () => {
    const mockApi = createMockIncidentsApi();
    mockApi.createIncidentReviewPacket.mockResolvedValue({
      reviewPacketPath: "/reviews/test.json",
    } as never);

    const result = await generateIncidentReviewPacket({
      bundle: "/artifacts/bundle.json",
      format: "json",
    });

    expect(result.reviewPacketPath).toBe("/reviews/test.json");
    expect(mockApi.createIncidentReviewPacket).toHaveBeenCalledTimes(1);
    expect(mockApi.createIncidentReviewPacket).toHaveBeenCalledWith({
      createIncidentReviewPacketRequest: {
        bundle: "/artifacts/bundle.json",
        format: "json",
      },
    });
  });
});

// ---------------------------------------------------------------------------
// executeNextCheckCandidate
// ---------------------------------------------------------------------------

describe("executeNextCheckCandidate wrapper mapping", () => {
  test("calls api.executeNextCheck with correct request object", async () => {
    const mockApi = createMockIncidentsApi();
    mockApi.executeNextCheck.mockResolvedValue({
      status: "executed",
    } as never);

    const result = await executeNextCheckCandidate({
      candidateId: "cand-123",
      candidateIndex: 0,
      clusterLabel: "cluster-a",
      planArtifactPath: "/plans/plan.json",
    });

    expect(result.status).toBe("executed");
    expect(mockApi.executeNextCheck).toHaveBeenCalledTimes(1);
    expect(mockApi.executeNextCheck).toHaveBeenCalledWith({
      executeNextCheckRequest: {
        candidateId: "cand-123",
        candidateIndex: 0,
        clusterLabel: "cluster-a",
        planArtifactPath: "/plans/plan.json",
      },
    });
  });

  test("preserves blockingReason from ResponseError body", async () => {
    const mockApi = createMockIncidentsApi();

    // Create a ResponseError with blockingReason in the JSON body
    const errorResponse = new Response(
      JSON.stringify({ error: "blocked", blockingReason: "budget_exhausted" }),
      { status: 400, statusText: "Bad Request" }
    );
    mockApi.executeNextCheck.mockRejectedValue(
      new ResponseError(errorResponse, "Response returned an error code")
    );

    try {
      await executeNextCheckCandidate({
        candidateId: "cand-123",
        candidateIndex: 0,
        clusterLabel: "cluster-a",
        planArtifactPath: "/plans/plan.json",
      });
      expect.fail("Should have thrown");
    } catch (e) {
      expect((e as Error).message).toBe("blocked");
      expect((e as { blockingReason?: string }).blockingReason).toBe("budget_exhausted");
    }
  });
});

// ---------------------------------------------------------------------------
// approveNextCheckCandidate
// ---------------------------------------------------------------------------

describe("approveNextCheckCandidate wrapper mapping", () => {
  test("calls api.approveNextCheck with correct request object", async () => {
    const mockApi = createMockIncidentsApi();
    mockApi.approveNextCheck.mockResolvedValue({
      status: "approved",
    } as never);

    const result = await approveNextCheckCandidate({
      candidateId: "cand-456",
      candidateIndex: 1,
      clusterLabel: "cluster-b",
    });

    expect(result.status).toBe("approved");
    expect(mockApi.approveNextCheck).toHaveBeenCalledTimes(1);
    expect(mockApi.approveNextCheck).toHaveBeenCalledWith({
      approveNextCheckRequest: {
        candidateId: "cand-456",
        candidateIndex: 1,
        clusterLabel: "cluster-b",
      },
    });
  });
});

// ---------------------------------------------------------------------------
// promoteDeterministicNextCheck
// ---------------------------------------------------------------------------

describe("promoteDeterministicNextCheck wrapper mapping", () => {
  test("calls api.promoteDeterministicNextCheck with all request fields", async () => {
    const mockApi = createMockIncidentsApi();
    mockApi.promoteDeterministicNextCheck.mockResolvedValue({
      status: "promoted",
    } as never);

    const request = {
      clusterLabel: "cluster-a",
      description: "Check memory pressure",
      method: "kubectl top nodes",
      evidenceNeeded: "Memory usage > 80%",
      workstream: "performance",
      urgency: "medium",
      whyNow: "High memory alerts",
      topProblem: "Memory pressure",
      priorityScore: 75,
      context: "Recurring memory alerts",
    };

    const result = await promoteDeterministicNextCheck(request);

    expect(result.status).toBe("promoted");
    expect(mockApi.promoteDeterministicNextCheck).toHaveBeenCalledTimes(1);
    expect(mockApi.promoteDeterministicNextCheck).toHaveBeenCalledWith({
      promoteDeterministicNextCheckRequest: {
        clusterLabel: "cluster-a",
        description: "Check memory pressure",
        method: "kubectl top nodes",
        evidenceNeeded: "Memory usage > 80%",
        workstream: "performance",
        urgency: "medium",
        whyNow: "High memory alerts",
        topProblem: "Memory pressure",
        priorityScore: 75,
        context: "Recurring memory alerts",
      },
    });
  });
});

// ---------------------------------------------------------------------------
// submitUsefulnessFeedback
// ---------------------------------------------------------------------------

describe("submitUsefulnessFeedback wrapper mapping", () => {
  test("calls api.recordNextCheckUsefulness with all 8 fields", async () => {
    const mockApi = createMockIncidentsApi();
    mockApi.recordNextCheckUsefulness.mockResolvedValue({
      status: "recorded",
    } as never);

    const request = {
      artifactPath: "/artifacts/feedback.json",
      usefulnessClass: "useful",
      usefulnessSummary: "Helped identify the issue",
      // Optional context fields
      reviewStage: "initial_diagnosis",
      workstream: "performance",
      problemClass: "memory",
      judgmentScope: "single_check",
      reviewerConfidence: "high",
    };

    const result = await submitUsefulnessFeedback(request);

    expect(result.status).toBe("recorded");
    expect(mockApi.recordNextCheckUsefulness).toHaveBeenCalledTimes(1);
    expect(mockApi.recordNextCheckUsefulness).toHaveBeenCalledWith({
      recordNextCheckUsefulnessRequest: {
        artifactPath: "/artifacts/feedback.json",
        usefulnessClass: "useful",
        usefulnessSummary: "Helped identify the issue",
        reviewStage: "initial_diagnosis",
        workstream: "performance",
        problemClass: "memory",
        judgmentScope: "single_check",
        reviewerConfidence: "high",
      },
    });
  });

  test("works with minimal required fields only", async () => {
    const mockApi = createMockIncidentsApi();
    mockApi.recordNextCheckUsefulness.mockResolvedValue({
      status: "recorded",
    } as never);

    const request = {
      artifactPath: "/artifacts/feedback.json",
      usefulnessClass: "useful",
      usefulnessSummary: "Short summary",
    };

    const result = await submitUsefulnessFeedback(request);

    expect(result.status).toBe("recorded");
    expect(mockApi.recordNextCheckUsefulness).toHaveBeenCalledWith({
      recordNextCheckUsefulnessRequest: {
        artifactPath: "/artifacts/feedback.json",
        usefulnessClass: "useful",
        usefulnessSummary: "Short summary",
        reviewStage: undefined,
        workstream: undefined,
        problemClass: undefined,
        judgmentScope: undefined,
        reviewerConfidence: undefined,
      },
    });
  });
});

// ---------------------------------------------------------------------------
// runBatchExecution
// ---------------------------------------------------------------------------

describe("runBatchExecution wrapper mapping", () => {
  test("calls api.runBatchNextCheckExecution with correct request object", async () => {
    const mockApi = createMockIncidentsApi();
    mockApi.runBatchNextCheckExecution.mockResolvedValue({
      status: "batch_executed",
      results: [],
    } as never);

    const result = await runBatchExecution({
      runId: "run-789",
      dryRun: false,
    });

    expect(result.status).toBe("batch_executed");
    expect(mockApi.runBatchNextCheckExecution).toHaveBeenCalledTimes(1);
    expect(mockApi.runBatchNextCheckExecution).toHaveBeenCalledWith({
      runBatchNextCheckExecutionRequest: {
        runId: "run-789",
        dryRun: false,
      },
    });
  });

  test("passes dryRun: true when specified", async () => {
    const mockApi = createMockIncidentsApi();
    mockApi.runBatchNextCheckExecution.mockResolvedValue({
      status: "dry_run_complete",
      results: [],
    } as never);

    await runBatchExecution({
      runId: "run-789",
      dryRun: true,
    });

    expect(mockApi.runBatchNextCheckExecution).toHaveBeenCalledWith({
      runBatchNextCheckExecutionRequest: {
        runId: "run-789",
        dryRun: true,
      },
    });
  });
});

// ---------------------------------------------------------------------------
// performAlertmanagerSourceAction
// ---------------------------------------------------------------------------

describe("performAlertmanagerSourceAction wrapper mapping", () => {
  test("calls api.performAlertmanagerSourceAction with correct request object", async () => {
    const mockApi = createMockIncidentsApi();
    mockApi.performAlertmanagerSourceAction.mockResolvedValue({
      status: "success",
    } as never);

    const result = await performAlertmanagerSourceAction(
      {
        sourceId: "src-123",
        clusterLabel: "cluster-a",
        action: "promote",
        reason: "Confirmed alert",
      },
      "run-456"
    );

    expect(result.status).toBe("success");
    expect(mockApi.performAlertmanagerSourceAction).toHaveBeenCalledTimes(1);
    expect(mockApi.performAlertmanagerSourceAction).toHaveBeenCalledWith({
      runId: "run-456",
      sourceId: "src-123",
      performAlertmanagerSourceActionRequest: {
        action: "promote",
        clusterLabel: "cluster-a",
        reason: "Confirmed alert",
      },
    });
  });
});

// ---------------------------------------------------------------------------
// submitAlertmanagerRelevanceFeedback
// ---------------------------------------------------------------------------

describe("submitAlertmanagerRelevanceFeedback wrapper mapping", () => {
  test("calls api.recordAlertmanagerRelevanceFeedback with correct request object", async () => {
    const mockApi = createMockIncidentsApi();
    mockApi.recordAlertmanagerRelevanceFeedback.mockResolvedValue({
      status: "recorded",
    } as never);

    const result = await submitAlertmanagerRelevanceFeedback({
      artifactPath: "/artifacts/feedback.json",
      alertmanagerRelevance: "relevant",
      alertmanagerRelevanceSummary: "This is a real alert",
    });

    expect(result.status).toBe("recorded");
    expect(mockApi.recordAlertmanagerRelevanceFeedback).toHaveBeenCalledTimes(1);
    expect(mockApi.recordAlertmanagerRelevanceFeedback).toHaveBeenCalledWith({
      recordAlertmanagerRelevanceFeedbackRequest: {
        artifactPath: "/artifacts/feedback.json",
        alertmanagerRelevance: "relevant",
        alertmanagerRelevanceSummary: "This is a real alert",
      },
    });
  });
});

// ---------------------------------------------------------------------------
// fetchRun - Regression test for initOverrides (clientRequestId, signal)
// ---------------------------------------------------------------------------

describe("fetchRun initOverrides regression", () => {
  test("passes clientRequestId in headers and signal via initOverrides", async () => {
    const mockApi = createMockIncidentsApi();
    mockApi.getRunDetail.mockResolvedValue({
      runId: "run-123",
    } as never);

    const clientRequestId = "req-abc-123";
    const signal = new AbortController().signal;

    await fetchRun("run-123", { clientRequestId, signal });

    expect(mockApi.getRunDetail).toHaveBeenCalledTimes(1);
    expect(mockApi.getRunDetail).toHaveBeenCalledWith(
      { runId: "run-123" },
      {
        headers: expect.objectContaining({
          "X-K9B-Client-Request-Id": clientRequestId,
        }),
        signal,
      }
    );
  });

  test("works without clientRequestId and signal", async () => {
    const mockApi = createMockIncidentsApi();
    mockApi.getRunDetail.mockResolvedValue({
      runId: "run-123",
    } as never);

    const result = await fetchRun("run-123");

    expect(result.runId).toBe("run-123");
    expect(mockApi.getRunDetail).toHaveBeenCalledTimes(1);
    expect(mockApi.getRunDetail).toHaveBeenCalledWith({ runId: "run-123" }, undefined);
  });
});
