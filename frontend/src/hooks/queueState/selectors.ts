/**
 * Pure derived-state helpers for queue state (selectors, formatters, rankers).
 */

import type { NextCheckQueueItem, NextCheckQueueStatus } from "./types";

import { QUEUE_PRIORITY_ORDER } from "./constants";

// ---------------------------------------------------------------------------
// Normalization helpers
// ---------------------------------------------------------------------------

/** Normalize priority to lowercase, defaulting to "unknown". */
export const normalizeQueuePriority = (value: string | null | undefined) =>
  (value ?? "unknown").toLowerCase();

/** Rank a priority value (lower = higher priority). */
export const queuePriorityRank = (value: string | null | undefined) =>
  QUEUE_PRIORITY_ORDER[normalizeQueuePriority(value)] ??
  Object.keys(QUEUE_PRIORITY_ORDER).length;

/** Parse a timestamp to a numeric value (0 if invalid). */
export const queueTimestampValue = (value: string | null | undefined) => {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
};

/** Normalize a filter value (trimmed string or "unknown"). */
export const normalizeFilterValue = (value: string | null | undefined) =>
  value && value.trim() ? value : "unknown";

// ---------------------------------------------------------------------------
// Format helpers
// ---------------------------------------------------------------------------

/** Format cluster name for display (truncate long names). */
export const formatCluster = (cluster: string | null | undefined): string => {
  if (!cluster) return "unknown";
  if (cluster.length > 50) {
    return `${cluster.slice(0, 47)}…`;
  }
  return cluster;
};

/** Format command family for display. */
export const formatCommandFamily = (family: string | null | undefined): string => {
  if (!family) return "unknown";
  return normalizeFilterValue(family);
};

/** Format priority label for display (title case). */
export const formatPriority = (priority: string | null | undefined): string => {
  const normalized = (priority ?? "unknown").toLowerCase();
  if (normalized === "primary") return "Primary";
  if (normalized === "secondary") return "Secondary";
  if (normalized === "fallback") return "Fallback";
  if (normalized === "unknown") return "Unknown";
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
};

// ---------------------------------------------------------------------------
// Derivation helpers (pure)
// ---------------------------------------------------------------------------

/** Extract unique sorted cluster options from queue items. */
export const deriveClusterOptions = (items: NextCheckQueueItem[]): string[] => {
  const values = new Set<string>();
  items.forEach((entry) => values.add(formatCluster(entry.targetCluster)));
  return Array.from(values).sort();
};

/** Extract unique sorted command family options from queue items. */
export const deriveCommandFamilyOptions = (items: NextCheckQueueItem[]): string[] => {
  const values = new Set<string>();
  items.forEach((entry) => values.add(formatCommandFamily(entry.suggestedCommandFamily)));
  return Array.from(values).sort();
};

/** Extract unique sorted priority options from queue items. */
export const derivePriorityOptions = (items: NextCheckQueueItem[]): string[] => {
  const values = new Set<string>();
  items.forEach((entry) => values.add(normalizeQueuePriority(entry.priorityLabel)));
  return Array.from(values).sort();
};

/** Extract unique sorted workstream options from queue items. */
export const deriveWorkstreamOptions = (items: NextCheckQueueItem[]): string[] => {
  const values = new Set<string>();
  items.forEach((entry) => {
    if (entry.workstream && entry.workstream.trim()) {
      values.add(entry.workstream);
    }
  });
  return Array.from(values).sort();
};
