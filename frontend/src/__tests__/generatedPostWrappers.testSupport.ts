/**
 * generatedPostWrappers.testSupport.ts
 *
 * Shared test fixtures and helpers for generatedPostWrappers tests.
 * Extracted to reduce file sizes below the 500-line threshold.
 */

import { vi } from "vitest";
import { ResponseError } from "../generated/k9b-api/runtime";

// ---------------------------------------------------------------------------
// Mock IncidentsApi instance
// ---------------------------------------------------------------------------

export const mockIncidentsApiInstance = {
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

// ---------------------------------------------------------------------------
// Helper to get the mock instance for assertions
// ---------------------------------------------------------------------------

export const createMockIncidentsApi = () => mockIncidentsApiInstance;

// ---------------------------------------------------------------------------
// ResponseError helper for testing error propagation
// ---------------------------------------------------------------------------

export const createResponseError = (
  status: number,
  body: Record<string, unknown>,
  statusText = "Bad Request"
): ResponseError => {
  const response = new Response(JSON.stringify(body), { status, statusText });
  return new ResponseError(response, "Response returned an error code");
};
