/**
 * WorkNextChecksLane - Presentational component for the "Work Next Checks" workflow lane.
 *
 * Displays the workflow lane header, execution history panel, and queue panel.
 * Does not own state or logic - receives all data and handlers as props.
 *
 * @module components/WorkNextChecksLane
 */
import type { NextCheckExecutionHistoryEntry, NextCheckQueueItem } from "../types";
import { ExecutionHistoryPanel } from "./ExecutionHistoryPanel";
import { QueuePanel } from "./QueuePanel";
import type { QueuePanelProps } from "./QueuePanel";
import type { ExecutionHistoryFilterState } from "./ExecutionHistoryPanel";
import { WORKFLOW_LANES } from "../utils/selectors";

// ============================================================================
// Props interface
// ============================================================================

export interface WorkNextChecksLaneProps {
  /** Whether a run is selected and loaded */
  run: { runId: string; label: string } | null;
  /** Execution history entries */
  history: NextCheckExecutionHistoryEntry[];
  /** Number of queue candidates */
  queueCandidateCount: number;
  /** Currently highlighted execution entry key */
  executionHistoryHighlightKey: string | null;
  /** Feedback submission handler */
  onSubmitFeedback: (artifactPath: string, usefulnessClass: string, summary: string | undefined) => Promise<void>;
  /** Alertmanager relevance feedback handler */
  onSubmitAlertmanagerRelevanceFeedback: (
    artifactPath: string,
    relevance: "relevant" | "not_relevant" | "noisy" | "unsure",
    summary: string | undefined
  ) => Promise<void>;
  /** Execution history filter state */
  executionHistoryFilter: ExecutionHistoryFilterState;
  /** Filter change handler */
  onExecutionHistoryFilterChange: (filter: ExecutionHistoryFilterState) => void;
  /** Queue for linking between execution history and queue panels */
  runQueue: NextCheckQueueItem[];
  /** Queue card highlight handler */
  onHighlightQueueCard: (key: string) => void;
  /** Props for the QueuePanel component */
  queuePanelProps: QueuePanelProps;
}

// ============================================================================
// Component
// ============================================================================

export const WorkNextChecksLane = ({
  run,
  history,
  queueCandidateCount,
  executionHistoryHighlightKey,
  onSubmitFeedback,
  onSubmitAlertmanagerRelevanceFeedback,
  executionHistoryFilter,
  onExecutionHistoryFilterChange,
  runQueue,
  onHighlightQueueCard,
  queuePanelProps,
}: WorkNextChecksLaneProps) => {
  return (
    <>
      {/* Workflow Lane: Work Next Checks */}
      <div className="workflow-lane-header">
        <div className="workflow-lane-label">
          <span className="workflow-lane-icon">⚡</span>
          <span className="workflow-lane-title">{WORKFLOW_LANES.work.label}</span>
        </div>
        <p className="workflow-lane-description muted small">{WORKFLOW_LANES.work.description}</p>
      </div>
      {run ? (
        <ExecutionHistoryPanel
          history={history}
          runId={run.runId}
          runLabel={run.label}
          queueCandidateCount={queueCandidateCount}
          highlightedKey={executionHistoryHighlightKey}
          onSubmitFeedback={onSubmitFeedback}
          onSubmitAlertmanagerRelevanceFeedback={onSubmitAlertmanagerRelevanceFeedback}
          filter={executionHistoryFilter}
          onFilterChange={onExecutionHistoryFilterChange}
          runQueue={runQueue}
          onHighlightQueueCard={onHighlightQueueCard}
        />
      ) : (
        <section className="panel execution-history-panel" id="execution-history">
          <div className="section-head">
            <h2>Execution review</h2>
            <p className="muted">Loading selected run…</p>
          </div>
        </section>
      )}
      {run ? (
        <QueuePanel {...queuePanelProps} />
      ) : (
        <section className="panel next-check-queue-panel" id="next-check-queue">
          <div className="section-head">
            <h2>Work list</h2>
            <p className="muted">Loading selected run…</p>
          </div>
        </section>
      )}
    </>
  );
};