/**
 * ExecutionHistoryEmptyState.tsx
 *
 * Empty state component for ExecutionHistoryPanel.
 */

interface ExecutionHistoryEmptyStateProps {
  hasHistory?: boolean;
}

export const ExecutionHistoryEmptyState = ({ hasHistory = false }: ExecutionHistoryEmptyStateProps) => {
  if (hasHistory) {
    return <p className="muted">No entries match the current filters. Try adjusting your filters.</p>;
  }
  return <p className="muted">No execution history for this run yet. Execute a check from the Work list above.</p>;
};

export default ExecutionHistoryEmptyState;
