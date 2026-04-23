/**
 * ClusterDetailSection Component
 *
 * Renders the cluster detail panel with findings, hypotheses, next checks,
 * drilldown coverage, related proposals, and notification references.
 *
 * Extracted from App.tsx as part of the second-pass decomposition effort.
 * Queue state and execution state ownership remain in App.tsx.
 * Sub-slices:
 * - "Next check plan" → ClusterNextCheckPlanSection.tsx
 * - "Related context" (drilldown, proposals, notifications) → ClusterRelatedContextSection.tsx
 */

import type {
  ClusterDetailPayload,
  ClusterSummary,
  FleetPayload,
  ArtifactLink,
} from "../types";
import { EvidenceDetails } from "./EvidenceDetails";
import { ClusterNextCheckPlanSection } from "./ClusterNextCheckPlanSection";
import type { ClusterNextCheckPlanSectionProps } from "./ClusterNextCheckPlanSection";
import { ClusterRelatedContextSection } from "./ClusterRelatedContextSection";
import type { ClusterRelatedContextSectionProps } from "./ClusterRelatedContextSection";

// Re-export execution/approval result types for App.tsx consumers
export type { ExecutionErrorResult, ExecutionResult, ApprovalResult } from "./ClusterNextCheckPlanSection";

// =============================================================================
// Helper functions (duplicated from App.tsx for render extraction)
// =============================================================================

/**
 * Build the recommended artifacts list for cluster detail display.
 * Collects from assessment, cluster artifacts, and drilldown coverage.
 */
const buildClusterRecommendedArtifacts = (detail?: ClusterDetailPayload) => {
  if (!detail) {
    return [];
  }
  const seen = new Map<string, ArtifactLink>();
  const add = (artifact: ArtifactLink | null | undefined) => {
    if (!artifact || !artifact.path) {
      return;
    }
    if (seen.has(artifact.path)) {
      return;
    }
    seen.set(artifact.path, artifact);
  };
  if (detail.assessment?.artifactPath) {
    add({ label: "Assessment artifact", path: detail.assessment.artifactPath });
  }
  detail.artifacts.forEach((artifact) => add(artifact));
  detail.drilldownCoverage.forEach((entry) => {
    if (entry.available && entry.artifactPath) {
      add({ label: `${entry.label} drilldown`, path: entry.artifactPath });
    }
  });
  return Array.from(seen.values()).slice(0, 3);
};

const safetyClass = (value?: string) => {
  const normalized = value ? value.replace(/[^a-z0-9]+/gi, "-").toLowerCase() : "";
  return `safety-pill ${normalized ? `safety-pill-${normalized}` : ""}`.trim();
};

// =============================================================================
// Props Contract
// =============================================================================

export interface ClusterDetailSectionProps {
  // Data
  clusterDetail: ClusterDetailPayload | null;
  selectedClusterLabel: string | null;
  selectedCluster: ClusterSummary | null;
  fleet: FleetPayload;

  // UI state
  activeTab: string;
  setActiveTab: (tab: "findings" | "hypotheses" | "checks") => void;
  clusterDetailExpanded: boolean;
  setClusterDetailExpanded: (open: boolean) => void;
  highlightedClusterLabel: string | null;

  // Derived display values
  clusterTriggerReason: string;
  drilldownSummary: string;
  recencyTimestamp: string;
  clusterFresh: boolean;
  clusterRecency: string | null;

  // Handlers
  handleClusterSelection: (label: string, options?: { expand?: boolean }) => void;

  // Helpers
  artifactUrl: (path: string) => string | null;
  formatTimestamp: (ts: string) => string;
  statusClass: (status: string) => string;

  // Next check plan sub-slice - delegated to ClusterNextCheckPlanSection
  // These props are forwarded directly to the sub-component
  nextCheckPlanSectionProps: Omit<ClusterNextCheckPlanSectionProps, never>;
}

// =============================================================================
// Component
// =============================================================================

