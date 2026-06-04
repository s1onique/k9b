/**
 * Build props for Cluster Detail plan/planner/discovery section - pure derivation bundle.
 *
 * Extracts plan/planner/discovery values from App.tsx for nextCheckPlanSectionProps.
 * Does not extract handlers, navigation helpers, execution state, or UI state.
 */

import type {
  ClusterDetailPayload,
  NextCheckPlanCandidate,
  NextCheckOrphanedApproval,
  RunPayload,
} from "../../types";
import { artifactUrl, relativeRecency } from "../../utils";
import type { ClusterNextCheckPlanSectionProps } from "./ClusterNextCheckPlanSection";

export interface BuildClusterPlanSectionPropsArgs {
  clusterDetail: ClusterDetailPayload | null;
  run: RunPayload | null;
  selectedClusterLabel: string | null;
  // Execution state - passed through from App.tsx
  executionResults: Record<string, unknown>;
  approvalResults: Record<string, unknown>;
  executingCandidate: string | null;
  approvingCandidate: string | null;
  // Handlers - passed through from App.tsx
  handleApproveCandidate: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;
  handleManualExecution: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;
  onRefresh: () => void;
  buildCandidateKey: (candidate: NextCheckPlanCandidate, index: number) => string;
  isManualExecutionAllowed: (candidate: NextCheckPlanCandidate) => boolean;
}

/**
 * Build cluster plan section props - pure value derivation.
 *
 * Takes run and cluster detail data plus execution state/handlers from App.tsx
 * and returns all values needed for nextCheckPlanSectionProps.
 */
export function buildClusterPlanSectionProps({
  clusterDetail,
  run,
  selectedClusterLabel,
  executionResults,
  approvalResults,
  executingCandidate,
  approvingCandidate,
  handleApproveCandidate,
  handleManualExecution,
  onRefresh,
  buildCandidateKey,
  isManualExecutionAllowed,
}: BuildClusterPlanSectionPropsArgs): ClusterNextCheckPlanSectionProps {
  // Plan candidates from cluster detail
  const planCandidates: NextCheckPlanCandidate[] = clusterDetail?.nextCheckPlan ?? [];

  // Run plan from selected run
  const runPlan = run?.nextCheckPlan;

  // Orphaned approvals
  const orphanedApprovals: NextCheckOrphanedApproval[] = runPlan?.orphanedApprovals ?? [];

  // Plan artifact link
  const planArtifactLink = runPlan?.artifactPath ? artifactUrl(runPlan.artifactPath) : null;

  // Planner availability from run
  const plannerAvailability = run?.plannerAvailability ?? null;

  // Planner reason for fallback text
  const plannerReason = plannerAvailability?.reason ?? null;

  // Plan summary text
  const planSummaryText =
    runPlan?.summary ?? plannerReason ?? "Provider-assisted next-check candidates are available.";

  // Plan candidate count label (with pluralization)
  const planCandidateCountLabel =
    runPlan?.candidateCount != null
      ? `${runPlan.candidateCount} candidate${runPlan.candidateCount === 1 ? "" : "s"}`
      : `${planCandidates.length} candidate${planCandidates.length === 1 ? "" : "s"}`;

  // Plan status text
  const planStatusText = runPlan?.status ?? null;

  // Outcome summary
  const outcomeSummary = runPlan?.outcomeCounts ?? [];

  // Next check plan section props - complete prop bundle for ClusterNextCheckPlanSection
  return {
    planCandidates,
    orphanedApprovals,
    planArtifactLink,
    planSummaryText,
    planCandidateCountLabel,
    planStatusText,
    outcomeSummary,
    selectedClusterLabel,
    executionResults,
    approvalResults,
    executingCandidate,
    approvingCandidate,
    handleApproveCandidate,
    handleManualExecution,
    onRefresh,
    buildCandidateKey,
    isManualExecutionAllowed,
    artifactUrl,
    relativeRecency,
  };
}
