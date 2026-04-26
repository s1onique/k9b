/**
 * RunKpiStrip.tsx
 *
 * Displays the run KPI cards (Clusters, Degraded, Proposals, Notifications, Drilldowns)
 * and the duration summary.
 * Extracted from RunSummaryPanel (E1-3b-step15).
 */

// Visual anchors for KPI cards - simple text-based indicators
const KPI_ICONS: Record<string, string> = {
  Clusters: "⬡",
  Degraded: "◆",
  Proposals: "▶",
  Notifications: "◎",
  Drilldowns: "→",
  // Default fallback
};

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
            className="run-stat-card kpi-card"
            key={stat.label}
            aria-label={`${stat.label}: ${stat.value}`}
          >
            <div className="kpi-card-inner">
              <div className="kpi-icon" aria-hidden="true">
                {KPI_ICONS[stat.label] || "●"}
              </div>
              <div className="kpi-content">
                <strong className="kpi-value">{stat.value}</strong>
                <span className="kpi-label">{stat.label}</span>
              </div>
            </div>
          </article>
        ))}
      </div>
      <p className="run-duration-summary muted small">{durationSummary}</p>
    </div>
  );
};
