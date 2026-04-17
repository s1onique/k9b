/**
 * Canonical Pagination Component
 * 
 * Provides a consistent, accessible pagination control for the dashboard.
 * 
 * Features:
 * - Previous/Next navigation buttons (hidden on single page)
 * - Current page indicator ("Page X of Y")
 * - Optional items per page selector
 * - Visible range summary ("Showing X–Y of Z")
 * - Keyboard accessible with visible focus states
 * - Works with all supported themes
 * - Responsive: controls wrap gracefully on narrow widths
 * 
 * Props:
 * - currentPage: 1-based current page number
 * - totalPages: total number of pages (0 = empty state)
 * - totalItems: total number of items across all pages
 * - pageSize: current items per page
 * - pageSizeOptions: array of available page sizes (shows selector if provided)
 * - onPageChange: callback when page changes
 * - onPageSizeChange: optional callback when page size changes
 * - label: optional label for aria identification (e.g., "Runs", "Notifications")
 */

import { useCallback } from "react";

export interface PaginationProps {
  currentPage: number;
  totalPages: number;
  totalItems: number;
  pageSize: number;
  pageSizeOptions?: readonly number[];
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
  label?: string;
}

const Pagination = ({
  currentPage,
  totalPages,
  totalItems,
  pageSize,
  pageSizeOptions,
  onPageChange,
  onPageSizeChange,
  label,
}: PaginationProps) => {
  // Early return for empty datasets - no controls at all
  if (totalItems === 0) {
    return null;
  }

  // Calculate visible range
  const startItem = Math.min((currentPage - 1) * pageSize + 1, totalItems);
  const endItem = Math.min(currentPage * pageSize, totalItems);

  // Determine visibility based on data characteristics
  const hasMultiplePages = totalPages > 1;
  const hasPageSizeOptions = pageSizeOptions && pageSizeOptions.length > 0 && onPageSizeChange;
  const showNavControls = hasMultiplePages;
  const showPageSizeSelector = hasPageSizeOptions;

  // Generate unique accessible label for this pagination region
  const paginationLabel = label ? `${label} pagination` : "Pagination";
  const prevLabel = `${label ? label + ' ' : ''}previous page`;
  const nextLabel = `${label ? label + ' ' : ''}next page`;

  const handlePrev = useCallback(() => {
    if (currentPage > 1) {
      onPageChange(currentPage - 1);
    }
  }, [currentPage, onPageChange]);

  const handleNext = useCallback(() => {
    if (currentPage < totalPages) {
      onPageChange(currentPage + 1);
    }
  }, [currentPage, totalPages, onPageChange]);

  const handlePageSizeChange = useCallback(
    (event: React.ChangeEvent<HTMLSelectElement>) => {
      const newSize = Number(event.target.value);
      if (onPageSizeChange) {
        onPageSizeChange(newSize);
      }
    },
    [onPageSizeChange]
  );

  return (
    <nav
      className="pagination"
      aria-label={paginationLabel}
      role="navigation"
    >
      {/* Page navigation controls - only shown when multiple pages exist */}
      {showNavControls && (
        <div className="pagination-controls" role="group" aria-label="Page navigation">
          <button
            type="button"
            onClick={handlePrev}
            disabled={currentPage <= 1}
            aria-label={prevLabel}
            className="pagination-btn pagination-btn--prev"
          >
            <span className="pagination-btn-icon" aria-hidden="true">‹</span>
            <span className="pagination-btn-label">Previous</span>
          </button>

          <span className="pagination-page-indicator">
            Page <strong>{currentPage}</strong> of <strong>{totalPages}</strong>
          </span>

          <button
            type="button"
            onClick={handleNext}
            disabled={currentPage >= totalPages}
            aria-label={nextLabel}
            className="pagination-btn pagination-btn--next"
          >
            <span className="pagination-btn-label">Next</span>
            <span className="pagination-btn-icon" aria-hidden="true">›</span>
          </button>
        </div>
      )}

      {/* Page size selector - shown intentionally even on single-page datasets */}
      {showPageSizeSelector && (
        <div className="pagination-size-selector" role="group" aria-label="Items per page selector">
          <label
            htmlFor={`pagination-${label?.toLowerCase().replace(/\s+/g, "-") || "default"}-page-size`}
            className="pagination-size-label"
          >
            Per page:
          </label>
          <select
            id={`pagination-${label?.toLowerCase().replace(/\s+/g, "-") || "default"}-page-size`}
            value={pageSize}
            onChange={handlePageSizeChange}
            className="pagination-size-select"
            aria-label="Items per page"
          >
            {pageSizeOptions.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Single live region: range summary that announces all pagination changes */}
      <p
        className="pagination-summary"
        aria-live="polite"
        aria-atomic="true"
      >
        Showing <strong>{startItem}</strong>–<strong>{endItem}</strong> of <strong>{totalItems}</strong>
      </p>
    </nav>
  );
};

export default Pagination;