import { render, screen } from "@testing-library/react";
import { describe, test, vi } from "vitest";
import { ProposalList } from "../App";
import { sampleProposals } from "./fixtures";

const renderProposalList = (props: Parameters<typeof ProposalList>[0]) =>
  render(<ProposalList {...props} />);

describe("ProposalList", () => {
  test("filters proposals by status and search text", () => {
    const toggle = vi.fn();
    const proposals = sampleProposals.proposals;
    renderProposalList({
      proposals,
      filter: "pending",
      sortKey: "proposalId",
      searchText: "cluster-a",
      expanded: new Set<string>(),
      toggle,
    });

    expect(screen.getByRole("heading", { level: 3, name: "critical-01" })).toBeInTheDocument();
    expect(screen.queryByText("medium-01")).toBeNull();
    expect(screen.queryByText("low-01")).toBeNull();
  });

  test("orders proposals by confidence when selected", () => {
    const toggle = vi.fn();
    const proposals = sampleProposals.proposals;
    renderProposalList({
      proposals,
      filter: "all",
      sortKey: "confidence",
      searchText: "",
      expanded: new Set<string>(),
      toggle,
    });

    const headings = screen.getAllByRole("heading", { level: 3 });
    expect(headings.map((heading) => heading.textContent)).toEqual([
      "critical-01",
      "medium-01",
      "low-01",
    ]);
  });
});
