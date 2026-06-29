/**
 * ClusterNextCheckPlanCard.tsx
 *
 * Renders a single next check plan candidate card.
 * Handles all states: safe, approval-needed, approved, stale, duplicate.
 */

import type {
  NextCheckPlanCandidate,
  ExecutionResult,
  ApprovalResult,
  NextCheckStatusVariant,
  ExecutionErrorResult,
} from "./ClusterNextCheckPlanTypes";
import {
  formatCandidatePriority,
  humanizeReason,
  outcomeStatusClass,
  outcomeStatusDisplay,
} from "./clusterNextCheckPlanFormatters";
import { deriveExecutionLabel } from "../../utils";
import {
  determineNextCheckStatusVariant,
  getPlanStatusLabel,
  buildRationaleEntries,
  formatAlertmanagerTooltip,
  formatAlertmanagerBadgeLabel,
} from "./clusterNextCheckPlanViewModel";

export interface ClusterNextCheckPlanCardProps {
  candidate: NextCheckPlanCandidate;
  index: number;
  selectedClusterLabel: string | null;
  executionResults: Record<string, ExecutionResult>;
  approvalResults: Record<string, ApprovalResult>;
  executingCandidate: string | null;
  approvingCandidate: string | null;
  candidateKey: string;
  isManualExecutionAllowed: (candidate: NextCheckPlanCandidate) => boolean;
  artifactUrl: (path: string) => string | null;
  relativeRecency: (ts: string) => string;
  handleApproveCandidate: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;
  handleManualExecution: (candidate: NextCheckPlanCandidate, candidateKey: string) => Promise<void>;
  onRefresh: () => void;
}

export function ClusterNextCheckPlanCard({
  candidate,
  index,
  selectedClusterLabel,
  executionResults,
  approvalResults,
  executingCandidate,
  approvingCandidate,
  candidateKey,
  isManualExecutionAllowed,
  artifactUrl,
  relativeRecency,
  handleApproveCandidate,
  handleManualExecution,
  onRefresh,
}: ClusterNextCheckPlanCardProps) {
  const variant = determineNextCheckStatusVariant(candidate);
  const statusLabel = getPlanStatusLabel(variant, candidate);
  const statusClassName = `plan-status-pill plan-status-pill-${variant}`;
  const priority = (candidate.priorityLabel ?? "secondary").toLowerCase();
  const displayPriority = formatCandidatePriority(priority);
  const priorityIndicatorClass = `priority-pill priority-pill-${priority}`;
  const targetLabel = candidate.targetCluster || selectedClusterLabel || "cluster";

  const executionResult = executionResults[candidateKey];
  const approvalResult = approvalResults[candidateKey];
  const approvalArtifactPath = approvalResult?.artifactPath ?? candidate.approvalArtifactPath;
  const approvalArtifactBaseLink = approvalArtifactPath && artifactUrl(approvalArtifactPath);
  const approvalArtifactLink =
    approvalArtifactBaseLink && approvalArtifactPath
      ? `${approvalArtifactBaseLink}#${approvalArtifactPath}`
      : null;
  const approvalTimestamp = candidate.approvalTimestamp ?? approvalResult?.approvalTimestamp;
  const approvalRecency = approvalTimestamp && relativeRecency(approvalTimestamp);
  const executionBlockingReason =
    executionResult && executionResult.status !== "success"
      ? (executionResult as ExecutionErrorResult).blockingReason
      : null;

  const rationaleEntries = buildRationaleEntries(candidate);
  const manualAllowed = isManualExecutionAllowed(candidate);

  return (
    <article className="next-check-plan-card" key={`${candidate.description}-${index}`}>
      {/* Header */}
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

      {/* Meta grid */}
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

      {/* Flags */}
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

      {/* Rationale */}
      {rationaleEntries.length ? (
        <div className="plan-rationale">
          {rationaleEntries.map((entry) => (
            <span key={entry.label} className="plan-rationale-item">
              <strong>{entry.label}:</strong> {humanizeReason(entry.value) || entry.value}
            </span>
          ))}
        </div>
      ) : null}

      {/* Priority rationale and Alertmanager badge */}
      {candidate.priorityRationale ? (
        <div className="next-check-queue-item-rationale">
          <span className="priority-rationale-label">Why not actionable now:</span>
          <span className="priority-rationale-badge">{candidate.priorityRationale}</span>
          {candidate.alertmanagerProvenance ? (
            <span
              className="ranking-reason-badge ranking-reason-badge--alertmanager"
              title={formatAlertmanagerTooltip(candidate.alertmanagerProvenance)}
            >
              🔔 {formatAlertmanagerBadgeLabel(candidate.alertmanagerProvenance)}
            </span>
          ) : candidate.rankingReason ? (
            <span className="ranking-reason-badge">{candidate.rankingReason}</span>
          ) : null}
        </div>
      ) : null}

      {/* Outcome meta */}
      <div className="next-check-outcome-meta">
        <span className={outcomeStatusClass(candidate.outcomeStatus)}>
          {outcomeStatusDisplay(candidate.outcomeStatus)}
        </span>
        <span className="muted tiny">
          Approval: {humanizeReason(candidate.approvalState) || candidate.approvalState || "unknown"} · Execution: {deriveExecutionLabel(candidate) ?? "—"}
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

      {/* Approval actions (for approval/stale variants) */}
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
            <p className={`next-check-approval-note next-check-approval-note-${approvalResult.status}`}>
              {approvalResult.summary}
            </p>
          ) : null}
          {approvalArtifactLink ? (
            <a className="link" href={approvalArtifactLink} target="_blank" rel="noreferrer">
              View approval record
            </a>
          ) : null}
        </div>
      )}

      {/* Stale note */}
      {variant === "stale" && (
        <p className="plan-stale-note">
          Recorded approval belongs to a prior plan. Request a fresh approval to run this candidate.
        </p>
      )}

      {/* Approved status */}
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

      {/* Manual execution actions */}
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

      {/* Normalization note */}
      {candidate.normalizationReason ? (
        <p className="plan-normalization">Normalized: {humanizeReason(candidate.normalizationReason)}</p>
      ) : null}

      {/* Gating note */}
      {candidate.gatingReason ? (
        <p className="plan-gating">Gating reason: {candidate.gatingReason}</p>
      ) : null}

      {/* Duplicate evidence note */}
      {candidate.duplicateEvidenceDescription ? (
        <p className="plan-gating">
          Duplicate evidence: {candidate.duplicateEvidenceDescription}
        </p>
      ) : null}
    </article>
  );
}
