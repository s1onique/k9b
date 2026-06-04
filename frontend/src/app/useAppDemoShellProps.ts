/**
 * useAppDemoShellProps - Hook for deriving demo shell overlay props in App.tsx
 *
 * Extracts the construction of realContext for the demo shell overlay from App.tsx
 * to reduce component size and move toward LLM-friendly limits.
 *
 * The hook takes props that are already computed in App.tsx and derives the
 * realContext object used by the demo shell to show "real run evidence" mode.
 *
 * Does NOT alter DemoShell or AppDemoShellOverlay behavior.
 */

import type { AppDemoShellOverlayProps } from "./AppDemoShellOverlay";

export interface UseAppDemoShellPropsArgs {
  /** Demo shell open state */
  isOpen: boolean;
  /** Close demo shell handler */
  onClose: () => void;
  /** Pre-built finding selection input from App.tsx */
  findingSelectionInput: AppDemoShellOverlayProps["findingSelectionInput"];
  /** Currently selected run ID */
  selectedRunId: string | null;
  /** Currently selected cluster label */
  selectedClusterLabel: string | null;
  /** Whether the run is considered fresh (not stale) */
  runFresh: boolean;
  /** Timestamp when the run was captured */
  headerRunTimestamp: string | null | undefined;
}

/**
 * Derives props for AppDemoShellOverlay from App.tsx state.
 *
 * Constructs the realContext object that enables "real run evidence" mode
 * in the demo shell, showing the selected run ID, cluster, and freshness status.
 *
 * The realContext object is only populated when a run is selected (selectedRunId is truthy).
 * When no run is selected, realContext remains undefined to show the default demo mode.
 */
export function useAppDemoShellProps({
  isOpen,
  onClose,
  findingSelectionInput,
  selectedRunId,
  selectedClusterLabel,
  runFresh,
  headerRunTimestamp,
}: UseAppDemoShellPropsArgs): AppDemoShellOverlayProps {
  // Build realContext only when a run is selected
  const realContext = selectedRunId
    ? {
        runId: selectedRunId,
        clusterLabel: selectedClusterLabel ?? undefined,
        isFresh: runFresh,
        runCapturedAt: headerRunTimestamp || undefined,
      }
    : undefined;

  return {
    isOpen,
    onClose,
    findingSelectionInput,
    realContext,
  };
}
