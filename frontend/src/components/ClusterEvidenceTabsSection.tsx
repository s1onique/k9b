/**
 * ClusterEvidenceTabsSection Component
 *
 * Renders the tabbed evidence block from ClusterDetailSection:
 * - Findings tab
 * - Hypotheses tab
 * - Next checks tab
 *
 * Extracted from ClusterDetailSection.tsx as part of the second-pass decomposition effort.
 * Tab state (activeTab, setActiveTab) is owned by App.tsx and passed as props.
 * No state ownership changes - this is a purely presentational slice.
 */

import type { ClusterDetailPayload, ArtifactLink } from "../types";
import { EvidenceDetails } from "./EvidenceDetails";

// =============================================================================
// Props Contract
// =============================================================================

export interface ClusterEvidenceTabsSectionProps {
  // Data
  clusterDetail: ClusterDetailPayload;

  // Tab state (owned by App.tsx, forwarded through ClusterDetailSection)
  activeTab: string;
  setActiveTab: (tab: "findings" | "hypotheses" | "checks") => void;

  // Helper
  artifactUrl: (path: string) => string | null;
}

// =============================================================================
// Component
// =============================================================================

export const ClusterEvidenceTabsSection: React.FC<ClusterEvidenceTabsSectionProps> = ({
  clusterDetail,
  activeTab,
  setActiveTab,
  artifactUrl,
}) => {
  const findings = clusterDetail.findings;
  const hypotheses = clusterDetail.hypotheses;
  const nextChecks = clusterDetail.nextChecks;

  return (
    <>
      <div className="tab-list" role="tablist" aria-label="Cluster detail tabs">
        {[
          { id: "findings", label: "Findings" },
          { id: "hypotheses", label: "Hypotheses" },
          { id: "checks", label: "Next checks" },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`tab ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id as "findings" | "hypotheses" | "checks")}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <article className="tab-panel">
        {activeTab === "findings" && (
          <div className="finding-list">
            {findings.length > 0 ? (
              findings.map((finding) => (
                <article className="finding-card" key={`${finding.label}-${finding.context}`}>
                  <header>
                    <div>
                      <strong>
                        {finding.label || "cluster"} · {finding.context || "n/a"}
                      </strong>
                      <p className="muted">
                        Triggers: {finding.triggerReasons.join(", ") || "none"}
                      </p>
                      <p className="small">
                        Warnings: {finding.warningEvents} · Non-running pods: {finding.nonRunningPods}
                      </p>
                    </div>
                    {finding.artifactPath ? (
                      <a
                        className="link"
                        href={artifactUrl(finding.artifactPath)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        View raw evidence
                      </a>
                    ) : null}
                  </header>
                  <EvidenceDetails title="Summary" entries={finding.summaryEntries} />
                  <EvidenceDetails title="Patterns" entries={finding.patternDetails} />
                  {finding.rolloutStatus.length ? (
                    <p className="small">Rollout status: {finding.rolloutStatus.join(", ")}</p>
                  ) : null}
                </article>
              ))
            ) : (
              <p className="muted small">No findings available yet.</p>
            )}
          </div>
        )}
        {activeTab === "hypotheses" && (
          <div className="finding-list">
            {hypotheses.length > 0 ? (
              hypotheses.map((hypothesis) => (
                <article className="finding-card compact" key={hypothesis.description}>
                  <strong>{hypothesis.description}</strong>
                  <p className="small">
                    Confidence: {hypothesis.confidence} · Layer: {hypothesis.probableLayer}
                  </p>
                  <p className="small">Falsifier: {hypothesis.falsifier}</p>
                </article>
              ))
            ) : (
              <p className="muted small">No hypotheses generated yet.</p>
            )}
          </div>
        )}
        {activeTab === "checks" && (
          <div className="finding-list">
            {nextChecks.length > 0 ? (
              nextChecks.map((check) => (
                <article className="finding-card compact" key={check.description}>
                  <strong>{check.description}</strong>
                  <p className="small">
                    Owner: {check.owner} · Method: {check.method}
                  </p>
                  <p className="small">Evidence: {check.evidenceNeeded.join(", ") || "n/a"}</p>
                </article>
              ))
            ) : (
              <p className="muted small">No next checks available yet.</p>
            )}
          </div>
        )}
      </article>
    </>
  );
};

export default ClusterEvidenceTabsSection;
