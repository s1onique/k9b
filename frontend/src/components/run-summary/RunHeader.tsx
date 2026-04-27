/**
 * RunHeader.tsx
 *
 * Displays the run header as a compact two-row card header.
 * Aligns with peer card header rhythm: kicker, title, metadata.
 *
 * Target structure:
 * Top row:    RUN SUMMARY                           Collector 0.0.0 · Apr 27, 2026 16:20 UTC
 * Second row: health-run-20260427T161756Z
 */

import { formatTimestamp } from "../../utils";

export interface RunHeaderProps {
  /** Run display label (run id) */
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
    <header className="run-summary-header">
      <div className="run-summary-header-row">
        <span className="run-summary-kicker">Run summary</span>
        <div className="run-summary-meta">
          <span className="run-summary-collector">Collector {collectorVersion}</span>
          <span aria-hidden="true">·</span>
          <time className="run-summary-time" dateTime={timestamp}>
            {formatTimestamp(timestamp)}
          </time>
        </div>
      </div>

      <h2 className="run-summary-title">{label}</h2>
    </header>
  );
};
