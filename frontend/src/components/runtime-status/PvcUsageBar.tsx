/**
 * PvcUsageBar.tsx - PVC storage usage progress bar component.
 *
 * Renders backend PVC usage with:
 * - Used/free/capacity in human-readable format
 * - Visual progress bar
 * - Accessible text label
 * - High usage warning styling
 */

import type { PvcDisplayState } from "./runtimeStatusTypes";

// ============================================================================
// Helpers
// ============================================================================

/**
 * Format bytes to human-readable string.
 * Returns "N/A" for null/undefined values.
 */
function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes === undefined) {
    return "N/A";
  }
  if (bytes === 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const value = bytes / Math.pow(k, i);
  // Show 1-2 significant digits
  const formatted = value < 10 ? value.toFixed(1) : Math.round(value);
  return `${formatted} ${units[i]}`;
}

/**
 * Build display state from raw PVC data.
 * Returns null if PVC data is not available (all null).
 */
export function buildPvcDisplayState(
  name: string,
  usedBytes: number | null,
  freeBytes: number | null,
  capacityBytes: number | null,
  usedPercent: number | null
): PvcDisplayState | null {
  // Check if data is available (at least one value must be non-null)
  if (
    usedBytes === null &&
    freeBytes === null &&
    capacityBytes === null &&
    usedPercent === null
  ) {
    return null;
  }

  const usedDisplay = formatBytes(usedBytes);
  const freeDisplay = formatBytes(freeBytes);
  const capacityDisplay = formatBytes(capacityBytes);

  // Calculate percentage if not provided
  const effectivePercent =
    usedPercent !== null
      ? usedPercent
      : capacityBytes && usedBytes !== null
      ? Math.round((usedBytes / capacityBytes) * 100)
      : null;

  // Build accessible label
  let accessibleLabel: string;
  if (effectivePercent !== null) {
    const freePercent = 100 - effectivePercent;
    accessibleLabel = `${effectivePercent}% used, ${freePercent}% free`;
  } else {
    accessibleLabel = "PVC usage unavailable";
  }

  return {
    name,
    usedDisplay,
    freeDisplay,
    capacityDisplay,
    usedPercent: effectivePercent ?? 0,
    accessibleLabel,
    unavailable: false,
    highUsage: effectivePercent !== null && effectivePercent > 80,
  };
}

// ============================================================================
// Component
// ============================================================================

interface PvcUsageBarProps {
  /** Display state from buildPvcDisplayState */
  displayState: PvcDisplayState;
}

/**
 * PVC storage usage progress bar with accessible labeling.
 * Shows used/free/capacity and a visual progress indicator.
 */
export const PvcUsageBar = ({ displayState }: PvcUsageBarProps) => {
  const {
    name,
    usedDisplay,
    freeDisplay,
    capacityDisplay,
    usedPercent,
    accessibleLabel,
    highUsage,
  } = displayState;

  return (
    <div
      className={`pvc-usage-bar ${highUsage ? "pvc-usage-bar--high" : ""}`}
      data-testid="pvc-usage-bar"
      role="meter"
      aria-label={accessibleLabel}
      aria-valuenow={usedPercent}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className="pvc-usage-header">
        <span className="pvc-usage-name">{name}</span>
        <span className="pvc-usage-percent">
          {usedPercent !== null ? `${usedPercent}%` : "N/A"}
        </span>
      </div>

      <div className="pvc-usage-track">
        <div
          className="pvc-usage-fill"
          style={{ width: `${Math.min(usedPercent, 100)}%` }}
          aria-hidden="true"
        />
      </div>

      <div className="pvc-usage-details">
        <span className="pvc-usage-used">Used: {usedDisplay}</span>
        <span className="pvc-usage-separator">·</span>
        <span className="pvc-usage-free">Free: {freeDisplay}</span>
        <span className="pvc-usage-separator">·</span>
        <span className="pvc-usage-capacity">Capacity: {capacityDisplay}</span>
      </div>

      {highUsage && (
        <div className="pvc-usage-warning" role="alert">
          <span className="pvc-usage-warning-icon" aria-hidden="true">⚠</span>
          <span className="pvc-usage-warning-text">High storage usage</span>
        </div>
      )}
    </div>
  );
};

// ============================================================================
// Unavailable state component
// ============================================================================

interface PvcUsageUnavailableProps {
  /** PVC name to display */
  name?: string;
}

/**
 * Renders unavailable state for PVC when data cannot be fetched.
 */
export const PvcUsageUnavailable = ({ name = "backend-data" }: PvcUsageUnavailableProps) => {
  return (
    <div
      className="pvc-usage-bar pvc-usage-bar--unavailable"
      data-testid="pvc-usage-bar-unavailable"
    >
      <div className="pvc-usage-header">
        <span className="pvc-usage-name">{name}</span>
        <span className="pvc-usage-percent">—</span>
      </div>

      <div className="pvc-usage-track pvc-usage-track--empty">
        <div
          className="pvc-usage-fill pvc-usage-fill--unavailable"
          style={{ width: "0%" }}
          aria-hidden="true"
        />
      </div>

      <div className="pvc-usage-details">
        <span className="pvc-usage-unavailable-text">PVC usage unavailable</span>
      </div>
    </div>
  );
};
