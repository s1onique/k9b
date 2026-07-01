/**
 * nextChecks.ts — API client for next-check execution operations.
 *
 * Covers: executeNextCheckCandidate, approveNextCheckCandidate,
 *         promoteDeterministicNextCheck, submitUsefulnessFeedback.
 *
 * POST operations with request bodies use raw fetch because the API schema
 * doesn't define request bodies for these endpoints.
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

// =============================================================================
// Next-check execution (raw fetch - API schema doesn't define request body)
// =============================================================================

type NextCheckExecutionError = Error & { blockingReason?: string | null };

/**
 * Execute a next-check candidate.
 *
 * Uses raw fetch because the generated client doesn't have request body support
 * (API schema doesn't define request body for this endpoint).
 */
export const executeNextCheckCandidate = async (
  request: NextCheckExecutionRequest
): Promise<NextCheckExecutionResponse> => {
  const response = await fetch("/api/next-check-execution", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    cache: "no-store",
  });

  if (!response.ok) {
    let message = response.statusText;
    let blockingReason: string | null | undefined;
    try {
      const payload = await response.json();
      if (payload && typeof payload === "object") {
        if ("error" in payload) {
          message = String((payload as Record<string, unknown>).error);
        }
        if ("blockingReason" in payload) {
          blockingReason = (payload as Record<string, unknown>).blockingReason as string | null;
        }
      }
    } catch {
      // ignore
    }
    const error = new Error(message || "Failed to execute next-check candidate") as NextCheckExecutionError;
    error.blockingReason = blockingReason ?? null;
    throw error;
  }

  const data = await response.json();
  return data as NextCheckExecutionResponse;
};

// =============================================================================
// Next-check approval (raw fetch - API schema doesn't define request body)
// =============================================================================

/**
 * Approve a next-check candidate for execution.
 *
 * Uses raw fetch because the generated client doesn't have request body support
 * (API schema doesn't define request body for this endpoint).
 */
export const approveNextCheckCandidate = async (
  request: NextCheckApprovalRequest
): Promise<NextCheckApprovalResponse> => {
  const response = await fetch("/api/next-check-approval", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    cache: "no-store",
  });

  if (!response.ok) {
    let message = response.statusText;
    try {
      const payload = await response.json();
      if (payload && typeof payload === "object" && "error" in payload) {
        message = String((payload as Record<string, unknown>).error);
      }
    } catch {
      // ignore
    }
    throw new Error(message || "Failed to approve next-check candidate");
  }

  const data = await response.json();
  return data as NextCheckApprovalResponse;
};

// =============================================================================
// Deterministic next-check promotion (raw fetch - API schema doesn't define request body)
// =============================================================================

/**
 * Promote a deterministic next-check candidate.
 *
 * Uses raw fetch because the generated client doesn't have request body support
 * (API schema doesn't define request body for this endpoint).
 */
export const promoteDeterministicNextCheck = async (
  request: DeterministicNextCheckPromotionRequest
): Promise<DeterministicNextCheckPromotionResponse> => {
  const response = await fetch("/api/deterministic-next-check/promote", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    cache: "no-store",
  });

  if (!response.ok) {
    let message = response.statusText;
    try {
      const payload = await response.json();
      if (payload && typeof payload === "object" && "error" in payload) {
        message = String((payload as Record<string, unknown>).error);
      }
    } catch {
      // ignore
    }
    throw new Error(message || "Failed to promote deterministic next check");
  }

  return (await response.json()) as DeterministicNextCheckPromotionResponse;
};

// =============================================================================
// Usefulness feedback (raw fetch - API schema doesn't define request body)
// =============================================================================

/**
 * Submit usefulness feedback for a next-check execution.
 *
 * Uses raw fetch because the generated client doesn't have request body support
 * (API schema doesn't define request body for this endpoint).
 */
export const submitUsefulnessFeedback = async (
  request: UsefulnessFeedbackRequest
): Promise<UsefulnessFeedbackResponse> => {
  const response = await fetch("/api/next-check-execution-usefulness", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    cache: "no-store",
  });

  if (!response.ok) {
    let message = response.statusText;
    try {
      const payload = await response.json();
      if (payload && typeof payload === "object" && "error" in payload) {
        message = String((payload as Record<string, unknown>).error);
      }
    } catch {
      // ignore
    }
    throw new Error(message || "Failed to submit usefulness feedback");
  }

  return (await response.json()) as UsefulnessFeedbackResponse;
};
