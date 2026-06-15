/**
 * useAppProposalSectionProps - Hook for deriving proposal section props in App.tsx
 *
 * Extracts the construction of AppProposalsSection props from App.tsx
 * to reduce component size and move toward LLM-friendly limits.
 *
 * Preserves the original event handler behavior exactly:
 * - status select uses event.target.value directly
 * - sort select casts event.target.value as SortKey
 * - search input uses event.target.value directly
 *
 * Does NOT alter AppProposalsSection, ProposalList, or ProposalControls behavior.
 */

import type { AppProposalsSectionProps } from "./AppProposalsSection";
import type { ProposalEntry, ProposalStatus } from "../types";

export type SortKey = "proposalId" | "confidence" | "status";

export interface UseAppProposalSectionPropsArgs {
  /** Proposals payload with list and metadata (may be null during initial load) */
  proposals: { proposals: ProposalEntry[] } | null;
  /** Current status filter value */
  statusFilter: string;
  /** Current sort key */
  sortKey: SortKey;
  /** Current search text */
  searchText: string;
  /** Available status options for the filter dropdown */
  statusOptions: ProposalStatus[];
  /** Map of proposal IDs to expanded state */
  expandedProposals: Record<string, boolean>;
  /** Setter for status filter */
  setStatusFilter: (value: string) => void;
  /** Setter for sort key */
  setSortKey: (value: SortKey) => void;
  /** Setter for search text */
  setSearchText: (value: string) => void;
  /** Handler for toggling proposal expansion */
  handleToggleProposal: (id: string) => void;
}

/**
 * Derives props for AppProposalsSection from App.tsx state and setters.
 *
 * Converts event-based setters from App.tsx into typed event handlers
 * that AppProposalsSection expects.
 */
export function useAppProposalSectionProps({
  proposals,
  statusFilter,
  sortKey,
  searchText,
  statusOptions,
  expandedProposals,
  setStatusFilter,
  setSortKey,
  setSearchText,
  handleToggleProposal,
}: UseAppProposalSectionPropsArgs): AppProposalsSectionProps {
  return {
    proposals: proposals?.proposals ?? [],
    statusFilter,
    sortKey,
    searchText,
    statusOptions,
    expandedProposals,
    onStatusFilterChange: (event) => setStatusFilter(event.target.value),
    onSortKeyChange: (event) => setSortKey(event.target.value as SortKey),
    onSearchTextChange: (event) => setSearchText(event.target.value),
    onToggleProposal: handleToggleProposal,
  };
}
