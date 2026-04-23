/**
 * ClusterDetailSection Component
 *
 * Renders the cluster detail panel with findings, hypotheses, next checks,
 * drilldown coverage, related proposals, and notification references.
 *
 * Extracted from App.tsx as part of the second-pass decomposition effort.
 * Queue state and execution state ownership remain in App.tsx.
 */

import type {
  ClusterDetailPayload,
  ClusterSummary,
  FleetPayload,
  NextCheckPlanCandidate,
  NextCheckOrphanedApproval,
  NextCheckOutcomeCount,
  NextCheckExecutionResponse,
  ArtifactLink,
} from "../types";
import { EvidenceDetails } from "./EvidenceDetails";

// Execution result types - kept inline to avoid circular imports
type ExecutionErrorResult = {
  status: "error";
  summary: string;
  blockingReason?: string | null;
};
type ExecutionResult = NextCheckExecutionResponse | ExecutionErrorResult;

type ApprovalResult = {
  status: "success" | "error";
  summary: string;
  artifactPath?: string | null;
  approvalTimestamp?: string | null;
};

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

const humanizeReason = (value?: string | null) => {
  if (!value) {
    return null;
  }
  return value
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
};

const formatCandidatePriority = (value?: string | null) => {
  const normalized = (value ?? "secondary").toLowerCase();
  return `${normalized.charAt(0).toUpperCase()}${normalized.slice(1)}`;
};

type NextCheckStatusVariant = "safe" | "approval" | "approved" | "duplicate" | "stale";

const determineNextCheckStatusVariant = (
  candidate: NextCheckPlanCandidate
): NextCheckStatusVariant => {
  if (candidate.duplicateOfExistingEvidence) {
    return "duplicate";
  }
  if (candidate.requiresOperatorApproval) {
    if (candidate.approvalStatus === "approved") {
      return "approved";
    }
    if (candidate.approvalStatus === "approval-stale") {
      return "stale";
    }
    return "approval";
  }
  return "safe";
};

const approvalStatusLabels: Record<string, string> = {
  approved: "Approved candidate",
  "approval-required": "Approval needed",
  "approval-stale": "Approval stale",
  "approval-orphaned": "Orphaned approval",
  "not-required": "Safe candidate",
};

const nextCheckStatusLabel = (variant: NextCheckStatusVariant) => {
  switch (variant) {
    case "approval":
      return "Approval needed";
    case "approved":
      return "Approved candidate";
    case "duplicate":
      return "Duplicate / already covered";
    case "stale":
      return "Approval stale";
    default:
      return "Safe candidate";
  }
};

const getPlanStatusLabel = (variant: NextCheckStatusVariant, candidate: NextCheckPlanCandidate) => {
  if (candidate.approvalStatus) {
    const override = approvalStatusLabels[candidate.approvalStatus];
    if (override) {
      return override;
    }
  }
  return nextCheckStatusLabel(variant);
};

const outcomeStatusLabels: Record<string, string> = {
  "executed-success": "Executed (success)",
  "executed-failed": "Executed (failed)",
  "timed-out": "Execution timed out",
  "approval-required": "Awaiting approval",
  approved: "Approved",
  "approval-stale": "Approval stale",
  "approval-orphaned": "Orphaned approval",
  "not-used": "Not used",
  unknown: "Unknown",
};

const outcomeStatusDisplay = (status?: string | null) =>
  outcomeStatusLabels[status ?? "unknown"] || (status ? status : "Unknown");

const outcomeStatusClass = (status?: string | null) =>
  `outcome-pill outcome-pill-${((status ?? "unknown").replace(/[^a-z0-9]+/gi, "-").toLowerCase())}`;

// =============================================================================
// Props Contract
// =============================================================================

export interface ClusterDetailSectionProps {
  // Data
  clusterDetail: ClusterDetailPayload | null;
  selectedClusterLabel: string | null;
  selectedCluster: ClusterSummary | null;
  fleet: FleetPayload;
  planCandidates: NextCheckPlanCandidate[];
  orphanedApprovals: NextCheckOrphanedApproval[];
  planArtifactLink: string | null;
  planSummaryText: string;
  planCandidateCountLabel: string;
  planStatusText: string | null;
  outcomeSummary: NextCheckOutcomeCount[];

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

