/**
 * RunHeader.tsx
 *
 * Displays the run header as a single horizontal identity line.
 * Compressed from stacked layout: kicker, run id, collector version, timestamp.
 *
 * Target structure:
 * RUN SUMMARY  health-run-20260427T145704Z  COLLECTOR 0.0.0                  Apr 27, 2026 14:59 UTC
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
      <div className="run-summary-identity">
        <span className="run-summary-kicker">Run summary</span>
        <h2 className="run-summary-title">{label}</h2>
        <span className="run-summary-collector">Collector {collectorVersion}</span>
      </div>
      <time className="run-summary-time" dateTime={timestamp}>
        {formatTimestamp(timestamp)}
      </time>
    </header>
  );
};
