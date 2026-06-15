/**
 * Build props for ClusterDetailSection - pure display derivation bundle.
 *
 * Extracts only the minimal pure values consumed by ClusterDetailSection.
 * Does not extract handlers, navigation helpers, execution state, or plan/discovery values.
 */

import type {
  ClusterDetailPayload,
  ClusterSummary,
  FleetPayload,
} from "../../types";
import { formatTimestamp, relativeRecency } from "../../utils";
import { isStaleTimestamp } from "../../utils/selectors";

export interface ClusterDetailSectionDisplayProps {
  selectedCluster: ClusterSummary | null;
  clusterTriggerReason: string;
  drilldownSummary: string;
  recencyTimestamp: string;
  clusterFresh: boolean;
  clusterRecency: string | null;
}

export interface BuildClusterDetailSectionPropsArgs {
  selectedClusterLabel: string | null;
  clusterDetail: ClusterDetailPayload | null;
  fleet: FleetPayload;
}

export function buildClusterDetailSectionProps({
  selectedClusterLabel,
  clusterDetail,
  fleet,
}: BuildClusterDetailSectionPropsArgs): ClusterDetailSectionDisplayProps {
  // Null guard: return safe defaults when fleet is not available
  if (!fleet) {
    return {
      selectedCluster: null,
      clusterTriggerReason: "Loading cluster data…",
      drilldownSummary: "Drilldown data pending",
      recencyTimestamp: "Awaiting run",
      clusterFresh: true,
      clusterRecency: null,
    };
  }

  // Derive selectedCluster from fleet
  const selectedCluster = fleet.clusters.find(
    (cluster) => cluster.label === selectedClusterLabel,
  ) ?? null;

  // Derive clusterFresh: true when cluster has recent timestamp, or when no cluster selected
  const clusterFresh = selectedCluster
    ? !isStaleTimestamp(selectedCluster.latestRunTimestamp)
    : true;

  // Derive clusterRecency: relative time string from latest run timestamp
  const clusterRecency = selectedCluster?.latestRunTimestamp
    ? relativeRecency(selectedCluster.latestRunTimestamp)
    : null;

  // Derive clusterTriggerReason: composed from selectedCluster topTriggerReason or clusterDetail findings
  const clusterTriggerReason =
    selectedCluster?.topTriggerReason ||
    clusterDetail?.findings?.[0]?.triggerReasons?.[0] ||
    clusterDetail?.topProblem?.title ||
    "Trigger reason pending";

  // Derive drilldownSummary: human-readable drilldown availability summary
  const drilldownAvailability = clusterDetail?.drilldownAvailability;
  const drilldownSummary = drilldownAvailability
    ? `${drilldownAvailability.available}/${drilldownAvailability.totalClusters} drilldown${
        drilldownAvailability.available === 1 ? "" : "s"
      } ready`
    : "Drilldown data pending";

  // Derive recencyTimestamp: formatted timestamp from latest run
  const recencyTimestamp = selectedCluster?.latestRunTimestamp
    ? formatTimestamp(selectedCluster.latestRunTimestamp)
    : "Awaiting run";

  return {
    selectedCluster,
    clusterTriggerReason,
    drilldownSummary,
    recencyTimestamp,
    clusterFresh,
    clusterRecency,
  };
}
