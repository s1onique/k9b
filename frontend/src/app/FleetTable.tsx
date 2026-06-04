/**
 * FleetTable Component
 *
 * Fleet overview table with cluster health information.
 * Extracted from App.tsx to reduce component size.
 */

import { relativeRecency, statusClass, formatTimestamp } from "../utils";
import { isStaleTimestamp } from "../utils/selectors";

export interface FleetCluster {
  label: string;
  healthRating: string;
  latestRunTimestamp: string;
  context: string;
  clusterClass: string;
  clusterRole: string;
  baselineCohort: string;
  topTriggerReason: string | null;
  drilldownAvailable: boolean;
  drilldownTimestamp: string | null;
}

export interface FleetTableProps {
  clusters: FleetCluster[];
  selectedClusterLabel: string | null;
  highlightedClusterLabel: string | null;
  onClusterSelect: (label: string) => void;
}

export function FleetTable({
  clusters,
  selectedClusterLabel,
  highlightedClusterLabel,
  onClusterSelect,
}: FleetTableProps) {
  return (
    <div className="fleet-table">
      <table>
        <thead>
          <tr>
            <th>Cluster</th>
            <th>Rating</th>
            <th>Latest run</th>
            <th>Trigger</th>
            <th>Drilldown</th>
          </tr>
        </thead>
        <tbody>
          {clusters.map((cluster) => {
            const isSelected = cluster.label === selectedClusterLabel;
            const isFleetRowHighlighted = cluster.label === highlightedClusterLabel;
            const clusterRowFresh = !isStaleTimestamp(cluster.latestRunTimestamp);
            const clusterRowRecency = relativeRecency(cluster.latestRunTimestamp);
            return (
              <tr
                key={cluster.label}
                className={
                  [
                    isSelected ? "row-selected" : null,
                    isFleetRowHighlighted ? "highlighted-row" : null,
                  ]
                    .filter(Boolean)
                    .join(" ") || undefined
                }
                data-highlighted={isFleetRowHighlighted ? "true" : undefined}
                onClick={() => onClusterSelect(cluster.label)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onClusterSelect(cluster.label);
                  }
                }}
                tabIndex={0}
              >
                <td>
                  <strong>{cluster.label}</strong>
                  <p className="small compact">{cluster.context}</p>
                  <p className="tiny compact">
                    {cluster.clusterClass}/{cluster.clusterRole} · {cluster.baselineCohort}
                  </p>
                </td>
                <td>
                  <span className={statusClass(cluster.healthRating)}>{cluster.healthRating}</span>
                </td>
                <td>
                  <span className={`recency-pill ${clusterRowFresh ? "fresh" : "stale"}`}>
                    {clusterRowRecency}
                  </span>
                  <p className="small compact">{formatTimestamp(cluster.latestRunTimestamp)}</p>
                </td>
                <td>
                  <p className="small">{cluster.topTriggerReason || "Awaiting trigger"}</p>
                </td>
                <td>
                  <span className="small">
                    {cluster.drilldownAvailable ? "Ready" : "Missing"}
                  </span>
                  <p className="small compact">{cluster.drilldownTimestamp || "pending"}</p>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}