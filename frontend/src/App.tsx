import { useCallback, useEffect } from "react";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import utc from "dayjs/plugin/utc";
import { useAppNavigationHighlights } from "./hooks/useAppNavigationHighlights";
import { useAppData } from "./hooks/useAppData";
import { useRunSelection } from "./hooks/useRunSelection";
import { useUIState } from "./hooks/useUIState";
import { useQueueState } from "./hooks/useQueueState";
import { useRunControl } from "./run-control";
import type {
  AlertmanagerProvenance,
  ArtifactLink,
  FeedbackAdaptationProvenance,
  FeedbackSummary,
  AutoInterpretation,
  ClusterDetailPayload,
  FleetPayload,
  LLMPolicy,
  LLMStats,
  NextCheckExecutionHistoryEntry,
  NextCheckExecutionResponse,
  NextCheckPlanCandidate,
  NextCheckQueueItem,
  NotificationDetail,
  NotificationEntry,
  NotificationsPayload,
  ProposalEntry,
  ProposalsPayload,
  ProviderExecution,
  ProviderExecutionBranch,
  DeterministicNextCheckPromotionRequest,
} from "./types";
import "./index.css";

// Extracted components
import { AppHeader } from "./app/AppHeader";
import { AppNavigation } from "./app/AppNavigation";
import { WorkflowLaneHeader } from "./app/WorkflowLaneHeader";
import { VmAlertPanels } from "./app/VmAlertPanels";
import { AppDiagnosePanels } from "./app/AppDiagnosePanels";
import { AppImprovePanels } from "./app/AppImprovePanels";
import { AppRunSummarySection } from "./app/AppRunSummarySection";
import { AppFleetSection } from "./app/AppFleetSection";
import { AppProposalsSection } from "./app/AppProposalsSection";
import { AppDemoShellOverlay } from "./app/AppDemoShellOverlay";
import { useAppRunSummaryProps } from "./app/useAppRunSummaryProps";
import { useAppClusterFocusHandler } from "./app/useAppClusterFocusHandler";
import { useAppDemoShellOverlayProps } from "./app/useAppDemoShellOverlayProps";
import { useAppProposalSectionProps } from "./app/useAppProposalSectionProps";
import { useAppClusterPlanProps } from "./app/useAppClusterPlanProps";
import { useAppWorkNextChecksLaneProps } from "./app/useAppWorkNextChecksLaneProps";
import { useAppManualExecutionHandlers } from "./app/useAppManualExecutionHandlers";
import { useApprovalFlowController } from "./app/approvalFlow";
import { useAppRunSelectionHandlers } from "./app/useAppRunSelectionHandlers";
import { useAppClusterSelectionHandlers } from "./app/useAppClusterSelectionHandlers";
import { useAppBatchExecutionHandlers } from "./app/useAppBatchExecutionHandlers";
import { useAppRecentRunsPanelProps } from "./app/useAppRecentRunsPanelProps";
import { useAppDiagnosePanelsProps } from "./app/useAppDiagnosePanelsProps";
import { useAppClusterDetailSectionProps } from "./app/useAppClusterDetailSectionProps";

