/**
 * QueuePanel - Renders the "Next-check queue" panel (work list).
 *
 * Displays a curated shortlist of next-check candidates for execution.
 * Supports filtering by cluster, status, command family, priority, workstream,
 * and search. Includes inline actions for manual execution, approval,
 * and navigation to cluster/execution details.
 *
 * @module components/QueuePanel
 */
import type {
  NextCheckQueueItem,
  NextCheckQueueStatus,
  NextCheckExecutionHistoryEntry,
  NextCheckExecutionResponse,
  FeedbackAdaptationProvenance,
} from "../types";
import {
  artifactUrl,
  formatTimestamp,
  relativeRecency,
  statusClass,
} from "../utils";
import { FailureFollowUpBlock } from "./FailureFollowUpBlock";
import { ResultInterpretationBlock } from "./ResultInterpretationBlock";

// ============================================================================
// Local utilities
// ============================================================================

/** Humanize a reason code into a readable label. */
const humanizeReason = (value?: string | null): string | null => {
  if (!value) return null;
  return value
    .replace(/_/g, " ")
    .replace(/([A-Z])/g, " $1")
    .replace(/^./, (str) => str.toUpperCase())
    .trim();
};

// ============================================================================
// Props interface
// ============================================================================

export interface QueuePanelProps {
  // Queue state (filtering/sorting)
  queueClusterFilter: string;
  queueStatusFilter: NextCheckQueueStatus | "all";
  queueCommandFamilyFilter: string;
  queuePriorityFilter: string;
  queueWorkstreamFilter: string;
  queueSearch: string;
  queueSortOption: string;
  queueFocusMode: string;
  // Setters
  setQueueClusterFilter: (v: string) => void;
  setQueueStatusFilter: (v: NextCheckQueueStatus | "all") => void;
  setQueueCommandFamilyFilter: (v: string) => void;
  setQueuePriorityFilter: (v: string) => void;
  setQueueWorkstreamFilter: (v: string) => void;
  setQueueSearch: (v: string) => void;
  setQueueSortOption: (v: string) => void;
  setQueueFocusMode: (v: string) => void;
  // Options (derived from queue items)
  queueClusterOptions: string[];
  queueCommandFamilyOptions: string[];
  queuePriorityOptions: string[];
  queueWorkstreamOptions: string[];
  // Queue data
  runQueue: NextCheckQueueItem[];
  sortedQueue: NextCheckQueueItem[];
  queueGroups: Array<{
    status: NextCheckQueueStatus;
    label: string;
    items: NextCheckQueueItem[];
  }>;
  queueExplanation: import("../types").NextCheckQueueExplanation | null | undefined;
  // UI state
  expandedQueueItems: Record<string, boolean>;
  toggleQueueDetails: (key: string) => void;
  queueHighlightKey: string | null;
  // Execution/approval state
  executionResults: Record<string, QueueExecutionResult>;
  approvalResults: Record<string, QueueApprovalResult>;
  executingCandidate: string | null;
  approvingCandidate: string | null;
  // Actions
  onToggleQueueFocusPreset: (mode: string) => void;
  onResetQueueFilters: () => void;
  onResetQueueView: () => void;
  onBackToQueue: () => void;
  onManualExecution: (candidate: NextCheckQueueItem, key: string) => void;
  onApproveCandidate: (candidate: NextCheckQueueItem, key: string) => void;
  onQueueClusterJump: (candidate: NextCheckQueueItem) => void;
  onQueueExecutionJump: (candidate: NextCheckQueueItem) => void;
  // Helpers
  buildCandidateKey: (candidate: NextCheckQueueItem, index: number) => string;
  findExecutionHistoryEntry: (candidate: NextCheckQueueItem) => NextCheckExecutionHistoryEntry | null;
  isManualExecutionAllowed: (candidate: NextCheckQueueItem) => boolean;
  getNotRunnableExplanation: (candidate: NextCheckQueueItem) => string | null;
  // Alertmanager display helpers
  getAlertmanagerProvenanceSubtext: (provenance: import("../types").AlertmanagerProvenance) => string;
  formatAlertmanagerProvenance: (provenance: import("../types").AlertmanagerProvenance) => string;
  getAlertmanagerPromotionSubtext: (rankingReason: string) => string | null;
  formatAlertmanagerPromotion: (rankingReason: string) => string;
  // Feedback adaptation display helpers
  getFeedbackAdaptationProvenanceSubtext: (provenance: import("../types").FeedbackAdaptationProvenance) => string;
  formatFeedbackAdaptationProvenance: (provenance: import("../types").FeedbackAdaptationProvenance) => string;
  // Callbacks
  onRefresh: () => void;
}

