/**
 * ClusterNextCheckPlanSection Component
 *
 * Renders the "Next check plan" block: planner candidates, orphaned approvals,
 * outcome summary, and per-candidate execution/approval controls.
 *
 * Extracted from ClusterDetailSection.tsx as part of the second-pass decomposition effort.
 * State ownership (executionResults, approvalResults, executing/approvingCandidate)
 * remains in App.tsx and is passed as props.
 */

import type {
  NextCheckPlanCandidate,
  NextCheckOrphanedApproval,
  NextCheckOutcomeCount,
  NextCheckExecutionResponse,
  ArtifactLink,
} from "../types";

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
// Helper functions (plan-local - extracted from ClusterDetailSection)
// =============================================================================

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

const humanizeReason = (value?: string | null) => {
  if (!value) {
    return null;
  }
  return value
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
};

// =============================================================================
// Props Contract
// =============================================================================

export interface ClusterNextCheckPlanSectionProps {
  // Data
  planCandidates: NextCheckPlanCandidate[];
  orphanedApprovals: NextCheckOrphanedApproval[];
  planArtifactLink: string | null;
  planSummaryText: string;
  planCandidateCountLabel: string;
  planStatusText: string | null;
  outcomeSummary: NextCheckOutcomeCount[];

  // Context for defaults
  selectedClusterLabel: string | null;

  // Execution state
  executionResults: Record<string, ExecutionResult>;
  approvalResults: Record<string, ApprovalResult>;
  executingCandidate: string | null;
  approvingCandidate: string | null;

  // Handlers
  handleApproveCandidate: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;
  handleManualExecution: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;
  onRefresh: () => void;

  // Helpers
  buildCandidateKey: (candidate: NextCheckPlanCandidate, index: number) => string;
  isManualExecutionAllowed: (candidate: NextCheckPlanCandidate) => boolean;
  artifactUrl: (path: string) => string | null;
  relativeRecency: (ts: string) => string;
}

// =============================================================================
// Component
// =============================================================================

export const ClusterNextCheckPlanSection: React.FC<ClusterNextCheckPlanSectionProps> = ({
  planCandidates,
  orphanedApprovals,
  planArtifactLink,
  planSummaryText,
  planCandidateCountLabel,
  planStatusText,
  outcomeSummary,
  selectedClusterLabel,
  executionResults,
  approvalResults,
  executingCandidate,
  approvingCandidate,
  handleApproveCandidate,
  handleManualExecution,
  onRefresh,
  buildCandidateKey,
  isManualExecutionAllowed,
  artifactUrl,
  relativeRecency,
}) => {
  return (
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
                      onClick={onRefresh}
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
  );
};

export default ClusterNextCheckPlanSection;
