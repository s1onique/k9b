/**
 * ExecutionHistoryRow.tsx
 *
 * Individual execution history card/row component.
 */

import { ResultInterpretationBlock } from "../ResultInterpretationBlock";
import { FailureFollowUpBlock } from "../FailureFollowUpBlock";
import { UsefulnessFeedbackControl } from "./UsefulnessFeedbackControl";
import { AlertmanagerRelevanceFeedbackControl } from "./AlertmanagerRelevanceFeedbackControl";
import { formatDuration } from "./executionHistoryFormat";
import { buildExecutionEntryKey, buildCandidateKey } from "./executionHistoryTypes";
import type { NextCheckExecutionHistoryEntry, NextCheckQueueItem } from "../../types";
import {
  artifactUrl,
  formatTimestamp,
  relativeRecency,
  statusClass,
  truncateText,
} from "../../utils";

// =============================================================================
// ExecutionHistoryRow Component
// =============================================================================

interface ExecutionHistoryRowProps {
  entry: NextCheckExecutionHistoryEntry;
  highlightedKey: string | null;
  runQueue?: NextCheckQueueItem[];
  onHighlightQueueCard?: (key: string) => void;
  onSubmitFeedback?: (artifactPath: string, usefulnessClass: string, summary: string | undefined) => Promise<void>;
  onSubmitAlertmanagerRelevanceFeedback?: (
    artifactPath: string,
    relevance: "relevant" | "not_relevant" | "noisy" | "unsure",
    summary: string | undefined
  ) => Promise<void>;
}

