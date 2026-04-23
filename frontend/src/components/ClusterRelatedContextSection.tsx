/**
 * ClusterRelatedContextSection Component
 *
 * Renders the lower supporting-context block from ClusterDetailSection:
 * - Drilldown summary
 * - Related proposals
 * - Related notifications
 *
 * Extracted from ClusterDetailSection.tsx as part of the second-pass decomposition effort.
 * This is a presentational block with no interaction/state behavior.
 */

import type {
  DrilldownCoverage,
  DrilldownSummary,
  ProposalEntry,
  NotificationEntry,
} from "../types";

// =============================================================================
// Props Contract
// =============================================================================

export interface ClusterRelatedContextSectionProps {
  // Data
  drilldownAvailability: DrilldownSummary | null;
  drilldownCoverage: DrilldownCoverage[];
  relatedProposals: ProposalEntry[];
  relatedNotifications: NotificationEntry[];

  // Helpers
  artifactUrl: (path: string) => string | null;
  formatTimestamp: (ts: string) => string;
  statusClass: (status: string) => string;
}

// =============================================================================
// Component
// =============================================================================

export const ClusterRelatedContextSection: React.FC<ClusterRelatedContextSectionProps> = ({
  drilldownAvailability,
  drilldownCoverage,
  relatedProposals,
  relatedNotifications,
  artifactUrl,
  formatTimestamp,
  statusClass,
}) => {
  return (
    <div className="cluster-lists">
      <div className="drilldown-summary">
        <h3>Drilldown summary</h3>
        {drilldownAvailability ? (
          <p className="small">
            {drilldownAvailability.available}/
            {drilldownAvailability.totalClusters} ready ·
            Missing: {drilldownAvailability.missingClusters.join(", ") || "none"}
          </p>
        ) : (
          <p className="small">Loading drilldown availability…</p>
        )}
        <div className="drilldown-grid">
          {drilldownCoverage.map((entry) => (
            <article
              className={`drilldown-card ${entry.available ? "available" : "missing"}`}
              key={entry.label}
            >
              <header>
                <strong>{entry.label}</strong>
                <span>{entry.available ? "Ready" : "Missing"}</span>
              </header>
              <p className="small">Context: {entry.context}</p>
              <p className="small">Captured: {entry.timestamp || "pending"}</p>
              {entry.artifactPath ? (
                <a
                  className="link"
                  href={artifactUrl(entry.artifactPath)}
                  target="_blank"
                  rel="noreferrer"
                >
                  View drilldown
                </a>
              ) : null}
            </article>
          ))}
        </div>
      </div>
      <div>
        <h3>Related proposals</h3>
        {relatedProposals.length ? (
          relatedProposals.map((proposal) => (
            <div className="related-card" key={proposal.proposalId}>
              <p className="eyebrow">{proposal.proposalId}</p>
              <p className="small">{proposal.target}</p>
              <span className={statusClass(proposal.status)}>{proposal.status}</span>
            </div>
          ))
        ) : (
          <p className="small muted">No related proposals found.</p>
        )}
      </div>
      <div>
        <h3>Related notifications</h3>
        {relatedNotifications.length ? (
          relatedNotifications.map((notification) => (
            <div className="related-card" key={notification.timestamp + notification.kind}>
              <p className="eyebrow">{notification.kind}</p>
              <p className="small">{notification.summary}</p>
              <span className="small">{formatTimestamp(notification.timestamp)}</span>
            </div>
          ))
        ) : (
          <p className="small muted">No related notifications found.</p>
        )}
      </div>
    </div>
  );
};

export default ClusterRelatedContextSection;
