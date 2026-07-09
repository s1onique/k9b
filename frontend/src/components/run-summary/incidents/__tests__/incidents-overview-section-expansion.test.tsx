/**
 * incidents-overview-section-expansion.test.tsx
 *
 * UI regression test: ensures expand/collapse ARIA behavior works correctly.
 * Tests WAI-ARIA accordion pattern compliance.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { IncidentsOverviewSection } from "../IncidentsOverviewSection";

// Mock the API module
vi.mock("../../../api", () => ({
  listIncidents: vi.fn(),
}));

import { listIncidents } from "../../../api";

describe("Incidents expand/collapse ARIA behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockIncidents = [
    {
      incident_id: "inc-expand-001",
      severity: "error",
      status: "open",
      object_kind: "Pod",
      object_name: "expandable-pod-1",
      namespace: "default",
      signal_count: 5,
      evidence_count: 2,
      review_packet: { status: "not_generated" },
      last_observed_at: "2024-01-15T10:30:00Z",
    },
    {
      incident_id: "inc-expand-002",
      severity: "warning",
      status: "investigating",
      object_kind: "Deployment",
      object_name: "expandable-deployment-2",
      namespace: "production",
      signal_count: 3,
      evidence_count: 1,
      review_packet: { status: "available" },
      last_observed_at: "2024-01-15T09:00:00Z",
    },
  ];

  it("expands an incident row with aria-expanded toggling to true", async () => {
    vi.mocked(listIncidents).mockResolvedValue({ incidents: mockIncidents });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      expect(screen.getByTestId("incident-row-inc-expand-001")).toBeInTheDocument();
    });

    // Find the expand button for the first incident
    const expandButton = screen.getByRole("button", { name: "Expand" });
    expect(expandButton).toHaveAttribute("aria-expanded", "false");

    // Click to expand
    expandButton.click();

    // Button should now show aria-expanded="true"
    await waitFor(() => {
      expect(expandButton).toHaveAttribute("aria-expanded", "true");
    });
  });

  it("collapses an expanded incident row", async () => {
    vi.mocked(listIncidents).mockResolvedValue({ incidents: mockIncidents });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      expect(screen.getByTestId("incident-row-inc-expand-001")).toBeInTheDocument();
    });

    // Expand first
    const expandButton = screen.getByRole("button", { name: "Expand" });
    expandButton.click();

    await waitFor(() => {
      expect(expandButton).toHaveAttribute("aria-expanded", "true");
    });

    // Collapse
    const collapseButton = screen.getByRole("button", { name: "Collapse" });
    collapseButton.click();

    await waitFor(() => {
      expect(collapseButton).toHaveAttribute("aria-expanded", "false");
    });
  });

  it("uses aria-controls pointing to the details element ID", async () => {
    vi.mocked(listIncidents).mockResolvedValue({ incidents: [mockIncidents[0]] });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      expect(screen.getByTestId("incident-row-inc-expand-001")).toBeInTheDocument();
    });

    const expandButton = screen.getByRole("button", { name: "Expand" });
    
    // aria-controls should point to the details ID
    const detailsId = `incident-details-inc-expand-001`;
    expect(expandButton).toHaveAttribute("aria-controls", detailsId);
  });

  it("shows expanded details content when expanded", async () => {
    vi.mocked(listIncidents).mockResolvedValue({ incidents: [mockIncidents[0]] });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      expect(screen.getByTestId("incident-row-inc-expand-001")).toBeInTheDocument();
    });

    // Expand the incident
    const expandButton = screen.getByRole("button", { name: "Expand" });
    expandButton.click();

    // Expanded row should appear with details
    await waitFor(() => {
      const expandedRow = screen.getByTestId("incident-expanded-inc-expand-001");
      expect(expandedRow).toBeInTheDocument();
      
      // Details should include incident ID
      expect(expandedRow).toHaveTextContent("inc-expand-001");
      expect(expandedRow).toHaveTextContent("Signal Count");
      expect(expandedRow).toHaveTextContent("Evidence Count");
    });
  });

  it("allows multiple incidents to be expanded simultaneously", async () => {
    vi.mocked(listIncidents).mockResolvedValue({ incidents: mockIncidents });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      expect(screen.getByTestId("incident-row-inc-expand-001")).toBeInTheDocument();
      expect(screen.getByTestId("incident-row-inc-expand-002")).toBeInTheDocument();
    });

    // Expand both incidents
    const buttons = screen.getAllByRole("button", { name: "Expand" });
    buttons[0].click();
    buttons[1].click();

    // Both should be expanded
    await waitFor(() => {
      const expandedRows = screen.getAllByTestId(/^incident-expanded-/);
      expect(expandedRows).toHaveLength(2);
    });
  });

  it("collapses expansions when changing page", async () => {
    // Create enough incidents to need pagination
    const manyIncidents = Array.from({ length: 15 }, (_, i) => ({
      incident_id: `inc-page-${i}`,
      severity: "error",
      status: "open",
      object_kind: "Pod",
      object_name: `pod-${i}`,
      namespace: "default",
      signal_count: 1,
      evidence_count: 0,
      review_packet: { status: "not_generated" },
      last_observed_at: "2024-01-01T00:00:00Z",
    }));

    vi.mocked(listIncidents).mockResolvedValue({ incidents: manyIncidents });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      expect(screen.getByTestId("incident-table-wrapper")).toBeInTheDocument();
    });

    // Expand first incident
    const expandButton = screen.getByRole("button", { name: "Expand" });
    expandButton.click();

    await waitFor(() => {
      expect(screen.getByTestId("incident-expanded-inc-page-0")).toBeInTheDocument();
    });

    // Go to page 2
    const page2Button = screen.getByRole("button", { name: /Go to page 2/ });
    page2Button.click();

    // Expanded row should be gone
    await waitFor(() => {
      expect(screen.queryByTestId("incident-expanded-inc-page-0")).not.toBeInTheDocument();
    });
  });
});
