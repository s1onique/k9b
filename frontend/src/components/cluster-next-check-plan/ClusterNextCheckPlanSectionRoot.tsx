/**
 * ClusterNextCheckPlanSectionRoot.tsx
 *
 * Root orchestration component for the Next Check Plan section.
 * Composes header, orphaned approvals, and candidate cards.
 */

import type { ClusterNextCheckPlanSectionProps } from "./ClusterNextCheckPlanTypes";
import { ClusterNextCheckPlanHeader } from "./ClusterNextCheckPlanHeader";
import { ClusterNextCheckPlanOrphanedApprovals } from "./ClusterNextCheckPlanOrphanedApprovals";
import { ClusterNextCheckPlanCard } from "./ClusterNextCheckPlanCard";
import { hasRenderablePlan, hasOrphanedApprovals } from "./clusterNextCheckPlanViewModel";

/**
 * Root container for the Next Check Plan section.
 * Handles empty state, orphaned approvals, and candidate grid rendering.
 */
export function ClusterNextCheckPlanSectionRoot(props: ClusterNextCheckPlanSectionProps) {
  const {
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
    buildCandidateKey,
    isManualExecutionAllowed,
    artifactUrl,
    relativeRecency,
    handleApproveCandidate,
    handleManualExecution,
    onRefresh,
  } = props;

  // Empty state
  if (!hasRenderablePlan(planCandidates)) {
    return null;
  }

  const showOrphanedApprovals = hasOrphanedApprovals(orphanedApprovals);

  return (
    <div className="next-check-plan">
      <ClusterNextCheckPlanHeader
        planSummaryText={planSummaryText}
        planCandidateCountLabel={planCandidateCountLabel}
        planStatusText={planStatusText}
        planArtifactLink={planArtifactLink}
        outcomeSummary={outcomeSummary}
      />

      {showOrphanedApprovals && (
        <ClusterNextCheckPlanOrphanedApprovals
          orphanedApprovals={orphanedApprovals}
          artifactUrl={artifactUrl}
          relativeRecency={relativeRecency}
        />
      )}

      <div className="next-check-plan-grid">
        {planCandidates.map((candidate, index) => {
          const candidateKey = buildCandidateKey(candidate, index);
          return (
            <ClusterNextCheckPlanCard
              key={`${candidate.description}-${index}`}
              candidate={candidate}
              index={index}
              selectedClusterLabel={selectedClusterLabel}
              executionResults={executionResults}
              approvalResults={approvalResults}
              executingCandidate={executingCandidate}
              approvingCandidate={approvingCandidate}
              candidateKey={candidateKey}
              isManualExecutionAllowed={isManualExecutionAllowed}
              artifactUrl={artifactUrl}
              relativeRecency={relativeRecency}
              handleApproveCandidate={handleApproveCandidate}
              handleManualExecution={handleManualExecution}
              onRefresh={onRefresh}
            />
          );
        })}
      </div>
    </div>
  );
}

export default ClusterNextCheckPlanSectionRoot;

// Re-export props type for consumers
export type { ClusterNextCheckPlanSectionProps } from "./ClusterNextCheckPlanTypes";
