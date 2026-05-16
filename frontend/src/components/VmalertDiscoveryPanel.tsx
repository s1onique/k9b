/**
 * VmalertDiscoveryPanel.tsx
 *
 * Compact operator-visible surface for VictoriaMetrics vmalert discovery status.
 * Follows the same visual treatment as AlertmanagerSnapshotPanel for consistency.
 *
 * Behavior:
 * - If vmalertSources is null: show nothing (quiet null-state, matching Alertmanager convention)
 * - If source_count == 0: show a neutral "vmalert not discovered" state (not an error)
 * - If source_count > 0: show "vmalert discovered" with the count
 * - If discovered_but_unverified_count > 0: show "discovered, unverified" clearly but non-fatally
 *
 * Actions (promote/disable) are out of scope for this slice - visibility only.
 */

import type { VmalertSources } from "../types/vmalert";

// Status labels for vmalert discovery status
const VMALERT_STATUS_LABELS: Record<string, string> = {
  discovered: "Discovered",
  "discovered-but-unverified": "Discovered (unverified)",
  "auto-tracked": "Auto-tracked",
  manual: "Manual",
  degraded: "Degraded",
  missing: "Missing",
};

const formatVmalertStatus = (status: string) =>
  VMALERT_STATUS_LABELS[status] ?? status.replace(/-/g, " ");

export type VmalertDiscoveryPanelProps = {
  vmalertSources: VmalertSources | undefined | null;
};

export const VmalertDiscoveryPanel = ({
  vmalertSources,
}: VmalertDiscoveryPanelProps) => {
  // Null state: show nothing (matching Alertmanager convention for no-data)
  if (vmalertSources == null) {
    return null;
  }

  const { source_count, discovered_count, discovered_but_unverified_count, auto_tracked_count, manual_count } = vmalertSources;

  // Derive primary status for display
  // Priority: manual > auto-tracked > discovered-but-unverified > discovered
  let primaryStatus: string;
  let primaryCount: number;

  if (manual_count > 0) {
    primaryStatus = "manual";
    primaryCount = manual_count;
  } else if (auto_tracked_count > 0) {
    primaryStatus = "auto-tracked";
    primaryCount = auto_tracked_count;
  } else if (discovered_but_unverified_count > 0) {
    primaryStatus = "discovered-but-unverified";
    primaryCount = discovered_but_unverified_count;
  } else if (discovered_count > 0) {
    primaryStatus = "discovered";
    primaryCount = discovered_count;
  } else {
    primaryStatus = "not-discovered";
    primaryCount = 0;
  }

  const statusLabel = formatVmalertStatus(primaryStatus);
  const hasSources = source_count > 0;
  const hasUnverified = discovered_but_unverified_count > 0;

  // Status pill class based on state
  const getStatusPillClass = (): string => {
    const normalized = primaryStatus.toLowerCase();
    if (normalized === "manual" || normalized === "auto-tracked") {
      return "status-pill status-pill--success";
    }
    if (normalized === "discovered-but-unverified" || normalized === "discovered") {
      return "status-pill status-pill--warning";
    }
    if (normalized === "degraded" || normalized === "missing") {
      return "status-pill status-pill--error";
    }
    return "status-pill";
  };

  return (
    <section className="panel vmalert-discovery" id="vmalert-discovery">
      <div className="section-head">
        <h2>vmalert discovery</h2>
        {hasSources ? (
          <span className={getStatusPillClass()}>
            {statusLabel} · {primaryCount}
          </span>
        ) : (
          <span className="muted small">Not discovered</span>
        )}
      </div>

      {!hasSources ? (
        // Zero sources: neutral quiet state, not an error
        <p className="muted small">
          No vmalert sources discovered for this run.
        </p>
      ) : (
        <>
          {/* Summary counts */}
          <div className="vmalert-discovery-summary">
            {manual_count > 0 && (
              <div className="vmalert-discovery-metric">
                <strong className="vmalert-discovery-metric-value">{manual_count}</strong>
                <span className="vmalert-discovery-metric-label">Manual</span>
              </div>
            )}
            {auto_tracked_count > 0 && (
              <div className="vmalert-discovery-metric">
                <strong className="vmalert-discovery-metric-value">{auto_tracked_count}</strong>
                <span className="vmalert-discovery-metric-label">Auto-tracked</span>
              </div>
            )}
            {discovered_count > 0 && (
              <div className="vmalert-discovery-metric">
                <strong className="vmalert-discovery-metric-value">{discovered_count}</strong>
                <span className="vmalert-discovery-metric-label">Discovered</span>
              </div>
            )}
          </div>

          {/* Unverified warning - non-fatal but visible */}
          {hasUnverified && (
            <p className="muted tiny vmalert-discovery-unverified-note">
              <span className="vmalert-discovery-unverified-indicator">⚠</span>
              {discovered_but_unverified_count} source{discovered_but_unverified_count !== 1 ? "s" : ""} discovered but unverified
            </p>
          )}
        </>
      )}
    </section>
  );
};