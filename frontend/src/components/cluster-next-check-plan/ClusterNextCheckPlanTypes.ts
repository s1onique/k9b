/**
 * ClusterNextCheckPlanTypes.ts
 *
 * Local props/view-model types for ClusterNextCheckPlanSection.
 * Re-exports types from parent types.ts and defines local-only types.
 */

import type {
  NextCheckPlanCandidate,
  NextCheckOrphanedApproval,
  NextCheckOutcomeCount,
  NextCheckExecutionResponse,
} from "../../types";

// Re-export for consumers
export type {
  NextCheckPlanCandidate,
  NextCheckOrphanedApproval,
  NextCheckOutcomeCount,
} from "../../types";

// =============================================================================
// Local execution/approval result types
// Kept here to avoid circular imports with ClusterDetailSection
// =============================================================================

export type ExecutionErrorResult = {
  status: "error";
  summary: string;
  blockingReason?: string | null;
};

export type ExecutionResult = NextCheckExecutionResponse | ExecutionErrorResult;

export type ApprovalResult = {
  status: "success" | "error";
  summary: string;
  artifactPath?: string | null;
  approvalTimestamp?: string | null;
};

// =============================================================================
// Status variant types
// =============================================================================

export type NextCheckStatusVariant = "safe" | "approval" | "approved" | "duplicate" | "stale";

// =============================================================================
// Props Contract
// =============================================================================

export interface ClusterNextCheckPlanSectionProps {
  // Data
  planCandidates: NextCheckPlanCandidate[];
  orphanedApprovals: NextCheckOrphanedApproval[];
  planArtifactLink: string | null;
  planSummaryText: string;
  planCandidateCountLabel: string;
  planStatusText: string | null;
  outcomeSummary: NextCheckOutcomeCount[];

  // Context for defaults
  selectedClusterLabel: string | null;

  // Execution state
  executionResults: Record<string, ExecutionResult>;
  approvalResults: Record<string, ApprovalResult>;
  executingCandidate: string | null;
  approvingCandidate: string | null;

  // Handlers
  handleApproveCandidate: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;
  handleManualExecution: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;
  onRefresh: () => void;

  // Helpers
  buildCandidateKey: (candidate: NextCheckPlanCandidate, index: number) => string;
  isManualExecutionAllowed: (candidate: NextCheckPlanCandidate) => boolean;
  artifactUrl: (path: string) => string | null;
  relativeRecency: (ts: string) => string;
}

// Re-export result types for consumers
export type { ExecutionResult, ExecutionErrorResult, ApprovalResult };
