/**
 * Shared pure utility functions used across components.
 * These are side-effect-free functions with no React dependencies.
 */

import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import utc from "dayjs/plugin/utc";

dayjs.extend(relativeTime);
dayjs.extend(utc);

// ==========================================================================
// URL / Artifact helpers
// ==========================================================================

/**
 * Builds an artifact URL from a path.
 * @param path - The artifact path
 * @returns The artifact URL or null if path is empty
 */
export const artifactUrl = (path: string | null) => {
  if (!path) {
    return null;
  }
  return `/artifact?path=${encodeURIComponent(path)}`;
};

// ==========================================================================
// Timestamp / Time formatting
// ==========================================================================

/**
 * Format a timestamp for display.
 * @param value - ISO timestamp string
 * @returns Formatted timestamp string
 */
export const formatTimestamp = (value: string) => dayjs.utc(value).format("MMM D, YYYY HH:mm [UTC]");

/**
 * Returns a relative time string (e.g., "2 hours ago") for a timestamp.
 */
export const relativeRecency = (timestamp: string) => dayjs(timestamp).fromNow();

// ==========================================================================
// Text formatting
// ==========================================================================

/**
 * Truncates text to a maximum length, appending an ellipsis if needed.
 */
export const truncateText = (value: string, length = 160) => {
  if (value.length <= length) {
    return value;
  }
  return `${value.slice(0, length).trim()}…`;
};

// ==========================================================================
// Latency formatting
// ==========================================================================

/**
 * Format latency value for display.
 * Rules:
 * - null/undefined/non-finite → "—"
 * - always displays in milliseconds (e.g., "153ms")
 */
export const formatLatency = (value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) {
    return "—";
  }
  return `${Math.round(value)}ms`;
};

// ==========================================================================
// Filter value normalization
// ==========================================================================

/**
 * Normalize a filter value, returning "unknown" for empty/null values.
 */
export const normalizeFilterValue = (value: string | null | undefined) =>
  value && value.trim() ? value : "unknown";

// ==========================================================================
// Status class formatting
// ==========================================================================

/**
 * Returns a CSS-friendly class name based on status value.
 * Used with status-pill wrapper elements.
 */
export const statusClass = (value: string) => {
  const normalized = value.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
  return `status-pill status-pill-${normalized}`;
};
