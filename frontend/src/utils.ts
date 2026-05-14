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

/**
 * Canonical executed item states from backend itemState field.
 * These represent the overall item state regardless of executionState.
 */
export const EXECUTED_ITEM_STATES = new Set(["executed", "reviewed"] as const);

/** Canonical executed execution states */
export const EXECUTED_STATES = new Set([
  "executed-success",
  "executed-failed",
  "timed-out",
  "completed",
] as const);

/**
 * Check if a candidate has been executed (has execution artifacts, execution state, or itemState).
 * This is the canonical predicate for all UI decisions about whether to show
 * "Run candidate" buttons and how to display execution status.
 */
export function isItemExecuted(item: {
  itemState?: string | null;
  executionState?: string | null;
  sourceArtifactRefs?: Array<{ path?: string | null }>;
}): boolean {
  // Check itemState first (backend state signal)
  if (item.itemState && EXECUTED_ITEM_STATES.has(item.itemState as typeof EXECUTED_ITEM_STATES extends Set<infer T> ? T : never)) {
    return true;
  }

  // Check executionState
  if (item.executionState && EXECUTED_STATES.has(item.executionState as typeof EXECUTED_STATES extends Set<infer T> ? T : never)) {
    return true;
  }

  // Check for execution artifacts (sourceArtifactRefs containing execution artifacts)
  if (item.sourceArtifactRefs) {
    const hasExecutionArtifact = item.sourceArtifactRefs.some((ref) =>
      ref.path?.includes("next-check-execution") || ref.path?.includes("execution")
    );
    if (hasExecutionArtifact) {
      return true;
    }
  }

  return false;
}

/**
 * Derive the canonical execution display label for a queue item.
 * Returns the appropriate display text for the execution badge:
 * - "executed / success" for successful execution
 * - "executed / failed" for failed execution
 * - "executed / timed-out" for timed-out execution
 * - "executed" when itemState says executed but executionState is missing/stale
 * - null if not executed
 */
export function deriveExecutionLabel(item: {
  itemState?: string | null;
  executionState?: string | null;
}): string | null {
  // If itemState says executed, show "executed" label regardless of executionState
  if (item.itemState && EXECUTED_ITEM_STATES.has(item.itemState as typeof EXECUTED_ITEM_STATES extends Set<infer T> ? T : never)) {
    if (!item.executionState || item.executionState === "unexecuted" || item.executionState === "pending") {
      return "executed";
    }
  }

  if (!item.executionState) {
    return null;
  }

  if (item.executionState === "executed-failed") {
    return "executed / failed";
  } else if (item.executionState === "timed-out") {
    return "executed / timed-out";
  } else if (EXECUTED_STATES.has(item.executionState as typeof EXECUTED_STATES extends Set<infer T> ? T : never)) {
    return "executed / success";
  }

  return null;
}
