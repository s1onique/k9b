/**
 * AlertmanagerPanel.tsx
 *
 * Contains two exported components extracted from App.tsx (E1-3b-step9):
 *   - AlertmanagerSnapshotPanel: displays the alertmanager compact snapshot
 *     (alert counts, severity/state breakdowns, affected namespaces/services/clusters)
 *   - AlertmanagerSourcesPanel: displays discovered alertmanager sources with
 *     promote / stop-tracking actions and identity debug details
 *
 * Both components are verbatim moves from App.tsx; no logic has been changed.
 * Helpers and constants that are solely used by these components (ALERTMANAGER_STATUS_LABELS,
 * formatAlertmanagerStatus) are co-located here.
 */

import { useMemo, useState } from "react";
import {
  promoteAlertmanagerSource,
  stopTrackingAlertmanagerSource,
} from "../api";
import type { AlertmanagerCompact, AlertmanagerSources } from "../types";
import { formatTimestamp, statusClass } from "../utils";

// ---------------------------------------------------------------------------
// Status label helpers (alertmanager-snapshot only)
// ---------------------------------------------------------------------------

// Status labels for Alertmanager compact capture status.
// These are run-scoped snapshots - wording is chosen to be clear and trustworthy.
const ALERTMANAGER_STATUS_LABELS: Record<string, string> = {
  ok: "Captured",
  available: "Captured",
  "no-artifact": "Not captured",
  empty: "Captured (no alerts)",
  disabled: "Disabled",
  timeout: "Timeout",
  upstream_error: "Upstream error",
  invalid_response: "Invalid response",
};

const formatAlertmanagerStatus = (status: string) =>
  ALERTMANAGER_STATUS_LABELS[status] ?? status.replace(/_/g, " ");

// ---------------------------------------------------------------------------
// AlertmanagerSnapshotPanel
// ---------------------------------------------------------------------------

export type AlertmanagerSnapshotPanelProps = {
  compact: AlertmanagerCompact | undefined | null;
  clusterLabel?: string | null;
};

