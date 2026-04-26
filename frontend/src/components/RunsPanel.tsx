/**
 * RunsPanel.tsx
 *
 * Contains two panel components:
 *   - RecentRunsPanel: displays the runs table with filter bar, pagination,
 *     and detached-mode notice
 *   - RunSummaryPanel: displays the selected run header, summary stats,
 *     LLM telemetry, artifacts, and next-checks preview
 *
 * RunSummaryPanel composes smaller components from run-summary/ directory
 * (E1-3b-step15 extraction).
 */

import type { NextCheckPlanCandidate, NextCheckStatusVariant, RunPayload, RunsListEntry } from "../types";
import { artifactUrl, formatTimestamp, relativeRecency, statusClass } from "../utils";
import {
  RunHeader,
  RunKpiStrip,
  LlmTelemetryCard,
  NextChecksSummaryCard,
  PastRunNotice,
} from "./run-summary";

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

  // Handler for "Review next checks" button
  const handleReviewNextChecks = () => {
    onFocusClusterForNextChecks();
  };

  return (
    <section className="panel run-summary" id="run-detail">
      {/* Extracted components (E1-3b-step15) */}
      <RunHeader
        label={run.label}
        collectorVersion={run.collectorVersion}
        timestamp={run.timestamp}
      />
      <RunKpiStrip
        stats={runSummaryStats}
        durationSummary={runStatsSummary}
      />
      <LlmTelemetryCard
        llmStatsLine={runLlmStatsLine}
        historicalLlmStatsLine={historicalLlmStatsLine}
        providerBreakdown={providerBreakdown}
      />
      {/* Artifacts strip - inline as it's a simple mapping */}
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
      <NextChecksSummaryCard
        runPlan={runPlan ? {
          summary: runPlan.summary,
          artifactPath: runPlan.artifactPath,
          status: runPlan.status,
          candidateCount: runPlan.candidateCount,
        } : null}
        runPlanCandidates={runPlanCandidates}
        planSummaryText={planSummaryText}
        planStatusText={planStatusText}
        plannerReasonText={plannerReasonText}
        plannerHint={plannerHint}
        plannerNextActionHint={plannerNextActionHint}
        plannerArtifactUrl={plannerArtifactUrl}
        planCandidateCountLabel={planCandidateCountLabel}
        discoveryVariantOrder={discoveryVariantOrder}
        discoveryVariantCounts={discoveryVariantCounts}
        discoveryClusters={discoveryClusters}
        onReviewNextChecks={handleReviewNextChecks}
        onFocusClusterForNextChecks={onFocusClusterForNextChecks}
      />
      <PastRunNotice
        isSelectedRunLatest={isSelectedRunLatest}
        runFresh={runFresh}
        runTimestamp={run.timestamp}
      />
    </section>
  );
};
