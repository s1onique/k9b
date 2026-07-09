/**
 * incidents-panel-deduplication.test.tsx
 *
 * UI regression test: ensures only ONE canonical Incidents section renders
 * for the selected-run page. This test prevents the duplicate panel regression
 * that triggered this ACT.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { IncidentsOverviewSection } from "../IncidentsOverviewSection";

import { listIncidents } from "../../../../api";

// Mock the API module
vi.mock("../../../../api", () => ({
  listIncidents: vi.fn(),
}));

describe("Incidents panel deduplication", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders only ONE Incidents section for a selected run", async () => {
    vi.mocked(listIncidents).mockResolvedValue({
      incidents: [
        {
          incident_id: "inc-001",
          severity: "error",
          status: "open",
          object_kind: "Pod",
          object_name: "test-pod",
          namespace: "default",
          signal_count: 1,
          evidence_count: 0,
          review_packet: { status: "not_generated" },
          last_observed_at: "2024-01-01T00:00:00Z",
        },
      ],
    });

    render(<IncidentsOverviewSection runId="run-123" />);

    // Count how many times the header appears
    const headers = await screen.findAllByText("Incidents");
    
    // Should be exactly 1 - not 2 (no duplicate)
    expect(headers).toHaveLength(1);

    // Should have exactly one section with the testid
    const sections = await screen.findAllByTestId("incidents-overview-section");
    expect(sections).toHaveLength(1);
  });

  it("does not render multiple Incidents sections when rerendered", () => {
    vi.mocked(listIncidents).mockResolvedValue({ incidents: [] });

    const { rerender } = render(<IncidentsOverviewSection runId="run-1" />);

    // Rerender with same data
    rerender(<IncidentsOverviewSection runId="run-1" />);

    // Should still have only one header
    const headers = screen.queryAllByText("Incidents");
    expect(headers).toHaveLength(1);
  });

  it("renders exactly one incidents table when data present", async () => {
    vi.mocked(listIncidents).mockResolvedValue({
      incidents: [
        {
          incident_id: "inc-001",
          severity: "error",
          status: "open",
          object_kind: "Pod",
          object_name: "test-pod",
          namespace: "default",
          signal_count: 1,
          evidence_count: 0,
          review_packet: { status: "not_generated" },
          last_observed_at: "2024-01-01T00:00:00Z",
        },
      ],
    });

    render(<IncidentsOverviewSection runId="run-123" />);

    // Should have exactly one table wrapper
    const tableWrappers = await screen.findAllByTestId("incidents-table-wrapper");
    expect(tableWrappers).toHaveLength(1);
  });
});
