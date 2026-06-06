/**
 * RuntimeStatusSummary.tsx - Runtime status section container component.
 *
 * Combines log window counts and PVC usage into a single compact
 * runtime status section for the dashboard.
 */

import type { RuntimeStatusPayload } from "./runtimeStatusTypes";
import { RuntimeLogWindowCounts, buildPodLogStatus } from "./RuntimeLogWindowCounts";
import { RuntimeLogWindowCountsUnavailable } from "./RuntimeLogWindowCounts";
import { PvcUsageBar, PvcUsageUnavailable, buildPvcDisplayState } from "./PvcUsageBar";

// ============================================================================
// Props
// ============================================================================

export interface RuntimeStatusSummaryProps {
  /** Runtime status data from backend */
  runtimeStatus: RuntimeStatusPayload | null;
  /** Whether data is still loading */
  isLoading: boolean;
  /** Whether there was an error fetching data */
  isError: boolean;
}

// ============================================================================
// Helpers
// ============================================================================

/**
 * Extract backend pod log status from runtime status payload.
 */
function extractBackendLogStatus(
  runtimeStatus: RuntimeStatusPayload
): ReturnType<typeof buildPodLogStatus> {
  const { backend } = runtimeStatus.log_windows;
  return buildPodLogStatus(
    "backend",
    backend["5m"],
    backend["10m"],
    backend["15m"]
  );
}

/**
 * Extract scheduler pod log status from runtime status payload.
 */
function extractSchedulerLogStatus(
  runtimeStatus: RuntimeStatusPayload
): ReturnType<typeof buildPodLogStatus> {
  const { scheduler } = runtimeStatus.log_windows;
  return buildPodLogStatus(
    "scheduler",
    scheduler["5m"],
    scheduler["10m"],
    scheduler["15m"]
  );
}

// ============================================================================
// Component
// ============================================================================

/**
 * Compact runtime status section showing:
 * - Backend and scheduler log summaries (ERROR + WARNING counts for 5m/10m/15m windows)
 * - Backend PVC storage usage with progress bar
 */
export const RuntimeStatusSummary = ({
  runtimeStatus,
  isLoading,
  isError,
}: RuntimeStatusSummaryProps) => {
  // Loading state
  if (isLoading) {
    return (
      <div
        className="runtime-status-summary runtime-status-summary--loading"
        data-testid="runtime-status-summary"
      >
        <div className="runtime-status-header">
          <span className="runtime-status-icon" aria-hidden="true">◉</span>
          <h3>Runtime Status</h3>
        </div>
        <div className="runtime-status-loading">
          <span className="loading-text">Loading runtime status...</span>
        </div>
      </div>
    );
  }

  // Error state - show unavailable for all data
  // Also guard against malformed payload (empty object or missing log_windows)
  if (isError || !runtimeStatus || !runtimeStatus.log_windows) {
    return (
      <div
        className="runtime-status-summary runtime-status-summary--error"
        data-testid="runtime-status-summary"
      >
        <div className="runtime-status-header">
          <span className="runtime-status-icon" aria-hidden="true">◉</span>
          <h3>Runtime Status</h3>
        </div>
        <div className="runtime-status-content">
          <div className="runtime-status-log-counts">
            <RuntimeLogWindowCountsUnavailable podName="backend" />
            <RuntimeLogWindowCountsUnavailable podName="scheduler" />
          </div>
          <div className="runtime-status-pvc">
            <PvcUsageUnavailable />
          </div>
        </div>
      </div>
    );
  }

  // Backend log status
  const backendLogStatus = extractBackendLogStatus(runtimeStatus);

  // Scheduler log status
  const schedulerLogStatus = extractSchedulerLogStatus(runtimeStatus);

  // PVC usage
  const pvcData = runtimeStatus.backend_pvc;
  let pvcDisplayState = null;
  if (pvcData) {
    pvcDisplayState = buildPvcDisplayState(
      pvcData.name,
      pvcData.used_bytes,
      pvcData.free_bytes,
      pvcData.capacity_bytes,
      pvcData.used_percent
    );
  }

  return (
    <div
      className="runtime-status-summary"
      data-testid="runtime-status-summary"
    >
      <div className="runtime-status-header">
        <span className="runtime-status-icon" aria-hidden="true">◉</span>
        <h3>Runtime Status</h3>
      </div>

      <div className="runtime-status-content">
        {/* Log counts section */}
        <div className="runtime-status-section">
          <h4 className="runtime-status-section-title">Log pressure</h4>
          <div className="runtime-status-log-counts" data-testid="log-counts-section">
            {backendLogStatus ? (
              <RuntimeLogWindowCounts podLogStatus={backendLogStatus} />
            ) : (
              <RuntimeLogWindowCountsUnavailable podName="backend" />
            )}
            {schedulerLogStatus ? (
              <RuntimeLogWindowCounts podLogStatus={schedulerLogStatus} />
            ) : (
              <RuntimeLogWindowCountsUnavailable podName="scheduler" />
            )}
          </div>
        </div>

        {/* PVC usage section */}
        <div className="runtime-status-section">
          <h4 className="runtime-status-section-title">PVC usage</h4>
          <div className="runtime-status-pvc" data-testid="pvc-section">
            {pvcDisplayState ? (
              <PvcUsageBar displayState={pvcDisplayState} />
            ) : (
              <PvcUsageUnavailable name={pvcData?.name ?? "backend-data"} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
