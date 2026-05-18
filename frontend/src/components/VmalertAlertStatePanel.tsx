/**
 * VmalertAlertStatePanel.tsx
 *
 * Compact operator-visible surface for VictoriaMetrics vmalert alert state.
 * Follows the same visual treatment as VmalertDiscoveryPanel for consistency.
 *
 * Behavior:
 * - If vmalertRuleState is null: show nothing (quiet null-state)
 * - If fetch_error_count > 0: show non-fatal warning about failed sources
 * - If alert_count == 0 and fetched_source_count > 0: show positive "No active alerts" state
 * - If pending_alert_count > 0: show pending count clearly
 * - If firing_alert_count > 0: show firing count clearly
 * - If critical_firing_count > 0: make this visually prominent
 * - Show alerts (priority: critical firing > other firing > pending) with pagination
 *
 * Actions (silence/ack/disable) are out of scope for this slice - visibility only.
 */

import { useState, useEffect, useMemo } from "react";
import type { VmalertRuleState, VmalertRuleStateAlert } from "../types";
import Pagination from "./Pagination";

// Severity ordering for alert display
const SEVERITY_ORDER = ["critical", "warning", "info", "unknown"];

// State ordering for alert display
const STATE_ORDER = ["firing", "pending"];

// Page size for alert list
const PAGE_SIZE = 10;

/**
 * Sort alerts by priority:
 * 1. Critical firing first
 * 2. Other firing (by severity)
 * 3. Pending (by severity)
 * 4. Then by alertname
 */
function sortAlertsByPriority(alerts: VmalertRuleStateAlert[]): VmalertRuleStateAlert[] {
  const severityRank = (sev: string | null): number => {
    const s = (sev ?? "unknown").toLowerCase();
    const idx = SEVERITY_ORDER.indexOf(s);
    return idx >= 0 ? idx : SEVERITY_ORDER.length;
  };

  const stateRank = (state: string): number => {
    const idx = STATE_ORDER.indexOf(state.toLowerCase());
    return idx >= 0 ? idx : STATE_ORDER.length;
  };

  return [...alerts].sort((a, b) => {
    // First by state (firing before pending)
    const stateDiff = stateRank(a.state) - stateRank(b.state);
    if (stateDiff !== 0) return stateDiff;

    // Then by severity
    const sevDiff = severityRank(a.severity) - severityRank(b.severity);
    if (sevDiff !== 0) return sevDiff;

    // Then by alertname
    return a.alertname.localeCompare(b.alertname);
  });
}

/**
 * Get severity CSS class suffix
 */
function severityClass(severity: string | null): string {
  const s = (severity ?? "unknown").toLowerCase();
  return s === "critical" ? "critical" : s === "warning" ? "warning" : "default";
}

export type VmalertAlertStatePanelProps = {
  vmalertRuleState: VmalertRuleState | undefined | null;
};

