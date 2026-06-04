/**
 * buildDeterministicChecksProps.ts
 *
 * Extracts deterministic next-checks data derivation from App.tsx.
 * Provides a focused seam for deterministic checks panel props construction.
 */

import type {
  DeterministicNextCheckCluster,
  DeterministicNextChecks,
} from "../../types";

export interface BuildDeterministicChecksPropsArgs {
  run: { deterministicNextChecks?: DeterministicNextChecks | null } | null | undefined;
}

export interface DeterministicChecksPropsModel {
  deterministicChecks: DeterministicNextChecks | undefined;
  deterministicClusters: DeterministicNextCheckCluster[];
  hasDeterministicNextChecks: boolean;
  deterministicSummary: string;
}

/**
 * Derives deterministic checks panel props from run data.
 *
 * Behavior-preserving extraction from App.tsx:
 * - deterministicChecks: raw data or undefined
 * - deterministicClusters: clusters array with empty fallback
 * - hasDeterministicNextChecks: boolean indicating if any clusters exist
 * - deterministicSummary: descriptive text for panel display
 */
export function buildDeterministicChecksProps({
  run,
}: BuildDeterministicChecksPropsArgs): DeterministicChecksPropsModel {
  const deterministicChecks = run?.deterministicNextChecks;
  const deterministicClusters = deterministicChecks?.clusters ?? [];
  const hasDeterministicNextChecks = deterministicClusters.length > 0;
  const deterministicSummary = hasDeterministicNextChecks
    ? `${deterministicChecks?.totalNextCheckCount ?? 0} candidate check${
        (deterministicChecks?.totalNextCheckCount ?? 0) === 1 ? "" : "s"
      } to review and promote to the work list`
    : "Review the cluster detail to generate candidate checks.";

  return {
    deterministicChecks,
    deterministicClusters,
    hasDeterministicNextChecks,
    deterministicSummary,
  };
}
