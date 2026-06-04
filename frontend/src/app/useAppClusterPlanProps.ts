/**
 * useAppClusterPlanProps - Hook for deriving ClusterDetailSection props in App.tsx
 *
 * Extracts the construction of derived display values for ClusterDetailSection
 * from App.tsx to reduce component size and move toward LLM-friendly limits.
 *
 * Uses ReturnType<typeof buildClusterDetailSectionProps> to preserve prop typing
 * without manually duplicating types.
 */

import type { NextCheckPlanCandidate } from "../types";
import { buildClusterDetailSectionProps } from "../components/ClusterDetailSection/buildClusterDetailSectionProps";
import { buildClusterPlanSectionProps } from "../components/ClusterDetailSection/buildClusterPlanSectionProps";

// Import types from builders for API shape documentation
import type {
  ClusterDetailPayload,
  ClusterSummary,
  FleetPayload,
  RunPayload,
} from "../types";
import type { ClusterNextCheckPlanSectionProps } from "../components/ClusterDetailSection/ClusterNextCheckPlanSection";

// Re-export display types for consumers
export type ClusterDetailSectionDisplayProps = ReturnType<typeof buildClusterDetailSectionProps>;

// Args interface - mirrors what App.tsx currently passes to the builders
export interface UseAppClusterPlanPropsArgs {
  clusterDetail: ClusterDetailPayload | null;
  selectedClusterLabel: string | null;
  fleet: FleetPayload;
  run: RunPayload | null;
  executionResults: Record<string, unknown>;
  approvalResults: Record<string, unknown>;
  executingCandidate: string | null;
  approvingCandidate: string | null;
  handleApproveCandidate: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;
  handleManualExecution: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;
  refresh: () => Promise<void>;
  buildCandidateKey: (candidate: NextCheckPlanCandidate, index: number) => string;
  isManualExecutionAllowed: (candidate: NextCheckPlanCandidate) => boolean;
}

// Return interface using ReturnType pattern for type safety
export interface UseAppClusterPlanPropsReturn {
  // Derived from buildClusterDetailSectionProps
  selectedCluster: ClusterSummary | null;
  clusterTriggerReason: string;
  drilldownSummary: string;
  recencyTimestamp: string;
  clusterFresh: boolean;
  clusterRecency: string | null;
  // Derived from buildClusterPlanSectionProps
  nextCheckPlanSectionProps: ClusterNextCheckPlanSectionProps;
}

/**
 * Derives ClusterDetailSection props from App.tsx state.
 *
 * Combines buildClusterDetailSectionProps and buildClusterPlanSectionProps
 * into a single hook for cleaner App.tsx composition.
 *
 * Does NOT alter ClusterDetailSection behavior - only moves prop construction.
 */
export function useAppClusterPlanProps({
  clusterDetail,
  selectedClusterLabel,
  fleet,
  run,
  executionResults,
  approvalResults,
  executingCandidate,
  approvingCandidate,
  handleApproveCandidate,
  handleManualExecution,
  refresh,
  buildCandidateKey,
  isManualExecutionAllowed,
}: UseAppClusterPlanPropsArgs): UseAppClusterPlanPropsReturn {
  // Derive cluster display props
  const displayProps = buildClusterDetailSectionProps({
    selectedClusterLabel,
    clusterDetail,
    fleet,
  });

  // Derive next-check plan section props
  const nextCheckPlanSectionProps = buildClusterPlanSectionProps({
    clusterDetail,
    run,
    selectedClusterLabel,
    executionResults,
    approvalResults,
    executingCandidate,
    approvingCandidate,
    handleApproveCandidate,
    handleManualExecution,
    onRefresh: refresh,
    buildCandidateKey,
    isManualExecutionAllowed,
  });

  return {
    selectedCluster: displayProps.selectedCluster,
    clusterTriggerReason: displayProps.clusterTriggerReason,
    drilldownSummary: displayProps.drilldownSummary,
    recencyTimestamp: displayProps.recencyTimestamp,
    clusterFresh: displayProps.clusterFresh,
    clusterRecency: displayProps.clusterRecency,
    nextCheckPlanSectionProps,
  };
}
