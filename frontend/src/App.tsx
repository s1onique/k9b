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
import { ThemeSwitch } from "./ThemeSwitch";
import { HeaderBranding } from "./components/HeaderBranding";
import { RunDiagnosticPackPanel } from "./components/RunDiagnosticPackPanel";
import { LLMActivityPanel } from "./components/LLMActivityPanel";
import { LLMPolicyPanel } from "./components/LLMPolicyPanel";
import {
  AdvisoryTopConcernsSection,
  AdvisoryEvidenceGapsSection,
  AdvisoryNextChecksSection,
  AdvisoryFocusNotesSection,
} from "./components/AdvisorySections";
import { ProposalList } from "./components/ProposalList";
import { ReviewEnrichmentPanel } from "./components/ReviewEnrichmentPanel";
import { DiagnosticPackReviewPanel } from "./components/DiagnosticPackReviewPanel";
import { ProviderExecutionPanel } from "./components/ProviderExecutionComponents";
import { buildExecutionEntryKey, formatDuration } from "./components/ExecutionHistoryPanel";
import { NotificationHistoryTable } from "./components/NotificationHistoryTable";
import { DeterministicNextChecksPanel } from "./components/DeterministicNextChecksPanel";
import { QueuePanel } from "./components/QueuePanel";
import { buildQueuePanelProps } from "./components/QueuePanel/buildQueuePanelProps";
import { WorkNextChecksLane } from "./components/WorkNextChecksLane";
import { DemoShell } from "./components/DemoShell";
import { useDemoShellModel } from "./demo-shell/useDemoShellModel";
import { AlertmanagerSnapshotPanel, AlertmanagerSourcesPanel } from "./components/AlertmanagerPanel";
import { ClusterDetailSection } from "./components/ClusterDetailSection";
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
  WORKFLOW_LANES,
  AUTOREFRESH_STORAGE_KEY,
  AUTOREFRESH_OPTIONS,
  getLlmScopeLabel,
  buildClusterRecommendedArtifacts,
  sortDeterministicSummaries,
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

