/**
 * useAppData hook - manages fleet, proposals, notifications, and cluster-detail fetch + state.
 *
 * Owns:
 *   - Fleet, proposals, cluster detail data fetching and state
 *   - Selected cluster label for detail view
 *   - Expanded proposals state
 *   - Refresh orchestration for app-level data
 *
 * Inputs:
 *   - selectedRunId: string | null - the selected run ID (triggers main refresh)
 *   - lastRefresh: Dayjs - timestamp of last run data refresh (triggers cluster detail refetch)
 *   - refreshRuns: () => Promise<void> - from useRunSelection hook
 *   - refreshRunData: () => Promise<void> - from useRunData hook
 *
 * Returns:
 *   - fleet: FleetPayload | null
 *   - proposals: ProposalsPayload | null
 *   - expandedProposals: Set<string>
 *   - handleToggleProposal: (id: string) => void
 *   - notifications: NotificationsPayload | null
 *   - clusterDetail: ClusterDetailPayload | null
 *   - isClusterDetailLoading: boolean
 *   - selectedClusterLabel: string | null
 *   - handleClusterSelection: (label: string, options?: { expand?: boolean }) => void
 *   - statusOptions: string[]
 *   - refreshAppData: () => Promise<void>
 *   - handlePromoteDeterministicCheck: callback
 *   - handleUsefulnessFeedback: callback
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  ClusterDetailPayload,
  DeterministicNextCheckPromotionRequest,
  DeterministicNextCheckSummary,
  FleetPayload,
  NotificationsPayload,
  ProposalsPayload,
  UsefulnessFeedbackRequest,
} from "../types";
import {
  fetchClusterDetail,
  fetchFleet,
  fetchNotifications,
  fetchProposals,
  promoteDeterministicNextCheck,
  submitUsefulnessFeedback,
} from "../api";

export interface UseAppDataParams {
  selectedRunId: string | null;
  lastRefresh: import("dayjs").Dayjs;
  refreshRuns: () => Promise<void>;
  refreshRunData: () => Promise<void>;
}

type PromotionStatus = {
  status: "idle" | "pending" | "success" | "error";
  message?: string | null;
};

export interface UseAppDataReturn {
  // fleet
  fleet: FleetPayload | null;
  // proposals
  proposals: ProposalsPayload | null;
  expandedProposals: Set<string>;
  handleToggleProposal: (id: string) => void;
  statusOptions: string[];
  // notifications
  notifications: NotificationsPayload | null;
  // cluster detail
  clusterDetail: ClusterDetailPayload | null;
  isClusterDetailLoading: boolean;
  selectedClusterLabel: string | null;
  handleClusterSelection: (label: string, options?: { expand?: boolean }) => void;
  // error state
  error: string | null;
  // promotion state
  promotionStatus: Record<string, PromotionStatus>;
  setPromotionStatus: (key: string, status: PromotionStatus) => void;
  // refresh trigger
  refreshAppData: () => Promise<void>;
  // callbacks that depend on refresh
  handlePromoteDeterministicCheck: (
    clusterLabel: string,
    clusterContext: string | null,
    topProblem: string | null,
    check: DeterministicNextCheckSummary,
    index: number
  ) => Promise<void>;
  handleUsefulnessFeedback: (
    artifactPath: string,
    usefulnessClass: string,
    summary: string | undefined
  ) => Promise<void>;
}

export const useAppData = ({
  selectedRunId,
  lastRefresh,
  refreshRuns,
  refreshRunData,
}: UseAppDataParams): UseAppDataReturn => {
  // State
  const [fleet, setFleet] = useState<FleetPayload | null>(null);
  const [proposals, setProposals] = useState<ProposalsPayload | null>(null);
  const [clusterDetail, setClusterDetail] = useState<ClusterDetailPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedClusterLabel, setSelectedClusterLabel] = useState<string | null>(null);
  const [expandedProposals, setExpandedProposals] = useState<Set<string>>(new Set());
  const [isClusterDetailLoading, setIsClusterDetailLoading] = useState(false);
  const [notifications, setNotifications] = useState<NotificationsPayload | null>(null);
  const [promotionStatus, setPromotionStatusState] = useState<Record<string, PromotionStatus>>({});

  // Ref to track if a refresh is in progress to prevent duplicate fetches
  const refreshInProgress = useRef(false);

  // Derive status options from proposals
  const statusOptions = useMemo(() => {
    const entries = proposals?.statusSummary.map((entry) => entry.status) ?? [];
    return ["all", ...Array.from(new Set(entries))];
  }, [proposals]);

  // Main refresh function - fetches fleet, proposals, and notifications
  const refreshAppData = useCallback(async () => {
    if (refreshInProgress.current) {
      return;
    }
    refreshInProgress.current = true;
    let active = true;
    try {
      setError(null);
      // Fetch fleet, proposals, and notifications in parallel
      const [fleetPayload, proposalsPayload, notificationsPayload] = await Promise.all([
        fetchFleet(),
        fetchProposals(),
        fetchNotifications(),
      ]);
      // Trigger hook-based refresh for runs list and run data
      refreshRuns();
      refreshRunData();
      if (active) {
        setFleet(fleetPayload);
        setNotifications(notificationsPayload);
        if (!selectedClusterLabel) {
          const fallbackLabel = fleetPayload.clusters[0]?.label ?? null;
          if (fallbackLabel) {
            setSelectedClusterLabel(fallbackLabel);
          }
        }
      }
      if (active) {
        setProposals(proposalsPayload);
      }
    } catch (err) {
      if (active) {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      refreshInProgress.current = false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedClusterLabel, refreshRuns, refreshRunData]);

  // Build promotion key helper
  const buildPromotionKey = (clusterLabel: string, description: string, index: number) =>
    `${clusterLabel}::${description}::${index}`;

  // Handle promote deterministic check
  const handlePromoteDeterministicCheck = useCallback(
    async (
      clusterLabel: string,
      clusterContext: string | null,
      topProblem: string | null,
      check: DeterministicNextCheckSummary,
      index: number
    ) => {
      const key = buildPromotionKey(clusterLabel, check.description, index);
      const request: DeterministicNextCheckPromotionRequest = {
        clusterLabel,
        context: clusterContext,
        description: check.description,
        method: check.method || null,
        evidenceNeeded: check.evidenceNeeded,
        workstream: check.workstream,
        urgency: check.urgency,
        whyNow: check.whyNow,
        topProblem,
        priorityScore: check.priorityScore ?? null,
      };
      // Set pending status
      setPromotionStatusState((prev) => ({
        ...prev,
        [key]: { status: "pending" },
      }));
      try {
        const result = await promoteDeterministicNextCheck(request);
        // Set success status with message from API response
        setPromotionStatusState((prev) => ({
          ...prev,
          [key]: {
            status: "success",
            message: result.summary ?? "Deterministic next check promoted to the queue",
          },
        }));
        // Refresh to get updated data
        await refreshAppData();
      } catch (err) {
        // Set error status
        setPromotionStatusState((prev) => ({
          ...prev,
          [key]: {
            status: "error",
            message: err instanceof Error ? err.message : "Promotion failed",
          },
        }));
        throw err;
      }
    },
    [refreshAppData]
  );

  // Handle usefulness feedback
  const handleUsefulnessFeedback = useCallback(
    async (
      artifactPath: string,
      usefulnessClass: string,
      summary: string | undefined
    ) => {
      await submitUsefulnessFeedback({
        artifactPath,
        usefulnessClass: usefulnessClass as "useful" | "partial" | "noisy" | "empty",
        usefulnessSummary: summary,
      });
      // Refresh to get updated data
      await refreshAppData();
    },
    [refreshAppData]
  );

  // Handle toggle proposal expansion
  const handleToggleProposal = (id: string) => {
    setExpandedProposals((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  // Handle cluster selection
  const handleClusterSelection = (label: string, options?: { expand?: boolean }) => {
    if (!label) {
      return;
    }
    if (label === selectedClusterLabel) {
      // Already selected, just expand if requested
      // Note: clusterDetailExpanded state remains in App.tsx as it's UI state
      return;
    }
    setSelectedClusterLabel(label);
  };

  // Main refresh effect - triggered when selectedRunId changes
  useEffect(() => {
    refreshAppData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRunId]);

  // Initial fetch on mount
  useEffect(() => {
    refreshAppData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Visibility change effect - refresh when tab becomes visible
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        refreshAppData();
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [refreshAppData]);

  // Cluster detail fetch effect - triggered when selectedClusterLabel or lastRefresh changes
  useEffect(() => {
    if (!selectedClusterLabel) {
      setClusterDetail(null);
      return;
    }
    let active = true;
    setIsClusterDetailLoading(true);
    const loadDetail = async () => {
      try {
        const detailPayload = await fetchClusterDetail(selectedClusterLabel);
        if (active) {
          setClusterDetail(detailPayload);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (active) {
          setIsClusterDetailLoading(false);
        }
      }
    };
    loadDetail();
    return () => {
      active = false;
    };
  }, [selectedClusterLabel, lastRefresh]);

  // Setter for promotion status
  const setPromotionStatus = (key: string, status: PromotionStatus) => {
    setPromotionStatusState((prev) => ({
      ...prev,
      [key]: status,
    }));
  };

  return {
    // fleet
    fleet,
    // proposals
    proposals,
    expandedProposals,
    handleToggleProposal,
    statusOptions,
    // notifications
    notifications,
    // cluster detail
    clusterDetail,
    isClusterDetailLoading,
    selectedClusterLabel,
    handleClusterSelection,
    // error state
    error,
    // promotion state
    promotionStatus,
    setPromotionStatus,
    // refresh
    refreshAppData,
    // callbacks
    handlePromoteDeterministicCheck,
    handleUsefulnessFeedback,
  };
};
