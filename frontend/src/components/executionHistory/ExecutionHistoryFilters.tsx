/**
 * ExecutionHistoryFilters.tsx
 *
 * Filter controls for ExecutionHistoryPanel.
 */

import type {
  ExecutionHistoryFilterState,
  ExecutionHistoryFilterCounts,
  ExecutionOutcomeFilter,
  UsefulnessReviewFilter,
} from "./executionHistoryTypes";

export { EXECUTION_OUTCOME_FILTER_OPTIONS, USEFULNESS_REVIEW_FILTER_OPTIONS } from "./executionHistoryFiltersData";
export type { ExecutionOutcomeFilter, UsefulnessReviewFilter };

interface ExecutionHistoryFiltersProps {
  filter: ExecutionHistoryFilterState;
  counts: ExecutionHistoryFilterCounts;
  clusters: string[];
  commandFamilies: string[];
  onOutcomeChange: (value: ExecutionOutcomeFilter) => void;
  onUsefulnessChange: (value: UsefulnessReviewFilter) => void;
  onClusterChange: (value: string) => void;
  onCommandFamilyChange: (value: string) => void;
  filteredCount: number;
  totalCount: number;
}

export const ExecutionHistoryFilters = ({
  filter,
  counts,
  clusters,
  commandFamilies,
  onOutcomeChange,
  onUsefulnessChange,
  onClusterChange,
  onCommandFamilyChange,
  filteredCount,
  totalCount,
}: ExecutionHistoryFiltersProps) => {
  return (
    <div className="execution-history-filters">
      <div className="filter-group">
        <label className="filter-label" htmlFor="exec-outcome-filter">Outcome:</label>
        <select
          id="exec-outcome-filter"
          className="filter-select"
          value={filter.outcomeFilter}
          onChange={(e) => onOutcomeChange(e.target.value as ExecutionOutcomeFilter)}
        >
          {EXECUTION_OUTCOME_FILTER_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label} ({counts.outcome[opt.value]})
            </option>
          ))}
        </select>
      </div>
      <div className="filter-group">
        <label className="filter-label" htmlFor="exec-usefulness-filter">Reviewed:</label>
        <select
          id="exec-usefulness-filter"
          className="filter-select"
          value={filter.usefulnessFilter}
          onChange={(e) => onUsefulnessChange(e.target.value as UsefulnessReviewFilter)}
        >
          {USEFULNESS_REVIEW_FILTER_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label} ({counts.usefulness[opt.value]})
            </option>
          ))}
        </select>
      </div>
      {clusters.length > 1 && (
        <div className="filter-group">
          <label className="filter-label" htmlFor="exec-cluster-filter">Cluster:</label>
          <select
            id="exec-cluster-filter"
            className="filter-select"
            value={filter.clusterFilter}
            onChange={(e) => onClusterChange(e.target.value)}
          >
            <option value="all">All clusters</option>
            {clusters.map((cluster) => (
              <option key={cluster} value={cluster}>{cluster}</option>
            ))}
          </select>
        </div>
      )}
      {commandFamilies.length > 1 && (
        <div className="filter-group">
          <label className="filter-label" htmlFor="exec-cmd-family-filter">Command:</label>
          <select
            id="exec-cmd-family-filter"
            className="filter-select"
            value={filter.commandFamilyFilter}
            onChange={(e) => onCommandFamilyChange(e.target.value)}
          >
            <option value="all">All commands</option>
            {commandFamilies.map((family) => (
              <option key={family} value={family}>{family}</option>
            ))}
          </select>
        </div>
      )}
      {filteredCount !== totalCount && (
        <span className="filter-count">
          Showing {filteredCount} of {totalCount}
        </span>
      )}
    </div>
  );
};

export default ExecutionHistoryFilters;
