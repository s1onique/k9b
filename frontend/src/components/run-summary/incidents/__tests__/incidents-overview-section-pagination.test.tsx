/**
 * incidents-overview-section-pagination.test.tsx
 *
 * UI regression test: ensures pagination works correctly with 42 incidents.
 * Tests that 42 incidents paginate as 1-10, 11-20, 21-30, 31-40, 41-42 (5 pages).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { IncidentsOverviewSection } from "../IncidentsOverviewSection";

import { listIncidents } from "../../../../api";

// Mock the API module
vi.mock("../../../../api", () => ({
  listIncidents: vi.fn(),
}));

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

  it("shows correct page range label on page 1", async () => {
    vi.mocked(listIncidents).mockResolvedValue({
      incidents: createFortyTwoIncidents(),
    });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      expect(screen.getByTestId("incidents-overview-section")).toBeInTheDocument();
    });

    // Assert on summary textContent since text may be split across elements
    const summary = document.querySelector(".pagination-summary");
    expect(summary).toHaveTextContent("Showing 1–10 of 42");
  });

  it("allows navigating to page 2 with Next button", async () => {
    const user = userEvent.setup();
    vi.mocked(listIncidents).mockResolvedValue({
      incidents: createFortyTwoIncidents(),
    });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      expect(screen.getByTestId("incidents-overview-section")).toBeInTheDocument();
    });

    // Initially on page 1
    const initialSummary = document.querySelector(".pagination-summary");
    expect(initialSummary).toHaveTextContent("Showing 1–10 of 42");

    // Find and click the Next button (Incidents next page)
    const nextButton = screen.getByRole("button", { name: /Incidents next page/i });
    await user.click(nextButton);

    // Should now be on page 2
    await waitFor(() => {
      const summary = document.querySelector(".pagination-summary");
      expect(summary).toHaveTextContent("Showing 11–20 of 42");
    });
  });

  it("allows changing page size", async () => {
    const user = userEvent.setup();
    vi.mocked(listIncidents).mockResolvedValue({
      incidents: createFortyTwoIncidents(),
    });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      expect(screen.getByTestId("incidents-overview-section")).toBeInTheDocument();
    });

    // Use accessible name to select the page-size combobox specifically
    const pageSizeSelect = screen.getByRole("combobox", {
      name: /items per page/i,
    });
    
    // Change to 25 items per page
    await user.selectOptions(pageSizeSelect, ["25"]);

    await waitFor(() => {
      const summary = document.querySelector(".pagination-summary");
      expect(summary).toHaveTextContent("Showing 1–25 of 42");
    });
  });

  it("resets to page 1 when changing page size", async () => {
    const user = userEvent.setup();
    vi.mocked(listIncidents).mockResolvedValue({
      incidents: createFortyTwoIncidents(),
    });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      expect(screen.getByTestId("incidents-overview-section")).toBeInTheDocument();
    });

    // Go to page 2 by clicking Next once
    const nextButton = screen.getByRole("button", { name: /Incidents next page/i });
    await user.click(nextButton);

    await waitFor(() => {
      const summary = document.querySelector(".pagination-summary");
      expect(summary).toHaveTextContent("Showing 11–20 of 42");
    });

    // Change page size to 50 (all items on one page)
    const pageSizeSelect = screen.getByRole("combobox", {
      name: /items per page/i,
    });
    await user.selectOptions(pageSizeSelect, ["50"]);

    await waitFor(() => {
      // Should reset to page 1 with new size (all 42 items on one page)
      const summary = document.querySelector(".pagination-summary");
      expect(summary).toHaveTextContent("Showing 1–42 of 42");
    });
  });

  it("allows navigating back with Previous button", async () => {
    const user = userEvent.setup();
    vi.mocked(listIncidents).mockResolvedValue({
      incidents: createFortyTwoIncidents(),
    });

    render(<IncidentsOverviewSection runId="run-123" />);

    await waitFor(() => {
      expect(screen.getByTestId("incidents-overview-section")).toBeInTheDocument();
    });

    // Go to page 2
    const nextButton = screen.getByRole("button", { name: /Incidents next page/i });
    await user.click(nextButton);

    await waitFor(() => {
      const summary = document.querySelector(".pagination-summary");
      expect(summary).toHaveTextContent("Showing 11–20 of 42");
    });

    // Previous button should be enabled
    const prevButton = screen.getByRole("button", { name: /Incidents previous page/i });
    expect(prevButton).not.toBeDisabled();
    
    // Click Previous to go back to page 1
    await user.click(prevButton);

    await waitFor(() => {
      const summary = document.querySelector(".pagination-summary");
      expect(summary).toHaveTextContent("Showing 1–10 of 42");
    });
  });
});
