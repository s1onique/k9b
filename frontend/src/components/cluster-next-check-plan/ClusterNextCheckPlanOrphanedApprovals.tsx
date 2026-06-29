/**
 * ClusterNextCheckPlanOrphanedApprovals.tsx
 *
 * Renders orphaned approvals section when present.
 */

import type { NextCheckOrphanedApproval } from "./ClusterNextCheckPlanTypes";
import { approvalStatusLabels, formatOrphanedApprovalLabel } from "./clusterNextCheckPlanFormatters";

export interface ClusterNextCheckPlanOrphanedApprovalsProps {
  orphanedApprovals: NextCheckOrphanedApproval[];
  artifactUrl: (path: string) => string | null;
  relativeRecency: (ts: string) => string;
}

export function ClusterNextCheckPlanOrphanedApprovals({
  orphanedApprovals,
  artifactUrl,
  relativeRecency,
}: ClusterNextCheckPlanOrphanedApprovalsProps) {
  return (
    <div className="next-check-orphaned">
      <p className="tiny muted">
        Orphaned approvals · {orphanedApprovals.length} record
        {orphanedApprovals.length === 1 ? "" : "s"}
      </p>
      <ul>
        {orphanedApprovals.map((approval, orphanIndex) => {
          const label = formatOrphanedApprovalLabel(approval);
          const recency = approval.approvalTimestamp
            ? ` · ${relativeRecency(approval.approvalTimestamp)}`
            : "";
          const target = approval.targetCluster
            ? ` · ${approval.targetCluster}`
            : "";
          const artifactLink =
            approval.approvalArtifactPath && artifactUrl(approval.approvalArtifactPath);
          return (
            <li key={`${label}-${orphanIndex}`}>
              <strong>{label}</strong>
              <p className="tiny muted">
                {approvalStatusLabels[approval.approvalStatus ?? ""] ?? "Orphaned"}
                {target}
                {recency}
              </p>
              {artifactLink ? (
                <a className="link" href={artifactLink} target="_blank" rel="noreferrer">
                  View approval record
                </a>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
