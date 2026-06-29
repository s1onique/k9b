/**
 * ClusterNextCheckPlanSection.tsx
 *
 * Thin facade / public import path for the Next Check Plan section.
 * Preserves the original import path for downstream consumers.
 *
 * Actual implementation lives in ./cluster-next-check-plan/
 */

export {
  ClusterNextCheckPlanSection,
  default,
} from "./cluster-next-check-plan";

// Re-export types for consumers
export type {
  ClusterNextCheckPlanSectionProps,
  ExecutionResult,
  ExecutionErrorResult,
  ApprovalResult,
  NextCheckStatusVariant,
  NextCheckPlanCandidate,
  NextCheckOrphanedApproval,
  NextCheckOutcomeCount,
} from "./cluster-next-check-plan";