export const ExecutionHistoryRow = ({
  entry,
  highlightedKey,
  runQueue,
  onHighlightQueueCard,
  onSubmitFeedback,
  onSubmitAlertmanagerRelevanceFeedback,
}: ExecutionHistoryRowProps) => {
  const badges: string[] = [
    entry.timedOut ? "Timed out" : null,
    entry.stdoutTruncated ? "stdout truncated" : null,
    entry.stderrTruncated ? "stderr truncated" : null,
  ].filter(Boolean) as string[];

  const durationSeconds = entry.durationMs != null ? entry.durationMs / 1000 : null;
  const entryKey = buildExecutionEntryKey(entry);
  const cardClasses = [
    "execution-history-card",
    highlightedKey === entryKey ? "highlight-target" : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <article
      className={cardClasses}
      key={`${entry.timestamp}-${entry.artifactPath ?? entry.candidateDescription ?? ""}`}
      data-highlighted={highlightedKey === entryKey ? "true" : undefined}
    >
      <header>
        <div>
          <p className="tiny muted">{relativeRecency(entry.timestamp)}</p>
          <strong>{formatTimestamp(entry.timestamp)}</strong>
        </div>
        <span className={statusClass(entry.status)}>{entry.status}</span>
      </header>
      <p className="small">
        {entry.candidateDescription || "Candidate description unavailable."}
      </p>
      <div className="execution-history-meta">
        <span>Cluster: {entry.clusterLabel || "unknown"}</span>
        <span>Command: {entry.commandFamily || "—"}</span>
        <span>Duration: {formatDuration(durationSeconds)}</span>
        {entry.candidateId && (
          <span className="provenance-hint" title={`Candidate ID: ${entry.candidateId}`}>
            #{entry.candidateIndex != null ? entry.candidateIndex + 1 : "?"}
          </span>
        )}
      </div>
      {/* Provenance traceability: jump link back to work list */}
      {entry.candidateId && runQueue && onHighlightQueueCard && (
        <div className="execution-history-provenance">
          <button
            type="button"
            className="provenance-jump"
            onClick={() => {
              const queueItemKey = runQueue.find(
                (q) => q.candidateId === entry.candidateId
              );
              if (queueItemKey) {
                const key = buildCandidateKey(queueItemKey, queueItemKey.candidateIndex ?? runQueue.indexOf(queueItemKey));
                onHighlightQueueCard(key);
              }
            }}
            title={`View candidate ${entry.candidateId} in work list`}
          >
            From work list #{entry.candidateIndex != null ? entry.candidateIndex + 1 : "?"}
          </button>
        </div>
      )}
      <div className="execution-history-badges">
        {badges.map((badge) => (
          <span key={badge} className="execution-history-badge">
            {badge}
          </span>
        ))}
        {entry.outputBytesCaptured != null && (
          <span className="execution-history-badge">
            Captured {entry.outputBytesCaptured} bytes
          </span>
        )}
      </div>
      <ResultInterpretationBlock
        resultClass={entry.resultClass}
        resultSummary={entry.resultSummary ? truncateText(entry.resultSummary, 120) : null}
        suggestedNextOperatorMove={entry.suggestedNextOperatorMove}
      />
      <FailureFollowUpBlock
        failureClass={entry.failureClass}
        failureSummary={entry.failureSummary}
        suggestedNextOperatorMove={entry.suggestedNextOperatorMove}
      />
      {entry.usefulnessClass ? (
        <div className="usefulness-indicator">
          <span className={`usefulness-badge usefulness-badge-${entry.usefulnessClass}`}>
            {entry.usefulnessClass}
          </span>
          {entry.usefulnessSummary && (
            <span className="muted small"> — {truncateText(entry.usefulnessSummary, 80)}</span>
          )}
        </div>
      ) : (
        <div className="usefulness-indicator unreviewed">
          <span className="muted small">Not reviewed</span>
        </div>
      )}
      {entry.packRefreshStatus && (
        <div className="execution-history-pack-refresh">
          <span className={entry.packRefreshStatus === "succeeded" ? "text-success" : "text-warning"}>
            Pack refresh: {entry.packRefreshStatus}
          </span>
          {entry.packRefreshWarning && (
            <span className="muted small"> — {entry.packRefreshWarning}</span>
          )}
        </div>
      )}
      {entry.artifactPath ? (
        <a
          className="link"
          href={artifactUrl(entry.artifactPath)}
          target="_blank"
          rel="noreferrer"
        >
          View artifact
        </a>
      ) : null}
      {onSubmitFeedback && entry.artifactPath && (
        <UsefulnessFeedbackControl
          entry={entry}
          onSubmit={onSubmitFeedback}
        />
      )}
      {/* Alertmanager provenance and relevance feedback section */}
      {entry.alertmanagerProvenance && (
        <div className="alertmanager-provenance-block">
          <span className="alertmanager-provenance-label">Alertmanager provenance</span>
          <span className="alertmanager-provenance-meta">
            Matched: {entry.alertmanagerProvenance.matchedDimensions?.join(", ") || "none"}
            {entry.alertmanagerProvenance.appliedBonus != null && (
              <> · bonus +{entry.alertmanagerProvenance.appliedBonus}</>
            )}
            {entry.alertmanagerProvenance.severitySummary && Object.keys(entry.alertmanagerProvenance.severitySummary).length > 0 && (
              <> · {Object.entries(entry.alertmanagerProvenance.severitySummary).map(([sev, count]) => `${count} ${sev}`).join(", ")}</>
            )}
          </span>
        </div>
      )}
      {entry.alertmanagerRelevance ? (
        <div className="alertmanager-relevance-indicator">
          <span className={`alertmanager-relevance-badge alertmanager-relevance-badge-${entry.alertmanagerRelevance}`}>
            {entry.alertmanagerRelevance}
          </span>
          {entry.alertmanagerRelevanceSummary && (
            <span className="muted small"> — {truncateText(entry.alertmanagerRelevanceSummary, 80)}</span>
          )}
          {entry.alertmanagerReviewedAt && (
            <span className="muted small"> · {relativeRecency(entry.alertmanagerReviewedAt)}</span>
          )}
        </div>
      ) : null}
      {onSubmitAlertmanagerRelevanceFeedback && entry.artifactPath && entry.alertmanagerProvenance && !entry.alertmanagerRelevance && (
        <AlertmanagerRelevanceFeedbackControl
          entry={entry}
          onSubmit={onSubmitAlertmanagerRelevanceFeedback}
        />
      )}
    </article>
  );
};

export default ExecutionHistoryRow;
