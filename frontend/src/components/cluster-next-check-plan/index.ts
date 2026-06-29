/**
 * cluster-next-check-plan/index.ts
 *
 * Public barrel export for the cluster-next-check-plan module.
 * Consumers should import from this file or the main facade.
 */

export { ClusterNextCheckPlanSectionRoot as ClusterNextCheckPlanSection } from "./ClusterNextCheckPlanSectionRoot";
export { default } from "./ClusterNextCheckPlanSectionRoot";

// Re-export types
export type {
  ClusterNextCheckPlanSectionProps,
  ExecutionResult,
  ExecutionErrorResult,
  ApprovalResult,
  NextCheckStatusVariant,
} from "./ClusterNextCheckPlanTypes";
export type { NextCheckPlanCandidate } from "./ClusterNextCheckPlanTypes";
export type { NextCheckOrphanedApproval } from "./ClusterNextCheckPlanTypes";
export type { NextCheckOutcomeCount } from "./ClusterNextCheckPlanTypes";

// Re-export view model helpers for testing
export {
  determineNextCheckStatusVariant,
  getPlanStatusLabel,
  buildRationaleEntries,
  hasRenderablePlan,
  hasOrphanedApprovals,
} from "./clusterNextCheckPlanViewModel";
