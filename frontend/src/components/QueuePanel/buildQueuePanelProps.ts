/**
 * QueuePanel props builder - extracts prop packaging from App.tsx.
 *
 * This module creates a clean seam for QueuePanel props without changing behavior.
 *
 * @module components/QueuePanel
 */
import type {
  AlertmanagerProvenance,
  FeedbackAdaptationProvenance,
  NextCheckExecutionHistoryEntry,
  NextCheckQueueExplanation,
  NextCheckExecutionResponse,
  NextCheckQueueItem,
  NextCheckQueueStatus,
} from "../../types";
import type { QueuePanelProps } from "./QueuePanel";

// Re-export the component's props interface for consumers
export type { QueuePanelProps };

// ============================================================================
// Builder arguments
// ============================================================================

export interface BuildQueuePanelPropsArgs {
  // Queue state (filtering/sorting)
  queueClusterFilter: string;
  queueStatusFilter: NextCheckQueueStatus | "all";
  queueCommandFamilyFilter: string;
  queuePriorityFilter: string;
  queueWorkstreamFilter: string;
  queueSearch: string;
  queueSortOption: string;
  queueFocusMode: string;
  // Setters
  setQueueClusterFilter: (v: string) => void;
  setQueueStatusFilter: (v: NextCheckQueueStatus | "all") => void;
  setQueueCommandFamilyFilter: (v: string) => void;
  setQueuePriorityFilter: (v: string) => void;
  setQueueWorkstreamFilter: (v: string) => void;
  setQueueSearch: (v: string) => void;
  setQueueSortOption: (v: string) => void;
  setQueueFocusMode: (v: string) => void;
  // Options
  queueClusterOptions: string[];
  queueCommandFamilyOptions: string[];
  queuePriorityOptions: string[];
  queueWorkstreamOptions: string[];
  // Queue data
  runQueue: NextCheckQueueItem[];
  sortedQueue: NextCheckQueueItem[];
  queueGroups: Array<{
    status: NextCheckQueueStatus;
    label: string;
    items: NextCheckQueueItem[];
  }>;
  queueExplanation: NextCheckQueueExplanation | null | undefined;
  // UI state
  expandedQueueItems: Record<string, boolean>;
  toggleQueueDetails: (key: string) => void;
  queueHighlightKey: string | null;
  // Execution/approval state
  executionResults: Record<string, QueueExecutionResult>;
  approvalResults: Record<string, QueueApprovalResult>;
  executingCandidate: string | null;
  approvingCandidate: string | null;
  // Actions
  toggleQueueFocusPreset: (mode: string) => void;
  resetQueueFilters: () => void;
  resetQueueView: () => void;
  handleBackToQueue: () => void;
  handleManualExecution: (candidate: NextCheckQueueItem, key: string) => void;
  handleApproveCandidate: (candidate: NextCheckQueueItem, key: string) => void;
  handleQueueClusterJump: (candidate: NextCheckQueueItem) => void;
  handleQueueExecutionJump: (candidate: NextCheckQueueItem) => void;
  // Helpers
  buildCandidateKey: (candidate: NextCheckQueueItem, index: number) => string;
  findExecutionHistoryEntry: (candidate: NextCheckQueueItem) => NextCheckExecutionHistoryEntry | null;
  isManualExecutionAllowed: (candidate: NextCheckQueueItem) => boolean;
  getNotRunnableExplanation: (candidate: NextCheckQueueItem) => string | null;
  // Alertmanager display helpers
  getAlertmanagerProvenanceSubtext: (provenance: AlertmanagerProvenance) => string;
  formatAlertmanagerProvenance: (provenance: AlertmanagerProvenance) => string;
  getAlertmanagerPromotionSubtext: (rankingReason: string) => string | null;
  formatAlertmanagerPromotion: (rankingReason: string) => string;
  // Feedback adaptation display helpers
  getFeedbackAdaptationProvenanceSubtext: (provenance: FeedbackAdaptationProvenance) => string;
  formatFeedbackAdaptationProvenance: (provenance: FeedbackAdaptationProvenance) => string;
  // Refresh callback
  refresh: () => void;
}

