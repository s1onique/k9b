/**
 * useAppDemoShellOverlayProps - Hook for demo shell overlay state and props in App.tsx
 *
 * Extracts demo shell open/close state, open/close handlers, finding selection input
 * construction, and real-context metadata from App.tsx to reduce component size and
 * move toward LLM-friendly limits.
 *
 * Combines:
 * - useDemoShellModel state management (isOpen, openDemo, closeDemo)
 * - buildDemoShellFindingInput for selected-run → demo finding mapping
 * - realContext derivation for "real run evidence" mode
 *
 * Does NOT alter DemoShell or AppDemoShellOverlay behavior.
 */

import type { AppDemoShellOverlayProps } from "./AppDemoShellOverlay";
import { useDemoShellModel } from "../demo-shell/useDemoShellModel";
import {
  buildDemoShellFindingInput,
  type BuildDemoShellFindingInputArgs,
} from "../demo-shell/buildDemoShellFindingInput";

/** Run payload shape (subset of RunPayload) */
export interface DemoShellRunPayload {
  incidentReport?: {
    status?: "critical" | "degraded" | "warning" | "healthy";
    topFinding?: {
      affectedResource?: string;
      findingType?: string;
    };
  };
  operatorWorklist?: unknown;
  timestamp?: string;
}

/** Arguments for useAppDemoShellOverlayProps */
export interface UseAppDemoShellOverlayPropsArgs {
  /** Selected run payload */
  run: DemoShellRunPayload | null | undefined;
  /** Age of the selected run in minutes */
  runAgeMinutes: number;
  /** Whether the selected run is fresh (not stale) */
  runFresh: boolean;
  /** Currently selected run ID */
  selectedRunId: string | null;
  /** Currently selected cluster label */
  selectedClusterLabel: string | null;
  /** Timestamp when the run was captured */
  headerRunTimestamp?: string | null;
}

/** Return type for the hook */
export interface UseAppDemoShellOverlayPropsReturn {
  /** Whether the demo shell is open */
  isOpen: boolean;
  /** Open demo shell handler */
  onOpen: () => void;
  /** Close demo shell handler */
  onClose: () => void;
  /** Props for AppDemoShellOverlay component */
  overlayProps: AppDemoShellOverlayProps;
}

/**
 * Derives demo shell overlay state and props from App.tsx.
 *
 * Combines the demo shell state model with finding selection input construction
 * to provide a single source for all demo shell overlay behavior.
 *
 * The hook manages:
 * - Demo shell open/close state via useDemoShellModel
 * - Finding selection input from selected run data
 * - Real context metadata for "real run evidence" mode
 */
export function useAppDemoShellOverlayProps({
  run,
  runAgeMinutes,
  runFresh,
  selectedRunId,
  selectedClusterLabel,
  headerRunTimestamp,
}: UseAppDemoShellOverlayPropsArgs): UseAppDemoShellOverlayPropsReturn {
  // Demo shell state management
  const demoShell = useDemoShellModel();
  const { isOpen } = demoShell.state;
  const { openDemo, closeDemo } = demoShell;

  // Build finding selection input from selected run
  // This normalizes operatorWorklist shapes and maps run data to demo format
  const buildArgs: BuildDemoShellFindingInputArgs = {
    run: run ?? null,
    selectedRunId,
    selectedClusterLabel,
    runAgeMinutes,
    runFresh,
  };
  const findingSelectionInput = buildDemoShellFindingInput(buildArgs);

  // Build realContext when a run is selected (enables "real run evidence" mode)
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
    onOpen: openDemo,
    onClose: closeDemo,
    overlayProps: {
      isOpen,
      onClose: closeDemo,
      findingSelectionInput,
      realContext,
    },
  };
}
