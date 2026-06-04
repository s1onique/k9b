/**
 * useAppClusterSelectionHandlers - Hook for cluster selection and detail expansion behavior
 *
 * Extracts cluster selection logic from App.tsx to reduce component size.
 *
 * Owns:
 *   - Cluster selection handler that coordinates hook + local expansion state
 *   - Cluster detail expansion coordination
 *
 * Preserves:
 *   - Exact selection behavior (delegate to useAppData's handler)
 *   - Exact expansion behavior (setClusterDetailExpanded when expand: true)
 *   - highlightedClusterLabel remains in useUIState (owned externally)
 *   - highlightCluster remains in useAppNavigationHighlights (owned externally)
 */
import type { Dispatch, SetStateAction } from "react";

export interface UseAppClusterSelectionHandlersArgs {
  /** Cluster selection handler from useAppData */
  hookHandleClusterSelection: (label: string, options?: { expand?: boolean }) => void;
  /** Current selected cluster label from useAppData */
  hookSelectedClusterLabel: string | null;
  /** Setter for cluster detail expansion (from useUIState) */
  setClusterDetailExpanded: Dispatch<SetStateAction<boolean>>;
}

export interface UseAppClusterSelectionHandlersReturn {
  /** Current selected cluster label */
  selectedClusterLabel: string | null;
  /** Combined cluster selection handler that coordinates hook + expansion state */
  handleClusterSelection: (label: string, options?: { expand?: boolean }) => void;
}

/**
 * Returns cluster selection handler that:
 * 1. Delegates to useAppData's handleClusterSelection for core selection logic
 * 2. Coordinates clusterDetailExpanded state based on options.expand flag
 *
 * This preserves the exact behavior of the inline handler that was in App.tsx.
 */
export function useAppClusterSelectionHandlers({
  hookHandleClusterSelection,
  hookSelectedClusterLabel,
  setClusterDetailExpanded,
}: UseAppClusterSelectionHandlersArgs): UseAppClusterSelectionHandlersReturn {
  // Derive selectedClusterLabel from hook (passthrough)
  const selectedClusterLabel = hookSelectedClusterLabel;

  // Handle cluster selection - combines hook logic with local clusterDetailExpanded state
  const handleClusterSelection = (label: string, options?: { expand?: boolean }) => {
    hookHandleClusterSelection(label, options);
    if (options?.expand) {
      setClusterDetailExpanded(true);
    }
  };

  return {
    selectedClusterLabel,
    handleClusterSelection,
  };
}