// ============================================================================
// Local types (shared with QueuePanel.tsx)
// ============================================================================

type ExecutionErrorResult = {
  status: "error";
  summary: string;
  blockingReason?: string | null;
};

type QueueExecutionResult = NextCheckExecutionResponse | ExecutionErrorResult;

type QueueApprovalResult = {
  status: "success" | "error";
  summary: string;
  artifactPath?: string | null;
  approvalTimestamp?: string | null;
};

// ============================================================================
// Builder
// ============================================================================

/**
 * Build QueuePanel props from App-level state and handlers.
 *
 * This is a pure function - no hooks. Prop values are passed in from App.tsx
 * which owns all state and derives the necessary values.
 */
export function buildQueuePanelProps(args: BuildQueuePanelPropsArgs): QueuePanelProps {
  const {
    queueClusterFilter,
    queueStatusFilter,
    queueCommandFamilyFilter,
    queuePriorityFilter,
    queueWorkstreamFilter,
    queueSearch,
    queueSortOption,
    queueFocusMode,
    setQueueClusterFilter,
    setQueueStatusFilter,
    setQueueCommandFamilyFilter,
    setQueuePriorityFilter,
    setQueueWorkstreamFilter,
    setQueueSearch,
    setQueueSortOption,
    setQueueFocusMode,
    queueClusterOptions,
    queueCommandFamilyOptions,
    queuePriorityOptions,
    queueWorkstreamOptions,
    runQueue,
    sortedQueue,
    queueGroups,
    queueExplanation,
    expandedQueueItems,
    toggleQueueDetails,
    queueHighlightKey,
    executionResults,
    approvalResults,
    executingCandidate,
    approvingCandidate,
    toggleQueueFocusPreset,
    resetQueueFilters,
    resetQueueView,
    handleBackToQueue,
    handleManualExecution,
    handleApproveCandidate,
    handleQueueClusterJump,
    handleQueueExecutionJump,
    buildCandidateKey,
    findExecutionHistoryEntry,
    isManualExecutionAllowed,
    getNotRunnableExplanation,
    getAlertmanagerProvenanceSubtext,
    formatAlertmanagerProvenance,
    getAlertmanagerPromotionSubtext,
    formatAlertmanagerPromotion,
    getFeedbackAdaptationProvenanceSubtext,
    formatFeedbackAdaptationProvenance,
    refresh,
  } = args;

  return {
    queueClusterFilter,
    queueStatusFilter,
    queueCommandFamilyFilter,
    queuePriorityFilter,
    queueWorkstreamFilter,
    queueSearch,
    queueSortOption,
    queueFocusMode,
    setQueueClusterFilter,
    setQueueStatusFilter,
    setQueueCommandFamilyFilter,
    setQueuePriorityFilter,
    setQueueWorkstreamFilter,
    setQueueSearch,
    setQueueSortOption,
    setQueueFocusMode,
    queueClusterOptions,
    queueCommandFamilyOptions,
    queuePriorityOptions,
    queueWorkstreamOptions,
    runQueue,
    sortedQueue,
    queueGroups,
    queueExplanation,
    expandedQueueItems,
    toggleQueueDetails,
    queueHighlightKey,
    executionResults,
    approvalResults,
    executingCandidate,
    approvingCandidate,
    onToggleQueueFocusPreset: toggleQueueFocusPreset,
    onResetQueueFilters: resetQueueFilters,
    onResetQueueView: resetQueueView,
    onBackToQueue: handleBackToQueue,
    onManualExecution: handleManualExecution,
    onApproveCandidate: handleApproveCandidate,
    onQueueClusterJump: handleQueueClusterJump,
    onQueueExecutionJump: handleQueueExecutionJump,
    buildCandidateKey,
    findExecutionHistoryEntry,
    isManualExecutionAllowed,
    getNotRunnableExplanation,
    getAlertmanagerProvenanceSubtext,
    formatAlertmanagerProvenance,
    getAlertmanagerPromotionSubtext,
    formatAlertmanagerPromotion,
    getFeedbackAdaptationProvenanceSubtext,
    formatFeedbackAdaptationProvenance,
    onRefresh: refresh,
  };
}
