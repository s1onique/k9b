/**
 * RunsPanel.tsx
 *
 * Contains two panel components extracted from App.tsx (E1-3b-step10):
 *   - RecentRunsPanel: displays the runs table with filter bar, pagination,
 *     and detached-mode notice
 *   - RunSummaryPanel: displays the selected run header, summary stats,
 *     LLM telemetry, artifacts, and next-checks preview
 *
 * Both components are verbatim moves from App.tsx; no logic has been changed.
 * Helper types and interfaces specific to runs display are co-located here.
 *
 * Design note: RunSummaryPanel accepts a pre-computed `run` prop (RunPayload)
 * and derives all display values from it. It does not receive individually
 * pre-computed stats to keep the interface stable and co-located.
 */

import type { NextCheckPlanCandidate, NextCheckStatusVariant, RunPayload, RunsListEntry } from "../types";
import { artifactUrl, formatTimestamp, relativeRecency, statusClass } from "../utils";

// Re-export the RunsReviewFilter type for consumers who need it
export { RUNS_PAGE_SIZE_OPTIONS } from "../hooks/useRunSelection";
export type { RunsReviewFilter } from "../hooks/useRunSelection";

// Import filter options from the hook (already exported there)
import { RUNS_REVIEW_FILTER_OPTIONS, type RunsReviewFilter } from "../hooks/useRunSelection";

// Import Pagination component
import Pagination from "./Pagination";

// Import dayjs for age duration formatting
import dayjs from "dayjs";

// ---------------------------------------------------------------------------
// RecentRunsPanel
// ---------------------------------------------------------------------------

export type RecentRunsPanelProps = {
  runsList: RunsListEntry[];
  selectedRunId: string | null;
  runsFilter: RunsReviewFilter;
  runsFilterCounts: Record<RunsReviewFilter, number>;
  paginatedRunsList: RunsListEntry[];
  filteredRunsList: RunsListEntry[];
  runsListLoading: boolean;
  runsListError: string | null;
  runsPage: number;
  totalRunsPages: number;
  runsPageSize: number;
  isRunsListFollowingSelection: boolean;
  isSelectedRunVisibleOnCurrentRunsPage: boolean;
  executingBatchRunId: string | null;
  batchExecutionError: Record<string, string>;
  onRunsFilterChange: (filter: RunsReviewFilter) => void;
  onRunsPageChange: (page: number) => void;
  onRunsPageSizeChange: (size: number) => void;
  onRunSelection: (runId: string) => void;
  onBatchExecution: (runId: string) => void;
  onShowSelectedRun: () => void;
  onFocusClusterForNextChecks: (clusterLabel?: string | null) => void;
};

