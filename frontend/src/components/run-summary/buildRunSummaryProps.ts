/**
 * buildRunSummaryProps - Pure props derivation for RunSummaryPanel from App.tsx
 *
 * This module computes the pure values used by <RunSummaryPanel> that are not
 * derived elsewhere or consumed by other components.
 *
 * Uses a pure function (not a hook) to avoid React hooks rule violations in tests.
 */

import type { FleetPayload, RunPayload } from "../../types";

export interface RunSummaryStatsItem {
  label: string;
  value: string | number;
}

export interface RunSummaryPropsModel {
  runStatsSummary: string;
  runSummaryStats: RunSummaryStatsItem[];
  degradedCount: number;
  hasDegradedClusters: boolean;
}

export interface BuildRunSummaryPropsArgs {
  run: RunPayload | null;
  fleet: FleetPayload;
  headerStats: Array<{ label: string; value: string }>;
}

/**
 * Derives RunSummaryPanel-specific props from the selected run and fleet data.
 *
 * Extracts only the pure display derivations needed by RunSummaryPanel:
 * - runStatsSummary: formatted string combining header stats for display
 * - runSummaryStats: array of labeled metric items for the stats strip
 * - degradedCount: count of degraded clusters in the fleet
 * - hasDegradedClusters: boolean indicating presence of degraded clusters
 *
 * Values intentionally NOT extracted (consumed by multiple components):
 * - plan-related props (used by ClusterDetailSection and RunSummaryPanel)
 * - LLM stats line rendering (uses renderLlmStatsLine which may have broader use)
 * - provider breakdown (derived from run.llmStats, may be used elsewhere)
 * - telemetry data (derived from run.llmStats)
 *
 * @param args - The run payload, fleet data, and header stats
 * @returns The derived RunSummaryPanel props model
 */
export function buildRunSummaryProps({
  run,
  fleet,
  headerStats,
}: BuildRunSummaryPropsArgs): RunSummaryPropsModel {
  // Degraded cluster count from fleet rating counts
  const degradedCount =
    fleet.fleetStatus.ratingCounts.find((entry) => entry.rating.toLowerCase() === "degraded")
      ?.count ?? 0;
  const hasDegradedClusters = degradedCount > 0;

  // Run stats summary: formatted string from header stats
  const runStatsSummary = headerStats.map((stat) => `${stat.label} ${stat.value}`).join(" · ");

  // Run summary stats: labeled metric items
  // Use fleet cluster count instead of run.clusterCount when run is null
  const runSummaryStats: RunSummaryStatsItem[] = run
    ? [
        { label: "Clusters", value: run.clusterCount },
        { label: "Degraded", value: degradedCount },
        { label: "Proposals", value: run.proposalCount },
        { label: "Notifications", value: run.notificationCount },
        { label: "Drilldowns", value: run.drilldownCount },
      ]
    : [
        { label: "Clusters", value: fleet.clusters.length },
        { label: "Degraded", value: degradedCount },
        { label: "Proposals", value: "—" },
        { label: "Notifications", value: "—" },
        { label: "Drilldowns", value: "—" },
      ];

  return {
    runStatsSummary,
    runSummaryStats,
    degradedCount,
    hasDegradedClusters,
  };
}
