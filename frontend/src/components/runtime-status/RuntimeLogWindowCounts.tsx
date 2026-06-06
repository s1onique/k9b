/**
 * RuntimeLogWindowCounts.tsx - Log window counts for a single pod.
 *
 * Renders non-info log counts (ERROR + WARNING only) for a pod
 * across sliding time windows (5m, 10m, 15m).
 *
 * Key design: missing data is "unavailable", not zero.
 * This distinction matters during demos and outages.
 */

import type { LogWindowCounts, PodLogStatus } from "./runtimeStatusTypes";

// ============================================================================
// Helpers
// ============================================================================

/**
 * Build display status from raw log window counts.
 * Returns null if data is unavailable (all null values).
 */
export function buildPodLogStatus(
  podName: string,
  window5m: LogWindowCounts,
  window10m: LogWindowCounts,
  window15m: LogWindowCounts
): PodLogStatus | null {
  // Check if data is unavailable (all values null across all windows)
  const allUnavailable =
    window5m.warning === null &&
    window5m.error === null &&
    window10m.warning === null &&
    window10m.error === null &&
    window15m.warning === null &&
    window15m.error === null;

  if (allUnavailable) {
    return null;
  }

  // Use 5m window for primary display
  const warning = window5m.warning ?? 0;
  const error = window5m.error ?? 0;

  // Build display status string
  let displayStatus: string;
  if (window5m.warning === null && window5m.error === null) {
    // 5m data unavailable, but other windows have data
    displayStatus = "unavailable";
  } else if (error === 0 && warning === 0) {
    displayStatus = "0 error / 0 warning";
  } else {
    const parts: string[] = [];
    if (error > 0) {
      parts.push(`${error} error${error !== 1 ? "s" : ""}`);
    }
    if (warning > 0) {
      parts.push(`${warning} warning${warning !== 1 ? "s" : ""}`);
    }
    displayStatus = parts.join(" / ");
  }

  return {
    podName,
    displayStatus,
    unavailable: window5m.warning === null && window5m.error === null,
    errorCount: error,
    warningCount: warning,
  };
}

// ============================================================================
// Component
// ============================================================================

interface RuntimeLogWindowCountsProps {
  /** Display status from buildPodLogStatus */
  podLogStatus: PodLogStatus;
}

/**
 * Renders log counts for a single pod across time windows.
 * Shows pod name, primary counts, and expandable detail view.
 */
export const RuntimeLogWindowCounts = ({ podLogStatus }: RuntimeLogWindowCountsProps) => {
  const { podName, displayStatus, unavailable, errorCount, warningCount } = podLogStatus;

  // Determine severity class based on counts
  const hasErrors = errorCount > 0;
  const hasWarnings = warningCount > 0;

  let severityClass = "log-counts--ok";
  if (hasErrors) {
    severityClass = "log-counts--error";
  } else if (hasWarnings) {
    severityClass = "log-counts--warning";
  }

  return (
    <div
      className={`log-counts ${severityClass} ${unavailable ? "log-counts--unavailable" : ""}`}
      data-testid={`log-counts-${podName.toLowerCase()}`}
    >
      <div className="log-counts-header">
        <span className="log-counts-pod-name">{podName}</span>
        {unavailable ? (
          <span className="log-counts-unavailable-label">unavailable</span>
        ) : (
          <span className="log-counts-status">{displayStatus}</span>
        )}
      </div>
    </div>
  );
};

// ============================================================================
// Unavailable state component
// ============================================================================

interface RuntimeLogWindowCountsUnavailableProps {
  /** Pod name to display */
  podName: string;
}

/**
 * Renders unavailable state for log counts when data cannot be fetched.
 */
export const RuntimeLogWindowCountsUnavailable = ({
  podName,
}: RuntimeLogWindowCountsUnavailableProps) => {
  return (
    <div
      className="log-counts log-counts--unavailable"
      data-testid={`log-counts-${podName.toLowerCase()}-unavailable`}
    >
      <div className="log-counts-header">
        <span className="log-counts-pod-name">{podName}</span>
        <span className="log-counts-unavailable-label">unavailable</span>
      </div>
    </div>
  );
};
