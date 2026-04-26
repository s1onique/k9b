/**
 * NextChecksSummaryCard.tsx
 *
 * Displays a summary of next-check candidates with status pills and cluster tags.
 * Extracted from RunSummaryPanel (E1-3b-step15).
 */

import type { NextCheckPlanCandidate, NextCheckStatusVariant } from "../../types";

// Status variant labels
type RunSummaryNextCheckStatusVariant = "safe" | "approval" | "approved" | "duplicate" | "stale";

const runSummaryNextCheckStatusLabel = (variant: RunSummaryNextCheckStatusVariant): string => {
  switch (variant) {
    case "approval":
      return "Approval needed";
    case "approved":
      return "Approved candidate";
    case "duplicate":
      return "Duplicate / already covered";
    case "stale":
      return "Approval stale";
    default:
      return "Safe candidate";
  }
};

export interface NextChecksSummaryCardProps {
  /** Next check plan (may be null) */
  runPlan: { summary: string | null; artifactPath: string | null; status: string; candidateCount?: number } | null;
  /** Plan candidates */
  runPlanCandidates: NextCheckPlanCandidate[];
  /** Summary text for the plan */
  planSummaryText: string;
  /** Plan status text (or null) */
  planStatusText: string | null;
  /** Reason text when plan is unavailable */
  plannerReasonText: string;
  /** Planner hint (or null) */
  plannerHint: string | null;
  /** Planner next action hint (or null) */
  plannerNextActionHint: string | null;
  /** Planner artifact URL (or null) */
  plannerArtifactUrl: string | null;
  /** Candidate count label */
  planCandidateCountLabel: string;
  /** Ordered status variants */
  discoveryVariantOrder: NextCheckStatusVariant[];
  /** Counts by status variant */
  discoveryVariantCounts: Record<NextCheckStatusVariant, number>;
  /** Target cluster labels */
  discoveryClusters: string[];
  /** Callback for general review next checks button */
  onReviewNextChecks: () => void;
  /** Callback when user clicks a specific cluster badge */
  onFocusClusterForNextChecks: (clusterLabel: string) => void;
}

export const NextChecksSummaryCard = ({
  runPlan,
  runPlanCandidates,
  planSummaryText,
  planStatusText,
  plannerReasonText,
  plannerHint,
  plannerNextActionHint,
  plannerArtifactUrl,
  planCandidateCountLabel,
  discoveryVariantOrder,
  discoveryVariantCounts,
  discoveryClusters,
  onReviewNextChecks,
  onFocusClusterForNextChecks,
}: NextChecksSummaryCardProps) => {
  return (
    <div className="run-summary-next-checks">
      <div className="run-summary-next-checks-head">
        <div>
          <p className="eyebrow">Next checks</p>
          <h3>Planner candidates</h3>
          {runPlan ? (
            <>
              <p className="muted tiny">{planSummaryText}</p>
              {planStatusText ? (
                <p className="muted tiny">Planner status: {planStatusText}</p>
              ) : null}
            </>
          ) : (
            <p className="muted tiny">{plannerReasonText}</p>
          )}
          {plannerNextActionHint ? (
            <p className="muted tiny">{plannerNextActionHint}</p>
          ) : null}
          {plannerArtifactUrl ? (
            <p className="muted tiny">
              <a className="link" href={plannerArtifactUrl} target="_blank" rel="noreferrer">
                View planner artifact
              </a>
            </p>
          ) : null}
          {runPlan && runPlanCandidates.length ? (
            <p className="muted tiny">{planCandidateCountLabel}</p>
          ) : null}
        </div>
        <button
          type="button"
          className="run-summary-next-checks-button"
          onClick={onReviewNextChecks}
          disabled={!runPlan}
        >
          Review next checks
        </button>
      </div>
      {!runPlan ? (
        <>
          <p className="muted small">No next checks generated for this run.</p>
          {plannerHint ? (
            <p className="muted tiny">{plannerHint}</p>
          ) : null}
        </>
      ) : runPlanCandidates.length ? (
        <>
          <div className="run-summary-next-checks-stats">
            {discoveryVariantOrder.map((variant) => {
              const count = discoveryVariantCounts[variant];
              if (!count) {
                return null;
              }
              return (
                <span
                  key={variant}
                  className={`next-check-discovery-pill next-check-discovery-pill-${variant}`}
                >
                  <strong>{count}</strong>
                  <span>{runSummaryNextCheckStatusLabel(variant as RunSummaryNextCheckStatusVariant)}</span>
                </span>
              );
            })}
          </div>
          <div className="run-summary-next-checks-clusters">
            <p className="muted tiny">
              Affected cluster{discoveryClusters.length === 1 ? "" : "s"}: {discoveryClusters.length || "None"}
            </p>
            <div className="next-check-cluster-tags">
              {discoveryClusters.length ? (
                discoveryClusters.map((cluster) => (
                  <button
                    type="button"
                    className="next-check-cluster-badge"
                    key={cluster}
                    onClick={() => onFocusClusterForNextChecks(cluster)}
                  >
                    {cluster}
                  </button>
                ))
              ) : (
                <p className="muted small">
                  Planner candidates do not target a specific cluster.
                </p>
              )}
            </div>
          </div>
        </>
      ) : (
        <p className="muted small">Planner created no candidates for this run.</p>
      )}
    </div>
  );
};