/**
 * Validation helpers for queue state (type guards).
 */

import type {
  NextCheckQueueStatus,
  QueueFocusMode,
  QueueSortOption,
} from "./types";

import {
  QUEUE_STATUS_FILTER_VALUES,
  QUEUE_SORT_VALUES,
  QUEUE_FOCUS_MODE_VALUES,
} from "./constants";

/** Guard for status filter values. */
export const isQueueStatusFilterValue = (
  value: unknown
): value is NextCheckQueueStatus | "all" =>
  typeof value === "string" &&
  QUEUE_STATUS_FILTER_VALUES.has(value as NextCheckQueueStatus | "all");

/** Guard for sort option values. */
export const isQueueSortOptionValue = (value: unknown): value is QueueSortOption =>
  typeof value === "string" &&
  (QUEUE_SORT_VALUES as readonly string[]).includes(value as QueueSortOption);

/** Guard for focus mode values. */
export const isQueueFocusModeValue = (value: unknown): value is QueueFocusMode =>
  typeof value === "string" &&
  (QUEUE_FOCUS_MODE_VALUES as readonly string[]).includes(value as QueueFocusMode);
