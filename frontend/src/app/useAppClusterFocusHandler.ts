/**
 * useAppClusterFocusHandler - Hook for cluster-focus behavior in App.tsx
 *
 * Extracts the inline onFocusClusterForNextChecks handler from App.tsx to reduce
 * component size and move toward LLM-friendly limits.
 *
 * Preserves the exact fallback chain and side effects:
 * - Fallback: clusterLabel -> discoveryClusters[0] -> selectedClusterLabel -> fleet.clusters[0]?.label -> null
 * - Side effects: handleClusterSelection(target, { expand: true }), highlightCluster(target), scrollToSection("cluster")
 */

import type { FleetPayload } from "../types";

export interface UseAppClusterFocusHandlerArgs {
  /** Available clusters from run plan discovery */
  discoveryClusters: string[];
  /** Currently selected cluster label */
  selectedClusterLabel: string | null;
  /** Fleet data for fallback cluster resolution */
  fleet: FleetPayload;
  /** Select and expand a cluster */
  handleClusterSelection: (label: string, options?: { expand?: boolean }) => void;
  /** Highlight a cluster row temporarily */
  highlightCluster: (clusterLabel: string | null) => void;
  /** Smooth scroll to a section by its DOM ID */
  scrollToSection: (sectionId: string) => void;
}

/**
 * Returns a focusClusterForNextChecks handler that:
 * 1. Resolves target cluster using the fallback chain
 * 2. Selects the cluster with expansion
 * 3. Highlights the cluster row
 * 4. Scrolls to the cluster section
 *
 * Note: Returns a new function on each render to avoid hook-order issues.
 * The handler is only used as a prop passed to child components.
 */
export function useAppClusterFocusHandler({
  discoveryClusters,
  selectedClusterLabel,
  fleet,
  handleClusterSelection,
  highlightCluster,
  scrollToSection,
}: UseAppClusterFocusHandlerArgs): {
  focusClusterForNextChecks: (clusterLabel?: string | null) => void;
} {
  // Return a new function on each render - this matches the original inline behavior
  // and avoids hook-order issues when called before/after early returns
  const focusClusterForNextChecks = (clusterLabel?: string | null) => {
    const target =
      clusterLabel ||
      discoveryClusters[0] ||
      selectedClusterLabel ||
      fleet.clusters[0]?.label ||
      null;
    if (!target) {
      return;
    }
    handleClusterSelection(target, { expand: true });
    highlightCluster(target);
    scrollToSection("cluster");
  };

  return { focusClusterForNextChecks };
}
