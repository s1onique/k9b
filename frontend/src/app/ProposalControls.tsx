/**
 * ProposalControls Component
 *
 * Filter and sort controls for the proposals section.
 * Extracted from App.tsx to reduce component size.
 */

import type { ProposalStatus } from "../types";

export interface ProposalControlsProps {
  statusFilter: string;
  onStatusFilterChange: (event: React.ChangeEvent<HTMLSelectElement>) => void;
  sortKey: string;
  onSortKeyChange: (event: React.ChangeEvent<HTMLSelectElement>) => void;
  searchText: string;
  onSearchTextChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  statusOptions: ProposalStatus[];
}

export function ProposalControls({
  statusFilter,
  onStatusFilterChange,
  sortKey,
  onSortKeyChange,
  searchText,
  onSearchTextChange,
  statusOptions,
}: ProposalControlsProps) {
  return (
    <div className="proposal-controls">
      <label>
        Status
        <select value={statusFilter} onChange={onStatusFilterChange}>
          {statusOptions.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
      </label>
      <label>
        Sort
        <select value={sortKey} onChange={onSortKeyChange}>
          <option value="proposalId">Proposal ID</option>
          <option value="confidence">Confidence</option>
          <option value="status">Status</option>
        </select>
      </label>
      <label>
        Search
        <input
          value={searchText}
          onChange={onSearchTextChange}
          placeholder="Target or rationale"
        />
      </label>
    </div>
  );
}