// ============================================================================
// Local types (same as App.tsx)
// ============================================================================

type ExecutionErrorResult = {
  status: "error";
  summary: string;
  blockingReason?: string | null;
};

type QueueExecutionResult = NextCheckExecutionResponse | ExecutionErrorResult;

type QueueApprovalResult = {
  status: "success" | "error";
  summary: string;
  artifactPath?: string | null;
  approvalTimestamp?: string | null;
};

// ============================================================================
// Constants (moved from App.tsx)
// ============================================================================

const NEXT_CHECK_QUEUE_STATUS_ORDER: NextCheckQueueStatus[] = [
  "approved-ready",
  "safe-ready",
  "approval-needed",
  "failed",
  "completed",
  "duplicate-or-stale",
];

const NEXT_CHECK_QUEUE_STATUS_LABELS: Record<NextCheckQueueStatus, string> = {
  "approved-ready": "Approved & ready",
  "safe-ready": "Safe to automate",
  "approval-needed": "Approval needed",
  "failed": "Failed executions",
  "completed": "Completed",
  "duplicate-or-stale": "Duplicate / stale",
};

const QUEUE_SORT_OPTIONS = [
  { label: "Backend order", value: "default" },
  { label: "Priority", value: "priority" },
  { label: "Cluster", value: "cluster" },
  { label: "Latest activity", value: "activity" },
] as const;

// ============================================================================
// Component
// ============================================================================