export const VmalertAlertStatePanel = ({
  vmalertRuleState,
}: VmalertAlertStatePanelProps) => {
  // Null state: show nothing (matching discovery panel convention for no-data)
  if (vmalertRuleState == null) {
    return null;
  }

  const {
    source_count,
    fetched_source_count,
    failed_source_count,
    alert_count,
    firing_alert_count,
    pending_alert_count,
    critical_firing_count,
    alerts,
    fetch_error_count,
  } = vmalertRuleState;

  const hasFetchErrors = fetch_error_count > 0;
  const hasAlerts = alert_count > 0;
  const hasFetchedSources = fetched_source_count > 0;

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);

  // Sort alerts by priority
  const sortedAlerts = useMemo(() => sortAlertsByPriority(alerts), [alerts]);

  // Calculate pagination values
  const totalPages = Math.max(1, Math.ceil(sortedAlerts.length / PAGE_SIZE));
  const startIndex = (currentPage - 1) * PAGE_SIZE;
  const displayedAlerts = sortedAlerts.slice(startIndex, startIndex + PAGE_SIZE);

  // Reset to page 1 when alert data changes
  useEffect(() => {
    setCurrentPage((prevPage) => {
      // If current page exceeds total pages, clamp to last page
      return prevPage > totalPages ? totalPages : 1;
    });
  }, [alert_count, totalPages]);

  // Build the source summary line
  const sourceSummaryParts: string[] = [];
  if (hasFetchedSources) {
    sourceSummaryParts.push(`${fetched_source_count} source${fetched_source_count !== 1 ? "s" : ""}`);
  }
  if (firing_alert_count > 0) {
    sourceSummaryParts.push(`${firing_alert_count} firing`);
  }
  if (pending_alert_count > 0) {
    sourceSummaryParts.push(`${pending_alert_count} pending`);
  }
  if (critical_firing_count > 0) {
    sourceSummaryParts.push(`${critical_firing_count} critical`);
  }
  const sourceSummary = sourceSummaryParts.join(" · ");

  // Determine if pagination controls should be shown
  const showPagination = hasAlerts && totalPages > 1;

  return (
    <section className="panel vmalert-alert-state" id="vmalert-alert-state">
      <div className="section-head">
        <h2>vmalert alert state</h2>
        {hasFetchErrors && (
          <span className="status-pill status-pill--warning">
            Partial
          </span>
        )}
        {!hasAlerts && hasFetchedSources && (
          <span className="status-pill status-pill--success">
            OK
          </span>
        )}
        {critical_firing_count > 0 && (
          <span className="status-pill status-pill--critical">
            {critical_firing_count} critical
          </span>
        )}
      </div>

      {/* Fetch error warning - non-fatal but visible */}
      {hasFetchErrors && (
        <div className="vmalert-alert-state-warning">
          <span className="vmalert-alert-state-warning-icon">⚠</span>
          <p className="vmalert-alert-state-warning-text">
            Could not fetch from {failed_source_count} vmalert source{failed_source_count !== 1 ? "s" : ""}.
            This is non-fatal.
          </p>
        </div>
      )}

      {/* Main content based on alert state */}
      {!hasAlerts && hasFetchedSources ? (
        // No alerts - positive quiet state
        <div className="vmalert-alert-state-healthy">
          <p className="vmalert-alert-state-healthy-title">No active vmalert alerts</p>
          {sourceSummary && (
            <p className="vmalert-alert-state-healthy-meta muted small">
              Fetched from {sourceSummary}
            </p>
          )}
        </div>
      ) : !hasFetchedSources && !hasFetchErrors ? (
        // No data collected yet
        <p className="muted small">
          No vmalert alert state collected for this run.
        </p>
      ) : hasAlerts ? (
        // Has alerts - show summary and list
        <div className="vmalert-alert-state-active">
          {/* Alert summary line */}
          <p className="vmalert-alert-state-summary">
            <strong>{alert_count}</strong> active alert{alert_count !== 1 ? "s" : ""}
            {sourceSummary && (
              <span className="muted"> · {sourceSummary}</span>
            )}
          </p>

          {/* Worklist promotion note when critical firing exists */}
          {critical_firing_count > 0 && (
            <p className="vmalert-alert-state-worklist-note muted tiny">
              Only critical firing alerts are promoted to the operator worklist.
              Other firing and pending alerts are diagnostic context only.
            </p>
          )}

          {/* Compact alert list */}
          <div className="vmalert-alert-state-list">
            <table className="vmalert-alert-state-table">
              <thead>
                <tr>
                  <th>Alert</th>
                  <th>State</th>
                  <th>Severity</th>
                  <th>Namespace</th>
                  <th>Workload</th>
                </tr>
              </thead>
              <tbody>
                {displayedAlerts.map((alert, index) => (
                  <tr
                    key={`${alert.alertname}-${alert.source_endpoint}-${index}`}
                    className={
                      alert.state === "firing" && alert.severity === "critical"
                        ? "vmalert-alert-row--critical"
                        : alert.state === "firing"
                        ? "vmalert-alert-row--firing"
                        : "vmalert-alert-row--pending"
                    }
                  >
                    <td className="vmalert-alert-cell vmalert-alert-cell--name">
                      <span className="vmalert-alert-name">{alert.alertname}</span>
                      {alert.summary && (
                        <span className="vmalert-alert-summary muted tiny">{alert.summary}</span>
                      )}
                    </td>
                    <td className="vmalert-alert-cell">
                      <span className={`vmalert-alert-state-badge vmalert-alert-state-badge--${alert.state.toLowerCase()}`}>
                        {alert.state}
                      </span>
                    </td>
                    <td className="vmalert-alert-cell">
                      <span className={`vmalert-alert-severity-badge vmalert-alert-severity-badge--${severityClass(alert.severity)}`}>
                        {alert.severity ?? "unknown"}
                      </span>
                    </td>
                    <td className="vmalert-alert-cell muted">
                      {alert.namespace ?? "—"}
                    </td>
                    <td className="vmalert-alert-cell muted">
                      {alert.workload ?? alert.pod ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination controls */}
            {showPagination && (
              <Pagination
                currentPage={currentPage}
                totalPages={totalPages}
                totalItems={sortedAlerts.length}
                pageSize={PAGE_SIZE}
                onPageChange={setCurrentPage}
                label="Alerts"
              />
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
};