import { ProposalList } from "./components/ProposalList";
import { formatDuration } from "./components/ExecutionHistoryPanel";
import { DeterministicNextChecksPanel } from "./components/DeterministicNextChecksPanel";
import { buildDeterministicChecksProps } from "./components/DeterministicNextChecksPanel/buildDeterministicChecksProps";
import { QueuePanel } from "./components/QueuePanel";
import { useAppQueuePanelProps } from "./app/useAppQueuePanelProps";
import { WorkNextChecksLane } from "./components/WorkNextChecksLane";
import { AlertmanagerSnapshotPanel, AlertmanagerSourcesPanel } from "./components/AlertmanagerPanel";
import { ClusterDetailSection } from "./components/ClusterDetailSection";
export { AlertmanagerSnapshotPanel, AlertmanagerSourcesPanel };
import { RecentRunsPanel, RunSummaryPanel } from "./components/RunsPanel";
export type { RecentRunsPanelProps, RunSummaryPanelProps } from "./components/RunsPanel";
import {
  artifactUrl,
  formatTimestamp,
  statusClass,
} from "./utils";
import {
  confidenceWeight,
  priorityLabel,
  getPageFreshnessLevel,
  getRunFreshnessLevel,
  FRESHNESS_EMOJI,
  FRESHNESS_LABEL,
  formatAgeDuration,
  AUTOREFRESH_STORAGE_KEY,
  AUTOREFRESH_OPTIONS,
  getLlmScopeLabel,
  buildClusterRecommendedArtifacts,
  safetyClass,
  formatSourceType,
  formatCandidatePriority,
  approvalStatusLabels,
  determineNextCheckStatusVariant,
  nextCheckStatusLabel,
  getPlanStatusLabel,
  buildDiscoveryVariantCounts,
  DISCOVERY_VARIANT_ORDER,
  NEXT_CHECK_QUEUE_STATUS_LABELS,
  NEXT_CHECK_QUEUE_STATUS_ORDER,
  QUEUE_SORT_OPTIONS,
  QUEUE_PRIORITY_ORDER,
  QUEUE_FOCUS_FILTERS,
  RUNS_REVIEW_FILTER_OPTIONS,
  computeRunsFilterCounts,
  RUNS_REVIEW_FILTER_VALUES,
  isRunsReviewFilterValue,
  normalizeQueuePriority,
  queuePriorityRank,
  queueTimestampValue,
  outcomeStatusLabels,
  outcomeStatusDisplay,
  outcomeStatusClass,
  parseNextCheckEntry,
  formatAlertmanagerPromotion,
  getAlertmanagerPromotionSubtext,
  formatAlertmanagerProvenance,
  getAlertmanagerProvenanceSubtext,
  formatFeedbackAdaptationProvenance,
  formatFeedbackSummary,
  getFeedbackAdaptationProvenanceSubtext,
  type ParsedNextCheck,
  type NextCheckStatusVariant,
  type NextCheckQueueStatus,
  type QueueSortOption,
  type QueueFocusMode,
  type RunsReviewFilter,
} from "./utils/selectors";
// Re-export for backward compatibility with existing tests and importers
export { AUTOREFRESH_STORAGE_KEY, formatAgeDuration } from "./utils/selectors";
// Re-export parseNextCheckEntry for components that import from App
export { parseNextCheckEntry } from "./utils/selectors";
// Re-export types
export type { ParsedNextCheck } from "./utils/selectors";
// Re-export ProposalList for backward compatibility with tests that import from App
export { ProposalList } from "./components/ProposalList";
// Import persistence helpers for localStorage state
import {
  clearStoredQueueViewState,
  DEFAULT_QUEUE_VIEW_STATE,
  persistSelectedRunId,
  QUEUE_VIEW_STORAGE_KEY,
  readStoredQueueViewState,
  readStoredRunsPageSize,
  readStoredRunsReviewFilter,
  readStoredSelectedRunId,
  RUNS_PAGE_SIZE_STORAGE_KEY,
  RUNS_REVIEW_FILTER_STORAGE_KEY,
  SELECTED_RUN_STORAGE_KEY,
  type QueueViewState,
} from "./utils/persistence";
// Re-export persistence storage keys for backward compatibility
export {
  QUEUE_VIEW_STORAGE_KEY,
  RUNS_PAGE_SIZE_STORAGE_KEY,
  RUNS_REVIEW_FILTER_STORAGE_KEY,
  SELECTED_RUN_STORAGE_KEY,
} from "./utils/persistence";

import { useAppHeaderProps } from "./app/useAppHeaderProps";

dayjs.extend(relativeTime);
dayjs.extend(utc);


