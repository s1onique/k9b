/**
 * runtimeStatusTypes.ts - TypeScript types for runtime status components.
 *
 * Covers:
 * - RuntimeStatusPayload: API response from /api/runtime-status
 * - LogWindowCounts: Non-info log counts for a pod across sliding windows
 * - PvcUsage: PVC storage usage with bytes and percentage
 *
 * Consumers: RuntimeStatusSummary, RuntimeLogWindowCounts, PvcUsageBar
 */

/**
 * Non-info log counts for a single pod across sliding time windows.
 * Only includes ERROR and WARNING severities (INFO excluded per design).
 *
 * Values may be null to indicate unavailable/missing data (not zero).
 * Zero counts are explicit: { warning: 0, error: 0 }
 */
export interface LogWindowCounts {
  /** Number of WARNING log lines in the window */
  warning: number | null;
  /** Number of ERROR log lines in the window */
  error: number | null;
}

/**
 * Log counts for a pod across multiple sliding time windows.
 */
export interface PodLogWindows {
  "5m": LogWindowCounts;
  "10m": LogWindowCounts;
  "15m": LogWindowCounts;
}

/**
 * Aggregated log counts for backend and scheduler pods.
 */
export interface LogWindows {
  backend: PodLogWindows;
  scheduler: PodLogWindows;
}

/**
 * PVC storage usage with byte counts and percentage.
 */
export interface PvcUsage {
  /** PVC name (e.g., "backend-data") */
  name: string;
  /** Used storage in bytes */
  used_bytes: number | null;
  /** Free storage in bytes */
  free_bytes: number | null;
  /** Total capacity in bytes */
  capacity_bytes: number | null;
  /** Percentage of capacity used (0-100) */
  used_percent: number | null;
  /** Data source method (e.g., "statvfs", "kubelet", "k8s_api") */
  source: string | null;
  /** Human-readable reason if data is unavailable */
  unavailable_reason: string | null;
}

/**
 * Complete runtime status payload from backend.
 *
 * This is a read-only observability projection derived from cluster data.
 * The frontend should only render; no data transformation is needed.
 */
export interface RuntimeStatusPayload {
  /** Non-info log counts for backend and scheduler pods */
  log_windows: LogWindows;
  /** Backend PVC storage usage */
  backend_pvc: PvcUsage | null;
}

// ============================================================================
// Display-ready types (derived, not from API)
// ============================================================================

/**
 * Display-ready log status for a single pod.
 * Combines error and warning into a single readable label.
 */
export interface PodLogStatus {
  /** Pod name for display */
  podName: string;
  /** Human-readable status string */
  displayStatus: string;
  /** Whether data is unavailable (not zero) */
  unavailable: boolean;
  /** Error count for the shortest window (5m) */
  errorCount: number;
  /** Warning count for the shortest window (5m) */
  warningCount: number;
}

/**
 * PVC display state with formatted values for rendering.
 */
export interface PvcDisplayState {
  /** PVC name */
  name: string;
  /** Formatted used string (e.g., "3 GB") */
  usedDisplay: string;
  /** Formatted free string (e.g., "7 GB") */
  freeDisplay: string;
  /** Formatted capacity string (e.g., "10 GB") */
  capacityDisplay: string;
  /** Percentage value (0-100) */
  usedPercent: number;
  /** Accessible label for progress bar (e.g., "30% used, 70% free") */
  accessibleLabel: string;
  /** Whether data is unavailable */
  unavailable: boolean;
  /** Whether usage is high (> 80%) */
  highUsage: boolean;
}

/**
 * Props for RuntimeStatusSummary component.
 */
export interface RuntimeStatusSummaryProps {
  /** Runtime status data from backend */
  runtimeStatus: RuntimeStatusPayload | null;
  /** Whether data is still loading */
  isLoading: boolean;
  /** Whether there was an error fetching data */
  isError: boolean;
}
