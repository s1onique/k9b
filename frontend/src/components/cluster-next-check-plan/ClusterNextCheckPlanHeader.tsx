/**
 * ClusterNextCheckPlanHeader.tsx
 *
 * Renders the header section of the Next Check Plan panel.
 * Shows summary text, candidate count, status, and artifact link.
 */

import type { NextCheckOutcomeCount } from "./ClusterNextCheckPlanTypes";
import { outcomeStatusClass, outcomeStatusDisplay } from "./clusterNextCheckPlanFormatters";

export interface ClusterNextCheckPlanHeaderProps {
  planSummaryText: string;
  planCandidateCountLabel: string;
  planStatusText: string | null;
  planArtifactLink: string | null;
  outcomeSummary: NextCheckOutcomeCount[];
}

export function ClusterNextCheckPlanHeader({
  planSummaryText,
  planCandidateCountLabel,
  planStatusText,
  planArtifactLink,
  outcomeSummary,
}: ClusterNextCheckPlanHeaderProps) {
  return (
    <div className="section-head next-check-plan-head">
      <div>
        <h3>Next check plan</h3>
        <p className="muted small">{planSummaryText}</p>
        <p className="muted tiny">
          {planCandidateCountLabel}
          {planStatusText ? ` · ${planStatusText}` : ""}
        </p>
        {outcomeSummary.length ? (
          <div className="next-check-outcome-summary">
            {outcomeSummary.map((entry) => (
              <span key={entry.status} className={outcomeStatusClass(entry.status)}>
                {outcomeStatusDisplay(entry.status)} · {entry.count}
              </span>
            ))}
          </div>
        ) : null}
      </div>
      {planArtifactLink ? (
        <a
          className="link"
          href={planArtifactLink}
          target="_blank"
          rel="noreferrer"
        >
          View planner artifact
        </a>
      ) : null}
    </div>
  );
}