export const QueuePanel = ({
  queueClusterFilter,
  queueStatusFilter,
  queueCommandFamilyFilter,
  queuePriorityFilter,
  queueWorkstreamFilter,
  queueSearch,
  queueSortOption,
  queueFocusMode,
  setQueueClusterFilter,
  setQueueStatusFilter,
  setQueueCommandFamilyFilter,
  setQueuePriorityFilter,
  setQueueWorkstreamFilter,
  setQueueSearch,
  setQueueSortOption,
  setQueueFocusMode,
  queueClusterOptions,
  queueCommandFamilyOptions,
  queuePriorityOptions,
  queueWorkstreamOptions,
  runQueue,
  sortedQueue,
  queueGroups,
  queueExplanation,
  expandedQueueItems,
  toggleQueueDetails,
  queueHighlightKey,
  executionResults,
  approvalResults,
  executingCandidate,
  approvingCandidate,
  onToggleQueueFocusPreset,
  onResetQueueFilters,
  onResetQueueView,
  onBackToQueue,
  onManualExecution,
  onApproveCandidate,
  onQueueClusterJump,
  onQueueExecutionJump,
  buildCandidateKey,
  findExecutionHistoryEntry,
  isManualExecutionAllowed,
  getNotRunnableExplanation,
  getAlertmanagerProvenanceSubtext,
  formatAlertmanagerProvenance,
  getAlertmanagerPromotionSubtext,
  formatAlertmanagerPromotion,
  getFeedbackAdaptationProvenanceSubtext,
  formatFeedbackAdaptationProvenance,
  onRefresh,
}: QueuePanelProps) => {
  // Derive filtersActive from filter state
  const queueSearchTerm = queueSearch.trim().toLowerCase();
  const filtersActive =
    queueClusterFilter !== "all" ||
    queueStatusFilter !== "all" ||
    queueCommandFamilyFilter !== "all" ||
    queuePriorityFilter !== "all" ||
    queueWorkstreamFilter !== "all" ||
    Boolean(queueSearchTerm) ||
    queueFocusMode !== "none";

  const formatSourceType = (value?: string | null) => {
    if (!value) return null;
    if (value === "deterministic") {
      return "Deterministic evidence";
    }
    return `${value.charAt(0).toUpperCase()}${value.slice(1)}`;
  };

  const formatCandidatePriority = (value?: string | null) => {
    const normalized = (value ?? "secondary").toLowerCase();
    return `${normalized.charAt(0).toUpperCase()}${normalized.slice(1)}`;
  };

  return (
    <section className="panel next-check-queue-panel" id="next-check-queue">
      <div className="section-head">
        <div>
          <h2>Work list</h2>
          <p className="muted tiny">Curated shortlist for execution; approve, run, or review what already ran.</p>
        </div>
        <span className="muted tiny">{runQueue.length} candidate{runQueue.length === 1 ? "" : "s"}</span>
      </div>
      <div className="next-check-queue-controls">
        <div className="next-check-filter-row">
          <label>
            Cluster filter
            <select
              value={queueClusterFilter}
              onChange={(event) => setQueueClusterFilter(event.target.value)}
            >
              <option value="all">All clusters</option>
              {queueClusterOptions.map((entry) => (
                <option key={entry} value={entry}>
                  {entry}
                </option>
              ))}
            </select>
          </label>
          <label>
            Queue status
            <select
              value={queueStatusFilter}
              onChange={(event) =>
                setQueueStatusFilter(event.target.value as NextCheckQueueStatus | "all")
              }
            >
              <option value="all">All statuses</option>
              {NEXT_CHECK_QUEUE_STATUS_ORDER.map((status) => (
                <option key={status} value={status}>
                  {NEXT_CHECK_QUEUE_STATUS_LABELS[status]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Command family
            <select
              value={queueCommandFamilyFilter}
              onChange={(event) => setQueueCommandFamilyFilter(event.target.value)}
            >
              <option value="all">All command families</option>
              {queueCommandFamilyOptions.map((entry) => (
                <option key={entry} value={entry}>
                  {entry}
                </option>
              ))}
            </select>
          </label>
          <label>
            Priority
            <select
              value={queuePriorityFilter}
              onChange={(event) => setQueuePriorityFilter(event.target.value)}
            >
              <option value="all">All priorities</option>
              {queuePriorityOptions.map((entry) => (
                <option key={entry} value={entry}>
                  {formatCandidatePriority(entry)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Workstream
            <select
              value={queueWorkstreamFilter}
              onChange={(event) => setQueueWorkstreamFilter(event.target.value)}
            >
              <option value="all">All workstreams</option>
              {queueWorkstreamOptions.map((entry) => (
                <option key={entry} value={entry}>
                  {entry}
                </option>
              ))}
            </select>
          </label>
          <label className="queue-search">
            Search queue
            <input
              type="search"
              placeholder="Description, reason, or signal"
              value={queueSearch}
              onChange={(event) => setQueueSearch(event.target.value)}
            />
          </label>
          <button type="button" className="text-button" onClick={onBackToQueue}>
            Back to queue
          </button>
        </div>
        <div className="next-check-control-row">
          <div className="focus-presets">
            <button
              type="button"
              className={`focus-preset-button ${queueFocusMode === "work" ? "active" : ""}`}
              aria-pressed={queueFocusMode === "work"}
              onClick={() => onToggleQueueFocusPreset("work")}
            >
              Work now
            </button>
            <button
              type="button"
              className={`focus-preset-button ${queueFocusMode === "review" ? "active" : ""}`}
              aria-pressed={queueFocusMode === "review"}
              onClick={() => onToggleQueueFocusPreset("review")}
            >
              Needs review
            </button>
          </div>
          <label>
            Sort by
            <select
              value={queueSortOption}
              onChange={(event) =>
                setQueueSortOption(event.target.value)
              }
            >
              {QUEUE_SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p className="muted tiny next-check-filter-summary">
          Showing {sortedQueue.length} of {runQueue.length} candidate{runQueue.length === 1 ? "" : "s"}
          {filtersActive ? " · filters applied" : ""}
          {" "}
          <button type="button" className="link tiny" onClick={onResetQueueView}>
            Reset queue view
          </button>
        </p>
      </div>
      {runQueue.length === 0 ? (
        <div className="queue-empty-state queue-empty-explanation">
          <p className="muted small">Work list is empty for this run.</p>
          {queueExplanation ? (
            <div className="queue-explanation-block">
              <div className="queue-explanation-header">
                <div>
                  <p className="tiny">Queue status: {queueExplanation.status}</p>
                  {queueExplanation.reason ? (
                    <p>{queueExplanation.reason}</p>
                  ) : null}
                </div>
                {queueExplanation.plannerArtifactPath ? (
                  <a
                    className="link tiny"
                    href={artifactUrl(queueExplanation.plannerArtifactPath)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View planner artifact
                  </a>
                ) : null}
              </div>
              {queueExplanation.hint ? (
                <p className="muted tiny">{queueExplanation.hint}</p>
              ) : null}
              <div className="queue-explanation-stats">
                <span>
                  Degraded clusters: {queueExplanation.clusterState.degradedClusterCount}
                  {queueExplanation.clusterState.degradedClusterLabels.length
                    ? ` (${queueExplanation.clusterState.degradedClusterLabels.join(", ")})`
                    : ""}
                </span>
                <span>
                  Drilldowns ready: {queueExplanation.clusterState.drilldownReadyCount}
                </span>
                <span>
                  Deterministic next checks: {queueExplanation.clusterState.deterministicNextCheckCount} available
                </span>
              </div>
              <div className="queue-explanation-accounting">
                <span>Generated: {queueExplanation.candidateAccounting.generated}</span>
                <span>Safe: {queueExplanation.candidateAccounting.safe}</span>
                <span>
                  Approval needed: {queueExplanation.candidateAccounting.approvalNeeded}
                </span>
                <span>Duplicate: {queueExplanation.candidateAccounting.duplicate}</span>
                <span>Completed: {queueExplanation.candidateAccounting.completed}</span>
                <span>
                  Stale/orphaned: {queueExplanation.candidateAccounting.staleOrphaned}
                </span>
              </div>
              <p className="muted tiny">
                Deterministic next checks available: {queueExplanation.deterministicNextChecksAvailable ? "Yes" : "No"}
              </p>
              {queueExplanation.recommendedNextActions.length ? (
                <div className="queue-explanation-actions">
                  <div className="queue-explanation-actions__label">Recommended next actions</div>
                  <ul>
                    {queueExplanation.recommendedNextActions.map((entry) => (
                      <li key={entry}>{entry}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : sortedQueue.length === 0 ? (
        <p className="muted small queue-empty-state">
          Filters hide all {runQueue.length} candidate{runQueue.length === 1 ? "" : "s"}.
          {filtersActive ? (
            <>
              {" "}
              <button type="button" className="link tiny" onClick={onResetQueueFilters}>
                Reset filters
              </button>
            </>
          ) : null}
        </p>
      ) : (
        queueGroups.map((group) => (
          <div className="next-check-queue-group" key={group.status}>
            <div className="next-check-queue-group-head">
              <div>
                <h3>{group.label}</h3>
                <p className="tiny muted">
                  {group.items.length} item{group.items.length === 1 ? "" : "s"} · {group.label}
                </p>
              </div>
              <span className={`queue-status-pill queue-status-pill-${group.status}`}>
                {group.label}
              </span>
            </div>
            <div className="next-check-queue-items">
              {group.items.map((item, index) => {
                const queueCandidateKey = buildCandidateKey(item, index);
                const approvalResult = approvalResults[queueCandidateKey];
                const executionResult = executionResults[queueCandidateKey];
                const latestArtifactLink = item.latestArtifactPath
                  ? artifactUrl(item.latestArtifactPath)
                  : null;
                const allowRun = isManualExecutionAllowed(item);
                const executionEntry = findExecutionHistoryEntry(item);
                const detailsExpanded = Boolean(expandedQueueItems[queueCandidateKey]);
                const planArtifactLink = item.planArtifactPath
                  ? artifactUrl(item.planArtifactPath)
                  : null;
                const metadataEntries = [
                  { label: "Origin", value: formatSourceType(item.sourceType) },
                  { label: "Source reason", value: item.sourceReason },
                  { label: "Expected signal", value: item.expectedSignal },
                  { label: "Normalization", value: humanizeReason(item.normalizationReason) },
                  { label: "Safety", value: humanizeReason(item.safetyReason) },
                  { label: "Approval reason", value: humanizeReason(item.approvalReason) },
                  { label: "Duplicate reason", value: humanizeReason(item.duplicateReason) },
                  { label: "Blocking reason", value: humanizeReason(item.blockingReason) },
                  { label: "Target context", value: item.targetContext },
                ].filter((entry) => entry.value);
                const isQueueCardHighlighted = queueHighlightKey === queueCandidateKey;
                const queueCardClasses = [
                  "next-check-queue-item",
                  isQueueCardHighlighted ? "highlight-target" : null,
                ]
                  .filter(Boolean)
                  .join(" ");
                return (
                  <article
                    className={queueCardClasses}
                    key={queueCandidateKey}
                    data-queue-key={queueCandidateKey}
                    data-highlighted={isQueueCardHighlighted ? "true" : undefined}
                  >
                    <div className="next-check-queue-item-header">
                      <div className="queue-item-title-block">
                        <h4 className="queue-item-title">{item.description}</h4>
                        {formatSourceType(item.sourceType) ? (
                          <span className="queue-source-pill">
                            {formatSourceType(item.sourceType)}
                          </span>
                        ) : null}
                      </div>
                      <div className="queue-item-status-badges">
                        <span className={`action-state-badge action-state-${item.approvalState === "approved" ? "ready" : item.approvalState === "approval-required" ? "approval" : "inactive"}`}>
                          {item.approvalState === "approved" ? "Approved" : item.approvalState === "approval-required" ? "Needs approval" : "Pending"}
                        </span>
                        {item.executionState && (
                          <span className={`execution-state-badge execution-state-${item.executionState}`}>
                            {item.executionState.replace(/[-]/g, " ")}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="next-check-queue-item-context">
                      <p className="queue-item-rationale-line">
                        <span className="queue-item-rationale-label">Why: </span>
                        {humanizeReason(item.sourceReason) || item.sourceReason || humanizeReason(item.normalizationReason) || "—"}{" "}
                        {item.expectedSignal ? <span className="queue-card-signal">→ {item.expectedSignal}</span> : null}
                      </p>
                      <div className="queue-item-meta-row">
                        <span className="queue-item-meta-tag">Cluster: {item.targetCluster ?? "Unassigned"}</span>
                        <span className="queue-item-meta-tag">{formatCandidatePriority((item.priorityLabel ?? "secondary").toLowerCase())}</span>
                        <span className="queue-item-meta-tag">{item.suggestedCommandFamily ?? "—"}</span>
                      </div>
                      {item.priorityRationale ? (
                        <div className="queue-item-blocker-note">
                          <span className="queue-item-blocker-icon">⏸</span>
                          <span className="queue-item-blocker-text">{item.priorityRationale}</span>
                          {item.alertmanagerProvenance && (
                            <span className="ranking-reason-badge ranking-reason-badge--alertmanager" title={getAlertmanagerProvenanceSubtext(item.alertmanagerProvenance)}>
                              🔔 {formatAlertmanagerProvenance(item.alertmanagerProvenance)}
                            </span>
                          )}
                          {item.feedbackAdaptationProvenance && (
                            <span className="ranking-reason-badge ranking-reason-badge--feedback" title={getFeedbackAdaptationProvenanceSubtext(item.feedbackAdaptationProvenance)}>
                              📝 {formatFeedbackAdaptationProvenance(item.feedbackAdaptationProvenance)}
                            </span>
                          )}
                          {!item.alertmanagerProvenance && !item.feedbackAdaptationProvenance && item.rankingReason && (
                            item.rankingReason.startsWith("alertmanager-context:") ? (
                              <span className="ranking-reason-badge ranking-reason-badge--alertmanager" title={getAlertmanagerPromotionSubtext(item.rankingReason) ?? "Ranking influenced by Alertmanager snapshot"}>
                                🔔 {formatAlertmanagerPromotion(item.rankingReason)}
                              </span>
                            ) : (
                              <span className="ranking-reason-badge">{item.rankingReason}</span>
                            )
                          )}
                        </div>
                      ) : null}
                    </div>
                    <div className="next-check-queue-item-actions">
                      {allowRun && (
                        <button
                          type="button"
                          className="button primary small queue-item-primary-action"
                          onClick={() => onManualExecution(item, queueCandidateKey)}
                          disabled={executingCandidate === queueCandidateKey}
                        >
                          {executingCandidate === queueCandidateKey ? "Running…" : "Run candidate"}
                        </button>
                      )}
                      {item.requiresOperatorApproval && item.approvalState !== "approved" && (
                        <button
                          type="button"
                          className="button secondary small"
                          onClick={() => onApproveCandidate(item, queueCandidateKey)}
                          disabled={approvingCandidate === queueCandidateKey}
                        >
                          {approvingCandidate === queueCandidateKey ? "Approving…" : "Approve"}
                        </button>
                      )}
                      {!allowRun && (
                        <span className="not-runnable-explanation">
                          {getNotRunnableExplanation(item)}
                        </span>
                      )}
                      <div className="queue-item-secondary-actions">
                        {latestArtifactLink && (
                          <a
                            className="link tiny"
                            href={latestArtifactLink}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Artifact
                          </a>
                        )}
                        <button
                          type="button"
                          className="queue-action-button"
                          onClick={() => onQueueClusterJump(item)}
                          disabled={!item.targetCluster}
                        >
                          Cluster
                        </button>
                        {executionEntry ? (
                          <button
                            type="button"
                            className="queue-action-button"
                            onClick={() => onQueueExecutionJump(item)}
                          >
                            Execution
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className="toggle-details-button"
                          onClick={() => toggleQueueDetails(queueCandidateKey)}
                        >
                          {detailsExpanded ? "Less" : "More"}
                        </button>
                      </div>
                    </div>
                    {approvalResult ? (
                      <p className={`next-check-approval-note next-check-approval-note-${approvalResult.status}`}>
                        {approvalResult.summary}
                        {approvalResult.artifactPath ? (
                          <>
                            {" "}
                            <a
                              className="link"
                              href={artifactUrl(approvalResult.artifactPath)}
                              target="_blank"
                              rel="noreferrer"
                            >
                              View approval record
                            </a>
                          </>
                        ) : null}
                      </p>
                    ) : null}
                    {executionResult ? (
                      <p
                        className={`next-check-execution next-check-execution-${
                          executionResult.status === "success" ? "success" : "error"
                        }`}
                      >
                        {executionResult.summary ||
                          (executionResult.status === "success" ? "Execution recorded." : "Execution failed.")}
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
                        onClick={() => onRefresh()}
                      >
                        Refresh now
                      </button>
                    ) : null}
                    {detailsExpanded && (
                      <div className="next-check-queue-item-details">
                        <ResultInterpretationBlock
                          resultClass={item.resultClass}
                          resultSummary={item.resultSummary}
                          suggestedNextOperatorMove={item.suggestedNextOperatorMove}
                        />
                        <FailureFollowUpBlock
                          failureClass={item.failureClass}
                          failureSummary={item.failureSummary}
                          suggestedNextOperatorMove={item.suggestedNextOperatorMove}
                        />
                        <div className="next-check-queue-item-metadata">
                          {metadataEntries.map((entry) => (
                            <span key={entry.label}>
                              <strong>{entry.label}:</strong> {entry.value}
                            </span>
                          ))}
                          {planArtifactLink ? (
                            <span>
                              <strong>Plan artifact:</strong>
                              {" "}
                              <a href={planArtifactLink} target="_blank" rel="noreferrer">
                                View planner artifact
                              </a>
                            </span>
                          ) : null}
                        </div>
                        <div className="next-check-command-preview">
                          <p className="tiny muted">Command preview</p>
                          <pre>{item.commandPreview ?? item.description}</pre>
                        </div>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          </div>
        ))
      )}
    </section>
  );
};