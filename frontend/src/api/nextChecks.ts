/**
 * nextChecks.ts — API client for next-check execution operations.
 *
 * Covers: executeNextCheckCandidate, approveNextCheckCandidate,
 *         promoteDeterministicNextCheck, submitUsefulnessFeedback.
 *
 * All POST operations use the generated OpenAPI client (IncidentsApi).
 * Request body types are generated from the backend API_ROUTES registry.
 *
 * Auth/session behavior: Uses credentials: "include" to preserve session cookies.
 */

import type {
  NextCheckExecutionRequest,
  NextCheckExecutionResponse,
  NextCheckApprovalRequest,
  NextCheckApprovalResponse,
  DeterministicNextCheckPromotionRequest,
  DeterministicNextCheckPromotionResponse,
  UsefulnessFeedbackRequest,
  UsefulnessFeedbackResponse,
} from "../types";

// Generated client imports
import { IncidentsApi } from "../generated/k9b-api";
import {
  ExecuteNextCheckRequest,
  ApproveNextCheckRequest,
  PromoteDeterministicNextCheckRequest,
  RecordNextCheckUsefulnessRequest,
} from "../generated/k9b-api";
import { createK9bApiConfiguration, normalizeGeneratedApiError } from "./generatedClient";
import { ResponseError } from "../generated/k9b-api/runtime";

// =============================================================================
// API Factory
// =============================================================================

function createIncidentsApi(): IncidentsApi {
  return new IncidentsApi(createK9bApiConfiguration());
}

// =============================================================================
// Next-check execution
// =============================================================================

type NextCheckExecutionError = Error & { blockingReason?: string | null };

/**
 * Normalize errors from next-check execution, preserving blockingReason.
 *
 * This is a specialized error normalizer that parses ResponseError directly
 * to extract the blockingReason field before generic error normalization.
 */
async function normalizeNextCheckExecutionError(
  error: unknown
): Promise<NextCheckExecutionError> {
  if (error instanceof ResponseError) {
    let message = error.response.statusText;
    let blockingReason: string | null | undefined;

    try {
      const payload = await error.response.json();
      if (payload && typeof payload === "object") {
        if ("error" in payload) {
          message = String((payload as Record<string, unknown>).error);
        }
        if ("blockingReason" in payload) {
          blockingReason = (payload as Record<string, unknown>).blockingReason as string | null;
        }
      }
    } catch {
      // keep statusText
    }

    const nextError = new Error(
      message || "Failed to execute next-check candidate"
    ) as NextCheckExecutionError;
    nextError.blockingReason = blockingReason ?? null;
    return nextError;
  }

  const normalized = await normalizeGeneratedApiError(error);
  const nextError = normalized as NextCheckExecutionError;
  nextError.blockingReason ??= null;
  return nextError;
}

/**
 * Execute a next-check candidate.
 *
 * Uses the generated client with typed request body from API schema.
 */
export const executeNextCheckCandidate = async (
  request: NextCheckExecutionRequest
): Promise<NextCheckExecutionResponse> => {
  try {
    const api = createIncidentsApi();
    const generatedRequest: ExecuteNextCheckRequest = {
      candidateId: request.candidateId,
      candidateIndex: request.candidateIndex,
      clusterLabel: request.clusterLabel,
      planArtifactPath: request.planArtifactPath,
    };
    const result = await api.executeNextCheck({
      executeNextCheckRequest: generatedRequest,
    });
    return result as NextCheckExecutionResponse;
  } catch (error) {
    throw await normalizeNextCheckExecutionError(error);
  }
};

// =============================================================================
// Next-check approval
// =============================================================================

/**
 * Approve a next-check candidate for execution.
 *
 * Uses the generated client with typed request body from API schema.
 */
export const approveNextCheckCandidate = async (
  request: NextCheckApprovalRequest
): Promise<NextCheckApprovalResponse> => {
  try {
    const api = createIncidentsApi();
    const generatedRequest: ApproveNextCheckRequest = {
      candidateId: request.candidateId,
      candidateIndex: request.candidateIndex,
      clusterLabel: request.clusterLabel,
    };
    const result = await api.approveNextCheck({
      approveNextCheckRequest: generatedRequest,
    });
    return result as NextCheckApprovalResponse;
  } catch (error) {
    throw await normalizeGeneratedApiError(error);
  }
};

// =============================================================================
// Deterministic next-check promotion
// =============================================================================

/**
 * Promote a deterministic next-check candidate.
 *
 * Uses the generated client with typed request body from API schema.
 */
export const promoteDeterministicNextCheck = async (
  request: DeterministicNextCheckPromotionRequest
): Promise<DeterministicNextCheckPromotionResponse> => {
  try {
    const api = createIncidentsApi();
    const generatedRequest: PromoteDeterministicNextCheckRequest = {
      clusterLabel: request.clusterLabel,
      description: request.description,
      method: request.method,
      evidenceNeeded: request.evidenceNeeded,
      workstream: request.workstream,
      urgency: request.urgency,
      whyNow: request.whyNow,
      topProblem: request.topProblem,
      priorityScore: request.priorityScore,
      context: request.context,
    };
    const result = await api.promoteDeterministicNextCheck({
      promoteDeterministicNextCheckRequest: generatedRequest,
    });
    return result as DeterministicNextCheckPromotionResponse;
  } catch (error) {
    throw await normalizeGeneratedApiError(error);
  }
};

// =============================================================================
// Usefulness feedback
// =============================================================================

/**
 * Submit usefulness feedback for a next-check execution.
 *
 * Uses the generated client with typed request body from API schema.
 */
export const submitUsefulnessFeedback = async (
  request: UsefulnessFeedbackRequest
): Promise<UsefulnessFeedbackResponse> => {
  try {
    const api = createIncidentsApi();
    const generatedRequest: RecordNextCheckUsefulnessRequest = {
      artifactPath: request.artifactPath,
      usefulnessClass: request.usefulnessClass,
      usefulnessSummary: request.usefulnessSummary,
      // Pass optional context fields for stage-aware feedback
      reviewStage: request.reviewStage,
      workstream: request.workstream,
      problemClass: request.problemClass,
      judgmentScope: request.judgmentScope,
      reviewerConfidence: request.reviewerConfidence,
    };
    const result = await api.recordNextCheckUsefulness({
      recordNextCheckUsefulnessRequest: generatedRequest,
    });
    return result as UsefulnessFeedbackResponse;
  } catch (error) {
    throw await normalizeGeneratedApiError(error);
  }
};