export const ClusterDetailSection: React.FC<ClusterDetailSectionProps> = ({
  clusterDetail,
  selectedClusterLabel,
  selectedCluster,
  fleet,
  activeTab,
  setActiveTab,
  clusterDetailExpanded,
  setClusterDetailExpanded,
  highlightedClusterLabel,
  clusterTriggerReason,
  drilldownSummary,
  recencyTimestamp,
  clusterFresh,
  clusterRecency,
  handleClusterSelection,
  artifactUrl,
  formatTimestamp,
  statusClass,
  nextCheckPlanSectionProps,
}) => {
  const recommendedArtifacts = buildClusterRecommendedArtifacts(clusterDetail);

  return (
    <section
      className={`panel${highlightedClusterLabel === selectedClusterLabel ? " cluster-highlighted-panel" : ""}`}
      id="cluster"
      data-highlighted={highlightedClusterLabel === selectedClusterLabel ? "true" : undefined}
    >
      <div className="section-head">
        <h2>Cluster detail</h2>
        <div className="cluster-controls">
          <label>
            Cluster
            <select
              value={selectedClusterLabel ?? ""}
              onChange={(event) => handleClusterSelection(event.target.value)}
            >
              {fleet.clusters.length ? (
                fleet.clusters.map((cluster) => (
                  <option key={cluster.label} value={cluster.label}>
                    {cluster.label} · {cluster.context}
                  </option>
                ))
              ) : (
                <option value="">No clusters configured</option>
              )}
            </select>
          </label>
        </div>
      </div>
      <details
        className="cluster-detail-panel"
        open={clusterDetailExpanded}
        onToggle={(event) => setClusterDetailExpanded(event.currentTarget.open)}
      >
        <summary>
          <div className="cluster-detail-summary">
            <div>
              <p className="eyebrow">Selected cluster</p>
              <strong>
                {clusterDetail?.selectedClusterLabel || selectedClusterLabel || "Cluster"}
              </strong>
              <p className="small compact">
                {selectedCluster?.context || clusterDetail?.selectedClusterContext || "Context unknown"}
              </p>
            </div>
            <div className="cluster-detail-summary-meta">
              <span
                className={statusClass(
                  clusterDetail?.assessment?.healthRating ?? selectedCluster?.healthRating ?? "pending"
                )}
              >
                {clusterDetail?.assessment?.healthRating ?? selectedCluster?.healthRating ?? "Pending"}
              </span>
              <span className={`recency-pill ${clusterFresh ? "fresh" : "stale"}`}>
                {clusterRecency ?? "Awaiting run"}
              </span>
            </div>
          </div>
          <div className="cluster-detail-summary-grid">
            <article className="cluster-summary-card">
              <p className="eyebrow">Current health state</p>
              <span
                className={statusClass(
                  clusterDetail?.assessment?.healthRating ?? selectedCluster?.healthRating ?? "pending"
                )}
              >
                {clusterDetail?.assessment?.healthRating ?? selectedCluster?.healthRating ?? "Pending"}
              </span>
              <p className="small">
                Missing evidence: {clusterDetail?.assessment?.missingEvidence.join(", ") || "none"}
              </p>
            </article>
            <article className="cluster-summary-card">
              <p className="eyebrow">Top problem</p>
              <strong>{clusterDetail?.topProblem?.title || "Awaiting problem"}</strong>
              <p className="small">
                {clusterDetail?.topProblem?.detail || "Control plane assessments are still running."}
              </p>
            </article>
            <article className="cluster-summary-card">
              <p className="eyebrow">Trigger / drilldown reason</p>
              <p className="small">{clusterTriggerReason}</p>
              <p className="small">{drilldownSummary}</p>
            </article>
            <article className="cluster-summary-card">
              <p className="eyebrow">Recency & freshness</p>
              <span className={`recency-pill ${clusterFresh ? "fresh" : "stale"}`}>
                {clusterRecency ?? "Awaiting run"}
              </span>
              <p className="small">{recencyTimestamp}</p>
            </article>
          </div>
          <div className="cluster-detail-summary-artifacts">
            <p className="eyebrow">Recommended artifacts</p>
            {recommendedArtifacts.length ? (
              <div className="artifact-strip">
                {recommendedArtifacts.map((artifact) => {
                  const url = artifactUrl(artifact.path);
                  return (
                    url && (
                      <a
                        key={`${artifact.label}-${artifact.path}`}
                        className="artifact-link cluster-summary-artifact-link"
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {artifact.label}
                      </a>
                    )
                  );
                })}
              </div>
            ) : (
              <p className="small muted">Artifacts are being captured; check back once collection finishes.</p>
            )}
          </div>
          <p className="small muted">Tap to expand findings, hypotheses, and next checks</p>
        </summary>
        <div className="cluster-detail-body">
          {clusterDetail ? (
            <>
              <div className="cluster-assessment">
                <div className="cluster-assessment-heading">
                  <div>
                    <p className="eyebrow">Deterministic evidence</p>
                    <h3>{clusterDetail.selectedClusterLabel || "Cluster"}</h3>
                    {clusterDetail.selectedClusterContext ? (
                      <p className="small">{clusterDetail.selectedClusterContext}</p>
                    ) : null}
                  </div>
                </div>
                {clusterDetail.assessment ? (
                  <div className="assessment-meta">
                    <span className={statusClass(clusterDetail.assessment.healthRating)}>
                      {clusterDetail.assessment.healthRating}
                    </span>
                    <p className="small">
                      Missing evidence: {clusterDetail.assessment.missingEvidence.join(", ") || "none"}
                    </p>
                    <p className="small">
                      Confidence: {clusterDetail.assessment.overallConfidence || "unknown"}
                    </p>
                    {clusterDetail.assessment.artifactPath ? (
                      <a
                        className="link"
                        href={artifactUrl(clusterDetail.assessment.artifactPath)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        View assessment artifact
                      </a>
                    ) : null}
                  </div>
                ) : (
                  <p className="muted">No assessment data is available yet.</p>
                )}
                {clusterDetail.artifacts.length ? (
                  <div className="artifact-strip cluster-artifacts">
                    {clusterDetail.artifacts.map((artifact) => {
                      const url = artifactUrl(artifact.path);
                      return (
                        url && (
                          <a
                            key={artifact.label}
                            className="artifact-link"
                            href={url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {artifact.label}
                          </a>
                        )
                      );
                    })}
                  </div>
                ) : null}
                {clusterDetail.recommendedAction ? (
                  <div className="recommended-action">
                    <p className="eyebrow">Recommended action</p>
                    <strong>{clusterDetail.recommendedAction.description}</strong>
                    <p className="small">
                      Safety:
                      <span className={safetyClass(clusterDetail.recommendedAction.safetyLevel)}>
                        {clusterDetail.recommendedAction.safetyLevel}
                      </span>
                    </p>
                    {clusterDetail.recommendedAction.references.length ? (
                      <p className="small">
                        References: {clusterDetail.recommendedAction.references.join(", ")}
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <div className="provider-assisted-block">
                <p className="eyebrow">Provider-assisted advisory</p>
                {clusterDetail.autoInterpretation ? (
                  <div className="llm-interpretation-card">
                    <h3>LLM drilldown interpretation</h3>
                    <p className="small">
                      Adapter: {clusterDetail.autoInterpretation.adapter} · Status:
                      <span className={statusClass(clusterDetail.autoInterpretation.status)}>
                        {clusterDetail.autoInterpretation.status}
                      </span>
                    </p>
                    <p className="small">Captured: {formatTimestamp(clusterDetail.autoInterpretation.timestamp)}</p>
                    {clusterDetail.autoInterpretation.summary ? (
                      <p className="small">{clusterDetail.autoInterpretation.summary}</p>
                    ) : null}
                    {clusterDetail.autoInterpretation.artifactPath ? (
                      <a
                        className="link"
                        href={artifactUrl(clusterDetail.autoInterpretation.artifactPath)!}
                        target="_blank"
                        rel="noreferrer"
                      >
                        View interpretation artifact
                      </a>
                    ) : null}
                    {clusterDetail.autoInterpretation.errorSummary ? (
                      <p className="small muted">Error: {clusterDetail.autoInterpretation.errorSummary}</p>
                    ) : null}
                    {clusterDetail.autoInterpretation.skipReason ? (
                      <p className="small muted">Skipped because {clusterDetail.autoInterpretation.skipReason}</p>
                    ) : null}
                  </div>
                ) : (
                  <p className="muted small">LLM drilldown interpretation not available.</p>
                )}
              </div>
              {/* Next check plan sub-slice - delegated to ClusterNextCheckPlanSection */}
              {nextCheckPlanSectionProps.planCandidates.length ? (
                <ClusterNextCheckPlanSection {...nextCheckPlanSectionProps} />
              ) : null}
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
                    {clusterDetail.findings.map((finding) => (
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
                    ))}
                  </div>
                )}
                {activeTab === "hypotheses" && (
                  <div className="finding-list">
                    {clusterDetail.hypotheses.map((hypothesis) => (
                      <article className="finding-card compact" key={hypothesis.description}>
                        <strong>{hypothesis.description}</strong>
                        <p className="small">
                          Confidence: {hypothesis.confidence} · Layer: {hypothesis.probableLayer}
                        </p>
                        <p className="small">Falsifier: {hypothesis.falsifier}</p>
                      </article>
                    ))}
                  </div>
                )}
                {activeTab === "checks" && (
                  <div className="finding-list">
                    {clusterDetail.nextChecks.map((check) => (
                      <article className="finding-card compact" key={check.description}>
                        <strong>{check.description}</strong>
                        <p className="small">
                          Owner: {check.owner} · Method: {check.method}
                        </p>
                        <p className="small">Evidence: {check.evidenceNeeded.join(", ") || "n/a"}</p>
                      </article>
                    ))}
                  </div>
                )}
              </article>
              {/* Lower supporting-context block - delegated to ClusterRelatedContextSection */}
              <ClusterRelatedContextSection
                drilldownAvailability={clusterDetail.drilldownAvailability}
                drilldownCoverage={clusterDetail.drilldownCoverage}
                relatedProposals={clusterDetail.relatedProposals}
                relatedNotifications={clusterDetail.relatedNotifications}
                artifactUrl={artifactUrl}
                formatTimestamp={formatTimestamp}
                statusClass={statusClass}
              />
            </>
          ) : (
            <p className="muted">Loading cluster evidence…</p>
          )}
        </div>
      </details>
    </section>
  );
};

export default ClusterDetailSection;
