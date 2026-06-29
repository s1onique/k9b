/**
 * executionHistoryFormat.ts
 *
 * Formatting utilities for ExecutionHistory components.
 * Pure, unit-testable helper functions.
 */

/**
 * Format duration in seconds to human-readable string
 */
export const formatDuration = (value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) {
    return "—";
  }
  const seconds = Math.max(0, Math.round(value));
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder === 0 ? `${minutes}m` : `${minutes}m ${remainder}s`;
};

/**
 * Build badges list from an execution entry
 */
export const buildExecutionBadges = (entry: {
  timedOut?: boolean | null;
  stdoutTruncated?: boolean | null;
  stderrTruncated?: boolean | null;
  outputBytesCaptured?: number | null;
}): string[] => {
  const badges: string[] = [];
  if (entry.timedOut) badges.push("Timed out");
  if (entry.stdoutTruncated) badges.push("stdout truncated");
  if (entry.stderrTruncated) badges.push("stderr truncated");
  return badges;
};
