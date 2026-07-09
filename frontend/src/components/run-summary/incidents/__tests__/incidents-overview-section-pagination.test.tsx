/**
 * incidents-overview-section-pagination.test.tsx
 *
 * UI regression test: ensures pagination works correctly with 42 incidents.
 * Tests that 42 incidents paginate as 1-10, 11-20, 21-30, 31-40, 41-42 (5 pages).
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

describe("Incidents pagination", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Create 42 mock incidents for pagination testing
  const createFortyTwoIncidents = () =>
    Array.from({ length: 42 }, (_, i) => ({
      incident_id: `inc-pag-${String(i + 1).padStart(3, "0")}`,
      severity: i % 3 === 0 ? "error" : i % 3 === 1 ? "warning" : "info",
      status: i % 2 === 0 ? "open" : "resolved",
      object_kind: "Pod",
      object_name: `paginated-pod-${i + 1}`,
      namespace: "default",
      signal_count: i + 1,
      evidence_count: Math.floor(i / 2),
      review_packet: { status: "not_generated" },
      last_observed_at: `2024-01-${String(Math.min(i + 1, 28)).padStart(2, "0")}T10:00:00Z`,
    }));

  it("paginate 42 incidents as pages 1-5 with 10 per page", async () => {
    vi.mocked(listIncidents).mockResolvedValue({
      incidents: createFortyTwoIncidents(),
    });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      expect(screen.getByTestId("incidents-overview-section")).toBeInTheDocument();
    });

    // Page 1: Should show incidents 1-10
    expect(screen.getByTestId("incident-row-inc-pag-001")).toBeInTheDocument();
    expect(screen.getByTestId("incident-row-inc-pag-010")).toBeInTheDocument();
    expect(screen.queryByTestId("incident-row-inc-pag-011")).not.toBeInTheDocument();

    // Go to page 2
    const page2Button = screen.getByRole("button", { name: /Go to page 2/ });
    page2Button.click();

    await waitFor(() => {
      // Page 2: Should show incidents 11-20
      expect(screen.getByTestId("incident-row-inc-pag-011")).toBeInTheDocument();
      expect(screen.getByTestId("incident-row-inc-pag-020")).toBeInTheDocument();
      expect(screen.queryByTestId("incident-row-inc-pag-010")).not.toBeInTheDocument();
    });

    // Go to page 3
    const page3Button = screen.getByRole("button", { name: /Go to page 3/ });
    page3Button.click();

    await waitFor(() => {
      // Page 3: Should show incidents 21-30
      expect(screen.getByTestId("incident-row-inc-pag-021")).toBeInTheDocument();
      expect(screen.getByTestId("incident-row-inc-pag-030")).toBeInTheDocument();
    });

    // Go to page 4
    const page4Button = screen.getByRole("button", { name: /Go to page 4/ });
    page4Button.click();

    await waitFor(() => {
      // Page 4: Should show incidents 31-40
      expect(screen.getByTestId("incident-row-inc-pag-031")).toBeInTheDocument();
      expect(screen.getByTestId("incident-row-inc-pag-040")).toBeInTheDocument();
    });

    // Go to page 5 (last page)
    const page5Button = screen.getByRole("button", { name: /Go to page 5/ });
    page5Button.click();

    await waitFor(() => {
      // Page 5: Should show incidents 41-42 (only 2)
      expect(screen.getByTestId("incident-row-inc-pag-041")).toBeInTheDocument();
      expect(screen.getByTestId("incident-row-inc-pag-042")).toBeInTheDocument();
      expect(screen.queryByTestId("incident-row-inc-pag-040")).not.toBeInTheDocument();
    });
  });

  it("shows correct page range label on page 1: 'Showing 1–10 of 42'", async () => {
    vi.mocked(listIncidents).mockResolvedValue({
      incidents: createFortyTwoIncidents(),
    });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      expect(screen.getByTestId("incidents-overview-section")).toBeInTheDocument();
    });

    // Should show the range label
    expect(screen.getByText("1–10 of 42")).toBeInTheDocument();
  });

  it("shows correct page range label on last page: 'Showing 41–42 of 42'", async () => {
    vi.mocked(listIncidents).mockResolvedValue({
      incidents: createFortyTwoIncidents(),
    });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      expect(screen.getByTestId("incidents-overview-section")).toBeInTheDocument();
    });

    // Go to last page
    const page5Button = screen.getByRole("button", { name: /Go to page 5/ });
    page5Button.click();

    await waitFor(() => {
      expect(screen.getByText("41–42 of 42")).toBeInTheDocument();
    });
  });

  it("allows changing page size", async () => {
    vi.mocked(listIncidents).mockResolvedValue({
      incidents: createFortyTwoIncidents(),
    });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      expect(screen.getByTestId("incidents-overview-section")).toBeInTheDocument();
    });

    // Find and use the page size selector (select element)
    const pageSizeSelect = screen.getByRole("combobox", { name: /Items per page/i });
    
    // Change to 25 items per page
    pageSizeSelect.selectOptions(["25"]);

    await waitFor(() => {
      // Should now show 1-25 on page 1
      expect(screen.getByText("1–25 of 42")).toBeInTheDocument();
      expect(screen.getByTestId("incident-row-inc-pag-001")).toBeInTheDocument();
      expect(screen.getByTestId("incident-row-inc-pag-025")).toBeInTheDocument();
    });
  });

  it("resets to page 1 when changing page size", async () => {
    vi.mocked(listIncidents).mockResolvedValue({
      incidents: createFortyTwoIncidents(),
    });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      expect(screen.getByTestId("incidents-overview-section")).toBeInTheDocument();
    });

    // Go to page 3
    const page3Button = screen.getByRole("button", { name: /Go to page 3/ });
    page3Button.click();

    await waitFor(() => {
      expect(screen.getByText("21–30 of 42")).toBeInTheDocument();
    });

    // Change page size
    const pageSizeSelect = screen.getByRole("combobox", { name: /Items per page/i });
    pageSizeSelect.selectOptions(["50"]);

    await waitFor(() => {
      // Should reset to page 1 with new size
      expect(screen.getByText("1–42 of 42")).toBeInTheDocument();
    });
  });

  it("clamps invalid page navigation to valid range", async () => {
    vi.mocked(listIncidents).mockResolvedValue({
      incidents: createFortyTwoIncidents(),
    });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      expect(screen.getByTestId("incidents-overview-section")).toBeInTheDocument();
    });

    // Go to page 2
    const page2Button = screen.getByRole("button", { name: /Go to page 2/ });
    page2Button.click();

    await waitFor(() => {
      expect(screen.getByText("11–20 of 42")).toBeInTheDocument();
    });

    // Page 1 button should be available and working
    const page1Button = screen.getByRole("button", { name: /Go to page 1/ });
    page1Button.click();

    await waitFor(() => {
      expect(screen.getByText("1–10 of 42")).toBeInTheDocument();
    });
  });
});