  // Execution state
  executionResults: Record<string, ExecutionResult>;
  approvalResults: Record<string, ApprovalResult>;
  executingCandidate: string | null;
  approvingCandidate: string | null;

  // Handlers
  handleClusterSelection: (label: string, options?: { expand?: boolean }) => void;
  handleApproveCandidate: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;
  handleManualExecution: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;

  // Helpers
  buildCandidateKey: (candidate: NextCheckPlanCandidate, index: number) => string;
  isManualExecutionAllowed: (candidate: NextCheckPlanCandidate) => boolean;
  artifactUrl: (path: string) => string | null;
  formatTimestamp: (ts: string) => string;
  relativeRecency: (ts: string) => string;
  statusClass: (status: string) => string;
}

// =============================================================================
// Component
// =============================================================================

export const ClusterDetailSection: React.FC<ClusterDetailSectionProps> = ({
  clusterDetail,
  selectedClusterLabel,
  selectedCluster,
  fleet,
  planCandidates,
  orphanedApprovals,
  planArtifactLink,
  planSummaryText,
  planCandidateCountLabel,
  planStatusText,
  outcomeSummary,
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
  executionResults,
  approvalResults,
  executingCandidate,
  approvingCandidate,
  handleClusterSelection,
  handleApproveCandidate,
  handleManualExecution,
  buildCandidateKey,
  isManualExecutionAllowed,
  artifactUrl,
  formatTimestamp,
  relativeRecency,
  statusClass,
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
              {planCandidates.length ? (
                <div className="next-check-plan">
                  <div className="section-head next-check-plan-head">
                    <div>
                      <h3>Next check plan</h3>
                      <p className="muted small">{planSummaryText}</p>
                      <p className="muted tiny">
                        {planCandidateCountLabel}
                        {planStatusText ? ` · ${planStatusText}` : ""}
                      </p>
                      {outcomeSummary.length ? (
                        <div className="next-check-outcome-summary">
                          {outcomeSummary.map((entry) => (
                            <span key={entry.status} className={outcomeStatusClass(entry.status)}>
                              {outcomeStatusDisplay(entry.status)} · {entry.count}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                    {planArtifactLink ? (
                      <a
                        className="link"
                        href={planArtifactLink}
                        target="_blank"
                        rel="noreferrer"
                      >
                        View planner artifact
                      </a>
                    ) : null}
                  </div>
                  {orphanedApprovals.length ? (
                    <div className="next-check-orphaned">
                      <p className="tiny muted">
                        Orphaned approvals · {orphanedApprovals.length} record
                        {orphanedApprovals.length === 1 ? "" : "s"}
                      </p>
                      <ul>
                        {orphanedApprovals.map((approval, orphanIndex) => {
                          const label =
                            approval.candidateDescription || approval.candidateId || "Unknown approval";
                          const recency = approval.approvalTimestamp
                            ? ` · ${relativeRecency(approval.approvalTimestamp)}`
                            : "";
                          const target = approval.targetCluster
                            ? ` · ${approval.targetCluster}`
                            : "";
                          const artifactLink =
                            approval.approvalArtifactPath && artifactUrl(approval.approvalArtifactPath);
                          return (
                            <li key={`${label}-${orphanIndex}`}>
                              <strong>{label}</strong>
                              <p className="tiny muted">
                                {approvalStatusLabels[approval.approvalStatus ?? ""] ?? "Orphaned"}
                                {target}
                                {recency}
                              </p>
                              {artifactLink ? (
                                <a className="link" href={artifactLink} target="_blank" rel="noreferrer">
                                  View approval record
                                </a>
                              ) : null}
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ) : null}
                  <div className="next-check-plan-grid">
                    {planCandidates.map((candidate, index) => {
                      const variant = determineNextCheckStatusVariant(candidate);
                      const statusLabel = getPlanStatusLabel(variant, candidate);
                      const statusClassName = `plan-status-pill plan-status-pill-${variant}`;
                      const priority = (candidate.priorityLabel ?? "secondary").toLowerCase();
                      const displayPriority = formatCandidatePriority(priority);
                      const priorityIndicatorClass = `priority-pill priority-pill-${priority}`;
                      const targetLabel =
                        candidate.targetCluster ||
                        clusterDetail?.selectedClusterLabel ||
                        selectedClusterLabel ||
                        "cluster";
                      const candidateKey = buildCandidateKey(candidate, index);
                      const manualAllowed = isManualExecutionAllowed(candidate);
                      const executionResult = executionResults[candidateKey];
                      const approvalResult = approvalResults[candidateKey];
                      const approvalArtifactPath =
                        approvalResult?.artifactPath ?? candidate.approvalArtifactPath;
                      const approvalArtifactBaseLink =
                        approvalArtifactPath && artifactUrl(approvalArtifactPath);
                      const approvalArtifactLink =
                        approvalArtifactBaseLink && approvalArtifactPath
                          ? `${approvalArtifactBaseLink}#${approvalArtifactPath}`
                          : null;
                      const approvalTimestamp =
                        candidate.approvalTimestamp ?? approvalResult?.approvalTimestamp;
                      const approvalRecency = approvalTimestamp && relativeRecency(approvalTimestamp);
                      const executionBlockingReason =
                        executionResult && executionResult.status !== "success"
                          ? (executionResult as ExecutionErrorResult).blockingReason
                          : null;
                      const rationaleEntries = [
                        {
                          label: "Normalization",
                          value: candidate.normalizationReason,
                        },
                        {
                          label: "Safety",
                          value: candidate.safetyReason,
                        },
                        {
                          label: "Approval",
                          value: candidate.approvalReason,
                        },
                        {
                          label: "Duplicate",
                          value: candidate.duplicateReason,
                        },
                        {
                          label: "Block",
                          value: candidate.blockingReason,
                        },
                      ].filter((entry) => entry.value);
                      return (
                        <article
                          className="next-check-plan-card"
                          key={`${candidate.description}-${index}`}
                        >
                          <header className="next-check-plan-card-header">
                            <div>
                              <p className="tiny muted">
                                Source: {candidate.sourceReason || "Planner advisory"}
                              </p>
                              <strong>{candidate.description}</strong>
                              <span className={priorityIndicatorClass}>
                                Priority: {displayPriority}
                              </span>
                            </div>
                            <span className={statusClassName}>{statusLabel}</span>
                          </header>
                          <div className="next-check-plan-meta">
                            <div>
                              <p className="tiny">Command family</p>
                              <strong>{candidate.suggestedCommandFamily || "—"}</strong>
                            </div>
                            <div>
                              <p className="tiny">Target</p>
                              <strong>{targetLabel}</strong>
                            </div>
                            <div>
                              <p className="tiny">Expected signal</p>
                              <strong>{candidate.expectedSignal || "—"}</strong>
                            </div>
                            <div>
                              <p className="tiny">Risk level</p>
                              <strong>{candidate.riskLevel}</strong>
                            </div>
                            <div>
                              <p className="tiny">Confidence</p>
                              <strong>{candidate.confidence}</strong>
                            </div>
                          </div>
                          <div className="next-check-plan-flags">
                            <span>
                              Safe to automate: <strong>{candidate.safeToAutomate ? "Yes" : "No"}</strong>
                            </span>
                            <span>
                              Operator approval: <strong>{candidate.requiresOperatorApproval ? "Yes" : "No"}</strong>
                            </span>
                            <span>
                              Estimated cost: <strong>{candidate.estimatedCost || "—"}</strong>
                            </span>
                          </div>
                          {rationaleEntries.length ? (
                            <div className="plan-rationale">
                              {rationaleEntries.map((entry) => (
                                <span key={entry.label} className="plan-rationale-item">
                                  <strong>{entry.label}:</strong> {humanizeReason(entry.value) || entry.value}
                                </span>
                              ))}
                            </div>
                          ) : null}
                          {candidate.priorityRationale ? (
                            <div className="next-check-queue-item-rationale">
                              <span className="priority-rationale-label">
                                Why not actionable now:
                              </span>
                              <span className="priority-rationale-badge">
                                {candidate.priorityRationale}
                              </span>
                              {candidate.alertmanagerProvenance ? (
                                <span
                                  className="ranking-reason-badge ranking-reason-badge--alertmanager"
                                  title={(() => {
                                    const prov = candidate.alertmanagerProvenance!;
                                    const parts: string[] = [];
                                    if (prov.baseBonus !== prov.appliedBonus) {
                                      parts.push(`Base bonus: ${prov.baseBonus}, Applied: ${prov.appliedBonus}`);
                                    } else if (prov.appliedBonus > 0) {
                                      parts.push(`Bonus: ${prov.appliedBonus}`);
                                    }
                                    if (Object.keys(prov.severitySummary).length > 0) {
                                      const sevParts = Object.entries(prov.severitySummary)
                                        .map(([sev, count]) => `${sev}: ${count}`)
                                        .join(", ");
                                      parts.push(`Severity: ${sevParts}`);
                                    }
                                    if (prov.signalStatus) {
                                      parts.push(`Signal: ${prov.signalStatus}`);
                                    }
                                    return parts.length > 0 ? parts.join(" · ") : "Ranking influenced by Alertmanager snapshot";
                                  })()}
                                >
                                  🔔{" "}
                                  {(() => {
                                    const prov = candidate.alertmanagerProvenance!;
                                    if (prov.matchedDimensions.length === 0) {
                                      return "Promoted by Alertmanager";
                                    }
                                    const parts = prov.matchedDimensions.map((dim) => {
                                      const values = prov.matchedValues[dim] ?? [];
                                      const valuesStr = values.length > 0 ? `: ${values.join(", ")}` : "";
                                      return `${dim}${valuesStr}`;
                                    });
                                    const bonusStr = prov.appliedBonus > 0 ? ` (+${prov.appliedBonus})` : "";
                                    return `Matched ${parts.join(", ")}${bonusStr}`;
                                  })()}
                                </span>
                              ) : candidate.rankingReason ? (
                                <span className="ranking-reason-badge">
                                  {candidate.rankingReason}
                                </span>
                              ) : null}
                            </div>
                          ) : null}
                          <div className="next-check-outcome-meta">
                            <span className={outcomeStatusClass(candidate.outcomeStatus)}>
                              {outcomeStatusDisplay(candidate.outcomeStatus)}
                            </span>
                            <span className="muted tiny">
                              Approval: {humanizeReason(candidate.approvalState) || candidate.approvalState || "unknown"} · Execution: {humanizeReason(candidate.executionState) || candidate.executionState || "unknown"}
                            </span>
                            {candidate.latestTimestamp ? (
                              <span className="muted tiny">Updated {relativeRecency(candidate.latestTimestamp)}</span>
                            ) : null}
                            {candidate.latestArtifactPath ? (
                              <a
                                className="link"
                                href={artifactUrl(candidate.latestArtifactPath)}
                                target="_blank"
                                rel="noreferrer"
                              >
                                View latest artifact
                              </a>
                            ) : null}
                          </div>
                          {(variant === "approval" || variant === "stale") && (
                            <div className="next-check-approval-actions">
                              <button
                                type="button"
                                className="button secondary small"
                                onClick={() => handleApproveCandidate(candidate, candidateKey)}
                                disabled={approvingCandidate === candidateKey}
                              >
                                {approvingCandidate === candidateKey ? "Approving…" : "Approve candidate"}
                              </button>
                              {approvalResult ? (
                                <p
                                  className={`next-check-approval-note next-check-approval-note-${approvalResult.status}`}
                                >
                                  {approvalResult.summary}
                                </p>
                              ) : null}
                              {approvalArtifactLink ? (
                                <a
                                  className="link"
                                  href={approvalArtifactLink}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  View approval record
                                </a>
                              ) : null}
                            </div>
                          )}
                          {variant === "stale" && (
                            <p className="plan-stale-note">
                              Recorded approval belongs to a prior plan. Request a fresh approval to
                              run this candidate.
                            </p>
                          )}
                          {variant === "approved" && (
                            <div className="next-check-approval-status">
                              <p className="next-check-approval-note next-check-approval-note-success">
                                Approved {approvalRecency ?? "recently"}.
                              </p>
                              {approvalArtifactLink ? (
                                <a className="link" href={approvalArtifactLink} target="_blank" rel="noreferrer">
                                  View approval record
                                </a>
                              ) : null}
                            </div>
                          )}
                          {manualAllowed && (
                            <div className="next-check-manual-actions">
                              <button
                                type="button"
                                className="button primary small"
                                onClick={() => handleManualExecution(candidate, candidateKey)}
                                disabled={executingCandidate === candidateKey}
                              >
                                {executingCandidate === candidateKey ? "Running…" : "Run candidate"}
                              </button>
                              {executionResult ? (
                                <p
                                  className={`next-check-execution next-check-execution-${
                                    executionResult.status === "success" ? "success" : "error"
                                  }`}
                                >
                                  {executionResult.summary ||
                                    (executionResult.status === "success"
                                      ? "Execution recorded."
                                      : "Execution failed.")}
                                  {executionResult.artifactPath ? (
                                    <>
                                      {" "}
                                      <a
                                        className="link"
                                        href={artifactUrl(executionResult.artifactPath)}
                                        target="_blank"
                                        rel="noreferrer"
                                      >
                                        View artifact
                                      </a>
                                    </>
                                  ) : null}
                                </p>
                              ) : null}
                              {executionResult?.warning ? (
                                <p className="next-check-execution next-check-execution-warning">
                                  {executionResult.warning}
                                </p>
                              ) : null}
                              {executionResult?.warning ? (
                                <button
                                  type="button"
                                  className="link tiny next-check-refresh-action"
                                  onClick={() => {
                                    /* refresh is handled by parent */
                                  }}
                                >
                                  Refresh now
                                </button>
                              ) : null}
                              {executionBlockingReason ? (
                                <p className="plan-blocking-reason">
                                  Reason: {humanizeReason(executionBlockingReason)}
                                </p>
                              ) : null}
                            </div>
                          )}
                          {candidate.normalizationReason ? (
                            <p className="plan-normalization">Normalized: {humanizeReason(candidate.normalizationReason)}</p>
                          ) : null}
                          {candidate.gatingReason ? (
                            <p className="plan-gating">Gating reason: {candidate.gatingReason}</p>
                          ) : null}
                          {candidate.duplicateEvidenceDescription ? (
                            <p className="plan-gating">
                              Duplicate evidence: {candidate.duplicateEvidenceDescription}
                            </p>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                </div>
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
              <div className="cluster-lists">
                <div className="drilldown-summary">
                  <h3>Drilldown summary</h3>
                  <p className="small">
                    {clusterDetail.drilldownAvailability.available}/
                    {clusterDetail.drilldownAvailability.totalClusters} ready ·
                    Missing: {clusterDetail.drilldownAvailability.missingClusters.join(", ") || "none"}
                  </p>
                  <div className="drilldown-grid">
                    {clusterDetail.drilldownCoverage.map((entry) => (
                      <article
                        className={`drilldown-card ${entry.available ? "available" : "missing"}`}
                        key={entry.label}
                      >
                        <header>
                          <strong>{entry.label}</strong>
                          <span>{entry.available ? "Ready" : "Missing"}</span>
                        </header>
                        <p className="small">Context: {entry.context}</p>
                        <p className="small">Captured: {entry.timestamp || "pending"}</p>
                        {entry.artifactPath ? (
                          <a
                            className="link"
                            href={artifactUrl(entry.artifactPath)}
                            target="_blank"
                            rel="noreferrer"
                          >
                            View drilldown
                          </a>
                        ) : null}
                      </article>
                    ))}
                  </div>
                </div>
                <div>
                  <h3>Related proposals</h3>
                  {clusterDetail.relatedProposals.map((proposal) => (
                    <div className="related-card" key={proposal.proposalId}>
                      <p className="eyebrow">{proposal.proposalId}</p>
                      <p className="small">{proposal.target}</p>
                      <span className={statusClass(proposal.status)}>{proposal.status}</span>
                    </div>
                  ))}
                </div>
                <div>
                  <h3>Related notifications</h3>
                  {clusterDetail.relatedNotifications.map((notification) => (
                    <div className="related-card" key={notification.timestamp + notification.kind}>
                      <p className="eyebrow">{notification.kind}</p>
                      <p className="small">{notification.summary}</p>
                      <span className="small">{formatTimestamp(notification.timestamp)}</span>
                    </div>
                  ))}
                </div>
              </div>
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
