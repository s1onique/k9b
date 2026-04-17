/**
 * Pagination Component Tests
 * 
 * Tests for the canonical Pagination component covering:
 * - Zero items (empty state)
 * - Single page behavior
 * - Multiple pages behavior
 * - Previous/Next button disabled states
 * - Page size changes
 * - Accessibility
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Pagination from "../components/Pagination";

// Helper to create minimal required props with sensible defaults
const createProps = (overrides = {}) => ({
  currentPage: 1,
  totalPages: 1,
  totalItems: 10,
  pageSize: 10,
  onPageChange: vi.fn(),
  ...overrides,
});

describe("Pagination Component", () => {
  describe("Empty state (zero items)", () => {
    it("returns null when totalItems is 0", () => {
      const props = createProps({ totalItems: 0, totalPages: 0 });
      const { container } = render(<Pagination {...props} />);
      expect(container.firstChild).toBeNull();
    });

    it("returns null when totalItems is 0 even with pageSizeOptions", () => {
      const props = createProps({ 
        totalItems: 0, 
        totalPages: 0,
        pageSizeOptions: [5, 10, 20] as const,
        onPageSizeChange: vi.fn(),
      });
      const { container } = render(<Pagination {...props} />);
      expect(container.firstChild).toBeNull();
    });
  });

  describe("Single page behavior", () => {
    it("does not render prev/next buttons when totalPages is 1", () => {
      const props = createProps({ totalPages: 1, totalItems: 5 });
      render(<Pagination {...props} />);
      
      expect(screen.queryByRole("button", { name: /previous/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /next/i })).not.toBeInTheDocument();
    });

    it("does not render page indicator when totalPages is 1", () => {
      const props = createProps({ totalPages: 1, totalItems: 5 });
      render(<Pagination {...props} />);
      
      // The pagination summary paragraph exists but no page indicator span
      const nav = screen.getByRole("navigation");
      const pageIndicator = nav.querySelector('.pagination-page-indicator');
      expect(pageIndicator).toBeNull();
    });

    it("renders page size selector when provided on single page", () => {
      const props = createProps({ 
        totalPages: 1, 
        totalItems: 5,
        pageSizeOptions: [5, 10, 20] as const,
        onPageSizeChange: vi.fn(),
      });
      render(<Pagination {...props} />);
      
      expect(screen.getByRole("combobox", { name: /items per page/i })).toBeInTheDocument();
    });

    it("renders range summary paragraph on single page", () => {
      const props = createProps({ 
        totalPages: 1, 
        totalItems: 5,
        currentPage: 1,
        pageSize: 5,
      });
      render(<Pagination {...props} />);
      
      // The pagination renders a summary paragraph
      expect(screen.getByText(/showing/i)).toBeInTheDocument();
    });
  });

  describe("Multiple pages behavior", () => {
    it("renders prev/next buttons when totalPages > 1", () => {
      const props = createProps({ totalPages: 3, totalItems: 30 });
      render(<Pagination {...props} />);
      
      expect(screen.getByRole("button", { name: /previous/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /next/i })).toBeInTheDocument();
    });

    it("renders page indicator showing current page", () => {
      const props = createProps({ 
        totalPages: 5, 
        totalItems: 50,
        currentPage: 3,
      });
      render(<Pagination {...props} />);
      
      const nav = screen.getByRole("navigation");
      const pageIndicator = nav.querySelector('.pagination-page-indicator');
      expect(pageIndicator).not.toBeNull();
    });

    it("renders page size selector when provided", () => {
      const props = createProps({ 
        totalPages: 3, 
        totalItems: 30,
        pageSizeOptions: [5, 10, 20] as const,
        onPageSizeChange: vi.fn(),
      });
      render(<Pagination {...props} />);
      
      expect(screen.getByRole("combobox", { name: /items per page/i })).toBeInTheDocument();
    });
  });

  describe("Previous button disabled state", () => {
    it("disables Previous button on first page", () => {
      const props = createProps({ 
        totalPages: 3, 
        totalItems: 30,
        currentPage: 1,
      });
      render(<Pagination {...props} />);
      
      const prevButton = screen.getByRole("button", { name: /previous/i });
      expect(prevButton).toBeDisabled();
    });

    it("enables Previous button on second page", () => {
      const props = createProps({ 
        totalPages: 3, 
        totalItems: 30,
        currentPage: 2,
      });
      render(<Pagination {...props} />);
      
      const prevButton = screen.getByRole("button", { name: /previous/i });
      expect(prevButton).not.toBeDisabled();
    });

    it("calls onPageChange with previous page number when Previous is clicked", async () => {
      const user = userEvent.setup();
      const onPageChange = vi.fn();
      const props = createProps({ 
        totalPages: 3, 
        totalItems: 30,
        currentPage: 2,
        onPageChange,
      });
      render(<Pagination {...props} />);
      
      const prevButton = screen.getByRole("button", { name: /previous/i });
      await user.click(prevButton);
      
      expect(onPageChange).toHaveBeenCalledWith(1);
    });
  });

  describe("Next button disabled state", () => {
    it("disables Next button on last page", () => {
      const props = createProps({ 
        totalPages: 3, 
        totalItems: 30,
        currentPage: 3,
      });
      render(<Pagination {...props} />);
      
      const nextButton = screen.getByRole("button", { name: /next/i });
      expect(nextButton).toBeDisabled();
    });

    it("enables Next button on first page", () => {
      const props = createProps({ 
        totalPages: 3, 
        totalItems: 30,
        currentPage: 1,
      });
      render(<Pagination {...props} />);
      
      const nextButton = screen.getByRole("button", { name: /next/i });
      expect(nextButton).not.toBeDisabled();
    });

    it("calls onPageChange with next page number when Next is clicked", async () => {
      const user = userEvent.setup();
      const onPageChange = vi.fn();
      const props = createProps({ 
        totalPages: 3, 
        totalItems: 30,
        currentPage: 2,
        onPageChange,
      });
      render(<Pagination {...props} />);
      
      const nextButton = screen.getByRole("button", { name: /next/i });
      await user.click(nextButton);
      
      expect(onPageChange).toHaveBeenCalledWith(3);
    });
  });

  describe("Page size changes", () => {
    it("renders page size selector with correct options", () => {
      const props = createProps({ 
        totalPages: 2,
        totalItems: 50,
        pageSizeOptions: [10, 25, 50] as const,
        onPageSizeChange: vi.fn(),
      });
      render(<Pagination {...props} />);
      
      const select = screen.getByRole("combobox", { name: /items per page/i }) as HTMLSelectElement;
      expect(select).toBeInTheDocument();
      
      const options = select.querySelectorAll("option");
      expect(options).toHaveLength(3);
      expect(options[0]).toHaveValue("10");
      expect(options[1]).toHaveValue("25");
      expect(options[2]).toHaveValue("50");
    });

    it("calls onPageSizeChange when page size is changed", async () => {
      const user = userEvent.setup();
      const onPageSizeChange = vi.fn();
      const props = createProps({ 
        totalPages: 2,
        totalItems: 50,
        pageSize: 10,
        pageSizeOptions: [10, 25, 50] as const,
        onPageSizeChange,
      });
      render(<Pagination {...props} />);
      
      const select = screen.getByRole("combobox", { name: /items per page/i });
      await user.selectOptions(select, "25");
      
      expect(onPageSizeChange).toHaveBeenCalledWith(25);
    });
  });

  describe("Accessibility", () => {
    it("has nav role for pagination region", () => {
      const props = createProps({ totalPages: 2, totalItems: 20 });
      render(<Pagination {...props} />);
      
      expect(screen.getByRole("navigation")).toBeInTheDocument();
    });

    it("uses label prop in navigation aria-label", () => {
      const props = createProps({ 
        totalPages: 2, 
        totalItems: 20,
        label: "Runs",
      });
      render(<Pagination {...props} />);
      
      expect(screen.getByRole("navigation", { name: /runs pagination/i })).toBeInTheDocument();
    });

    it("uses generic aria-label when no label prop provided", () => {
      const props = createProps({ totalPages: 2, totalItems: 20 });
      render(<Pagination {...props} />);
      
      expect(screen.getByRole("navigation", { name: /pagination/i })).toBeInTheDocument();
    });

    it("has visible focus styles via className", () => {
      const props = createProps({ totalPages: 2, totalItems: 20 });
      render(<Pagination {...props} />);
      
      const prevButton = screen.getByRole("button", { name: /previous/i });
      expect(prevButton).toHaveClass("pagination-btn");
    });

    it("previous button has correct aria-label with label context", () => {
      const props = createProps({ 
        totalPages: 2, 
        totalItems: 20,
        label: "Runs",
      });
      render(<Pagination {...props} />);
      
      expect(screen.getByRole("button", { name: /runs previous page/i })).toBeInTheDocument();
    });

    it("next button has correct aria-label with label context", () => {
      const props = createProps({ 
        totalPages: 2, 
        totalItems: 20,
        label: "Runs",
      });
      render(<Pagination {...props} />);
      
      expect(screen.getByRole("button", { name: /runs next page/i })).toBeInTheDocument();
    });
  });

  describe("Recent runs integration", () => {
    it("renders with Runs label for Recent runs panel", () => {
      const props = createProps({ 
        currentPage: 1,
        totalPages: 2,
        totalItems: 25,
        pageSize: 20,
        pageSizeOptions: [5, 10, 20] as const,
        onPageSizeChange: vi.fn(),
        label: "Runs",
      });
      render(<Pagination {...props} />);
      
      // Check navigation region is labeled
      expect(screen.getByRole("navigation", { name: /runs pagination/i })).toBeInTheDocument();
      
      // Check page indicator is present
      const nav = screen.getByRole("navigation");
      const pageIndicator = nav.querySelector('.pagination-page-indicator');
      expect(pageIndicator).not.toBeNull();
      
      // Check page size selector
      expect(screen.getByRole("combobox", { name: /items per page/i })).toBeInTheDocument();
      
      // Check range summary exists
      expect(screen.getByText(/showing/i)).toBeInTheDocument();
    });

    it("renders expected pagination controls after migration", () => {
      const props = createProps({ 
        currentPage: 2,
        totalPages: 3,
        totalItems: 45,
        pageSize: 15,
        pageSizeOptions: [5, 10, 20] as const,
        onPageChange: vi.fn(),
        onPageSizeChange: vi.fn(),
        label: "Runs",
      });
      render(<Pagination {...props} />);
      
      // Previous button enabled on page 2
      const prevButton = screen.getByRole("button", { name: /previous/i });
      expect(prevButton).not.toBeDisabled();
      
      // Next button enabled on page 2 of 3
      const nextButton = screen.getByRole("button", { name: /next/i });
      expect(nextButton).not.toBeDisabled();
      
      // Page indicator exists
      const nav = screen.getByRole("navigation");
      const pageIndicator = nav.querySelector('.pagination-page-indicator');
      expect(pageIndicator).not.toBeNull();
      
      // Page size selector present
      expect(screen.getByRole("combobox", { name: /items per page/i })).toBeInTheDocument();
      
      // Range summary exists
      expect(screen.getByText(/showing/i)).toBeInTheDocument();
    });

    it("handles empty runs list (zero items)", () => {
      const props = createProps({ 
        totalItems: 0,
        totalPages: 0,
        currentPage: 1,
        pageSize: 10,
        pageSizeOptions: [5, 10, 20] as const,
        onPageChange: vi.fn(),
        onPageSizeChange: vi.fn(),
        label: "Runs",
      });
      const { container } = render(<Pagination {...props} />);
      
      // Should render nothing for empty state
      expect(container.firstChild).toBeNull();
    });

    it("handles single page runs list", () => {
      const props = createProps({ 
        totalItems: 5,
        totalPages: 1,
        currentPage: 1,
        pageSize: 10,
        pageSizeOptions: [5, 10, 20] as const,
        onPageChange: vi.fn(),
        onPageSizeChange: vi.fn(),
        label: "Runs",
      });
      render(<Pagination {...props} />);
      
      // No prev/next buttons on single page
      expect(screen.queryByRole("button", { name: /previous/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /next/i })).not.toBeInTheDocument();
      
      // But page size selector still visible
      expect(screen.getByRole("combobox", { name: /items per page/i })).toBeInTheDocument();
      
      // And range summary
      expect(screen.getByText(/showing/i)).toBeInTheDocument();
    });
  });
});