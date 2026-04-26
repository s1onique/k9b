/**
 * RunKpiStrip.tsx
 *
 * Displays the run KPI cards (Clusters, Degraded, Proposals, Notifications, Drilldowns)
 * and the duration summary.
 * Extracted from RunSummaryPanel (E1-3b-step15).
 */

export interface RunKpiStat {
  label: string;
  value: string | number;
}

export interface RunKpiStripProps {
  /** KPI stats to display */
  stats: RunKpiStat[];
  /** Duration summary text (e.g., "Last 32s · Runs 12 · P50 24s") */
  durationSummary: string;
}

export const RunKpiStrip = ({
  stats,
  durationSummary,
}: RunKpiStripProps) => {
  return (
    <div className="run-summary-metrics">
      <div className="run-summary-stats">
        {stats.map((stat) => (
          <article
            className="run-stat-card"
            key={stat.label}
            aria-label={`${stat.label}: ${stat.value}`}
          >
            <strong>{stat.value}</strong>
            <span>{stat.label}</span>
          </article>
        ))}
      </div>
      <p className="run-duration-summary muted small">{durationSummary}</p>
    </div>
  );
};