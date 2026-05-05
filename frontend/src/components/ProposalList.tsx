import { useMemo } from "react";
import type { ProposalEntry } from "../types";
import { artifactUrl, statusClass, truncateText } from "../utils";
import { confidenceWeight, priorityLabel } from "../utils/selectors";

export type { ProposalEntry };

type SortKey = "proposalId" | "confidence" | "status";

export const ProposalList = ({
  proposals,
  filter,
  sortKey,
  searchText,
  expanded,
  toggle,
}: {
  proposals: ProposalEntry[];
  filter: string;
  sortKey: SortKey;
  searchText: string;
  expanded: Set<string>;
  toggle: (id: string) => void;
}) => {
  const visible = useMemo(() => {
    return proposals
      .filter((entry) => {
        if (filter !== "all" && entry.status !== filter) {
          return false;
        }
        if (!searchText) {
          return true;
        }
        const needle = searchText.toLowerCase();
        return (
          entry.target.toLowerCase().includes(needle) ||
          entry.rationale.toLowerCase().includes(needle)
        );
      })
      .sort((a, b) => {
        if (sortKey === "confidence") {
          return confidenceWeight(a.confidence) - confidenceWeight(b.confidence);
        }
        return a[sortKey].localeCompare(b[sortKey]);
      });
  }, [filter, proposals, searchText, sortKey]);

  if (!visible.length) {
    return <p className="muted">No proposals match the current filters.</p>;
  }

  return (
    <div className="proposal-table">
      {visible.map((proposal) => {
        const expandedEntry = expanded.has(proposal.proposalId);
        const summaryRationale = expandedEntry
          ? proposal.rationale
          : truncateText(proposal.rationale, 180);
        return (
          <article
            className="proposal-row"
            key={proposal.proposalId}
            data-testid="proposal-row"
            data-proposal-id={proposal.proposalId}
          >
            <div className="proposal-row-summary">
              <div>
                <p className="eyebrow compact">{proposal.target}</p>
                <strong>{proposal.proposalId}</strong>
                <div className="proposal-status-line">
                  <span className={statusClass(proposal.status)}>{proposal.status}</span>
                  <span
                    className={`confidence-badge level-${priorityLabel(proposal.confidence)}`}
                  >
                    {proposal.confidence} confidence
                  </span>
                </div>
              </div>
              <div className="proposal-row-actions">
                <span className="small">Run {proposal.sourceRunId}</span>
                <button type="button" className="text-button" onClick={() => toggle(proposal.proposalId)}>
                  {expandedEntry ? "Hide details" : "Show details"}
                </button>
              </div>
            </div>
            <div className={`proposal-row-details ${expandedEntry ? "is-visible" : ""}`}>
              <p className="proposal-rationale">{summaryRationale}</p>
              <div className="proposal-meta-grid">
                <div>
                  <p className="small">Expected benefit</p>
                  <p className="small">{proposal.expectedBenefit}</p>
                </div>
                <div>
                  <p className="small">Lifecycle</p>
                  <div className="lifecycle-row">
                    {proposal.lifecycle.map((step) => (
                      <span className="lifecycle-chip" key={`${step.status}-${step.timestamp}`}>
                        {step.status}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="small">Latest note</p>
                  <p className="small">{proposal.latestNote || "n/a"}</p>
                </div>
              </div>
              <div className="proposal-artifacts">
                {proposal.artifacts.map((artifact) => {
                  const url = artifactUrl(artifact.path);
                  return (
                    url && (
                      <a
                        key={artifact.label}
                        className="artifact-chip"
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
            </div>
          </article>
        );
      })}
    </div>
  );
};