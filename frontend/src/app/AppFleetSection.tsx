/**
 * AppFleetSection Component
 *
 * Fleet overview section with summary cards and cluster table.
 * Extracted from App.tsx to reduce component size.
 */

import { FleetTable } from "./FleetTable";
import type { FleetPayload } from "../types";

export interface AppFleetSectionProps {
  fleet: FleetPayload;
  selectedClusterLabel: string | null;
  highlightedClusterLabel: string | null;
  onClusterSelect: (label: string) => void;
}

export function AppFleetSection({
  fleet,
  selectedClusterLabel,
  highlightedClusterLabel,
  onClusterSelect,
}: AppFleetSectionProps) {
  return (
    <section className="panel" id="fleet">
      <div className="section-head">
        <div>
          <h2>Fleet overview</h2>
          <p className="muted">Top problem: {fleet.topProblem.detail}</p>
        </div>
        <div className="status-badges">
          {fleet.fleetStatus.ratingCounts.map((entry) => (
            <span key={entry.rating} className={`status-badge status-badge--${entry.rating.toLowerCase()}`}>
              {entry.rating} · {entry.count}
            </span>
          ))}
        </div>
      </div>
      <div className="fleet-metrics">
        <article>
          <p className="eyebrow">Pending proposals</p>
          <strong>{fleet.proposalSummary.pending}</strong>
        </article>
        <article>
          <p className="eyebrow">Total proposals</p>
          <strong>{fleet.proposalSummary.total}</strong>
        </article>
      </div>
      <FleetTable
        clusters={fleet.clusters}
        selectedClusterLabel={selectedClusterLabel}
        highlightedClusterLabel={highlightedClusterLabel}
        onClusterSelect={onClusterSelect}
      />
    </section>
  );
}