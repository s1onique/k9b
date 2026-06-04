/**
 * AppProposalsSection Component
 *
 * Proposals section with controls and list.
 * Extracted from App.tsx to reduce component size.
 */

import { ProposalList } from "../components/ProposalList";
import { ProposalControls } from "./ProposalControls";
import type { ProposalStatus, ProposalEntry } from "../types";

type SortKey = "proposalId" | "confidence" | "status";

export interface AppProposalsSectionProps {
  proposals: ProposalEntry[];
  statusFilter: string;
  sortKey: SortKey;
  searchText: string;
  statusOptions: ProposalStatus[];
  expandedProposals: Record<string, boolean>;
  onStatusFilterChange: (event: React.ChangeEvent<HTMLSelectElement>) => void;
  onSortKeyChange: (event: React.ChangeEvent<HTMLSelectElement>) => void;
  onSearchTextChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onToggleProposal: (id: string) => void;
}

export function AppProposalsSection({
  proposals,
  statusFilter,
  sortKey,
  searchText,
  statusOptions,
  expandedProposals,
  onStatusFilterChange,
  onSortKeyChange,
  onSearchTextChange,
  onToggleProposal,
}: AppProposalsSectionProps) {
  return (
    <section className="panel" id="proposals">
      <div className="section-head">
        <h2>Action proposals</h2>
        <span className="muted tiny">
          Findings surfaced for triage; actionable improvements for the system.
        </span>
      </div>
      <ProposalControls
        statusFilter={statusFilter}
        onStatusFilterChange={onStatusFilterChange}
        sortKey={sortKey}
        onSortKeyChange={onSortKeyChange}
        searchText={searchText}
        onSearchTextChange={onSearchTextChange}
        statusOptions={statusOptions}
      />
      <ProposalList
        proposals={proposals}
        filter={statusFilter}
        sortKey={sortKey}
        searchText={searchText}
        expanded={expandedProposals}
        toggle={onToggleProposal}
      />
    </section>
  );
}