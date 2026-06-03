/**
 * Demo Shell Dashboard Screen Component
 *
 * Shows cluster connection status and findings list.
 */

import type { DemoFinding } from "./DemoShellTypes";
import { EvidenceSourceBadge } from "./DemoShellBadges";
import { SafetyModeLabel } from "./DemoShellBadges";
import { SeverityBadge } from "./DemoShellBadges";

interface DashboardScreenProps {
  clusterName: string;
  onSelectFinding: (finding: DemoFinding) => void;
  onCleanClusterFallback: () => void;
  isCleanCluster: boolean;
}

export const DashboardScreen = ({
  clusterName,
  onSelectFinding,
  onCleanClusterFallback,
  isCleanCluster,
}: DashboardScreenProps) => {
  // Placeholder findings for demo shell - no fake data, just UI structure
  const placeholderFindings: DemoFinding[] = [
    {
      id: "placeholder-1",
      title: "No live finding selected yet",
      severity: "info",
      affectedResource: "—",
      evidenceSource: "none",
      probableCause: "Select a finding from live health run or historical evidence",
      diagnosticEvidence: "Waiting for live health run",
      recommendedAction: "Connect cluster to start diagnostic collection",
      safetyMode: "read-only",
    },
  ];

  return (
    <div className="demo-screen demo-screen--dashboard">
      <div className="demo-dashboard-header">
        <div className="demo-cluster-info">
          <h2 className="demo-cluster-name">{clusterName}</h2>
          <span className={`demo-status-indicator ${isCleanCluster ? "demo-status--healthy" : "demo-status--connected"}`}>
            {isCleanCluster ? "Healthy" : "Connected"}
          </span>
        </div>
        <div className="demo-dashboard-meta">
          <EvidenceSourceBadge source={isCleanCluster ? "none" : "live"} />
          <SafetyModeLabel mode="read-only" />
        </div>
      </div>

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
              {placeholderFindings.map((finding) => (
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
          Evidence source: {isCleanCluster ? "No findings" : "Live scan"} · Last scan: Just now
        </p>
      </div>
    </div>
  );
};