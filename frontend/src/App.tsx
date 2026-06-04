import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import utc from "dayjs/plugin/utc";
import {
  approveNextCheckCandidate,
  executeNextCheckCandidate,
  fetchNotifications,
  runBatchExecution,
  submitUsefulnessFeedback,
} from "./api";
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

import { ProposalList } from "./components/ProposalList";
import { buildExecutionEntryKey, formatDuration } from "./components/ExecutionHistoryPanel";
import { NotificationHistoryTable } from "./components/NotificationHistoryTable";
import { DeterministicNextChecksPanel } from "./components/DeterministicNextChecksPanel";
import { buildDeterministicChecksProps } from "./components/DeterministicNextChecksPanel/buildDeterministicChecksProps";
import { QueuePanel } from "./components/QueuePanel";
import { buildQueuePanelProps } from "./components/QueuePanel/buildQueuePanelProps";
import { WorkNextChecksLane } from "./components/WorkNextChecksLane";
import { DemoShell } from "./components/DemoShell";
import { useDemoShellModel } from "./demo-shell/useDemoShellModel";
import { buildDemoShellFindingInput } from "./demo-shell/buildDemoShellFindingInput";
import { AlertmanagerSnapshotPanel, AlertmanagerSourcesPanel } from "./components/AlertmanagerPanel";
import { ClusterDetailSection } from "./components/ClusterDetailSection";
import { buildClusterDetailSectionProps } from "./components/ClusterDetailSection/buildClusterDetailSectionProps";
import { buildClusterPlanSectionProps } from "./components/ClusterDetailSection/buildClusterPlanSectionProps";
import { VmalertDiscoveryPanel } from "./components/VmalertDiscoveryPanel";
import { VmalertAlertStatePanel } from "./components/VmalertAlertStatePanel";
export { AlertmanagerSnapshotPanel, AlertmanagerSourcesPanel };
import { RecentRunsPanel, RunSummaryPanel } from "./components/RunsPanel";
export type { RecentRunsPanelProps, RunSummaryPanelProps } from "./components/RunsPanel";
import {
  artifactUrl,
  formatTimestamp,
  formatLatency,
  normalizeFilterValue,
  relativeRecency,
  statusClass,
  truncateText,
  isItemExecuted,
} from "./utils";
import {
  confidenceWeight,
  priorityLabel,
  getPageFreshnessLevel,
  getRunFreshnessLevel,
  FRESHNESS_EMOJI,
  FRESHNESS_LABEL,
  FRESHNESS_THRESHOLD_MINUTES,
  isStaleTimestamp,
  formatAgeDuration,
  AUTOREFRESH_STORAGE_KEY,
  AUTOREFRESH_OPTIONS,
  getLlmScopeLabel,
  buildClusterRecommendedArtifacts,
  safetyClass,
  formatSourceType,
  humanizeReason,
  formatCandidatePriority,
  ALLOWED_MANUAL_FAMILIES,
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
  persistQueueViewState,
  persistRunsPageSize,
  persistRunsReviewFilter,
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

import { useRunHeaderModel } from "./components/run-summary/useRunHeaderModel";

dayjs.extend(relativeTime);
dayjs.extend(utc);

type SortKey = "proposalId" | "confidence" | "status";

const NAVIGATION_HIGHLIGHT_DURATION_MS = 2200;

// ==========================================================================
// Specialized lower advisory section components
// ==========================================================================

/** Top concerns - compact concern rows with left accent */

/** Evidence gaps - uncertainty-oriented rows with gap marker */

/** Next checks - action rows with parsed intent, cluster badge, and command preview */

/** Focus notes - demoted secondary guidance hints */

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
    showLatestJump,
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
    computePageForRunId,
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

  // Derive combined loading and error state (using RunControl for selected run state)
  // isLoading is no longer tied to run detail fetch - fleet/proposals are the critical path
  const isLoading = runsListLoading;
  const isError = error;
  
  // isSelectedRunLatest derived from RunControl's selectedRunId vs latestRunId
  const isSelectedRunLatest = selectedRunId !== null && selectedRunId === latestRunId;

  // Derive header display model from extracted hook
  const headerModel = useRunHeaderModel({
    run,
    runsList,
    selectedRunId,
    latestRunId,
  });

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

  // Execution/approval transient state - stays in App.tsx (per-execution lifecycle)
  const [executionResults, setExecutionResults] = useState<Record<string, ExecutionResult>>({});
  const [executingCandidate, setExecutingCandidate] = useState<string | null>(null);
  const [approvalResults, setApprovalResults] = useState<Record<string, ApprovalResult>>({});
  const [approvingCandidate, setApprovingCandidate] = useState<string | null>(null);
  // Track the last executed candidate key so we can highlight it after refresh
  const lastExecutedCandidateKey = useRef<string | null>(null);

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

  // Batch execution state for recent runs
  const [executingBatchRunId, setExecutingBatchRunId] = useState<string | null>(null);
  const [batchExecutionError, setBatchExecutionError] = useState<Record<string, string>>({});

  // Demo shell state - ACT 9.5: Mount K8s Accelerator demo shell in UI
  // Elm-ish model extracted for clean hook ordering
  const demoShell = useDemoShellModel();

  // Run selection causal chain:
  // - runControlSelectRun triggers RunControl to fetch /api/run for the selected run.
  // - navigateToPageContainingRun keeps the Recent Runs list page in sync with the selected run.
  // Keep these actions together: RunControl owns selected-run data; useRunSelection owns list navigation.
  //
  // Phase 3: Wire RecentRunsPanel's onRunSelection to use RunControl
  // This ensures the causal chain goes through RunControl: selection -> fetch -> payload
  const handleRunSelectionViaRunControl = useCallback((runId: string) => {
    // Select run in RunControl (fetches run payload, updates header)
    runControlSelectRun(runId);
    // Navigate to the page containing the selected run so it becomes visible in the list
    navigateToPageContainingRun(runId);
  }, [runControlSelectRun, navigateToPageContainingRun]);

  // Handle batch execution for a run - refreshes runs list and selected run via hooks
  // Phase 5: Uses RunControl's poll() to refresh runs after batch execution completes
  const handleBatchExecution = useCallback(async (runId: string) => {
    setExecutingBatchRunId(runId);
    setBatchExecutionError((prev) => {
      const next = { ...prev };
      delete next[runId];
      return next;
    });
    try {
      // Explicitly send dryRun: false for actual execution
      // The backend defaults to False, but being explicit improves clarity and debugging
      await runBatchExecution({ runId, dryRun: false });
      // Refresh runs list via RunControl's poll() - single authoritative path
      poll();
      // If the executed run is currently selected, refresh its data through RunControl
      // This ensures the execution history / next-check state is up to date
      if (selectedRunId === runId) {
        retrySelectedRun();
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Batch execution failed";
      setBatchExecutionError((prev) => ({
        ...prev,
        [runId]: message,
      }));
    } finally {
      setExecutingBatchRunId((current) => (current === runId ? null : current));
    }
  }, [selectedRunId, poll, retrySelectedRun]);

  // Derive selectedClusterLabel from hook (with local clusterDetailExpanded handling)
  const selectedClusterLabel = hookSelectedClusterLabel;

  // Handle cluster selection - combines hook logic with local clusterDetailExpanded state
  const handleClusterSelection = (label: string, options?: { expand?: boolean }) => {
    hookHandleClusterSelection(label, options);
    if (options?.expand) {
      setClusterDetailExpanded(true);
    }
  };

  const {
    scrollToSection,
    highlightCluster,
    highlightExecutionEntry,
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

  // App-level refresh wrapper - calls hook refresh and handles App-specific side effects
  const refresh = useCallback(async () => {
    await refreshAppData();
    // Clear local execution results after successful refresh reconciliation.
    // This allows the UI to transition from transient local execution state
    // to refreshed artifact-backed payload as the durable source of truth.
    setExecutionResults({});
    // After successful refresh reconciliation, highlight the last executed candidate
    // if we have a tracked key from a recent manual execution.
    if (lastExecutedCandidateKey.current) {
      const keyToHighlight = lastExecutedCandidateKey.current;
      // Clear the ref so we don't keep highlighting on subsequent auto-refreshes
      lastExecutedCandidateKey.current = null;
      // Trigger the highlight after state updates have settled
      requestAnimationFrame(() => {
        highlightQueueCard(keyToHighlight);
      });
    }
  }, [refreshAppData]);

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

  const buildCandidateKey = (candidate: NextCheckPlanCandidate, index: number) =>
    `next-check-${candidate.candidateId ?? candidate.candidateIndex ?? index}-${
      candidate.targetCluster ?? selectedClusterLabel ?? "global"
    }`;

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

  const isManualExecutionAllowed = (candidate: NextCheckPlanCandidate) => {
    const hasCandidateIdentifier = Boolean(candidate.candidateId?.trim()) || candidate.candidateIndex != null;
    if (!hasCandidateIdentifier) {
      return false;
    }
    if (!candidate.safeToAutomate) {
      return false;
    }
    if (candidate.requiresOperatorApproval && candidate.approvalStatus !== "approved") {
      return false;
    }
    if (candidate.duplicateOfExistingEvidence) {
      return false;
    }
    if (!candidate.suggestedCommandFamily) {
      return false;
    }
    if (!ALLOWED_MANUAL_FAMILIES.has(candidate.suggestedCommandFamily)) {
      return false;
    }
    const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
    if (!targetLabel) {
      return false;
    }
    // CRITICAL: Do not allow re-execution of already executed items
    // Use canonical execution state derivation to prevent contradictions
    if (isItemExecuted(candidate)) {
      return false;
    }
    return true;
  };

  const getNotRunnableExplanation = (candidate: NextCheckPlanCandidate): string | null => {
    // Check in the same order as isManualExecutionAllowed to ensure consistency
    // 1. Candidate identifier
    const hasCandidateIdentifier = Boolean(candidate.candidateId?.trim()) || candidate.candidateIndex != null;
    if (!hasCandidateIdentifier) {
      return "Not runnable: missing candidate identifier";
    }

    // 2. Safe to automate
    if (!candidate.safeToAutomate) {
      const reason = candidate.safetyReason || "not marked safe to automate";
      return `Not runnable: ${humanizeReason(reason) || reason}`;
    }

    // 3. Approval required
    if (candidate.requiresOperatorApproval && candidate.approvalStatus !== "approved") {
      const reason = candidate.approvalReason || "approval required";
      return `Not runnable: ${humanizeReason(reason) || reason}`;
    }

    // 4. Duplicate
    if (candidate.duplicateOfExistingEvidence) {
      const reason = candidate.duplicateReason || "duplicate of existing evidence";
      return `Not runnable: ${humanizeReason(reason) || reason}`;
    }

    // 5. Command family exists
    if (!candidate.suggestedCommandFamily) {
      return "Not runnable: no command family specified";
    }

    // 6. Command family allowed
    if (!ALLOWED_MANUAL_FAMILIES.has(candidate.suggestedCommandFamily)) {
      return `Not runnable: unsupported command family '${candidate.suggestedCommandFamily}'`;
    }

    // 7. Target cluster resolved
    const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
    if (!targetLabel) {
      return "Not runnable: target cluster unresolved";
    }

    // Fallback - should not reach here if logic is correct
    return "Not eligible for manual execution";
  };

  const handleManualExecution = async (candidate: NextCheckPlanCandidate, candidateKey: string) => {
    const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
    const candidateId = candidate.candidateId?.trim() ? candidate.candidateId : undefined;
    const candidateIndex = candidate.candidateIndex;
    const planArtifactPath = candidate.planArtifactPath?.trim() ? candidate.planArtifactPath : undefined;
    if (!targetLabel || (candidateIndex == null && !candidateId)) {
      setExecutionResults((prev) => ({
        ...prev,
        [candidateKey]: { status: "error", summary: "Unable to determine candidate target." },
      }));
      return;
    }
    setExecutingCandidate(candidateKey);
    // Track the candidate key so we can highlight it after refresh reconciliation
    lastExecutedCandidateKey.current = candidateKey;
    try {
      const result = await executeNextCheckCandidate({
        candidateId,
        candidateIndex: candidateIndex ?? undefined,
        clusterLabel: targetLabel,
        planArtifactPath: planArtifactPath ?? null,
      });
      setExecutionResults((prev) => ({
        ...prev,
        [candidateKey]: result,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Manual execution failed";
      const blockingReason =
        err instanceof Error && "blockingReason" in err
          ? (err as ExecutionErrorResult).blockingReason
          : undefined;
      setExecutionResults((prev) => ({
        ...prev,
        [candidateKey]: {
          status: "error",
          summary: message,
          blockingReason: blockingReason ?? null,
        },
      }));
    } finally {
      setExecutingCandidate((current) => (current === candidateKey ? null : current));
    }
  };

  const handleApproveCandidate = async (
    candidate: NextCheckPlanCandidate,
    candidateKey: string
  ) => {
    const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
    const candidateId = candidate.candidateId?.trim() ? candidate.candidateId : undefined;
    const candidateIndex = candidate.candidateIndex;
    if (!targetLabel || (candidateIndex == null && !candidateId)) {
      setApprovalResults((prev) => ({
        ...prev,
        [candidateKey]: {
          status: "error",
          summary: "Unable to determine candidate target",
        },
      }));
      return;
    }
    setApprovingCandidate(candidateKey);
    try {
      const result = await approveNextCheckCandidate({
        candidateId,
        candidateIndex: candidateIndex ?? undefined,
        clusterLabel: targetLabel,
      });
      setApprovalResults((prev) => ({
        ...prev,
        [candidateKey]: {
          status: result.status === "success" ? "success" : "error",
          summary:
            result.summary ||
            (result.status === "success" ? "Candidate approved" : "Approval failed"),
          artifactPath: result.artifactPath,
          approvalTimestamp: result.approvalTimestamp,
        },
      }));
      await refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Approval failed";
      setApprovalResults((prev) => ({
        ...prev,
        [candidateKey]: { status: "error", summary: message },
      }));
    } finally {
      setApprovingCandidate((current) => (current === candidateKey ? null : current));
    }
  };

  // Derive header display metadata - MUST be before early return for hook consistency
  // These computations only use data that's available before the loading guard
  const selectedRunListEntry = runsList.find((r) => r.runId === selectedRunId) ?? null;
  const headerRunTimestamp = selectedRunListEntry?.timestamp ?? run?.timestamp ?? "";
  const runFresh = !isStaleTimestamp(headerRunTimestamp);
  const runAgeMinutes = headerRunTimestamp
    ? Math.floor(dayjs().diff(headerRunTimestamp, "minute"))
    : 0;

  // Build finding selection input from real/current run data
  // Maps run, incident report, and worklist to demo finding selection format
  // ACT 9.5: Real-derived input for DemoShell
  // NOTE: Moved BEFORE early return to fix hook-order consistency
  const findingSelectionInput = buildDemoShellFindingInput({
    run,
    selectedRunId,
    selectedClusterLabel,
    runAgeMinutes,
    runFresh,
  });

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

  // Use header model values from extracted hook
  const { headerRunId, headerRunLabel, runRecency, latestRunTimestamp, latestRunRecency, headerStats } = headerModel;

  // headerRunTimestamp already computed above (before early return) for findingSelectionInput
  // Reuse it here for the freshness indicator; hook returns latestRunTimestamp but not headerRunTimestamp

  // Derive ClusterDetailSection-specific display props from extracted builder
  const {
    selectedCluster,
    clusterTriggerReason,
    drilldownSummary,
    recencyTimestamp,
    clusterFresh,
    clusterRecency,
  } = buildClusterDetailSectionProps({
    selectedClusterLabel,
    clusterDetail,
    fleet,
  });

  const nextCheckPlanSectionProps = buildClusterPlanSectionProps({
    clusterDetail,
    run,
    selectedClusterLabel,
    executionResults,
    approvalResults,
    executingCandidate,
    approvingCandidate,
    handleApproveCandidate,
    handleManualExecution,
    onRefresh: refresh,
    buildCandidateKey,
    isManualExecutionAllowed,
  });

  const autoRefreshSelectValue = autoRefreshInterval ? String(autoRefreshInterval) : "off";
  const autoRefreshStatusText = autoRefreshInterval
    ? `Auto refresh every ${autoRefreshInterval}s`
    : "Auto refresh is off";
  const interpretation: AutoInterpretation | null = clusterDetail?.autoInterpretation || null;
  const recommendedArtifacts = buildClusterRecommendedArtifacts(clusterDetail);
  const planCandidates: NextCheckPlanCandidate[] = clusterDetail?.nextCheckPlan ?? [];
  const runPlan = run?.nextCheckPlan;
  const orphanedApprovals = runPlan?.orphanedApprovals ?? [];
  const planArtifactLink = runPlan?.artifactPath ? artifactUrl(runPlan.artifactPath) : null;
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
  const outcomeSummary = runPlan?.outcomeCounts ?? [];

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
    deterministicClusters,
    hasDeterministicNextChecks,
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

  const queuePanelProps = buildQueuePanelProps({
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

  return (
    <div className="app-shell">
      <AppHeader
        headerRunId={headerRunId}
        headerRunLabel={headerRunLabel}
        headerRunTimestamp={headerRunTimestamp}
        isSelectedRunLatest={isSelectedRunLatest}
        latestRunRecency={latestRunRecency}
        runRecency={runRecency}
        lastRefresh={lastRefresh}
        onRefresh={refresh}
        autoRefreshInterval={autoRefreshInterval}
        onAutoRefreshChange={handleAutoRefreshChange}
        onClickLatest={clickLatest}
        onOpenDemo={demoShell.openDemo}
      />
      <AppNavigation run={run} />
      {error && <div className="alert">{error}</div>}
      <RecentRunsPanel
        runsList={runsList}
        selectedRunId={selectedRunId}
        runsFilter={runsFilter}
        runsFilterCounts={runsFilterCounts}
        paginatedRunsList={paginatedRunsList}
        filteredRunsList={filteredRunsList}
        runsListLoading={runsListLoading}
        runsListError={runsListError}
        runsListRefreshing={runsListLoading && runsList.length > 0}
        runsPage={runsPage}
        totalRunsPages={totalRunsPages}
        runsPageSize={runsPageSize}
        isRunsListFollowingSelection={isRunsListFollowingSelection}
        isSelectedRunVisibleOnCurrentRunsPage={isSelectedRunVisibleOnCurrentRunsPage}
        executingBatchRunId={executingBatchRunId}
        batchExecutionError={batchExecutionError}
        onRunsFilterChange={handleRunsFilterChange}
        onRunsPageChange={handleRunsPageChange}
        onRunsPageSizeChange={handleRunsPageSizeChange}
        onRunSelection={handleRunSelectionViaRunControl}
        onBatchExecution={handleBatchExecution}
        onShowSelectedRun={handleShowSelectedRun}
        onFocusClusterForNextChecks={runSummaryLoadedProps.onFocusClusterForNextChecks}
      />
      <AppRunSummarySection
        run={run}
        runOwnedPanelState={runOwnedPanelState}
        loadedProps={runSummaryLoadedProps}
        unavailableProps={runSummaryUnavailableProps}
      />
      <WorkflowLaneHeader type="diagnose" />
      <AppDiagnosePanels
        run={run}
        selectedClusterLabel={selectedClusterLabel}
        onRefresh={refresh}
        onNavigateToQueue={() => scrollToSection("next-check-queue")}
        onFocusQueueReview={() => setQueueFocusMode("review")}
        onPromoteCheck={handlePromoteDeterministicCheck}
        onToggleIncidentExpansion={toggleIncidentExpansion}
        onFocusClusterForNextChecks={runSummaryLoadedProps.onFocusClusterForNextChecks}
        onSetQueueStatusFilter={setQueueStatusFilter}
        onSetQueueClusterFilter={setQueueClusterFilter}
        onScrollToSection={scrollToSection}
        artifactUrl={artifactUrl}
        hasDegradedClusters={hasDegradedClusters}
        hookPromotionStatus={hookPromotionStatus}
        incidentExpandedClusters={incidentExpandedClusters}
        deterministicChecks={deterministicChecks}
        deterministicSummary={deterministicSummary}
      />
      <VmAlertPanels
        vmalertSources={run?.vmalertSources}
        vmalertRuleState={run?.vmalertRuleState}
      />
      <WorkNextChecksLane
        run={run}
        history={executionHistory}
        queueCandidateCount={runQueue.length}
        executionHistoryHighlightKey={executionHistoryHighlightKey}
        onSubmitFeedback={handleUsefulnessFeedback}
        onSubmitAlertmanagerRelevanceFeedback={handleAlertmanagerRelevanceFeedback}
        executionHistoryFilter={executionHistoryFilter}
        onExecutionHistoryFilterChange={setExecutionHistoryFilter}
        runQueue={runQueue}
        onHighlightQueueCard={highlightQueueCard}
        queuePanelProps={queuePanelProps}
      />
      <AppFleetSection
        fleet={fleet}
        selectedClusterLabel={selectedClusterLabel}
        highlightedClusterLabel={highlightedClusterLabel}
        onClusterSelect={handleClusterSelection}
      />
      <ClusterDetailSection
        clusterDetail={clusterDetail}
        selectedClusterLabel={selectedClusterLabel}
        selectedCluster={selectedCluster}
        fleet={fleet}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        clusterDetailExpanded={clusterDetailExpanded}
        setClusterDetailExpanded={setClusterDetailExpanded}
        highlightedClusterLabel={highlightedClusterLabel}
        clusterTriggerReason={clusterTriggerReason}
        drilldownSummary={drilldownSummary}
        recencyTimestamp={recencyTimestamp}
        clusterFresh={clusterFresh}
        clusterRecency={clusterRecency}
        handleClusterSelection={handleClusterSelection}
        artifactUrl={artifactUrl}
        formatTimestamp={formatTimestamp}
        statusClass={statusClass}
        nextCheckPlanSectionProps={nextCheckPlanSectionProps}
      />
    <WorkflowLaneHeader type="improve" />
      <AppProposalsSection
        proposals={proposals.proposals}
        statusFilter={statusFilter}
        sortKey={sortKey}
        searchText={searchText}
        statusOptions={statusOptions}
        expandedProposals={expandedProposals}
        onStatusFilterChange={(event) => setStatusFilter(event.target.value)}
        onSortKeyChange={(event) => setSortKey(event.target.value as SortKey)}
        onSearchTextChange={(event) => setSearchText(event.target.value)}
        onToggleProposal={handleToggleProposal}
      />
      <AppImprovePanels run={run} />
      <AppDemoShellOverlay
        isOpen={demoShell.state.isOpen}
        onClose={demoShell.closeDemo}
        findingSelectionInput={findingSelectionInput}
        realContext={
          selectedRunId
            ? {
                runId: selectedRunId,
                clusterLabel: selectedClusterLabel ?? undefined,
                isFresh: runFresh,
                runCapturedAt: headerRunTimestamp || undefined,
              }
            : undefined
        }
      />
    </div>
  );
};

export default App;
