/**
 * useAppClusterDetailSectionProps - Hook for deriving all ClusterDetailSection props in App.tsx
 *
 * Extracts cluster plan props and direct ClusterDetailSection props from App.tsx
 * to reduce component size and remove the intermediate clusterPlanProps variable.
 *
 * Does not alter ClusterDetailSection behavior.
 */

import type { NextCheckPlanCandidate } from "../types";
import { useAppClusterPlanProps } from "./useAppClusterPlanProps";

export interface UseAppClusterDetailSectionPropsArgs {
  // From useAppClusterPlanProps
  clusterDetail: import("../types").ClusterDetailPayload | null;
  selectedClusterLabel: string | null;
  fleet: import("../types").FleetPayload;
  run: import("../types").RunPayload | null;
  executionResults: Record<string, unknown>;
  approvalResults: Record<string, unknown>;
  executingCandidate: string | null;
  approvingCandidate: string | null;
  handleApproveCandidate: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;
  handleManualExecution: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;
  refresh: () => Promise<void>;
  buildCandidateKey: (candidate: NextCheckPlanCandidate, index: number) => string;
  isManualExecutionAllowed: (candidate: NextCheckPlanCandidate) => boolean;
  // Direct props
  activeTab: string;
  setActiveTab: (tab: "findings" | "hypotheses" | "checks") => void;
  clusterDetailExpanded: boolean;
  setClusterDetailExpanded: (open: boolean) => void;
  highlightedClusterLabel: string | null;
  handleClusterSelection: (label: string, options?: { expand?: boolean }) => void;
  artifactUrl: (path: string) => string | null;
  formatTimestamp: (ts: string) => string;
  statusClass: (status: string) => string;
}

export interface UseAppClusterDetailSectionPropsResult {
  clusterDetail: import("../types").ClusterDetailPayload | null;
  selectedClusterLabel: string | null;
  selectedCluster: import("../types").ClusterSummary | null;
  fleet: import("../types").FleetPayload;
  activeTab: string;
  setActiveTab: (tab: "findings" | "hypotheses" | "checks") => void;
  clusterDetailExpanded: boolean;
  setClusterDetailExpanded: (open: boolean) => void;
  highlightedClusterLabel: string | null;
  clusterTriggerReason: string;
  drilldownSummary: string;
  recencyTimestamp: string;
  clusterFresh: boolean;
  clusterRecency: string | null;
  handleClusterSelection: (label: string, options?: { expand?: boolean }) => void;
  artifactUrl: (path: string) => string | null;
  formatTimestamp: (ts: string) => string;
  statusClass: (status: string) => string;
  nextCheckPlanSectionProps: import("../components/ClusterDetailSection/ClusterNextCheckPlanSection").ClusterNextCheckPlanSectionProps;
}

/**
 * Derives all ClusterDetailSection props from App.tsx state.
 *
 * Combines useAppClusterPlanProps with direct JSX props into single hook.
 */
export function useAppClusterDetailSectionProps({
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
  activeTab,
  setActiveTab,
  clusterDetailExpanded,
  setClusterDetailExpanded,
  highlightedClusterLabel,
  handleClusterSelection,
  artifactUrl,
  formatTimestamp,
  statusClass,
}: UseAppClusterDetailSectionPropsArgs): UseAppClusterDetailSectionPropsResult {
  // Delegate to existing cluster plan hook
  const planProps = useAppClusterPlanProps({
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
  });

  return {
    clusterDetail,
    selectedClusterLabel,
    selectedCluster: planProps.selectedCluster,
    fleet,
    activeTab,
    setActiveTab,
    clusterDetailExpanded,
    setClusterDetailExpanded,
    highlightedClusterLabel,
    clusterTriggerReason: planProps.clusterTriggerReason,
    drilldownSummary: planProps.drilldownSummary,
    recencyTimestamp: planProps.recencyTimestamp,
    clusterFresh: planProps.clusterFresh,
    clusterRecency: planProps.clusterRecency,
    handleClusterSelection,
    artifactUrl,
    formatTimestamp,
    statusClass,
    nextCheckPlanSectionProps: planProps.nextCheckPlanSectionProps,
  };
}