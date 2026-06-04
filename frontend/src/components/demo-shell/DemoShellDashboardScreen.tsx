/**
 * Demo Shell Dashboard Screen Component
 *
 * Shows real context summary and findings list.
 * Uses real cluster/run info instead of fake cluster names.
 */

import type { DemoFinding, DemoShellRealContext, EvidenceSource } from "./DemoShellTypes";
import { EvidenceSourceBadge } from "./DemoShellBadges";
import { SafetyModeLabel } from "./DemoShellBadges";
import { SeverityBadge } from "./DemoShellBadges";
import { getFreshnessLabel } from "./DemoShellData";

interface DashboardScreenProps {
  /** Real context metadata when launched from the main app */
  realContext?: DemoShellRealContext;
  /** Selected findings from demo finding selection */
  findings?: DemoFinding[];
  /** Evidence source for the findings */
  evidenceSource?: EvidenceSource;
  /** Human-readable explanation from selection */
  explanation?: string;
  onSelectFinding: (finding: DemoFinding) => void;
  onCleanClusterFallback: () => void;
  isCleanCluster: boolean;
}

/**
 * Format a run ID for display (truncate if too long)
 */
function formatRunId(runId: string | undefined): string {
  if (!runId) return "—";
  if (runId.length <= 12) return runId;
  return `${runId.slice(0, 8)}...`;
}

export const DashboardScreen = ({
  realContext,
  findings = [],
  evidenceSource = "none",
  explanation,
  onSelectFinding,
  onCleanClusterFallback,
  isCleanCluster,
}: DashboardScreenProps) => {
  const hasRealContext = Boolean(realContext?.runId);

  // Use provided findings or show placeholder if empty
  const displayFindings =
    findings.length > 0
      ? findings
      : [
          {
            id: "placeholder-empty",
            title: "No live finding selected yet",
            severity: "info" as const,
            affectedResource: "—",
            evidenceSource: "none" as const,
            probableCause: "Select a finding from live health run or historical evidence",
            diagnosticEvidence: "Waiting for live health run",
            recommendedAction: "Connect cluster to start diagnostic collection",
            safetyMode: "read-only" as const,
          },
        ];

  // Determine evidence source for badge
  const badgeSource = findings.length > 0 ? evidenceSource : "none";

  // Determine display name - use real cluster label or placeholder
  const displayClusterName = realContext?.clusterLabel ?? (hasRealContext ? "Selected cluster" : "—");

  return (
    <div className="demo-screen demo-screen--dashboard">
      <div className="demo-dashboard-header">
        <div className="demo-cluster-info">
          <h2 className="demo-cluster-name" data-testid="demo-cluster-name">
            {displayClusterName}
          </h2>
          <span className={`demo-status-indicator ${isCleanCluster ? "demo-status--healthy" : "demo-status--connected"}`}>
            {isCleanCluster ? "Healthy" : "Connected"}
          </span>
        </div>
        <div className="demo-dashboard-meta">
          {/* Show real context badges when available */}
          {hasRealContext ? (
            <>
              <span
                className={`demo-badge demo-badge--freshness ${realContext.isFresh ? "demo-badge--fresh" : "demo-badge--stale"}`}
                data-testid="demo-context-badge"
              >
                {getFreshnessLabel(realContext.isFresh)}
              </span>
              <span className="demo-badge demo-badge--run-id" data-testid="demo-run-id-badge">
                Run {formatRunId(realContext.runId)}
              </span>
            </>
          ) : (
            <EvidenceSourceBadge source={isCleanCluster ? "none" : "live"} />
          )}
          <SafetyModeLabel mode="read-only" />
        </div>
      </div>

      {/* Real context detail section */}
      {hasRealContext && (
        <div className="demo-context-detail" data-testid="demo-context-detail">
          <div className="demo-context-item">
            <span className="demo-context-item-label">Run ID</span>
            <span className="demo-context-item-value">{realContext.runId}</span>
          </div>
          {realContext.clusterLabel && (
            <div className="demo-context-item">
              <span className="demo-context-item-label">Cluster</span>
              <span className="demo-context-item-value">{realContext.clusterLabel}</span>
            </div>
          )}
          <div className="demo-context-item">
            <span className="demo-context-item-label">State</span>
            <span className={`demo-context-item-value ${realContext.isFresh ? "demo-context-item-value--fresh" : "demo-context-item-value--stale"}`}>
              {getFreshnessLabel(realContext.isFresh)}
            </span>
          </div>
          {explanation && (
            <div className="demo-context-item demo-context-item--full">
              <span className="demo-context-item-label">Findings</span>
              <span className="demo-context-item-value">{explanation}</span>
            </div>
          )}
        </div>
      )}

      <div className="demo-dashboard-content">
        {isCleanCluster ? (
          <div className="demo-clean-cluster">
            <div className="demo-empty-state">
              <p className="demo-empty-title">No critical issues found</p>
              <p className="demo-empty-message">
                This cluster is currently healthy. No fake incidents were injected for this demo.
              </p>
              <div className="demo-empty-actions">
                <button
                  type="button"
                  className="demo-button demo-button--secondary"
                  onClick={onCleanClusterFallback}
                  data-testid="demo-view-historical-button"
                >
                  View historical real evidence
                </button>
              </div>
              <p className="demo-empty-note">
                Prefer to show real issues, but healthy is honest evidence of good operations.
              </p>
            </div>
          </div>
        ) : (
          <div className="demo-finding-feed">
            <h3 className="demo-section-title">Findings</h3>
            <p className="demo-section-hint">
              Live health run evidence · Click to view analysis
            </p>
            <div className="demo-finding-list">
              {displayFindings.map((finding) => (
                <button
                  type="button"
                  key={finding.id}
                  className="demo-finding-card"
                  onClick={() => onSelectFinding(finding)}
                  data-testid={`demo-finding-card-${finding.id}`}
                >
                  <div className="demo-finding-card-header">
                    <SeverityBadge severity={finding.severity} />
                    <EvidenceSourceBadge source={finding.evidenceSource} />
                  </div>
                  <p className="demo-finding-card-title">{finding.title}</p>
                  <p className="demo-finding-card-resource">{finding.affectedResource}</p>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="demo-dashboard-footer">
        <p className="demo-footer-note">
          {hasRealContext
            ? `Real run evidence · Run ${formatRunId(realContext.runId)} · ${getFreshnessLabel(realContext.isFresh)}`
            : `Evidence source: ${isCleanCluster ? "No findings" : "Live scan"} · Last scan: Just now`}
        </p>
      </div>
    </div>
  );
};
