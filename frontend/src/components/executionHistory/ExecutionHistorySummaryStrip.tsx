/**
 * ExecutionHistorySummaryStrip.tsx
 *
 * Summary strip showing useful/noisy/repeated checks.
 */

import { truncateText } from "../../utils";
import type {
  ExecutionHistorySummary,
  UsefulnessReviewFilter,
} from "./executionHistoryTypes";
import { buildExecutionEntryKey } from "./executionHistoryTypes";
import type { NextCheckExecutionHistoryEntry } from "../../types";

// Limit displayed items in summary strips
const SUMMARY_ITEM_LIMIT = 3;

interface ExecutionHistorySummaryStripProps {
  summary: ExecutionHistorySummary;
  onHighlightEntry?: (entryKey: string | null) => void;
  onFilterChange?: (filter: Partial<{ usefulnessFilter: UsefulnessReviewFilter }>) => void;
}

export const ExecutionHistorySummaryStrip = ({
  summary,
  onHighlightEntry,
  onFilterChange,
}: ExecutionHistorySummaryStripProps) => {
  const hasUseful = summary.usefulChecks.length > 0;
  const hasNoisyEmpty = summary.noisyEmptyChecks.length > 0;
  const hasRepeated = summary.repeatedFailures.length > 0;

  // Don't render if no summary categories have content
  if (!hasUseful && !hasNoisyEmpty && !hasRepeated) {
    return null;
  }

  const handleEntryClick = (entry: NextCheckExecutionHistoryEntry) => {
    if (onHighlightEntry) {
      const key = buildExecutionEntryKey(entry);
      onHighlightEntry(key);
    }
  };

  const handleFilterClick = (usefulnessFilter?: UsefulnessReviewFilter) => {
    if (onFilterChange) {
      onFilterChange({
        usefulnessFilter: usefulnessFilter || "all",
      });
    }
  };

  return (
    <div className="execution-history-summary">
      {hasUseful && (
        <div className="exec-summary-strip exec-summary-strip--useful">
          <div className="exec-summary-header">
            <span className="exec-summary-label">Most useful</span>
            <span className="exec-summary-count">{summary.usefulChecks.length}</span>
          </div>
          <div className="exec-summary-items">
            {summary.usefulChecks.slice(0, SUMMARY_ITEM_LIMIT).map((entry) => (
              <button
                key={buildExecutionEntryKey(entry)}
                type="button"
                className="exec-summary-item"
                onClick={() => handleEntryClick(entry)}
                title={entry.candidateDescription || "Check"}
              >
                <span className="exec-summary-item-text">
                  {truncateText(entry.candidateDescription || "Check", 40)}
                </span>
                {entry.clusterLabel && (
                  <span className="exec-summary-item-meta">{entry.clusterLabel}</span>
                )}
              </button>
            ))}
            {summary.usefulChecks.length > SUMMARY_ITEM_LIMIT && (
              <button
                type="button"
                className="exec-summary-more"
                onClick={() => handleFilterClick("useful")}
              >
                +{summary.usefulChecks.length - SUMMARY_ITEM_LIMIT} more
              </button>
            )}
          </div>
        </div>
      )}

      {hasNoisyEmpty && (
        <div className="exec-summary-strip exec-summary-strip--noisy">
          <div className="exec-summary-header">
            <span className="exec-summary-label">Noisy / empty</span>
            <span className="exec-summary-count">{summary.noisyEmptyChecks.length}</span>
          </div>
          <div className="exec-summary-items">
            {summary.noisyEmptyChecks.slice(0, SUMMARY_ITEM_LIMIT).map((entry) => (
              <button
                key={buildExecutionEntryKey(entry)}
                type="button"
                className="exec-summary-item"
                onClick={() => handleEntryClick(entry)}
                title={entry.candidateDescription || "Check"}
              >
                <span className={`exec-summary-item-badge usefulness-badge-${entry.usefulnessClass}`}>
                  {entry.usefulnessClass}
                </span>
                <span className="exec-summary-item-text">
                  {truncateText(entry.candidateDescription || "Check", 35)}
                </span>
              </button>
            ))}
            {summary.noisyEmptyChecks.length > SUMMARY_ITEM_LIMIT && (
              <button
                type="button"
                className="exec-summary-more"
                onClick={() => handleFilterClick("noisy")}
              >
                +{summary.noisyEmptyChecks.length - SUMMARY_ITEM_LIMIT} more
              </button>
            )}
          </div>
        </div>
      )}

      {hasRepeated && (
        <div className="exec-summary-strip exec-summary-strip--repeated">
          <div className="exec-summary-header">
            <span className="exec-summary-label">Repeated failures</span>
            <span className="exec-summary-count">
              {summary.repeatedFailures.reduce((sum, g) => sum + g.count, 0)}
            </span>
          </div>
          <div className="exec-summary-items">
            {summary.repeatedFailures.slice(0, SUMMARY_ITEM_LIMIT).map((group) => (
              <button
                key={group.failurePattern}
                type="button"
                className="exec-summary-item"
                onClick={() => handleEntryClick(group.entries[0])}
                title={`${group.count} similar failures: ${group.label}`}
              >
                <span className="exec-summary-item-badge exec-summary-item-badge--repeated">
                  ×{group.count}
                </span>
                <span className="exec-summary-item-text">{group.label}</span>
              </button>
            ))}
            {summary.repeatedFailures.length > SUMMARY_ITEM_LIMIT && (
              <span className="exec-summary-more">
                +{summary.repeatedFailures.length - SUMMARY_ITEM_LIMIT} more patterns
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ExecutionHistorySummaryStrip;