const App = () => {
  // Phase 3: Run Control Plane - source of truth for selected-run causal chain
  // Single useRunControl call provides all selected-run state and actions
  const {
    selectedRunId,
    latestRunId,
    selectedRun,
    selectedRunStatus,
    selectedRunError,
    runOwnedPanelState,
    clickLatest,
    poll,
    retrySelectedRun,
    model,
    selectRun: runControlSelectRun,
  } = useRunControl({
    autoBoot: true,
    slowAfterMs: 10_000,
  });

  // Phase 5: RunControl owns runs list data
  // Pass runs, isLoading, and error from RunControl model to useRunSelection
  const runsListFromModel = model.runs.items;
  const runsListLoadingFromModel = model.runs.status === "loading";
  const runsListErrorFromModel = model.runs.error;

  // Run selection state - extracted to useRunSelection hook
  // PHASE 5: This hook now receives runs data as INPUT (from RunControl)
  // It only owns pagination/filter/navigation helpers and autoRefreshInterval preference
  const {
    runs: runsList,
    isLoading: runsListLoading,
    error: runsListError,
    autoRefreshInterval,
    handleAutoRefreshChange,
    // Pagination and filter state
    runsFilter,
    setRunsFilter,
    runsPageSize,
    setRunsPageSize,
    runsPage,
    setRunsPage,
    isRunsListFollowingSelection,
    setIsRunsListFollowingSelection,
    filteredRunsList,
    runsFilterCounts,
    paginatedRunsList,
    totalRunsPages,
    isSelectedRunVisibleOnCurrentRunsPage,
    handleRunsFilterChange,
    handleRunsPageSizeChange,
    handleRunsPageChange,
    navigateToPageContainingRun,
    handleShowSelectedRun,
  } = useRunSelection({
    selectedRunId,
    runs: runsListFromModel,
    isLoading: runsListLoadingFromModel,
    error: runsListErrorFromModel,
  });

  // Phase 5: App.tsx owns the auto-refresh timer
  // This timer calls RunControl's poll() which is the single authoritative refresh path
  // Previously this timer lived in useRunSelection which caused dual-write refresh
  useEffect(() => {
    if (!autoRefreshInterval) {
      return; // Auto-refresh disabled
    }
    const timerId = setInterval(() => {
      poll(); // RunControl's poll() updates model.runs.lastLoadedAtMs for page freshness
    }, autoRefreshInterval * 1000);
    return () => clearInterval(timerId);
  }, [autoRefreshInterval, poll]);

  // Run payload from RunControl (now the authoritative source)
  const run = selectedRun;

  // Phase 3: Derive header freshness from RunControl model instead of local state
  // model.runs.lastLoadedAtMs is updated by the reducer when runs list loads
  const lastRefreshMs = model.runs.lastLoadedAtMs ?? null;
  const lastRefresh = lastRefreshMs ? dayjs(lastRefreshMs) : dayjs();

  // App data state - extracted to useAppData hook
  const {
    fleet,
    proposals,
    expandedProposals,
    handleToggleProposal,
    statusOptions,
    clusterDetail,
    selectedClusterLabel: hookSelectedClusterLabel,
    handleClusterSelection: hookHandleClusterSelection,
    promotionStatus: hookPromotionStatus,
    refreshAppData,
    handlePromoteDeterministicCheck,
    handleUsefulnessFeedback,
    handleAlertmanagerRelevanceFeedback,
    error,
  } = useAppData({
    selectedRunId,
    lastRefreshMs,
    // useAppData refreshes fleet/proposals internally; RunControl owns runs refresh.
    // The runs list is refreshed via RunControl's poll() which is called by the App.tsx timer.
  });

  // isSelectedRunLatest derived from RunControl's selectedRunId vs latestRunId
  const isSelectedRunLatest = selectedRunId !== null && selectedRunId === latestRunId;

  // UI state - extracted to useUIState hook
  const {
    statusFilter,
    setStatusFilter,
    searchText,
    setSearchText,
    sortKey,
    setSortKey,
    activeTab,
    setActiveTab,
    clusterDetailExpanded,
    setClusterDetailExpanded,
    highlightedClusterLabel,
    setHighlightedClusterLabel,
    incidentExpandedClusters,
    setIncidentExpandedClusters,
    executionHistoryHighlightKey,
    setExecutionHistoryHighlightKey,
    queueHighlightKey,
    setQueueHighlightKey,
    executionHistoryFilter,
    setExecutionHistoryFilter,
    expandedQueueItems,
    setExpandedQueueItems,
    toggleQueueDetails,
  } = useUIState();

  // Queue state - derived from run data
  const runQueue: NextCheckQueueItem[] = run?.nextCheckQueue ?? [];

  // Queue state - managed by useQueueState hook
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
    filteredQueue,
    sortedQueue,
    queueGroups,
  } = useQueueState({ runQueue });

  // Execution history derived from run data - needed by useAppNavigationHighlights
  const executionHistory: NextCheckExecutionHistoryEntry[] = run?.nextCheckExecutionHistory ?? [];

  // findExecutionHistoryEntry must be defined before useAppNavigationHighlights hook
  const findExecutionHistoryEntry = (candidate: NextCheckQueueItem) => {
    if (!executionHistory.length) {
      return null;
    }
    if (candidate.latestArtifactPath) {
      const artifactMatch = executionHistory.find(
        (entry) => entry.artifactPath === candidate.latestArtifactPath
      );
      if (artifactMatch) {
        return artifactMatch;
      }
    }
    const normalizedDescription = candidate.description?.trim();
    if (candidate.targetCluster && normalizedDescription) {
      const contextMatch = executionHistory.find(
        (entry) =>
          entry.clusterLabel === candidate.targetCluster &&
          entry.candidateDescription === normalizedDescription
      );
      if (contextMatch) {
        return contextMatch;
      }
    }
    if (normalizedDescription) {
      const descriptionMatch = executionHistory.find(
        (entry) => entry.candidateDescription === normalizedDescription
      );
      if (descriptionMatch) {
        return descriptionMatch;
      }
    }
    return null;
  };

  // Batch execution handlers - extracted to hook
  const {
    executingBatchRunId,
    batchExecutionError,
    handleBatchExecution,
  } = useAppBatchExecutionHandlers({
    selectedRunId,
    poll,
    retrySelectedRun,
  });

  // Run selection handlers - extracted to hook
  const { handleRunSelectionViaRunControl } = useAppRunSelectionHandlers({
    runControlSelectRun,
    navigateToPageContainingRun,
  });

  // Cluster selection handlers - extracted to hook
  const { selectedClusterLabel, handleClusterSelection } = useAppClusterSelectionHandlers({
    hookHandleClusterSelection,
    hookSelectedClusterLabel,
    setClusterDetailExpanded,
  });

  const {
    scrollToSection,
    highlightCluster,
    highlightQueueCard,
    handleBackToQueue,
    handleQueueClusterJump,
    handleQueueExecutionJump,
  } = useAppNavigationHighlights({
    setHighlightedClusterLabel,
    setExecutionHistoryHighlightKey,
    setQueueHighlightKey,
    onClusterSelect: handleClusterSelection,
    findExecutionHistoryEntry,
    getDiscoveryClusters: () => discoveryClusters,
    getSelectedClusterLabel: () => selectedClusterLabel,
  });

  // Manual execution handlers - extracted to hook to reduce App.tsx size
  // Note: Placed after useAppNavigationHighlights so highlightQueueCard is available (TDZ fix)
  const {
    executionResults,
    executingCandidate,
    handleManualExecution,
    getNotRunnableExplanation,
    isManualExecutionAllowed,
    buildCandidateKey,
    clearExecutionResults,
    handlePostExecutionHighlight,
  } = useAppManualExecutionHandlers({
    selectedClusterLabel: hookSelectedClusterLabel,
    highlightQueueCard,
  });

  // App-level refresh wrapper - must be defined BEFORE the approval flow controller
  // because the controller receives refresh as a dependency.
  const refresh = useCallback(async () => {
    await refreshAppData();
    // Clear local execution results after successful refresh reconciliation.
    // This allows the UI to transition from transient local execution state
    // to refreshed artifact-backed payload as the durable source of truth.
    clearExecutionResults();
    // After successful refresh reconciliation, highlight the last executed candidate
    // if we have a tracked key from a recent manual execution.
    handlePostExecutionHighlight();
  }, [refreshAppData, clearExecutionResults, handlePostExecutionHighlight]);

  // Approval flow - Elm-ish state machine for candidate approval
  const {
    approvalResults,
    approvingCandidate,
    handleApproveCandidate,
    clearApprovalResults,
  } = useApprovalFlowController({
    selectedClusterLabel: hookSelectedClusterLabel,
    refresh,
  });

  // Build promotion key helper
  const buildPromotionKey = (clusterLabel: string, description: string, index: number) =>
    `${clusterLabel}::${description}::${index}`;

  // toggleIncidentExpansion remains in App.tsx - more coupled to incident expansion state
  const toggleIncidentExpansion = (label: string) => {
    setIncidentExpandedClusters((current) => ({
      ...current,
      [label]: !current[label],
    }));
  };

  const queueExplanation = run?.nextCheckQueueExplanation ?? null;

  const toggleQueueFocusPreset = (mode: QueueFocusMode) => {
    setQueueFocusMode((current) => (current === mode ? "none" : mode));
  };

  const resetQueueFilters = () => {
    setQueueClusterFilter(DEFAULT_QUEUE_VIEW_STATE.clusterFilter);
    setQueueStatusFilter(DEFAULT_QUEUE_VIEW_STATE.statusFilter);
    setQueueCommandFamilyFilter(DEFAULT_QUEUE_VIEW_STATE.commandFamilyFilter);
    setQueuePriorityFilter(DEFAULT_QUEUE_VIEW_STATE.priorityFilter);
    setQueueWorkstreamFilter(DEFAULT_QUEUE_VIEW_STATE.workstreamFilter);
    setQueueSearch(DEFAULT_QUEUE_VIEW_STATE.searchText);
    setQueueSortOption(DEFAULT_QUEUE_VIEW_STATE.sortOption);
    setQueueFocusMode(DEFAULT_QUEUE_VIEW_STATE.focusMode);
  };

  const resetQueueView = () => {
    resetQueueFilters();
    clearStoredQueueViewState();
  };

  // Extract header props - MUST be before early return for hook consistency
  // Also extracts freshness-related values needed by useAppDemoShellOverlayProps
  // Must compute freshness values BEFORE calling useAppDemoShellOverlayProps
  // because headerRunTimestamp is needed by both hooks
  const { headerDerivedProps, headerRunTimestamp, runFresh, runAgeMinutes, headerStats } = useAppHeaderProps({
    run,
    runsList,
    selectedRunId,
    isSelectedRunLatest,
    latestRunId,
    lastRefresh,
    autoRefreshInterval,
    refresh,
    handleAutoRefreshChange,
    clickLatest,
  });

  // Extract demo shell overlay props - MUST be before early return to maintain hook order
  // This hook uses useDemoShellModel (useReducer) which must always be called in the same order
  // Call it only ONCE to avoid creating duplicate demo-shell state
  const { onOpen: demoShellOpen, overlayProps: demoShellOverlayProps } = useAppDemoShellOverlayProps({
    run,
    runAgeMinutes,
    runFresh,
    selectedRunId,
    selectedClusterLabel,
    headerRunTimestamp,
  });

  // Build appHeaderProps by combining header derived props with demo shell open handler
  const appHeaderProps = {
    ...headerDerivedProps,
    onOpenDemo: demoShellOpen,
  };

  // Progressive loading: only wait for CRITICAL data (fleet + proposals).
  // Run detail is non-critical - shell renders immediately, run panels show local loading.
  if (!fleet || !proposals) {
    return (
      <div className="app-shell loading">
        <div>
          <p>Loading operator data…</p>
          {error && <div className="alert">{error}</div>}
        </div>
      </div>
    );
  }

  // Extract cluster detail section props
  const clusterDetailSectionProps = useAppClusterDetailSectionProps({
    clusterDetail,
    selectedClusterLabel,
    fleet,
    run,
    executionResults,
    approvalResults,
    executingCandidate,
    approvingCandidate,
    handleApproveCandidate,
    handleManualExecution,
    refresh,
    buildCandidateKey,
    isManualExecutionAllowed,
    activeTab,
    setActiveTab,
    clusterDetailExpanded,
    setClusterDetailExpanded,
    highlightedClusterLabel,
    handleClusterSelection,
    artifactUrl,
    formatTimestamp,
    statusClass,
  });

  const planCandidates: NextCheckPlanCandidate[] = clusterDetail?.nextCheckPlan ?? [];
  const runPlan = run?.nextCheckPlan;
  const plannerAvailability = run?.plannerAvailability ?? null;
  const plannerReason = plannerAvailability?.reason;
  const plannerHint = plannerAvailability?.hint;
  const plannerArtifactPath = plannerAvailability?.artifactPath ?? runPlan?.artifactPath ?? null;
  const plannerArtifactUrl = plannerArtifactPath ? artifactUrl(plannerArtifactPath) : null;
  const plannerNextActionHint = plannerAvailability?.nextActionHint;
  const planSummaryText =
    runPlan?.summary ?? plannerReason ?? "Provider-assisted next-check candidates are available.";
  const plannerReasonText = plannerReason ?? "Planner data is not available for this run.";
  const planCandidateCountLabel =
    runPlan?.candidateCount != null
      ? `${runPlan.candidateCount} candidate${runPlan.candidateCount === 1 ? "" : "s"}`
      : `${planCandidates.length} candidate${planCandidates.length === 1 ? "" : "s"}`;
  const planStatusText = runPlan?.status ?? null;

  const runPlanCandidates: NextCheckPlanCandidate[] = runPlan?.candidates ?? [];
  const discoveryVariantOrder: NextCheckStatusVariant[] = DISCOVERY_VARIANT_ORDER;
  const discoveryVariantCounts = buildDiscoveryVariantCounts(runPlanCandidates);
  const discoveryClusters = Array.from(
    new Set(
      runPlanCandidates
        .map((candidate) => candidate.targetCluster)
        .filter((label): label is string => Boolean(label))
    )
  );

  const {
    deterministicChecks,
    deterministicSummary,
  } = buildDeterministicChecksProps({ run });

  // Extract cluster focus handler - must be called before useAppRunSummaryProps to preserve hook order
  // Note: discoveryClusters must be computed above this line
  const { focusClusterForNextChecks } = useAppClusterFocusHandler({
    discoveryClusters,
    selectedClusterLabel,
    fleet,
    handleClusterSelection,
    highlightCluster,
    scrollToSection,
  });

  // Build props for RunSummaryPanel using the extracted hook
  const {
    runSummaryLoadedProps,
    runSummaryUnavailableProps,
    hasDegradedClusters,
  } = useAppRunSummaryProps({
    run,
    isSelectedRunLatest,
    selectedRunId,
    runOwnedPanelState,
    selectedRunError,
    onRetrySelectedRun: retrySelectedRun,
    selectedClusterLabel,
    onFocusClusterForNextChecks: focusClusterForNextChecks,
    fleet,
    headerStats,
    runPlan,
    runPlanCandidates,
    planSummaryText,
    planStatusText,
    plannerReasonText,
    plannerHint,
    plannerNextActionHint,
    plannerArtifactUrl,
    planCandidateCountLabel,
    discoveryVariantOrder,
    discoveryVariantCounts,
    discoveryClusters,
  });

  const queuePanelProps = useAppQueuePanelProps({
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
    getFeedbackAdaptationProvenanceSubtext,
    formatFeedbackAdaptationProvenance,
    getAlertmanagerPromotionSubtext,
    formatAlertmanagerPromotion,
    refresh,
  });

  // Extract proposal section props
  const proposalSectionProps = useAppProposalSectionProps({
    proposals,
    statusFilter,
    sortKey,
    searchText,
    statusOptions,
    expandedProposals,
    setStatusFilter,
    setSortKey,
    setSearchText,
    handleToggleProposal,
  });

  // Extract work next checks lane props
  const workNextChecksLaneProps = useAppWorkNextChecksLaneProps({
    run,
    executionHistory,
    runQueue,
    executionHistoryHighlightKey,
    handleUsefulnessFeedback,
    handleAlertmanagerRelevanceFeedback,
    executionHistoryFilter,
    setExecutionHistoryFilter,
    highlightQueueCard,
    queuePanelProps,
  });

  // Extract recent runs panel props
  const recentRunsPanelProps = useAppRecentRunsPanelProps({
    runsList,
    selectedRunId,
    runsFilter,
    runsFilterCounts,
    paginatedRunsList,
    filteredRunsList,
    runsListLoading,
    runsListError,
    runsPage,
    totalRunsPages,
    runsPageSize,
    isRunsListFollowingSelection,
    isSelectedRunVisibleOnCurrentRunsPage,
    executingBatchRunId,
    batchExecutionError,
    onRunsFilterChange: handleRunsFilterChange,
    onRunsPageChange: handleRunsPageChange,
    onRunsPageSizeChange: handleRunsPageSizeChange,
    onRunSelection: handleRunSelectionViaRunControl,
    onBatchExecution: handleBatchExecution,
    onShowSelectedRun: handleShowSelectedRun,
    onFocusClusterForNextChecks: runSummaryLoadedProps.onFocusClusterForNextChecks,
  });

  // Extract diagnose panels props
  const diagnosePanelsProps = useAppDiagnosePanelsProps({
    run,
    selectedClusterLabel,
    onRefresh: refresh,
    scrollToSection,
    setQueueFocusMode,
    onPromoteCheck: handlePromoteDeterministicCheck,
    onToggleIncidentExpansion: toggleIncidentExpansion,
    onFocusClusterForNextChecks: runSummaryLoadedProps.onFocusClusterForNextChecks,
    onSetQueueStatusFilter: setQueueStatusFilter,
    onSetQueueClusterFilter: setQueueClusterFilter,
    incidentExpandedClusters,
    deterministicChecks,
    deterministicSummary,
    hookPromotionStatus,
    hasDegradedClusters,
    artifactUrl,
  });

  return (
    <div className="app-shell">
      <AppHeader {...appHeaderProps} />
      <AppNavigation run={run} />
      {error && <div className="alert">{error}</div>}
      <RecentRunsPanel {...recentRunsPanelProps} />
      <AppRunSummarySection
        run={run}
        runOwnedPanelState={runOwnedPanelState}
        loadedProps={runSummaryLoadedProps}
        unavailableProps={runSummaryUnavailableProps}
      />
      <WorkflowLaneHeader type="diagnose" />
      <AppDiagnosePanels {...diagnosePanelsProps} />
      <VmAlertPanels
        vmalertSources={run?.vmalertSources}
        vmalertRuleState={run?.vmalertRuleState}
      />
      <WorkNextChecksLane {...workNextChecksLaneProps} />
      <AppFleetSection
        fleet={fleet}
        selectedClusterLabel={selectedClusterLabel}
        highlightedClusterLabel={highlightedClusterLabel}
        onClusterSelect={handleClusterSelection}
      />
      <ClusterDetailSection {...clusterDetailSectionProps} />
    <WorkflowLaneHeader type="improve" />
      <AppProposalsSection {...proposalSectionProps} />
      <AppImprovePanels run={run} />
      <AppDemoShellOverlay {...demoShellOverlayProps} />
    </div>
  );
};

export default App;
