/**
 * RunHeader.tsx
 *
 * Displays the run header section: run label, collector version, and timestamp.
 * Extracted from RunSummaryPanel (E1-3b-step15).
 */

import { formatTimestamp } from "../../utils";

export interface RunHeaderProps {
  /** Run display label */
  label: string;
  /** Collector version string */
  collectorVersion: string;
  /** ISO timestamp for the run */
  timestamp: string;
}

export const RunHeader = ({
  label,
  collectorVersion,
  timestamp,
}: RunHeaderProps) => {
  return (
    <div className="run-summary-head">
      <div>
        <p className="eyebrow">Run summary</p>
        <h2>{label}</h2>
        <p className="muted tiny run-summary-collector">Collector {collectorVersion}</p>
      </div>
      <div className="run-summary-freshness">
        <p className="muted small">{formatTimestamp(timestamp)}</p>
      </div>
    </div>
  );
};