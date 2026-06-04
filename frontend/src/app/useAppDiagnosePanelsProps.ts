/**
 * useAppDiagnosePanelsProps — Hook for AppDiagnosePanels prop wiring in App.tsx
 *
 * Extracts inline JSX prop wiring from App.tsx to reduce component size.
 *
 * Inputs:
 * - run: from useRunControl (selectedRun)
 * - selectedClusterLabel: from useAppClusterSelectionHandlers
 * - refresh: from App-level refresh callback
 * - scrollToSection: from useAppNavigationHighlights
 * - setQueueFocusMode: from useUIState
 * - handlePromoteDeterministicCheck: from useAppData
 * - toggleIncidentExpansion: local to App.tsx (incident expansion state)
 * - runSummaryLoadedProps.onFocusClusterForNextChecks: from useAppRunSummaryProps
 * - setQueueStatusFilter: from useUIState
 * - setQueueClusterFilter: from useUIState
 * - incidentExpandedClusters: from useUIState
 * - deterministicChecks: from buildDeterministicChecksProps
 * - deterministicSummary: from buildDeterministicChecksProps
 * - hookPromotionStatus: from useAppData
 * - hasDegradedClusters: from useAppRunSummaryProps
 * - artifactUrl: from utils
 *
 * Does NOT change AppDiagnosePanels rendering, deterministic check behavior,
 * incident expansion logic, queue filter behavior, or promotion flow.
 */

import type { DeterministicNextCheckSummary, PromotionStatus } from "../types";
import type { AppDiagnosePanelsProps } from "./AppDiagnosePanels";

export interface UseAppDiagnosePanelsPropsArgs {
  /** Selected run payload */
  run: AppDiagnosePanelsProps["run"];
  /** Currently selected cluster label */
  selectedClusterLabel: string | null;
  /** App-level refresh handler */
  onRefresh: () => void;
  /** Navigation to scroll to queue section */
  scrollToSection: (section: string) => void;
  /** Set queue focus mode */
  setQueueFocusMode: (mode: "none" | "review" | "approval-needed" | "pending") => void;
  /** Promote deterministic check handler */
  onPromoteCheck: (
    clusterLabel: string,
    context: string | null,
    topProblem: string | null,
    check: DeterministicNextCheckSummary,
    index: number
  ) => void;
  /** Toggle incident expansion handler */
  onToggleIncidentExpansion: (label: string) => void;
  /** Focus cluster for next checks handler */
  onFocusClusterForNextChecks: (clusterLabel?: string | null) => void;
  /** Set queue status filter */
  onSetQueueStatusFilter: (status: string) => void;
  /** Set queue cluster filter */
  onSetQueueClusterFilter: (cluster: string) => void;
  /** Incident expanded clusters state */
  incidentExpandedClusters: Record<string, boolean>;
  /** Deterministic checks data */
  deterministicChecks?: DeterministicNextCheckSummary[];
  /** Deterministic checks summary text */
  deterministicSummary?: string;
  /** Promotion status from hook */
  hookPromotionStatus: Record<string, PromotionStatus>;
  /** Whether there are degraded clusters */
  hasDegradedClusters: boolean;
  /** Artifact URL builder */
  artifactUrl: (path: string) => string;
}

/**
 * Derives props for AppDiagnosePanels from App.tsx state and handlers.
 *
 * Replaces inline JSX prop wiring with a clean hook interface.
 */
export function useAppDiagnosePanelsProps({
  run,
  selectedClusterLabel,
  onRefresh,
  scrollToSection,
  setQueueFocusMode,
  onPromoteCheck,
  onToggleIncidentExpansion,
  onFocusClusterForNextChecks,
  onSetQueueStatusFilter,
  onSetQueueClusterFilter,
  incidentExpandedClusters,
  deterministicChecks,
  deterministicSummary,
  hookPromotionStatus,
  hasDegradedClusters,
  artifactUrl,
}: UseAppDiagnosePanelsPropsArgs): AppDiagnosePanelsProps {
  return {
    run,
    selectedClusterLabel,
    onRefresh,
    onNavigateToQueue: () => scrollToSection("next-check-queue"),
    onFocusQueueReview: () => setQueueFocusMode("review"),
    onPromoteCheck,
    onToggleIncidentExpansion,
    onFocusClusterForNextChecks,
    onSetQueueStatusFilter,
    onSetQueueClusterFilter,
    onScrollToSection: scrollToSection,
    artifactUrl,
    hasDegradedClusters,
    hookPromotionStatus,
    incidentExpandedClusters,
    deterministicChecks,
    deterministicSummary,
  };
}