import type { LlmTelemetryPreviewData } from "./components/run-summary/RunOverviewDashboard";
import { renderLlmStatsLine } from "./components/run-summary/renderLlmStatsLine";
import { useRunHeaderModel } from "./components/run-summary/useRunHeaderModel";
import { buildRunSummaryProps } from "./components/run-summary/buildRunSummaryProps";

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
  const clusterHighlightTimer = useRef<number | null>(null);
  const executionHighlightTimer = useRef<number | null>(null);
  const queueHighlightTimer = useRef<number | null>(null);
  // Track the last executed candidate key so we can highlight it after refresh
  const lastExecutedCandidateKey = useRef<string | null>(null);

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

  const scrollToSection = (id: string) => {
    if (typeof document === "undefined") {
      return;
    }
    const section = document.getElementById(id);
    if (!section) {
      return;
    }
    section.scrollIntoView?.({ behavior: "smooth", block: "start" });
  };

  const highlightCluster = (label: string | null) => {
    setHighlightedClusterLabel(label);
    if (clusterHighlightTimer.current) {
      window.clearTimeout(clusterHighlightTimer.current);
    }
    if (!label) {
      return;
    }
    clusterHighlightTimer.current = window.setTimeout(() => {
      setHighlightedClusterLabel(null);
    }, NAVIGATION_HIGHLIGHT_DURATION_MS);
  };

  const highlightExecutionEntry = (key: string | null) => {
    setExecutionHistoryHighlightKey(key);
    if (executionHighlightTimer.current) {
      window.clearTimeout(executionHighlightTimer.current);
    }
    if (!key) {
      return;
    }
    executionHighlightTimer.current = window.setTimeout(() => {
      setExecutionHistoryHighlightKey(null);
    }, NAVIGATION_HIGHLIGHT_DURATION_MS);
  };

  const highlightQueueCard = (key: string | null) => {
    setQueueHighlightKey(key);
    if (queueHighlightTimer.current) {
      window.clearTimeout(queueHighlightTimer.current);
    }
    if (!key) {
      return;
    }
    queueHighlightTimer.current = window.setTimeout(() => {
      setQueueHighlightKey(null);
    }, NAVIGATION_HIGHLIGHT_DURATION_MS);
    // Scroll the highlighted queue card into view
    requestAnimationFrame(() => {
      const element = document.querySelector(`[data-queue-key="${CSS.escape(key)}"]`);
      if (element) {
        element.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
  };

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

  const executionHistory: NextCheckExecutionHistoryEntry[] = run?.nextCheckExecutionHistory ?? [];
  const queueExplanation = run?.nextCheckQueueExplanation ?? null;

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
  const findingSelectionInput = useMemo(() => {
    if (!run) {
      return undefined;
    }

    // Extract incident report status from run data
    const incidentReport = run.incidentReport
      ? {
          status: run.incidentReport.status as "critical" | "degraded" | "warning" | "healthy" | undefined,
          resource: run.incidentReport.topFinding?.affectedResource,
          findingType: run.incidentReport.topFinding?.findingType,
        }
      : undefined;

    // Extract operator worklist items
    // NOTE: run.operatorWorklist is OperatorWorklistPayload (object with items array), NOT a direct array.
    // Guard against non-array shapes to prevent TypeError at runtime.
    const worklistPayload = run.operatorWorklist;
    const worklistItems = Array.isArray(worklistPayload)
      ? worklistPayload
      : Array.isArray(worklistPayload?.items)
        ? worklistPayload.items
        : Array.isArray(worklistPayload?.candidates)
          ? worklistPayload.candidates
          : [];

    const operatorWorklist = worklistItems.length > 0
      ? worklistItems.map((item) => ({
          severity: item.severity as "critical" | "warning" | "info" | undefined,
          resource: item.resource,
          status: item.status,
          message: item.message,
        }))
      : undefined;

    // Extract run freshness
    const freshness = {
      age: runAgeMinutes * 60, // Convert to seconds
      isStale: !runFresh,
    };

    return {
      incidentReport,
      operatorWorklist,
      freshness,
      runId: selectedRunId ?? undefined,
      clusterLabel: selectedClusterLabel ?? undefined,
    };
  }, [run, runAgeMinutes, runFresh, selectedRunId, selectedClusterLabel]);

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

  // Derive RunSummaryPanel-specific props from extracted builder
  const { runStatsSummary, runSummaryStats, degradedCount, hasDegradedClusters } = buildRunSummaryProps({
    run,
    fleet,
    headerStats,
  });
  const selectedCluster = fleet.clusters.find((cluster) => cluster.label === selectedClusterLabel) ?? null;
  const clusterRecency = selectedCluster?.latestRunTimestamp
    ? relativeRecency(selectedCluster.latestRunTimestamp)
    : null;
  const clusterFresh = selectedCluster ? !isStaleTimestamp(selectedCluster.latestRunTimestamp) : true;
  const autoRefreshSelectValue = autoRefreshInterval ? String(autoRefreshInterval) : "off";
  const autoRefreshStatusText = autoRefreshInterval
    ? `Auto refresh every ${autoRefreshInterval}s`
    : "Auto refresh is off";
  const interpretation: AutoInterpretation | null = clusterDetail?.autoInterpretation || null;
  const recommendedArtifacts = buildClusterRecommendedArtifacts(clusterDetail);
  const clusterTriggerReason =
    selectedCluster?.topTriggerReason ||
    clusterDetail?.findings?.[0]?.triggerReasons?.[0] ||
    clusterDetail?.topProblem?.title ||
    "Trigger reason pending";

  const drilldownAvailability = clusterDetail?.drilldownAvailability;
  const drilldownSummary = drilldownAvailability
    ? `${drilldownAvailability.available}/${drilldownAvailability.totalClusters} drilldown${
        drilldownAvailability.available === 1 ? "" : "s"
      } ready`
    : "Drilldown data pending";
  const recencyTimestamp = selectedCluster?.latestRunTimestamp
    ? formatTimestamp(selectedCluster.latestRunTimestamp)
    : "Awaiting run";
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

  const deterministicChecks = run?.deterministicNextChecks;
  const deterministicClusters = deterministicChecks?.clusters ?? [];
  const hasDeterministicNextChecks = deterministicClusters.length > 0;
  const deterministicSummary = hasDeterministicNextChecks
    ? `${deterministicChecks?.totalNextCheckCount ?? 0} candidate check${
        (deterministicChecks?.totalNextCheckCount ?? 0) === 1 ? "" : "s"
      } to review and promote to the work list`
    : "Review the cluster detail to generate candidate checks.";

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
    if (typeof document !== "undefined") {
      scrollToSection("cluster");
    }
  };

  const handleBackToQueue = () => {
    scrollToSection("next-check-queue");
  };

  const handleQueueClusterJump = (candidate: NextCheckQueueItem) => {
    focusClusterForNextChecks(candidate.targetCluster ?? undefined);
  };

  const handleQueueExecutionJump = (candidate: NextCheckQueueItem) => {
    const entry = findExecutionHistoryEntry(candidate);
    highlightExecutionEntry(entry ? buildExecutionEntryKey(entry) : null);
    scrollToSection("execution-history");
  };

  const runLlmStatsLine = run ? renderLlmStatsLine(run.llmStats) : null;
  const historicalLlmStatsLine = run?.historicalLlmStats
    ? renderLlmStatsLine(run.historicalLlmStats, "llm-stats-line-historical")
    : null;
  const providerBreakdown = run?.llmStats.providerBreakdown
    .map((entry) => `${entry.provider} ${entry.calls} (${entry.failedCalls} failed)`)
    .join(" · ") ?? null;

  // Create structured telemetry data for LlmTelemetryPreviewCard
  const telemetryData: LlmTelemetryPreviewData | null = run ? {
    totalCalls: run.llmStats.totalCalls,
    successfulCalls: run.llmStats.successfulCalls,
    failedCalls: run.llmStats.failedCalls,
    lastCallRecency: run.llmStats.lastCallTimestamp ? relativeRecency(run.llmStats.lastCallTimestamp) : null,
    p50LatencyMs: run.llmStats.p50LatencyMs,
    p95LatencyMs: run.llmStats.p95LatencyMs,
    p99LatencyMs: run.llmStats.p99LatencyMs,
    providers: run.llmStats.providerBreakdown,
  } : null;

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
      <header className="panel hero compact">
        <div className="hero-content">
          <HeaderBranding />
          <div className="hero-run">
            <div className="hero-run-identity">
              <div className="hero-run-header">
                <p className="eyebrow hero-run-label">Selected run</p>
                <span className={`run-badge run-badge--${isSelectedRunLatest ? "latest" : "past"}`}>
                  {isSelectedRunLatest ? "Latest" : "Past run"}
                </span>
              </div>
              <div className="hero-run-title">
                <strong>Run {headerRunLabel}</strong>
                <span className="hero-run-id">ID {headerRunId}</span>
              </div>
              <p className="hero-run-captured">Captured {runRecency}</p>
            </div>
            <div className="hero-run-freshness">
              {isSelectedRunLatest && (
                <span className={`freshness-indicator freshness-indicator--${getRunFreshnessLevel(headerRunTimestamp)}`}>
                  <span className="freshness-indicator__emoji">{FRESHNESS_EMOJI[getRunFreshnessLevel(headerRunTimestamp)]}</span>
                  <span className="freshness-indicator__label">{FRESHNESS_LABEL[getRunFreshnessLevel(headerRunTimestamp)]}</span>
                </span>
              )}
              {!isSelectedRunLatest && (
                <button
                  type="button"
                  className="link tiny"
                  onClick={clickLatest}
                  title="Jump back to the latest run"
                >
                  ← Latest
                </button>
              )}
            </div>
            {!isSelectedRunLatest && (
              <p className="hero-run-latest-hint">
                Latest run available: {latestRunRecency}
              </p>
            )}
          </div>
        </div>
        <div className="hero-actions">
          <div className="refresh-controls">
            <span
              className={`page-freshness-indicator page-freshness-indicator--${getPageFreshnessLevel(lastRefresh)}`}
              title={`Page data refreshed ${relativeRecency(lastRefresh.toISOString())}`}
              aria-label={`Page data freshness: ${getPageFreshnessLevel(lastRefresh)}`}
            >
              {FRESHNESS_EMOJI[getPageFreshnessLevel(lastRefresh)]}
            </span>
            <button type="button" onClick={refresh}>
              Refresh
            </button>
            <div className="autorefresh-control">
              <label htmlFor="auto-refresh-interval">Auto</label>
              <select
                id="auto-refresh-interval"
                value={autoRefreshSelectValue}
                onChange={(event) => handleAutoRefreshChange(event.target.value)}
              >
                {AUTOREFRESH_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {/* ACT 9.5: K8s Accelerator demo entry point */}
          <button
            type="button"
            className="demo-entry-button"
            onClick={demoShell.openDemo}
            title="Launch the guided K8s Accelerator demo"
            data-testid="start-demo-button"
          >
            Start demo
          </button>
          <ThemeSwitch />
        </div>
      </header>
      <nav className="cockpit-nav" aria-label="Fleet cockpit sections">
        <a className="cockpit-nav__item" href="#recent-runs">Recent runs</a>
        <a className="cockpit-nav__item" href="#run-detail">Run summary</a>
        <a className="cockpit-nav__item" href="#review-enrichment">Provider advisory</a>
        <a className="cockpit-nav__item" href="#provider-execution">Provider branches</a>
        <a className="cockpit-nav__item" href="#diagnostic-pack-download">Diagnostic package</a>
        {run?.diagnosticPackReview && (
          <a className="cockpit-nav__item" href="#diagnostic-pack-review">Diagnostic pack review</a>
        )}
        <a className="cockpit-nav__item" href="#deterministic-next-checks">Deterministic checks</a>
        <a className="cockpit-nav__item" href="#execution-history">Execution review</a>
        <a className="cockpit-nav__item" href="#next-check-queue">Work list</a>
        <a className="cockpit-nav__item" href="#fleet">Fleet overview</a>
        <a className="cockpit-nav__item" href="#cluster">Cluster detail</a>
        <a className="cockpit-nav__item" href="#proposals">Action proposals</a>
        <a className="cockpit-nav__item" href="#notifications">Notifications</a>
        <a className="cockpit-nav__item" href="#llm-policy">LLM policy</a>
        <a className="cockpit-nav__item" href="#llm-activity">LLM activity</a>
      </nav>
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
        onFocusClusterForNextChecks={focusClusterForNextChecks}
      />
      {run ? (
        <RunSummaryPanel
          run={run}
          isSelectedRunLatest={isSelectedRunLatest}
          selectedClusterLabel={selectedClusterLabel}
          onFocusClusterForNextChecks={focusClusterForNextChecks}
          runSummaryStats={runSummaryStats}
          runStatsSummary={runStatsSummary}
          runLlmStatsLine={runLlmStatsLine}
          historicalLlmStatsLine={historicalLlmStatsLine}
          providerBreakdown={providerBreakdown}
          telemetryData={telemetryData}
          runPlan={runPlan}
          runPlanCandidates={runPlanCandidates}
          planSummaryText={planSummaryText}
          planStatusText={planStatusText}
          plannerReasonText={plannerReasonText}
          plannerHint={plannerHint}
          plannerNextActionHint={plannerNextActionHint}
          plannerArtifactUrl={plannerArtifactUrl}
          planCandidateCountLabel={planCandidateCountLabel}
          discoveryVariantOrder={discoveryVariantOrder}
          discoveryVariantCounts={discoveryVariantCounts}
          discoveryClusters={discoveryClusters}
          // Phase 3: Wire RunControl-derived state for progressive loading UI
          runOwnedPanelState={runOwnedPanelState}
          selectedRunError={selectedRunError}
          onRetrySelectedRun={retrySelectedRun}
          selectedRunId={selectedRunId}
        />
      ) : (
        // Phase 3: When no run payload yet, check for slow/failed states from RunControl
        runOwnedPanelState === "slow" || runOwnedPanelState === "failed" ? (
          <RunSummaryPanel
            run={null}
            isSelectedRunLatest={isSelectedRunLatest}
            selectedClusterLabel={selectedClusterLabel}
            onFocusClusterForNextChecks={focusClusterForNextChecks}
            runSummaryStats={runSummaryStats}
            runStatsSummary={runStatsSummary}
            runLlmStatsLine={runLlmStatsLine}
            historicalLlmStatsLine={historicalLlmStatsLine}
            providerBreakdown={providerBreakdown}
            telemetryData={telemetryData}
            runPlan={null}
            runPlanCandidates={[]}
            planSummaryText=""
            planStatusText={null}
            plannerReasonText=""
            plannerHint={null}
            plannerNextActionHint={null}
            plannerArtifactUrl={null}
            planCandidateCountLabel=""
            discoveryVariantOrder={discoveryVariantOrder}
            discoveryVariantCounts={discoveryVariantCounts}
            discoveryClusters={[]}
            // Phase 3: Wire RunControl-derived state for progressive loading UI
            runOwnedPanelState={runOwnedPanelState}
            selectedRunError={selectedRunError}
            onRetrySelectedRun={retrySelectedRun}
            selectedRunId={selectedRunId}
          />
        ) : (
          <section className="panel" id="run-detail">
            <div className="section-head">
              <h2>Run summary</h2>
              <p className="muted">Loading selected run…</p>
            </div>
          </section>
        )
      )}
      {/* Workflow Lane: Diagnose Now */}
      <div className="workflow-lane-header">
        <div className="workflow-lane-label">
          <span className="workflow-lane-icon">🔍</span>
          <span className="workflow-lane-title">{WORKFLOW_LANES.diagnose.label}</span>
        </div>
        <p className="workflow-lane-description muted small">{WORKFLOW_LANES.diagnose.description}</p>
      </div>
      {run ? (
        <ReviewEnrichmentPanel
          reviewEnrichment={run.reviewEnrichment}
          reviewEnrichmentStatus={run.reviewEnrichmentStatus}
          nextCheckPlan={run.nextCheckPlan}
          onNavigateToQueue={() => scrollToSection("next-check-queue")}
          onFocusQueueReview={() => setQueueFocusMode("review")}
        />
      ) : (
        <section className="panel" id="review-enrichment">
          <p className="muted">Provider advisory — Loading selected run…</p>
        </section>
      )}
      {run ? (
        <ProviderExecutionPanel execution={run.providerExecution} />
      ) : (
        <section className="panel" id="provider-execution">
          <p className="muted">Provider branches — Loading selected run…</p>
        </section>
      )}
      {run ? (
        <RunDiagnosticPackPanel diagnosticPack={run.diagnosticPack} />
      ) : (
        <section className="panel" id="diagnostic-pack-download">
          <p className="muted">Diagnostic package — Loading selected run…</p>
        </section>
      )}
      {run?.diagnosticPackReview && (
        <DiagnosticPackReviewPanel review={run.diagnosticPackReview} />
      )}
      {run ? (
        <AlertmanagerSnapshotPanel compact={run.alertmanagerCompact} clusterLabel={selectedClusterLabel} />
      ) : (
        <section className="panel" id="alertmanager-snapshot">
          <p className="muted">Alertmanager snapshot — Loading selected run…</p>
        </section>
      )}
      {run?.alertmanagerSources && (
        <AlertmanagerSourcesPanel
          sources={run.alertmanagerSources}
          runId={run.runId}
          clusterLabel={selectedClusterLabel}
          onRefresh={refresh}
        />
      )}
      {/* VictoriaMetrics vmalert discovery - compact display only, no actions */}
      <VmalertDiscoveryPanel vmalertSources={run?.vmalertSources} />
      {/* VictoriaMetrics vmalert alert state - compact display of alert counts and firing alerts */}
      <VmalertAlertStatePanel vmalertRuleState={run?.vmalertRuleState} />
      {run ? (
        <DeterministicNextChecksPanel
          deterministicChecks={deterministicChecks}
          deterministicSummary={deterministicSummary}
          hookPromotionStatus={hookPromotionStatus}
          incidentExpandedClusters={incidentExpandedClusters}
          onPromoteCheck={handlePromoteDeterministicCheck}
          onToggleIncidentExpansion={toggleIncidentExpansion}
          onFocusClusterForNextChecks={focusClusterForNextChecks}
          onSetQueueStatusFilter={setQueueStatusFilter}
          onSetQueueClusterFilter={setQueueClusterFilter}
          onScrollToSection={scrollToSection}
          artifactUrl={artifactUrl}
          hasDegradedClusters={hasDegradedClusters}
        />
      ) : (
        <section className="panel deterministic-next-checks-panel" id="deterministic-next-checks">
          <div className="section-head">
            <h2>Deterministic checks</h2>
            <p className="muted">Loading selected run…</p>
          </div>
        </section>
      )}
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
      <section className="panel" id="fleet">
        <div className="section-head">
          <div>
            <h2>Fleet overview</h2>
            <p className="muted">Top problem: {fleet.topProblem.detail}</p>
          </div>
          <div className="status-badges">
            {fleet.fleetStatus.ratingCounts.map((entry) => (
              <span key={entry.rating} className={statusClass(entry.rating)}>
                {entry.rating} · {entry.count}
              </span>
            ))}
          </div>
        </div>
        <div className="fleet-metrics">
          <article>
            <p className="eyebrow">Pending proposals</p>
            <strong>{fleet.proposalSummary.pending}</strong>
          </article>
          <article>
            <p className="eyebrow">Total proposals</p>
            <strong>{fleet.proposalSummary.total}</strong>
          </article>
        </div>
        <div className="fleet-table">
          <table>
            <thead>
              <tr>
                <th>Cluster</th>
                <th>Rating</th>
                <th>Latest run</th>
                <th>Trigger</th>
                <th>Drilldown</th>
              </tr>
            </thead>
            <tbody>
              {fleet.clusters.map((cluster) => {
                const isSelected = cluster.label === selectedClusterLabel;
                const isFleetRowHighlighted = cluster.label === highlightedClusterLabel;
                const clusterRowFresh = !isStaleTimestamp(cluster.latestRunTimestamp);
                const clusterRowRecency = relativeRecency(cluster.latestRunTimestamp);
                return (
                  <tr
                    key={cluster.label}
                    className={
                      [
                        isSelected ? "row-selected" : null,
                        isFleetRowHighlighted ? "highlighted-row" : null,
                      ]
                        .filter(Boolean)
                        .join(" ") || undefined
                    }
                    data-highlighted={isFleetRowHighlighted ? "true" : undefined}
                    onClick={() => handleClusterSelection(cluster.label)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        handleClusterSelection(cluster.label);
                      }
                    }}
                    tabIndex={0}
                  >
                    <td>
                      <strong>{cluster.label}</strong>
                      <p className="small compact">{cluster.context}</p>
                      <p className="tiny compact">
                        {cluster.clusterClass}/{cluster.clusterRole} · {cluster.baselineCohort}
                      </p>
                    </td>
                    <td>
                      <span className={statusClass(cluster.healthRating)}>{cluster.healthRating}</span>
                    </td>
                    <td>
                      <span className={`recency-pill ${clusterRowFresh ? "fresh" : "stale"}`}>
                        {clusterRowRecency}
                      </span>
                      <p className="small compact">{formatTimestamp(cluster.latestRunTimestamp)}</p>
                    </td>
                    <td>
                      <p className="small">{cluster.topTriggerReason || "Awaiting trigger"}</p>
                    </td>
                    <td>
                      <span className="small">
                        {cluster.drilldownAvailable ? "Ready" : "Missing"}
                      </span>
                      <p className="small compact">{cluster.drilldownTimestamp || "pending"}</p>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
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
        nextCheckPlanSectionProps={{
          planCandidates,
          orphanedApprovals,
          planArtifactLink,
          planSummaryText,
          planCandidateCountLabel,
          planStatusText,
          outcomeSummary,
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
          artifactUrl,
          relativeRecency,
        }}
      />
    {/* Workflow Lane: Improve the System */}
    <div className="workflow-lane-header">
      <div className="workflow-lane-label">
        <span className="workflow-lane-icon">📈</span>
        <span className="workflow-lane-title">{WORKFLOW_LANES.improve.label}</span>
      </div>
      <p className="workflow-lane-description muted small">{WORKFLOW_LANES.improve.description}</p>
    </div>
      <section className="panel" id="proposals">
        <div className="section-head">
          <h2>Action proposals</h2>
          <span className="muted tiny">
            Findings surfaced for triage; actionable improvements for the system.
          </span>
        </div>
        <div className="proposal-controls">
          <label>
            Status
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              {statusOptions.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </label>
          <label>
            Sort
            <select value={sortKey} onChange={(event) => setSortKey(event.target.value as SortKey)}>
              <option value="proposalId">Proposal ID</option>
              <option value="confidence">Confidence</option>
              <option value="status">Status</option>
            </select>
          </label>
          <label>
            Search
            <input
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              placeholder="Target or rationale"
            />
          </label>
        </div>
        <ProposalList
          proposals={proposals.proposals}
          filter={statusFilter}
          sortKey={sortKey}
          searchText={searchText}
          expanded={expandedProposals}
          toggle={handleToggleProposal}
        />
      </section>
      <section className="panel" id="notifications">
        <div className="section-head">
          <h2>Notification history</h2>
          <p className="small">Filtering applies to the entire retained archive.</p>
        </div>
        <NotificationHistoryTable />
      </section>
      {run ? (
        <LLMPolicyPanel policy={run.llmPolicy} />
      ) : (
        <section className="panel llm-policy-panel" id="llm-policy">
          <div className="section-head">
            <h2>LLM policy</h2>
            <p className="muted">Loading selected run…</p>
          </div>
        </section>
      )}
      {run ? (
        <LLMActivityPanel activity={run.llmActivity} />
      ) : (
        <section className="panel llm-activity-panel" id="llm-activity">
          <div className="section-head">
            <h2>LLM activity</h2>
            <p className="muted">Loading selected run…</p>
          </div>
        </section>
      )}
      {/* ACT 9.5: K8s Accelerator demo shell overlay */}
      {demoShell.state.isOpen && (
        <DemoShell
          onClose={demoShell.closeDemo}
          findingSelectionInput={findingSelectionInput}
        />
      )}
    </div>
  );
};

export default App;
