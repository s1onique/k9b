/**
 * usePlannerDataProps — extracted planner data derivation.
 *
 * Responsibilities:
 * - Derive plan candidates from cluster detail
 * - Extract run plan and planner availability from run
 * - Build summary text, status text, and candidate count labels
 * - Compute discovery variant order, counts, and discovered clusters
 *
 * Owned by this hook:
 * - All planner-derived values
 *
 * NOT owned by this hook:
 * - Queue filter state
 * - Cluster detail state
 * - Run selection state
 * - Approval/manual execution handlers
 * - Rendering components
 */
import type { NextCheckPlanCandidate, NextCheckStatusVariant } from "../types";
import { buildDiscoveryVariantCounts, DISCOVERY_VARIANT_ORDER } from "../utils/selectors";
import type { ClusterDetailPayload, RunPayload } from "../types";
import { artifactUrl } from "../utils";

export interface UsePlannerDataPropsOptions {
  /** Cluster detail payload for plan candidates */
  run: RunPayload | null;
  /** Cluster detail payload for plan candidates */
  clusterDetail: ClusterDetailPayload | null;
}

export interface UsePlannerDataPropsResult {
  /** Plan candidates from cluster detail */
  planCandidates: NextCheckPlanCandidate[];
  /** Run plan from run payload */
  runPlan: RunPayload["nextCheckPlan"];
  /** Planner availability from run payload */
  plannerAvailability: RunPayload["plannerAvailability"];
  /** Planner reason string */
  plannerReason: string | null | undefined;
  /** Planner hint string */
  plannerHint: string | null | undefined;
  /** Planner artifact path (availability or run plan fallback) */
  plannerArtifactPath: string | null;
  /** Planner artifact URL */
  plannerArtifactUrl: string | null;
  /** Planner next action hint */
  plannerNextActionHint: string | null | undefined;
  /** Summary text for plan display */
  planSummaryText: string;
  /** Planner reason text fallback */
  plannerReasonText: string;
  /** Label for candidate count display */
  planCandidateCountLabel: string;
  /** Status text for plan */
  planStatusText: string | null;
  /** Run plan candidates array */
  runPlanCandidates: NextCheckPlanCandidate[];
  /** Ordered discovery variants */
  discoveryVariantOrder: NextCheckStatusVariant[];
  /** Counts by discovery variant */
  discoveryVariantCounts: Record<NextCheckStatusVariant, number>;
  /** Unique cluster labels from run plan candidates */
  discoveryClusters: string[];
}

/**
 * usePlannerDataProps — derives all planner-related data from run and cluster detail.
 *
 * Extracts from App.tsx lines ~518-544:
 * - planCandidates: from clusterDetail?.nextCheckPlan
 * - runPlan: from run?.nextCheckPlan
 * - plannerAvailability: from run?.plannerAvailability
 * - plannerReason/Hint/ArtifactPath/ArtifactUrl/NextActionHint: derived from availability + runPlan
 * - planSummaryText: composed from runPlan?.summary ?? plannerReason ?? default
 * - plannerReasonText: fallback reason text
 * - planCandidateCountLabel: candidate count with plural handling
 * - planStatusText: runPlan?.status
 * - runPlanCandidates: from runPlan?.candidates
 * - discoveryVariantOrder: constant DISCOVERY_VARIANT_ORDER
 * - discoveryVariantCounts: buildDiscoveryVariantCounts(runPlanCandidates)
 * - discoveryClusters: unique targetCluster labels from runPlanCandidates
 *
 * Behavior preserved exactly:
 * - Candidate count wording: "candidate" vs "candidates" (singular/plural)
 * - Null/undefined fallbacks: runPlan = run?.nextCheckPlan ?? null, etc.
 * - Variant count/order: same as buildDiscoveryVariantCounts and DISCOVERY_VARIANT_ORDER
 * - Cluster derivation: Array.from(Set(...).filter(Boolean))
 */
export const usePlannerDataProps = (
  options: UsePlannerDataPropsOptions
): UsePlannerDataPropsResult => {
  const { run, clusterDetail } = options;

  // Plan candidates from cluster detail
  const planCandidates: NextCheckPlanCandidate[] = clusterDetail?.nextCheckPlan ?? [];

  // Run plan from run payload
  const runPlan = run?.nextCheckPlan;

  // Planner availability
  const plannerAvailability = run?.plannerAvailability ?? null;
  const plannerReason = plannerAvailability?.reason;
  const plannerHint = plannerAvailability?.hint;

  // Artifact path with fallback to runPlan
  const plannerArtifactPath = plannerAvailability?.artifactPath ?? runPlan?.artifactPath ?? null;
  const plannerArtifactUrl = plannerArtifactPath ? artifactUrl(plannerArtifactPath) : null;
  const plannerNextActionHint = plannerAvailability?.nextActionHint;

  // Summary text composition
  const planSummaryText =
    runPlan?.summary ?? plannerReason ?? "Provider-assisted next-check candidates are available.";
  const plannerReasonText = plannerReason ?? "Planner data is not available for this run.";

  // Candidate count label with plural handling
  const planCandidateCountLabel =
    runPlan?.candidateCount != null
      ? `${runPlan.candidateCount} candidate${runPlan.candidateCount === 1 ? "" : "s"}`
      : `${planCandidates.length} candidate${planCandidates.length === 1 ? "" : "s"}`;

  // Status text
  const planStatusText = runPlan?.status ?? null;

  // Run plan candidates
  const runPlanCandidates: NextCheckPlanCandidate[] = runPlan?.candidates ?? [];

  // Discovery variant ordering
  const discoveryVariantOrder: NextCheckStatusVariant[] = DISCOVERY_VARIANT_ORDER;

  // Discovery variant counts
  const discoveryVariantCounts = buildDiscoveryVariantCounts(runPlanCandidates);

  // Discovered clusters from run plan candidates
  const discoveryClusters = Array.from(
    new Set(
      runPlanCandidates
        .map((candidate) => candidate.targetCluster)
        .filter((label): label is string => Boolean(label))
    )
  );

  return {
    planCandidates,
    runPlan,
    plannerAvailability,
    plannerReason,
    plannerHint,
    plannerArtifactPath,
    plannerArtifactUrl,
    plannerNextActionHint,
    planSummaryText,
    plannerReasonText,
    planCandidateCountLabel,
    planStatusText,
    runPlanCandidates,
    discoveryVariantOrder,
    discoveryVariantCounts,
    discoveryClusters,
  };
};