export const RecentRunsPanel = ({
  runsList,
  selectedRunId,
  runsFilter,
  runsFilterCounts,
  paginatedRunsList,
  filteredRunsList,
  runsListLoading,
  runsListError,
  runsPage,
  totalRunsPages,
  runsPageSize,
  isRunsListFollowingSelection,
  isSelectedRunVisibleOnCurrentRunsPage,
  executingBatchRunId,
  batchExecutionError,
  onRunsFilterChange,
  onRunsPageChange,
  onRunsPageSizeChange,
  onRunSelection,
  onBatchExecution,
  onShowSelectedRun,
}: RecentRunsPanelProps) => {
  return (
    <section className="panel recent-runs" id="recent-runs">
      <div className="section-head">
        <div>
          <h2>Recent runs</h2>
          <p className="muted small">Historical runs with triage status for review tracking.</p>
        </div>
      </div>
      <div className="runs-filter-bar">
        <div className="runs-filter-options">
          {RUNS_REVIEW_FILTER_OPTIONS.map((option) => {
            const count = runsFilterCounts[option.value];
            const isActive = runsFilter === option.value;
            return (
              <button
                key={option.value}
                type="button"
                className={`runs-filter-button ${isActive ? "active" : ""}`}
                onClick={() => onRunsFilterChange(option.value)}
              >
                <span className="runs-filter-label">{option.label}</span>
                <span className="runs-filter-count">({count})</span>
              </button>
            );
          })}
        </div>
      </div>
      {runsFilter !== "all" && filteredRunsList.length > 0 && (
        <p className="runs-filter-summary small muted">
          Showing {filteredRunsList.length} of {runsList.length} runs
        </p>
      )}
      {runsListLoading ? (
        <p className="muted">Loading runs...</p>
      ) : runsListError ? (
        <div className="alert alert-inline">{runsListError}</div>
      ) : filteredRunsList.length === 0 ? (
        <p className="muted">No runs match the current filter.</p>
      ) : (
        <div className="runs-table-wrapper">
          <table className="runs-table" aria-label="Recent runs">
            <thead>
              <tr>
                <th>Run</th>
                <th>Status</th>
                <th>Review</th>
                <th>Timestamp</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {paginatedRunsList.map((runEntry) => {
                const isSelected = selectedRunId === runEntry.runId;
                return (
                  <tr
                    key={runEntry.runId}
                    className={`run-row ${isSelected ? "run-row-selected" : ""}`}
                    data-testid="run-entry"
                    data-run-id={runEntry.runId}
                    onClick={() => onRunSelection(runEntry.runId)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onRunSelection(runEntry.runId);
                      }
                    }}
                    tabIndex={0}
                    role="button"
                    aria-pressed={isSelected}
                    aria-label={`Run ${runEntry.label}, ${runEntry.reviewStatus}, selected: ${isSelected}`}
                  >
                    <td>
                      <div className="run-cell-main">
                        <strong>Run {runEntry.label}</strong>
                        <span className="muted small">ID {runEntry.runId}</span>
                      </div>
                    </td>
                    <td>
                      <span className={statusClass(runEntry.reviewStatus)}>
                        {runEntry.reviewStatus}
                      </span>
                    </td>
                    <td>
                      {runEntry.reviewDownloadPath ? (
                        <a
                          href={artifactUrl(runEntry.reviewDownloadPath)}
                          className="row-action row-action--secondary"
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                        >
                          Download
                        </a>
                      ) : (
                        <span className="run-action-empty" aria-label="No action available">—</span>
                      )}
                    </td>
                    <td>
                      {runEntry.timestamp ? (
                        <div className="run-cell-timestamp">
                          <span className="recency">{relativeRecency(runEntry.timestamp)}</span>
                          <span className="absolute" title={formatTimestamp(runEntry.timestamp)}>
                            {formatTimestamp(runEntry.timestamp)}
                          </span>
                        </div>
                      ) : (
                        <span className="muted small">—</span>
                      )}
                    </td>
                    <td>
                      {runEntry.reviewStatus === "no-executions" ? (
                        <button
                          type="button"
                          className="row-action row-action--primary"
                          onClick={(e) => {
                            e.stopPropagation();
                            onBatchExecution(runEntry.runId);
                          }}
                          disabled={executingBatchRunId === runEntry.runId}
                        >
                          {executingBatchRunId === runEntry.runId ? "Running…" : "Execute"}
                        </button>
                      ) : (
                        <span className="run-action-empty" aria-label="No action available">—</span>
                      )}
                      {batchExecutionError[runEntry.runId] && (
                        <p className="runs-execution-error">
                          {batchExecutionError[runEntry.runId]}
                        </p>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <Pagination
        currentPage={runsPage}
        totalPages={totalRunsPages}
        totalItems={filteredRunsList.length}
        pageSize={runsPageSize}
        pageSizeOptions={[5, 10, 20] as const}
        onPageChange={onRunsPageChange}
        onPageSizeChange={onRunsPageSizeChange}
        label="Runs"
      />
      {/* Detached mode notice - shown only when operator is detached AND selected run is not visible on current page */}
      {!isRunsListFollowingSelection && selectedRunId && !isSelectedRunVisibleOnCurrentRunsPage && (
        <div className="runs-detached-notice">
          <span className="muted small">
            Browsing page {runsPage} of {totalRunsPages} · Selected: Run {runsList.find(r => r.runId === selectedRunId)?.runLabel ?? selectedRunId}
          </span>
          <button
            type="button"
            className="link tiny"
            onClick={onShowSelectedRun}
          >
            Show selected run
          </button>
        </div>
      )}
    </section>
  );
};

// ---------------------------------------------------------------------------
// RunSummaryPanel
// ---------------------------------------------------------------------------

// Status variant types (must match App.tsx's NextCheckStatusVariant)
type RunSummaryNextCheckStatusVariant = "safe" | "approval" | "approved" | "duplicate" | "stale";

// Status label function (must match App.tsx's nextCheckStatusLabel)
const runSummaryNextCheckStatusLabel = (variant: RunSummaryNextCheckStatusVariant): string => {
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

// Format age duration (abbreviated)
const formatAgeDuration = (minutes: number): string => {
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
};

// Determine freshness level for timestamp (must match App.tsx's isStaleTimestamp)
const isStaleTimestamp = (timestamp: string | null | undefined): boolean => {
  if (!timestamp) return true;
  const ageMinutes = dayjs().diff(dayjs(timestamp), "minute");
  return ageMinutes >= 10; // >=10 minutes considered stale (matches App.tsx FRESHNESS_THRESHOLD_MINUTES)
};

export type RunSummaryPanelProps = {
  run: RunPayload;
  isSelectedRunLatest: boolean;
  selectedClusterLabel: string | null;
  onFocusClusterForNextChecks: (clusterLabel?: string | null) => void;
  // Computed stats that App.tsx derives from run and context
  runSummaryStats: { label: string; value: string | number }[];
  runStatsSummary: string;
  runLlmStatsLine: React.ReactNode;
  historicalLlmStatsLine: React.ReactNode | null;
  providerBreakdown: string | null;
  // Plan-related derived values
  runPlan: RunPayload["nextCheckPlan"];
  runPlanCandidates: NextCheckPlanCandidate[];
  planSummaryText: string;
  planStatusText: string | null;
  plannerReasonText: string;
  plannerHint: string | null;
  plannerNextActionHint: string | null;
  plannerArtifactUrl: string | null;
  planCandidateCountLabel: string;
  discoveryVariantOrder: NextCheckStatusVariant[];
  discoveryVariantCounts: Record<NextCheckStatusVariant, number>;
  discoveryClusters: string[];
};

export const RunSummaryPanel = ({
  run,
  isSelectedRunLatest,
  selectedClusterLabel,
  onFocusClusterForNextChecks,
  runSummaryStats,
  runStatsSummary,
  runLlmStatsLine,
  historicalLlmStatsLine,
  providerBreakdown,
  runPlan,
  runPlanCandidates,
  planSummaryText,
  planStatusText,
  plannerReasonText,
  plannerHint,
  plannerNextActionHint,
  plannerArtifactUrl,
  planCandidateCountLabel,
  discoveryVariantOrder,
  discoveryVariantCounts,
  discoveryClusters,
}: RunSummaryPanelProps) => {
  const runFresh = !isStaleTimestamp(run.timestamp);
  const runAgeMinutes = Math.floor(dayjs().diff(dayjs(run.timestamp), "minute"));

  return (
    <section className="panel run-summary" id="run-detail">
      <div className="run-summary-head">
        <div>
          <p className="eyebrow">Run summary</p>
          <h2>{run.label}</h2>
          <p className="muted tiny run-summary-collector">Collector {run.collectorVersion}</p>
        </div>
        <div className="run-summary-freshness">
          <p className="muted small">{formatTimestamp(run.timestamp)}</p>
        </div>
      </div>
      <div className="run-summary-metrics">
        <div className="run-summary-stats">
          {runSummaryStats.map((stat) => (
            <article
              className="run-stat-card"
              key={stat.label}
              aria-label={`${stat.label}: ${stat.value}`}
            >
              <strong>{stat.value}</strong>
              <span>{stat.label}</span>
            </article>
          ))}
        </div>
        <p className="run-duration-summary muted small">{runStatsSummary}</p>
      </div>
      <div className="run-summary-llm">
        <div className="run-summary-llm-heading">
          <p className="eyebrow">LLM telemetry</p>
          <span className="muted tiny">Provider call metrics from artifacts</span>
        </div>
        <div className="llm-current-line">
          {runLlmStatsLine}
          {providerBreakdown && (
            <p className="llm-provider-breakdown muted tiny">Providers: {providerBreakdown}</p>
          )}
        </div>
        {historicalLlmStatsLine && (
          <details className="llm-historical">
            <summary>Retained history stats</summary>
            {historicalLlmStatsLine}
          </details>
        )}
      </div>
      <div className="artifact-strip run-artifacts">
        {run.artifacts.map((artifact) => {
          const url = artifactUrl(artifact.path);
          return (
            url && (
              <a
                key={artifact.label}
                className="artifact-link run-artifact-link"
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
      <div className="run-summary-next-checks">
        <div className="run-summary-next-checks-head">
          <div>
            <p className="eyebrow">Next checks</p>
            <h3>Planner candidates</h3>
            {runPlan ? (
              <>
                <p className="muted tiny">{planSummaryText}</p>
                {planStatusText ? (
                  <p className="muted tiny">Planner status: {planStatusText}</p>
                ) : null}
              </>
            ) : (
              <p className="muted tiny">{plannerReasonText}</p>
            )}
            {plannerNextActionHint ? (
              <p className="muted tiny">{plannerNextActionHint}</p>
            ) : null}
            {plannerArtifactUrl ? (
              <p className="muted tiny">
                <a className="link" href={plannerArtifactUrl} target="_blank" rel="noreferrer">
                  View planner artifact
                </a>
              </p>
            ) : null}
            {runPlan && runPlanCandidates.length ? (
              <p className="muted tiny">{planCandidateCountLabel}</p>
            ) : null}
          </div>
          <button
            type="button"
            className="run-summary-next-checks-button"
            onClick={() => onFocusClusterForNextChecks()}
            disabled={!runPlan}
          >
            Review next checks
          </button>
        </div>
        {!runPlan ? (
          <>
            <p className="muted small">No next checks generated for this run.</p>
            {plannerHint ? (
              <p className="muted tiny">{plannerHint}</p>
            ) : null}
          </>
        ) : runPlanCandidates.length ? (
          <>
            <div className="run-summary-next-checks-stats">
              {discoveryVariantOrder.map((variant) => {
                const count = discoveryVariantCounts[variant];
                if (!count) {
                  return null;
                }
                return (
                  <span
                    key={variant}
                    className={`next-check-discovery-pill next-check-discovery-pill-${variant}`}
                  >
                    <strong>{count}</strong>
                    <span>{runSummaryNextCheckStatusLabel(variant)}</span>
                  </span>
                );
              })}
            </div>
            <div className="run-summary-next-checks-clusters">
              <p className="muted tiny">
                Affected cluster{discoveryClusters.length === 1 ? "" : "s"}: {discoveryClusters.length || "None"}
              </p>
              <div className="next-check-cluster-tags">
                {discoveryClusters.length ? (
                  discoveryClusters.map((cluster) => (
                    <button
                      type="button"
                      className="next-check-cluster-badge"
                      key={cluster}
                      onClick={() => onFocusClusterForNextChecks(cluster)}
                    >
                      {cluster}
                    </button>
                  ))
                ) : (
                  <p className="muted small">
                    Planner candidates do not target a specific cluster.
                  </p>
                )}
              </div>
            </div>
          </>
        ) : (
          <p className="muted small">Planner created no candidates for this run.</p>
        )}
      </div>
      {!isSelectedRunLatest && (
        <div className="alert alert-inline alert-past-run">
          This is a past run collected {formatAgeDuration(dayjs().diff(run.timestamp, "minute"))} ago.
        </div>
      )}
      {isSelectedRunLatest && !runFresh && (
        <div className="alert alert-inline">
          Latest run is {runAgeMinutes} minute{runAgeMinutes === 1 ? "" : "s"} old; ensure the scheduler is running.
        </div>
      )}
    </section>
  );
};
