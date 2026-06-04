/**
 * useAppRunSummaryProps - Hook for deriving RunSummaryPanel props in App.tsx
 *
 * Extracts the construction of runSummaryLoadedProps and runSummaryUnavailableProps
 * from App.tsx to reduce component size and move toward LLM-friendly limits.
 *
 * Uses ComponentProps<typeof RunSummaryPanel> to preserve prop typing.
 * Does not alter RunSummaryPanel behavior or loading/slow/failed semantics.
 */

import type { ComponentProps, ReactNode } from "react";
import type { RunPayload } from "../types";
import type { LlmTelemetryPreviewData } from "../components/run-summary/RunOverviewDashboard";
import type { NextCheckPlanCandidate, NextCheckStatusVariant } from "../types";
import { renderLlmStatsLine } from "../components/run-summary/renderLlmStatsLine";
import { relativeRecency } from "../utils";
import { buildRunSummaryProps, type RunSummaryStatsItem } from "../components/run-summary/buildRunSummaryProps";

// Re-export the stats item type for consumers
export type { RunSummaryStatsItem };

// Props required by the hook - extracted from App.tsx's hook calls and derived values
export interface UseAppRunSummaryPropsArgs {
  // Core run data from RunControl
  run: RunPayload | null;
  // RunControl-derived state for progressive loading
  isSelectedRunLatest: boolean;
  selectedRunId: string | null;
  runOwnedPanelState: "no-selection" | "loading" | "slow" | "failed" | "loaded" | undefined;
  selectedRunError: string | null | undefined;
  onRetrySelectedRun: (() => void) | undefined;
  // Cluster context
  selectedClusterLabel: string | null;
  onFocusClusterForNextChecks: (clusterLabel?: string | null) => void;
  // Fleet data for fallback stats
  fleet: import("../types").FleetPayload;
  // Header stats from useRunHeaderModel
  headerStats: Array<{ label: string; value: string }>;
  // Plan-related derived values from App.tsx
  runPlan: RunPayload["nextCheckPlan"];
  runPlanCandidates: NextCheckPlanCandidate[];
  planSummaryText: string;
  planStatusText: string | null;
  plannerReasonText: string;
  plannerHint: string | null;
  plannerNextActionHint: string | null;
  plannerArtifactUrl: string | null;
  planCandidateCountLabel: string;
  discoveryVariantOrder: NextCheckStatusVariant[];
  discoveryVariantCounts: Record<NextCheckStatusVariant, number>;
  discoveryClusters: string[];
}

// Return type using ComponentProps pattern
export interface UseAppRunSummaryPropsResult {
  runSummaryLoadedProps: RunSummaryPanelProps;
  runSummaryUnavailableProps: RunSummaryPanelProps;
  hasDegradedClusters: boolean;
}

// Type alias for clarity
type RunSummaryPanelProps = ComponentProps<typeof import("../components/RunsPanel").RunSummaryPanel>;

/**
 * Derives RunSummaryPanel props from App.tsx state and hooks.
 *
 * Constructs two prop objects:
 * - runSummaryLoadedProps: full props when run data is available
 * - runSummaryUnavailableProps: fallback props for slow/failed states
 *
 * Does NOT alter RunSummaryPanel behavior - preserves loading/slow/failed semantics.
 */
export function useAppRunSummaryProps({
  run,
  isSelectedRunLatest,
  selectedRunId,
  runOwnedPanelState,
  selectedRunError,
  onRetrySelectedRun,
  selectedClusterLabel,
  onFocusClusterForNextChecks,
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
}: UseAppRunSummaryPropsArgs): UseAppRunSummaryPropsResult {
  // Derive RunSummaryPanel-specific stats from extracted builder
  const { runStatsSummary, runSummaryStats, hasDegradedClusters } = buildRunSummaryProps({
    run,
    fleet,
    headerStats,
  });

  // LLM stats lines - derived from run data
  const runLlmStatsLine = run ? renderLlmStatsLine(run.llmStats) : null;
  const historicalLlmStatsLine = run?.historicalLlmStats
    ? renderLlmStatsLine(run.historicalLlmStats, "llm-stats-line-historical")
    : null;

  // Provider breakdown string
  const providerBreakdown = run?.llmStats.providerBreakdown
    .map((entry) => `${entry.provider} ${entry.calls} (${entry.failedCalls} failed)`)
    .join(" · ") ?? null;

  // Structured telemetry data for LlmTelemetryPreviewCard
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

  // Build props for RunSummaryPanel using ComponentProps pattern
  const runSummaryLoadedProps: RunSummaryPanelProps = {
    run,
    isSelectedRunLatest,
    selectedClusterLabel,
    onFocusClusterForNextChecks,
    runSummaryStats,
    runStatsSummary,
    runLlmStatsLine: runLlmStatsLine as ReactNode,
    historicalLlmStatsLine: historicalLlmStatsLine as ReactNode | null,
    providerBreakdown,
    telemetryData: telemetryData as LlmTelemetryPreviewData,
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
    runOwnedPanelState,
    selectedRunError,
    onRetrySelectedRun,
    selectedRunId,
  };

  const runSummaryUnavailableProps: RunSummaryPanelProps = {
    ...runSummaryLoadedProps,
    run: null,
    runPlan: null,
    runPlanCandidates: [],
    planSummaryText: "",
    planStatusText: null,
    plannerReasonText: "",
    plannerHint: null,
    plannerNextActionHint: null,
    plannerArtifactUrl: null,
    planCandidateCountLabel: "",
    discoveryClusters: [],
  };

  return {
    runSummaryLoadedProps,
    runSummaryUnavailableProps,
    hasDegradedClusters,
  };
}
