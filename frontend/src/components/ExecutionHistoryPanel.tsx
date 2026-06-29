/**
 * ExecutionHistoryPanel component and related execution history utilities.
 *
 * This module is a thin facade that re-exports from the executionHistory/ subdirectory
 * for backward compatibility with existing imports.
 *
 * New code should prefer imports from "./executionHistory" directly.
 */

import { useMemo } from "react";
import {
  ExecutionHistoryEmptyState,
  ExecutionHistoryFilters,
  ExecutionHistoryRow,
  ExecutionHistorySummaryStrip,
  filterExecutionHistory,
  extractClustersFromHistory,
  extractCommandFamiliesFromHistory,
  computeExecutionHistoryFilterCounts,
  computeExecutionHistorySummary,
  persistExecutionHistoryFilter,
  readStoredExecutionHistoryFilter,
  EXECUTION_HISTORY_FILTER_STORAGE_KEY,
  formatDuration,
  buildExecutionEntryKey,
} from "./executionHistory";

import type {
  ExecutionHistoryPanelProps,
  ExecutionHistoryFilterState,
  ExecutionOutcomeFilter,
  UsefulnessReviewFilter,
} from "./executionHistory";

// Re-export for backward compatibility
export type { ExecutionHistoryPanelProps };
export type { ExecutionHistoryFilterState, ExecutionOutcomeFilter, UsefulnessReviewFilter };
export {
  filterExecutionHistory,
  extractClustersFromHistory,
  extractCommandFamiliesFromHistory,
  computeExecutionHistoryFilterCounts,
  computeExecutionHistorySummary,
  persistExecutionHistoryFilter,
  readStoredExecutionHistoryFilter,
  EXECUTION_HISTORY_FILTER_STORAGE_KEY,
  formatDuration,
  buildExecutionEntryKey,
};

export const ExecutionHistoryPanel = ({
  history,
  runId,
  runLabel,
  queueCandidateCount,
  highlightedKey,
  onSubmitFeedback,
  onSubmitAlertmanagerRelevanceFeedback,
  filter,
  onFilterChange,
  runQueue,
  onHighlightQueueCard,
}: ExecutionHistoryPanelProps) => {
  const filteredHistory = useMemo(
    () => filterExecutionHistory(history, filter),
    [history, filter],
  );

  const clusters = useMemo(() => extractClustersFromHistory(history), [history]);
  const commandFamilies = useMemo(() => extractCommandFamiliesFromHistory(history), [history]);
  const counts = useMemo(() => computeExecutionHistoryFilterCounts(history), [history]);

  // Compute run-scoped summary for the summary strips (based on filtered entries)
  const summary = useMemo(() => computeExecutionHistorySummary(filteredHistory), [filteredHistory]);

  const handleOutcomeChange = (value: ExecutionOutcomeFilter) => {
    onFilterChange({ ...filter, outcomeFilter: value });
  };

  const handleUsefulnessChange = (value: UsefulnessReviewFilter) => {
    onFilterChange({ ...filter, usefulnessFilter: value });
  };

  const handleClusterChange = (value: string) => {
    onFilterChange({ ...filter, clusterFilter: value });
  };

  const handleCommandFamilyChange = (value: string) => {
    onFilterChange({ ...filter, commandFamilyFilter: value });
  };

  return (
    <section className="panel execution-history-panel" id="execution-history">
      <div className="section-head">
        <div>
          <p className="eyebrow">Execution history</p>
          <h2>Check execution review</h2>
          <p className="muted small">Checks that ran in this run; review results and signal quality. Work list candidates appear here after execution.</p>
        </div>
        <div className="execution-history-context">
          <span className="muted tiny">Run {runLabel}</span>
          <span className="muted tiny">ID {runId}</span>
          <span className="muted tiny">{history.length} executed</span>
          {queueCandidateCount > 0 && history.length === 0 && (
            <span className="muted tiny">{queueCandidateCount} in work list</span>
          )}
        </div>
      </div>
      <ExecutionHistoryFilters
        filter={filter}
        counts={counts}
        clusters={clusters}
        commandFamilies={commandFamilies}
        onOutcomeChange={handleOutcomeChange}
        onUsefulnessChange={handleUsefulnessChange}
        onClusterChange={handleClusterChange}
        onCommandFamilyChange={handleCommandFamilyChange}
        filteredCount={filteredHistory.length}
        totalCount={history.length}
      />
      <ExecutionHistorySummaryStrip
        summary={summary}
        onHighlightEntry={highlightedKey !== undefined ? () => {
          // Bubble up highlight request if onHighlightEntry prop is provided in the future
        } : undefined}
      />
      {filteredHistory.length ? (
        <div className="execution-history-grid">
          {filteredHistory.map((entry) => (
            <ExecutionHistoryRow
              key={`${entry.timestamp}-${entry.artifactPath ?? entry.candidateDescription ?? ""}`}
              entry={entry}
              highlightedKey={highlightedKey}
              runQueue={runQueue}
              onHighlightQueueCard={onHighlightQueueCard}
              onSubmitFeedback={onSubmitFeedback}
              onSubmitAlertmanagerRelevanceFeedback={onSubmitAlertmanagerRelevanceFeedback}
            />
          ))}
        </div>
      ) : history.length === 0 ? (
        <ExecutionHistoryEmptyState hasHistory={false} />
      ) : (
        <ExecutionHistoryEmptyState hasHistory={true} />
      )}
    </section>
  );
};

export default ExecutionHistoryPanel;