export const AlertmanagerSnapshotPanel = ({
  compact,
  clusterLabel,
}: AlertmanagerSnapshotPanelProps) => {
  const statusLabel = compact ? formatAlertmanagerStatus(compact.status) : "No data";
  const isAvailable = compact?.status === "available";
  const isOk = compact?.status === "ok";
  const showAlertDetails = compact && (isAvailable || isOk);

  // Derive cluster-specific snapshot when clusterLabel is provided and by_cluster data exists
  const clusterData = useMemo(() => {
    if (!clusterLabel || !compact?.by_cluster) {
      return null;
    }
    return compact.by_cluster.find(c => c.cluster === clusterLabel) ?? null;
  }, [compact, clusterLabel]);

  // Determine display mode: cluster-filtered, run-global, or no-data
  const isClusterFilteredMode = Boolean(clusterLabel && clusterData);
  const isNoClusterDataMode = Boolean(clusterLabel && !clusterData && compact?.by_cluster);
  const isRunGlobalMode = Boolean(!clusterLabel && compact);

  // Use cluster-specific data when available. When cluster data is missing but clusterLabel is set,
  // fall back to run-global alert_count (but not other fields like severity/service which are cluster-specific).
  const alertCount = clusterData?.alert_count ?? compact?.alert_count ?? 0;
  const severityCounts = clusterData?.severity_counts ?? (isRunGlobalMode ? (compact?.severity_counts ?? {}) : {});
  const stateCounts = clusterData?.state_counts ?? (isRunGlobalMode ? (compact?.state_counts ?? {}) : {});
  const topAlertNames = clusterData?.top_alert_names ?? (isRunGlobalMode ? (compact?.top_alert_names ?? []) : []);
  const affectedNamespaces = clusterData?.affected_namespaces ?? (isRunGlobalMode ? (compact?.affected_namespaces ?? []) : []);
  const affectedServices = clusterData?.affected_services ?? (isRunGlobalMode ? (compact?.affected_services ?? []) : []);
  // Only show affected_clusters in run-global mode (it's a run-level field, not cluster-level)
  const showAffectedClusters = isRunGlobalMode && (compact?.affected_clusters?.length ?? 0) > 0;

  // Use alert_count as the primary indicator for whether to show alert data.
  // state_counts.firing is available for additional context but alert_count is authoritative.
  // Note: Alertmanager uses "firing" and "pending" states, but alert_count is the reliable count.
  const hasActiveAlerts = alertCount > 0;

  const displayLabel = isClusterFilteredMode ? clusterLabel : (clusterLabel || "All clusters");

  return (
    <section className="panel alertmanager-snapshot" id="alertmanager-snapshot">
      <div className="section-head">
        <h2>Alertmanager snapshot · {displayLabel}</h2>
        <span className={`status-pill ${statusClass(statusLabel)}`}>
          {statusLabel}
        </span>
      </div>
      {!compact ? (
        <p className="muted small">
          Alertmanager snapshot data is not available for this run.
        </p>
      ) : !isAvailable && !isOk ? (
        <p className="muted small">
          Alertmanager snapshot is not available: {statusLabel.toLowerCase()}.
        </p>
      ) : isNoClusterDataMode ? (
        // Selected cluster has no alerts - show truthful no-data state
        <p className="muted small">
          No alerts captured for cluster &ldquo;{clusterLabel}&rdquo;.
        </p>
      ) : (
        <>
          <p className="muted tiny">
            Captured {compact.captured_at ? formatTimestamp(compact.captured_at) : "—"}
            {compact.truncated ? " · Truncated" : ""}
            {isClusterFilteredMode ? " (cluster-filtered)" : ""}
          </p>
          {hasActiveAlerts ? (
            <div className="alertmanager-snapshot-grid">
              <div className="alertmanager-snapshot-metric">
                <strong className="alertmanager-metric-value">{alertCount}</strong>
                <span className="alertmanager-metric-label">Total alerts</span>
              </div>
              {Object.keys(severityCounts).length > 0 && (
                <div className="alertmanager-snapshot-section">
                  <p className="alertmanager-section-label">By severity</p>
                  <div className="alertmanager-severity-list">
                    {Object.entries(severityCounts).map(([severity, count]) => (
                      <span key={severity} className={`alertmanager-severity-badge alertmanager-severity-badge--${severity.toLowerCase()}`}>
                        {severity}: {count}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {Object.keys(stateCounts).length > 0 && (
                <div className="alertmanager-snapshot-section">
                  <p className="alertmanager-section-label">By state</p>
                  <div className="alertmanager-state-list">
                    {Object.entries(stateCounts).map(([state, count]) => (
                      <span key={state} className="alertmanager-state-badge">
                        {state}: {count}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {topAlertNames.length > 0 && (
                <div className="alertmanager-snapshot-section">
                  <p className="alertmanager-section-label">Top alerts</p>
                  <ul className="alertmanager-top-alerts">
                    {topAlertNames.slice(0, 5).map((name, idx) => (
                      <li key={idx}>{name}</li>
                    ))}
                  </ul>
                </div>
              )}
              {affectedNamespaces.length > 0 && (
                <div className="alertmanager-snapshot-section">
                  <p className="alertmanager-section-label">Affected namespaces ({affectedNamespaces.length})</p>
                  <div className="alertmanager-tag-list">
                    {affectedNamespaces.slice(0, 10).map((ns, idx) => (
                      <span key={idx} className="alertmanager-tag">{ns}</span>
                    ))}
                    {affectedNamespaces.length > 10 && (
                      <span className="alertmanager-tag alertmanager-tag--more">
                        +{affectedNamespaces.length - 10} more
                      </span>
                    )}
                  </div>
                </div>
              )}
              {showAffectedClusters && (
                <div className="alertmanager-snapshot-section">
                  <p className="alertmanager-section-label">Affected clusters ({compact.affected_clusters?.length})</p>
                  <div className="alertmanager-tag-list">
                    {compact.affected_clusters?.map((cluster, idx) => (
                      <span key={idx} className="alertmanager-tag">{cluster}</span>
                    ))}
                  </div>
                </div>
              )}
              {affectedServices.length > 0 && (
                <div className="alertmanager-snapshot-section">
                  <p className="alertmanager-section-label">Affected services ({affectedServices.length})</p>
                  <div className="alertmanager-tag-list">
                    {affectedServices.slice(0, 10).map((svc, idx) => (
                      <span key={idx} className="alertmanager-tag">{svc}</span>
                    ))}
                    {affectedServices.length > 10 && (
                      <span className="alertmanager-tag alertmanager-tag--more">
                        +{affectedServices.length - 10} more
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="muted small">No active alerts captured.</p>
          )}
        </>
      )}
    </section>
  );
};

// ---------------------------------------------------------------------------
// AlertmanagerSourcesPanel
// ---------------------------------------------------------------------------

export type AlertmanagerSourcesPanelProps = {
  sources: AlertmanagerSources;
  runId?: string;
  clusterLabel?: string | null;
  onRefresh?: () => void;
};

/** AlertmanagerSourcesPanel - Display and manage tracked alertmanager sources.
 * Shows summary counts and a table of sources with visual state indicators.
 * 
 * Action semantics by source state:
 * - Discovered/Auto-tracked sources: Show Promote + Stop tracking buttons
 * - Manual sources: Show "Managed manually" badge + Stop tracking button
 *   (Promote is hidden because source is already manual - action is meaningless)
 * - Stop tracking is a persistent destructive action that filters source from future runs
 * 
 * State color mapping:
 * - manual/auto-tracked: green (healthy)
 * - discovered: yellow (caution)
 * - degraded: red (warning)
 * - missing: muted
 */
export const AlertmanagerSourcesPanel = ({
  sources,
  runId,
  clusterLabel,
  onRefresh,
}: AlertmanagerSourcesPanelProps) => {
  // Filter sources by cluster when clusterLabel is provided
  // This prevents cross-cluster bleed-through in the Fleet overview
  const filteredSources = clusterLabel
    ? sources.sources.filter((s) => s.cluster_label === clusterLabel)
    : sources.sources;

  // Track loading state for action buttons
  const [actionLoading, setActionLoading] = useState<Record<string, "promote" | "disable" | null>>({});
  const [actionError, setActionError] = useState<Record<string, string | null>>({});
  const [actionSuccess, setActionSuccess] = useState<Record<string, string | null>>({});

  // Handle promote action
  const handlePromote = async (sourceId: string) => {
    if (!clusterLabel) {
      setActionError((prev) => ({ ...prev, [sourceId]: "No cluster context available" }));
      return;
    }
    if (!runId) {
      setActionError((prev) => ({ ...prev, [sourceId]: "No run context available" }));
      return;
    }
    setActionLoading((prev) => ({ ...prev, [sourceId]: "promote" }));
    setActionError((prev) => ({ ...prev, [sourceId]: null }));
    setActionSuccess((prev) => ({ ...prev, [sourceId]: null }));
    try {
      const response = await promoteAlertmanagerSource({ sourceId, clusterLabel }, runId);
      if (response.status === "success") {
        setActionSuccess((prev) => ({ ...prev, [sourceId]: response.summary || "Source promoted" }));
        if (onRefresh) {
          setTimeout(onRefresh, 500);
        }
      } else {
        setActionError((prev) => ({ ...prev, [sourceId]: response.summary || "Promotion failed" }));
      }
    } catch (err) {
      setActionError((prev) => ({
        ...prev,
        [sourceId]: err instanceof Error ? err.message : "Failed to promote source",
      }));
    } finally {
      setActionLoading((prev) => {
        const next = { ...prev };
        delete next[sourceId];
        return next;
      });
    }
  };

  // Handle stop tracking action
  const handleStopTracking = async (sourceId: string) => {
    if (!clusterLabel) {
      setActionError((prev) => ({ ...prev, [sourceId]: "No cluster context available" }));
      return;
    }
    if (!runId) {
      setActionError((prev) => ({ ...prev, [sourceId]: "No run context available" }));
      return;
    }
    setActionLoading((prev) => ({ ...prev, [sourceId]: "stop_tracking" }));
    setActionError((prev) => ({ ...prev, [sourceId]: null }));
    setActionSuccess((prev) => ({ ...prev, [sourceId]: null }));
    try {
      const response = await stopTrackingAlertmanagerSource({ sourceId, clusterLabel }, runId);
      if (response.status === "success") {
        setActionSuccess((prev) => ({ ...prev, [sourceId]: response.summary || "Stopped tracking source" }));
        if (onRefresh) {
          setTimeout(onRefresh, 500);
        }
      } else {
        setActionError((prev) => ({ ...prev, [sourceId]: response.summary || "Stop tracking failed" }));
      }
    } catch (err) {
      setActionError((prev) => ({
        ...prev,
        [sourceId]: err instanceof Error ? err.message : "Failed to stop tracking source",
      }));
    } finally {
      setActionLoading((prev) => {
        const next = { ...prev };
        delete next[sourceId];
        return next;
      });
    }
  };

  // State color class mapping based on display_state
  const getSourceStateClass = (displayState: string): string => {
    const normalized = (displayState || "").toLowerCase();
    if (normalized === "manual" || normalized === "auto-tracked" || normalized === "tracked") {
      return "alertmanager-source-healthy";
    }
    if (normalized === "discovered") {
      return "alertmanager-source-caution";
    }
    if (normalized === "degraded") {
      return "alertmanager-source-warning";
    }
    if (normalized === "missing") {
      return "alertmanager-source-muted";
    }
    return "alertmanager-source-default";
  };

  // Truncate long text for table cells
  const truncateSourceCell = (value: string | null | undefined, maxLength = 80): string => {
    if (!value) return "—";
    return value.length <= maxLength ? value : `${value.slice(0, maxLength).trim()}…`;
  };

  // Derive summary counts from filtered sources when clusterLabel is provided
  const summaryItems = clusterLabel
    ? [
        { label: "Total", value: filteredSources.length },
        { label: "Tracked", value: filteredSources.filter((s) => s.display_state?.toLowerCase() === "auto-tracked" || s.display_state?.toLowerCase() === "tracked").length },
        { label: "Manual", value: filteredSources.filter((s) => s.display_state?.toLowerCase() === "manual").length },
        { label: "Degraded", value: filteredSources.filter((s) => s.display_state?.toLowerCase() === "degraded").length },
        { label: "Missing", value: filteredSources.filter((s) => s.display_state?.toLowerCase() === "missing").length },
      ]
    : [
        { label: "Total", value: sources.total_count },
        { label: "Tracked", value: sources.tracked_count },
        { label: "Manual", value: sources.manual_count },
        { label: "Degraded", value: sources.degraded_count },
        { label: "Missing", value: sources.missing_count },
      ];

  return (
    <section className="panel alertmanager-sources" id="alertmanager-sources">
      <div className="section-head">
        <h2>Alertmanager sources</h2>
        <span className="muted small">
          {sources.cluster_context ? `Context: ${sources.cluster_context}` : ""}
        </span>
      </div>

      {/* Summary row with counts */}
      <div className="alertmanager-sources-summary">
        {summaryItems.map((item) => (
          <div key={item.label} className="alertmanager-sources-summary-item">
            <strong className="alertmanager-sources-metric-value">{item.value}</strong>
            <span className="alertmanager-sources-metric-label">{item.label}</span>
          </div>
        ))}
      </div>

      {/* Discovery timestamp */}
      {sources.discovery_timestamp && (
        <p className="muted tiny alertmanager-sources-timestamp">
          Discovered {formatTimestamp(sources.discovery_timestamp)}
        </p>
      )}

      {/* Sources table - show filtered when clusterLabel is provided, else show all */}
      {filteredSources.length > 0 ? (
        <div className="alertmanager-sources-table-wrapper">
          <table className="alertmanager-sources-table">
            <thead>
              <tr>
                <th>State</th>
                <th>Origin</th>
                <th>Endpoint</th>
                <th>Namespace / Name</th>
                <th>Version</th>
                <th>Provenance</th>
                <th>Cluster</th>
                <th>Actions</th>
                <th>Last Error</th>
                <th>Identity</th>
              </tr>
            </thead>
            <tbody>
              {filteredSources.map((source) => {
                const stateClass = getSourceStateClass(source.display_state);
                const namespaceName = [source.namespace, source.name]
                  .filter(Boolean)
                  .join(" / ") || "—";
                const isLoading = actionLoading[source.source_id] != null;
                const error = actionError[source.source_id];
                const success = actionSuccess[source.source_id];

                // Derive display label for state pill:
                // - Use distinct labels when manual_source_mode is present
                // - Fall back to display_state for legacy artifacts (manual_source_mode is null)
                const stateLabel = (() => {
                  if (source.manual_source_mode === "operator-configured") {
                    return "Configured manually";
                  }
                  if (source.manual_source_mode === "operator-promoted") {
                    return "Promoted";
                  }
                  return source.display_state || source.state || "unknown";
                })();

                return (
                  <tr key={source.source_id} className={`alertmanager-source-row ${stateClass}`}>
                    <td>
                      <span className={`alertmanager-source-state-pill alertmanager-source-state-pill-${stateClass}`}>
                        {stateLabel}
                      </span>
                    </td>
                    <td className="alertmanager-source-origin">
                      {truncateSourceCell(source.display_origin || source.origin)}
                    </td>
                    <td className="alertmanager-source-endpoint">
                      <code 
                        className="alertmanager-source-endpoint-code clickable"
                        title={`Copy: ${source.endpoint}`}
                        onClick={() => {
                          navigator.clipboard.writeText(source.endpoint).catch(() => {
                            // Fallback for older browsers
                            const textArea = document.createElement('textarea');
                            textArea.value = source.endpoint;
                            document.body.appendChild(textArea);
                            textArea.select();
                            document.execCommand('copy');
                            document.body.removeChild(textArea);
                          });
                        }}
                        style={{ cursor: 'pointer' }}
                      >
                        {truncateSourceCell(source.endpoint, 50)}
                      </code>
                    </td>
                    <td className="alertmanager-source-namespace">
                      {namespaceName}
                    </td>
                    <td className="alertmanager-source-version">
                      {source.verified_version || "—"}
                    </td>
                    <td className="alertmanager-source-provenance" title={source.display_provenance || source.provenance_summary}>
                      <span className="muted tiny">
                        {truncateSourceCell(source.display_provenance || source.provenance_summary, 60)}
                      </span>
                    </td>
                    <td className="alertmanager-source-cluster">
                      {source.cluster_label || "—"}
                    </td>
                    <td className="alertmanager-source-actions">
                      <div className="alertmanager-source-action-buttons">
                        {/* Determine action label: manual_source_mode-first, then display_state fallback */}
                        {source.manual_source_mode === "operator-promoted" ? (
                          <span className="alertmanager-managed-badge">Promoted</span>
                        ) : source.manual_source_mode === "operator-configured" ? (
                          <span className="alertmanager-managed-badge">Managed manually</span>
                        ) : source.display_state?.toLowerCase() === "manual" ? (
                          <span className="alertmanager-managed-badge">Managed manually</span>
                        ) : (
                          <button
                            type="button"
                            className="button primary tiny alertmanager-action-btn"
                            onClick={() => handlePromote(source.source_id)}
                            disabled={isLoading || !source.can_promote}
                            title={source.can_promote ? "Promote to manual tracking" : "Cannot promote this source"}
                          >
                            {isLoading && actionLoading[source.source_id] === "promote" ? "…" : "Promote"}
                          </button>
                        )}
                        <button
                          type="button"
                          className="button secondary tiny alertmanager-action-btn"
                          onClick={() => handleStopTracking(source.source_id)}
                          disabled={isLoading || !source.can_disable}
                          title={source.can_disable ? "Stop tracking this source (filters it from future runs)" : "Cannot stop tracking this source"}
                        >
                          {isLoading && actionLoading[source.source_id] === "stop_tracking" ? "…" : "Stop tracking"}
                        </button>
                      </div>
                      {error && (
                        <p className="alertmanager-source-action-error">{error}</p>
                      )}
                      {success && (
                        <p className="alertmanager-source-action-success">{success}</p>
                      )}
                    </td>
                    <td className="alertmanager-source-error">
                      {source.last_error ? (
                        <span className="alertmanager-source-error-text" title={source.last_error}>
                          {truncateSourceCell(source.last_error, 40)}
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    {/* Debug/Provenance column - Canonical Identity details */}
                    <td className="alertmanager-source-identity">
                      {(source.canonicalEntityId || source.cluster_uid || source.object_uid) ? (
                        <details className="alertmanager-source-identity-details">
                          <summary className="alertmanager-source-identity-toggle" title="View debug identity">
                            <span className="alertmanager-source-identity-icon">⧉</span>
                          </summary>
                          <div className="alertmanager-source-identity-content">
                            <p className="alertmanager-source-identity-explanation muted tiny">
                              Deterministic identity for historical/debug tracking
                            </p>
                            {source.canonicalEntityId && (
                              <div className="alertmanager-source-identity-field">
                                <span className="alertmanager-source-identity-label">Canonical ID:</span>
                                <code className="alertmanager-source-identity-value" title={source.canonicalEntityId}>
                                  {truncateSourceCell(source.canonicalEntityId, 32)}
                                </code>
                              </div>
                            )}
                            {source.cluster_uid && (
                              <div className="alertmanager-source-identity-field">
                                <span className="alertmanager-source-identity-label">Cluster UID:</span>
                                <code className="alertmanager-source-identity-value" title={source.cluster_uid}>
                                  {truncateSourceCell(source.cluster_uid, 32)}
                                </code>
                              </div>
                            )}
                            {source.object_uid && (
                              <div className="alertmanager-source-identity-field">
                                <span className="alertmanager-source-identity-label">Object UID:</span>
                                <code className="alertmanager-source-identity-value" title={source.object_uid}>
                                  {truncateSourceCell(source.object_uid, 32)}
                                </code>
                              </div>
                            )}
                            <p className="alertmanager-source-identity-note tiny muted">
                              IDs may differ across runs when anchor capture differs
                            </p>
                          </div>
                        </details>
                      ) : (
                        <span className="muted tiny">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted small">
          {clusterLabel
            ? `No alertmanager sources found for cluster "${clusterLabel}".`
            : "No alertmanager sources discovered for this run."}
        </p>
      )}
    </section>
  );
};
